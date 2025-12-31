# Handoff

## Current Session Summary (2025-12-31 - Session 12)

### SYSTEM CLEANUP & VERIFICATION

Verified all major systems are fully implemented and updated task tracking.

**Verified Complete:**

1. **Handoff System** (WH-033 - DONE)
   - Handoff model with full lifecycle tracking
   - API endpoints: create, accept, complete, fail, history
   - agent_runner.py integrated with handoff API
   - UI shows handoff history in task detail page
   - Migration applied, table exists in DB

2. **Proof Tracking** (WH-031 - DONE)
   - Proof model with task-centric design
   - Hybrid storage: files + DB metadata
   - API endpoints for history and download
   - Backfill script for existing proofs

3. **Vision LLM Service** (WH-034 - DONE)
   - get_image_description() with caching
   - enrich_text_with_image_descriptions()
   - Director settings integration
   - Qwen3-VL via Docker Model Runner

4. **Role Configs** (WH-021 - DONE)
   - All 7 roles seeded: director, pm, dev, qa, security, docs, cicd
   - Prompts loaded from database

**Updated:**
- todo.json: Marked WH-021, WH-031 as done, added WH-033, WH-034

**Plan Status:**
- `/Users/mz/.claude/plans/structured-prancing-tiger.md` - Handoff redesign plan is COMPLETE

---

## Previous Session Summary (2025-12-31 - Session 11)

### GOOSE + VISION LLM INTEGRATION - IMPLEMENTED

Fixed Goose agent execution and added multimodal vision support for screenshot analysis.

**Key Fixes & Features:**

1. **Fixed Goose Command Syntax** (`scripts/agent_runner.py`)
   - Changed from `goose session start/resume` to `goose run -n <name> -t <prompt>`
   - Fixed Project attribute names (git_url→repository_url, branch→primary_branch, etc.)
   - Added task_id to format variables for prompt templates

2. **Vision LLM Service** (`app/services/llm_service.py`)
   - `get_image_description(image_path)` - Analyze images with Qwen3-VL
   - `enrich_text_with_image_descriptions(text)` - Auto-find image paths and append descriptions
   - Caching system in `.cache/image_descriptions/` (keyed by path + mtime)
   - Prompts for error messages, all visible text, UI elements

3. **Director Settings for Images** (`app/views/api.py`)
   - Added `include_images` setting (bool) - Enable/disable image enrichment
   - Added `vision_model` setting (string) - Model to use (default: ai/qwen3-vl)
   - Settings persist in `_director_settings` dict

4. **Handoff Integration** (`app/services/handoff_service.py`)
   - `get_handoff_for_prompt()` now accepts `include_images` parameter
   - When enabled, auto-enriches context with image descriptions from referenced paths
   - Checks director settings if not explicitly passed

5. **Models in Use**
   - `ai/qwen3-coder:latest` - Default model for all agent code generation
   - `ai/qwen3-vl` - Vision model for screenshot/image analysis
   - `ai/gemma3` - Alternative (has vision but may hallucinate)

### Files Modified/Created
| File | Change |
|------|--------|
| `scripts/agent_runner.py` | Fixed Goose commands, Project attributes, task_id |
| `app/services/llm_service.py` | Added vision service functions |
| `app/services/handoff_service.py` | Added image enrichment to handoff |
| `app/views/api.py` | Added include_images/vision_model settings |
| `.gitignore` | Added .cache/ |

### Test Vision Service
```bash
# Enable images in director settings
curl -X POST http://localhost:8000/api/director/settings \
  -H "Content-Type: application/json" \
  -d '{"include_images": true}'

# Test image description
python -c "
from app.services.llm_service import get_image_description
desc = get_image_description('/path/to/screenshot.png')
print(desc)
"

# Test text enrichment
python -c "
from app.services.llm_service import enrich_text_with_image_descriptions
text = 'Review /path/to/image.png'
print(enrich_text_with_image_descriptions(text))
"
```

### Pipeline Run Successful
- Task 633 ran through full pipeline: DEV → QA → SEC → DOCS → READY_FOR_COMMIT
- Run 683 completed successfully
- Bug task 667 created for drag-drop file upload feature

### TODO / What's Left
1. **LLM Session Persistence** - The `set_state` API doesn't persist (needs investigation)
2. **Goose Session Management** - Consider using task-based sessions instead of run-based
3. **Image Processing in Agent Prompts** - Currently only enriches handoff, not the full agent prompt
4. **Multimodal Model Auth** - Llama 3.2 Vision, LLaVA require Docker Hub auth

---

## Previous Session Summary (2025-12-30 - Session 10)

### PROOF-OF-WORK DATABASE TRACKING - IMPLEMENTED

Implemented hybrid proof storage: files in filesystem + metadata in database. This enables agents to query proof history for task context and memory.

**Key Features:**
1. **Proof Model** (`app/models/proof.py`)
   - Task-centric design (task_id is required, run_id is optional context)
   - ProofType enum: screenshot, log, report, test_result, code_diff, other
   - `to_dict()` for API responses
   - `to_agent_context()` for compact agent memory format

2. **API Endpoints**
   - `GET /api/tasks/{id}/proof-history` - All proofs for a task across all runs
   - `GET /api/projects/{id}/proof-history` - Project-wide proof history
   - `GET /api/tasks/{id}/proofs/{proof_id}/download` - Download by DB id

3. **Proof Upload Integration**
   - `proof_upload()` now saves metadata to database
   - Existing filesystem storage unchanged
   - Both agent and human uploads tracked

4. **Backfill Script** (`scripts/backfill_proofs.py`)
   - Migrates existing filesystem proofs to database
   - Handles both task-level and run-level proofs
   - Run with: `source .env && python scripts/backfill_proofs.py`

### Files Modified/Created
| File | Change |
|------|--------|
| `app/models/proof.py` | New model with ProofType enum |
| `app/models/__init__.py` | Export Proof, ProofType |
| `app/views/api.py` | Added proof history endpoints, download endpoint |
| `app/urls.py` | Added routes for new endpoints |
| `alembic/versions/d2657c9e4cb3_add_proofs_table.py` | Migration |
| `scripts/backfill_proofs.py` | Backfill script |
| `todo.json` | Added WH-030, WH-031, WH-032 |

### New TODO Items Added
| ID | Task | Priority |
|----|------|----------|
| WH-030 | AJAX-based component refresh (no full page reloads) | 2 |
| WH-031 | Proof-of-work database tracking with task history API | 1 (done) |
| WH-032 | Simple completion tool for agents (bypass Goose) | 3 |

### Test the Proof History API
```bash
# Get all proofs for a task
curl http://localhost:8000/api/tasks/666/proof-history

# Get project-wide proofs
curl http://localhost:8000/api/projects/730/proof-history

# Download a proof by ID
curl http://localhost:8000/api/tasks/666/proofs/4/download
```

---

## Previous Session Summary (2025-12-26 - Session 8)

### DIRECTOR & ROLE CONFIG ARCHITECTURE - DESIGNED

Designed and documented the Director agent and database-driven role configuration system.

**Key Decisions:**

1. **Director Role** - Supervisory agent that:
   - Ensures pipeline runs smoothly
   - Enforces coding principles (TDD, DRY, ORM, migrations)
   - Course corrects agents when standards not met
   - Runs as always-on daemon service
   - Modeled after human supervisor behavior

2. **PM vs Director Distinction**:
   - **PM** = Project-level, breaks down requirements, manages one project
   - **Director** = System-level, supervises all projects, enforces standards

3. **CICD Agent** - Deployment agent requiring human approval

4. **Database-Driven Prompts** (DRY principle):
   - Role prompts stored in `role_configs` table, not hardcoded
   - Removed anti-pattern of hardcoded ROLE_PROMPTS in agent_runner.py

### Files Created

| File | Description |
|------|-------------|
| `_spec/DIRECTOR.md` | Director role specification, enforcement rules, decision tree |
| `_spec/AGENTS.md` | All agent roles, DB schema for role_configs, workflow |

### Tasks Added to todo.json

| ID | Task | Priority | Blocked By |
|----|------|----------|------------|
| WH-011 | Write tests for RoleConfig model (TDD) | 1 | - |
| WH-010 | Create RoleConfig model for agent prompts in DB | 1 | WH-011 |
| WH-012 | Add DIRECTOR and CICD to AgentRole enum | 1 | WH-011 |
| WH-013 | Refactor agent_runner.py to load prompts from DB | 1 | WH-010 |
| WH-014 | Implement Director service daemon | 1 | WH-013 |
| WH-015 | Implement CICD agent with approval gate | 2 | WH-013 |
| WH-016 | Add Director GUI controls to dashboard | 2 | WH-014 |
| WH-017 | Hybrid task/run pipeline flow | 2 | WH-014 |
| WH-018 | Test Director with PyCRUD pipeline | 2 | WH-017 |

### Next Steps (TDD Order)

1. **WH-011** - Write failing tests first for RoleConfig
2. **WH-012** - Add new roles to AgentRole enum
3. **WH-010** - Implement RoleConfig model to pass tests
4. **WH-013** - Refactor agent_runner to use DB
5. **WH-014** - Implement Director daemon

---

## Previous Session Summary (2025-12-26 - Session 6)

### TASK PIPELINE WORKFLOW - IN PROGRESS

The user's vision is a **sprint-like workflow** where each task individually progresses through pipeline stages (DEV → QA → SEC → DOCS → COMPLETE), not just the run as a whole.

**Big Picture Goal**:
- Each task goes through all stages: DEV → QA → SEC → DOCS → COMPLETE
- Agents work on individual tasks (not entire runs)
- Run completes when all its tasks reach COMPLETE
- Visibility into each task's current stage
- Mostly automated with ability to pause/course-correct
- No tasks fall through cracks

### What Was Implemented

#### 1. TaskPipelineStage Enum - DONE
**File**: `app/models/task.py`
```python
class TaskPipelineStage(enum.Enum):
    NONE = "none"      # Not in pipeline yet
    DEV = "dev"        # Being implemented by DEV agent
    QA = "qa"          # Being tested by QA agent
    SEC = "sec"        # Being reviewed by Security agent
    DOCS = "docs"      # Documentation stage
    COMPLETE = "complete"  # Passed all stages
```

#### 2. Task Model Updated - DONE
**File**: `app/models/task.py`
- Added `pipeline_stage` column (Enum, nullable)
- Updated `to_dict()` to include pipeline_stage

#### 3. Database Migration - DONE
**File**: `alembic/versions/8ff917fb21f0_add_pipeline_stage_to_tasks.py`
- Fixed to create PostgreSQL enum type before adding column
- Migration applied successfully

#### 4. Task Pipeline API Endpoints - DONE
**File**: `app/views/api.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks/queue` | GET | Get next tasks to work on (by run_id, stage) |
| `/api/tasks/{id}/advance-stage` | POST | Advance task to next stage (or back to DEV on fail) |
| `/api/tasks/{id}/set-stage` | POST | Set task stage directly |
| `/api/runs/{id}/task-progress` | GET | Get task progress summary for a run |
| `/api/runs/{id}/kill` | POST | Kill (soft delete) a run |

**Stage Progression Map**:
```
NONE → DEV → QA → SEC → DOCS → COMPLETE
        ↑___________________|  (on fail, loop back to DEV)
```

#### 5. Run Service Updated - DONE
**File**: `app/services/run_service.py`
- Added `TaskPipelineStage` import
- Tasks created from findings now start at `pipeline_stage=DEV, status=IN_PROGRESS`
- Added `_initialize_task_stages()` - Sets tasks to DEV stage when run enters DEV
- Added `get_task_progress()` - Returns stage counts and progress percentage
- Added `_check_tasks_ready_for_advance()` - Checks if all tasks passed current stage

### Key Files Modified
1. `app/models/task.py` - TaskPipelineStage enum, pipeline_stage field
2. `app/views/api.py` - Task pipeline endpoints
3. `app/urls.py` - URL routes for new endpoints
4. `app/services/run_service.py` - Task stage initialization and progress tracking
5. `alembic/versions/8ff917fb21f0_*.py` - Fixed PostgreSQL enum migration

### What's NOT Done Yet (TODOs)

#### 1. Update Agents to Use Task Pipeline API (HIGH PRIORITY)
The agents in `scripts/agent_runner.py` need to:
- Call `/api/tasks/queue?run_id=X&stage=dev` to get tasks
- Work on each task individually
- Call `/api/tasks/{id}/advance-stage` when done

**Current flow** (run-centric):
```
Agent runs on whole run → submits report → run advances
```

**Target flow** (task-centric):
```
Agent gets task from queue → works on it → advances task stage → repeat
When all tasks at next stage → run advances
```

#### 2. Add UI for Task Pipeline Progress
Show task stages in:
- Run detail view (column/badge showing stage per task)
- Dashboard (overall progress)
- Project view (task pipeline progress)

#### 3. Test Full Task Pipeline Flow
- Create run with tasks
- Watch tasks progress through stages
- Verify loopback on failure

#### 4. Create Dockerfile for SaaS Deployment

### Current Working State
- Server: `http://localhost:8000`
- Database: PostgreSQL on `localhost:5432`
- Migration: Applied (tasks have pipeline_stage column)
- Django check: Passes

### Test the Task Pipeline API
```bash
# Get task queue for a run
curl http://localhost:8000/api/tasks/queue?run_id=432&stage=dev

# Advance a task
curl -X POST http://localhost:8000/api/tasks/17/advance-stage \
  -H "Content-Type: application/json" \
  -d '{"result": "pass", "notes": "Fixed security issue"}'

# Get run task progress
curl http://localhost:8000/api/runs/432/task-progress
```

---

## Previous Session Summary (2025-12-26 - Session 5)

### RecursionError in run_detail.html - FIXED

**Problem**: Template include causing Python recursion limit exceeded
- `/ui/run/432/` returned HTTP 500 with RecursionError
- Django's `{% include %}` with `with` was causing deep context stack

**Solution**: Inlined task_row.html content directly into run_detail.html
- Removed `{% include 'partials/task_row.html' with task=task show_edit=True %}`
- Copied task row HTML inline in the for loop
- Page now loads correctly with all 16 tasks rendering

**Files Modified**:
- `app/templates/run_detail.html` - Inlined task row HTML
- `app/templates/partials/task_row.html` - Previously fixed to inline delete button
- `tests/test_ui_screenshots.py` - Updated to use run 432 (run 377 was deleted)

**Note on DRY**: Inlining is the correct solution here because:
1. The task row is only used in one place (run_detail.html)
2. Django's `{% include ... with %}` can cause context stack overflow with many iterations
3. Partials only save duplication when used in multiple places

### Security Agent Handoff - FIXED

**Problem**: Security agent reported `status="pass"` even when it found high/critical vulnerabilities in `security_report.json`

**Root Cause**: `scripts/agent_runner.py` was using a fallback that assumed success if goose completed, ignoring the actual security findings file.

**Solution**: Modified `run_goose()` in `agent_runner.py` to:
1. Check for `security_report.json` after security agent runs
2. Count vulnerabilities by severity (critical, high, medium, low)
3. Return `status="fail"` if any high/critical vulnerabilities found
4. Same logic added for QA agent checking `bugs.json`

**Files Modified**:
- `scripts/agent_runner.py` - Added security_report.json and bugs.json parsing

**State Machine Flow** (now working correctly):
```
SEC → SEC_FAILED (if high/critical vulns) → DEV (loop back with tasks created)
     → DOCS (if pass) → READY_FOR_COMMIT
```

### Auto-Loopback for Failed States - ADDED
**File**: `app/services/webhook_service.py`

When AUTO_TRIGGER_AGENTS=true:
- `qa_failed`, `sec_failed`, `testing_failed`, `docs_failed` states
- Automatically call `reset_to_dev()` with `create_tasks=True`
- Creates fix tasks and loops back to DEV for remediation

### Task Creation from Findings - FIXED
**File**: `app/services/run_service.py`

**Problem**: Tasks created from security findings had empty descriptions

**Solution**: Updated `_extract_security_findings()` to properly parse:
- `issue` field → title
- `file:line` → description
- `recommendation` → description
- `severity` → priority (critical/high = 10, medium = 7, low = 5)

---

## Previous Sessions (2025-12-26 - Sessions 1-4)

### AUTOMATIC PIPELINE TRIGGERING - IMPLEMENTED

The system supports fully automated agent pipelines that auto-advance through stages.

**Components**:
1. **AgentService** (`app/services/agent_service.py`)
   - `trigger_agent(run_id, agent_type, async_mode)`
   - `trigger_pipeline(run_id, max_iterations)`

2. **Webhook Auto-Trigger** (`app/services/webhook_service.py`)
   - `AUTO_TRIGGER_AGENTS=true` enables automatic advancement
   - Triggers next agent on state_change/run_created events

3. **API Endpoints**
   - `POST /api/runs/{id}/trigger-agent`
   - `POST /api/runs/{id}/trigger-pipeline`

### Previous Fixes
- Auto-refresh page crash (MutationObserver feedback loop)
- Tasks not showing in run view (query used run_id instead of project_id)
- Runs list page (was 404, now working)
- Rich TUI for workflow visualization
- Bug report widget
- Task queue service

---

## Commands
```bash
# Start everything
docker compose -f docker/docker-compose.yml up -d
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Run tests
pytest tests/ -v

# Run Playwright UI tests
pytest tests/test_ui_screenshots.py -v

# Database migration
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

## URLs
- Dashboard: http://localhost:8000/ui/
- Projects: http://localhost:8000/ui/projects/
- Runs: http://localhost:8000/ui/runs/
- Run Detail: http://localhost:8000/ui/run/432/
- Bug Reports: http://localhost:8000/ui/bugs/
- API Status: http://localhost:8000/api/status

## Environment Variables
```bash
AUTO_TRIGGER_AGENTS=true   # Enable automatic pipeline advancement
LLM_TIMEOUT=600            # Increased for local LLMs
GOOSE_PROVIDER=anthropic   # LLM provider for agents
```
