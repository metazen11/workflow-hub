"""Claim-Test-Evidence service for the Falsification Framework.

This service provides the core logic for managing claims, tests, and evidence.
It handles:
- CRUD operations for claims, tests, and evidence
- Test execution and result capture
- Gate enforcement based on claim validation
- Claim status aggregation and reporting

The goal is to transform the question from "did work get done?" to
"can we prove/disprove specific claims?"
"""
import os
import subprocess
import json
import csv
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from app.models.claim import (
    Claim, ClaimTest, ClaimEvidence,
    ClaimScope, ClaimStatus, ClaimCategory,
    TestType, TestStatus, EvidenceType
)
from app.models.project import Project
from app.models.task import Task
from app.models.run import Run
from app.models.audit import log_event
from app.services.ledger_service import LedgerService


class ClaimService:
    """Service for managing falsification framework: claims, tests, evidence."""

    def __init__(self, db):
        self.db = db

    # -------------------------------------------------------------------------
    # Claim CRUD
    # -------------------------------------------------------------------------

    def create_claim(
        self,
        project_id: int,
        claim_text: str,
        scope: ClaimScope = ClaimScope.PROJECT,
        task_id: int = None,
        category: ClaimCategory = ClaimCategory.OTHER,
        priority: int = 5,
        created_by: str = "user"
    ) -> Tuple[Optional[Claim], Optional[str]]:
        """Create a new claim for a project or task.

        Args:
            project_id: The project this claim belongs to
            claim_text: The falsifiable statement (max 500 chars)
            scope: PROJECT or TASK level
            task_id: Required if scope is TASK
            category: Type of claim (accuracy, performance, etc.)
            priority: 1-10, higher = more important
            created_by: Who created this claim

        Returns:
            (Claim, None) on success, (None, error_message) on failure
        """
        # Validate project exists
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None, "Project not found"

        # Validate task if scope is TASK
        if scope == ClaimScope.TASK:
            if not task_id:
                return None, "task_id required for TASK scope claims"
            task = self.db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return None, "Task not found"
            if task.project_id != project_id:
                return None, "Task does not belong to this project"

        claim = Claim(
            project_id=project_id,
            task_id=task_id if scope == ClaimScope.TASK else None,
            claim_text=claim_text[:500],
            scope=scope,
            category=category,
            priority=priority,
            status=ClaimStatus.PENDING,
            created_by=created_by
        )
        self.db.add(claim)
        self.db.commit()
        self.db.refresh(claim)

        log_event(
            self.db,
            actor=created_by,
            action="create_claim",
            entity_type="claim",
            entity_id=claim.id,
            details={
                "claim_text": claim_text[:100],
                "scope": scope.value,
                "project_id": project_id,
                "task_id": task_id
            }
        )

        return claim, None

    def get_claim(self, claim_id: int) -> Optional[Claim]:
        """Get a claim by ID."""
        return self.db.query(Claim).filter(Claim.id == claim_id).first()

    def get_project_claims(
        self,
        project_id: int,
        include_task_claims: bool = True,
        status_filter: List[ClaimStatus] = None
    ) -> List[Claim]:
        """Get all claims for a project.

        Args:
            project_id: The project ID
            include_task_claims: If True, include task-level claims
            status_filter: Optional list of statuses to filter by

        Returns:
            List of claims
        """
        query = self.db.query(Claim).filter(Claim.project_id == project_id)

        if not include_task_claims:
            query = query.filter(Claim.scope == ClaimScope.PROJECT)

        if status_filter:
            query = query.filter(Claim.status.in_(status_filter))

        return query.order_by(Claim.priority.desc(), Claim.created_at).all()

    def get_task_claims(self, task_id: int, include_project_claims: bool = True) -> List[Claim]:
        """Get all claims applicable to a task.

        Args:
            task_id: The task ID
            include_project_claims: If True, include project-level claims

        Returns:
            List of claims (task-specific + inherited project claims)
        """
        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return []

        claims = []

        # Get task-specific claims
        task_claims = self.db.query(Claim).filter(
            Claim.task_id == task_id,
            Claim.scope == ClaimScope.TASK
        ).all()
        claims.extend(task_claims)

        # Get project-level claims (inherited)
        if include_project_claims:
            project_claims = self.db.query(Claim).filter(
                Claim.project_id == task.project_id,
                Claim.scope == ClaimScope.PROJECT
            ).all()
            claims.extend(project_claims)

        return sorted(claims, key=lambda c: (-c.priority, c.created_at))

    def update_claim(
        self,
        claim_id: int,
        claim_text: str = None,
        category: ClaimCategory = None,
        priority: int = None,
        actor: str = "user"
    ) -> Tuple[Optional[Claim], Optional[str]]:
        """Update a claim's properties."""
        claim = self.get_claim(claim_id)
        if not claim:
            return None, "Claim not found"

        if claim_text is not None:
            claim.claim_text = claim_text[:500]
        if category is not None:
            claim.category = category
        if priority is not None:
            claim.priority = max(1, min(10, priority))

        self.db.commit()
        self.db.refresh(claim)

        log_event(self.db, actor, "update_claim", "claim", claim_id, {})
        return claim, None

    def delete_claim(self, claim_id: int, actor: str = "user") -> Tuple[bool, Optional[str]]:
        """Delete a claim and its associated tests/evidence."""
        claim = self.get_claim(claim_id)
        if not claim:
            return False, "Claim not found"

        log_event(
            self.db, actor, "delete_claim", "claim", claim_id,
            {"claim_text": claim.claim_text[:100]}
        )

        self.db.delete(claim)
        self.db.commit()
        return True, None

    # -------------------------------------------------------------------------
    # Test CRUD & Execution
    # -------------------------------------------------------------------------

    def create_test(
        self,
        claim_id: int,
        name: str,
        test_type: TestType,
        config: Dict[str, Any] = None,
        is_automated: bool = True,
        run_on_stages: List[str] = None,
        timeout_seconds: int = 300
    ) -> Tuple[Optional[ClaimTest], Optional[str]]:
        """Create a test for a claim.

        Args:
            claim_id: The claim this test validates
            name: Human-readable test name
            test_type: Type of test (gold_set, benchmark, etc.)
            config: Test-specific configuration (dataset path, thresholds, etc.)
            is_automated: Can run without human intervention
            run_on_stages: Pipeline stages when to run ["qa", "sec"]
            timeout_seconds: Max execution time

        Returns:
            (ClaimTest, None) on success, (None, error) on failure
        """
        claim = self.get_claim(claim_id)
        if not claim:
            return None, "Claim not found"

        test = ClaimTest(
            claim_id=claim_id,
            name=name,
            test_type=test_type,
            config=config or {},
            is_automated=is_automated,
            run_on_stages=run_on_stages or ["qa"],
            timeout_seconds=timeout_seconds,
            status=TestStatus.PENDING
        )
        self.db.add(test)
        self.db.commit()
        self.db.refresh(test)

        return test, None

    def get_test(self, test_id: int) -> Optional[ClaimTest]:
        """Get a test by ID."""
        return self.db.query(ClaimTest).filter(ClaimTest.id == test_id).first()

    def get_claim_tests(self, claim_id: int) -> List[ClaimTest]:
        """Get all tests for a claim."""
        return self.db.query(ClaimTest).filter(
            ClaimTest.claim_id == claim_id
        ).order_by(ClaimTest.created_at).all()

    def run_test(
        self,
        test_id: int,
        run_id: int = None,
        actor: str = "agent"
    ) -> Tuple[Optional[ClaimEvidence], Optional[str]]:
        """Execute a test and capture evidence.

        Args:
            test_id: The test to run
            run_id: Optional run context
            actor: Who triggered the test

        Returns:
            (ClaimEvidence, None) on success with evidence, (None, error) on failure
        """
        test = self.get_test(test_id)
        if not test:
            return None, "Test not found"

        if not test.is_automated:
            return None, "Test requires manual execution"

        # Mark as running
        test.status = TestStatus.RUNNING
        test.last_run_at = datetime.utcnow()
        self.db.commit()

        # Execute based on test type
        try:
            result = self._execute_test(test)

            # Update test status
            test.status = TestStatus.PASSED if result["passed"] else TestStatus.FAILED
            test.last_result = result
            self.db.commit()

            # Create evidence from result
            evidence = self._create_evidence_from_result(
                test=test,
                result=result,
                run_id=run_id,
                actor=actor
            )

            # Update claim status based on all tests
            self._update_claim_status(test.claim_id)

            # If test failed, create ledger entry and auto-generate tasks
            if not result.get("passed"):
                claim = self.get_claim(test.claim_id)
                if claim:
                    ledger_service = LedgerService(self.db)

                    # Create ledger entry
                    entry_id, _ = ledger_service.create_entry_from_failure(
                        claim=claim,
                        test=test,
                        result=result
                    )

                    # Auto-generate tasks from failure
                    if entry_id:
                        tasks = ledger_service.create_tasks_from_failure(
                            claim=claim,
                            test=test,
                            result=result,
                            entry_id=entry_id
                        )

                        log_event(
                            self.db,
                            actor=actor,
                            action="claim_failed",
                            entity_type="claim",
                            entity_id=claim.id,
                            details={
                                "ledger_entry": entry_id,
                                "tasks_created": len(tasks),
                                "test_name": test.name
                            }
                        )

            return evidence, None

        except Exception as e:
            test.status = TestStatus.ERROR
            test.last_result = {"error": str(e)}
            self.db.commit()
            return None, f"Test execution failed: {e}"

    def _execute_test(self, test: ClaimTest) -> Dict[str, Any]:
        """Execute a test based on its type. Returns result dict."""
        config = test.config or {}

        if test.test_type == TestType.GOLD_SET:
            return self._run_gold_set_test(config)
        elif test.test_type == TestType.BENCHMARK:
            return self._run_benchmark_test(config, test.timeout_seconds)
        elif test.test_type == TestType.UNIT_TEST:
            return self._run_unit_test(config, test.timeout_seconds)
        elif test.test_type == TestType.METRIC_THRESHOLD:
            return self._run_metric_threshold_test(config)
        elif test.test_type == TestType.SCRIPT:
            return self._run_script_test(config, test.timeout_seconds)
        elif test.test_type == TestType.MANUAL_CHECK:
            return {"passed": None, "requires_manual": True}
        else:
            return {"passed": False, "error": f"Unknown test type: {test.test_type}"}

    def _run_gold_set_test(self, config: dict) -> Dict[str, Any]:
        """Compare output against gold-standard dataset.

        Config:
            dataset_path: Path to gold CSV
            output_path: Path to generated output CSV
            metric: Metric to compute (accuracy, f1, etc.)
            threshold: Minimum value to pass
            key_column: Column to match on (optional)
            value_column: Column to compare (optional)
        """
        dataset_path = config.get("dataset_path")
        output_path = config.get("output_path")
        metric = config.get("metric", "accuracy")
        threshold = config.get("threshold", 0.9)
        key_col = config.get("key_column", 0)
        value_col = config.get("value_column", 1)

        if not dataset_path or not output_path:
            return {"passed": False, "error": "Missing dataset_path or output_path"}

        if not os.path.exists(dataset_path):
            return {"passed": False, "error": f"Gold set not found: {dataset_path}"}

        if not os.path.exists(output_path):
            return {"passed": False, "error": f"Output not found: {output_path}"}

        try:
            # Load both files
            gold_data = {}
            with open(dataset_path, newline='') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) > max(key_col, value_col):
                        gold_data[row[key_col]] = row[value_col]

            output_data = {}
            with open(output_path, newline='') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) > max(key_col, value_col):
                        output_data[row[key_col]] = row[value_col]

            # Compare
            total = len(gold_data)
            if total == 0:
                return {"passed": False, "error": "Gold set is empty"}

            matches = sum(1 for k, v in gold_data.items() if output_data.get(k) == v)
            accuracy = matches / total

            failures = [
                {"key": k, "expected": v, "got": output_data.get(k, "<missing>")}
                for k, v in gold_data.items()
                if output_data.get(k) != v
            ][:20]  # Limit to 20 failures

            passed = accuracy >= threshold

            return {
                "passed": passed,
                "metric": metric,
                "value": round(accuracy, 4),
                "threshold": threshold,
                "total": total,
                "matches": matches,
                "failures": failures
            }

        except Exception as e:
            return {"passed": False, "error": str(e)}

    def _run_benchmark_test(self, config: dict, timeout: int) -> Dict[str, Any]:
        """Run a benchmark command and parse metrics.

        Config:
            command: Command to run
            metric: Metric name to extract
            threshold: Value to compare against
            comparison: "gte" (>=), "lte" (<=), "eq" (==)
            metric_regex: Optional regex to extract metric
        """
        command = config.get("command")
        metric = config.get("metric", "result")
        threshold = config.get("threshold", 0)
        comparison = config.get("comparison", "gte")

        if not command:
            return {"passed": False, "error": "Missing command"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout + result.stderr

            # Try to parse metric from output
            # Look for patterns like "metric: value" or JSON output
            value = None

            # Try JSON first
            try:
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    value = data.get(metric)
            except json.JSONDecodeError:
                pass

            # Try simple pattern matching
            if value is None:
                import re
                pattern = rf"{metric}\s*[:=]\s*([\d.]+)"
                match = re.search(pattern, output, re.IGNORECASE)
                if match:
                    value = float(match.group(1))

            if value is None:
                return {
                    "passed": False,
                    "error": f"Could not extract metric '{metric}' from output",
                    "output": output[:1000]
                }

            # Compare
            if comparison == "gte":
                passed = value >= threshold
            elif comparison == "lte":
                passed = value <= threshold
            elif comparison == "eq":
                passed = value == threshold
            else:
                passed = value >= threshold

            return {
                "passed": passed,
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "comparison": comparison,
                "output": output[:1000]
            }

        except subprocess.TimeoutExpired:
            return {"passed": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"passed": False, "error": str(e)}

    def _run_unit_test(self, config: dict, timeout: int) -> Dict[str, Any]:
        """Run unit tests with pytest.

        Config:
            test_path: Path to test file or directory
            markers: Optional pytest markers to filter
            min_passed: Minimum tests that must pass
        """
        test_path = config.get("test_path", "tests/")
        markers = config.get("markers")
        min_passed = config.get("min_passed", 1)

        cmd = ["pytest", test_path, "-v", "--tb=short", "--json-report", "--json-report-file=/tmp/pytest_report.json"]
        if markers:
            cmd.extend(["-m", markers])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            # Try to parse JSON report
            try:
                with open("/tmp/pytest_report.json") as f:
                    report = json.load(f)

                summary = report.get("summary", {})
                passed = summary.get("passed", 0)
                failed = summary.get("failed", 0)
                errors = summary.get("error", 0)

                test_passed = failed == 0 and errors == 0 and passed >= min_passed

                failures = []
                for test in report.get("tests", []):
                    if test.get("outcome") in ("failed", "error"):
                        failures.append({
                            "name": test.get("nodeid"),
                            "outcome": test.get("outcome"),
                            "message": test.get("call", {}).get("crash", {}).get("message", "")[:200]
                        })

                return {
                    "passed": test_passed,
                    "tests_passed": passed,
                    "tests_failed": failed,
                    "tests_error": errors,
                    "failures": failures[:10]
                }
            except Exception:
                # Fallback: check exit code
                return {
                    "passed": result.returncode == 0,
                    "output": result.stdout[:1000],
                    "stderr": result.stderr[:500]
                }

        except subprocess.TimeoutExpired:
            return {"passed": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"passed": False, "error": str(e)}

    def _run_metric_threshold_test(self, config: dict) -> Dict[str, Any]:
        """Check a metric against a threshold.

        Config:
            metric_file: Path to JSON file with metrics
            metric_name: Name of metric to check
            threshold: Value to compare against
            comparison: "gte", "lte", "eq"
        """
        metric_file = config.get("metric_file")
        metric_name = config.get("metric_name")
        threshold = config.get("threshold", 0)
        comparison = config.get("comparison", "gte")

        if not metric_file or not metric_name:
            return {"passed": False, "error": "Missing metric_file or metric_name"}

        if not os.path.exists(metric_file):
            return {"passed": False, "error": f"Metric file not found: {metric_file}"}

        try:
            with open(metric_file) as f:
                data = json.load(f)

            # Navigate to metric (supports dot notation)
            value = data
            for key in metric_name.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break

            if value is None:
                return {"passed": False, "error": f"Metric '{metric_name}' not found"}

            # Compare
            if comparison == "gte":
                passed = value >= threshold
            elif comparison == "lte":
                passed = value <= threshold
            elif comparison == "eq":
                passed = value == threshold
            else:
                passed = value >= threshold

            return {
                "passed": passed,
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "comparison": comparison
            }

        except Exception as e:
            return {"passed": False, "error": str(e)}

    def _run_script_test(self, config: dict, timeout: int) -> Dict[str, Any]:
        """Run an arbitrary script and check exit code.

        Config:
            command: Command/script to run
            working_dir: Optional working directory
            expect_exit_code: Expected exit code (default 0)
        """
        command = config.get("command")
        working_dir = config.get("working_dir")
        expect_exit_code = config.get("expect_exit_code", 0)

        if not command:
            return {"passed": False, "error": "Missing command"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir
            )

            passed = result.returncode == expect_exit_code

            return {
                "passed": passed,
                "exit_code": result.returncode,
                "expected_exit_code": expect_exit_code,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500]
            }

        except subprocess.TimeoutExpired:
            return {"passed": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"passed": False, "error": str(e)}

    def _create_evidence_from_result(
        self,
        test: ClaimTest,
        result: Dict[str, Any],
        run_id: int = None,
        actor: str = "agent"
    ) -> ClaimEvidence:
        """Create evidence from a test result."""
        passed = result.get("passed")
        supports_claim = True if passed else (False if passed is False else None)

        # Determine evidence type
        if "failures" in result:
            evidence_type = EvidenceType.DIFF_LOG
        elif "metric" in result:
            evidence_type = EvidenceType.METRICS_JSON
        elif "output" in result:
            evidence_type = EvidenceType.TEST_OUTPUT
        else:
            evidence_type = EvidenceType.OTHER

        # Build title
        if passed:
            title = f"PASS: {test.name}"
        elif passed is False:
            title = f"FAIL: {test.name}"
        else:
            title = f"INCONCLUSIVE: {test.name}"

        # Extract metrics
        metrics = {}
        for key in ["metric", "value", "threshold", "tests_passed", "tests_failed", "accuracy"]:
            if key in result:
                metrics[key] = result[key]

        # Extract failures
        failures = result.get("failures", [])

        # Build verdict reason
        if "error" in result:
            verdict_reason = f"Error: {result['error']}"
        elif passed:
            value = result.get("value", "N/A")
            threshold = result.get("threshold", "N/A")
            verdict_reason = f"Value {value} meets threshold {threshold}"
        else:
            value = result.get("value", "N/A")
            threshold = result.get("threshold", "N/A")
            fail_count = len(failures)
            verdict_reason = f"Value {value} below threshold {threshold}. {fail_count} failures."

        evidence = ClaimEvidence(
            claim_id=test.claim_id,
            test_id=test.id,
            run_id=run_id,
            title=title,
            evidence_type=evidence_type,
            content=json.dumps(result, indent=2)[:5000],  # Store full result
            metrics=metrics,
            failures=failures,
            supports_claim=supports_claim,
            verdict_reason=verdict_reason,
            created_by=actor
        )
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)

        return evidence

    # -------------------------------------------------------------------------
    # Evidence CRUD
    # -------------------------------------------------------------------------

    def capture_evidence(
        self,
        claim_id: int,
        title: str,
        evidence_type: EvidenceType = EvidenceType.OTHER,
        content: str = None,
        filename: str = None,
        filepath: str = None,
        metrics: Dict[str, Any] = None,
        failures: List[Dict] = None,
        supports_claim: bool = None,
        verdict_reason: str = None,
        test_id: int = None,
        run_id: int = None,
        created_by: str = "agent"
    ) -> Tuple[Optional[ClaimEvidence], Optional[str]]:
        """Manually capture evidence for a claim.

        This is used when evidence comes from external sources, manual checks,
        or when tests are run outside the framework.

        Returns:
            (ClaimEvidence, None) on success, (None, error) on failure
        """
        claim = self.get_claim(claim_id)
        if not claim:
            return None, "Claim not found"

        evidence = ClaimEvidence(
            claim_id=claim_id,
            test_id=test_id,
            run_id=run_id,
            title=title,
            evidence_type=evidence_type,
            content=content,
            filename=filename,
            filepath=filepath,
            metrics=metrics,
            failures=failures,
            supports_claim=supports_claim,
            verdict_reason=verdict_reason,
            created_by=created_by
        )
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)

        # Update claim status
        self._update_claim_status(claim_id)

        return evidence, None

    def get_evidence(self, evidence_id: int) -> Optional[ClaimEvidence]:
        """Get evidence by ID."""
        return self.db.query(ClaimEvidence).filter(ClaimEvidence.id == evidence_id).first()

    def get_claim_evidence(
        self,
        claim_id: int,
        run_id: int = None
    ) -> List[ClaimEvidence]:
        """Get all evidence for a claim, optionally filtered by run."""
        query = self.db.query(ClaimEvidence).filter(ClaimEvidence.claim_id == claim_id)
        if run_id:
            query = query.filter(ClaimEvidence.run_id == run_id)
        return query.order_by(ClaimEvidence.created_at.desc()).all()

    # -------------------------------------------------------------------------
    # Claim Status & Validation
    # -------------------------------------------------------------------------

    def _update_claim_status(self, claim_id: int) -> None:
        """Update claim status based on all evidence and test results."""
        claim = self.get_claim(claim_id)
        if not claim:
            return

        tests = self.get_claim_tests(claim_id)
        evidence = self.get_claim_evidence(claim_id)

        if not tests and not evidence:
            claim.status = ClaimStatus.PENDING
            claim.status_reason = "No tests or evidence yet"
        else:
            # Check test results
            test_statuses = [t.status for t in tests]
            any_failed = TestStatus.FAILED in test_statuses or TestStatus.ERROR in test_statuses
            all_passed = all(s == TestStatus.PASSED for s in test_statuses) if test_statuses else True

            # Check evidence verdicts
            evidence_verdicts = [e.supports_claim for e in evidence]
            any_falsified = False in evidence_verdicts
            any_validated = True in evidence_verdicts

            if any_failed or any_falsified:
                claim.status = ClaimStatus.FALSIFIED
                claim.status_reason = "One or more tests failed or evidence contradicts claim"
            elif all_passed and any_validated:
                claim.status = ClaimStatus.VALIDATED
                claim.status_reason = "All tests passed and evidence supports claim"
            else:
                claim.status = ClaimStatus.INCONCLUSIVE
                claim.status_reason = "Mixed or incomplete results"

        self.db.commit()

    def validate_claims_for_run(
        self,
        run_id: int
    ) -> Dict[str, Any]:
        """Check all claims have evidence for a run.

        Returns validation summary:
        {
            "valid": True/False,
            "total_claims": N,
            "validated": N,
            "falsified": N,
            "pending": N,
            "missing_evidence": [list of claim IDs],
            "failed_claims": [list of claim IDs]
        }
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"valid": False, "error": "Run not found"}

        # Get all applicable claims (project + task)
        claims = self.get_project_claims(run.project_id, include_task_claims=True)

        validated = 0
        falsified = 0
        pending = 0
        missing_evidence = []
        failed_claims = []

        for claim in claims:
            # Check for run-specific evidence
            run_evidence = self.get_claim_evidence(claim.id, run_id=run_id)

            if not run_evidence:
                missing_evidence.append(claim.id)
                pending += 1
            elif claim.status == ClaimStatus.VALIDATED:
                validated += 1
            elif claim.status == ClaimStatus.FALSIFIED:
                falsified += 1
                failed_claims.append(claim.id)
            else:
                pending += 1

        valid = len(missing_evidence) == 0 and len(failed_claims) == 0

        return {
            "valid": valid,
            "total_claims": len(claims),
            "validated": validated,
            "falsified": falsified,
            "pending": pending,
            "missing_evidence": missing_evidence,
            "failed_claims": failed_claims
        }

    def can_advance_gate(
        self,
        run_id: int,
        gate: str
    ) -> Tuple[bool, List[int]]:
        """Check if a run can advance through a gate based on claims.

        Args:
            run_id: The run to check
            gate: The gate to check (qa, sec, etc.)

        Returns:
            (can_advance, list_of_blocking_claim_ids)
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return False, []

        project = self.db.query(Project).filter(Project.id == run.project_id).first()
        if not project:
            return False, []

        # If enforcement not enabled, always allow
        if not project.require_evidence_for_gates:
            return True, []

        # Get claims that should run on this stage
        all_claims = self.get_project_claims(run.project_id, include_task_claims=True)

        blocking = []
        for claim in all_claims:
            # Check if any tests should run on this gate
            for test in claim.tests:
                if gate in (test.run_on_stages or []):
                    # This test should run at this gate
                    if test.status != TestStatus.PASSED:
                        blocking.append(claim.id)
                        break  # One failing test is enough to block

        return len(blocking) == 0, blocking

    def run_tests_for_stage(
        self,
        run_id: int,
        stage: str,
        actor: str = "agent"
    ) -> Dict[str, Any]:
        """Run all tests configured for a pipeline stage.

        Args:
            run_id: The run context
            stage: Pipeline stage (qa, sec, etc.)
            actor: Who triggered the tests

        Returns:
            Summary of test results
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"error": "Run not found"}

        claims = self.get_project_claims(run.project_id, include_task_claims=True)

        results = {
            "stage": stage,
            "run_id": run_id,
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "details": []
        }

        for claim in claims:
            for test in claim.tests:
                if stage in (test.run_on_stages or []) and test.is_automated:
                    evidence, error = self.run_test(test.id, run_id=run_id, actor=actor)

                    results["tests_run"] += 1
                    if error:
                        results["errors"] += 1
                        results["details"].append({
                            "test_id": test.id,
                            "name": test.name,
                            "status": "error",
                            "error": error
                        })
                    elif evidence and evidence.supports_claim:
                        results["passed"] += 1
                        results["details"].append({
                            "test_id": test.id,
                            "name": test.name,
                            "status": "passed"
                        })
                    else:
                        results["failed"] += 1
                        results["details"].append({
                            "test_id": test.id,
                            "name": test.name,
                            "status": "failed",
                            "verdict_reason": evidence.verdict_reason if evidence else None
                        })

        return results

    def get_claims_summary(self, project_id: int) -> Dict[str, Any]:
        """Get summary of claims status for a project.

        Returns:
        {
            "total": N,
            "by_status": {"pending": N, "validated": N, ...},
            "by_category": {"accuracy": N, ...},
            "falsification_rate": 0.0-1.0
        }
        """
        claims = self.get_project_claims(project_id)

        by_status = {}
        by_category = {}

        for claim in claims:
            status = claim.status.value if claim.status else "pending"
            by_status[status] = by_status.get(status, 0) + 1

            category = claim.category.value if claim.category else "other"
            by_category[category] = by_category.get(category, 0) + 1

        total = len(claims)
        falsified = by_status.get("falsified", 0)
        validated = by_status.get("validated", 0)

        tested = falsified + validated
        falsification_rate = (falsified / tested) if tested > 0 else 0.0

        return {
            "total": total,
            "by_status": by_status,
            "by_category": by_category,
            "falsification_rate": round(falsification_rate, 3)
        }
