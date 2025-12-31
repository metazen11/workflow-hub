# Workflow Hub

A local-first web app for managing agentic software development cycles with explicit handoffs, test/security gates, and human approval for deployment.

## Features

- **Multi-Agent Pipeline**: PM → DEV → QA → SEC → Deploy with automated handoffs
- **Project Management**: Full CRUD for projects, tasks, credentials, and environments
- **Dashboard UI**: Modern responsive interface with light/dark theme support
- **Credential Storage**: Secure storage for API keys, SSH keys, OAuth tokens, etc.
- **Environment Management**: Configure dev, staging, production environments
- **Bug Tracking**: Built-in bug report system with screenshots
- **Webhook Integration**: n8n-compatible webhooks for external automation
- **Audit Trail**: Complete logging of all actions

## Prerequisites

- **Python 3.9+**
- **Docker Desktop** (for PostgreSQL and LLM models)
- **Goose CLI** (optional, for agent execution)

## Quick Installation

The fastest way to get started:

```bash
git clone https://github.com/metazen11/workflow-hub.git
cd workflow-hub
./scripts/install.sh
```

This script will:
1. Check prerequisites (Python, Docker)
2. Create Python virtual environment
3. Install dependencies
4. Configure environment (.env)
5. Start PostgreSQL via Docker
6. Run database migrations
7. Seed agent role configurations
8. Pull LLM models (qwen3-coder, qwen3-vl)

**Options:**
```bash
./scripts/install.sh --skip-models   # Skip LLM model download
./scripts/install.sh --skip-docker   # Skip Docker service startup
```

After installation:
```bash
source venv/bin/activate
source .env
python manage.py runserver 0.0.0.0:8000
```

Then open: http://localhost:8000/ui/

## Manual Installation

### 1. Clone the Repository

```bash
git clone https://github.com/metazen11/workflow-hub.git
cd workflow-hub
```

### 2. Start PostgreSQL

Using Docker (recommended):
```bash
docker compose -f docker/docker-compose.yml up -d
```

Or connect to an existing PostgreSQL instance.

### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings:
# - Set DATABASE_URL to your PostgreSQL connection string
# - Generate a new DJANGO_SECRET_KEY
# - Configure LLM settings if using agents
```

**Generate Django Secret Key:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Run Database Migrations

```bash
source venv/bin/activate
source .env
alembic upgrade head
```

### 6. Seed Role Configurations

```bash
python scripts/seed_role_configs.py
```

### 7. Pull LLM Models (Optional)

For agent execution via Docker Model Runner:
```bash
docker model pull ai/qwen3-coder    # Code generation
docker model pull ai/qwen3-vl       # Vision/screenshots
```

### 8. Start the Server

```bash
python manage.py runserver 0.0.0.0:8000
```

### 9. Open the Dashboard

Navigate to http://localhost:8000/ui/

## Architecture

```
PM → DEV → QA → SEC → READY_FOR_COMMIT → MERGED → READY_FOR_DEPLOY → DEPLOYED
              ↓        ↓
          QA_FAILED  SEC_FAILED (can retry)
```

**Gate Enforcement:**
- QA must pass before Security review
- Security must pass before code is ready for commit
- Human approval required for deployment

## Multi-Agent Workflow

Each agent has a specific role and responsibilities:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **PM** | Product Manager | Defines requirements, updates `_spec/*.md` |
| **DEV** | Developer | Implements code to satisfy tests |
| **QA** | Quality Assurance | Writes failing tests first (TDD) |
| **Security** | Security Engineer | Converts threat intel into tests/scanners |

### Running Agents

Use the workflow CLI to run agents:

```bash
# Run the full pipeline for a project
./wf pipeline --project-id 1

# Run a single agent
./wf run pm --run-id 1
./wf run dev --run-id 1
./wf run qa --run-id 1
./wf run sec --run-id 1
```

Or use the agent runner script directly:
```bash
python scripts/agent_runner.py pipeline --run-id 328
```

## Dashboard UI

The dashboard provides a visual interface for:

- **Home** (`/ui/`): Kanban board of all runs, stats, activity feed
- **Projects** (`/ui/projects/`): List and manage projects
- **Project Detail** (`/ui/project/{id}/`):
  - Overview with tech stack, commands, key files
  - Tasks management
  - Credentials storage (API keys, SSH keys, tokens)
  - Environment configuration (dev, staging, prod)
  - Project settings
- **Bug Reports** (`/ui/bugs/`): Track and manage bugs
- **Runs** (`/ui/runs/`): Monitor pipeline runs

## API Reference

### Projects

```bash
# List projects
curl http://localhost:8000/api/projects

# Create project
curl -X POST http://localhost:8000/api/projects/create \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "description": "...", "repo_path": "/path/to/repo"}'

# Get project with full context (for orchestrator)
curl http://localhost:8000/api/projects/{id}/context

# Update project
curl -X PATCH http://localhost:8000/api/projects/{id}/update \
  -H "Content-Type: application/json" \
  -d '{"languages": ["python"], "frameworks": ["django"]}'

# Execute project pipeline
curl -X POST http://localhost:8000/api/projects/{id}/execute
```

### Credentials

```bash
# List credentials for a project
curl http://localhost:8000/api/projects/{id}/credentials

# Create credential
curl -X POST http://localhost:8000/api/projects/{id}/credentials/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "GitHub API",
    "credential_type": "api_key",
    "service": "github",
    "api_key_encrypted": "your_api_key"
  }'

# Delete credential
curl -X DELETE http://localhost:8000/api/credentials/{id}/delete
```

### Environments

```bash
# List environments for a project
curl http://localhost:8000/api/projects/{id}/environments

# Create environment
curl -X POST http://localhost:8000/api/projects/{id}/environments/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production",
    "env_type": "production",
    "url": "https://app.example.com",
    "ssh_host": "server.example.com",
    "ssh_user": "deploy"
  }'
```

### Tasks

```bash
# Create task
curl -X POST http://localhost:8000/api/projects/{id}/tasks/create \
  -H "Content-Type: application/json" \
  -d '{"task_id": "T1", "title": "Implement login form"}'

# Update task status
curl -X POST http://localhost:8000/api/tasks/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'

# Execute single task through pipeline
curl -X POST http://localhost:8000/api/tasks/{id}/execute
```

### Runs (Development Cycles)

```bash
# Create a run
curl -X POST http://localhost:8000/api/projects/{id}/runs/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Run 2025-12-26_01"}'

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

# Reset to DEV state (from QA/SEC failed)
curl -X POST http://localhost:8000/api/runs/{id}/reset-to-dev

# Human approval for deployment
curl -X POST http://localhost:8000/api/runs/{id}/approve-deploy
```

### Bug Reports

```bash
# List bugs
curl http://localhost:8000/api/bugs

# Create bug
curl -X POST http://localhost:8000/api/bugs/create \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Login button not working",
    "description": "...",
    "app_name": "frontend"
  }'

# Update bug status
curl -X POST http://localhost:8000/api/bugs/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "resolved"}'
```

### Webhooks

```bash
# Create webhook (for n8n integration)
curl -X POST http://localhost:8000/api/webhooks/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Slack Notifications",
    "url": "https://your-n8n-instance/webhook/...",
    "events": ["run.state_changed", "bug.created"]
  }'
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
├── models/          # Project, Task, Run, Credential, Environment, etc.
├── services/        # Business logic (RunService, WebhookService)
├── views/           # API and UI views
├── templates/       # Django templates
├── static/          # CSS and JavaScript
└── urls.py          # URL routing

scripts/             # Agent runner, CLI tools
_spec/               # Specifications (PM-managed)
├── BRIEF.md         # Current sprint goal
├── HANDOFF.md       # Session handoff notes
└── ...

docs/                # Additional documentation
tests/               # Pytest test suite
alembic/             # Database migrations
docker/              # Docker compose files
```

## Key Rules

1. **QA writes tests first** (TDD) - Dev does not weaken tests
2. **Only PM updates `_spec/*.md`** - Single source of truth
3. **Tests define truth** - If tests pass, feature is done
4. **Human approval for deploy** - No automated deployments
5. **Every action is logged** - Full audit trail

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `DJANGO_SECRET_KEY` | Django secret key | Required in production |
| `WORKFLOW_HUB_URL` | Hub URL for agents | `http://localhost:8000` |
| `WORKFLOW_MAX_ITER` | Max retry iterations | `3` |
| `GOOSE_PROVIDER` | LLM provider (ollama) | `ollama` |
| `OLLAMA_HOST` | Ollama/Docker Model Runner URL | `http://localhost:12434` |
| `GOOSE_MODEL` | Model for agent code generation | `ai/qwen3-coder:latest` |
| `VISION_MODEL` | Model for screenshot analysis | `ai/qwen3-vl` |

## License

MIT
