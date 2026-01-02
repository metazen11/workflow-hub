"""SQLAlchemy models for Workflow Hub.

Core models (refactored):
- Project: Container for work
- Task: Unit of work with claims
- WorkCycle: Agent work session on a task
- Claim, ClaimTest, ClaimEvidence: Falsification framework

Supporting models:
- Credential, Environment: Deployment
- BugReport: External intake
- Webhook: n8n integration
- RoleConfig: Agent prompts
- LLMSession: Chat history
- TaskAttachment: Task files

Legacy models (deprecated, will be removed):
- Run, RunState: Being replaced by Task workflow
- AgentReport: Being replaced by WorkCycle
- Requirement: Being replaced by Claims
- ThreatIntel: Unused
- WorkCycle, WorkCycleStatus: Renamed to WorkCycle
- TaskPipelineStage: Removed, claims define validation
"""
from app.models.credential import Credential, CredentialType
from app.models.environment import Environment, EnvironmentType
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.work_cycle import WorkCycle, WorkCycleStatus
from app.models.audit import AuditEvent
from app.models.webhook import Webhook
from app.models.bug_report import BugReport, BugReportStatus
from app.models.attachment import TaskAttachment, AttachmentType, validate_file_security, AttachmentSecurityError
from app.models.role_config import RoleConfig
from app.models.deployment_history import DeploymentHistory, DeploymentStatus
from app.models.llm_session import LLMSession
from app.models.llm_job import LLMJob, JobType, JobStatus, JobPriority
from app.models.claim import (
    Claim, ClaimTest, ClaimEvidence,
    ClaimScope, ClaimStatus, ClaimCategory,
    TestType, TestStatus, EvidenceType
)

# Legacy imports for backward compatibility during migration
# TODO: Remove these after migration complete
from app.models.requirement import Requirement
from app.models.run import Run, RunState
from app.models.report import AgentReport, AgentRole
from app.models.threat_intel import ThreatIntel, ThreatStatus
from app.models.proof import Proof, ProofType
from app.models.work_cycle import WorkCycle, WorkCycleStatus

# TaskPipelineStage imported above for backward compatibility


__all__ = [
    # Core models
    'Project',
    'Task',
    'TaskStatus',
    'WorkCycle',
    'WorkCycleStatus',

    # Falsification Framework
    'Claim',
    'ClaimTest',
    'ClaimEvidence',
    'ClaimScope',
    'ClaimStatus',
    'ClaimCategory',
    'TestType',
    'TestStatus',
    'EvidenceType',

    # Supporting models
    'Credential',
    'CredentialType',
    'Environment',
    'EnvironmentType',
    'BugReport',
    'BugReportStatus',
    'TaskAttachment',
    'AttachmentType',
    'validate_file_security',
    'AttachmentSecurityError',
    'RoleConfig',
    'DeploymentHistory',
    'DeploymentStatus',
    'LLMSession',
    'LLMJob',
    'JobType',
    'JobStatus',
    'JobPriority',
    'AuditEvent',
    'Webhook',

    # Legacy (deprecated)
    'Requirement',
    'Run',
    'RunState',
    'AgentReport',
    'AgentRole',
    'ThreatIntel',
    'ThreatStatus',
    'Proof',
    'ProofType',
    'WorkCycle',
    'WorkCycleStatus',
    'TaskPipelineStage',
]
