"""
Celery tasks for single iteration execution
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from celery.exceptions import SoftTimeLimitExceeded
from app.celery_app import celery_app
from app.schemas.iteration import IterationStatus

logger = logging.getLogger(__name__)

# Old _update_iteration_status function removed - now using _update_iteration_and_execution_status

ALLOWED_ITERATION_UPDATE_FIELDS = {
    "celery_task_id",
    "started_at",
    "completed_at",
    "execution_time_seconds",
    "result_data",
    "error_message",
    "logs",
    "verification_details",
    "verification_comments",
    "last_model_response",
    "eval_insights",
    "total_steps",
}


def _update_iteration_and_execution_status(iteration_id: str, status: IterationStatus, **kwargs) -> None:
    """Update iteration status and execution status in a single transaction"""
    logger.info(
        "🔄 Starting _update_iteration_and_execution_status for iteration %s with status %s",
        iteration_id,
        status.value,
    )

    filtered_kwargs = {}
    for key, value in kwargs.items():
        if key not in ALLOWED_ITERATION_UPDATE_FIELDS:
            logger.warning(
                "⚠️ Ignoring unsupported iteration column '%s' (value=%s)",
                key,
                value,
            )
            continue
        filtered_kwargs[key] = value

    logger.info(
        "🔄 Function parameters after filtering: iteration_id=%s, status=%s, kwargs=%s",
        iteration_id,
        status,
        filtered_kwargs,
    )
    
    # DEBUG: Log last_model_response specifically
    if 'last_model_response' in filtered_kwargs:
        model_response = filtered_kwargs['last_model_response']
        logger.info(f"🔍 DEBUG: last_model_response being saved: '{model_response[:100]}...' (length: {len(model_response)})")
    else:
        logger.info("🔍 DEBUG: No last_model_response in filtered_kwargs")
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        from app.core.config import settings

        # Using centralized db_utils for synchronous DB access
        with get_db_session() as db:
            # Update iteration status
            update_fields = []
            update_values = {"status": status.value}
            
            # Process kwargs - update only supported columns
            for key, value in filtered_kwargs.items():
                if value is not None:
                    update_fields.append(f"{key} = :{key}")
                    update_values[key] = value
            
            if update_fields:
                update_fields.append("status = :status")
                update_fields.append("updated_at = NOW()")
                query = f"""
                    UPDATE iterations 
                    SET {', '.join(update_fields)}
                    WHERE uuid = :iteration_id
                """
                update_values["iteration_id"] = iteration_id
                
                logger.info(f"🔄 Executing query: {query}")
                logger.info(f"🔄 With values: {update_values}")
                result = db.execute(text(query), update_values)
                logger.info(f"✅ Updated iteration {iteration_id} status to {status.value}, rows affected: {result.rowcount}")
                
                # DEBUG: Log what was actually saved for last_model_response
                if 'last_model_response' in update_values:
                    saved_response = update_values['last_model_response']
                    logger.info(f"🔍 DEBUG: last_model_response saved to DB: '{saved_response[:100]}...' (length: {len(saved_response)})")
            else:
                # Just update status
                query = """
                    UPDATE iterations 
                    SET status = :status, updated_at = NOW()
                    WHERE uuid = :iteration_id
                """
                logger.info(f"🔄 Executing simple query: {query}")
                logger.info(f"🔄 With values: {{'status': '{status.value}', 'iteration_id': '{iteration_id}'}}")
                result = db.execute(text(query), {"status": status.value, "iteration_id": iteration_id})
                logger.info(f"✅ Updated iteration {iteration_id} status to {status.value}, rows affected: {result.rowcount}")
            
            # Get execution_id from iteration
            exec_query = """
                SELECT execution_id 
                FROM iterations 
                WHERE uuid = :iteration_id
            """
            result = db.execute(text(exec_query), {"iteration_id": iteration_id})
            row = result.fetchone()
            
            if row:
                execution_id = row.execution_id
                
                # Get iteration status summary (now in same transaction)
                summary_query = """
                    SELECT 
                        COUNT(*) as total_iterations,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
                        COUNT(*) FILTER (WHERE status = 'executing') as executing_count,
                        COUNT(*) FILTER (WHERE status = 'passed') as passed_count,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
                        COUNT(*) FILTER (WHERE status = 'crashed') as crashed_count
                    FROM iterations 
                    WHERE execution_id = :execution_id
                """
                summary_result = db.execute(text(summary_query), {"execution_id": execution_id})
                summary = summary_result.fetchone()
                
                total_iterations = summary.total_iterations
                pending_count = summary.pending_count
                executing_count = summary.executing_count
                passed_count = summary.passed_count
                failed_count = summary.failed_count
                crashed_count = summary.crashed_count
                
                logger.info(f"Execution {execution_id} status check: "
                          f"Total={total_iterations}, Pending={pending_count}, "
                          f"Executing={executing_count}, Passed={passed_count}, "
                          f"Failed={failed_count}, Crashed={crashed_count}")
                
                # Status is now computed in real-time, no need to update the execution table
                logger.info(f"Computed execution {execution_id} status from updated iterations")
            
            # Commit the transaction
            db.commit()
            logger.info(f"✅ Successfully committed iteration {iteration_id} status update to {status.value}")
                
    except Exception as e:
        logger.error(f"❌ Failed to update iteration and execution status: {e}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        logger.error(f"❌ Exception details: {str(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")

def _execute_single_iteration(iteration_id: str, task_id: str, gym_id: str, runner_type: str, max_wait_time: int = None) -> Dict[str, Any]:
    """Execute a single iteration using the appropriate runner"""
    try:
        logger.info(f"Executing iteration {iteration_id} for task {task_id} with {runner_type}")
        
        # Get or create a shared UnifiedTaskRunner instance for this execution
        # Each iteration gets its own async Playwright instance, but shares the runner
        from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
        runner = UnifiedTaskRunner()  # Shared runner instance per execution, isolated Playwright per iteration
        
        # Get execution snapshot configs (grader_config and simulator_config) from iteration
        execution_snapshot_configs = _get_execution_snapshot_configs_from_iteration(iteration_id)
        if execution_snapshot_configs:
            logger.info(f"✅ Loaded grader_config and simulator_config from execution snapshot")
        
        # Get task data from database with execution snapshot configs (preferred over task table)
        task_data = _get_task_data_from_db(task_id, gym_id, execution_snapshot_configs)
        if not task_data:
            raise ValueError(f"Task {task_id} not found in gym {gym_id}")
        
        # Get iteration number from database
        iteration_number = _get_iteration_number_from_db(iteration_id)
        
        # Get execution folder name from database
        execution_folder_name = _get_execution_folder_name_from_iteration(iteration_id)
        
        # Get execution_id from database
        execution_id = _get_execution_id_from_iteration(iteration_id)
        
        # Execute single iteration - UnifiedTaskRunner.execute_single_iteration_from_db is synchronous
        # No need for asyncio.run() which creates event loops that conflict with Playwright
        result = runner.execute_single_iteration_from_db(
            task_data=task_data,
            iteration_number=iteration_number,
            max_wait_time=max_wait_time,
            execution_folder_name=execution_folder_name,
            iteration_id=iteration_id,
            execution_id=execution_id
        )
        
        # Add metadata to the result (UnifiedTaskRunner returns consistent format)
        result["runner_type"] = runner_type
        result["iteration_id"] = iteration_id
        result["task_id"] = task_id
        result["gym_id"] = gym_id
        result["execution_status"] = "completed"
        
        return result
        
    except SoftTimeLimitExceeded:
        # Re-raise SoftTimeLimitExceeded to be handled by the main Celery task
        raise
    except Exception as e:
        logger.error(f"Iteration execution failed: {e}")
        return {
            "runner_type": runner_type,
            "iteration_id": iteration_id,
            "task_id": task_id,
            "gym_id": gym_id,
            "error": str(e),
            "status": "failed"
        }

def _get_execution_snapshot_configs_from_iteration(iteration_id: str) -> Optional[Dict[str, Any]]:
    """Get grader_config and simulator_config from execution snapshot via iteration_id"""
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        with get_db_session() as db:
            query = """
                SELECT e.grader_config, e.simulator_config
                FROM executions e
                JOIN iterations i ON e.uuid = i.execution_id
                WHERE i.uuid = :iteration_id
            """
            result = db.execute(text(query), {"iteration_id": iteration_id})
            row = result.fetchone()
            
            if row:
                return {
                    'grader_config': row.grader_config,
                    'simulator_config': row.simulator_config
                }
            else:
                logger.warning(f"Execution snapshot configs not found for iteration {iteration_id}")
                return None
                
    except Exception as e:
        logger.error(f"Error getting execution snapshot configs: {e}")
        return None

def _get_task_data_from_db(task_id: str, gym_id: str, execution_snapshot_configs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get task data from database using synchronous operations"""
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        from app.core.config import settings
        from app.core.config_loader import load_configs_from_files

        # Load configs from files if feature flag is enabled
        file_configs = {}
        if settings.USE_CONFIG_FILES:
            file_configs = load_configs_from_files(task_id)

        # Using centralized db_utils for synchronous DB access
        with get_db_session() as db:
            query = """
                SELECT t.task_id, t.prompt, t.grader_config, t.simulator_config, t.verifier_path, t.gym_id, g.base_url, g.verification_strategy
                FROM tasks t
                JOIN gyms g ON t.gym_id = g.uuid
                WHERE t.uuid = :task_id AND t.gym_id = :gym_id
            """
            result = db.execute(text(query), {"task_id": task_id, "gym_id": gym_id})
            row = result.fetchone()
            
            if row:
                # Ensure verification_strategy is the string value, not the enum name
                verification_strategy = row.verification_strategy
                if hasattr(verification_strategy, 'value'):
                    verification_strategy = verification_strategy.value
                
                # Priority: File configs > Execution snapshot > Task table
                grader_config = (
                    file_configs.get('grader_config') or 
                    (execution_snapshot_configs.get('grader_config') if execution_snapshot_configs else None) or
                    row.grader_config
                )
                simulator_config = (
                    file_configs.get('simulator_config') or 
                    (execution_snapshot_configs.get('simulator_config') if execution_snapshot_configs else None) or
                    row.simulator_config
                )
                
                if settings.USE_CONFIG_FILES and (file_configs.get('grader_config') or file_configs.get('simulator_config')):
                    logger.info(f"✅ Loaded configs from files for task: {task_id}")
                
                return {
                    "task_id": row.task_id,
                    "prompt": row.prompt,
                    "task_description": row.prompt,  # Add task_description for compatibility
                    "grader_config": grader_config,  # Include grader_config (from file or DB)
                    "simulator_config": simulator_config,  # Include simulator_config (from file or DB)
                    "verifier_path": row.verifier_path,  # Include verifier_path for verifier_api_script strategy
                    "gym_id": str(row.gym_id),
                    "base_url": row.base_url,
                    "verification_strategy": verification_strategy,
                    "task_link": row.base_url,  # Use base_url as task_link
                    "max_steps": 100,  # Default max steps for task execution
                    "max_wait_time": 7200,  # Default max wait time (120 minutes / 2 hours)
                    "priority": "medium"  # Default priority
                }
            return None
            
    except Exception as e:
        logger.error(f"Error getting task data from database: {e}")
        return None

def _get_execution_folder_name_from_iteration(iteration_id: str) -> str:
    """Get execution folder name from iteration using synchronous operations"""
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        from app.core.config import settings

        # Using centralized db_utils for synchronous DB access
        with get_db_session() as db:
            query = """
                SELECT e.execution_folder_name, e.uuid as execution_id, e.created_at
                FROM iterations i
                JOIN executions e ON i.execution_id = e.uuid
                WHERE i.uuid = :iteration_id
            """
            result = db.execute(text(query), {"iteration_id": iteration_id})
            row = result.fetchone()
            
            if row and row.execution_folder_name:
                logger.info(f"Using stored execution folder name: {row.execution_folder_name}")
                return row.execution_folder_name
            elif row:
                # If execution_folder_name is None, try to reconstruct it using the creation timestamp
                if row.created_at:
                    timestamp = row.created_at.strftime('%Y%m%d_%H%M%S')
                    reconstructed_name = f"execution_iterations_{timestamp}"
                    logger.warning(f"Execution folder name was None, reconstructed as: {reconstructed_name}")
                    return reconstructed_name
                else:
                    # Fallback to current timestamp
                    fallback_name = f"execution_iterations_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    logger.warning(f"Could not reconstruct folder name, using fallback: {fallback_name}")
                    return fallback_name
            else:
                # No execution found
                fallback_name = f"execution_iterations_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                logger.error(f"No execution found for iteration {iteration_id}, using fallback: {fallback_name}")
                return fallback_name
                
    except Exception as e:
        logger.error(f"Error getting execution folder name: {e}")
        fallback_name = f"execution_iterations_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.error(f"Using emergency fallback: {fallback_name}")
        return fallback_name

def _get_iteration_number_from_db(iteration_id: str) -> int:
    """Get iteration number from database"""
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        from app.core.config import settings

        # Using centralized db_utils for synchronous DB access
        with get_db_session() as db:
            query = """
                SELECT iteration_number
                FROM iterations
                WHERE uuid = :iteration_id
            """
            result = db.execute(text(query), {"iteration_id": iteration_id})
            row = result.fetchone()
            
            if row:
                logger.info(f"Found iteration number: {row.iteration_number}")
                return row.iteration_number
            else:
                logger.warning(f"Iteration {iteration_id} not found, using default iteration number 1")
                return 1
                
    except Exception as e:
        logger.error(f"Error getting iteration number: {e}")
        logger.warning("Using default iteration number 1")
        return 1


def _get_execution_id_from_iteration(iteration_id: str) -> str:
    """Get execution_id from iteration"""
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        with get_db_session() as db:
            query = """
                SELECT execution_id
                FROM iterations
                WHERE uuid = :iteration_id
            """
            result = db.execute(text(query), {"iteration_id": iteration_id})
            row = result.fetchone()
            
            if row:
                logger.info(f"Found execution_id: {row.execution_id}")
                return str(row.execution_id)
            else:
                logger.warning(f"Iteration {iteration_id} not found, cannot get execution_id")
                return None
                
    except Exception as e:
        logger.error(f"Error getting execution_id: {e}")
        return None


@celery_app.task(bind=True, name="app.tasks.iteration_execution.execute_single_iteration", priority=10)
def execute_single_iteration(self, iteration_id: str, task_id: str, gym_id: str, runner_type: str, max_wait_time: int = None):
    """Execute a single iteration"""
    start_time = datetime.now()
    
    try:
        logger.info(f"Starting iteration execution: {iteration_id} for task {task_id} with {runner_type}")
        
        # Update iteration status to executing
        _update_iteration_and_execution_status(
            iteration_id, 
            IterationStatus.EXECUTING,
            started_at=start_time,
            celery_task_id=self.request.id
        )
        
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "Starting iteration execution"}
        )
        
        # Execute the iteration
        result = _execute_single_iteration(iteration_id, task_id, gym_id, runner_type, max_wait_time)
        
        # Calculate execution time
        end_time = datetime.now()
        execution_time = int((end_time - start_time).total_seconds())
        
        # Determine unified status based on result analysis
        error_message = None
        verification_details = None
        
        # For OpenAI CUA runner, result is now the task result directly
        if runner_type == "openai" or runner_type == "openai-advanced":
            task_result = result
        else:
            # For other runners, result is wrapped in a "result" field
            task_result = result.get("result", {})
        
        unified_status = task_result.get("status", "failed")
        verification_details = task_result.get("verification_details")
        
        # Check if this is a timeout first
        if unified_status == "timeout":
            final_status = IterationStatus.TIMEOUT
            error_message = task_result.get("error")
            logger.info(f"Iteration {iteration_id} timed out: {error_message}")
        elif result.get("error") and unified_status != "timeout":
            # Runner encountered an error during execution (but not timeout)
            final_status = IterationStatus.CRASHED
            error_message = result.get("error")
            logger.info(f"Iteration {iteration_id} crashed with error: {error_message}")
        else:
            # Runner completed successfully, process the status
            
            logger.info(f"🔍 Debug - runner_type: {runner_type}")
            logger.info(f"🔍 Debug - unified_status: {unified_status}")
            logger.info(f"🔍 Debug - verification_details present: {verification_details is not None}")
            if verification_details:
                logger.info(f"🔍 Debug - verification_status: {verification_details.get('verification_status', 'N/A')}")
            
            logger.info(f"Iteration {iteration_id} unified status: {unified_status}")
            
            # Map unified status to iteration status
            if unified_status == "passed":
                final_status = IterationStatus.PASSED
                logger.info(f"Iteration {iteration_id} passed")
            elif unified_status == "failed":
                final_status = IterationStatus.FAILED
                logger.info(f"Iteration {iteration_id} failed")
            elif unified_status == "crashed":
                final_status = IterationStatus.CRASHED
                logger.info(f"Iteration {iteration_id} crashed")
            else:
                # Default case - if we can't determine, mark as failed
                final_status = IterationStatus.FAILED
                logger.warning(f"Iteration {iteration_id} status unclear - unified_status: {unified_status}, defaulting to failed")
        
        # Extract run_id from task result
        run_id = task_result.get("run_id")
        
        # Extract eval_insights from task result
        eval_insights = task_result.get("eval_insights", "")
        
        # Extract total_steps from result (could be in result or task_result)
        total_steps = result.get("total_steps") or task_result.get("total_steps")
        
        # Update iteration with results and execution status in a single transaction
        logger.info(f"🔄 About to call _update_iteration_and_execution_status for iteration {iteration_id}")
        logger.info(f"🆔 Extracted run_id from result: {run_id}")
        logger.info(f"📊 Extracted eval_insights: {len(eval_insights)} characters")
        try:
            _update_iteration_and_execution_status(
                iteration_id,
                final_status,
                completed_at=end_time,
                execution_time_seconds=execution_time,
                error_message=error_message,
                verification_details=json.dumps(verification_details) if verification_details else None,
                eval_insights=eval_insights,
                total_steps=total_steps
            )
            logger.info(f"✅ Successfully called _update_iteration_and_execution_status for iteration {iteration_id}")
        except Exception as e:
            logger.error(f"❌ Error calling _update_iteration_and_execution_status: {e}")
            logger.error(f"❌ Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
        
        # Update final state
        self.update_state(
            state="SUCCESS",
            meta={"current": 100, "total": 100, "status": "Iteration completed", "result": result}
        )
        
        logger.info(f"✅ Completed iteration execution: {iteration_id} in {execution_time}s with status {final_status.value}")
        logger.info(f"📊 Final iteration status: {final_status.value} (error_message: {error_message})")
        return result
        
    except SoftTimeLimitExceeded as e:
        logger.warning(f"⏰ Iteration {iteration_id} timed out: {e}")
        
        # Calculate execution time up to timeout
        end_time = datetime.now()
        execution_time = int((end_time - start_time).total_seconds())
        
        # Update iteration status to timeout
        _update_iteration_and_execution_status(
            iteration_id,
            IterationStatus.TIMEOUT,
            completed_at=end_time,
            execution_time_seconds=execution_time,
            error_message=f"Task timed out: {str(e)}"
        )
        
        self.update_state(
            state="FAILURE",
            meta={"current": 0, "total": 100, "status": f"Iteration timed out: {str(e)}"}
        )
        
        logger.info(f"⏰ Iteration {iteration_id} marked as timeout after {execution_time}s")
        raise
        
    except Exception as e:
        logger.error(f"Iteration execution failed: {e}")
        
        # Update iteration status to crashed
        _update_iteration_and_execution_status(
            iteration_id,
            IterationStatus.CRASHED,
            completed_at=datetime.now(),
            error_message=str(e)
        )
        
        self.update_state(
            state="FAILURE",
            meta={"current": 0, "total": 100, "status": f"Iteration failed: {str(e)}"}
        )
        raise
