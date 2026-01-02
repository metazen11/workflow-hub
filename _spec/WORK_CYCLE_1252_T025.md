# WorkCycle Context
Generated: 2026-01-02 04:20:19
Run ID: 1252 | Project: Workflow Hub | Task: T025

## Pipeline Position
- **Current State**: pm
- **Your Role**: DEV
- **Run**: Execute Task: T023 - Pipelilne Activity Animation and Feedback
- **Goal**: No goal specified

## Current Task: T025
**Title**: Add Simplify button to task detail view
**Status**: in_progress
**Pipeline Stage**: DEV
**Priority**: 6

### Description
## Implementation Steps

1. In `app/models/task.py`, add a new method `simplify_description` to the Task class that returns a simplified version of the description:
```python
def simplify_description(self):
    # Placeholder for simplification logic
    return f"Simplified steps for: {self.description}"
```

2. In `app/views/task_views.py`, add a new endpoint `/api/tasks/{id}/simplify` that handles POST requests:
```python
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def simplify_task(request, task_id):
    if request.method == 'POST':
        task = Task.objects.get(id=task_id)
        simplified = task.simplify_description()
        return JsonResponse({'implementation_steps': simplified})
    return JsonResponse({'error': 'Invalid request'}, status=400)
```

3. In `app/urls.py`, add the new URL pattern for the simplify endpoint:
```python
from django.urls import path
from .views import task_views

urlpatterns = [
    path('api/tasks/<int:task_id>/simplify', task_views.simplify_task, name='simplify_task'),
    # existing patterns...
]
```

4. In `templates/task_detail.html`, locate the Enhance button and add the Simplify button next to it:
```html
<button id="enhance-btn" class="btn btn-primary">Enhance</button>
<button id="simplify-btn" class="btn btn-secondary">Simplify</button>
```

5. In `static/js/task_detail.js`, add JavaScript to handle the Simplify button click:
```javascript
document.getElementById('simplify-btn').addEventListener('click', async function() {
    const taskId = {{ task.id }};
    const button = this;
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Simplifying...';

    try {
        const response = await fetch(`/api/tasks/${taskId}/simplify`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const data = await response.json();
        if (data.implementation_steps) {
            document.getElementById('description').innerText = data.implementation_steps;
        }
    } catch (error) {
        console.error('Error:', error);
    } finally {
        button.disabled = false;
        button.innerHTML = 'Simplify';
    }
});
```

6. In `static/css/task_detail.css`, ensure both buttons have consistent styling:
```css
.btn-secondary {
    background-color: #6c757d;
    border-color: #6c757d;
}
```

7. Run unit tests to verify the new functionality:
```bash
pytest tests/test_task_views.py -v
```

---
<details>
<summary>Original Description</summary>

Add a Simplify button next to the Enhance button on the task detail page that calls /api/tasks/{id}/simplify to convert complex task descriptions into step-by-step implementation instructions. The button should be styled consistently with the Enhance button and show a loading state while the API call is in progress.
</details>

### Acceptance Criteria
1. Simplify button appears next to Enhance button on task detail view
2. Button calls POST /api/tasks/{id}/simplify when clicked
3. Loading spinner shown during API call
4. Task description updates to show Implementation Steps after success

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
 app/services/work_cycle_service.py                 | 1007 +++++++++++++------
 app/templates/base.html                            |   68 +-
 app/templates/dashboard.html                       |  161 ++++
 app/templates/partials/kanban_card.html            |   39 +-
 app/templates/task_board.html                      |  390 +++++++-
 app/urls.py                                        |   29 +-
 app/views/api.py                                   | 1015 +++++++++++++++++---
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
 40 files changed, 3122 insertions(+), 1761 deletions(-)
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
