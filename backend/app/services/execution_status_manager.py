"""
Execution status management service for parent-child execution architecture
"""

import logging
from typing import Any, Dict

from app.core.database import AsyncSessionLocal
from app.schemas.execution import ExecutionStatus, TaskStatusSummary, ExecutionStatusSummary, ExecutionResponseWithStatus
from app.services.crud.execution import execution_crud
from app.services.crud.iteration import iteration_crud
from app.services.crud.task import task_crud

logger = logging.getLogger(__name__)

class ExecutionStatusManager:
    """Manages execution status based on child iteration statuses"""
    
    @staticmethod
    async def update_execution_status_from_iterations(execution_id: str) -> ExecutionStatus:
        """
        Update parent execution status based on child iteration statuses.

        Priority order:
        1. EXECUTING - if any iteration is still executing (highest priority for active states)
        2. CRASHED - if any iteration has crashed (highest priority for final states)
        3. FAILED - if any iteration has failed
        4. TIMEOUT - if any iteration has timed out (and no crashed/failed)
        5. PASSED - only if ALL iterations have passed
        6. PENDING - if all iterations are pending or no other rule matched
        """
        async with AsyncSessionLocal() as db:
            try:
                # Get execution summary
                summary = await iteration_crud.get_execution_summary(db, execution_id)
                
                total_iterations = summary['total_iterations']
                pending_count = summary['pending_count']
                executing_count = summary['executing_count']
                passed_count = summary['passed_count']
                failed_count = summary['failed_count']
                crashed_count = summary['crashed_count']
                timeout_count = summary['timeout_count']
                
                logger.info(f"Execution {execution_id} status check: "
                          f"Total={total_iterations}, Pending={pending_count}, "
                          f"Executing={executing_count}, Passed={passed_count}, "
                          f"Failed={failed_count}, Crashed={crashed_count}, Timeout={timeout_count}")
                
                # Determine new status - prioritize active states over final states
                new_status = ExecutionStatus.PENDING

                if executing_count > 0:
                    new_status = ExecutionStatus.EXECUTING
                elif crashed_count > 0:
                    new_status = ExecutionStatus.CRASHED
                elif failed_count > 0:
                    new_status = ExecutionStatus.FAILED
                elif timeout_count > 0:
                    new_status = ExecutionStatus.TIMEOUT
                elif passed_count == total_iterations and total_iterations > 0:
                    new_status = ExecutionStatus.PASSED
                elif pending_count == total_iterations:
                    new_status = ExecutionStatus.PENDING
                
                # Status is now computed in real-time, no need to update the execution table
                logger.info(f"Computed execution {execution_id} status as {new_status.value}")
                
                return new_status
                
            except Exception as e:
                logger.error(f"Error updating execution status for {execution_id}: {e}")
                await db.rollback()
                return ExecutionStatus.CRASHED
    
    @staticmethod
    async def get_execution_progress(execution_id: str) -> Dict[str, Any]:
        """Get detailed progress information for an execution"""
        async with AsyncSessionLocal() as db:
            try:
                # Get execution details
                execution = await execution_crud.get(db, execution_id)
                if not execution:
                    return {"error": "Execution not found"}
                
                # Get iteration summary
                summary = await iteration_crud.get_execution_summary(db, execution_id)
                
                # Get individual iterations with task information
                iterations = await iteration_crud.get_by_execution_id(db, execution_id)
                
                # Calculate progress percentage
                total_iterations = summary['total_iterations']
                completed_iterations = summary['passed_count'] + summary['failed_count'] + summary['crashed_count'] + summary['timeout_count']
                progress_percentage = (completed_iterations / total_iterations * 100) if total_iterations > 0 else 0
                
                # Compute execution status from iterations
                computed_status = await ExecutionStatusManager.update_execution_status_from_iterations(execution_id)
                
                # Group iterations by task_id using execution snapshot data
                tasks_data = {}
                
                # Use execution's snapshot fields (task_identifier and prompt)
                task_id = execution.task_identifier or "Unknown"
                
                if task_id not in tasks_data:
                    tasks_data[task_id] = {
                        "task_id": task_id,
                        "task_uuid": None,  # No longer have task UUID (decoupled)
                        "prompt": execution.prompt or "Unknown Task",
                        "iterations": []
                    }
                
                for iter in iterations:
                    tasks_data[task_id]["iterations"].append({
                        "uuid": str(iter.uuid),
                        "iteration_number": iter.iteration_number,
                        "status": iter.status,
                        "started_at": iter.started_at,
                        "completed_at": iter.completed_at,
                        "execution_time_seconds": iter.execution_time_seconds,
                        "verification_details": iter.verification_details,
                        "verification_comments": iter.verification_comments,
                        "eval_insights": iter.eval_insights
                    })
                
                # Sort iterations within each task by iteration number
                for task_data in tasks_data.values():
                    task_data["iterations"].sort(key=lambda x: x["iteration_number"])
                
                return {
                    "execution_id": execution_id,
                    "execution_status": computed_status.value,
                    "total_iterations": total_iterations,
                    "completed_iterations": completed_iterations,
                    "progress_percentage": round(progress_percentage, 2),
                    "summary": summary,
                    "tasks": list(tasks_data.values()),
                    # Keep backward compatibility
                    "iterations": [
                        {
                            "uuid": str(iter.uuid),
                            "iteration_number": iter.iteration_number,
                            "status": iter.status,
                            "started_at": iter.started_at,
                            "completed_at": iter.completed_at,
                            "execution_time_seconds": iter.execution_time_seconds,
                            "verification_details": iter.verification_details,
                            "verification_comments": iter.verification_comments,
                            "eval_insights": iter.eval_insights
                        }
                        for iter in iterations
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error getting execution progress for {execution_id}: {e}")
                return {"error": str(e)}
    
    @staticmethod
    async def create_execution_with_iterations(
        execution_data: Dict[str, Any],
        task_ids: list[str],
        number_of_iterations: int
    ) -> str:
        """Create parent execution and child iterations"""
        async with AsyncSessionLocal() as db:
            try:
                # Create parent execution
                execution = await execution_crud.create(db, execution_data)
                execution_id = str(execution.uuid)
                
                # Create iterations for each task
                # Note: After task decoupling, iterations don't store task_id
                # They get task info from their parent execution
                all_iterations = []
                for task_id in task_ids:
                    iterations = await iteration_crud.create_batch(
                        db, 
                        execution_id=execution.uuid,
                        number_of_iterations=number_of_iterations
                    )
                    all_iterations.extend(iterations)
                
                await db.commit()
                
                logger.info(f"Created execution {execution_id} with {len(all_iterations)} iterations")
                return execution_id
                
            except Exception as e:
                logger.error(f"Error creating execution with iterations: {e}")
                await db.rollback()
                raise
    
    @staticmethod
    async def calculate_task_status(iterations: list) -> ExecutionStatus:
        """
        Calculate task status based on its iterations using the same logic as execution status.
        
        Priority order:
        1. EXECUTING - if any iteration is executing (highest priority for active states)
        2. CRASHED - if any iteration has crashed (highest priority for final states)
        3. FAILED - if any iteration has failed
        4. TIMEOUT - if any iteration has timed out (and no crashed/failed)
        5. PASSED - only if ALL iterations have passed
        6. PENDING - if all iterations are pending or no other rule matched
        """
        if not iterations:
            return ExecutionStatus.PENDING
        
        # Count iterations by status
        status_counts = {}
        for iteration in iterations:
            status = iteration.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        executing_count = status_counts.get('executing', 0)
        crashed_count = status_counts.get('crashed', 0)
        failed_count = status_counts.get('failed', 0)
        timeout_count = status_counts.get('timeout', 0)
        passed_count = status_counts.get('passed', 0)
        pending_count = status_counts.get('pending', 0)
        total_iterations = len(iterations)
        
        # Determine status - prioritize active states over final states
        if executing_count > 0:
            return ExecutionStatus.EXECUTING
        elif crashed_count > 0:
            return ExecutionStatus.CRASHED
        elif failed_count > 0:
            return ExecutionStatus.FAILED
        elif timeout_count > 0:
            return ExecutionStatus.TIMEOUT
        elif passed_count == total_iterations and total_iterations > 0:
            return ExecutionStatus.PASSED
        elif pending_count == total_iterations:
            return ExecutionStatus.PENDING
        else:
            return ExecutionStatus.PENDING
    
    @staticmethod
    async def create_execution_response_with_status(execution, db) -> ExecutionResponseWithStatus:
        """Create an enhanced execution response with task status and iteration counts"""
        try:
            # Get all iterations for this execution
            iterations = await iteration_crud.get_by_execution_id(db, execution.uuid)
            
            # Get execution summary
            summary = await iteration_crud.get_execution_summary(db, str(execution.uuid))
            
            # Create execution status summary
            status_summary = ExecutionStatusSummary(
                total_iterations=summary['total_iterations'],
                passed_count=summary['passed_count'],
                failed_count=summary['failed_count'],
                crashed_count=summary['crashed_count'],
                timeout_count=summary['timeout_count'],
                pending_count=summary['pending_count'],
                executing_count=summary['executing_count']
            )
            
            # Group iterations by task and calculate task status
            # Use execution's task_identifier (all iterations in this execution belong to same task)
            task_id = execution.task_identifier
            
            if task_id:
                tasks_data = {
                    task_id: {
                        "task_identifier": task_id,
                        "prompt": execution.prompt,
                        "iterations": iterations
                    }
                }
            else:
                tasks_data = {}
            
            # Create task status summaries
            task_summaries = []
            for task_id, task_data in tasks_data.items():
                task_iterations = task_data["iterations"]
                
                # Count iterations by status for this task
                status_counts = {}
                for iteration in task_iterations:
                    status = iteration.status
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                # Calculate task status
                task_status = await ExecutionStatusManager.calculate_task_status(task_iterations)
                
                task_summary = TaskStatusSummary(
                    task_id=task_id,
                    task_uuid=None,  # No longer have task UUID (task decoupled)
                    prompt=task_data["prompt"],
                    status=task_status,
                    total_iterations=len(task_iterations),
                    passed_count=status_counts.get('passed', 0),
                    failed_count=status_counts.get('failed', 0),
                    crashed_count=status_counts.get('crashed', 0),
                    timeout_count=status_counts.get('timeout', 0),
                    pending_count=status_counts.get('pending', 0),
                    executing_count=status_counts.get('executing', 0)
                )
                task_summaries.append(task_summary)
            
            # Compute overall execution status
            computed_status = await ExecutionStatusManager.update_execution_status_from_iterations(str(execution.uuid))
            
            # Get execution_type value (convert enum to string if needed)
            execution_type_value = execution.execution_type
            if hasattr(execution_type_value, 'value'):
                execution_type_value = execution_type_value.value
            elif hasattr(execution_type_value, 'name'):
                # If it's an enum, get the value
                from app.models.execution import ExecutionType
                if execution_type_value == ExecutionType.BATCH:
                    execution_type_value = 'batch'
                elif execution_type_value == ExecutionType.PLAYGROUND:
                    execution_type_value = 'playground'
            
            # Create the enhanced response
            execution_dict = {
                "uuid": execution.uuid,
                "execution_folder_name": execution.execution_folder_name,
                "task_identifier": execution.task_identifier,
                "prompt": execution.prompt,
                "gym_id": execution.gym_id,
                "batch_id": execution.batch_id,
                "number_of_iterations": execution.number_of_iterations,
                "model": execution.model,
                "execution_type": execution_type_value,  # Include execution_type
                "playground_url": execution.playground_url,  # Include playground_url
                "status": computed_status,
                "eval_insights": execution.eval_insights,
                "created_at": execution.created_at,
                "updated_at": execution.updated_at,
                "status_summary": status_summary,
                "tasks": task_summaries
            }
            
            return ExecutionResponseWithStatus(**execution_dict)
            
        except Exception as e:
            logger.error(f"Error creating execution response with status: {e}")
            raise
