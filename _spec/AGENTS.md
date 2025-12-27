# Agent Roles Specification

## Overview

All agent roles and their prompts are stored in the database (`role_configs` table), not hardcoded. This follows DRY principles and allows runtime configuration.

## Agent Roles

| Role | Purpose | Approval Required |
|------|---------|-------------------|
| **DIRECTOR** | Supervise pipeline, enforce standards, course correct | N/A (always running) |
| **PM** | Break down requirements into tasks | No |
| **DEV** | Implement code to satisfy tests | No |
| **QA** | Write tests before implementation (TDD) | No |
| **SECURITY** | Security review and vulnerability scanning | No |
| **DOCS** | Documentation generation and updates | No |
| **CICD** | Deployment to environments | **Yes - Human approval** |

## Database Schema

### role_configs Table

```sql
CREATE TABLE role_configs (
    id SERIAL PRIMARY KEY,
    role VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    prompt TEXT NOT NULL,
    checks JSONB DEFAULT '{}',
    requires_approval BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| role | VARCHAR(50) | Unique role identifier (e.g., "director", "pm") |
| name | VARCHAR(100) | Display name (e.g., "Director", "Project Manager") |
| description | TEXT | What this role does |
| prompt | TEXT | Full prompt template for this agent |
| checks | JSONB | Enforcement rules (for Director) |
| requires_approval | BOOLEAN | If true, human must approve before execution |
| active | BOOLEAN | Can be disabled without deletion |

## Agent Prompts

Prompts are stored in the database and loaded at runtime. They support template variables:

- `{project_path}` - Path to project workspace
- `{run_id}` - Current run ID
- `{task_id}` - Current task ID (if task-level)
- `{coding_principles}` - Content of coding principles

## Workflow

### Run-Level Flow (Full Project)
```
PM creates tasks → DEV implements → QA tests → SEC reviews → DOCS → CICD (with approval)
```

### Task-Level Flow (Single Feature)
```
Task created → DEV stage → QA stage → SEC stage → DOCS stage → COMPLETE
```

### Director Oversight
```
Director runs continuously, reviewing all stage transitions and enforcing standards
```

## CICD Agent

The CICD agent handles deployments and requires human approval:

### Approval Flow
```
Run reaches READY_FOR_DEPLOY
    │
    └── Director notifies human
            │
            ├── Human approves → CICD agent deploys → DEPLOYED
            │
            └── Human rejects → Run stays in READY_FOR_DEPLOY
```

### CICD Responsibilities
- Build artifacts
- Run deployment scripts
- Update environments
- Verify deployment success
- Rollback on failure

### Environments
```
DEV → STAGING → PRODUCTION
```

Each environment requires separate approval for production.

## Agent Runner

The `agent_runner.py` script loads prompts from the database:

```python
def get_agent_prompt(role: str, db) -> str:
    """Load agent prompt from database."""
    config = db.query(RoleConfig).filter(RoleConfig.role == role).first()
    if not config:
        raise ValueError(f"No configuration found for role: {role}")
    return config.prompt
```

## Testing Requirements

All agent configurations must have tests:

```python
def test_all_roles_have_config():
    """Every AgentRole enum value must have a RoleConfig in DB."""

def test_prompts_have_required_sections():
    """Prompts must include role, workflow, and output format."""

def test_director_checks_are_valid():
    """Director enforcement rules must be valid JSON with required fields."""
```

## Migration

When adding a new role:
1. Add to AgentRole enum
2. Create Alembic migration
3. Insert RoleConfig with prompt
4. Add tests
5. Update agent_runner.py if needed
