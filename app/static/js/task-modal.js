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
    // Clear dropzone if available
    if (typeof clearDropzone === 'function') clearDropzone();
    _taskModalTaskId = null;
}

/**
 * Save task changes from modal
 */
async function saveTaskModal() {
    if (!_taskModalTaskId) return;

    const title = document.getElementById('modal-task-title').value.trim();
    const description = document.getElementById('modal-task-description').value.trim();
    const priority = parseInt(document.getElementById('modal-task-priority').value) || 5;
    const stage = document.getElementById('modal-task-stage').value;
    const status = document.getElementById('modal-task-status').value;
    const filesInput = document.getElementById('modal-task-files');
    const files = filesInput ? filesInput.files : [];

    if (!title) {
        alert('Title is required');
        return;
    }

    try {
        // Update task details
        let res = await fetch(`/api/tasks/${_taskModalTaskId}/update`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, description, priority })
        });
        let data = await res.json();
        if (!data.task && !data.success) throw new Error(data.error || 'Failed to update task');

        // Update status
        await fetch(`/api/tasks/${_taskModalTaskId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status })
        });

        // Update stage
        await fetch(`/api/tasks/${_taskModalTaskId}/set-stage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage })
        });

        // Upload files if any
        if (files.length > 0) {
            await uploadTaskFiles(_taskModalTaskId, files);
        }

        closeTaskModal();
        window.location.reload();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

/**
 * Upload files to a task
 * @param {number} taskId - Task ID to attach files to
 * @param {FileList|Array} files - Files to upload
 * @returns {Promise<Array>} Array of upload results
 */
async function uploadTaskFiles(taskId, files) {
    const results = [];
    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`/api/tasks/${taskId}/attachments/upload`, {
                method: 'POST',
                body: formData
            });
            results.push(await res.json());
        } catch (err) {
            results.push({ error: err.message, filename: file.name });
        }
    }
    return results;
}

/**
 * Create a task and optionally upload attachments
 * @param {number} projectId - Project ID
 * @param {object} taskData - {title, description, priority}
 * @param {FileList|Array} files - Optional files to attach
 * @returns {Promise<object>} Created task
 */
async function createTaskWithFiles(projectId, taskData, files = []) {
    // Create the task
    const res = await fetch(`/api/projects/${projectId}/tasks/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(taskData)
    });
    const result = await res.json();

    if (!result.task) {
        throw new Error(result.error || 'Failed to create task');
    }

    // Upload files if provided
    if (files && files.length > 0) {
        await uploadTaskFiles(result.task.id, files);
    }

    return result.task;
}

/**
 * Initialize a dropzone for file uploads with drag-drop and previews
 * @param {string} dropzoneId - ID of the dropzone container
 * @param {string} inputId - ID of the file input
 * @param {string} previewsId - ID of the previews container
 * @returns {object} - {clear: function} to reset the dropzone
 */
function initDropzone(dropzoneId, inputId, previewsId) {
    const dropzone = document.getElementById(dropzoneId);
    const fileInput = document.getElementById(inputId);
    const previews = document.getElementById(previewsId);
    if (!dropzone || !fileInput || !previews) return null;

    let fileList = new DataTransfer();

    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

    function handleFiles(files) {
        for (const file of files) {
            fileList.items.add(file);
            addPreview(file, fileList.items.length - 1);
        }
        fileInput.files = fileList.files;
    }

    function addPreview(file, index) {
        const div = document.createElement('div');
        div.className = 'file-preview';
        if (file.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            div.appendChild(img);
        } else {
            div.innerHTML = '<div class="file-icon">📄</div>';
        }
        const btn = document.createElement('button');
        btn.className = 'remove-btn';
        btn.type = 'button';
        btn.textContent = '×';
        btn.onclick = (e) => { e.stopPropagation(); removeFile(index); };
        div.appendChild(btn);
        previews.appendChild(div);
    }

    function removeFile(index) {
        const newList = new DataTransfer();
        for (let i = 0; i < fileList.files.length; i++) {
            if (i !== index) newList.items.add(fileList.files[i]);
        }
        fileList = newList;
        fileInput.files = fileList.files;
        refreshPreviews();
    }

    function refreshPreviews() {
        previews.innerHTML = '';
        for (let i = 0; i < fileList.files.length; i++) {
            addPreview(fileList.files[i], i);
        }
    }

    function clear() {
        fileList = new DataTransfer();
        fileInput.files = fileList.files;
        previews.innerHTML = '';
    }

    return { clear };
}

// Setup modal event handlers when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('task-modal');
    if (!modal) return;

    // Initialize dropzone for task modal
    const modalDropzone = initDropzone('modal-dropzone', 'modal-task-files', 'modal-file-previews');
    if (modalDropzone) {
        window.clearDropzone = modalDropzone.clear;
    }

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
