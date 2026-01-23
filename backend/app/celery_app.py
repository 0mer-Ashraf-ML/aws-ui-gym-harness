"""
Celery application configuration
"""

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

# CRITICAL: Apply nest_asyncio for Playwright compatibility in Celery workers
# This must happen BEFORE any event loops are created in workers
# Playwright sync API requires this to work inside Celery workers
# Note: We only apply in worker context, not in FastAPI (which uses uvloop)
import nest_asyncio

# Try to apply at module level, but ignore if uvloop is already running (FastAPI)
try:
    nest_asyncio.apply()
except ValueError as e:
    # FastAPI uses uvloop which nest_asyncio can't patch - this is OK
    # We'll apply in worker_process_init for Celery workers instead
    pass


@worker_process_init.connect
def init_worker_process(**kwargs):
    """
    Called when a worker process starts.
    Apply nest_asyncio patch to allow Playwright sync API to work
    even if an asyncio event loop is running.
    This is critical for Celery workers.
    """
    import nest_asyncio
    try:
        nest_asyncio.apply()
    except ValueError:
        # Ignore if event loop type doesn't support patching
        pass

# Create Celery instance
celery_app = Celery(
    "harness_main_aws",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.unified_execution",
        "app.tasks.monitoring",
        "app.tasks.cleanup",
        "app.tasks.iteration_execution",
        "app.tasks.batch_dispatch",
    ]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=7200,  # 120 minutes (2 hours)
    task_time_limit=7200,  # 120 minutes (2 hours)
    worker_prefetch_multiplier=1,  # Only prefetch 1 task at a time
    worker_max_tasks_per_child=1000,
    result_expires=24 * 3600,  # 24 hours
    # Support configurable concurrent tasks
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,  # Configurable concurrent worker processes
    task_routes={
        "app.tasks.iteration_execution.*": {"queue": "celery"},
        "app.tasks.unified_execution.*": {"queue": "celery"},
        "app.tasks.monitoring.*": {"queue": "monitoring"},
        "app.tasks.cleanup.*": {"queue": "cleanup"},
        "app.tasks.batch_dispatch.*": {"queue": "batch_dispatch"},
    },
    task_annotations={
        "*": {"rate_limit": "10/s"},
        "app.tasks.iteration_execution.execute_single_iteration": {"rate_limit": f"{settings.CELERY_WORKER_CONCURRENCY}/s"},  # Allow configurable concurrent executions
        "app.tasks.unified_execution.execute_single_iteration_unified": {"rate_limit": f"{settings.CELERY_WORKER_CONCURRENCY}/s"},  # Allow configurable concurrent unified executions
    },
    # Ensure tasks are processed in order
    task_default_queue="celery",
    task_default_exchange="celery",
    task_default_routing_key="celery",
    # Additional settings for single task execution
    task_acks_late=True,  # Acknowledge tasks only after completion
    worker_disable_rate_limits=False,  # Keep rate limits enabled
    task_reject_on_worker_lost=True,  # Don't reject tasks if worker is lost
    # Ensure tasks are processed in order
    task_default_priority=10,  # Default priority for tasks
    # Additional safety settings
    task_always_eager=False,  # Don't execute tasks synchronously
    task_eager_propagates=True,  # Propagate exceptions in eager mode
    # Ensure tasks run only once - no retries
    task_default_retry_delay=0,  # No retry delay
    task_default_max_retries=0,  # No retries allowed
    task_autoretry_for=(),  # No automatic retries for any exceptions
    
    # Beat schedule for continuous monitoring and batch recovery
    beat_schedule={
        'dispatch-pending-tasks': {
            'task': 'app.tasks.monitoring.dispatch_pending_tasks',
            'schedule': 30.0,  # Every 30 seconds - keep pending iterations flowing
            'options': {'queue': 'monitoring'},
        },
        'check-stale-executing-tasks': {
            'task': 'app.tasks.monitoring.check_stale_executing_tasks',
            'schedule': 60.0,  # Every 60 seconds - reconcile stale executing tasks
            'options': {'queue': 'monitoring'},
        },
        'handle-cleanup-fallbacks': {
            'task': 'app.tasks.monitoring.handle_cleanup_fallbacks',
            'schedule': 120.0,  # Every 2 minutes - cleanup fallback data
            'options': {'queue': 'cleanup'},
        },
        'auto-recover-batches': {
            'task': 'app.tasks.monitoring.auto_recover_batches',
            # Default: 600s (10 min); override via AUTO_RECOVER_INTERVAL_SECONDS for quicker checks
            'schedule': float(settings.AUTO_RECOVER_INTERVAL_SECONDS),
            'kwargs': {'days_back': 2},  # Check batches from last 2 days
            'options': {'queue': 'monitoring'},
        },
        'cleanup-leaked-browsers': {
            'task': 'app.tasks.monitoring.cleanup_leaked_browsers',
            'schedule': 300.0,  # Every 5 minutes - kill leaked browser processes
            'options': {'queue': 'cleanup'},
        },
        'cleanup-dangling-firefox': {
            'task': 'app.tasks.monitoring.cleanup_dangling_firefox',
            'schedule': 60.0,  # Every 60 seconds - kill dangling Firefox processes from crashed tasks
            'options': {'queue': 'cleanup'},
        },
    },
)

# Optional configuration for production
if not settings.DEBUG:
    celery_app.conf.update(
        worker_hijack_root_logger=False,
        worker_log_color=False,
    )
