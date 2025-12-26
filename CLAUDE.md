# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## READ FIRST - Every Session

**Before doing anything, read these files:**
1. `_spec/SESSION_CONTEXT.md` - Current task and what we're building
2. `_spec/HANDOFF.md` - What's been done and current state
3. `_spec/BRIEF.md` - Project goals

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

```bash
# Start PostgreSQL
docker compose -f docker/docker-compose.yml up -d

# Set up environment
source venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
python manage.py runserver 0.0.0.0:8000

# Run tests
pytest tests/ -v

# Create new migration
alembic revision --autogenerate -m "description"
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

PostgreSQL 16 on localhost:5432 (user/pass/db: app)

Models: Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent
