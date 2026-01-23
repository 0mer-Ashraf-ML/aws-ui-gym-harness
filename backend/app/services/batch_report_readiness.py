"""
Batch report readiness service - determines if a batch report can be generated
"""

import logging
from pathlib import Path
from typing import Dict, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.services.crud.batch import batch_crud
from app.services.crud.execution import execution_crud
from app.schemas.batch import BatchStatus

logger = logging.getLogger(__name__)


class BatchReportReadinessService:
    """Service to check if a batch report is ready for generation"""
    
    @staticmethod
    async def is_report_ready(db: AsyncSession, batch_id: UUID) -> Dict:
        """
        Check if a batch report is ready to be generated.
        
        A report is ready when:
        1. No tasks are pending
        2. No tasks are executing
        3. No tasks are crashed
        4. Failed tasks MUST have their execution directories present
        
        Returns:
            Dict with:
            - ready: bool - whether report is ready
            - reason: str - reason if not ready
            - blocking_items: List[Dict] - list of items blocking report generation
        """
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            return {
                "ready": False,
                "reason": "Batch not found",
                "blocking_items": []
            }
        
        # Get all executions for this batch
        executions = await execution_crud.get_multi_by_batch(db, batch_id)
        if not executions:
            return {
                "ready": False,
                "reason": "No executions found for this batch",
                "blocking_items": []
            }
        
        blocking_items = []
        results_dir = Path(settings.RESULTS_DIR)
        
        # Check each execution's iterations
        for execution in executions:
            query = """
                SELECT 
                    i.uuid,
                    i.iteration_number,
                    i.status,
                    i.error_message
                FROM iterations i
                WHERE i.execution_id = :execution_id
                ORDER BY i.iteration_number
            """
            result = await db.execute(text(query), {"execution_id": execution.uuid})
            iterations = result.fetchall()
            
            for iteration in iterations:
                status = iteration.status.lower() if iteration.status else "pending"
                
                # Check for blocking conditions
                if status == "pending":
                    blocking_items.append({
                        "type": "pending_iteration",
                        "execution_id": str(execution.uuid),
                        "iteration_number": iteration.iteration_number,
                        "status": status,
                        "task_identifier": execution.task_identifier,
                        "model": execution.model
                    })
                elif status == "executing":
                    blocking_items.append({
                        "type": "executing_iteration",
                        "execution_id": str(execution.uuid),
                        "iteration_number": iteration.iteration_number,
                        "status": status,
                        "task_identifier": execution.task_identifier,
                        "model": execution.model
                    })
                elif status == "crashed":
                    blocking_items.append({
                        "type": "crashed_iteration",
                        "execution_id": str(execution.uuid),
                        "iteration_number": iteration.iteration_number,
                        "status": status,
                        "task_identifier": execution.task_identifier,
                        "model": execution.model,
                        "error_message": iteration.error_message
                    })
                elif status == "failed":
                    # Check if iteration directory exists for failed tasks
                    if execution.execution_folder_name and execution.task_identifier:
                        execution_dir = results_dir / execution.execution_folder_name
                        task_dir = execution_dir / execution.task_identifier
                        iteration_dir = task_dir / f"iteration_{iteration.iteration_number}"
                        
                        if not iteration_dir.exists():
                            # Failed task without directory - likely a false failure
                            blocking_items.append({
                                "type": "failed_without_directory",
                                "execution_id": str(execution.uuid),
                                "iteration_number": iteration.iteration_number,
                                "status": status,
                                "task_identifier": execution.task_identifier,
                                "model": execution.model,
                                "error_message": iteration.error_message,
                                "missing_directory": str(iteration_dir)
                            })
        
        # Determine if report is ready
        if not blocking_items:
            return {
                "ready": True,
                "reason": "All tasks completed successfully or with valid failures",
                "blocking_items": []
            }
        
        # Categorize blocking items for better messaging
        pending_count = sum(1 for item in blocking_items if item["type"] == "pending_iteration")
        executing_count = sum(1 for item in blocking_items if item["type"] == "executing_iteration")
        crashed_count = sum(1 for item in blocking_items if item["type"] == "crashed_iteration")
        failed_no_dir_count = sum(1 for item in blocking_items if item["type"] == "failed_without_directory")
        
        reasons = []
        if pending_count > 0:
            reasons.append(f"{pending_count} pending iteration(s)")
        if executing_count > 0:
            reasons.append(f"{executing_count} executing iteration(s)")
        if crashed_count > 0:
            reasons.append(f"{crashed_count} crashed iteration(s)")
        if failed_no_dir_count > 0:
            reasons.append(f"{failed_no_dir_count} failed iteration(s) without execution directory")
        
        return {
            "ready": False,
            "reason": "Report cannot be generated: " + ", ".join(reasons),
            "blocking_items": blocking_items,
            "counts": {
                "pending": pending_count,
                "executing": executing_count,
                "crashed": crashed_count,
                "failed_without_directory": failed_no_dir_count,
                "total_blocking": len(blocking_items)
            }
        }
    
    @staticmethod
    async def get_all_ready_batches(db: AsyncSession, user_id: UUID = None, unread_only: bool = False) -> List[Dict]:
        """
        Get all batches that have reports ready to be generated.
        
        Args:
            db: Database session
            user_id: Current user's UUID for filtering read notifications
            unread_only: If True, only return batches not read by the user
        
        Returns:
            List of batch dicts with basic info for notifications
        """
        # Get all batches (ordered by most recent first)
        query = """
            SELECT 
                b.uuid,
                b.name,
                b.gym_id,
                b.number_of_iterations,
                b.notification_read_by,
                b.created_at,
                b.updated_at
            FROM batches b
            ORDER BY b.updated_at DESC
            LIMIT 100
        """
        result = await db.execute(text(query))
        batches = result.fetchall()
        
        ready_batches = []
        
        for batch in batches:
            batch_id = batch.uuid
            
            # Check if this batch's report is ready
            readiness = await BatchReportReadinessService.is_report_ready(db, batch_id)
            
            if readiness["ready"]:
                # Check if user has read this notification
                read_by_users = batch.notification_read_by or []
                user_id_str = str(user_id) if user_id else None
                is_read = user_id_str in read_by_users if user_id_str else False
                
                # Filter based on unread_only flag
                if unread_only and is_read:
                    continue
                
                ready_batches.append({
                    "batch_id": str(batch_id),
                    "batch_name": batch.name,
                    "gym_id": str(batch.gym_id),
                    "number_of_iterations": batch.number_of_iterations,
                    "is_read": is_read,
                    "created_at": batch.created_at.isoformat() if batch.created_at else None,
                    "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
                })
        
        logger.info(f"Found {len(ready_batches)} batches with ready reports out of {len(batches)} total batches (unread_only={unread_only})")
        
        return ready_batches


# Singleton instance
batch_report_readiness_service = BatchReportReadinessService()

