"""Claim-Test-Evidence models for the Falsification Framework.

This module implements the core "Claim → Test → Evidence" contract:
- Claim: A falsifiable statement about what the system must do
- ClaimTest: A predefined test that can validate/falsify the claim
- ClaimEvidence: Evidence captured from test execution

The framework transforms workflow from "did work get done?" to
"can we prove/disprove specific claims?"

Example (BeatBridge):
- Claim: "Downbeat detection accuracy ≥90% on gold set"
- Test: Gold-set comparison against verified dataset
- Evidence: CSV of results, accuracy metrics, failure list
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
    Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
import enum

from app.db import Base


class ClaimScope(enum.Enum):
    """Scope of a claim."""
    PROJECT = "project"  # Applies to entire project
    TASK = "task"  # Applies to specific task


class ClaimStatus(enum.Enum):
    """Status of claim validation."""
    PENDING = "pending"  # Not yet tested
    VALIDATED = "validated"  # Tests passed, claim holds
    FALSIFIED = "falsified"  # Tests failed, claim disproven
    SKIPPED = "skipped"  # Explicitly skipped (with reason)
    INCONCLUSIVE = "inconclusive"  # Tests ran but result unclear


class ClaimCategory(enum.Enum):
    """Category of claim."""
    ACCURACY = "accuracy"  # Correctness of output
    PERFORMANCE = "performance"  # Speed, throughput
    SECURITY = "security"  # Security properties
    RELIABILITY = "reliability"  # Uptime, error rates
    USABILITY = "usability"  # User experience
    COMPATIBILITY = "compatibility"  # Integration, standards
    OTHER = "other"


class TestType(enum.Enum):
    """Types of claim tests."""
    GOLD_SET = "gold_set"  # Compare against verified dataset
    BENCHMARK = "benchmark"  # Run command, parse metrics
    UNIT_TEST = "unit_test"  # Run pytest/jest
    METRIC_THRESHOLD = "metric_threshold"  # Query metrics, check threshold
    SCRIPT = "script"  # Run arbitrary script, check exit code
    MANUAL_CHECK = "manual_check"  # Human verification required


class TestStatus(enum.Enum):
    """Status of test execution."""
    PENDING = "pending"  # Not yet run
    RUNNING = "running"  # Currently executing
    PASSED = "passed"  # Test passed
    FAILED = "failed"  # Test failed
    ERROR = "error"  # Test errored (couldn't complete)
    SKIPPED = "skipped"  # Explicitly skipped


class EvidenceType(enum.Enum):
    """Types of evidence artifacts."""
    METRICS_JSON = "metrics_json"  # Machine-readable metrics
    DIFF_LOG = "diff_log"  # Comparison results
    TEST_OUTPUT = "test_output"  # Raw test output
    CSV_REPORT = "csv_report"  # Tabular results
    SCREENSHOT = "screenshot"  # Visual evidence
    LOG_FILE = "log_file"  # Execution logs
    OTHER = "other"


class Claim(Base):
    """A falsifiable claim about what the system must do.

    Claims can be defined at project level (applies to all tasks) or
    task level (applies to specific task).

    Example claims:
    - "Downbeat detection accuracy ≥90% on gold set" (accuracy)
    - "API response time <200ms for 95th percentile" (performance)
    - "No SQL injection vulnerabilities in user input handlers" (security)
    """
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)

    # Ownership - project is required, task is optional
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)

    # Claim definition
    claim_text = Column(String(500), nullable=False)  # The falsifiable statement
    scope = Column(SQLEnum(ClaimScope), default=ClaimScope.PROJECT)
    category = Column(SQLEnum(ClaimCategory), default=ClaimCategory.OTHER)
    priority = Column(Integer, default=5)  # 1-10, higher = more important

    # Status tracking
    status = Column(SQLEnum(ClaimStatus), default=ClaimStatus.PENDING)
    status_reason = Column(Text, nullable=True)  # Why status changed

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    created_by = Column(String(100), default="user")  # user, agent, system

    # Relationships
    project = relationship("Project", backref="claims")
    task = relationship("Task", backref="claims")
    tests = relationship("ClaimTest", back_populates="claim", cascade="all, delete-orphan")
    evidence = relationship("ClaimEvidence", back_populates="claim", cascade="all, delete-orphan")

    def to_dict(self, include_tests=False, include_evidence=False):
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "claim_text": self.claim_text,
            "scope": self.scope.value if self.scope else "project",
            "category": self.category.value if self.category else "other",
            "priority": self.priority,
            "status": self.status.value if self.status else "pending",
            "status_reason": self.status_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }

        if include_tests:
            result["tests"] = [t.to_dict() for t in self.tests]

        if include_evidence:
            result["evidence"] = [e.to_dict() for e in self.evidence]

        return result

    def __repr__(self):
        return f"<Claim {self.id}: {self.claim_text[:50]}... ({self.status.value if self.status else 'pending'})>"


class ClaimTest(Base):
    """A predefined test that can validate/falsify a claim.

    Tests are defined upfront - before any work is done. This ensures
    we know how to falsify a claim before we try to validate it.

    The config JSON stores test-specific parameters:
    - gold_set: {"dataset_path": "/data/gold.csv", "metric": "accuracy", "threshold": 0.90}
    - benchmark: {"command": "python bench.py", "metric": "latency_p95", "threshold": 200}
    - unit_test: {"test_path": "tests/test_api.py", "markers": "security"}
    - metric_threshold: {"metric_name": "error_rate", "threshold": 0.01, "comparison": "lte"}
    - script: {"command": "./validate.sh", "timeout": 300}
    - manual_check: {"checklist": ["Verify login flow", "Check error messages"]}
    """
    __tablename__ = "claim_tests"

    id = Column(Integer, primary_key=True)

    # Parent claim
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False, index=True)

    # Test definition
    name = Column(String(255), nullable=False)  # Human-readable test name
    test_type = Column(SQLEnum(TestType), nullable=False)
    config = Column(JSON, default=dict)  # Test-specific configuration

    # Execution settings
    is_automated = Column(Boolean, default=True)  # Can run without human
    run_on_stages = Column(JSON, default=list)  # ["qa", "sec"] - when to run
    timeout_seconds = Column(Integer, default=300)  # Max execution time

    # Status tracking
    status = Column(SQLEnum(TestStatus), default=TestStatus.PENDING)
    last_run_at = Column(DateTime, nullable=True)
    last_result = Column(JSON, nullable=True)  # Output from last run

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    claim = relationship("Claim", back_populates="tests")
    evidence = relationship("ClaimEvidence", back_populates="test", cascade="all, delete-orphan")

    def to_dict(self, include_evidence=False):
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "claim_id": self.claim_id,
            "name": self.name,
            "test_type": self.test_type.value if self.test_type else None,
            "config": self.config or {},
            "is_automated": self.is_automated,
            "run_on_stages": self.run_on_stages or [],
            "timeout_seconds": self.timeout_seconds,
            "status": self.status.value if self.status else "pending",
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_result": self.last_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        if include_evidence:
            result["evidence"] = [e.to_dict() for e in self.evidence]

        return result

    def __repr__(self):
        return f"<ClaimTest {self.id}: {self.name} ({self.test_type.value if self.test_type else 'unknown'})>"


class ClaimEvidence(Base):
    """Evidence captured from test execution.

    Evidence is the proof that a test ran and what it found.
    It can support (validate) or contradict (falsify) a claim.

    Evidence types:
    - metrics_json: {"accuracy": 0.92, "f1_score": 0.89}
    - diff_log: Text showing expected vs actual
    - csv_report: Path to detailed results file
    - screenshot: Path to visual evidence
    """
    __tablename__ = "claim_evidence"

    id = Column(Integer, primary_key=True)

    # Parent relationships
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False, index=True)
    test_id = Column(Integer, ForeignKey("claim_tests.id"), nullable=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True, index=True)

    # Evidence metadata
    title = Column(String(255), nullable=False)
    evidence_type = Column(SQLEnum(EvidenceType), default=EvidenceType.OTHER)

    # Content - either inline or file-based
    content = Column(Text, nullable=True)  # Inline content (for small data)
    filename = Column(String(255), nullable=True)  # File name
    filepath = Column(Text, nullable=True)  # Full path to file

    # Structured data
    metrics = Column(JSON, nullable=True)  # Machine-readable metrics
    failures = Column(JSON, nullable=True)  # List of specific failures

    # Verdict
    supports_claim = Column(Boolean, nullable=True)  # True=validates, False=falsifies, None=inconclusive
    verdict_reason = Column(Text, nullable=True)  # Explanation of verdict

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), default="agent")  # agent, human, system

    # Relationships
    claim = relationship("Claim", back_populates="evidence")
    test = relationship("ClaimTest", back_populates="evidence")
    run = relationship("Run", backref="claim_evidence")

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "test_id": self.test_id,
            "run_id": self.run_id,
            "title": self.title,
            "evidence_type": self.evidence_type.value if self.evidence_type else "other",
            "content": self.content,
            "filename": self.filename,
            "filepath": self.filepath,
            "metrics": self.metrics,
            "failures": self.failures,
            "supports_claim": self.supports_claim,
            "verdict_reason": self.verdict_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }

    def to_summary(self):
        """Compact format for summaries."""
        verdict = "✓" if self.supports_claim else ("✗" if self.supports_claim is False else "?")
        return {
            "id": self.id,
            "title": self.title,
            "type": self.evidence_type.value if self.evidence_type else "other",
            "verdict": verdict,
            "metrics": self.metrics,
        }

    def __repr__(self):
        verdict = "validates" if self.supports_claim else ("falsifies" if self.supports_claim is False else "inconclusive")
        return f"<ClaimEvidence {self.id}: {self.title} ({verdict})>"
