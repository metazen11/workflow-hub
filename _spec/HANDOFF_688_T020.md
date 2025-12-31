# Handoff Context
Generated: 2025-12-31 17:48:02
Run ID: 688 | Project: Workflow Hub | Task: T020

## Pipeline Position
- **Current State**: docs
- **Your Role**: DOCS
- **Run**: Execute Task: T020 - when i switch states in the task view - the button does not get updated to R...
- **Goal**: PM agent execution completed

## Current Task: T020
**Title**: when i switch states in the task view - the button does not get updated to RUN [NEW STATE] AGENT
**Status**: in_progress
**Pipeline Stage**: DOCS
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
### PM Agent (12-31 17:47)
**Status**: pass
**Summary**: PM agent execution completed

```
starting session | provider: ollama model: ai/qwen3-coder:latest
    session id: 20251231_15
    working directory: /Users/mz/Dropbox/_CODING/Agentic
Ran into this error: Server error: Server error (500 Internal Server Error): .

Please retry if you think this is a transient or recoverable error.

```
---
### DEV Agent (12-31 17:47)
**Status**: pass
**Summary**: DEV agent execution completed

```
starting session | provider: ollama model: ai/qwen3-coder:latest
    session id: 20251231_16
    working directory: /Users/mz/Dropbox/_CODING/Agentic
Ran into this error: Server error: Server error (500 Internal Server Error): .

Please retry if you think this is a transient or recoverable error.

```
---
### QA Agent (12-31 17:47)
**Status**: pass
**Summary**: QA agent execution completed

```
starting session | provider: ollama model: ai/qwen3-coder:latest
    session id: 20251231_17
    working directory: /Users/mz/Dropbox/_CODING/Agentic
Ran into this error: Server error: Server error (500 Internal Server Error): .

Please retry if you think this is a transient or recoverable error.

```
---
### SECURITY Agent (12-31 17:48)
**Status**: pass
**Summary**: SECURITY agent execution completed

```
starting session | provider: ollama model: ai/qwen3-coder:latest
    session id: 20251231_18
    working directory: /Users/mz/Dropbox/_CODING/Agentic
Ran into this error: Server error: Server error (500 Internal Server Error): .

Please retry if you think this is a transient or recoverable error.

```
---
## Recent Git Commits
- `368f8bb7` fix: Truncate run name to fit varchar(100) column limit (MZ)
- `f89d39e3` feat: Add Tasks nav menu, dedicated task list view, and auto-attach screenshots (MZ)
- `d2daf3bf` feat: Configure LLM context sizes in install script (MZ)
- `3c107133` fix: Add PM stage to task pipeline kanban board (MZ)
- `8cdb3762` feat: Add start.sh script, fix project_delete CSRF (MZ)

## Your Deliverables
- VERIFY: Run tests first (pytest), ensure feature works
- CAPTURE: Take screenshots of working feature (Playwright)
- UPLOAD: Submit proofs to /api/runs/{run_id}/proofs/upload
- FIX: If tests fail, fix issues (second-layer debug)
- DOCUMENT: Update README.md and docs/ with working examples
- COMMIT: Stage and commit all documentation and fixes
- Output JSON report with tests_passed, screenshots_taken, proofs_uploaded, commit_hash

## Important
- Stay within workspace: /Users/mz/Dropbox/_CODING/Agentic
- Output a JSON status report when done
- Do NOT modify files outside the project
