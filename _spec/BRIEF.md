# Brief

## Goal
Build MVP Workflow Hub that supports Projects, Requirements, Tasks, Runs, Reports, and gating.

## Next 3 tasks
1. Implement SQLAlchemy models + migration strategy (Alembic)
2. Implement basic Django views/API for CRUD (Projects, Requirements, Tasks)
3. Implement Run state machine + report ingestion + gate enforcement

## Commands
```bash
docker compose up -d
pytest
```

## Open issues
- Decide: use Django templates vs DRF vs simple JSON views
- Decide: Alembic vs Django migrations (with SQLAlchemy: Alembic is cleanest)
