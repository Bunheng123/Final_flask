"""
Scheduled background jobs package (Flask-APScheduler).
"""
import os
import logging
from flask_apscheduler import APScheduler
from jobs.grace_period import auto_confirm_pending_orders_job

logger = logging.getLogger(__name__)

scheduler = APScheduler()

def init_scheduler(app):
    """
    Initializes and starts APScheduler:
    - Starts only if SCHEDULER_ENABLED is true.
    - Never starts during tests (TESTING is True).
    - Prevents duplicate execution under the Werkzeug debug reloader.
    - Runs the grace period stub every 5 minutes with max_instances=1.
    """
    if not app.config.get('SCHEDULER_ENABLED', False):
        logger.info("[Scheduler] SCHEDULER_ENABLED is False; skipping scheduler initialization.")
        return None

    if app.config.get('TESTING', False):
        logger.info("[Scheduler] App is in TESTING mode; skipping scheduler initialization.")
        return None

    # Avoid starting twice in Werkzeug debug reloader
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        logger.info("[Scheduler] Main reloader process detected; deferring scheduler to child worker.")
        return None

    scheduler.init_app(app)

    @scheduler.task('interval', id='grace_period_auto_confirm', minutes=5, max_instances=1)
    def scheduled_grace_period():
        with app.app_context():
            try:
                auto_confirm_pending_orders_job()
            except NotImplementedError:
                pass
            except Exception as e:
                logger.error(f"[Scheduler] Grace period job encountered an error: {e}")

    scheduler.start()
    logger.info("[Scheduler] Background scheduler started successfully with grace_period_auto_confirm job.")
    return scheduler
