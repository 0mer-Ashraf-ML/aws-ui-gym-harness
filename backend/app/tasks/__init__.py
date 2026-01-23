"""Celery tasks package."""

# Import task modules so Celery auto-discovers registered tasks when the package is imported
from . import batch_dispatch  # noqa: F401  # pylint: disable=unused-import
from . import cleanup  # noqa: F401  # pylint: disable=unused-import
from . import iteration_execution  # noqa: F401  # pylint: disable=unused-import
from . import monitoring  # noqa: F401  # pylint: disable=unused-import
from . import unified_execution  # noqa: F401  # pylint: disable=unused-import
