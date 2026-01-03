# Changelog

All notable changes to Workflow Hub since the core architecture refactor.

## [Unreleased] - January 2026

### Core Refactor (bc7cfad)

**Major architectural simplification with PostgREST integration:**

- **PostgREST Service**: Added auto-generated REST API via PostgREST Docker service
- **Renamed Handoff → WorkCycle**: Clearer semantics for agent work sessions
- **Simplified Task States**:
  - Before: BACKLOG → PM → DEV → QA → SEC → DOCS → COMPLETE (with multiple failure states)
  - After: BACKLOG → IN_PROGRESS → VALIDATING → DONE
- **Removed Run-based Pipeline**: Pipeline stages now live on Tasks, not Runs
- **Claim Tracking**: Added claims_total, validated, failed columns to Task
- **WorkCycleService**: New service for task-centric work sessions
- **Core Flow**: Project → Task → WorkCycle → Claim validation → Ledger

---

### Job Queue System (0094c4f - 62635a5)

**Complete job queue for serialized LLM and agent execution:**

- **LLMJob Model**: Database-backed priority queue
  - Job types: llm_complete, llm_chat, llm_query, vision_analyze, agent_run
  - Statuses: pending, running, completed, failed, timeout, cancelled
  - Priority levels: CRITICAL(1), HIGH(2), NORMAL(3), LOW(4)
- **JobQueueService**: Enqueueing, dequeuing, status tracking
- **JobWorker**: Background threads processing queued jobs
  - LLM Worker: Handles completions and chat
  - Agent Worker: Handles Goose agent runs
  - Vision Worker: Handles image analysis
- **Queue Status Popover**:
  - Visual badge showing running/pending counts
  - Current job details with elapsed time
  - DMR (Docker Model Runner) health indicator
  - Pending jobs list with task links
  - Kill job functionality
- **Activity Log Page**: `/ui/activity/` for full job history

### API Endpoints Added
```
GET  /api/queue/status          - Queue status with DMR health
POST /api/queue/enqueue         - Add job to queue
GET  /api/queue/jobs/{id}       - Job status
GET  /api/queue/jobs/{id}/wait  - Long-poll for completion
POST /api/queue/jobs/{id}/cancel - Cancel pending job
POST /api/queue/jobs/{id}/kill  - Force kill running job
POST /api/queue/cleanup         - Remove old completed jobs
POST /api/queue/kill-all        - Emergency stop all jobs
GET  /api/llm/activity          - Recent activity for popover
GET  /api/llm/activity/full     - Full activity for log page
```

---

### Director Persistence (62635a5)

**Director settings now persist across server restarts:**

- **DirectorSettings Model**: Singleton pattern for settings persistence
  - enabled: Auto-start on server boot
  - poll_interval, enforce_tdd, enforce_dry, enforce_security
  - include_images, vision_model
- **Auto-start**: Director checks database on startup, starts if enabled=true
- **API Updates**:
  - `POST /api/director/start` sets enabled=true
  - `POST /api/director/stop` sets enabled=false

---

### App Settings UI (e12ba82)

**New settings management system:**

- **AppSetting Model**: Key-value storage with categories
  - Categories: llm, agent, queue, ui, general
  - Support for secrets (masked in UI)
  - Read-only settings for system values
- **Settings Page**: `/ui/settings/`
  - Inline editing with immediate save
  - Director status card with start/stop toggle
  - Category grouping with icons
  - Toast notifications for feedback
- **API Endpoints**:
  - `GET /api/settings` - List all settings
  - `POST /api/settings/update` - Update settings
  - `POST /api/settings/seed` - Seed defaults
  - `GET /api/settings/{key}` - Get single setting

---

### Vision LLM Service (c1c7b17, 3d1f860)

**Image analysis capabilities for agent prompts:**

- **Vision Model**: Uses qwen3-vl via Docker Model Runner
- **MCP Vision Server**: `scripts/mcp_vision_server.py`
  - Image path detection in prompts
  - Automatic description generation
  - Goose extension integration
- **Features**:
  - Screenshot analysis for QA agents
  - UI validation in automated tests
  - Error screenshot processing

---

### Claim-Test-Evidence Framework (bb86602, ac41d7e)

**Falsification-based validation system:**

- **Claims**: Testable assertions about task completion
- **Tests**: Automated checks that can falsify claims
- **Evidence**: Proof collected during test execution
- **Failed Claims Ledger**: `/ui/ledger/` for tracking failures
- **Auto-generation**: Tasks created from failed claims

---

### Project Discovery (8071641)

**Automatic project analysis:**

- **Discovery Wizard**: Multi-step project import
  - Directory structure analysis
  - Tech stack detection (languages, frameworks, databases)
  - Key file identification
  - Build/test/run command inference
- **Credential Encryption**: Secure storage for API keys
- **PM Pipeline Stage**: Added to task board for planning phase

---

### UI Improvements

- **Inline Editing** (2fbe4e1): Edit fields directly in tables
- **Proof-of-Work System**: Upload screenshots, logs, reports as evidence
- **Security Validation**: Input sanitization across forms
- **Kanban Board**: Shared task creation modal (DRY)
- **Task List View**: Dedicated `/ui/tasks/` with filtering
- **Expandable Reports**: Collapsible agent report details

---

## Migration Notes

### Database Changes

1. Run migration for new tables:
   ```bash
   source .env && alembic upgrade head
   ```

2. Seed default settings:
   ```bash
   curl -X POST http://localhost:8000/api/settings/seed
   ```

### Environment Variables

New/updated variables:
```bash
# Job Queue
JOB_QUEUE_ENABLED=true
LLM_TIMEOUT=300
AGENT_TIMEOUT=600

# Docker Model Runner
OLLAMA_HOST=http://localhost:12434/engines/llama.cpp
```

### Breaking Changes

- `Handoff` model renamed to `WorkCycle`
- Task `run_id` column removed (tasks no longer tied to runs)
- Pipeline stages now on Task, not Run
- Some API endpoints renamed for consistency
