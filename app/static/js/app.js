/**
 * Workflow Hub - Dashboard JavaScript
 * Handles auto-refresh, theme toggle, and keyboard shortcuts
 */

(function () {
  'use strict';

  // Configuration
  const REFRESH_INTERVAL = 30000; // 30 seconds
  const COUNTDOWN_SECONDS = 30;
  let countdown = COUNTDOWN_SECONDS;
  let isPaused = false;
  let lastDataHash = null;
  let isUpdatingDOM = false; // Flag to prevent observer feedback loop
  let refreshIntervalId = null;

  // ============================================
  // Theme Management
  // ============================================
  function getPreferredTheme() {
    const stored = localStorage.getItem('theme');
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    setTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Initialize theme
  const initialTheme = getPreferredTheme();
  if (initialTheme) {
    setTheme(initialTheme);
  }

  // Theme toggle button
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', toggleTheme);
  }

  // ============================================
  // Auto-Refresh (Smarter, Less Aggressive)
  // ============================================
  const countdownEl = document.querySelector('.refresh-countdown');
  const mainContent = document.getElementById('main-content');

  function updateCountdown() {
    if (countdownEl) {
      if (isPaused) {
        countdownEl.textContent = '⏸';
        countdownEl.title = 'Auto-refresh paused (modal open or user active)';
      } else {
        countdownEl.textContent = countdown;
        countdownEl.title = `Auto-refresh in ${countdown}s`;
      }
    }
  }

  // Simple hash for change detection
  function hashContent(content) {
    let hash = 0;
    for (let i = 0; i < content.length; i++) {
      const char = content.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash;
  }

  function refreshContent() {
    if (isPaused || isUpdatingDOM) return;

    fetch(window.location.href, {
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(response => response.text())
      .then(html => {
        // Re-check pause state after async fetch
        if (isPaused) {
          countdown = COUNTDOWN_SECONDS;
          updateCountdown();
          return;
        }

        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const newContent = doc.getElementById('main-content');

        if (newContent && mainContent) {
          // Check if content actually changed
          const newHash = hashContent(newContent.innerHTML);
          if (newHash === lastDataHash) {
            // No changes, skip update
            countdown = COUNTDOWN_SECONDS;
            updateCountdown();
            return;
          }
          lastDataHash = newHash;

          // Set flag to prevent observer feedback loop
          isUpdatingDOM = true;

          // Smooth transition only if there are changes
          mainContent.style.opacity = '0.7';
          setTimeout(() => {
            mainContent.innerHTML = newContent.innerHTML;
            mainContent.style.opacity = '1';
            // Clear flag after DOM update settles
            setTimeout(() => {
              isUpdatingDOM = false;
            }, 50);
          }, 100);
        }

        // Reset countdown
        countdown = COUNTDOWN_SECONDS;
        updateCountdown();
      })
      .catch(err => {
        console.warn('Refresh failed:', err);
        countdown = COUNTDOWN_SECONDS;
        updateCountdown();
      });
  }

  function startAutoRefresh() {
    // Prevent multiple intervals
    if (refreshIntervalId) {
      clearInterval(refreshIntervalId);
    }

    // Countdown timer - every second
    refreshIntervalId = setInterval(() => {
      if (!isPaused && !isUpdatingDOM) {
        countdown--;
        updateCountdown();

        if (countdown <= 0) {
          refreshContent();
        }
      }
    }, 1000);
  }

  // Pause refresh when user is interacting
  let interactionTimer = null;
  const RESUME_DELAY = 5000; // Resume 5 seconds after last interaction

  function pauseRefresh() {
    isPaused = true;
    updateCountdown();
  }

  function resumeRefresh() {
    isPaused = false;
    countdown = COUNTDOWN_SECONDS; // Reset countdown when resuming
    updateCountdown();
  }

  // Expose globally for other scripts to use
  window.pauseAutoRefresh = pauseRefresh;
  window.resumeAutoRefresh = resumeRefresh;

  // Check if any modal/overlay is visible OR if a native dialog might be open
  let nativeDialogActive = false;

  // Override native confirm/alert/prompt to track when they're active
  const originalConfirm = window.confirm;
  const originalAlert = window.alert;
  const originalPrompt = window.prompt;

  window.confirm = function (...args) {
    nativeDialogActive = true;
    pauseRefresh();
    try {
      return originalConfirm.apply(this, args);
    } finally {
      nativeDialogActive = false;
      // Don't resume immediately - wait for any subsequent action
      setTimeout(() => {
        if (!isEditing() && !isModalOpen() && !nativeDialogActive) {
          resumeRefresh();
        }
      }, 1000);
    }
  };

  window.alert = function (...args) {
    nativeDialogActive = true;
    pauseRefresh();
    try {
      return originalAlert.apply(this, args);
    } finally {
      nativeDialogActive = false;
      setTimeout(() => {
        if (!isEditing() && !isModalOpen() && !nativeDialogActive) {
          resumeRefresh();
        }
      }, 1000);
    }
  };

  window.prompt = function (...args) {
    nativeDialogActive = true;
    pauseRefresh();
    try {
      return originalPrompt.apply(this, args);
    } finally {
      nativeDialogActive = false;
      setTimeout(() => {
        if (!isEditing() && !isModalOpen() && !nativeDialogActive) {
          resumeRefresh();
        }
      }, 1000);
    }
  };

  function isModalOpen() {
    // Check for native dialogs first
    if (nativeDialogActive) return true;

    // Check for any visible modal using class-based detection (no getComputedStyle)
    const modals = document.querySelectorAll('.modal');
    for (const modal of modals) {
      // Check for common "open" patterns: active class or inline style
      if (modal.classList.contains('active') ||
        modal.classList.contains('show') ||
        modal.classList.contains('open') ||
        modal.style.display === 'flex' ||
        modal.style.display === 'block') {
        return true;
      }
    }
    // Check for keyboard help overlay
    if (document.getElementById('keyboard-help')) {
      return true;
    }
    return false;
  }

  // Check if user is editing (any editable element has focus)
  function isEditing() {
    const active = document.activeElement;
    if (!active) return false;

    const editableTags = ['INPUT', 'TEXTAREA', 'SELECT'];
    if (editableTags.includes(active.tagName)) return true;

    // Check for contenteditable elements
    if (active.isContentEditable) return true;

    return false;
  }

  // Universal interaction handler - pause on any form activity
  function handleInteraction() {
    // Clear any pending resume
    if (interactionTimer) {
      clearTimeout(interactionTimer);
      interactionTimer = null;
    }

    // Pause if editing or modal open
    if (isEditing() || isModalOpen()) {
      pauseRefresh();
      return;
    }
  }

  // Schedule resume after interaction stops
  function scheduleResume() {
    if (interactionTimer) clearTimeout(interactionTimer);

    interactionTimer = setTimeout(() => {
      // Only resume if not editing and no modals open
      if (!isEditing() && !isModalOpen()) {
        resumeRefresh();
      }
    }, RESUME_DELAY);
  }

  // Watch for DOM changes (modals opening/closing)
  // Use debounced observer to prevent feedback loops
  let observerTimeout = null;
  const observer = new MutationObserver(() => {
    // Skip if we're in the middle of a refresh update
    if (isUpdatingDOM) return;

    // Debounce observer callbacks
    if (observerTimeout) clearTimeout(observerTimeout);
    observerTimeout = setTimeout(() => {
      if (isUpdatingDOM) return; // Double-check after timeout
      if (isModalOpen() || isEditing()) {
        pauseRefresh();
      } else if (isPaused) {
        scheduleResume();
      }
    }, 100);
  });
  // Only observe modals container and form elements, not the entire body
  observer.observe(document.body, { childList: true, subtree: false, attributes: true, attributeFilter: ['class'] });

  // Pause immediately when user focuses any editable element
  document.addEventListener('focus', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
      e.target.tagName === 'SELECT' || e.target.isContentEditable) {
      pauseRefresh();
    }
  }, true);

  // Schedule resume when focus leaves editable element
  document.addEventListener('blur', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
      e.target.tagName === 'SELECT' || e.target.isContentEditable) {
      scheduleResume();
    }
  }, true);

  // Pause on any click inside a modal
  document.addEventListener('click', (e) => {
    if (e.target.closest('.modal')) {
      pauseRefresh();
    }
  }, true);

  // Pause while typing anywhere
  document.addEventListener('keydown', (e) => {
    // Only pause for actual typing keys, not navigation
    if (e.key.length === 1 || e.key === 'Backspace' || e.key === 'Delete') {
      if (isEditing() || isModalOpen()) {
        pauseRefresh();
      }
    }
  }, true);

  // Start auto-refresh on page load
  if (mainContent) {
    // Initialize hash
    lastDataHash = hashContent(mainContent.innerHTML);
    startAutoRefresh();
  }

  // ============================================
  // Keyboard Shortcuts
  // ============================================
  document.addEventListener('keydown', (e) => {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return;
    }

    switch (e.key.toLowerCase()) {
      case 'r':
        // Manual refresh
        e.preventDefault();
        countdown = 0;
        refreshContent();
        break;

      case 't':
        // Toggle theme
        e.preventDefault();
        toggleTheme();
        break;

      case 'b':
        // Go to bugs
        e.preventDefault();
        window.location.href = '/ui/bugs/';
        break;

      case 'd':
        // Go to dashboard
        e.preventDefault();
        window.location.href = '/ui/';
        break;

      case 'p':
        // Toggle pause
        e.preventDefault();
        if (isPaused) {
          resumeRefresh();
        } else {
          pauseRefresh();
        }
        break;

      case '?':
        // Show help
        e.preventDefault();
        showHelp();
        break;
    }
  });

  function showHelp() {
    const existing = document.getElementById('keyboard-help');
    if (existing) {
      existing.remove();
      return;
    }

    const help = document.createElement('div');
    help.id = 'keyboard-help';
    help.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 24px;
      z-index: 1000;
      box-shadow: 0 10px 40px rgba(0,0,0,0.2);
      min-width: 300px;
    `;
    help.innerHTML = `
      <h3 style="margin-bottom: 16px; font-size: 1.1rem;">Keyboard Shortcuts</h3>
      <table style="width: 100%;">
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">r</kbd></td><td>Refresh now</td></tr>
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">p</kbd></td><td>Pause/resume auto-refresh</td></tr>
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">t</kbd></td><td>Toggle theme</td></tr>
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">d</kbd></td><td>Dashboard</td></tr>
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">b</kbd></td><td>Bug reports</td></tr>
        <tr><td style="padding: 4px 0;"><kbd style="background: var(--bg-secondary); padding: 2px 8px; border-radius: 4px;">?</kbd></td><td>Toggle help</td></tr>
      </table>
      <p style="margin-top: 16px; font-size: 0.85rem; color: var(--text-muted);">Press any key to close</p>
    `;
    document.body.appendChild(help);

    // Close on any key or click
    const close = () => {
      help.remove();
      document.removeEventListener('keydown', close);
      document.removeEventListener('click', close);
    };
    setTimeout(() => {
      document.addEventListener('keydown', close, { once: true });
      document.addEventListener('click', close, { once: true });
    }, 100);
  }

  // ============================================
  // Status Update (for bug detail page)
  // ============================================
  window.updateBugStatus = function (bugId, status) {
    fetch(`/api/bugs/${bugId}/status`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ status: status })
    })
      .then(r => r.json())
      .then(data => {
        if (data.bug) {
          // Refresh page to show updated status
          countdown = 0;
          refreshContent();
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(err => {
        alert('Error: ' + err.message);
      });
  };

  // ============================================
  // Kill Actions (Soft Delete)
  // ============================================
  window.killBug = function (bugId) {
    if (!confirm('Kill this bug? It will be removed from active views but history is preserved.')) {
      return;
    }

    fetch(`/api/bugs/${bugId}/kill`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          // Redirect to bugs list
          window.location.href = '/ui/bugs/';
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(err => {
        alert('Error: ' + err.message);
      });
  };

  window.killRun = function (runId) {
    if (!confirm('Kill this run? It will be removed from active views but history is preserved.')) {
      return;
    }

    fetch(`/api/runs/${runId}/kill`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          // Refresh to update kanban
          countdown = 0;
          refreshContent();
        } else {
          alert('Error: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(err => {
        alert('Error: ' + err.message);
      });
  };

  // ============================================
  // Task Input Form (Start Pipeline)
  // ============================================
  const taskForm = document.getElementById('new-task-form');
  const taskInput = document.getElementById('task-input');
  const projectSelect = document.getElementById('project-select');

  if (taskForm) {
    taskForm.addEventListener('submit', function (e) {
      e.preventDefault();

      const task = taskInput.value.trim();
      const projectId = projectSelect.value;

      if (!task) {
        alert('Please enter a task or feature request');
        return;
      }

      if (!projectId) {
        alert('Please select a project');
        return;
      }

      // Disable form while submitting
      const submitBtn = taskForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle></svg> Starting...';

      // Create a new run via API
      fetch(`/api/projects/${projectId}/runs/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: task,
          feature_request: task
        })
      })
        .then(r => r.json())
        .then(data => {
          if (data.run) {
            // Clear form
            taskInput.value = '';
            // Refresh to show new run in kanban
            countdown = 0;
            refreshContent();
          } else {
            alert('Error: ' + (data.error || 'Failed to start pipeline'));
          }
        })
        .catch(err => {
          alert('Error: ' + err.message);
        })
        .finally(() => {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Start Pipeline';
        });
    });
  }

  // ============================================
  // Global Confirmation Modal
  // ============================================
  let confirmCallback = null;

  function showConfirmModal(title, message, callback, btnText = 'Confirm', btnClass = 'btn-danger') {
    const modal = document.getElementById('global-confirm-modal');
    if (!modal) {
      if (confirm(message)) callback();
      return;
    }

    document.getElementById('global-confirm-title').textContent = title;
    document.getElementById('global-confirm-message').textContent = message;

    const confirmBtn = document.getElementById('global-confirm-btn');
    confirmBtn.textContent = btnText;
    confirmBtn.className = 'btn ' + btnClass;

    // Clean listener
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.onclick = function () {
      if (callback) callback();
      closeConfirmModal();
    };

    modal.classList.add('active');
  }

  function closeConfirmModal() {
    confirmCallback = null;
    const modal = document.getElementById('global-confirm-modal');
    if (modal) modal.classList.remove('active');
  }

  window.showConfirmModal = showConfirmModal;
  window.closeConfirmModal = closeConfirmModal;

  // ============================================
  // Smooth transitions
  // ============================================
  if (mainContent) {
    mainContent.style.transition = 'opacity 0.15s ease';
  }

  console.log('Workflow Hub initialized. Press ? for keyboard shortcuts.');
})();
