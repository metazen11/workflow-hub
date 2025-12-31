# Session Context - READ THIS FIRST

**Last Updated**: 2025-12-24

## Current Goal
Build a **simple kanban-style todo app** using the Workflow Hub to demonstrate end-to-end agent pipeline.

## Non-Negotiable Principles

### TDD (Test-Driven Development)
- Write tests FIRST, then implement
- Every new feature needs a failing test before code
- Run tests frequently: `pytest tests/ -v`
- Don't mark task complete until tests pass

### DRY (Don't Repeat Yourself)
- Check for existing patterns before adding new code
- Consolidate duplicate logic into shared modules
- If you write similar code twice, refactor to a helper

### Stay Focused
- Complete ONE task before starting another
- Don't refactor unrelated code
- Don't add features not requested
- Clean up as you go, but stay on the main task

## What's Running
- Workflow Hub: http://localhost:8000/ui/
- PostgreSQL: localhost:5432 (Docker)
- Docker Model Runner: http://localhost:12434 (local LLM API)
- Goose: `/opt/homebrew/bin/goose`

## LLM Models
- **Code Generation**: `ai/qwen3-coder:latest` (default for all agents)
- **Vision/Screenshots**: `ai/qwen3-vl` (image analysis, UI verification)

## Current Pipeline
```
PM → DEV → QA → SEC → DOCS → Deploy → Testing → Deployed
     ↑___________|  (loops back on failure)
```

## The Task at Hand
1. Create a project "Kanban Todo App" in Workflow Hub
2. Have PM agent break it into tasks
3. Watch each task move through the pipeline
4. The output should be a working todo app

## Files That Matter
- `app/views/ui.py` - Dashboard views
- `app/views/api.py` - API endpoints
- `scripts/agent_runner.py` - Runs Goose agents
- `app/services/run_service.py` - Pipeline state machine
- `app/templates/dashboard.html` - Kanban board

## Quick Commands
```bash
# Check status
curl http://localhost:8000/api/status

# Create project
curl -X POST http://localhost:8000/api/projects/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Kanban Todo", "description": "Simple todo app"}'

# Create run (starts PM stage)
curl -X POST http://localhost:8000/api/projects/1/runs/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Build Todo App"}'

# Run agent manually
python scripts/agent_runner.py run --agent pm --run-id 1 --project-path ./workspaces/todo --submit

# Run tests
pytest tests/ -v
```

## What to Remind Me
If conversation compacts and I lose context, tell me:
1. "Read _spec/SESSION_CONTEXT.md first"
2. "We're building a kanban todo app through the pipeline"
3. "TDD - write tests first"
4. "DRY - check for existing patterns"
5. "Stay focused - one task at a time"
