"""Celery task for dispatching batch iterations"""

import logging
import time
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, text, update

from app.celery_app import celery_app
from app.core.config import settings
from app.core.database_utils import get_db_session
from app.models.execution import Execution
from app.models.iteration import Iteration
from app.schemas.iteration import IterationStatus
from app.tasks.unified_execution import execute_single_iteration_unified


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.batch_dispatch.dispatch_batch_iterations")
def dispatch_batch_iterations(
    self,
    batch_id: str,
    iteration_ids: Optional[List[str]] = None,
    max_wait_time: Optional[int] = None,
    dispatch_delay: float = 0.5,
) -> dict:
    """Dispatch iterations for a batch using Celery.

    Args:
        batch_id: UUID of the batch as string.
        iteration_ids: Optional list of iteration UUIDs (as strings) to dispatch.
            When not provided, all pending iterations for the batch will be dispatched.
        max_wait_time: Optional override for iteration max wait time.
        dispatch_delay: Delay between dispatching iterations to avoid queue bursts.

    Returns:
        A summary dictionary with counts of dispatched iterations.
    """

    logger.info(
        "🚀 Starting batch dispatch task for batch_id=%s with %s explicit iteration(s)",
        batch_id,
        len(iteration_ids) if iteration_ids else "all pending",
    )

    try:
        batch_uuid = UUID(batch_id)
    except (TypeError, ValueError):
        logger.error("❌ Invalid batch_id supplied to dispatch task: %s", batch_id)
        return {"status": "error", "reason": "invalid_batch_id", "dispatched": 0}

    # Use centralized database utility with proper pooling
    try:
        with get_db_session() as session:
            # Check if batch exists
            batch_check = session.execute(
                text("SELECT uuid FROM batches WHERE uuid = :batch_id"),
                {"batch_id": str(batch_uuid)}
            ).fetchone()
            
            if not batch_check:
                logger.warning("⚠️ Batch %s not found. Skipping dispatch.", batch_uuid)
                return {"status": "not_found", "dispatched": 0}

            iteration_uuid_filters: Optional[List[UUID]] = None
            if iteration_ids:
                iteration_uuid_filters = []
                for raw_id in iteration_ids:
                    try:
                        iteration_uuid_filters.append(UUID(raw_id))
                    except (TypeError, ValueError):
                        logger.warning(
                            "⚠️ Skipping invalid iteration_id '%s' in dispatch request", raw_id
                        )

                if not iteration_uuid_filters:
                    logger.warning("⚠️ No valid iteration IDs provided for dispatch")
                    return {"status": "no_iterations", "dispatched": 0}

            # Build base query to fetch iteration metadata required for dispatch
            query = (
                select(
                    Iteration.uuid,
                    Iteration.iteration_number,
                    Execution.task_identifier,
                    Execution.prompt,
                    Execution.gym_id,
                    Execution.model,
                )
                .join(Execution, Iteration.execution_id == Execution.uuid)
                .where(Execution.batch_id == batch_uuid)
                .where(Iteration.status == IterationStatus.PENDING.value)  # ALWAYS check status
                .where(Iteration.celery_task_id.is_(None))  # CRITICAL: Prevent double-dispatch
            )

            if iteration_uuid_filters is not None:
                query = query.where(Iteration.uuid.in_(iteration_uuid_filters))

            query = query.order_by(Execution.created_at, Iteration.iteration_number)

            result = session.execute(query)
            rows: Sequence = result.all()

            if not rows:
                if iteration_uuid_filters:
                    logger.warning(
                        "⚠️ No PENDING iterations found for batch %s (requested %s iteration(s) but none are PENDING)",
                        batch_uuid,
                        len(iteration_uuid_filters)
                    )
                else:
                    logger.info("ℹ️ No PENDING iterations found to dispatch for batch %s", batch_uuid)
                return {"status": "success", "dispatched": 0}

            # Check concurrency limits BEFORE dispatching
            executing_query = """
                SELECT COUNT(*) as executing_count
                FROM iterations 
                WHERE status = 'executing'
            """
            executing_result = session.execute(text(executing_query))
            executing_count = executing_result.fetchone().executing_count
            
            # Get configured concurrency limit
            max_concurrency = settings.CELERY_WORKER_CONCURRENCY
            available_slots = max_concurrency - executing_count
            
            logger.info(
                "📊 Concurrency check - Executing: %s, Max: %s, Available: %s, Requested: %s",
                executing_count,
                max_concurrency,
                available_slots,
                len(rows)
            )
            
            if available_slots <= 0:
                logger.warning(
                    "⚠️ No available concurrency slots for batch %s (executing: %s, max: %s)",
                    batch_uuid,
                    executing_count,
                    max_concurrency
                )
                return {
                    "status": "concurrency_limit",
                    "dispatched": 0,
                    "executing_count": executing_count,
                    "max_concurrency": max_concurrency
                }
            
            # Limit dispatching to available slots
            rows_to_dispatch = rows[:available_slots]
            if len(rows_to_dispatch) < len(rows):
                logger.info(
                    "⚠️ Limiting dispatch to %s iterations (out of %s) due to concurrency constraints",
                    len(rows_to_dispatch),
                    len(rows)
                )

            dispatched = 0
            failed = 0
            for row in rows_to_dispatch:
                # Wrap ENTIRE iteration processing in try-catch to ensure one failure doesn't halt others
                try:
                    iteration_uuid = str(row.uuid)
                    task_identifier = row.task_identifier
                    prompt = row.prompt
                    gym_id = str(row.gym_id)
                    runner_type = row.model

                    if not task_identifier:
                        logger.warning(
                            "⚠️ Iteration %s missing task identifier; skipping dispatch",
                            iteration_uuid,
                        )
                        failed += 1
                        continue

                    wait_time = max_wait_time if max_wait_time is not None else settings.MAX_WAIT_TIME

                    try:
                        # Dispatch task to Celery
                        result = execute_single_iteration_unified.delay(
                            iteration_id=iteration_uuid,
                            task_id=task_identifier,
                            gym_id=gym_id,
                            runner_type=runner_type,
                            max_wait_time=wait_time,
                            prompt=prompt,
                        )
                        
                        # CRITICAL: Update celery_task_id immediately to prevent double-dispatch
                        # This closes the race window between dispatch and task execution
                        try:
                            update_stmt = (
                                update(Iteration)
                                .where(Iteration.uuid == row.uuid)
                                .values(celery_task_id=result.id)
                            )
                            session.execute(update_stmt)
                            session.commit()
                        except Exception as db_error:  # pylint: disable=broad-except
                            logger.error(
                                "❌ Failed to update celery_task_id for iteration %s: %s",
                                iteration_uuid,
                                db_error,
                            )
                            # Continue anyway - task is already dispatched
                        
                        dispatched += 1
                        logger.info(
                            "✅ Dispatched iteration %s (model=%s, celery_task_id=%s) for batch %s",
                            iteration_uuid,
                            runner_type,
                            result.id,
                            batch_uuid,
                        )
                        
                        # Small delay to avoid queue burst (using sync sleep)
                        if dispatch_delay > 0:
                            time.sleep(dispatch_delay)
                            
                    except Exception as celery_error:  # pylint: disable=broad-except
                        logger.error(
                            "❌ Failed to dispatch iteration %s: %s",
                            iteration_uuid,
                            celery_error,
                        )
                        failed += 1
                        # Continue to next iteration - don't halt entire batch
                        
                except Exception as iteration_error:  # pylint: disable=broad-except
                    # Catch ANY error during iteration processing to prevent halting
                    logger.error(
                        "❌ Critical error processing iteration in batch %s: %s",
                        batch_uuid,
                        iteration_error,
                    )
                    failed += 1
                    # Continue to next iteration

            # Calculate how many were not dispatched due to concurrency
            skipped_due_to_concurrency = len(rows) - len(rows_to_dispatch)
            
            logger.info(
                "✅ Completed dispatch for batch %s. Dispatched: %s, Failed: %s, Skipped (concurrency): %s, Total available: %s",
                batch_uuid,
                dispatched,
                failed,
                skipped_due_to_concurrency,
                len(rows),
            )

            return {
                "status": "success",
                "dispatched": dispatched,
                "failed": failed,
                "skipped_concurrency": skipped_due_to_concurrency,
                "total": len(rows)
            }

    except Exception as error:  # pylint: disable=broad-except
        logger.error("❌ Batch dispatch task failed for batch %s: %s", batch_uuid, error)
        return {"status": "error", "reason": str(error), "dispatched": 0}
