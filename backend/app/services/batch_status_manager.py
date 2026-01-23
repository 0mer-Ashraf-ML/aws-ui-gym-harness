"""
Batch status management service
"""

import logging
from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.schemas.batch import BatchStatus
from app.services.crud.execution import execution_crud
from app.services.execution_status_manager import ExecutionStatusManager

logger = logging.getLogger(__name__)


class BatchStatusManager:
    """Service for managing batch status updates"""
    
    @staticmethod
    async def update_batch_status_from_executions(batch_id: UUID) -> BatchStatus:
        """
        Update batch status based on execution statuses.
        
        Priority order:
        1. EXECUTING - if ANY execution is currently executing (highest priority for active states)
        2. PENDING - if NO executions are executing but some are pending
        3. CRASHED - if any execution has crashed (highest priority for final states)
        4. FAILED - if any execution has failed/timeout
        5. COMPLETED - only if ALL executions have passed
        6. PENDING - fallback if no other rule matched
        """
        async with AsyncSessionLocal() as db:
            try:
                # Get all executions for this batch
                executions = await execution_crud.get_multi_by_batch(db, batch_id)
                
                if not executions:
                    logger.warning(f"No executions found for batch {batch_id}")
                    return BatchStatus.PENDING
                
                # Count executions by status (map execution status to batch status)
                status_counts = {
                    'pending': 0,
                    'executing': 0,
                    'completed': 0,  # Maps from execution 'passed'
                    'failed': 0,     # Maps from execution 'failed', 'timeout'
                    'crashed': 0     # Maps from execution 'crashed'
                }
                
                total_executions = len(executions)
                
                for execution in executions:
                    # Get computed execution status
                    execution_status = await ExecutionStatusManager.update_execution_status_from_iterations(str(execution.uuid))
                    
                    # Map execution status to batch status (same priority as ExecutionStatusManager)
                    if execution_status.value == 'crashed':
                        status_counts['crashed'] += 1
                    elif execution_status.value == 'passed':
                        status_counts['completed'] += 1
                    elif execution_status.value in ['failed', 'timeout']:
                        status_counts['failed'] += 1
                    elif execution_status.value == 'executing':
                        status_counts['executing'] += 1
                    elif execution_status.value == 'pending':
                        status_counts['pending'] += 1
                
                # Check if any executions are still running (pending or executing)
                has_running_executions = status_counts['pending'] > 0 or status_counts['executing'] > 0
                
                logger.info(f"Batch {batch_id} status check: "
                          f"Total={total_executions}, Pending={status_counts['pending']}, "
                          f"Executing={status_counts['executing']}, Completed={status_counts['completed']}, "
                          f"Failed={status_counts['failed']}, Crashed={status_counts['crashed']}, "
                          f"HasRunning={has_running_executions}")
                
                # Determine new batch status (priority: active states > final states)
                new_status = BatchStatus.PENDING
                
                # PRIORITY 1: EXECUTING - If ANY execution is currently running, batch is executing
                if status_counts['executing'] > 0:
                    new_status = BatchStatus.EXECUTING
                # PRIORITY 2: PENDING - If NO executions are executing but some are pending
                elif status_counts['pending'] > 0:
                    new_status = BatchStatus.PENDING
                else:
                    # All executions are finished, determine final status
                    # PRIORITY 3-5: Final states (crashed > failed > completed)
                    if status_counts['crashed'] > 0:
                        new_status = BatchStatus.CRASHED
                    elif status_counts['failed'] > 0:
                        new_status = BatchStatus.FAILED
                    elif status_counts['completed'] == total_executions and total_executions > 0:
                        new_status = BatchStatus.COMPLETED
                    else:
                        # PRIORITY 6: Fallback - should not happen
                        new_status = BatchStatus.PENDING
                
                # Status is computed in real-time, no need to update the database
                logger.info(f"Computed batch {batch_id} status as {new_status.value}")
                
                return new_status
                
            except Exception as e:
                logger.error(f"Error updating batch {batch_id} status: {e}")
                return BatchStatus.PENDING
    
    @staticmethod
    async def get_batch_status_summary(batch_id: UUID) -> dict:
        """Get a summary of batch execution statuses"""
        async with AsyncSessionLocal() as db:
            try:
                executions = await execution_crud.get_multi_by_batch(db, batch_id)
                
                if not executions:
                    return {
                        'total_executions': 0,
                        'pending_count': 0,
                        'executing_count': 0,
                        'passed_count': 0,
                        'failed_count': 0,
                        'crashed_count': 0,
                        'timeout_count': 0
                    }
                
                status_counts = {
                    'pending': 0,
                    'executing': 0,
                    'passed': 0,
                    'failed': 0,
                    'crashed': 0,
                    'timeout': 0
                }
                
                for execution in executions:
                    execution_status = await ExecutionStatusManager.update_execution_status_from_iterations(str(execution.uuid))
                    status_counts[execution_status.value] += 1
                
                return {
                    'total_executions': len(executions),
                    'pending_count': status_counts['pending'],
                    'executing_count': status_counts['executing'],
                    'passed_count': status_counts['passed'],
                    'failed_count': status_counts['failed'],
                    'crashed_count': status_counts['crashed'],
                    'timeout_count': status_counts['timeout']
                }
                
            except Exception as e:
                logger.error(f"Error getting batch {batch_id} status summary: {e}")
                return {
                    'total_executions': 0,
                    'pending_count': 0,
                    'executing_count': 0,
                    'passed_count': 0,
                    'failed_count': 0,
                    'crashed_count': 0,
                    'timeout_count': 0
                }


# Create a singleton instance
batch_status_manager = BatchStatusManager()
