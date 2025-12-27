/**
 * Bug Report Widget
 *
 * Embeddable JavaScript widget for capturing and submitting bug reports.
 * Supports both html2canvas auto-capture and manual file upload.
 *
 * Usage:
 *   <script>
 *     window.BUG_REPORT_API = 'http://localhost:8000/api/bugs/create';
 *     window.BUG_REPORT_APP = 'My App Name';
 *   </script>
 *   <script src="http://localhost:8000/static/bug-widget.js"></script>
 */
(function() {
  'use strict';

  // Configuration with defaults
  const CONFIG = {
    apiUrl: window.BUG_REPORT_API || 'http://localhost:8000/api/bugs/create',
    appName: window.BUG_REPORT_APP || 'Unknown App',
    buttonText: window.BUG_REPORT_BUTTON_TEXT || 'Report Bug',
    position: window.BUG_REPORT_POSITION || 'bottom-right',
    primaryColor: window.BUG_REPORT_COLOR || '#dc3545'
  };

  // Inject html2canvas from CDN
  let html2canvasLoaded = false;
  const script = document.createElement('script');
  script.src = 'https://html2canvas.hertzen.com/dist/html2canvas.min.js';
  script.onload = () => { html2canvasLoaded = true; };
  script.onerror = () => { console.warn('Bug Widget: html2canvas failed to load, using file upload only'); };
  document.head.appendChild(script);

  // CSS Styles
  const styles = `
    #bug-widget-btn {
      position: fixed;
      ${CONFIG.position.includes('bottom') ? 'bottom: 16px;' : 'top: 16px;'}
      ${CONFIG.position.includes('right') ? 'right: 16px;' : 'left: 16px;'}
      padding: 8px;
      background: transparent;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      z-index: 99998;
      opacity: 0.5;
      transition: opacity 0.2s, transform 0.2s;
    }
    #bug-widget-btn:hover {
      opacity: 1;
      transform: scale(1.15);
    }
    #bug-widget-btn svg {
      display: block;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
    }
    #bug-widget-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0,0,0,0.5);
      z-index: 99999;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #bug-widget-modal {
      background: white;
      border-radius: 8px;
      width: 90%;
      max-width: 500px;
      max-height: 90vh;
      overflow-y: auto;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    #bug-widget-modal h2 {
      margin: 0;
      padding: 16px 20px;
      background: ${CONFIG.primaryColor};
      color: white;
      font-size: 18px;
      border-radius: 8px 8px 0 0;
    }
    #bug-widget-form {
      padding: 20px;
    }
    .bug-widget-field {
      margin-bottom: 16px;
    }
    .bug-widget-field label {
      display: block;
      margin-bottom: 6px;
      font-weight: 500;
      color: #333;
      font-size: 14px;
    }
    .bug-widget-field input,
    .bug-widget-field textarea {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      font-family: inherit;
      box-sizing: border-box;
    }
    .bug-widget-field input:focus,
    .bug-widget-field textarea:focus {
      outline: none;
      border-color: ${CONFIG.primaryColor};
      box-shadow: 0 0 0 2px ${CONFIG.primaryColor}22;
    }
    .bug-widget-field textarea {
      min-height: 80px;
      resize: vertical;
    }
    #bug-widget-screenshot-preview {
      max-width: 100%;
      max-height: 200px;
      border: 1px solid #ddd;
      border-radius: 4px;
      margin-top: 8px;
      display: none;
    }
    .bug-widget-screenshot-actions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }
    .bug-widget-screenshot-actions button {
      padding: 8px 12px;
      border: 1px solid #ddd;
      background: #f5f5f5;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
      transition: background 0.2s;
    }
    .bug-widget-screenshot-actions button:hover {
      background: #eee;
    }
    .bug-widget-screenshot-actions button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    #bug-widget-file-input {
      display: none;
    }
    .bug-widget-buttons {
      display: flex;
      gap: 10px;
      justify-content: flex-end;
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid #eee;
    }
    .bug-widget-buttons button {
      padding: 10px 20px;
      border-radius: 4px;
      font-size: 14px;
      cursor: pointer;
      transition: background 0.2s;
    }
    #bug-widget-cancel {
      background: #f5f5f5;
      border: 1px solid #ddd;
      color: #333;
    }
    #bug-widget-cancel:hover {
      background: #eee;
    }
    #bug-widget-submit {
      background: ${CONFIG.primaryColor};
      border: none;
      color: white;
    }
    #bug-widget-submit:hover {
      opacity: 0.9;
    }
    #bug-widget-submit:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .bug-widget-status {
      padding: 12px;
      border-radius: 4px;
      margin-bottom: 16px;
      font-size: 14px;
    }
    .bug-widget-status.success {
      background: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .bug-widget-status.error {
      background: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
    .bug-widget-loading {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid #fff;
      border-top-color: transparent;
      border-radius: 50%;
      animation: bug-widget-spin 0.8s linear infinite;
      margin-right: 8px;
      vertical-align: middle;
    }
    @keyframes bug-widget-spin {
      to { transform: rotate(360deg); }
    }
  `;

  // Inject styles
  const styleEl = document.createElement('style');
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);

  // Ladybug SVG icon
  const ladybugSVG = `
    <svg viewBox="0 0 100 100" width="32" height="32" xmlns="http://www.w3.org/2000/svg">
      <!-- Body -->
      <ellipse cx="50" cy="55" rx="35" ry="40" fill="#e53935"/>
      <!-- Center line -->
      <line x1="50" y1="20" x2="50" y2="95" stroke="#222" stroke-width="3"/>
      <!-- Spots -->
      <circle cx="35" cy="45" r="8" fill="#222"/>
      <circle cx="65" cy="45" r="8" fill="#222"/>
      <circle cx="30" cy="70" r="7" fill="#222"/>
      <circle cx="70" cy="70" r="7" fill="#222"/>
      <circle cx="50" cy="80" r="6" fill="#222"/>
      <!-- Head -->
      <circle cx="50" cy="22" r="15" fill="#222"/>
      <!-- Eyes -->
      <circle cx="44" cy="20" r="4" fill="#fff"/>
      <circle cx="56" cy="20" r="4" fill="#fff"/>
      <circle cx="44" cy="21" r="2" fill="#222"/>
      <circle cx="56" cy="21" r="2" fill="#222"/>
      <!-- Antennae -->
      <path d="M42 10 Q38 2 32 5" stroke="#222" stroke-width="2" fill="none"/>
      <path d="M58 10 Q62 2 68 5" stroke="#222" stroke-width="2" fill="none"/>
    </svg>
  `;

  // Create floating button
  const button = document.createElement('button');
  button.id = 'bug-widget-btn';
  button.innerHTML = ladybugSVG;
  button.title = 'Report a Bug';
  document.body.appendChild(button);

  let screenshotData = null;

  // Show modal
  function showModal() {
    const overlay = document.createElement('div');
    overlay.id = 'bug-widget-overlay';
    overlay.innerHTML = `
      <div id="bug-widget-modal">
        <h2>Report a Bug</h2>
        <form id="bug-widget-form">
          <div id="bug-widget-status-container"></div>

          <div class="bug-widget-field">
            <label for="bug-widget-title">Title *</label>
            <input type="text" id="bug-widget-title" placeholder="Brief description of the issue" required>
          </div>

          <div class="bug-widget-field">
            <label for="bug-widget-description">Description</label>
            <textarea id="bug-widget-description" placeholder="What happened? What did you expect?"></textarea>
          </div>

          <div class="bug-widget-field">
            <label>Screenshot</label>
            <div class="bug-widget-screenshot-actions">
              <button type="button" id="bug-widget-capture" ${!html2canvasLoaded ? 'disabled title="html2canvas not loaded"' : ''}>
                Capture Screen
              </button>
              <button type="button" id="bug-widget-upload">
                Upload Image
              </button>
              <button type="button" id="bug-widget-clear-screenshot" style="display:none">
                Clear
              </button>
            </div>
            <input type="file" id="bug-widget-file-input" accept="image/*">
            <img id="bug-widget-screenshot-preview" alt="Screenshot preview">
          </div>

          <div class="bug-widget-buttons">
            <button type="button" id="bug-widget-cancel">Cancel</button>
            <button type="submit" id="bug-widget-submit">Submit Report</button>
          </div>
        </form>
      </div>
    `;

    document.body.appendChild(overlay);
    screenshotData = null;

    // Event listeners
    const form = document.getElementById('bug-widget-form');
    const captureBtn = document.getElementById('bug-widget-capture');
    const uploadBtn = document.getElementById('bug-widget-upload');
    const fileInput = document.getElementById('bug-widget-file-input');
    const clearBtn = document.getElementById('bug-widget-clear-screenshot');
    const preview = document.getElementById('bug-widget-screenshot-preview');
    const cancelBtn = document.getElementById('bug-widget-cancel');

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    // Close on Escape
    document.addEventListener('keydown', function escHandler(e) {
      if (e.key === 'Escape') {
        closeModal();
        document.removeEventListener('keydown', escHandler);
      }
    });

    cancelBtn.addEventListener('click', closeModal);

    // Capture screenshot
    captureBtn.addEventListener('click', async () => {
      if (!html2canvasLoaded || typeof html2canvas === 'undefined') {
        showStatus('html2canvas not available. Please upload an image instead.', 'error');
        return;
      }

      captureBtn.disabled = true;
      captureBtn.innerHTML = '<span class="bug-widget-loading"></span>Capturing...';

      // Hide the modal temporarily for capture
      overlay.style.display = 'none';

      try {
        const canvas = await html2canvas(document.body, {
          logging: false,
          useCORS: true,
          allowTaint: true
        });
        screenshotData = canvas.toDataURL('image/png');
        preview.src = screenshotData;
        preview.style.display = 'block';
        clearBtn.style.display = 'inline-block';
      } catch (err) {
        console.error('Screenshot capture failed:', err);
        showStatus('Failed to capture screenshot. Try uploading an image instead.', 'error');
      } finally {
        overlay.style.display = 'flex';
        captureBtn.disabled = false;
        captureBtn.innerHTML = 'Capture Screen';
      }
    });

    // Upload image
    uploadBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;

      if (!file.type.startsWith('image/')) {
        showStatus('Please select an image file.', 'error');
        return;
      }

      if (file.size > 5 * 1024 * 1024) {
        showStatus('Image too large. Maximum size is 5MB.', 'error');
        return;
      }

      const reader = new FileReader();
      reader.onload = (event) => {
        screenshotData = event.target.result;
        preview.src = screenshotData;
        preview.style.display = 'block';
        clearBtn.style.display = 'inline-block';
      };
      reader.readAsDataURL(file);
    });

    // Clear screenshot
    clearBtn.addEventListener('click', () => {
      screenshotData = null;
      preview.src = '';
      preview.style.display = 'none';
      clearBtn.style.display = 'none';
      fileInput.value = '';
    });

    // Submit form
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const title = document.getElementById('bug-widget-title').value.trim();
      const description = document.getElementById('bug-widget-description').value.trim();
      const submitBtn = document.getElementById('bug-widget-submit');

      if (!title) {
        showStatus('Please enter a title.', 'error');
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="bug-widget-loading"></span>Submitting...';

      const payload = {
        title: title,
        description: description || null,
        screenshot: screenshotData || null,
        url: window.location.href,
        app_name: CONFIG.appName,
        project_id: window.BUG_REPORT_PROJECT_ID || null
      };

      try {
        const response = await fetch(CONFIG.apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        showStatus(`Bug report submitted successfully! (ID: ${data.id})`, 'success');

        // Close after delay
        setTimeout(closeModal, 2000);

      } catch (err) {
        console.error('Bug report submission failed:', err);
        showStatus(`Failed to submit: ${err.message}`, 'error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Submit Report';
      }
    });

    // Focus title input
    document.getElementById('bug-widget-title').focus();
  }

  function showStatus(message, type) {
    const container = document.getElementById('bug-widget-status-container');
    container.innerHTML = `<div class="bug-widget-status ${type}">${message}</div>`;
  }

  function closeModal() {
    const overlay = document.getElementById('bug-widget-overlay');
    if (overlay) {
      overlay.remove();
    }
    screenshotData = null;
  }

  // Attach click handler
  button.addEventListener('click', showModal);

  // Expose API for programmatic use
  window.BugReportWidget = {
    open: showModal,
    close: closeModal,
    config: CONFIG
  };

  console.log('Bug Report Widget initialized for:', CONFIG.appName);
})();
