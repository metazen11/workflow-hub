/**
 * Workflow Hub - React Components
 * Shared UI components using React for state management
 * Uses React.createElement with a cleaner wrapper syntax
 */

(function() {
  'use strict';

  const { createElement, useState, useEffect, useCallback, useRef, Fragment } = React;
  const { createRoot, createPortal } = ReactDOM;

  // JSX-like helper: el('div', {className: 'foo'}, 'text', el('span', null, 'child'))
  // Shorthand: el.div({className: 'foo'}, 'text')
  function el(type, props, ...children) {
    return createElement(type, props, ...children);
  }

  // Convenience shortcuts for common elements
  const tags = ['div', 'span', 'p', 'h3', 'button', 'input', 'textarea', 'select', 'option', 'label', 'svg', 'path', 'polygon', 'polyline', 'circle', 'line'];
  tags.forEach(tag => {
    el[tag] = (props, ...children) => createElement(tag, props, ...children);
  });

  // Alias for readability
  const h = el;

  // ============================================
  // ConfirmDialog Component
  // A modal dialog that pauses auto-refresh while open
  // ============================================
  function ConfirmDialog({
    isOpen,
    title = 'Confirm',
    message,
    confirmText = 'Confirm',
    confirmClass = 'btn-danger',
    onConfirm,
    onCancel
  }) {
    useEffect(() => {
      if (isOpen) {
        // Pause auto-refresh while dialog is open
        if (window.pauseAutoRefresh) window.pauseAutoRefresh();

        // Handle escape key
        const handleEscape = (e) => {
          if (e.key === 'Escape') onCancel();
        };
        document.addEventListener('keydown', handleEscape);
        return () => {
          document.removeEventListener('keydown', handleEscape);
        };
      } else {
        // Resume auto-refresh when dialog closes
        if (window.resumeAutoRefresh) {
          setTimeout(() => window.resumeAutoRefresh(), 500);
        }
      }
    }, [isOpen, onCancel]);

    if (!isOpen) return null;

    // Use portal to render at document body level
    return createPortal(
      h('div', {
        className: 'modal active',
        onClick: (e) => e.target.className === 'modal active' && onCancel()
      },
        h('div', { className: 'modal-content', style: { maxWidth: '400px', padding: 0 } },
          h('div', { className: 'modal-header' },
            h('h3', null, title),
            h('button', { className: 'modal-close', onClick: onCancel }, '\u00D7')
          ),
          h('div', { className: 'modal-body' },
            h('p', { style: { color: 'var(--text-primary)', margin: 0 } }, message)
          ),
          h('div', { className: 'modal-footer' },
            h('button', { className: 'btn btn-secondary', onClick: onCancel }, 'Cancel'),
            h('button', { className: 'btn ' + confirmClass, onClick: onConfirm }, confirmText)
          )
        )
      ),
      document.body
    );
  }

  // ============================================
  // ActionButton Component
  // Button with loading state and confirmation
  // ============================================
  function ActionButton({
    children,
    onClick,
    className = 'btn btn-primary',
    disabled = false,
    confirmMessage = null,
    confirmTitle = 'Confirm',
    loadingText = 'Loading...',
    icon = null
  }) {
    const [isLoading, setIsLoading] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);

    const handleClick = useCallback(async () => {
      if (confirmMessage) {
        setShowConfirm(true);
        return;
      }
      await executeAction();
    }, [confirmMessage, onClick]);

    const executeAction = useCallback(async () => {
      setShowConfirm(false);
      setIsLoading(true);
      try {
        await onClick();
      } catch (err) {
        console.error('Action failed:', err);
        alert('Error: ' + (err.message || 'Action failed'));
      } finally {
        setIsLoading(false);
      }
    }, [onClick]);

    const handleCancel = useCallback(() => {
      setShowConfirm(false);
    }, []);

    return h('div', { style: { display: 'inline-block' } },
      h('button', {
        className: className + (isLoading ? ' btn-loading' : ''),
        disabled: disabled || isLoading,
        onClick: handleClick
      },
        isLoading
          ? h('span', null,
              h('span', { className: 'spinner-sm', style: { marginRight: '6px' } }),
              loadingText
            )
          : h('span', null, icon, children)
      ),
      h(ConfirmDialog, {
        isOpen: showConfirm,
        title: confirmTitle,
        message: confirmMessage,
        onConfirm: executeAction,
        onCancel: handleCancel
      })
    );
  }

  // ============================================
  // RunAgentButton Component
  // Specialized button for triggering agent runs with polling
  // ============================================
  function RunAgentButton({ taskId, currentStage, onComplete, existingRunId }) {
    const [status, setStatus] = useState('idle'); // idle, confirming, starting, running, complete, error
    const [runId, setRunId] = useState(null);
    const [stateLabel, setStateLabel] = useState('');
    const pollInterval = useRef(null);

    // Check for existing run on mount (from prop or sessionStorage)
    useEffect(() => {
      // Priority: existingRunId prop > sessionStorage
      const storedRunId = sessionStorage.getItem('runningAgentFor_' + taskId);
      const activeRunId = existingRunId || (storedRunId && storedRunId !== 'null' ? parseInt(storedRunId) : null);

      if (activeRunId) {
        setRunId(activeRunId);
        setStatus('running');
        setStateLabel('Checking...');
        // Store it in sessionStorage for consistency
        sessionStorage.setItem('runningAgentFor_' + taskId, activeRunId);
      }
    }, [taskId, existingRunId]);

    // Polling effect
    useEffect(() => {
      if (status === 'running' && runId) {
        // Pause auto-refresh during agent execution
        if (window.pauseAutoRefresh) window.pauseAutoRefresh();

        pollInterval.current = setInterval(() => pollRunStatus(), 3000);
        pollRunStatus(); // Immediate poll

        return () => {
          if (pollInterval.current) clearInterval(pollInterval.current);
        };
      }
    }, [status, runId]);

    const pollRunStatus = useCallback(() => {
      if (!runId) return;

      fetch('/api/runs/' + runId)
        .then(r => r.json())
        .then(data => {
          if (!data.run) {
            console.error('Run not found');
            resetButton();
            return;
          }

          const state = data.run.state;
          setStateLabel(state.toUpperCase());

          const finalStates = ['deployed', 'merged', 'ready_for_deploy', 'ready_for_commit', 'killed'];
          const failedStates = ['qa_failed', 'sec_failed', 'testing_failed'];

          if (finalStates.includes(state)) {
            if (pollInterval.current) clearInterval(pollInterval.current);
            setStatus('complete');
            setTimeout(() => {
              resetButton();
              alert('Agent completed! Final state: ' + state.toUpperCase());
              if (onComplete) onComplete(state);
            }, 1000);
          } else if (failedStates.includes(state)) {
            if (pollInterval.current) clearInterval(pollInterval.current);
            setStatus('error');
            setTimeout(() => {
              resetButton();
              alert('Agent stopped at: ' + state.toUpperCase() + '. Check reports for details.');
              if (onComplete) onComplete(state);
            }, 1000);
          } else if (data.run.killed) {
            if (pollInterval.current) clearInterval(pollInterval.current);
            resetButton();
            alert('Agent run was killed.');
          }
        })
        .catch(err => console.error('Error polling:', err));
    }, [runId, onComplete]);

    const resetButton = useCallback(() => {
      setStatus('idle');
      setRunId(null);
      setStateLabel('');
      sessionStorage.removeItem('runningAgentFor_' + taskId);
      if (pollInterval.current) clearInterval(pollInterval.current);
      if (window.resumeAutoRefresh) {
        setTimeout(() => window.resumeAutoRefresh(), 1000);
      }
    }, [taskId]);

    const handleConfirm = useCallback(() => {
      setStatus('confirming');
    }, []);

    const handleCancel = useCallback(() => {
      setStatus('idle');
    }, []);

    const executeAgent = useCallback(async () => {
      setStatus('starting');
      setStateLabel('Starting...');

      try {
        const response = await fetch('/api/tasks/' + taskId + '/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.run_id) {
          setRunId(data.run_id);
          sessionStorage.setItem('runningAgentFor_' + taskId, data.run_id);
          setStatus('running');
          setStateLabel('Running...');
        } else {
          throw new Error(data.error || 'Failed to start agent');
        }
      } catch (err) {
        setStatus('error');
        alert('Error: ' + err.message);
        setTimeout(resetButton, 2000);
      }
    }, [taskId, resetButton]);

    const isDisabled = status !== 'idle';

    const buttonText = {
      'idle': 'Run Agent',
      'confirming': 'Run Agent',
      'starting': 'Starting...',
      'running': 'Agent: ' + stateLabel,
      'complete': 'Done: ' + stateLabel,
      'error': 'Failed: ' + stateLabel
    }[status] || 'Run Agent';

    const buttonClass = 'btn btn-primary' +
      (status === 'running' ? ' btn-running' : '') +
      (status === 'complete' ? ' btn-success' : '') +
      (status === 'error' ? ' btn-danger' : '');

    return h('div', { style: { display: 'inline-block' } },
      h('button', {
        className: buttonClass,
        disabled: isDisabled,
        onClick: handleConfirm,
        id: 'run-agent-btn-react'
      },
        h('svg', {
          width: 14, height: 14, viewBox: '0 0 24 24',
          fill: 'none', stroke: 'currentColor', strokeWidth: 2,
          style: { marginRight: '6px' }
        },
          h('polygon', { points: '5 3 19 12 5 21 5 3' })
        ),
        h('span', { className: 'btn-text' }, buttonText)
      ),
      h(ConfirmDialog, {
        isOpen: status === 'confirming',
        title: 'Run Agent',
        message: 'Are you sure you want to trigger the agent for the current stage (' + (currentStage || 'DEV').toUpperCase() + ')?',
        confirmText: 'Run Agent',
        confirmClass: 'btn-primary',
        onConfirm: executeAgent,
        onCancel: handleCancel
      })
    );
  }

  // ============================================
  // DeployButton Component
  // Button for deployment with environment selection
  // ============================================
  function DeployButton({ runId, environmentId = null, onComplete }) {
    const [status, setStatus] = useState('idle');
    const [showDialog, setShowDialog] = useState(false);
    const [envId, setEnvId] = useState(environmentId || '');
    const [approver, setApprover] = useState('');

    const handleClick = useCallback(() => {
      if (window.pauseAutoRefresh) window.pauseAutoRefresh();
      setShowDialog(true);
    }, []);

    const handleCancel = useCallback(() => {
      setShowDialog(false);
      if (window.resumeAutoRefresh) setTimeout(() => window.resumeAutoRefresh(), 500);
    }, []);

    const handleDeploy = useCallback(async () => {
      if (!envId) {
        alert('Please enter an Environment ID');
        return;
      }

      setShowDialog(false);
      setStatus('deploying');

      try {
        const response = await fetch('/api/runs/' + runId + '/deploy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            environment_id: parseInt(envId),
            approved_by: approver || 'human'
          })
        });
        const data = await response.json();

        if (data.error) {
          throw new Error(data.error);
        }

        setStatus('complete');
        alert('Deployment started! It will run health checks and tests automatically.');
        if (onComplete) onComplete();
        else window.location.reload();
      } catch (err) {
        setStatus('error');
        alert('Error: ' + err.message);
        setTimeout(() => setStatus('idle'), 2000);
      }
    }, [runId, envId, approver, onComplete]);

    const buttonText = {
      'idle': 'Start Deployment',
      'deploying': 'Deploying...',
      'complete': 'Deployed',
      'error': 'Failed'
    }[status];

    // Custom dialog for deployment (needs inputs)
    const dialog = showDialog ? createPortal(
      h('div', {
        className: 'modal active',
        onClick: (e) => e.target.className === 'modal active' && handleCancel()
      },
        h('div', { className: 'modal-content', style: { maxWidth: '400px', padding: 0 } },
          h('div', { className: 'modal-header' },
            h('h3', null, 'Start Deployment'),
            h('button', { className: 'modal-close', onClick: handleCancel }, '\u00D7')
          ),
          h('div', { className: 'modal-body' },
            h('div', { className: 'form-group', style: { marginBottom: '16px' } },
              h('label', { style: { display: 'block', marginBottom: '4px' } }, 'Environment ID:'),
              h('input', {
                type: 'number',
                className: 'form-input',
                value: envId,
                onChange: (e) => setEnvId(e.target.value),
                placeholder: 'Enter environment ID',
                style: { width: '100%' }
              })
            ),
            h('div', { className: 'form-group' },
              h('label', { style: { display: 'block', marginBottom: '4px' } }, 'Your name (for audit):'),
              h('input', {
                type: 'text',
                className: 'form-input',
                value: approver,
                onChange: (e) => setApprover(e.target.value),
                placeholder: 'Optional',
                style: { width: '100%' }
              })
            )
          ),
          h('div', { className: 'modal-footer' },
            h('button', { className: 'btn btn-secondary', onClick: handleCancel }, 'Cancel'),
            h('button', { className: 'btn btn-primary', onClick: handleDeploy }, 'Deploy')
          )
        )
      ),
      document.body
    ) : null;

    return h('div', { style: { display: 'inline-block' } },
      h('button', {
        className: 'btn btn-primary' + (status === 'deploying' ? ' btn-loading' : ''),
        disabled: status !== 'idle',
        onClick: handleClick
      },
        h('svg', {
          width: 14, height: 14, viewBox: '0 0 24 24',
          fill: 'none', stroke: 'currentColor', strokeWidth: 2,
          style: { marginRight: '6px' }
        },
          h('path', { d: 'M22 12h-4l-3 9L9 3l-3 9H2' })
        ),
        buttonText
      ),
      dialog
    );
  }

  // ============================================
  // RollbackButton Component
  // ============================================
  function RollbackButton({ runId, onComplete }) {
    const [status, setStatus] = useState('idle');
    const [showDialog, setShowDialog] = useState(false);
    const [reason, setReason] = useState('Manual rollback requested');

    const handleClick = useCallback(() => {
      if (window.pauseAutoRefresh) window.pauseAutoRefresh();
      setShowDialog(true);
    }, []);

    const handleCancel = useCallback(() => {
      setShowDialog(false);
      if (window.resumeAutoRefresh) setTimeout(() => window.resumeAutoRefresh(), 500);
    }, []);

    const handleRollback = useCallback(async () => {
      setShowDialog(false);
      setStatus('rolling_back');

      try {
        const response = await fetch('/api/runs/' + runId + '/rollback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason })
        });
        const data = await response.json();

        if (data.error) {
          throw new Error(data.error);
        }

        setStatus('complete');
        alert('Rollback started! The system will revert to the previous deployment.');
        if (onComplete) onComplete();
        else window.location.reload();
      } catch (err) {
        setStatus('error');
        alert('Error: ' + err.message);
        setTimeout(() => setStatus('idle'), 2000);
      }
    }, [runId, reason, onComplete]);

    const buttonText = {
      'idle': 'Rollback',
      'rolling_back': 'Rolling back...',
      'complete': 'Rolled back',
      'error': 'Failed'
    }[status];

    const dialog = showDialog ? createPortal(
      h('div', {
        className: 'modal active',
        onClick: (e) => e.target.className === 'modal active' && handleCancel()
      },
        h('div', { className: 'modal-content', style: { maxWidth: '400px', padding: 0 } },
          h('div', { className: 'modal-header' },
            h('h3', null, 'Rollback Deployment'),
            h('button', { className: 'modal-close', onClick: handleCancel }, '\u00D7')
          ),
          h('div', { className: 'modal-body' },
            h('p', { style: { marginBottom: '16px', color: 'var(--warning)' } },
              'This will revert to the previous deployment.'),
            h('div', { className: 'form-group' },
              h('label', { style: { display: 'block', marginBottom: '4px' } }, 'Reason for rollback:'),
              h('textarea', {
                className: 'form-textarea',
                value: reason,
                onChange: (e) => setReason(e.target.value),
                rows: 3,
                style: { width: '100%' }
              })
            )
          ),
          h('div', { className: 'modal-footer' },
            h('button', { className: 'btn btn-secondary', onClick: handleCancel }, 'Cancel'),
            h('button', { className: 'btn btn-warning', onClick: handleRollback }, 'Rollback')
          )
        )
      ),
      document.body
    ) : null;

    return h('div', { style: { display: 'inline-block' } },
      h('button', {
        className: 'btn btn-warning' + (status === 'rolling_back' ? ' btn-loading' : ''),
        disabled: status !== 'idle',
        onClick: handleClick
      },
        h('svg', {
          width: 14, height: 14, viewBox: '0 0 24 24',
          fill: 'none', stroke: 'currentColor', strokeWidth: 2,
          style: { marginRight: '6px' }
        },
          h('polyline', { points: '1 4 1 10 7 10' }),
          h('path', { d: 'M3.51 15a9 9 0 1 0 2.13-9.36L1 10' })
        ),
        buttonText
      ),
      dialog
    );
  }

  // ============================================
  // Mount Helpers
  // ============================================
  function mountComponent(Component, props, container) {
    if (!container) {
      console.warn('Container not found for React component');
      return null;
    }
    const root = createRoot(container);
    root.render(h(Component, props));
    return root;
  }

  function mountRunAgentButton(taskId, currentStage, containerId, existingRunId) {
    const container = document.getElementById(containerId);
    if (container) {
      return mountComponent(RunAgentButton, { taskId, currentStage, existingRunId }, container);
    }
  }

  function mountDeployButton(runId, containerId) {
    const container = document.getElementById(containerId);
    if (container) {
      return mountComponent(DeployButton, { runId }, container);
    }
  }

  function mountRollbackButton(runId, containerId) {
    const container = document.getElementById(containerId);
    if (container) {
      return mountComponent(RollbackButton, { runId }, container);
    }
  }

  // ============================================
  // Export to window
  // ============================================
  window.WH = window.WH || {};
  window.WH.React = {
    ConfirmDialog,
    ActionButton,
    RunAgentButton,
    DeployButton,
    RollbackButton,
    mountComponent,
    mountRunAgentButton,
    mountDeployButton,
    mountRollbackButton
  };

  console.log('React components loaded. Access via window.WH.React');
})();
