/**
 * Inline Edit - Click-to-edit functionality for Workflow Hub
 * Based on PyCRUD pattern - click any .editable element to edit inline
 */
class InlineEdit {
    constructor(options = {}) {
        this.saveUrl = options.saveUrl || '/api/projects/{id}/update';
        this.entityId = options.entityId;
        this.onSave = options.onSave || (() => {});
        this.onError = options.onError || ((err) => console.error(err));
        this.init();
    }

    init() {
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Click to edit
        document.addEventListener('click', (e) => {
            const editable = e.target.closest('.editable');
            if (editable && !editable.classList.contains('editing')) {
                this.makeEditable(editable);
            }
        });

        // Save on blur
        document.addEventListener('blur', (e) => {
            if (e.target.classList.contains('inline-input')) {
                this.save(e.target);
            }
        }, true);

        // Save on Enter, cancel on Escape
        document.addEventListener('keydown', (e) => {
            if (e.target.classList.contains('inline-input')) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.save(e.target);
                } else if (e.key === 'Escape') {
                    this.cancel(e.target);
                }
            }
        });
    }

    makeEditable(element) {
        const currentValue = element.textContent.trim();
        const field = element.dataset.field;
        const inputType = element.dataset.type || 'text';

        // Store original value for cancel
        element.dataset.originalValue = currentValue;
        element.classList.add('editing');

        // Create appropriate input element
        let input;
        if (inputType === 'textarea' || element.dataset.multiline) {
            input = document.createElement('textarea');
            input.rows = 3;
        } else {
            input = document.createElement('input');
            input.type = inputType;
        }

        input.className = 'inline-input';
        input.value = currentValue === '-' ? '' : currentValue;
        input.dataset.field = field;

        // Style to match container
        input.style.width = '100%';
        input.style.padding = '4px 8px';
        input.style.border = '2px solid #4a90d9';
        input.style.borderRadius = '4px';
        input.style.fontSize = 'inherit';
        input.style.fontFamily = 'inherit';
        input.style.backgroundColor = '#fff';
        input.style.outline = 'none';

        // Replace content with input
        element.innerHTML = '';
        element.appendChild(input);
        input.focus();
        input.select();
    }

    async save(input) {
        const element = input.parentElement;
        const field = input.dataset.field;
        const newValue = input.value.trim();
        const originalValue = element.dataset.originalValue;

        // No change
        if (newValue === originalValue || (newValue === '' && originalValue === '-')) {
            this.restoreDisplay(element, originalValue);
            return;
        }

        // Show saving state
        element.classList.add('saving');
        input.disabled = true;

        try {
            const url = this.saveUrl.replace('{id}', this.entityId);
            const response = await fetch(url, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ [field]: newValue || null })
            });

            const result = await response.json();

            if (response.ok && (result.project || result.status === 'success')) {
                // Success - show new value
                this.restoreDisplay(element, newValue || '-');
                this.showFeedback(element, 'success');
                this.onSave(field, newValue);
            } else {
                // Error - restore original
                this.restoreDisplay(element, originalValue);
                this.showFeedback(element, 'error');
                this.onError(result.error || 'Failed to save');
            }
        } catch (error) {
            this.restoreDisplay(element, originalValue);
            this.showFeedback(element, 'error');
            this.onError(error.message);
        }
    }

    cancel(input) {
        const element = input.parentElement;
        const originalValue = element.dataset.originalValue;
        this.restoreDisplay(element, originalValue);
    }

    restoreDisplay(element, value) {
        element.classList.remove('editing', 'saving');
        element.textContent = value || '-';
        delete element.dataset.originalValue;
    }

    showFeedback(element, type) {
        element.classList.add(`feedback-${type}`);
        setTimeout(() => {
            element.classList.remove(`feedback-${type}`);
        }, 1500);
    }
}

// CSS styles for inline editing
const inlineEditStyles = `
.editable {
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
    transition: background-color 0.2s;
    min-height: 1.2em;
}
.editable:hover {
    background-color: rgba(74, 144, 217, 0.1);
}
.editable:hover::after {
    content: ' ✎';
    opacity: 0.5;
    font-size: 0.8em;
}
.editable.editing {
    padding: 0;
}
.editable.editing:hover::after {
    content: '';
}
.editable.saving {
    opacity: 0.6;
}
.editable.feedback-success {
    background-color: rgba(40, 167, 69, 0.2);
}
.editable.feedback-error {
    background-color: rgba(220, 53, 69, 0.2);
}
.inline-input {
    box-sizing: border-box;
}
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = inlineEditStyles;
document.head.appendChild(styleSheet);
