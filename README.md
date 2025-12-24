# Workflow Hub

A local-first web app for managing agentic software development cycles with explicit handoffs, test/security gates, and human approval for deployment.

## Quick Start

```bash
# 1. Start PostgreSQL
docker compose -f docker/docker-compose.yml up -d

# 2. Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Run database migrations
alembic upgrade head

# 4. Start the server
python manage.py runserver 0.0.0.0:8000

# 5. Open the dashboard
open http://localhost:8000/ui/
```

## Architecture

```
PM → DEV → QA → SEC → READY_FOR_COMMIT → MERGED → READY_FOR_DEPLOY → DEPLOYED
                ↓        ↓
            QA_FAILED  SEC_FAILED (can retry)
```

**Gate Enforcement:**
- QA must pass before Security review
- Security must pass before code is ready for commit
- Human approval required for deployment (R8)

## Multi-Agent Workflow

Each agent has a specific role and responsibilities:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **PM** | Product Manager | Defines requirements, updates `_spec/*.md` |
| **DEV** | Developer | Implements code to satisfy tests |
| **QA** | Quality Assurance | Writes failing tests first (TDD) |
| **Security** | Security Engineer | Converts threat intel into tests/scanners |

### Agent Workflow

1. **PM** creates a Run and submits requirements
2. **DEV** implements the code and submits a report
3. **QA** writes tests and submits pass/fail report
   - If QA fails → run enters `QA_FAILED` state (can retry)
4. **Security** reviews and submits pass/fail report
   - If Security fails → run enters `SEC_FAILED` state (can retry)
5. **Human** approves deployment when ready

## API Reference

### Projects

```bash
# List projects
curl http://localhost:8000/api/projects

# Create project
curl -X POST http://localhost:8000/api/projects/create \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "description": "...", "stack_tags": ["python"]}'

# Get project details
curl http://localhost:8000/api/projects/{id}
```

### Requirements & Tasks

```bash
# Create requirement
curl -X POST http://localhost:8000/api/projects/{id}/requirements/create \
  -H "Content-Type: application/json" \
  -d '{"req_id": "R1", "title": "User Login", "acceptance_criteria": "..."}'

# Create task
curl -X POST http://localhost:8000/api/projects/{id}/tasks/create \
  -H "Content-Type: application/json" \
  -d '{"task_id": "T1", "title": "Implement login form"}'

# Update task status
curl -X POST http://localhost:8000/api/tasks/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'  # backlog, in_progress, blocked, done
```

### Runs (Development Cycles)

```bash
# Create a run
curl -X POST http://localhost:8000/api/projects/{id}/runs/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Run 2025-12-24_01"}'

# Get run details
curl http://localhost:8000/api/runs/{id}

# Submit agent report
curl -X POST http://localhost:8000/api/runs/{id}/report \
  -H "Content-Type: application/json" \
  -d '{
    "role": "qa",
    "status": "pass",
    "summary": "All 35 tests pass",
    "details": {"tests_run": 35, "tests_passed": 35}
  }'

# Advance to next state
curl -X POST http://localhost:8000/api/runs/{id}/advance

# Retry from failed state
curl -X POST http://localhost:8000/api/runs/{id}/retry

# Human approval for deployment
curl -X POST http://localhost:8000/api/runs/{id}/approve-deploy
```

### Threat Intel

```bash
# List threat intel
curl http://localhost:8000/api/threat-intel

# Create threat intel entry
curl -X POST http://localhost:8000/api/threat-intel/create \
  -H "Content-Type: application/json" \
  -d '{
    "source": "CVE-2025-0001",
    "summary": "SQL injection in Django",
    "affected_tech": "Django < 4.2",
    "action": "Upgrade Django"
  }'
```

### Audit Log

```bash
# View audit log
curl http://localhost:8000/api/audit?limit=50
```

## Agent JSON Report Format

When agents submit reports, they use this format:

```json
{
  "role": "qa",           // pm, dev, qa, security
  "status": "pass",       // pass, fail, pending
  "summary": "Brief description",
  "details": {
    // Role-specific data
  }
}
```

### QA Report Details
```json
{
  "tests_added": ["test_login", "test_logout"],
  "tests_changed": [],
  "commands_run": ["pytest tests/"],
  "failing_tests": [],
  "requirements_covered": ["R1", "R2"]
}
```

### Security Report Details
```json
{
  "intel_refs": [1, 2],
  "controls_verified": ["no_hardcoded_secrets", "parameterized_sql"],
  "vulnerabilities_found": []
}
```

## Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

## Project Structure

```
app/
├── db/              # SQLAlchemy engine/session
├── models/          # Project, Requirement, Task, Run, AgentReport, etc.
├── services/        # Business logic (RunService with state machine)
├── views/           # API and UI views
└── urls.py          # URL routing

_spec/               # Specifications (PM-managed)
├── BRIEF.md         # Current sprint goal
├── HANDOFF.md       # Session handoff notes
├── REQUIREMENTS.md  # Product requirements
├── ARCHITECTURE.md  # System design
└── ...

agents/              # Agent role definitions
tests/               # Pytest test suite
alembic/             # Database migrations
```

## Key Rules

1. **QA writes tests first** (TDD) - Dev does not weaken tests
2. **Only PM updates `_spec/*.md`** - Single source of truth
3. **Tests define truth** - If tests pass, feature is done
4. **Human approval for deploy** - No automated deployments
5. **Every action is logged** - Full audit trail
