"""Django app configuration for Workflow Hub."""
import os
import logging
from django.apps import AppConfig as DjangoAppConfig

logger = logging.getLogger(__name__)


class WorkflowHubConfig(DjangoAppConfig):
    """Workflow Hub app configuration."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        """Called when Django starts up."""
        # Only start workers in the main process, not in autoreload subprocess
        # Check RUN_MAIN to avoid double-starting in development
        if os.environ.get('RUN_MAIN') == 'true':
            self._start_job_workers()

    def _start_job_workers(self):
        """Start background job workers if enabled."""
        # Check if queue is enabled
        queue_enabled = os.getenv('JOB_QUEUE_ENABLED', 'true').lower() == 'true'

        if not queue_enabled:
            logger.info("Job queue workers disabled (JOB_QUEUE_ENABLED=false)")
            return

        try:
            from app.services.job_worker import start_workers
            start_workers()
            logger.info("Job queue workers started")
        except Exception as e:
            logger.error(f"Failed to start job workers: {e}")
