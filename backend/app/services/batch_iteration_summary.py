"""
Batch Iteration Summary Service
Aggregates iteration-level statistics for batches
"""

import logging
from typing import Dict, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.batch import Batch
from app.models.execution import Execution
from app.models.iteration import Iteration
from app.models.task import Task
from app.services.crud.batch import batch_crud
from app.services.crud.execution import execution_crud

logger = logging.getLogger(__name__)


class BatchIterationSummaryService:
    """Service for generating batch iteration summaries"""
    
    @staticmethod
    async def get_batch_iteration_summary(batch_id: UUID) -> Dict:
        """
        Get comprehensive iteration summary for a batch.
        
        Returns:
            - Overall iteration counts across all executions
            - Per-execution iteration breakdown with task and model info
        """
        async with AsyncSessionLocal() as db:
            try:
                # Get the batch
                batch = await batch_crud.get(db, batch_id)
                if not batch:
                    raise ValueError(f"Batch {batch_id} not found")
                
                # Get all executions for this batch with task information
                executions = await execution_crud.get_multi_by_batch(db, batch_id)
                
                if not executions:
                    return {
                        "batch_id": str(batch_id),
                        "batch_name": batch.name,
                        "overall_summary": {
                            "total_executions": 0,
                            "total_iterations": 0,
                            "iteration_counts": {
                                "pending": 0,
                                "executing": 0,
                                "passed": 0,
                                "failed": 0,
                                "crashed": 0
                            }
                        },
                        "execution_breakdowns": [],
                        "generated_at": datetime.utcnow().isoformat()
                    }
                
                # Initialize overall counters
                overall_counts = {
                    "pending": 0,
                    "executing": 0,
                    "passed": 0,
                    "failed": 0,
                    "crashed": 0
                }
                total_iterations = 0
                
                # Build per-execution breakdowns
                execution_breakdowns = []
                
                for execution in executions:
                    # Task information is now stored as snapshot in execution
                    # No need to query Task table - use execution.task_identifier and execution.prompt directly
                    
                    # Count iterations by status for this execution
                    iteration_result = await db.execute(
                        select(
                            Iteration.status,
                            func.count(Iteration.uuid).label('count')
                        )
                        .where(Iteration.execution_id == execution.uuid)
                        .group_by(Iteration.status)
                    )
                    
                    iteration_status_counts = {
                        "pending": 0,
                        "executing": 0,
                        "passed": 0,
                        "failed": 0,
                        "crashed": 0
                    }
                    
                    execution_total_iterations = 0
                    
                    for row in iteration_result:
                        status = row.status.lower()
                        count = row.count
                        
                        if status in iteration_status_counts:
                            iteration_status_counts[status] = count
                            overall_counts[status] += count
                            execution_total_iterations += count
                            total_iterations += count
                    
                    # Build execution breakdown using snapshot fields
                    execution_breakdowns.append({
                        "execution_id": str(execution.uuid),
                        "task_id": execution.task_identifier or "Unknown",  # Use snapshot field
                        "task_name": execution.prompt or "Unknown Task",  # Use snapshot field
                        "model": execution.model,
                        "total_iterations": execution_total_iterations,
                        "iteration_counts": iteration_status_counts
                    })
                
                # Build final response
                summary = {
                    "batch_id": str(batch_id),
                    "batch_name": batch.name,
                    "overall_summary": {
                        "total_executions": len(executions),
                        "total_iterations": total_iterations,
                        "iteration_counts": overall_counts
                    },
                    "execution_breakdowns": execution_breakdowns,
                    "generated_at": datetime.utcnow().isoformat()
                }
                
                logger.info(
                    f"Generated iteration summary for batch {batch_id}: "
                    f"{total_iterations} total iterations across {len(executions)} executions"
                )
                
                return summary
                
            except Exception as e:
                logger.error(f"Error generating iteration summary for batch {batch_id}: {e}")
                raise


# Create singleton instance
batch_iteration_summary_service = BatchIterationSummaryService()
