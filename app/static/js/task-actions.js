/**
 * Task Actions - Shared JavaScript for task operations
 * Include in base.html for site-wide availability
 */

// Delete task via event delegation
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.delete-task-btn');
    if (!btn) return;

    const taskId = btn.dataset.taskId;
    const title = btn.dataset.title || 'this task';

    if (!confirm(`Are you sure you want to delete "${title}"? This cannot be undone.`)) {
        return;
    }

    fetch(`/api/tasks/${taskId}/delete`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Try to remove from DOM if in a list
            const taskItem = btn.closest('.task-item');
            if (taskItem) {
                taskItem.remove();
                // Update task count if displayed
                const countEl = document.querySelector('.tasks-count');
                if (countEl) {
                    const current = parseInt(countEl.textContent) || 0;
                    countEl.textContent = Math.max(0, current - 1);
                }
            } else {
                // If on task detail page, redirect
                window.location.href = '/ui/projects/';
            }
        } else {
            alert('Error: ' + (data.error || 'Failed to delete task'));
        }
    })
    .catch(err => {
        console.error('Delete error:', err);
        alert('Failed to delete task');
    });
});
