# WorkCycle Context
Generated: 2026-01-02 03:14:35
Run ID: 1252 | Project: Workflow Hub | Task: T024

## Pipeline Position
- **Current State**: pm
- **Your Role**: DEV
- **Run**: Execute Task: T023 - Pipelilne Activity Animation and Feedback
- **Goal**: No goal specified

## Current Task: T024
**Title**: Enhance job status display with elapsed time and cancel button
**Status**: in_progress
**Pipeline Stage**: DEV
**Priority**: 7

### Description
## Context
The unified task execution flow uses these endpoints:
- POST /api/tasks/{id}/start-work - triggers agent and returns job_id
- GET /api/tasks/{id}/job-status - returns job status for polling

## Files to Modify

### 1. app/templates/global_board.html

**CSS additions (after line 295 .job-status-badge.failed):**
```css
.job-elapsed {
    font-size: 8px;
    opacity: 0.8;
    margin-left: 4px;
}
.job-cancel-btn {
    background: transparent;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0 2px;
    margin-left: 2px;
    opacity: 0.7;
}
.job-cancel-btn:hover {
    opacity: 1;
}
```

**JavaScript modifications:**

1. Add to activeJobs Map storage (line 317):
```javascript
let activeJobs = new Map(); // Already exists
// Add: Store start times for elapsed display
let jobStartTimes = new Map();
```

2. Modify updateCardJobStatus function (line 560) to show elapsed time:
```javascript
function updateCardJobStatus(taskId, status, label, startTime = null) {
    // ... existing code ...
    if (status === "running" && startTime) {
        jobStartTimes.set(taskId, new Date(startTime));
    }
}
```

3. Add elapsed time updater (after startJobStatusPolling):
```javascript
setInterval(() => {
    jobStartTimes.forEach((startTime, taskId) => {
        const badge = document.querySelector(`.job-status-badge[data-task="${taskId}"]`);
        if (badge && badge.classList.contains("running")) {
            const elapsed = Math.floor((Date.now() - startTime.getTime()) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const timeSpan = badge.querySelector(".job-elapsed") || document.createElement("span");
            timeSpan.className = "job-elapsed";
            timeSpan.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;
            if (!badge.querySelector(".job-elapsed")) badge.appendChild(timeSpan);
        }
    });
}, 1000);
```

4. Add cancel function:
```javascript
function cancelJob(taskId) {
    const jobInfo = activeJobs.get(taskId);
    if (!jobInfo) return;
    fetch(`/api/queue/jobs/${jobInfo.jobId}/cancel`, { method: "POST" })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                updateCardJobStatus(taskId, "idle", "");
                activeJobs.delete(taskId);
                jobStartTimes.delete(taskId);
                showToast("Job cancelled", "info");
            }
        });
}
```

### 2. app/templates/partials/kanban_card_global.html

Modify job-status-badge span (line 11) to include cancel button:
```html
<span class="job-status-badge d-none" data-task="{{ task.id }}">
    <span class="job-label"></span>
    <button class="job-cancel-btn" onclick="event.stopPropagation(); cancelJob({{ task.id }})" title="Cancel">&times;</button>
</span>
```

### 3. app/views/api.py

The cancel endpoint already exists at /api/queue/jobs/{job_id}/cancel (queue_job_cancel function around line 2835).

## Testing
1. Start a job via the board play button
2. Verify elapsed time shows and updates every second
3. Click cancel button, verify job stops and badge disappears
4. Verify toast notification appears

### Acceptance Criteria
1. Running jobs show elapsed time (M:SS format) that updates every second in .job-elapsed span
2. Cancel button (X) appears in .job-status-badge for pending/running jobs
3. Clicking cancel calls /api/queue/jobs/{id}/cancel and removes job from activeJobs Map
4. jobStartTimes Map tracks start times for elapsed calculation
5. Toast notification confirms cancellation

## Previous Agent Work
No previous reports. You are the first agent on this run.

## Recent Git Commits
- `e9e16d6b` chore: Fix PostgREST env and add docker env template (MZ)
- `bc7cfad7` refactor: Simplify core architecture with PostgREST (MZ)
- `d6a7b2b4` fix: Correct project detail link in task board (projects -> project) (MZ)
- `ac41d7eb` feat: Auto-generate ledger entries and tasks on claim failure (MZ)
- `25bd4a97` feat: Add Failed Claims Ledger UI (MZ)

## Uncommitted Changes
```
CLAUDE.md                                          |    5 +
 .../a87c1e3226a4_refactor_simplify_core.py         |   10 +-
 app/models/__init__.py                             |   21 +-
 app/models/handoff.py                              |  126 ---
 app/models/requirement.py                          |   11 +-
 app/models/task.py                                 |   51 +-
 app/models/work_cycle.py                           |   95 +-
 app/services/agent_service.py                      |  220 ++++-
 app/services/director_service.py                   |  144 ++-
 app/services/handoff_service.py                    |  735 --------------
 app/services/llm_service.py                        |   34 +-
 app/services/run_service.py                        |   27 +-
 app/services/task_queue_service.py                 |   71 +-
 app/services/webhook_service.py                    |   26 +-
 app/services/work_cycle_service.py                 | 1007 ++++++++++++++------
 app/templates/base.html                            |   68 +-
 app/templates/dashboard.html                       |  161 ++++
 app/templates/partials/kanban_card.html            |   39 +-
 app/templates/task_board.html                      |  390 +++++++-
 app/urls.py                                        |   28 +-
 app/views/api.py                                   |  861 ++++++++++++++---
 app/views/ui.py                                    |   77 +-
 config/settings.py                                 |    2 +-
 ledger/failed_claims.yaml                          |   13 +-
 screenshots/01_dashboard.png                       |  Bin 132856 -> 341163 bytes
 screenshots/02_run_detail.png                      |  Bin 324477 -> 305533 bytes
 screenshots/03_task_modal.png                      |  Bin 293571 -> 315996 bytes
 screenshots/04_add_task_modal.png                  |  Bin 282016 -> 305280 bytes
 screenshots/05_projects_list.png                   |  Bin 62276 -> 235406 bytes
 screenshots/06_runs_list.png                       |  Bin 54434 -> 271976 bytes
 scripts/agent_runner.py                            |  145 +--
 scripts/workflow.py                                |   54 +-
 tests/conftest.py                                  |  107 ++-
 tests/e2e/test_pipeline_monitoring.py              |    2 +-
 tests/test_bug_api.py                              |   20 +-
 tests/test_project_api.py                          |   31 +-
 tests/test_task_queue.py                           |   32 +-
 tests/test_task_queue_service.py                   |  105 +-
 tests/test_ui_views.py                             |    2 +-
 tests/test_workflow_tui.py                         |    8 +-
 40 files changed, 2967 insertions(+), 1761 deletions(-)
```

## Your Deliverables
- Implement code to satisfy tests
- Follow TDD - tests should already exist from QA
- COMMIT: Stage and commit ALL changes with descriptive message (git add -A && git commit -m '...')
- Output JSON report with files changed and commit hash

## Important
- Stay within workspace: /Users/mz/Dropbox/_CODING/Agentic
- Output a JSON status report when done
- Do NOT modify files outside the project
