"""Ledger Service for Failed Claims tracking.

Auto-generates ledger entries and tasks when claims fail falsification.
Implements the Non-Resurrection Rule: failed claims cannot be retried
unless failure modes are explicitly addressed.
"""
import os
import yaml
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from django.conf import settings

from app.models.claim import Claim, ClaimTest, ClaimEvidence, ClaimStatus, TestStatus
from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.project import Project


class LedgerService:
    """Service for managing the Failed Claims Ledger."""

    def __init__(self, db):
        self.db = db
        self.ledger_path = os.path.join(settings.BASE_DIR, 'ledger')
        self.index_path = os.path.join(self.ledger_path, 'failed_claims.yaml')
        self.claims_dir = os.path.join(self.ledger_path, 'failed_claims')

        # Ensure directories exist
        os.makedirs(self.claims_dir, exist_ok=True)

    def _generate_entry_id(self) -> str:
        """Generate next ledger entry ID."""
        year = datetime.utcnow().year

        # Find existing entries for this year
        existing = []
        if os.path.exists(self.index_path):
            with open(self.index_path, 'r') as f:
                index = yaml.safe_load(f) or {}
                for entry in index.get('entries', []):
                    entry_id = entry.get('id', '')
                    if entry_id.startswith(f'FC-{year}-'):
                        try:
                            num = int(entry_id.split('-')[-1])
                            existing.append(num)
                        except ValueError:
                            pass

        next_num = max(existing, default=0) + 1
        return f"FC-{year}-{next_num:03d}"

    def create_entry_from_failure(
        self,
        claim: Claim,
        test: ClaimTest,
        result: Dict[str, Any],
        failure_modes: List[str] = None,
        lesson: str = None,
        decision: str = None,
        revisit: str = None
    ) -> Tuple[str, Optional[str]]:
        """Create a ledger entry from a failed claim test.

        Args:
            claim: The claim that failed
            test: The test that produced the failure
            result: The test result dict
            failure_modes: List of specific failure reasons
            lesson: Insight gained from failure
            decision: Action taken as result
            revisit: Conditions for reconsidering

        Returns:
            (entry_id, error) tuple
        """
        entry_id = self._generate_entry_id()
        project = self.db.query(Project).filter(Project.id == claim.project_id).first()
        project_name = project.name if project else "unknown"

        # Extract failure details from result
        if not failure_modes:
            failure_modes = []
            if result.get('failures'):
                # Extract from detailed failures
                for f in result.get('failures', [])[:5]:
                    if isinstance(f, dict):
                        failure_modes.append(f.get('key', str(f)))
                    else:
                        failure_modes.append(str(f))
            if result.get('error'):
                failure_modes.append(result['error'])

        # Build result summary
        result_summary = {}
        if 'value' in result:
            result_summary['value'] = result['value']
        if 'threshold' in result:
            result_summary['threshold'] = result['threshold']
        if 'accuracy' in result:
            result_summary['accuracy'] = result['accuracy']
        if 'total' in result:
            result_summary['total'] = result['total']
        if 'matches' in result:
            result_summary['matches'] = result['matches']

        # Build failure condition from test config
        config = test.config or {}
        threshold = config.get('threshold')
        comparison = config.get('comparison', 'gte')
        metric = config.get('metric', result.get('metric', 'value'))

        if threshold is not None:
            if comparison == 'gte':
                failure_condition = f"{metric} < {threshold}"
            elif comparison == 'lte':
                failure_condition = f"{metric} > {threshold}"
            else:
                failure_condition = f"{metric} != {threshold}"
        else:
            failure_condition = "test failed"

        # Auto-generate lesson if not provided
        if not lesson:
            value = result.get('value', result.get('accuracy', 'N/A'))
            lesson = f"Test failed: {metric} was {value}, needed {threshold or 'passing'}"

        # Auto-generate decision if not provided
        if not decision:
            decision = "Requires investigation and corrective action"

        # Auto-generate revisit conditions
        if not revisit:
            revisit = "Only after addressing the identified failure modes"

        entry = {
            'id': entry_id,
            'date': datetime.utcnow().strftime('%Y-%m-%d'),
            'project': project_name.lower().replace(' ', '_'),
            'claim': claim.claim_text,
            'claim_id': claim.id,
            'test': {
                'method': test.test_type.value if test.test_type else 'unknown',
                'name': test.name,
                'config': config
            },
            'failure_condition': failure_condition,
            'result': result_summary if result_summary else result,
            'status': 'failed',
            'failure_mode': failure_modes,
            'lesson': lesson,
            'decision': decision,
            'revisit': revisit
        }

        # Write entry file
        entry_file = os.path.join(self.claims_dir, f"{entry_id}.yaml")
        with open(entry_file, 'w') as f:
            yaml.dump(entry, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # Update index
        self._add_to_index(entry_id, datetime.utcnow().strftime('%Y-%m-%d'),
                          project_name.lower().replace(' ', '_'), claim.claim_text[:80])

        return entry_id, None

    def _add_to_index(self, entry_id: str, date: str, project: str, claim_summary: str):
        """Add entry to the index file."""
        index = {'entries': []}

        if os.path.exists(self.index_path):
            with open(self.index_path, 'r') as f:
                index = yaml.safe_load(f) or {'entries': []}

        index['entries'].append({
            'id': entry_id,
            'date': date,
            'project': project,
            'claim_summary': claim_summary,
            'status': 'failed'
        })

        with open(self.index_path, 'w') as f:
            yaml.dump(index, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def create_tasks_from_failure(
        self,
        claim: Claim,
        test: ClaimTest,
        result: Dict[str, Any],
        entry_id: str
    ) -> List[Task]:
        """Auto-generate tasks from failure modes.

        Creates one task per failure mode, plus a general investigation task.

        Args:
            claim: The failed claim
            test: The test that failed
            result: The test result
            entry_id: The ledger entry ID

        Returns:
            List of created tasks
        """
        tasks = []
        project = self.db.query(Project).filter(Project.id == claim.project_id).first()

        if not project:
            return tasks

        # Get existing task count for numbering
        existing_count = self.db.query(Task).filter(Task.project_id == claim.project_id).count()
        task_num = existing_count + 1

        # Extract failures
        failures = result.get('failures', [])
        error = result.get('error')

        # Create investigation task
        investigation_task = Task(
            project_id=claim.project_id,
            task_id=f"T{task_num:03d}",
            title=f"Investigate failed claim: {claim.claim_text[:50]}",
            description=f"""Ledger Entry: {entry_id}

Claim: {claim.claim_text}

Test: {test.name} ({test.test_type.value if test.test_type else 'unknown'})

Result: {result.get('value', 'N/A')} (threshold: {result.get('threshold', 'N/A')})

This claim failed falsification testing. Investigate the root cause and determine:
1. Is the claim achievable with modifications?
2. Should the scope be narrowed?
3. What specific changes are needed?

See ledger entry {entry_id} for full details.""",
            status=TaskStatus.BACKLOG,
            pipeline_stage=TaskPipelineStage.DEV,
            priority=8,  # High priority for failures
            acceptance_criteria=[
                f"Root cause identified for ledger entry {entry_id}",
                "Decision documented: narrow scope, modify approach, or deprecate claim",
                "If continuing: new tasks created with specific fixes"
            ]
        )
        self.db.add(investigation_task)
        tasks.append(investigation_task)
        task_num += 1

        # Create task for each specific failure (up to 5)
        failure_items = failures[:5] if failures else []

        for i, failure in enumerate(failure_items):
            if isinstance(failure, dict):
                failure_desc = f"Key: {failure.get('key', 'N/A')}, Expected: {failure.get('expected', 'N/A')}, Got: {failure.get('got', 'N/A')}"
                failure_title = str(failure.get('key', f'failure_{i+1}'))[:30]
            else:
                failure_desc = str(failure)
                failure_title = str(failure)[:30]

            task = Task(
                project_id=claim.project_id,
                task_id=f"T{task_num:03d}",
                title=f"Fix: {failure_title}",
                description=f"""Ledger Entry: {entry_id}

Specific failure from claim test:
{failure_desc}

Parent claim: {claim.claim_text[:100]}

Fix this specific failure case.""",
                status=TaskStatus.BACKLOG,
                pipeline_stage=TaskPipelineStage.DEV,
                priority=7,
                acceptance_criteria=[
                    f"This specific case passes: {failure_title}",
                    "No regression in other test cases"
                ]
            )
            self.db.add(task)
            tasks.append(task)
            task_num += 1

        # If there was an error, create task for that
        if error and not failures:
            task = Task(
                project_id=claim.project_id,
                task_id=f"T{task_num:03d}",
                title=f"Fix error: {str(error)[:40]}",
                description=f"""Ledger Entry: {entry_id}

Test error: {error}

The test itself failed to execute properly. Fix the underlying issue.

Claim: {claim.claim_text[:100]}""",
                status=TaskStatus.BACKLOG,
                pipeline_stage=TaskPipelineStage.DEV,
                priority=9,  # Errors are highest priority
                acceptance_criteria=[
                    "Test executes without error",
                    "Claim can be properly evaluated"
                ]
            )
            self.db.add(task)
            tasks.append(task)

        self.db.commit()

        # Refresh all tasks
        for task in tasks:
            self.db.refresh(task)

        return tasks

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a ledger entry by ID."""
        entry_file = os.path.join(self.claims_dir, f"{entry_id}.yaml")
        if not os.path.exists(entry_file):
            return None

        with open(entry_file, 'r') as f:
            return yaml.safe_load(f)

    def get_all_entries(self) -> List[Dict[str, Any]]:
        """Get all ledger entries."""
        entries = []

        if not os.path.exists(self.index_path):
            return entries

        with open(self.index_path, 'r') as f:
            index = yaml.safe_load(f) or {}

        for entry_ref in index.get('entries', []):
            entry = self.get_entry(entry_ref.get('id', ''))
            if entry:
                entries.append(entry)

        return sorted(entries, key=lambda x: str(x.get('date', '')), reverse=True)

    def check_resurrection_allowed(self, claim_id: int) -> Tuple[bool, Optional[str]]:
        """Check if a failed claim can be retried (Non-Resurrection Rule).

        A claim can only be retried if:
        1. It has no failed ledger entries, OR
        2. All failure modes have been addressed (tasks completed)

        Returns:
            (allowed, reason) tuple
        """
        # Find ledger entries for this claim
        entries = self.get_all_entries()
        claim_entries = [e for e in entries if e.get('claim_id') == claim_id]

        if not claim_entries:
            return True, None

        # Check if there are open tasks related to these entries
        for entry in claim_entries:
            entry_id = entry.get('id', '')

            # Find tasks that reference this entry
            related_tasks = self.db.query(Task).filter(
                Task.description.contains(entry_id)
            ).all()

            # Check if all related tasks are done
            incomplete = [t for t in related_tasks if t.status != TaskStatus.DONE]

            if incomplete:
                return False, f"Ledger entry {entry_id} has {len(incomplete)} incomplete tasks. Complete them before retrying this claim."

        return True, "All failure modes addressed"
