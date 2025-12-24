# Handoff

## What changed
- MVP Workflow Hub is complete and functional
- All SQLAlchemy models implemented (Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent)
- Run state machine with gate enforcement (QA/Security gates)
- Human approval required for deployment
- Full audit logging
- 35 tests passing
- Dashboard UI at `/ui/`
- Complete REST API

## What to do next
1. Add more UI features (forms for creating projects/runs)
2. Integrate with actual agent runners (Claude Code hooks)
3. Add authentication for the dashboard
4. Consider adding WebSocket for real-time updates

## Commands
```bash
# Start everything
docker compose -f docker/docker-compose.yml up -d
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Run tests
pytest tests/ -v

# Create migration after model changes
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Current state
- Server runs on http://localhost:8000
- Dashboard at http://localhost:8000/ui/
- API at http://localhost:8000/api/
- PostgreSQL on localhost:5432 (user/pass/db: app)
