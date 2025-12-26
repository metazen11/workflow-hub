/**
 * Workflow Hub - Dashboard JavaScript
 * Handles auto-refresh, theme toggle, and keyboard shortcuts
 */

(function() {
  'use strict';

  // Configuration
  const REFRESH_INTERVAL = 5000; // 5 seconds
  let refreshTimer = null;
  let countdown = 5;

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
  // Auto-Refresh
  // ============================================
  const countdownEl = document.querySelector('.refresh-countdown');
  const mainContent = document.getElementById('main-content');

  function updateCountdown() {
    if (countdownEl) {
      countdownEl.textContent = countdown;
    }
  }

  function refreshContent() {
    fetch(window.location.href, {
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    .then(response => response.text())
    .then(html => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const newContent = doc.getElementById('main-content');

      if (newContent && mainContent) {
        // Smooth transition
        mainContent.style.opacity = '0.5';
        setTimeout(() => {
          mainContent.innerHTML = newContent.innerHTML;
          mainContent.style.opacity = '1';
        }, 100);
      }

      // Reset countdown
      countdown = 5;
      updateCountdown();
    })
    .catch(err => {
      console.warn('Refresh failed:', err);
      countdown = 5;
      updateCountdown();
    });
  }

  function startAutoRefresh() {
    // Countdown timer
    setInterval(() => {
      countdown--;
      updateCountdown();

      if (countdown <= 0) {
        refreshContent();
      }
    }, 1000);
  }

  // Start auto-refresh on page load
  if (mainContent) {
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

    switch(e.key.toLowerCase()) {
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
  window.updateBugStatus = function(bugId, status) {
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
  window.killBug = function(bugId) {
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

  window.killRun = function(runId) {
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
    taskForm.addEventListener('submit', function(e) {
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
  // Smooth transitions
  // ============================================
  if (mainContent) {
    mainContent.style.transition = 'opacity 0.15s ease';
  }

  console.log('Workflow Hub initialized. Press ? for keyboard shortcuts.');
})();
