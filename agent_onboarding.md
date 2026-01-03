# Agent Onboarding (Compact Context)

## Always Read First
- _spec/SESSION_CONTEXT.md
- _spec/HANDOFF.md
- _spec/BRIEF.md
- coding_principles.md
- todo.json

## Project Snapshot
- Stack: Django + SQLAlchemy (no Django ORM). API in app/views/api.py; UI in app/views/ui.py; models in app/models/; services in app/services/.
- Pipeline: Run-centric state machine in app/models/run.py + app/services/run_service.py. Task pipeline stages exist but are deprecated in app/models/task.py.
- Docs mention a task-centric refactor (WorkCycle/claims/PostgREST) in docs/CHANGELOG.md; code still mostly run-based.
- Agent system: prompts stored in DB (RoleConfig). scripts/agent_runner.py builds prompts with app/services/work_cycle_service.py.
- Frontend: pipeline-editor/ is Next.js + ReactFlow; uses PostgREST endpoints like /postgrest/pipeline_configs.

## Non-Negotiables
- TDD: tests first, then code. Run pytest tests/ -v.
- DRY: reuse patterns; no duplication.
- SQLAlchemy only; no Django ORM; no raw SQL strings.
- Validate/sanitize input; html.escape() for strings.
- JSON responses: {"success": true, "entity": {...}} or {"success": false, "error": "..."}.
- Templates extend base.html; CSS uses variables only; no heavy CSS frameworks.
