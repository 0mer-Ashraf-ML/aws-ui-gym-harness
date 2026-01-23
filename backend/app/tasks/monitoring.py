"""
Celery tasks for monitoring and maintenance
"""

import json
import logging
from datetime import datetime, timedelta

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.monitoring.health_check")
def health_check():
    """Perform system health check"""
    try:
        logger.info("Performing health check")
        
        from app.services.task_manager import TaskManager
        
        async def check_health():
            task_manager = TaskManager()
            
            # Get system stats
            stats = await task_manager.get_system_stats()
            
            # Check for issues
            alerts = []
            
            if stats.failed_today > stats.completed_today * 0.5:  # More than 50% failure rate
                alerts.append({
                    "type": "high_failure_rate",
                    "message": f"High failure rate today: {stats.failed_today} failures vs {stats.completed_today} successes"
                })
            
            if stats.active_executions > 10:  # Too many active executions
                alerts.append({
                    "type": "high_active_executions",
                    "message": f"High number of active executions: {stats.active_executions}"
                })
            
            health_status = {
                "timestamp": datetime.now().isoformat(),
                "status": "healthy" if not alerts else "warning",
                "alerts": alerts,
                "stats": stats.dict()
            }
            
            logger.info(f"Health check completed: {health_status}")
            return health_status
        
        # Run async health check
        import asyncio
        return asyncio.run(check_health())
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise

@celery_app.task(name="app.tasks.monitoring.dispatch_pending_tasks")
def dispatch_pending_tasks():
    """Automatically dispatch pending tasks from database to Celery queue - ensures each task is enqueued exactly once"""
    try:
        logger.info("🔄 Starting dispatch_pending_tasks")
        
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        from app.tasks.unified_execution import execute_single_iteration_unified
        
        dispatched_count = 0
        
        # Use centralized session manager
        with get_db_session() as db:
            # Get list of active iteration IDs from Celery to exclude from database query
            active_iteration_ids = set()
            try:
                from app.celery_app import celery_app
                active_tasks = celery_app.control.inspect().active()
                if active_tasks:
                    for worker, tasks in active_tasks.items():
                        if tasks:
                            for task in tasks:
                                kwargs = task.get('kwargs', {})
                                task_iteration_id = kwargs.get('iteration_id')
                                if task_iteration_id:
                                    active_iteration_ids.add(task_iteration_id)
                logger.info(f"🔍 Found {len(active_iteration_ids)} active tasks in Celery to exclude from dispatch")
            except Exception as celery_check_error:
                logger.warning(f"⚠️ Failed to check Celery active tasks: {celery_check_error}")
                # Continue without exclusion if we can't check Celery status
            
            # Build query to exclude active Celery tasks - ensures no duplication
            exclude_clause = ""
            if active_iteration_ids:
                # Convert set to comma-separated string for SQL IN clause
                iteration_ids_str = "', '".join(active_iteration_ids)
                exclude_clause = f"AND i.uuid NOT IN ('{iteration_ids_str}')"
            
            # Get current executing count to respect concurrency limits
            executing_query = """
                SELECT COUNT(*) as executing_count
                FROM iterations 
                WHERE status = 'executing'
            """
            executing_result = db.execute(text(executing_query))
            executing_count = executing_result.fetchone().executing_count
            
            # Get configured concurrency limit
            from app.core.config import settings
            max_concurrency = settings.CELERY_WORKER_CONCURRENCY
            available_slots = max_concurrency - executing_count
            
            logger.info(f"Current executing: {executing_count}, Max concurrency: {max_concurrency}, Available slots: {available_slots}")
            
            if available_slots <= 0:
                logger.info("No available slots for new tasks")
                return {
                    "status": "success",
                    "dispatched_count": 0,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Get pending tasks - simple ordering by creation time
            # Includes both batch executions and playground executions
            # Note: task_identifier and prompt now come from execution snapshots (decoupled from tasks table)
            query = f"""
                SELECT 
                    i.uuid as iteration_id,
                    i.execution_id,
                    e.gym_id,
                    e.model,
                    e.execution_folder_name,
                    e.task_identifier as task_id,
                    e.prompt
                FROM iterations i
                JOIN executions e ON i.execution_id = e.uuid
                WHERE i.status = 'pending'
                AND i.celery_task_id IS NULL  -- CRITICAL: Prevent redispatch of queued tasks
                AND (e.batch_id IS NOT NULL OR e.execution_type = 'playground')  -- Include both batch and playground executions
                {exclude_clause}
                ORDER BY i.created_at ASC  -- Simple ordering: oldest first
                LIMIT :available_slots
            """
            
            result = db.execute(text(query), {"available_slots": available_slots})
            pending_iterations = result.fetchall()
            
            logger.info(f"Found {len(pending_iterations)} pending iterations to dispatch (limit: {available_slots})")
            
            for iteration in pending_iterations:
                # Wrap ENTIRE iteration processing in try-catch to ensure one failure doesn't halt others
                try:
                    logger.info(f"🚀 Dispatching iteration {iteration.iteration_id}")
                    logger.info(f"   Task: {iteration.prompt}")
                    logger.info(f"   Gym: {iteration.gym_id}")
                    logger.info(f"   Model: {iteration.model}")
                    
                    # Dispatch the task using unified execution
                    # CRITICAL: Set celery_task_id immediately to prevent double dispatch
                    # The Celery task itself will update status to 'executing' when it starts
                    # This prevents marking as executing if Celery task fails to queue, but prevents double dispatch
                    # Pass prompt from execution snapshot for decoupling
                    # For playground executions, gym_id will be None (handled in unified_execution)
                    try:
                        celery_result = execute_single_iteration_unified.delay(
                            iteration_id=str(iteration.iteration_id),
                            task_id=str(iteration.task_id),
                            gym_id=str(iteration.gym_id) if iteration.gym_id else None,  # None for playground
                            runner_type=iteration.model,
                            max_wait_time=7200,  # 120 minutes (2 hours) timeout
                            prompt=iteration.prompt
                        )
                        
                        # CRITICAL: Update celery_task_id immediately to prevent double dispatch
                        # Use atomic update with WHERE clause to prevent race conditions
                        update_celery_id_query = """
                            UPDATE iterations 
                            SET celery_task_id = :celery_task_id
                            WHERE uuid = :iteration_id 
                            AND celery_task_id IS NULL
                            AND status = 'pending'
                        """
                        update_result = db.execute(text(update_celery_id_query), {
                            "celery_task_id": celery_result.id,
                            "iteration_id": iteration.iteration_id
                        })
                        
                        if update_result.rowcount > 0:
                            # Successfully set celery_task_id - commit to prevent double dispatch
                            db.commit()
                            dispatched_count += 1
                            logger.info(f"✅ Dispatched iteration {iteration.iteration_id} to Celery queue (task_id={celery_result.id})")
                        else:
                            # Race condition: another process already dispatched this iteration
                            logger.warning(f"⚠️ Iteration {iteration.iteration_id} was already dispatched by another process")
                            # Don't increment dispatched_count
                            
                    except Exception as celery_error:
                        # If Celery task fails to queue, log but don't mark as executing
                        logger.error(f"❌ Failed to queue Celery task for iteration {iteration.iteration_id}: {celery_error}")
                        # Rollback any partial state
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        # Don't increment dispatched_count - will retry on next cycle
                        continue
                    
                except Exception as e:
                    # Log error but CONTINUE to next iteration - don't halt entire dispatch cycle
                    logger.error(f"❌ Failed to dispatch iteration {iteration.iteration_id}: {e}", exc_info=True)
                    # Rollback any partial state
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    # Continue to next iteration - critical to not halt other dispatches
        
        logger.info(f"✅ Dispatch cycle completed. Dispatched: {dispatched_count} pending tasks")
        
        return {
            "status": "success",
            "dispatched_count": dispatched_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Critical error in dispatch_pending_tasks: {e}")
        return {
            "status": "error",
            "error": str(e),
            "dispatched_count": 0,
            "timestamp": datetime.now().isoformat()
        }

@celery_app.task(name="app.tasks.monitoring.handle_cleanup_fallbacks")
def handle_cleanup_fallbacks():
    """Handle tasks that are finished but stuck in cleanup phase"""
    try:
        logger.info("Starting cleanup fallback handling")
        
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        cleanup_fallbacks_handled = 0
        
        # Use centralized session manager
        with get_db_session() as db:
            # Find iterations that are marked as finished but have been stuck for a while
            # These might be stuck in cleanup phase
            # Note: task_identifier and prompt now come from execution snapshots (decoupled from tasks table)
            stuck_cleanup_query = """
                SELECT 
                    i.uuid as iteration_id,
                    i.execution_id,
                    e.gym_id,
                    e.model,
                    e.execution_folder_name,
                    e.task_identifier as task_id,
                    e.prompt,
                    i.completed_at,
                    i.status,
                    EXTRACT(EPOCH FROM (NOW() - i.completed_at)) as completed_time_seconds
                FROM iterations i
                JOIN executions e ON i.execution_id = e.uuid
                WHERE i.status IN ('passed', 'failed', 'crashed', 'timeout')
                AND i.completed_at IS NOT NULL
                AND i.completed_at < NOW() - INTERVAL '5 minutes'
                AND (i.result_data IS NULL OR i.verification_details IS NULL)
                ORDER BY i.completed_at ASC
                LIMIT 30
            """
            
            result = db.execute(text(stuck_cleanup_query))
            stuck_cleanup_iterations = result.fetchall()
            
            if stuck_cleanup_iterations:
                logger.warning(f"🧹 Found {len(stuck_cleanup_iterations)} iterations with incomplete cleanup data")
                
                for iteration in stuck_cleanup_iterations:
                    try:
                        logger.warning(f"🔄 Handling cleanup fallback for iteration {iteration.iteration_id} (completed {iteration.completed_time_seconds:.0f}s ago)")
                        
                        # Update with fallback data if missing
                        update_fields = []
                        update_values = {"iteration_id": iteration.iteration_id}
                        
                        if iteration.result_data is None:
                            update_fields.append("result_data = :result_data")
                            update_values["result_data"] = json.dumps({
                                "status": iteration.status,
                                "error": "Cleanup fallback - missing result data",
                                "execution_time": 0,
                                "iteration": 1,
                                "run_id": "cleanup_fallback",
                                "verification_results": {},
                                "iteration_directory": "N/A"
                            })
                        
                        if iteration.verification_details is None:
                            update_fields.append("verification_details = :verification_details")
                            update_values["verification_details"] = json.dumps({
                                "verification_status": "unknown",
                                "verification_comments": "Cleanup fallback - missing verification data"
                            })
                        
                        if update_fields:
                            update_fields.append("updated_at = NOW()")
                            update_query = f"""
                                UPDATE iterations 
                                SET {', '.join(update_fields)}
                                WHERE uuid = :iteration_id
                            """
                            db.execute(text(update_query), update_values)
                            db.commit()
                            
                            cleanup_fallbacks_handled += 1
                            logger.warning(f"✅ Applied cleanup fallback for iteration {iteration.iteration_id}")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to handle cleanup fallback for iteration {iteration.iteration_id}: {e}")
                        continue
        
        logger.info(f"🧹 Successfully handled {cleanup_fallbacks_handled} cleanup fallbacks!")
        return {
            "cleanup_fallbacks_handled": cleanup_fallbacks_handled,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cleanup fallback handling failed: {e}")
        raise

@celery_app.task(name="app.tasks.monitoring.check_stale_executing_tasks")
def check_stale_executing_tasks():
    """Check for tasks stuck in 'executing' state and reconcile with Celery's actual task states"""
    try:
        logger.info("🔍 Starting check for stale executing tasks")
        
        from sqlalchemy import text
        from app.core.config import settings
        from app.core.database_utils import get_db_session
        from app.schemas.iteration import IterationStatus
        
        reconciled_count = 0
        
        with get_db_session() as db:
            # Get all iterations currently marked as 'executing' with execution info for cleanup
            executing_query = """
                SELECT 
                    i.uuid as iteration_id,
                    i.celery_task_id,
                    i.started_at,
                    i.execution_id,
                    i.iteration_number,
                    e.execution_folder_name,
                    e.task_identifier,
                    EXTRACT(EPOCH FROM (NOW() - i.started_at)) as execution_time_seconds
                FROM iterations i
                JOIN executions e ON i.execution_id = e.uuid
                WHERE i.status = 'executing'
                ORDER BY i.started_at ASC
            """
            
            result = db.execute(text(executing_query))
            executing_iterations = result.fetchall()
            
            if not executing_iterations:
                logger.info("✅ No executing tasks found - all clean")
                return {
                    "status": "success",
                    "reconciled_count": 0,
                    "timestamp": datetime.now().isoformat()
                }
            
            logger.info(f"Found {len(executing_iterations)} iterations in 'executing' state")
            
            # Get active Celery tasks
            active_celery_task_ids = set()
            try:
                from app.celery_app import celery_app as celery_instance
                active_tasks = celery_instance.control.inspect().active()
                if active_tasks:
                    for worker, tasks in active_tasks.items():
                        if tasks:
                            for task in tasks:
                                task_id = task.get('id')
                                if task_id:
                                    active_celery_task_ids.add(task_id)
                logger.info(f"🔍 Found {len(active_celery_task_ids)} active tasks in Celery")
            except Exception as celery_check_error:
                logger.warning(f"⚠️ Failed to check Celery active tasks: {celery_check_error}")
                # Fall back to threshold-based cleanup when Celery inspection fails
                
            stale_threshold_seconds = settings.STALE_EXECUTING_THRESHOLD_SECONDS

            # Import required modules for cleanup and reset
            from pathlib import Path
            from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
            
            failed_cleanups = 0
            failed_resets = 0
            
            for iteration in executing_iterations:
                iteration_id = str(iteration.iteration_id)
                celery_task_id = iteration.celery_task_id
                execution_time = iteration.execution_time_seconds
                
                # Skip iterations without started_at (shouldn't happen, but handle gracefully)
                if execution_time is None:
                    logger.warning(f"⚠️ Iteration {iteration_id} has no started_at timestamp, skipping stale check")
                    continue
                
                # Check if this iteration's celery task is actually running
                is_actually_running = celery_task_id and celery_task_id in active_celery_task_ids
                
                # Treat task as stale only if it is missing from Celery's active list longer than the configured threshold
                if not is_actually_running and execution_time > stale_threshold_seconds:
                    logger.warning(
                        f"🔄 Found stale executing task: {iteration_id} "
                        f"(running for {execution_time:.0f}s, celery_task_id={celery_task_id})"
                    )
                    
                    try:
                        # Get execution info for cleanup
                        execution_folder_name = iteration.execution_folder_name
                        task_identifier = iteration.task_identifier
                        iteration_number = iteration.iteration_number
                        
                        # Step 1: Clean up iteration directory (if it exists)
                        # Same logic as rerun batch endpoint
                        # Note: cleanup_iteration_directory only works for batch executions (requires batch_ prefix)
                        if execution_folder_name and task_identifier and iteration_number:
                            # Only attempt cleanup for batch executions
                            if execution_folder_name.startswith("batch_") or execution_folder_name.startswith("playground_"):
                                base_results_dir = Path(settings.RESULTS_DIR)
                                execution_dir = base_results_dir / execution_folder_name
                                task_dir = execution_dir / task_identifier
                                iteration_dir = task_dir / f"iteration_{iteration_number}"
                                
                                iteration_dir_exists = iteration_dir.exists() and iteration_dir.is_dir()
                                
                                if iteration_dir_exists:
                                    logger.info(f"🧹 Cleaning up files for stale iteration {iteration_id}")
                                    cleanup_success = UnifiedTaskRunner.cleanup_iteration_directory(
                                        execution_folder_name, task_identifier, iteration_number
                                    )
                                    
                                    if not cleanup_success:
                                        logger.error(f"⚠️ Failed to cleanup files for iteration {iteration_id}")
                                        failed_cleanups += 1
                                        # Continue with reset even if cleanup fails
                                    else:
                                        logger.info(f"✅ Successfully cleaned up files for iteration {iteration_id}")
                                else:
                                    logger.info(f"ℹ️ No iteration directory to clean up for {iteration_id}")
                            else:
                                # Playground execution - skip cleanup (cleanup_iteration_directory doesn't support playground)
                                logger.info(f"ℹ️ Skipping cleanup for playground execution {iteration_id} (cleanup only supported for batch executions)")
                        else:
                            logger.warning(f"⚠️ Missing execution info for iteration {iteration_id} (folder={execution_folder_name}, task={task_identifier}, iter={iteration_number})")
                        
                        # Step 2: Reset iteration to pending status (same logic as rerun)
                        # Clear celery_task_id and all execution data, set status to pending
                        reset_query = """
                            UPDATE iterations 
                            SET 
                                status = :status,
                                celery_task_id = NULL,
                                started_at = NULL,
                                completed_at = NULL,
                                execution_time_seconds = NULL,
                                result_data = NULL,
                                error_message = NULL,
                                logs = NULL,
                                verification_details = NULL,
                                verification_comments = NULL,
                                updated_at = NOW()
                            WHERE uuid = :iteration_id
                            AND status = 'executing'
                        """
                        
                        reset_result = db.execute(text(reset_query), {
                            "status": IterationStatus.PENDING.value,
                            "iteration_id": iteration_id
                        })
                        db.commit()
                        
                        if reset_result.rowcount > 0:
                            reconciled_count += 1
                            logger.info(f"✅ Reconciled stale task {iteration_id} -> PENDING (will be redispatched)")
                        else:
                            logger.warning(f"⚠️ Failed to reset iteration {iteration_id} (may have been updated by another process)")
                            failed_resets += 1
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to reconcile iteration {iteration_id}: {e}", exc_info=True)
                        failed_resets += 1
                        # Rollback any partial changes
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        continue
        
        logger.info(f"✅ Stale task check completed. Reconciled {reconciled_count} tasks to pending")
        if failed_cleanups > 0 or failed_resets > 0:
            logger.warning(f"⚠️ Some operations failed: {failed_cleanups} cleanup failures, {failed_resets} reset failures")
        
        return {
            "status": "success",
            "reconciled_count": reconciled_count,
            "failed_cleanups": failed_cleanups,
            "failed_resets": failed_resets,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Stale task check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "reconciled_count": 0,
            "timestamp": datetime.now().isoformat()
        }

@celery_app.task(name="app.tasks.monitoring.backup_results")
def backup_results():
    """Backup execution results"""
    try:
        logger.info("Starting results backup")
        
        import shutil
        from datetime import datetime
        from pathlib import Path

        # Create backup directory
        backup_dir = Path("backups") / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup results directory
        results_dir = Path("results")
        if results_dir.exists():
            shutil.copytree(results_dir, backup_dir / "results")
        
        # Backup logs directory
        logs_dir = Path("logs")
        if logs_dir.exists():
            shutil.copytree(logs_dir, backup_dir / "logs")
        
        logger.info(f"Results backup completed: {backup_dir}")
        return str(backup_dir)
        
    except Exception as e:
        logger.error(f"Results backup failed: {e}")
        raise


@celery_app.task(name="app.tasks.monitoring.auto_recover_batches")
def auto_recover_batches(days_back: int = 2):
    """
    Automatically recover crashed and stuck batches
    
    This task runs on a schedule to detect and recover:
    1. Crashed batches: No pending/executing tasks, has failures → Rerun
    2. Stuck batches: Has executing tasks, latest iteration >2h old → Terminate + Rerun
    
    Args:
        days_back: Number of days to look back for batches (default: 2)
    """
    try:
        logger.info(f"🚀 Starting automated batch recovery (checking last {days_back} days)")
        
        from app.core.database_utils import get_db_session
        from app.services.batch_recovery_service import BatchRecoveryService
        
        # Use centralized synchronous database session (NullPool)
        with get_db_session() as db:
            result = BatchRecoveryService.auto_recover_batches(db, days_back)
        
        # Log summary
        logger.info(f"✅ Automated batch recovery complete:")
        logger.info(f"   💥 Crashed batches: {result['crashed_batches_recovered']}/{result['crashed_batches_found']}")
        logger.info(f"   🔒 Stuck batches: {result['stuck_batches_recovered']}/{result['stuck_batches_found']}")
        
        return {
            "status": "success",
            "crashed_batches_found": result['crashed_batches_found'],
            "crashed_batches_recovered": result['crashed_batches_recovered'],
            "stuck_batches_found": result['stuck_batches_found'],
            "stuck_batches_recovered": result['stuck_batches_recovered'],
            "timestamp": result['timestamp']
        }
        
    except Exception as e:
        logger.error(f"❌ Automated batch recovery failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@celery_app.task(name="app.tasks.monitoring.cleanup_leaked_browsers")
def cleanup_leaked_browsers():
    """
    Periodic task to detect and kill leaked browser processes
    
    Uses a two-tier safety approach:
    - AGGRESSIVE: If 200+ browsers AND no active tasks → kill all (safe)
    - CONSERVATIVE: If 50+ browsers → kill only orphaned/old processes (safer)
    
    This ensures running tasks are never interrupted.
    """
    try:
        from app.tasks.cleanup_utils import kill_leaked_browsers
        from app.core.config import settings
        
        logger.info("🧹 Starting leaked browser cleanup check")
        
        # Calculate thresholds based on worker concurrency
        concurrency = settings.CELERY_WORKER_CONCURRENCY
        normal_threshold = concurrency * 2  # 2 browsers per worker
        aggressive_threshold = concurrency * 4  # 4 browsers per worker (clearly leaked)
        
        # Execute safe cleanup
        result = kill_leaked_browsers(
            threshold=normal_threshold,
            aggressive_threshold=aggressive_threshold
        )
        
        # Log results
        if result["status"] == "cleaned_aggressive":
            logger.warning(
                f"🧹 AGGRESSIVE cleanup: Killed {result['killed_count']} browsers "
                f"(0 active tasks, threshold={aggressive_threshold})"
            )
        elif result["status"] == "cleaned_conservative":
            logger.warning(
                f"🧹 CONSERVATIVE cleanup: Killed {result['killed_count']} orphaned/old browsers "
                f"({result['active_tasks']} active tasks, {result['browser_count']} total browsers)"
            )
        elif result["status"] == "skipped":
            logger.warning(f"⚠️ Cleanup skipped: {result.get('reason', 'unknown')}")
        else:
            logger.info(
                f"✅ Browser count OK: {result.get('browser_count', 0)} browsers, "
                f"{result.get('active_tasks', 0)} active tasks (threshold={normal_threshold})"
            )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Browser cleanup failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


@celery_app.task(name="app.tasks.monitoring.cleanup_dangling_firefox")
def cleanup_dangling_firefox():
    """
    Critical task to detect and kill dangling Firefox processes
    
    This task implements a smart cleanup strategy:
    1. Finds the oldest executing task's runtime (e.g., 70 minutes)
    2. Counts running Firefox processes
    3. Counts executing tasks in database
    4. If firefox_processes > executing_tasks:
       - Calculates dynamic threshold: oldest_task_age + buffer (e.g., 70 + 10 = 80 minutes)
       - Kills Firefox processes older than threshold
    
    Note: In this system, Firefox is exclusively used by Playwright,
    so all Firefox processes are Playwright-managed processes.
    
    This ensures:
    - Active tasks are NEVER interrupted (threshold is dynamic based on oldest task)
    - Dangling processes from crashed tasks are cleaned up
    - Buffer is configurable via FIREFOX_CLEANUP_BUFFER_MINUTES env var (default: 10 min)
    
    Runs every 60 seconds to keep processes under control.
    """
    try:
        from app.tasks.cleanup_utils import kill_old_firefox_processes
        from app.core.config import settings
        
        logger.info("🦊 Starting dangling Firefox cleanup check")
        
        # Use dynamic threshold: oldest_executing_task_age + buffer
        # Buffer is configurable (default 10 minutes, can be set to 5, 20, etc.)
        # Example: If oldest task is 70 min old and buffer is 10 min, kill processes older than 80 min
        result = kill_old_firefox_processes(buffer_minutes=settings.FIREFOX_CLEANUP_BUFFER_MINUTES)
        
        # Log results
        if result["status"] == "cleaned":
            # Check if this was orphaned cleanup (no executing tasks) or dynamic threshold cleanup
            if result['executing_count'] == 0:
                logger.warning(
                    f"🧹 ORPHANED FIREFOX CLEANUP: Killed {result['killed_count']} processes "
                    f"(no executing tasks, {result['firefox_count']} total processes, "
                    f"min age: {result.get('minimum_age_minutes', 'N/A')} min)"
                )
            else:
                logger.warning(
                    f"🧹 DANGLING FIREFOX CLEANUP: Killed {result['killed_count']} processes "
                    f"(firefox: {result['firefox_count']}, executing: {result['executing_count']}, "
                    f"oldest task: {result.get('oldest_task_age_minutes', 0):.1f}min, "
                    f"buffer: {result.get('buffer_minutes', 0)}min, "
                    f"threshold: {result.get('age_threshold_minutes', 0):.1f}min)"
                )
            if result.get('killed_pids'):
                logger.info(f"   Killed PIDs: {', '.join(result['killed_pids'])}")
        elif result["status"] == "ok":
            logger.debug(
                f"✅ Firefox processes OK: {result['firefox_count']} processes, "
                f"{result['executing_count']} executing tasks"
            )
        elif result["status"] == "error":
            logger.error(f"❌ Firefox cleanup error: {result.get('error', 'unknown')}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Dangling Firefox cleanup failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "killed_count": 0
        }
