# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## READ FIRST - Every Session

**Before doing anything, read these files:**
1. `_spec/SESSION_CONTEXT.md` - Current task and what we're building
2. `_spec/HANDOFF.md` - What's been done and current state
3. `_spec/BRIEF.md` - Project goals
4. `coding_principles.md` - TDD/DRY standards and development workflow
5. `todo.json` - Current task status and priorities

---

## Core Principles (NON-NEGOTIABLE)

### TDD - Test-Driven Development
- Write tests FIRST, then implement
- Red → Green → Refactor
- Don't mark complete until tests pass
- Run: `pytest tests/ -v`

### DRY - Don't Repeat Yourself
- Check existing patterns before writing new code
- Refactor duplicates into helpers
- One source of truth

### Stay Focused
- Complete ONE task before starting the next
- Don't refactor unrelated code
- Don't add unrequested features
- Clean up as you go, stay on main task

---

## Project Overview

**Workflow Hub** - A local-first web app for managing agentic software development cycles with explicit handoffs, test/security gates, and human approval for deployment.

## Commands

### Quick Start (ALWAYS use this)
```bash
# Start everything (order matters!)
docker compose -f docker/docker-compose.yml up -d
source venv/bin/activate
source .env  # CRITICAL: Load database credentials
alembic upgrade head  # Ensure schema is current
python scripts/seed_role_configs.py  # Seed agent role prompts (idempotent)
python manage.py runserver 0.0.0.0:8000
```

### Other Commands
```bash
# Run tests
source .env && pytest tests/ -v

# Create new migration
source .env && alembic revision --autogenerate -m "description"
source .env && alembic upgrade head
```

### Database Warnings
- **NEVER run `docker compose down -v`** - the `-v` flag deletes the data volume!
- Safe shutdown: `docker compose -f docker/docker-compose.yml down` (no -v)
- Data persists in Docker volume `docker_pgdata`
- If data is lost, check volume: `docker volume ls | grep pgdata`

### Database Backup/Restore
```bash
# Backup (run periodically!)
source .env && docker exec docker-db-1 pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
source .env && docker exec -i docker-db-1 psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup_YYYYMMDD_HHMMSS.sql

# Quick data check
source .env && docker exec docker-db-1 psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 'projects', COUNT(*) FROM projects UNION ALL SELECT 'runs', COUNT(*) FROM runs UNION ALL SELECT 'tasks', COUNT(*) FROM tasks;"
```

## Architecture

Django + SQLAlchemy (no Django ORM). All database access via SQLAlchemy.

**Run Pipeline:**
```
PM → DEV → QA → SEC → READY_FOR_COMMIT → MERGED → READY_FOR_DEPLOY → DEPLOYED
                ↓        ↓
            QA_FAILED  SEC_FAILED
```

**Key files:**
- `app/models/run.py` - Run model with state machine and valid transitions
- `app/services/run_service.py` - Business logic for state transitions and gate enforcement
- `app/views/api.py` - REST API endpoints
- `app/views/ui.py` - Dashboard views

## Multi-Agent System

Always read before starting work:
- `_spec/BRIEF.md` - Current goal and next tasks
- `_spec/HANDOFF.md` - What changed and commands to run

### Agent Roles

| Role | Responsibility |
|------|----------------|
| PM | Updates `_spec/*.md` files only |
| QA | Writes failing tests first (TDD) |
| Dev | Implements code to satisfy tests |
| Security | Converts threat intel into tests/scanners |

**Rules:**
- **TDD: Write tests FIRST, then implement** (Red → Green → Refactor)
- Dev does not weaken tests
- Only PM updates `_spec/*.md`
- Tests define truth
- Always output a JSON result report for your role

## API Endpoints

- `GET /api/status` - System status
- `GET/POST /api/projects` - List/create projects
- `GET /api/projects/{id}` - Project details
- `POST /api/projects/{id}/runs/create` - Create run
- `POST /api/runs/{id}/report` - Submit agent report
- `POST /api/runs/{id}/advance` - Advance state
- `POST /api/runs/{id}/approve-deploy` - Human approval

## Database

PostgreSQL 16 on localhost:5432 (credentials in `.env` file - user/db: wfhub)

Models: Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent, Credential, Environment, BugReport

## Task Tracking

### todo.json
Project tasks are tracked in `todo.json`:
```json
{
  "id": "WH-001",
  "title": "Task description",
  "status": "pending|in_progress|done",
  "priority": 1-10,
  "acceptance_criteria": ["list of requirements"]
}
```

### Git Auto-Initialization
When a run is created:
- Checks if project has `repo_path`
- Creates git repo if not exists
- Extracts git info (branch, remote)
- Updates project with git details

## UI Testing - Use Playwright, Not curl

**IMPORTANT:** When testing UI functionality, use Playwright instead of curl.

- `curl` only fetches raw HTML - it doesn't execute JavaScript or render the page
- `Playwright` runs a real browser - it clicks buttons, fills forms, and shows what users actually see

```python
# Example: Test a button click
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8000/ui/projects/')
    page.click('text=Add Existing')  # Actually clicks the button
    page.fill('#discover-path', '/path/to/project')
    page.click('#discover-btn')
    page.wait_for_timeout(3000)  # Wait for async operations
    # Check what actually rendered
    print(page.is_visible('#import-step-2'))
    browser.close()
```

Use curl only for:
- Testing raw API endpoints (JSON responses)
- Checking if server is running
- Verifying HTML structure (not behavior)

## Documentation

Additional documentation in `docs/`:
- `DOCKER_MODEL_RUNNER.md` - Local LLM API for simple completions (docs enrichment, wizards)
- `OFFLINE_SETUP.md` - Offline environment setup
- `N8N_INTEGRATION.md` - N8N workflow integration

---

## Monitoring

Pipeline health monitoring via Playwright:
```bash
# Run manual check
python tests/e2e/test_pipeline_monitoring.py

# Run Playwright tests
pytest tests/e2e/test_pipeline_monitoring.py -v
```

Checks:
- Run states progressing
- Database fields populated
- UI renders correctly
- Agent handoffs working
