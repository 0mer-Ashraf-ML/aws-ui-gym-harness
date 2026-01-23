"""
Automated Batch Recovery Service

This service monitors batches and automatically recovers them when they are:
1. Crashed (no pending/executing tasks, only failed/crashed/passed)
2. Stuck (has executing tasks but the latest iteration started >2 hours ago)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.execution import Execution
from app.models.iteration import Iteration
from app.schemas.iteration import IterationStatus

logger = logging.getLogger(__name__)


class BatchRecoveryService:
    """Service for automated batch recovery"""

    @staticmethod
    def find_batches_needing_recovery(
        db: Session,
        days_back: int = 2
    ) -> Dict[str, List[UUID]]:
        """
        Find batches that need recovery
        
        Args:
            db: Database session
            days_back: How many days back to check batches (default: 2)
            
        Returns:
            Dictionary with two lists:
            - crashed_batches: List of batch UUIDs that are crashed
            - stuck_batches: List of batch UUIDs that are stuck
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        
        logger.info(f"🔍 Checking batches created after {cutoff_date}")
        logger.info(f"🔍 Checking for stuck iterations started before {two_hours_ago}")
        
        crashed_batches = []
        stuck_batches = []
        
        # Get all batches created within the time window
        result = db.execute(
            select(Batch)
            .where(Batch.created_at >= cutoff_date)
            .order_by(Batch.created_at.desc())
        )
        recent_batches = result.scalars().all()
        
        logger.info(f"📊 Found {len(recent_batches)} batches created in the last {days_back} days")
        
        for batch in recent_batches:
            logger.info(f"🔎 Analyzing batch {batch.uuid} ({batch.name})")
            
            # Get all iterations for this batch using a single query
            query = """
                SELECT 
                    i.uuid as iteration_id,
                    i.status,
                    i.started_at
                FROM iterations i
                JOIN executions e ON i.execution_id = e.uuid
                WHERE e.batch_id = :batch_id
                ORDER BY i.started_at DESC NULLS LAST
            """
            
            result = db.execute(text(query), {"batch_id": str(batch.uuid)})
            iterations = result.fetchall()
            
            if not iterations:
                logger.info(f"⚠️  Batch {batch.uuid} has no iterations, skipping")
                continue
            
            # Count iterations by status
            status_counts = {
                'pending': 0,
                'executing': 0,
                'passed': 0,
                'failed': 0,
                'crashed': 0,
                'timeout': 0
            }
            
            latest_iteration_start = None
            
            for iteration in iterations:
                status = iteration.status
                if status in status_counts:
                    status_counts[status] += 1
                
                # Track the latest started_at (query is already ordered by started_at DESC)
                if latest_iteration_start is None and iteration.started_at is not None:
                    latest_iteration_start = iteration.started_at
            
            logger.info(f"📈 Batch {batch.uuid} status counts: {status_counts}")
            logger.info(f"⏰ Latest iteration start time: {latest_iteration_start}")
            
            # Case 1: Crashed Batch
            # No pending or executing tasks, only terminal states (passed/failed/crashed/timeout)
            if status_counts['pending'] == 0 and status_counts['executing'] == 0:
                # Check if there are any crashed/timeout tasks (always rerun these)
                has_hard_failures = (
                    status_counts['crashed'] > 0 or 
                    status_counts['timeout'] > 0
                )
                
                if has_hard_failures:
                    logger.info(f"💥 Batch {batch.uuid} is CRASHED (no pending/executing, has crashed/timeout)")
                    crashed_batches.append(batch.uuid)
                # For failed tasks, we'll check for false failures in Case 3
                # This allows batches with only legitimate failures (with directories) to be skipped
                elif status_counts['failed'] == 0:
                    logger.info(f"✅ Batch {batch.uuid} is completed successfully, no recovery needed")
            
            # Case 2: Stuck Batch
            # Has executing tasks AND the latest iteration started more than 2 hours ago
            elif status_counts['executing'] > 0:
                if latest_iteration_start is None:
                    logger.warning(f"⚠️  Batch {batch.uuid} has executing tasks but no started_at timestamp")
                    continue
                
                # Make latest_iteration_start timezone-aware if it isn't
                if latest_iteration_start.tzinfo is None:
                    latest_iteration_start = latest_iteration_start.replace(tzinfo=timezone.utc)
                
                time_since_last_start = datetime.now(timezone.utc) - latest_iteration_start
                hours_since_last_start = time_since_last_start.total_seconds() / 3600
                
                logger.info(f"⏱️  Hours since latest iteration started: {hours_since_last_start:.2f}")
                
                if time_since_last_start > timedelta(hours=2):
                    logger.info(f"🔒 Batch {batch.uuid} is STUCK (has executing tasks, latest started {hours_since_last_start:.2f}h ago)")
                    stuck_batches.append(batch.uuid)
                else:
                    logger.info(f"🏃 Batch {batch.uuid} is actively running (latest iteration started {hours_since_last_start:.2f}h ago)")
            else:
                logger.info(f"⏳ Batch {batch.uuid} has pending tasks but nothing executing, waiting...")
            
            # Case 3: Check for false failures (failed tasks without directories) in ALL batches
            # This handles cases where tasks failed early without creating directories
            # Applies to both active batches AND fully completed batches
            if status_counts['failed'] > 0 and batch.uuid not in crashed_batches:
                # Check if any failed tasks are missing directories
                has_false_failures = BatchRecoveryService.check_for_false_failures(db, batch.uuid)
                if has_false_failures:
                    logger.info(f"⚠️  Batch {batch.uuid} has failed tasks without directories - adding to crashed list for recovery")
                    crashed_batches.append(batch.uuid)
                else:
                    # All failed tasks have directories - these are legitimate failures, skip recovery
                    logger.info(f"ℹ️  Batch {batch.uuid} has failed tasks but all have directories (legitimate failures), skipping recovery")
        
        logger.info(f"🎯 Recovery Summary: {len(crashed_batches)} crashed, {len(stuck_batches)} stuck")
        
        return {
            'crashed_batches': crashed_batches,
            'stuck_batches': stuck_batches
        }

    @staticmethod
    def check_for_false_failures(db: Session, batch_id: UUID) -> bool:
        """
        Check if a batch has any failed iterations without execution directories
        (false failures that occurred before directory creation)
        
        Args:
            db: Database session
            batch_id: Batch UUID to check
            
        Returns:
            True if false failures detected, False otherwise
        """
        from pathlib import Path
        from app.core.config import settings
        
        # Get failed iterations for this batch
        query = """
            SELECT 
                i.uuid as iteration_id,
                e.task_identifier as task_string_id,
                i.iteration_number,
                e.execution_folder_name
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            WHERE e.batch_id = :batch_id 
            AND i.status = 'failed'
        """
        
        result = db.execute(text(query), {"batch_id": str(batch_id)})
        failed_iterations = result.fetchall()
        
        if not failed_iterations:
            return False
        
        # Check if any failed iterations are missing directories
        for iteration in failed_iterations:
            base_results_dir = Path(settings.RESULTS_DIR)
            execution_dir = base_results_dir / iteration.execution_folder_name
            task_dir = execution_dir / str(iteration.task_string_id)
            iteration_dir = task_dir / f"iteration_{iteration.iteration_number}"
            
            if not (iteration_dir.exists() and iteration_dir.is_dir()):
                logger.info(f"⚠️  False failure detected: iteration {iteration.iteration_id} has no directory")
                return True
        
        return False
    
    @staticmethod
    def recover_crashed_batch(
        db: Session,
        batch_id: UUID
    ) -> Dict[str, Any]:
        """
        Recover a crashed batch by rerunning failed iterations
        
        Args:
            db: Database session
            batch_id: Batch UUID to recover
            
        Returns:
            Recovery result with details
        """
        logger.info(f"🔄 Recovering crashed batch {batch_id}")
        
        # Verify batch exists using direct query
        result = db.execute(
            select(Batch).where(Batch.uuid == batch_id)
        )
        batch = result.scalar_one_or_none()
        
        if not batch:
            logger.error(f"❌ Batch {batch_id} not found")
            return {
                'success': False,
                'error': 'Batch not found',
                'batch_id': str(batch_id)
            }
        
        # Check if rerun is disabled (user terminated the batch)
        if not getattr(batch, "rerun_enabled", True):
            logger.info(f"⏸️  Skipping auto-recovery for batch {batch_id} - rerun disabled after user termination")
            return {
                'success': False,
                'error': 'Rerun disabled - user terminated this batch',
                'batch_id': str(batch_id),
                'skipped': True
            }
        
        # Call the existing rerun_failed_iterations logic
        # We'll use the same query logic as the endpoint
        # Fetch crashed tasks + failed tasks (to check for false failures without execution dirs)
        query = """
            SELECT 
                i.uuid as iteration_id,
                e.task_identifier as task_string_id,
                e.prompt as task_prompt,
                i.iteration_number,
                i.status,
                e.execution_folder_name,
                e.gym_id,
                e.model as runner_type
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            WHERE e.batch_id = :batch_id 
            AND i.status IN ('crashed', 'failed')
            ORDER BY i.iteration_number ASC
        """
        
        result = db.execute(text(query), {"batch_id": str(batch_id)})
        iterations_to_check = result.fetchall()
        
        if not iterations_to_check:
            logger.info(f"ℹ️  No crashed or failed iterations to check for batch {batch_id}")
            return {
                'success': True,
                'batch_id': str(batch_id),
                'total_failed_iterations': 0,
                'rerun_iterations': 0,
                'message': 'No crashed or failed iterations to rerun'
            }
        
        logger.info(f"📝 Found {len(iterations_to_check)} crashed/failed iterations to check")
        
        # Import required modules for the rerun process
        from pathlib import Path
        from app.core.config import settings
        from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
        from app.tasks.unified_execution import unified_integration
        
        # Process each crashed/failed iteration
        pending_iteration_ids = []
        rerun_iterations = 0
        skipped_iterations = 0
        failed_cleanups = 0
        failed_resets = 0
        
        for iteration in iterations_to_check:
            iteration_id = str(iteration.iteration_id)
            task_string_id = str(iteration.task_string_id)
            iteration_number = iteration.iteration_number
            status = iteration.status
            execution_folder_name = iteration.execution_folder_name
            
            logger.info(f"🔧 Processing iteration {iteration_id} (status: {status})")
            
            # Check if iteration directory exists
            base_results_dir = Path(settings.RESULTS_DIR)
            execution_dir = base_results_dir / execution_folder_name
            task_dir = execution_dir / task_string_id
            iteration_dir = task_dir / f"iteration_{iteration_number}"
            
            iteration_dir_exists = iteration_dir.exists() and iteration_dir.is_dir()
            
            # Determine if we should rerun this iteration
            should_rerun = False
            
            if status == 'crashed':
                # Always rerun crashed tasks
                should_rerun = True
                logger.info(f"✅ Crashed task - will rerun")
            elif status == 'failed':
                # Only rerun failed tasks if execution directory doesn't exist (false failure)
                if not iteration_dir_exists:
                    should_rerun = True
                    logger.warning(f"⚠️  Failed task without execution directory - false failure detected, will rerun")
                else:
                    logger.info(f"ℹ️  Failed task with execution directory exists - preserving for debugging, skipping rerun")
                    skipped_iterations += 1
            
            if not should_rerun:
                continue
            
            # Step 1: Clean up iteration directory (if it exists)
            if iteration_dir_exists:
                logger.info(f"🧹 Cleaning up files for iteration {iteration_id}")
                cleanup_success = UnifiedTaskRunner.cleanup_iteration_directory(
                    execution_folder_name, task_string_id, iteration_number
                )
                
                if not cleanup_success:
                    logger.error(f"⚠️  Failed to cleanup files for iteration {iteration_id}")
                    failed_cleanups += 1
                    # Continue with other operations even if cleanup fails
            else:
                logger.info(f"ℹ️  No iteration directory to clean up for {iteration_id}")
            
            # Step 2: Reset iteration database record
            reset_success = unified_integration.reset_iteration_for_rerun(iteration_id)
            
            if not reset_success:
                logger.error(f"❌ Failed to reset database record for iteration {iteration_id}")
                failed_resets += 1
                continue
            
            if iteration_id not in pending_iteration_ids:
                rerun_iterations += 1
                pending_iteration_ids.append(iteration_id)
                logger.info(
                    "✅ Iteration %s reset to pending; dispatch deferred to beat scheduler",
                    iteration_id,
                )

        # No immediate dispatch – allow the beat scheduler to enqueue work in its next cycle
        failed_queues = 0
        if pending_iteration_ids:
            logger.info(
                "🚦 Deferred dispatch: %s iteration(s) marked pending for scheduler dispatch",
                len(pending_iteration_ids),
            )

        return {
            'success': True,
            'batch_id': str(batch_id),
            'total_failed_iterations': len(iterations_to_check),
            'rerun_iterations': rerun_iterations,
            'skipped_iterations': skipped_iterations,
            'failed_cleanups': failed_cleanups,
            'failed_resets': failed_resets,
            'failed_queues': failed_queues,
            'message': (
                f'Marked {rerun_iterations} iteration(s) as pending for rerun '
                f'({skipped_iterations} failed tasks with directories preserved); '
                'beat scheduler will handle dispatch'
            )
        }

    @staticmethod
    def recover_stuck_batch(
        db: Session,
        batch_id: UUID
    ) -> Dict[str, Any]:
        """
        Recover a stuck batch by terminating and then rerunning failed iterations
        
        Args:
            db: Database session
            batch_id: Batch UUID to recover
            
        Returns:
            Recovery result with details
        """
        logger.info(f"🔄 Recovering stuck batch {batch_id}")
        
        # Verify batch exists
        result = db.execute(
            select(Batch).where(Batch.uuid == batch_id)
        )
        batch = result.scalar_one_or_none()
        
        if not batch:
            logger.error(f"❌ Batch {batch_id} not found")
            return {
                'success': False,
                'error': 'Batch not found',
                'batch_id': str(batch_id)
            }
        
        # Check if rerun is disabled (user terminated the batch)
        if not getattr(batch, "rerun_enabled", True):
            logger.info(f"⏸️  Skipping auto-recovery for batch {batch_id} - rerun disabled after user termination")
            return {
                'success': False,
                'error': 'Rerun disabled - user terminated this batch',
                'batch_id': str(batch_id),
                'skipped': True
            }
        
        # Step 1: Terminate the batch
        logger.info(f"🛑 Terminating stuck batch {batch_id}")
        
        # Get all executions for this batch
        executions_result = db.execute(
            select(Execution).where(Execution.batch_id == batch_id)
        )
        executions = executions_result.scalars().all()
        
        from app.celery_app import celery_app

        terminated_count = 0
        for execution in executions:
            # Get iterations for this execution
            iterations_result = db.execute(
                select(Iteration).where(Iteration.execution_id == execution.uuid)
            )
            iterations = iterations_result.scalars().all()
            
            for iteration in iterations:
                if iteration.status == 'executing':
                    # Proactively stop the live Celery task running this iteration
                    if iteration.celery_task_id:
                        try:
                            logger.info(
                                f"🛑 Revoking executing Celery task {iteration.celery_task_id} "
                                f"for iteration {iteration.uuid}"
                            )
                            celery_app.control.revoke(
                                iteration.celery_task_id,
                                terminate=True,
                                signal="SIGKILL"
                            )
                        except Exception as revoke_error:
                            logger.warning(
                                f"⚠️  Failed to revoke Celery task {iteration.celery_task_id} "
                                f"for iteration {iteration.uuid}: {revoke_error}"
                            )
                    else:
                        logger.warning(
                            f"⚠️  Iteration {iteration.uuid} is executing but has no Celery task ID; "
                            "skipping revoke"
                        )

                    # Mark as crashed so it can be rerun
                    iteration.status = 'crashed'
                    iteration.error_message = 'Terminated by automated recovery: stuck for >2 hours'
                    terminated_count += 1

        db.commit()
        logger.info(f"🛑 Terminated {terminated_count} executing iterations")
        
        # Step 2: Rerun the now-crashed iterations
        logger.info(f"🔄 Rerunning failed iterations for batch {batch_id}")
        rerun_result = BatchRecoveryService.recover_crashed_batch(db, batch_id)
        
        return {
            'success': True,
            'batch_id': str(batch_id),
            'terminated_count': terminated_count,
            'rerun_result': rerun_result,
            'message': (
                f'Terminated {terminated_count} stuck iterations and marked '
                f'{rerun_result.get("rerun_iterations", 0)} pending for rerun'
            )
        }

    @staticmethod
    def detect_stuck_executing_tasks(
        db: Session,
        log_timeout_minutes: int = 20
    ) -> Dict[str, Any]:
        """
        Detect executing tasks where log file hasn't been updated in X minutes
        
        Args:
            db: Database session
            log_timeout_minutes: Minutes of log inactivity before marking as stuck (default: 20)
            
        Returns:
            Dictionary with stuck task details
        """
        from pathlib import Path
        from app.core.config import settings
        from app.celery_app import celery_app
        import os
        import time
        
        logger.info(f"🔍 Checking for stuck executing tasks (log timeout: {log_timeout_minutes} min)")
        
        # Get all executing iterations
        query = """
            SELECT 
                i.uuid as iteration_id,
                i.celery_task_id,
                i.started_at,
                e.execution_folder_name,
                e.task_identifier,
                i.iteration_number,
                e.batch_id
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            WHERE i.status = 'executing'
            ORDER BY i.started_at ASC
        """
        
        result = db.execute(text(query))
        executing_iterations = result.fetchall()
        
        if not executing_iterations:
            logger.info("ℹ️  No executing iterations found")
            return {
                'success': True,
                'stuck_count': 0,
                'message': 'No executing iterations to check'
            }
        
        logger.info(f"📊 Found {len(executing_iterations)} executing iterations to check")
        
        base_results_dir = Path(settings.RESULTS_DIR)
        timeout_seconds = log_timeout_minutes * 60
        current_time = time.time()
        
        stuck_iterations = []
        
        for iteration in executing_iterations:
            iteration_id = str(iteration.iteration_id)
            execution_folder_name = iteration.execution_folder_name
            task_identifier = iteration.task_identifier
            iteration_number = iteration.iteration_number
            
            # Build log directory path
            iteration_dir = base_results_dir / execution_folder_name / task_identifier / f"iteration_{iteration_number}"
            logs_dir = iteration_dir / "logs"
            
            if not logs_dir.exists():
                logger.warning(f"⚠️  Iteration {iteration_id}: No logs directory found at {logs_dir}")
                continue
            
            # Get the most recent log file modification time
            try:
                log_files = list(logs_dir.glob("*.log"))
                if not log_files:
                    logger.warning(f"⚠️  Iteration {iteration_id}: No log files found in {logs_dir}")
                    continue
                
                # Get the most recently modified log file
                most_recent_log = max(log_files, key=lambda f: f.stat().st_mtime)
                last_modified_time = most_recent_log.stat().st_mtime
                time_since_update = current_time - last_modified_time
                minutes_since_update = time_since_update / 60
                
                logger.info(
                    f"📝 Iteration {iteration_id}: Last log update {minutes_since_update:.1f} min ago "
                    f"(file: {most_recent_log.name})"
                )
                
                if time_since_update > timeout_seconds:
                    logger.warning(
                        f"🚨 Iteration {iteration_id}: STUCK! Log inactive for {minutes_since_update:.1f} min "
                        f"(threshold: {log_timeout_minutes} min)"
                    )
                    stuck_iterations.append({
                        'iteration_id': iteration_id,
                        'celery_task_id': iteration.celery_task_id,
                        'batch_id': str(iteration.batch_id) if iteration.batch_id else None,
                        'minutes_inactive': minutes_since_update,
                        'last_log_file': str(most_recent_log)
                    })
                    
            except Exception as e:
                logger.error(f"❌ Error checking logs for iteration {iteration_id}: {e}")
                continue
        
        # Mark stuck iterations as crashed and revoke their tasks
        crashed_count = 0
        for stuck_info in stuck_iterations:
            iteration_id = stuck_info['iteration_id']
            celery_task_id = stuck_info['celery_task_id']
            
            try:
                # Revoke the Celery task
                if celery_task_id:
                    logger.info(f"🛑 Revoking stuck Celery task {celery_task_id} for iteration {iteration_id}")
                    celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGKILL")
                
                # Mark as crashed in database
                update_query = """
                    UPDATE iterations
                    SET status = 'crashed',
                        error_message = :error_message,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE uuid = :iteration_id AND status = 'executing'
                """
                error_message = f"Task stuck: log inactive for {stuck_info['minutes_inactive']:.1f} minutes (timeout: {log_timeout_minutes} min)"
                
                update_result = db.execute(
                    text(update_query),
                    {
                        "iteration_id": iteration_id,
                        "error_message": error_message
                    }
                )
                
                if update_result.rowcount > 0:
                    crashed_count += 1
                    logger.info(f"✅ Marked iteration {iteration_id} as crashed")
                
            except Exception as e:
                logger.error(f"❌ Failed to crash iteration {iteration_id}: {e}")
        
        db.commit()
        
        logger.info(f"🎯 Stuck task detection complete: {crashed_count} tasks marked as crashed")
        
        return {
            'success': True,
            'stuck_count': crashed_count,
            'stuck_iterations': stuck_iterations,
            'message': f'Marked {crashed_count} stuck executing task(s) as crashed'
        }

    @staticmethod
    def auto_recover_batches(
        db: Session,
        days_back: int = 2
    ) -> Dict[str, Any]:
        """
        Main entry point for automated batch recovery
        
        Args:
            db: Database session
            days_back: How many days back to check batches (default: 2)
            
        Returns:
            Complete recovery report
        """
        logger.info(f"🚀 Starting automated batch recovery (checking last {days_back} days)")
        
        # Step 1: Detect and crash stuck executing tasks (log timeout)
        stuck_tasks_result = BatchRecoveryService.detect_stuck_executing_tasks(db, log_timeout_minutes=20)
        
        # Step 2: Find batches needing recovery
        batches_to_recover = BatchRecoveryService.find_batches_needing_recovery(
            db, days_back
        )
        
        crashed_batches = batches_to_recover['crashed_batches']
        stuck_batches = batches_to_recover['stuck_batches']
        
        # Recover crashed batches
        crashed_results = []
        for batch_id in crashed_batches:
            try:
                result = BatchRecoveryService.recover_crashed_batch(db, batch_id)
                crashed_results.append(result)
            except Exception as e:
                logger.error(f"❌ Error recovering crashed batch {batch_id}: {e}")
                crashed_results.append({
                    'success': False,
                    'batch_id': str(batch_id),
                    'error': str(e)
                })
        
        # Recover stuck batches
        stuck_results = []
        for batch_id in stuck_batches:
            try:
                result = BatchRecoveryService.recover_stuck_batch(db, batch_id)
                stuck_results.append(result)
            except Exception as e:
                logger.error(f"❌ Error recovering stuck batch {batch_id}: {e}")
                stuck_results.append({
                    'success': False,
                    'batch_id': str(batch_id),
                    'error': str(e)
                })
        
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'days_checked': days_back,
            'stuck_executing_tasks': stuck_tasks_result.get('stuck_count', 0),
            'crashed_batches_found': len(crashed_batches),
            'stuck_batches_found': len(stuck_batches),
            'crashed_batches_recovered': sum(1 for r in crashed_results if r.get('success')),
            'stuck_batches_recovered': sum(1 for r in stuck_results if r.get('success')),
            'stuck_tasks_details': stuck_tasks_result,
            'crashed_recovery_details': crashed_results,
            'stuck_recovery_details': stuck_results
        }
        
        logger.info(
            f"✅ Automated batch recovery complete: "
            f"{stuck_tasks_result.get('stuck_count', 0)} stuck executing tasks, "
            f"{summary['crashed_batches_recovered']}/{summary['crashed_batches_found']} crashed batches, "
            f"{summary['stuck_batches_recovered']}/{summary['stuck_batches_found']} stuck batches"
        )
        
        return summary
