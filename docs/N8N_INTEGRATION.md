# n8n Integration Guide

This guide explains how to set up n8n to orchestrate multi-agent workflows with Goose LLM agents.

## Architecture

```
┌─────────────────┐     webhook      ┌─────────────┐     trigger     ┌─────────────┐
│  Workflow Hub   │ ───────────────> │     n8n     │ ──────────────> │    Goose    │
│  (Django API)   │                  │ (orchestr.) │                 │ (LLM Agent) │
└─────────────────┘ <─────────────── └─────────────┘ <────────────── └─────────────┘
       ^                submit report              return result           |
       |                                                                   |
       └───────────────────────────────────────────────────────────────────┘
                              Submit Report API
```

## Setup Steps

### 1. Install n8n

```bash
# Using Docker (recommended)
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# Or via npm
npm install -g n8n
n8n start
```

### 2. Install Goose

```bash
# Install Goose (Block's AI coding agent)
pipx install goose-ai

# Configure your LLM provider
goose configure
```

### 3. Start the Agent Runner

```bash
cd /path/to/workflow-hub
source venv/bin/activate

# Set environment variables
export WORKFLOW_HUB_URL=http://localhost:8000
export GOOSE_PROVIDER=anthropic  # or openai, ollama, etc.

# Start the agent runner server
python scripts/agent_runner.py serve --port 5001
```

### 4. Register Webhooks in Workflow Hub

```bash
# Register n8n webhook endpoint
curl -X POST http://localhost:8000/api/webhooks/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "n8n-orchestrator",
    "url": "http://localhost:5678/webhook/workflow-hub",
    "events": ["run_created", "state_change", "report_submitted", "gate_failed", "ready_for_deploy"],
    "active": true
  }'
```

### 5. Create n8n Workflow

Create a new workflow in n8n with these nodes:

#### Webhook Trigger Node
- **HTTP Method**: POST
- **Path**: `/workflow-hub`
- **Response Mode**: Immediately

#### Switch Node (Route by Event)
Route based on `{{$json.event}}`:
- `run_created` → Start PM agent
- `state_change` → Route to appropriate agent based on `next_agent`
- `gate_failed` → Send notification
- `ready_for_deploy` → Send approval request

#### HTTP Request Node (Trigger Agent)
For each agent (PM, Dev, QA, Security):
- **Method**: POST
- **URL**: `http://localhost:5001/`
- **Body**:
```json
{
  "event": "{{ $json.event }}",
  "payload": {{ $json.payload }}
}
```

## Webhook Events

The Workflow Hub emits these webhook events:

| Event | Trigger | Payload |
|-------|---------|---------|
| `run_created` | New development run started | `run_id`, `project_id`, `name`, `next_agent: "pm"` |
| `state_change` | Run transitioned to new state | `run_id`, `from_state`, `to_state`, `next_agent` |
| `report_submitted` | Agent submitted a report | `run_id`, `role`, `status`, `summary` |
| `gate_failed` | QA or Security gate failed | `run_id`, `gate`, `reason` |
| `ready_for_deploy` | All gates passed, awaiting approval | `run_id`, `message` |

## Agent Flow

1. **PM Agent** → Creates tasks, refines requirements
2. **Dev Agent** → Implements functionality
3. **QA Agent** → Writes tests, verifies implementation
4. **Security Agent** → Scans for vulnerabilities

Each agent receives the webhook, runs Goose with appropriate prompts, and submits a report back to the Workflow Hub.

## Manual Testing

```bash
# Create a project
curl -X POST http://localhost:8000/api/projects/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project", "repo_path": "/path/to/repo"}'

# Start a development run
curl -X POST http://localhost:8000/api/projects/1/runs/create \
  -H "Content-Type: application/json" \
  -d '{"name": "Feature: Add user authentication"}'

# This triggers the webhook → n8n → Agent Runner → Goose → Report submission
```

## LLM Providers

Goose supports multiple LLM providers. Configure in `~/.config/goose/config.yaml`:

```yaml
# Anthropic (Claude)
provider: anthropic
model: claude-3-sonnet-20240229

# OpenAI
provider: openai
model: gpt-4-turbo

# Ollama (local)
provider: ollama
model: llama2
host: http://localhost:11434
```

## Security Notes

- Use HMAC secrets for webhook authentication
- Run agent runner in isolated environment
- Limit file system access for Goose
- Review generated code before merging
- Human approval required for deployment

## Troubleshooting

### Webhooks not firing
```bash
# Check webhook configuration
curl http://localhost:8000/api/webhooks

# Check audit log
curl http://localhost:8000/api/audit
```

### Agent not receiving webhooks
```bash
# Test agent runner directly
python scripts/agent_runner.py run \
  --agent pm \
  --run-id 1 \
  --project-path /path/to/repo \
  --submit
```

### Goose not installed
```bash
pipx install goose-ai
goose configure
```
