"""
Batch execution service
"""

import logging
from typing import List
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.batch import Batch
from app.models.execution import Execution
from app.schemas.execution import ExecutionCreate, ModelType
from app.services.crud.batch import batch_crud
from app.services.crud.execution import execution_crud
from app.services.crud.task import task_crud
from app.services.crud.iteration import iteration_crud

logger = logging.getLogger(__name__)


class BatchExecutionService:
    """Service for executing batches"""
    
    async def execute_batch(
        self, 
        db: AsyncSession, 
        batch_id: UUID,
        selected_models: List[ModelType] = None,
        selected_task_ids: List[UUID] = None
    ) -> List[Execution]:
        """Execute a batch by creating separate executions for each task+model combination"""
        
        # Get the batch
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")
        
        # Get tasks based on selection
        if selected_task_ids:
            # Filter to selected tasks only
            # Use a high limit to ensure we get all tasks (or fetch in chunks if needed)
            all_tasks = await task_crud.get_multi_by_gym(db, batch.gym_id, skip=0, limit=10000)
            tasks = [task for task in all_tasks if task.uuid in selected_task_ids]
            if not tasks:
                raise ValueError(f"None of the selected task IDs were found in gym {batch.gym_id}")
            logger.info(f"Using {len(tasks)} selected tasks from gym {batch.gym_id}")
        else:
            # Get all tasks for the gym (default behavior)
            # Use a high limit to ensure we get all tasks
            tasks = await task_crud.get_multi_by_gym(db, batch.gym_id, skip=0, limit=10000)
            if not tasks:
                raise ValueError(f"No tasks found for gym {batch.gym_id}")
            logger.info(f"Using all {len(tasks)} tasks from gym {batch.gym_id}")
        
        # Models to run for each task (use selected models or default to all)
        if selected_models is None:
            models = [ModelType.OPENAI, ModelType.ANTHROPIC, ModelType.GEMINI]
        else:
            models = selected_models
        
        # Create executions for each task (each task gets its own execution folder)
        executions = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sanitized_batch_name = batch.name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        
        for task in tasks:
            for model in models:
                # Create execution folder name for this specific task+model combination
                # Format: batch_name_task_model (separate execution per model)
                execution_folder_name = f"batch_{sanitized_batch_name}_{timestamp}_{task.task_id}_{model.value}"
                
                # Create execution record for this specific task+model combination
                # Use snapshot fields (task_identifier, prompt, grader_config, simulator_config) instead of task_id FK
                from app.schemas.execution import ExecutionType
                execution_data = ExecutionCreate(
                    gym_id=batch.gym_id,
                    task_identifier=task.task_id,  # Snapshot field (string)
                    prompt=task.prompt,  # Snapshot field
                    grader_config=task.grader_config,  # Snapshot field
                    simulator_config=task.simulator_config,  # Snapshot field
                    batch_id=batch.uuid,
                    number_of_iterations=batch.number_of_iterations,
                    model=model,  # Specific model for this execution
                    execution_folder_name=execution_folder_name,  # Separate folder per model
                    execution_type=ExecutionType.BATCH  # Explicitly set to batch for batch executions
                )
                
                execution = await execution_crud.create(db, execution_data)
                executions.append(execution)
                logger.info(f"Created execution {execution.uuid} for task {task.task_id} with model {model.value}")

                # Create iterations for this specific execution
                await iteration_crud.create_batch(
                    db,
                    execution_id=execution.uuid,
                    task_id=task.uuid,
                    number_of_iterations=batch.number_of_iterations
                )

                # Ensure database transaction is committed before dispatching Celery tasks
                await db.commit()
        
        logger.info(
            f"Created {len(executions)} executions for batch {batch_id} with {len(tasks)} tasks and {len(models)} models"
        )
        
        # Don't dispatch directly - let the monitoring task handle dispatch
        # This ensures consistent ordering and prevents race conditions
        logger.info(
            f"Iterations will be dispatched by the monitoring task (same flow as playground executions)"
        )
        
        return executions
    


# Create a singleton instance
batch_execution_service = BatchExecutionService()
