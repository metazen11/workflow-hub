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
        # Startup logic for background workers:
        # - In development: RUN_MAIN='true' indicates the main reloader process
        # - In production (gunicorn): Single worker means no coordination needed

        run_main = os.environ.get('RUN_MAIN')

        if run_main == 'true':
            # Django development server main process
            self._start_job_workers()
            self._start_director_if_enabled()
        elif run_main is None:
            # Production mode (gunicorn with single worker)
            self._start_job_workers()
            self._start_director_if_enabled()

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

    def _start_director_if_enabled(self):
        """Start Director daemon if enabled in database settings."""
        try:
            from app.db import SessionLocal
            from app.models.director_settings import DirectorSettings

            db = SessionLocal()
            try:
                settings = DirectorSettings.get_settings(db)
                if not settings.enabled:
                    logger.info("Director auto-start disabled (enabled=false in database)")
                    return

                # Start Director daemon
                import threading
                from app.services.director_service import run_director_daemon
                from app.db import get_db

                # Import the global flag from api.py
                import app.views.api as api_views

                def daemon_wrapper():
                    api_views._director_daemon_running = True
                    try:
                        run_director_daemon(get_db, poll_interval=settings.poll_interval)
                    finally:
                        api_views._director_daemon_running = False

                thread = threading.Thread(target=daemon_wrapper, daemon=True)
                thread.start()
                api_views._director_daemon_thread = thread

                logger.info(f"Director daemon auto-started (poll_interval={settings.poll_interval}s)")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to auto-start Director: {e}")
