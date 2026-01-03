# Job Queue System

The Job Queue System serializes LLM requests and agent runs to prevent resource contention. Since local LLMs (via Docker Model Runner) and Goose agents can only process one request at a time, this queue ensures orderly execution with priority-based scheduling.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Request Sources                           │
│  API Endpoints | Director Daemon | AgentService | Webhooks   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   JobQueueService                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ LLM Queue   │  │ Agent Queue │  │ Vision Queue│          │
│  │ (priority)  │  │ (priority)  │  │ (low prio)  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                              │
│  Database: llm_jobs table (priority queue)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ LLM Worker  │  │ Agent Worker│  │Vision Worker│
│ (1 thread)  │  │ (1 thread)  │  │ (1 thread)  │
└─────────────┘  └─────────────┘  └─────────────┘
          │               │               │
          ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│Docker Model │  │   Goose     │  │ Vision LLM  │
│  Runner     │  │   CLI       │  │ (qwen3-vl)  │
└─────────────┘  └─────────────┘  └─────────────┘
```

## Key Components

### 1. LLMJob Model (`app/models/llm_job.py`)

The database model for queue entries:

```python
class LLMJob(Base):
    __tablename__ = "llm_jobs"

    id: int                    # Primary key
    job_type: str              # llm_complete, llm_chat, agent_run, vision_analyze
    status: str                # pending, running, completed, failed, timeout, cancelled
    priority: int              # 1=CRITICAL, 2=HIGH, 3=NORMAL, 4=LOW
    request_data: JSON         # Serialized request parameters
    result_data: JSON          # Response data (on completion)
    error_message: str         # Error details (on failure)

    # Context links
    project_id: int            # Optional project reference
    task_id: int               # Optional task reference
    session_id: int            # Optional LLM session for chat continuity

    # Timing
    created_at: datetime       # When job was enqueued
    started_at: datetime       # When worker picked it up
    completed_at: datetime     # When job finished
    timeout_seconds: int       # Max runtime (default: 300s)

    # Tracking
    worker_id: str             # Which worker processed this job
    position_at_creation: int  # Queue position when created
```

### 2. Job Types

| Type | Description | Default Timeout |
|------|-------------|-----------------|
| `llm_complete` | Simple completion request | 300s (5 min) |
| `llm_chat` | Chat with message history | 300s (5 min) |
| `llm_query` | Contextual query with project context | 300s (5 min) |
| `vision_analyze` | Image analysis | 120s (2 min) |
| `agent_run` | Goose agent execution | 600s (10 min) |

### 3. Priority Levels

| Priority | Value | Use Case |
|----------|-------|----------|
| CRITICAL | 1 | User-facing requests, blocking UI |
| HIGH | 2 | Agent work cycles, pipeline advancement |
| NORMAL | 3 | Background enrichment, doc generation |
| LOW | 4 | Vision preprocessing, optional analysis |

Jobs with higher priority (lower number) are processed first. Within the same priority, FIFO ordering applies.

### 4. Job Statuses

| Status | Description |
|--------|-------------|
| `pending` | Waiting in queue |
| `running` | Currently being processed by a worker |
| `completed` | Finished successfully |
| `failed` | Finished with error |
| `timeout` | Exceeded timeout limit |
| `cancelled` | Cancelled by user |

## JobQueueService (`app/services/job_queue_service.py`)

The service layer for queue management:

### Enqueueing Methods

```python
# LLM request
queue.enqueue_llm_request(
    job_type="llm_complete",
    request_data={"prompt": "...", "model": "..."},
    priority=JobPriority.NORMAL,
    timeout=300
)

# Agent run
queue.enqueue_agent_run(
    task_id=123,
    agent_type="dev",
    project_path="/path/to/repo",
    priority=JobPriority.HIGH,
    timeout=600
)

# Vision analysis
queue.enqueue_vision_request(
    image_path="/path/to/image.png",
    prompt="Describe this screenshot",
    priority=JobPriority.LOW
)
```

### Queue Management

```python
# Get next job to process
job = queue.get_next_job(job_types=["llm_complete", "llm_chat"])

# Get queue status
status = queue.get_queue_status()
# Returns: {pending: {llm: 0, agent: 1, vision: 0}, running: [...], ...}

# Get job position
position = queue.get_job_position(job_id)
```

### Job Lifecycle

```python
# Mark job as running
queue.start_job(job_id, worker_id="llm")

# Complete job
queue.complete_job(job_id, result_data={"content": "..."})

# Fail job
queue.fail_job(job_id, error="Something went wrong")

# Cancel pending job
queue.cancel_job(job_id)

# Force kill running job
queue.force_kill_job(job_id, reason="User cancelled")
```

## JobWorker (`app/services/job_worker.py`)

Background workers that process queued jobs:

### Worker Types

| Worker | Job Types | Poll Interval |
|--------|-----------|---------------|
| `llm` | llm_complete, llm_chat, llm_query | 0.5s |
| `agent` | agent_run | 1.0s |
| `vision` | vision_analyze | 2.0s |

### Worker Lifecycle

```python
from app.services.job_worker import start_workers, stop_workers

# Start all workers (called on Django startup)
start_workers()

# Stop all workers gracefully
stop_workers()
```

### Worker Manager

```python
from app.services.job_worker import get_worker_manager

manager = get_worker_manager()
status = manager.get_status()
# Returns: {started: true, workers: [{id: "llm", is_busy: false, ...}, ...]}
```

## API Endpoints

### Queue Status
```http
GET /api/queue/status
```
Returns queue lengths, running jobs, DMR health, and worker status.

### Enqueue Job
```http
POST /api/queue/enqueue
Content-Type: application/json

{
  "job_type": "llm_complete",
  "request_data": {"prompt": "Hello"},
  "priority": 3,
  "timeout": 300
}
```

### Job Status
```http
GET /api/queue/jobs/{job_id}
```

### Wait for Job
```http
GET /api/queue/jobs/{job_id}/wait
```
Long-polls until job completes (max 30s).

### Cancel Job
```http
POST /api/queue/jobs/{job_id}/cancel
```

### Kill Job
```http
POST /api/queue/jobs/{job_id}/kill
```

### Cleanup Old Jobs
```http
POST /api/queue/cleanup
```
Removes completed/failed jobs older than 24 hours.

### Kill All Running
```http
POST /api/queue/kill-all
```
Emergency stop for all running jobs.

## UI Integration

### Queue Status Popover

The nav bar shows a queue status indicator that displays:
- Running/pending job counts with visual badge
- Current job details with elapsed time
- DMR (Docker Model Runner) online/offline status
- Pending jobs list with task links
- Kill job functionality

Located in: `app/templates/base.html`

### Activity Log Page

Full activity log accessible at `/ui/activity/` showing:
- All job history with filters
- Stats cards (total, running, completed, failed)
- Auto-refresh capability

## Configuration

Environment variables:

```bash
# Enable/disable job queue (default: true)
JOB_QUEUE_ENABLED=true

# Job timeouts
LLM_TIMEOUT=300          # 5 minutes for LLM requests
AGENT_TIMEOUT=600        # 10 minutes for agent runs
VISION_TIMEOUT=120       # 2 minutes for vision analysis

# Cleanup
JOB_CLEANUP_HOURS=24     # Delete old jobs after 24 hours
```

## Flow Example: Agent Execution

1. **Director triggers agent** for task in DEV stage
2. **AgentService.trigger_agent()** is called
3. **Queue service creates LLMJob** with type=agent_run, priority=HIGH
4. **Agent worker picks up job** (FIFO within priority)
5. **Worker runs agent_runner.py** subprocess
6. **Goose executes** with project context
7. **Result is stored** in job.result_data
8. **Task status updated** based on result

## Troubleshooting

### Jobs Timing Out
- Check DMR health: `curl http://localhost:12434/engines/llama.cpp/v1/models`
- Increase timeout for complex tasks
- Monitor via Activity Log at `/ui/activity/`

### Queue Not Processing
- Verify workers are running: `GET /api/queue/status`
- Check for stuck running jobs
- Use `/api/queue/kill-all` to reset

### Job Stuck in Running
- Check worker status in queue status API
- Use `/api/queue/jobs/{id}/kill` to force stop
- Worker will mark job as failed
