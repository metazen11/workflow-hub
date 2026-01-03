# WorkCycle Context
Generated: 2026-01-02 12:31:58
Run ID: 1367 | Project: Workflow Hub | Task: T025

## Pipeline Position
- **Current State**: pm
- **Your Role**: PM
- **Run**: Execute Task: SEO-003 - Create GitHub release v0.1.0
- **Goal**: No goal specified

## Current Task: T025
**Title**: Add Simplify button to task detail view
**Status**: in_progress
**Pipeline Stage**: QA
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
- `e12ba823` feat: Add inline-editable settings page for app configuration (MZ)
- `62635a52` feat: Persist Director settings to database for auto-start on restart (MZ)
- `38767aeb` T001: Setup project structure and dependencies - Added tests to validate project setup (MZ)
- `0094c4fe` feat: Add queue status indicator with DMR health display (MZ)
- `bec4bc20` T001: Setup project structure and dependencies - All requirements met and tests passing (MZ)

## Uncommitted Changes
```
CLAUDE.md                        |  18 ++++++
 Dockerfile                       |   5 +-
 app/apps.py                      |  15 ++++-
 app/models/director_settings.py  |  28 +++++++++
 app/services/director_service.py |   8 +++
 app/views/api.py                 | 124 +++++++++++++++++++++++++++------------
 requirements.txt                 |   1 +
 screenshots/01_dashboard.png     | Bin 341163 -> 304882 bytes
 screenshots/02_run_detail.png    | Bin 305533 -> 308604 bytes
 screenshots/03_task_modal.png    | Bin 315996 -> 318595 bytes
 screenshots/05_projects_list.png | Bin 235406 -> 102157 bytes
 screenshots/06_runs_list.png     | Bin 271976 -> 284084 bytes
 screenshots/debug_no_button.png  | Bin 71605 -> 75153 bytes
 13 files changed, 158 insertions(+), 41 deletions(-)
```

## Your Deliverables
- Break down requirements into tasks
- Update _spec/BRIEF.md with goals
- Create task definitions with acceptance criteria
- Output JSON report with task breakdown

## Important
- Stay within workspace: /Users/mz/Dropbox/_CODING/Agentic
- Output a JSON status report when done
- Do NOT modify files outside the project
