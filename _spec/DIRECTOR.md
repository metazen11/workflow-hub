# Director Agent Specification

## Overview

The Director is the supervisory agent that ensures the Workflow Hub pipeline runs smoothly and all agents follow established standards.

## Role

| Aspect | Description |
|--------|-------------|
| **Scope** | System-wide oversight of all projects and runs |
| **Runs as** | Always-on background service (daemon) |
| **Purpose** | Ensure quality, enforce standards, course correct agents |
| **Modeled after** | Human supervisor who keeps agents on track |

## Responsibilities

### 1. Keep Things On Task
- Monitor work progress across all projects
- Detect stalled or stuck tasks
- Retry failed work or escalate to human

### 2. Enforce Coding Principles
- Ensure TDD is followed (tests before implementation)
- Ensure DRY (re-use existing tools, don't duplicate)
- Ensure security standards (OWASP, parameterized queries)
- Ensure proper tooling (SQLAlchemy ORM, Alembic migrations)

### 3. Course Correct Agents
- Review agent outputs before advancing stages
- Send work back if standards not met
- Provide feedback/guidance on what to fix

## Enforcement Rules

| Category | Rule | Check |
|----------|------|-------|
| **ORM** | Use SQLAlchemy ORM | No raw SQL strings, no string concatenation in queries |
| **Workspace** | Correct project directory | Agent working in `workspaces/{project}/`, not elsewhere |
| **DRY** | Re-use existing tools | Check if helper/util exists before creating new one |
| **Migrations** | Alembic for schema changes | No manual DDL, all changes via `alembic revision` |
| **Frameworks** | Stay within Django/SQLAlchemy | No alternative ORMs, no bypassing established patterns |
| **Proven Tools** | Use established libraries | Prefer pytest, requests, etc. over custom solutions |
| **TDD** | Tests before implementation | QA creates tests → DEV implements → not the reverse |
| **Security** | Follow OWASP, parameterized queries | No hardcoded secrets, validate all input |

## Decision Tree

```
Agent submits work
    │
    ├── Using raw SQL? ──Yes──→ "Use SQLAlchemy ORM" → REJECT
    │
    ├── Created new util that exists? ──Yes──→ "Use existing {util}" → REJECT
    │
    ├── Schema change without migration? ──Yes──→ "Create Alembic migration" → REJECT
    │
    ├── Working outside workspace? ──Yes──→ "Stay in workspaces/{project}/" → REJECT
    │
    ├── New dependency when proven one exists? ──Yes──→ "Use {proven_lib}" → REJECT
    │
    ├── DEV implemented without tests? ──Yes──→ "QA must write tests first" → REJECT
    │
    └── All checks pass? ──Yes──→ APPROVE → Advance stage
```

## Director Checks (Stored in DB)

```json
{
  "orm_usage": {
    "description": "Must use SQLAlchemy ORM, not raw SQL",
    "patterns_to_reject": ["execute(\"", "cursor.", "f\"SELECT", "f\"INSERT", "f\"UPDATE", "f\"DELETE"],
    "patterns_to_require": ["db.query(", "db.add(", "session."]
  },
  "workspace": {
    "description": "Must work in correct project workspace",
    "required_path_pattern": "workspaces/{project_slug}/",
    "reject_paths": ["/tmp/", "~/Desktop/", "/Users/*/Documents/"]
  },
  "dry": {
    "description": "Re-use existing tools before creating new",
    "check_directories": ["app/services/", "app/utils/", "scripts/"]
  },
  "migrations": {
    "description": "Schema changes via Alembic only",
    "require_for": ["Column(", "Table(", "create_table", "drop_table"]
  },
  "frameworks": {
    "description": "Stay within established stack",
    "allowed": ["django", "sqlalchemy", "jinja2", "pytest", "requests", "playwright"],
    "reject": ["flask", "peewee", "mongoengine", "tortoise"]
  },
  "tdd": {
    "description": "Tests must exist before implementation marked done",
    "check": "tests/test_*.py must be modified before or with source files"
  },
  "security": {
    "description": "Follow security best practices",
    "reject_patterns": ["password=", "secret=", "api_key="],
    "require": ["os.getenv(", "environ.get("]
  }
}
```

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  DIRECTOR SERVICE (daemon)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ Task Poller │    │ Health Check│    │  Reviewer   │         │
│  │             │    │             │    │             │         │
│  │ - Queue     │    │ - Agents OK?│    │ - Standards │         │
│  │ - Priority  │    │ - DB OK?    │    │ - Quality   │         │
│  │ - Dispatch  │    │ - Stalled?  │    │ - Approve   │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## GUI Controls

```
┌─ Director Service ──────────────────────────────┐
│  Status: 🟢 Running                             │
│  Uptime: 2h 34m                                 │
│  Tasks reviewed: 47                             │
│  Rejections: 3 (sent back for fixes)            │
│                                                 │
│  [■ Stop]  [⚙ Settings]  [📋 View Logs]         │
│                                                 │
│  Settings:                                      │
│  ☑ Enforce TDD                                  │
│  ☑ Enforce DRY                                  │
│  ☑ Auto-reject on security issues               │
│  Poll interval: [30] seconds                    │
└─────────────────────────────────────────────────┘
```

## Relationship to Other Agents

| Agent | Director's Role |
|-------|-----------------|
| **PM** | Verify task breakdown is complete, requirements covered |
| **DEV** | Verify code follows standards, DRY, ORM usage |
| **QA** | Verify tests exist and are meaningful |
| **SECURITY** | Verify all findings addressed before advancing |
| **DOCS** | Verify documentation is updated |
| **CICD** | Verify human approval before deployment |

## Implementation Notes

- Director configuration stored in `role_configs` table
- Prompts and checks loaded from DB (not hardcoded)
- Director reads `coding_principles.md` from DB or file
- All enforcement rules are configurable per-project if needed
