/**
 * Task Modal - Shared JavaScript for task editing modal
 * Used by: dashboard.html, run_detail.html, project_detail.html
 *
 * Include after DOM ready:
 *   <script src="/static/js/task-modal.js"></script>
 */

// Current task being edited
let _taskModalTaskId = null;

/**
 * Open the task modal for editing
 * @param {number|string} taskId - Task ID
 * @param {object} taskData - Optional task data {title, description, priority, stage, status}
 */
function openTaskModal(taskId, taskData = null) {
    _taskModalTaskId = taskId;

    const modal = document.getElementById('task-modal');
    if (!modal) {
        console.error('Task modal not found - include partials/task_modal.html');
        return;
    }

    // Reset form
    document.getElementById('modal-task-id').value = taskId;
    document.getElementById('modal-task-title').value = '';
    document.getElementById('modal-task-description').value = '';
    document.getElementById('modal-task-priority').value = '5';
    document.getElementById('modal-task-stage').value = 'none';
    document.getElementById('modal-task-status').value = 'backlog';

    if (taskData) {
        // Use provided data
        populateTaskModal(taskData);
        modal.style.display = 'flex';
    } else {
        // Fetch from API
        fetch(`/api/tasks/${taskId}/details`)
            .then(r => r.json())
            .then(data => {
                if (data.task) {
                    populateTaskModal(data.task);
                }
                modal.style.display = 'flex';
            })
            .catch(() => {
                modal.style.display = 'flex';
            });
    }
}

/**
 * Populate modal fields with task data
 */
function populateTaskModal(task) {
    if (task.title) document.getElementById('modal-task-title').value = task.title;
    if (task.description) document.getElementById('modal-task-description').value = task.description;
    if (task.priority) document.getElementById('modal-task-priority').value = task.priority;
    if (task.pipeline_stage) document.getElementById('modal-task-stage').value = task.pipeline_stage;
    if (task.status) document.getElementById('modal-task-status').value = task.status;
}

/**
 * Close the task modal
 */
function closeTaskModal() {
    const modal = document.getElementById('task-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    _taskModalTaskId = null;
}

/**
 * Save task changes from modal
 */
function saveTaskModal() {
    if (!_taskModalTaskId) return;

    const title = document.getElementById('modal-task-title').value.trim();
    const description = document.getElementById('modal-task-description').value.trim();
    const priority = parseInt(document.getElementById('modal-task-priority').value) || 5;
    const stage = document.getElementById('modal-task-stage').value;
    const status = document.getElementById('modal-task-status').value;

    if (!title) {
        alert('Title is required');
        return;
    }

    // Update task details
    fetch(`/api/tasks/${_taskModalTaskId}/update`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description, priority })
    })
    .then(r => r.json())
    .then(data => {
        if (data.task || data.success) {
            // Update status
            return fetch(`/api/tasks/${_taskModalTaskId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: status })
            });
        } else {
            throw new Error(data.error || 'Failed to update task');
        }
    })
    .then(r => r.json())
    .then(data => {
        // Update stage
        return fetch(`/api/tasks/${_taskModalTaskId}/set-stage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: stage })
        });
    })
    .then(r => r.json())
    .then(data => {
        closeTaskModal();
        window.location.reload();
    })
    .catch(err => alert('Error: ' + err.message));
}

// Setup modal event handlers when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('task-modal');
    if (!modal) return;

    // Close on outside click
    modal.addEventListener('click', function(e) {
        if (e.target === this) closeTaskModal();
    });

    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            closeTaskModal();
        }
    });
});
