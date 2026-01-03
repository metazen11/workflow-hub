# WorkCycle Context
Generated: 2026-01-02 03:04:35
Run ID: 1252 | Project: Workflow Hub | Task: T020

## Pipeline Position
- **Current State**: pm
- **Your Role**: DEV
- **Run**: Execute Task: T023 - Pipelilne Activity Animation and Feedback
- **Goal**: No goal specified

## Current Task: T020
**Title**: when i switch states in the task view - the button does not get updated to RUN [NEW STATE] AGENT
**Status**: in_progress
**Pipeline Stage**: DEV
**Priority**: 5

### Description
a bug in the ui where i can switch the state but button to run the agent in that state is not reflected
http://localhost:8000/ui/task/689/
button <button id="run-agent-fallback" class="btn btn-primary" onclick="triggerAgent(689)">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 6px;">
                                <polygon points="5 3 19 12 5 21 5 3"></polygon>
                            </svg>
                            Run NONE Agent
                        </button>

this should be updatd to the correct agent when you click on <button class="btn btn-secondary" id="move-stage-btn" data-task-id="689">
                        Move to Stage
                    </button>

also when you click on prepare- this should update the project description with the acceptance criteria.

the task description should get reloaded after you click on prepare.



### Acceptance Criteria
1. Bug is fixed and no longer reproducible
2. Regression test added to prevent recurrence
3. Root cause documented in commit message

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
