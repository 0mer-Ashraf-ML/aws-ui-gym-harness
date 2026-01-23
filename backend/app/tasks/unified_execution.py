#!/usr/bin/env python3
"""
Integration Layer - Connects new unified task runner with existing backend/frontend
Handles async processes, centralized tracking, and proper status management
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from celery import current_app
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
from app.services.task_runners.task_verification import TaskVerification
from app.schemas.iteration import IterationStatus
from app.schemas.execution import ExecutionStatus


class UnifiedTaskIntegration:
    """
    Integration layer that connects the new unified task runner with existing backend/frontend
    Handles async processes, centralized tracking, and proper status management
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.task_verification = TaskVerification(self.logger)
        
    def execute_iteration_sync(
        self, 
        iteration_id: str, 
        task_id: str, 
        gym_id: str = None,  # None for playground executions
        runner_type: str = None, 
        max_wait_time: int = None,
        prompt: str = None
    ) -> Dict[str, Any]:
        """
        Execute a single iteration synchronously using the unified task runner
        This is the preferred method for Celery tasks to avoid event loop conflicts
        
        Args:
            iteration_id: Iteration UUID
            task_id: Task identifier string (from execution snapshot)
            gym_id: Gym UUID (None for playground executions)
            runner_type: Model type (anthropic, openai, etc.)
            max_wait_time: Maximum wait time for execution
            prompt: Task prompt (from execution snapshot) - optional, will query if not provided
            
        Returns:
            Execution result dictionary
        """
        self.logger.info(f"🚀 Starting sync iteration execution: {iteration_id}")
        
        try:
            # Get execution data to check if it's a playground execution
            execution_data = self._get_execution_data_from_iteration(iteration_id)
            is_playground = execution_data and execution_data.get('execution_type') == 'playground'
            
            if is_playground:
                self.logger.info(f"🎮 Playground execution detected for iteration {iteration_id}")
                # For playground: use playground_url instead of gym
                playground_url = execution_data.get('playground_url')
                if not playground_url:
                    raise ValueError(f"Playground URL not found for execution {execution_data.get('execution_id')}")
                
                # Get execution snapshot configs (grader_config and simulator_config) from iteration
                execution_snapshot_configs = self._get_execution_snapshot_configs_from_iteration(iteration_id)
                
                # Create task data for playground (no gym, no verification)
                task_data = {
                    'task_id': task_id,
                    'task_description': prompt or execution_data.get('prompt', ''),
                    'base_url': playground_url,
                    'playground_url': playground_url,  # Store for reference
                    'gym_url': playground_url,
                    'task_link': playground_url,
                    'verification_strategy': 'verification_endpoint',  # Dummy, won't be used
                    'grader_config': execution_snapshot_configs.get('grader_config') if execution_snapshot_configs else None,
                    'simulator_config': execution_snapshot_configs.get('simulator_config') if execution_snapshot_configs else None,
                    'is_playground': True,  # Flag to skip verification
                }
                self.logger.info(f"✅ Created playground task data with URL: {playground_url}")
            else:
                # Batch execution - use existing logic
                # Use task data from execution snapshot if provided, otherwise fallback to database
                # Note: Check for 'is not None' because prompt could be empty string
                if prompt is not None:
                    self.logger.info(f"🔍 DEBUG: Using task data from execution snapshot for task {task_id}")
                    # Get gym data (base_url and verification_strategy needed for execution)
                    if not gym_id:
                        raise ValueError("gym_id is required for batch executions")
                    gym_data = self._get_gym_data_from_db(gym_id)
                    if not gym_data:
                        raise ValueError(f"Gym {gym_id} not found in database")
                    
                    # Get execution snapshot configs (grader_config and simulator_config) from iteration
                    execution_snapshot_configs = self._get_execution_snapshot_configs_from_iteration(iteration_id)
                    if execution_snapshot_configs:
                        self.logger.info(f"✅ Loaded grader_config and simulator_config from execution snapshot")
                    
                    # Load task data with execution snapshot configs (preferred over task table)
                    task_data = self._get_task_data_from_db(task_id, gym_id, execution_snapshot_configs)
                    if not task_data:
                        raise ValueError(f"Task {task_id} not found in database")
                    
                    # Override with execution snapshot data where provided
                    task_data.update({
                        'task_description': prompt,  # Use prompt from execution snapshot
                        'base_url': gym_data['base_url'],  # Use gym data
                        'verification_strategy': gym_data['verification_strategy'],
                        'task_link': gym_data['base_url'],
                        'gym_url': gym_data['base_url'],
                        'is_playground': False,  # Flag for batch execution
                    })
                    # Note: grader_config and simulator_config already use execution snapshot priority in _get_task_data_from_db
                else:
                    # Fallback: Get full task data from database (legacy support)
                    self.logger.info(f"🔍 DEBUG: Getting task data from database for task {task_id}")
                    if not gym_id:
                        raise ValueError("gym_id is required for batch executions")
                    task_data = self._get_task_data_from_db(task_id, gym_id)
                    if not task_data:
                        raise ValueError(f"Task {task_id} not found in database")
                    task_data['is_playground'] = False
            self.logger.info(f"🔍 DEBUG: Task data retrieved successfully")
            
            # Get execution folder name from database
            self.logger.info(f"🔍 DEBUG: Getting execution folder name for iteration {iteration_id}")
            execution_folder_name = self._get_execution_folder_name_from_iteration(iteration_id)
            self.logger.info(f"🔍 DEBUG: Execution folder name: {execution_folder_name}")
            
            # Get iteration number from database
            self.logger.info(f"🔍 DEBUG: Getting iteration number for iteration {iteration_id}")
            iteration_number = self._get_iteration_number_from_db(iteration_id)
            self.logger.info(f"🔍 DEBUG: Iteration number: {iteration_number}")
            
            # Get execution_id from database for token tracking
            self.logger.info(f"🔍 DEBUG: Getting execution_id for iteration {iteration_id}")
            execution_id = self._get_execution_id_from_iteration(iteration_id)
            self.logger.info(f"🔍 DEBUG: execution_id: {execution_id}")
            
            # Add iteration-specific data
            task_data.update({
                'iteration_id': iteration_id,
                'iteration': iteration_number,
                'model_type': runner_type,
                'max_wait_time': max_wait_time or settings.UNIFIED_RUNNER_TIMEOUT,
                'runner_type': runner_type,
                'execution_folder_name': execution_folder_name
            })
            self.logger.info(f"🔍 DEBUG: Task data updated with iteration info")
            
            # Create a FRESH unified task runner instance for each iteration to ensure isolation
            self.logger.info(f"🔍 DEBUG: Creating UnifiedTaskRunner instance")
            runner = UnifiedTaskRunner()  # Each iteration gets its own isolated runner instance
            self.logger.info(f"🔍 DEBUG: UnifiedTaskRunner instance created")
            
            # Execute the task synchronously (no async/await needed)
            self.logger.info(f"🔍 DEBUG: About to call runner.execute_single_iteration_from_db")
            self.logger.info(f"🔍 DEBUG: Task data keys: {list(task_data.keys())}")
            self.logger.info(f"🔍 DEBUG: Iteration number: {iteration_number}")
            self.logger.info(f"🔍 DEBUG: Max wait time: {max_wait_time}")
            self.logger.info(f"🔍 DEBUG: Execution folder name: {execution_folder_name}")
            self.logger.info(f"🔍 DEBUG: iteration_id: {iteration_id}, execution_id: {execution_id}")
            
            try:
                # Add timeout protection to prevent hanging
                import signal
                import time
                
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Runner execution timed out after {max_wait_time or settings.UNIFIED_RUNNER_TIMEOUT} seconds")
                
                # Set up timeout signal (only works on Unix systems)
                if hasattr(signal, 'SIGALRM'):
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(max_wait_time or settings.UNIFIED_RUNNER_TIMEOUT)
                
                self.logger.info(f"🔍 DEBUG: Starting runner execution with timeout protection")
                start_time = time.time()
                
                result = runner.execute_single_iteration_from_db(
                    task_data=task_data,
                    iteration_number=iteration_number,
                    max_wait_time=max_wait_time,
                    execution_folder_name=execution_folder_name,
                    iteration_id=iteration_id,
                    execution_id=execution_id
                )
                
                execution_time = time.time() - start_time
                self.logger.info(f"🔍 DEBUG: runner.execute_single_iteration_from_db completed successfully in {execution_time:.2f}s")
                self.logger.info(f"🔍 DEBUG: Result type: {type(result)}")
                self.logger.info(f"🔍 DEBUG: Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                
                # Cancel timeout
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                    
            except TimeoutError as timeout_error:
                self.logger.error(f"❌ CRITICAL: Runner execution timed out: {timeout_error}")
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                raise
            except Exception as runner_error:
                self.logger.error(f"❌ CRITICAL: runner.execute_single_iteration_from_db failed: {runner_error}")
                self.logger.error(f"❌ CRITICAL: Runner error type: {type(runner_error)}")
                self.logger.error(f"❌ CRITICAL: Runner error details: {str(runner_error)}")
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                raise
            
            # Add iteration-specific metadata
            result['iteration_id'] = iteration_id
            result['gym_id'] = gym_id if not is_playground else None
            result['runner_type'] = runner_type
            result['is_playground'] = is_playground
            self.logger.info(f"🔍 DEBUG: Added iteration metadata to result (is_playground={is_playground})")
            
            self.logger.info(f"✅ Sync iteration execution completed: {iteration_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Sync iteration execution failed: {iteration_id} - {e}")
            return self._create_error_result(iteration_id, task_id, gym_id, runner_type, str(e))
        
    async def execute_iteration_async(
        self, 
        iteration_id: str, 
        task_id: str, 
        gym_id: str, 
        runner_type: str, 
        max_wait_time: int = None
    ) -> Dict[str, Any]:
        """
        Execute a single iteration asynchronously using the unified task runner
        
        Args:
            iteration_id: Iteration UUID
            task_id: Task UUID
            gym_id: Gym UUID
            runner_type: Model type (anthropic, openai, etc.)
            max_wait_time: Maximum wait time for execution
            
        Returns:
            Execution result dictionary
        """
        self.logger.info(f"🚀 Starting async iteration execution: {iteration_id}")
        
        try:
            # Get full task data from database
            task_data = self._get_task_data_from_db(task_id, gym_id)
            if not task_data:
                raise ValueError(f"Task {task_id} not found in database")
            
            # Get execution folder name from database
            execution_folder_name = self._get_execution_folder_name_from_iteration(iteration_id)
            
            # Get iteration number from database
            iteration_number = self._get_iteration_number_from_db(iteration_id)
            
            # Add iteration-specific data
            task_data.update({
                'iteration_id': iteration_id,
                'iteration': iteration_number,
                'model_type': runner_type,
                'max_wait_time': max_wait_time or settings.UNIFIED_RUNNER_TIMEOUT,
                'runner_type': runner_type,
                'execution_folder_name': execution_folder_name
            })
            
            # Create a FRESH unified task runner instance for each iteration to ensure isolation
            runner = UnifiedTaskRunner()  # Each iteration gets its own isolated runner instance
            
            # Execute the task asynchronously
            result = await self._execute_task_with_timeout(runner, task_data, max_wait_time)
            
            # Add iteration-specific metadata
            result['iteration_id'] = iteration_id
            result['gym_id'] = gym_id
            result['runner_type'] = runner_type
            
            self.logger.info(f"✅ Async iteration execution completed: {iteration_id}")
            return result
            
        except asyncio.TimeoutError:
            self.logger.error(f"⏰ Async iteration execution timed out: {iteration_id}")
            return self._create_timeout_result(iteration_id, task_id, gym_id, runner_type)
        except Exception as e:
            self.logger.error(f"❌ Async iteration execution failed: {iteration_id} - {e}")
            return self._create_error_result(iteration_id, task_id, gym_id, runner_type, str(e))
    
    async def _execute_task_with_timeout(
        self, 
        runner: UnifiedTaskRunner, 
        task_data: Dict[str, Any], 
        max_wait_time: int
    ) -> Dict[str, Any]:
        """
        Execute task with proper timeout handling
        
        Args:
            runner: UnifiedTaskRunner instance
            task_data: Task data
            max_wait_time: Maximum wait time
            
        Returns:
            Execution result
        """
        try:
            # Use asyncio.wait_for for proper timeout handling
            result = await asyncio.wait_for(
                self._run_task_sync(runner, task_data),
                timeout=max_wait_time
            )
            return result
        except asyncio.TimeoutError:
            self.logger.warning(f"⏰ Task execution timed out after {max_wait_time} seconds")
            raise
        except Exception as e:
            self.logger.error(f"❌ Task execution failed: {e}")
            raise
    
    async def _run_task_sync(self, runner: UnifiedTaskRunner, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run synchronous task in async context
        
        Args:
            runner: UnifiedTaskRunner instance
            task_data: Task data
            
        Returns:
            Execution result
        """
        # Extract execution folder name and iteration number from task data
        execution_folder_name = task_data.get('execution_folder_name')
        iteration_number = task_data.get('iteration', 1)
        max_wait_time = task_data.get('max_wait_time', settings.UNIFIED_RUNNER_TIMEOUT)
        
        # Use the correct method that accepts execution folder name
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            runner.execute_single_iteration_from_db, 
            task_data,
            iteration_number,
            max_wait_time,
            execution_folder_name
        )
        return result
    
    def _create_timeout_result(
        self, 
        iteration_id: str, 
        task_id: str, 
        gym_id: str, 
        runner_type: str
    ) -> Dict[str, Any]:
        """Create timeout result dictionary"""
        return {
            'iteration_id': iteration_id,
            'task_id': task_id,
            'gym_id': gym_id,
            'runner_type': runner_type,
            'status': 'timeout',
            'error': 'Task execution timed out',
            'execution_time': 0,
            'response': None,
            'verification_results': {},
            'timestamp': datetime.now().isoformat(),
            'agent_type': 'UnifiedTaskRunner'
        }
    
    def _create_error_result(
        self, 
        iteration_id: str, 
        task_id: str, 
        gym_id: str, 
        runner_type: str, 
        error_message: str
    ) -> Dict[str, Any]:
        """Create error result dictionary"""
        return {
            'iteration_id': iteration_id,
            'task_id': task_id,
            'gym_id': gym_id,
            'runner_type': runner_type,
            'status': 'crashed',
            'error': error_message,
            'execution_time': 0,
            'response': None,
            'verification_results': {},
            'timestamp': datetime.now().isoformat(),
            'agent_type': 'UnifiedTaskRunner'
        }
    
    def _get_task_data_from_db(self, task_id: str, gym_id: str, execution_snapshot_configs: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Get task data from database using synchronous operations with proper session cleanup"""
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            from app.core.config import settings
            from app.core.config_loader import load_configs_from_files
            
            # Load configs from files if feature flag is enabled
            file_configs = {}
            if settings.USE_CONFIG_FILES:
                file_configs = load_configs_from_files(task_id)
            
            # Use context manager to ensure session is always closed
            with get_db_session() as db:
                # Get task from database using raw SQL with gym join for complete data
                # Note: task_id parameter is a string identifier (task_id column), not UUID
                query = """
                    SELECT t.uuid, t.task_id, t.gym_id, t.prompt, t.grader_config, t.simulator_config, t.verifier_path,
                           g.base_url, g.verification_strategy
                    FROM tasks t
                    LEFT JOIN gyms g ON t.gym_id = g.uuid
                    WHERE t.task_id = :task_id AND t.gym_id = :gym_id
                """
                result = db.execute(text(query), {"task_id": task_id, "gym_id": gym_id})
                row = result.fetchone()
                
                if not row:
                    self.logger.error(f"❌ Task {task_id} not found in database")
                    return None
                
                # Ensure verification_strategy is the string value, not the enum name
                verification_strategy = row.verification_strategy if row.verification_strategy else 'verification_endpoint'
                if hasattr(verification_strategy, 'value'):
                    verification_strategy = verification_strategy.value
                
                # Convert to dictionary
                # Priority: File configs > Execution snapshot > Task table
                # Use file configs if available, otherwise execution snapshot, then task table
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
                
                task_data = {
                    'task_id': row.task_id,
                    'task_description': row.prompt,  # Use 'prompt' instead of 'task_description'
                    'grader_config': grader_config,  # Include grader_config (from file or DB)
                    'simulator_config': simulator_config,  # Include simulator_config (from file or DB)
                    'verifier_path': row.verifier_path,  # Include verifier_path for verifier_api_script strategy
                    'gym_id': str(row.gym_id) if row.gym_id else gym_id,
                    'gym_url': row.base_url if row.base_url else None,
                    'base_url': row.base_url if row.base_url else None,
                    'verification_strategy': verification_strategy,
                    'task_link': row.base_url if row.base_url else None
                }
                
                if settings.USE_CONFIG_FILES and (file_configs.get('grader_config') or file_configs.get('simulator_config')):
                    self.logger.info(f"✅ Loaded configs from files for task: {task_id}")
                
                self.logger.info(f"✅ Retrieved task data from database: {task_id}")
                return task_data
                
        except Exception as e:
            self.logger.error(f"❌ Error getting task data from database: {e}")
            raise RuntimeError(f"CRITICAL DATABASE ERROR: {e}") from e
    
    def _get_gym_data_from_db(self, gym_id: str) -> Optional[Dict[str, Any]]:
        """Get gym data (base_url and verification_strategy) from database with proper session cleanup"""
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            
            # Use context manager to ensure session is always closed
            with get_db_session() as db:
                query = """
                    SELECT uuid, base_url, verification_strategy
                    FROM gyms
                    WHERE uuid = :gym_id
                """
                result = db.execute(text(query), {"gym_id": gym_id})
                row = result.fetchone()
                
                if not row:
                    self.logger.error(f"❌ Gym {gym_id} not found in database")
                    return None
                
                # Ensure verification_strategy is the string value, not the enum name
                verification_strategy = row.verification_strategy
                if hasattr(verification_strategy, 'value'):
                    verification_strategy = verification_strategy.value
                
                gym_data = {
                    'gym_id': str(row.uuid),
                    'base_url': row.base_url,
                    'verification_strategy': verification_strategy
                }
                
            self.logger.info(f"✅ Retrieved gym data from database: {gym_id}")
            return gym_data
                
        except Exception as e:
            self.logger.error(f"❌ Error getting gym data from database: {e}")
            return None
    
    def _get_execution_folder_name_from_iteration(self, iteration_id: str) -> str:
        """Get execution folder name from iteration with proper session cleanup"""
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            
            # Use context manager to ensure session is always closed
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
                    self.logger.info(f"Using stored execution folder name: {row.execution_folder_name}")
                    return row.execution_folder_name
                else:
                    # NO FALLBACK - This should never happen for batch executions
                    error_msg = f"❌ CRITICAL ERROR: No execution folder name found for iteration {iteration_id}. This indicates a database integrity issue."
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)
                
        except Exception as e:
            error_msg = f"❌ CRITICAL ERROR: Failed to get execution folder name for iteration {iteration_id}: {e}"
            self.logger.error(error_msg)
            raise RuntimeError(f"CRITICAL DATABASE ERROR: {e}") from e
    
    def _get_iteration_number_from_db(self, iteration_id: str) -> int:
        """Get iteration number from database with proper session cleanup"""
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            
            with get_db_session() as db:
                query = """
                    SELECT iteration_number
                    FROM iterations
                    WHERE uuid = :iteration_id
                """
                result = db.execute(text(query), {"iteration_id": iteration_id})
                row = result.fetchone()
                
                if row:
                    self.logger.info(f"Found iteration number: {row.iteration_number}")
                    return row.iteration_number
                else:
                    self.logger.warning(f"Iteration {iteration_id} not found, using default iteration number 1")
                    return 1
                    
        except Exception as e:
            self.logger.error(f"Error getting iteration number: {e}")
            self.logger.warning("Using default iteration number 1")
            return 1
    
    def _get_execution_id_from_iteration(self, iteration_id: str) -> Optional[str]:
        """Get execution_id from iteration_id using synchronous operations"""
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
                    self.logger.info(f"Found execution_id: {row.execution_id}")
                    return str(row.execution_id)
                else:
                    self.logger.warning(f"Execution not found for iteration {iteration_id}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting execution_id: {e}")
            return None
    
    def _get_execution_data_from_iteration(self, iteration_id: str) -> Optional[Dict[str, Any]]:
        """Get execution data (including execution_type and playground_url) from iteration_id"""
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            
            with get_db_session() as db:
                query = """
                    SELECT e.uuid as execution_id, e.execution_type, e.playground_url, e.prompt, e.gym_id
                    FROM executions e
                    JOIN iterations i ON e.uuid = i.execution_id
                    WHERE i.uuid = :iteration_id
                """
                result = db.execute(text(query), {"iteration_id": iteration_id})
                row = result.fetchone()
                
                if row:
                    execution_type = row.execution_type
                    if hasattr(execution_type, 'value'):
                        execution_type = execution_type.value
                    return {
                        'execution_id': str(row.execution_id),
                        'execution_type': execution_type,
                        'playground_url': row.playground_url,
                        'prompt': row.prompt,
                        'gym_id': str(row.gym_id) if row.gym_id else None
                    }
                else:
                    self.logger.warning(f"Execution data not found for iteration {iteration_id}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting execution data: {e}")
            return None
    
    def _get_execution_snapshot_configs_from_iteration(self, iteration_id: str) -> Optional[Dict[str, Any]]:
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
                    self.logger.warning(f"Execution snapshot configs not found for iteration {iteration_id}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error getting execution snapshot configs: {e}")
            return None

    def reset_iteration_for_rerun(self, iteration_id: str) -> bool:
        """
        Reset iteration database record for rerun
        
        Args:
            iteration_id: UUID of the iteration to reset
            
        Returns:
            bool: True if reset was successful, False otherwise
        """
        try:
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            from app.schemas.iteration import IterationStatus
            
            with get_db_session() as db:
                # Reset iteration to pending status and clear all execution data
                # IMPORTANT: Only reset iterations in terminal failed states (crashed, failed, timeout)
                # to prevent re-dispatching iterations that are already executing or pending
                query = """
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
                    AND status IN ('crashed', 'failed', 'timeout')
                """

                try:
                    result = db.execute(text(query), {
                        "status": IterationStatus.PENDING.value,
                        "iteration_id": iteration_id
                    })
                    # Explicitly commit the transaction so the status reset persists
                    db.commit()

                    if result.rowcount > 0:
                        self.logger.info(f"✅ Successfully reset iteration {iteration_id} for rerun")
                        return True
                    else:
                        self.logger.warning(f"⚠️ No iteration found with ID {iteration_id} or iteration is not in crashed/failed/timeout state (may be executing or pending)")
                        return False
                except Exception as commit_error:
                    # Rollback and re-raise to be caught by outer except
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    raise commit_error
                    
        except Exception as e:
            self.logger.error(f"❌ Error resetting iteration {iteration_id} for rerun: {e}")
            return False


# Global integration instance
unified_integration = UnifiedTaskIntegration()


# Note: Removed complex batched execution - using simple one task per iteration approach
# This leverages Celery's natural worker distribution (100 workers in production, 5 locally)


@current_app.task(bind=True, name="app.tasks.unified_execution.execute_single_iteration_unified")
def execute_single_iteration_unified(
    self, 
    iteration_id: str, 
    task_id: str, 
    gym_id: str = None,  # None for playground executions
    runner_type: str = None, 
    max_wait_time: int = None,
    prompt: str = None
):
    """
    Celery task wrapper for unified iteration execution with asyncio cleanup
    This replaces the old execute_single_iteration task
    Note: task_id is now task_identifier (string), and prompt comes from execution snapshot
    """
    logger = logging.getLogger(__name__)
    
    # Log IMMEDIATELY at the very start, before ANY operations
    logger.info(f"🔵🔵🔵 TASK START: {iteration_id} for task {task_id} with {runner_type}")
    logger.info(f"🔵 DEBUG: iteration_id={iteration_id}, task_id={task_id}, gym_id={gym_id}, runner_type={runner_type}, prompt={prompt}")
    
    # Call the actual implementation
    return _execute_single_iteration_unified_impl(self, iteration_id, task_id, gym_id, runner_type, max_wait_time, prompt)


def _execute_single_iteration_unified_impl(
    self, 
    iteration_id: str, 
    task_id: str, 
    gym_id: str = None,  # None for playground executions
    runner_type: str = None, 
    max_wait_time: int = None,
    prompt: str = None
):
    """Actual implementation without asyncio cleanup (handled in wrapper)"""
    logger = logging.getLogger(__name__)
    start_time = datetime.now()
    
    # Initialize file_handler outside try block so it's accessible in finally
    file_handler = None
    
    try:
        logger.info(f"🚀 Starting unified iteration execution: {iteration_id} for task {task_id} with {runner_type}")
        
        # CRITICAL: Check if iteration was terminated before starting execution
        # This prevents re-execution of iterations that were marked as crashed during batch termination
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        with get_db_session() as db:
            check_query = "SELECT status FROM iterations WHERE uuid = :iteration_id"
            result = db.execute(text(check_query), {"iteration_id": iteration_id})
            current_status = result.scalar()
            
            logger.info(f"🔍 Pre-execution status check for iteration {iteration_id}: current_status = '{current_status}'")
            
            # CRITICAL SAFETY CHECK: If iteration doesn't exist in database, skip execution
            if current_status is None:
                logger.error(f"❌ CRITICAL: Iteration {iteration_id} not found in database - this is a stale queue entry from a previous batch")
                logger.error(f"❌ Skipping execution to prevent crashes. This task should be removed from the queue.")
                return {
                    "status": "skipped",
                    "reason": f"Iteration {iteration_id} not found in database (stale queue entry)",
                    "iteration_id": iteration_id,
                    "task_id": task_id,
                    "error": "STALE_QUEUE_ENTRY"
                }
            
            if current_status in ['crashed', 'timeout', 'passed', 'failed', 'executing']:
                logger.warning(
                    f"⚠️ SKIPPING: Iteration {iteration_id} is already in state '{current_status}', "
                    f"will not execute again to avoid duplicate runs"
                )
                return {
                    "status": "skipped",
                    "reason": f"Iteration already in state: {current_status}",
                    "iteration_id": iteration_id
                }
            
            logger.info(f"✅ Iteration {iteration_id} status '{current_status}' is not terminal, proceeding with execution")
        
        # Update iteration status to executing
        from app.tasks.iteration_execution import _update_iteration_and_execution_status
        try:
            _update_iteration_and_execution_status(
                iteration_id, 
                IterationStatus.EXECUTING,
                started_at=start_time,
                celery_task_id=self.request.id
            )
            logger.info(f"✅ Successfully updated iteration status to EXECUTING")
        except Exception as db_error:
            logger.error(f"❌ CRITICAL: Failed to update iteration status to EXECUTING: {db_error}")
            logger.error(f"❌ This is likely a database connection issue. Task will crash immediately.")
            logger.error(f"❌ Database error type: {type(db_error).__name__}")
            import traceback
            logger.error(f"❌ Database error traceback: {traceback.format_exc()}")
            # Re-raise to crash the task immediately with proper error info
            raise Exception(f"Database connection failed during task registration: {str(db_error)}")
        
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "Starting unified iteration execution"}
        )
        
        # Execute the iteration using unified integration - Use sync method to avoid asyncio conflicts in Celery
        logger.info(f"🔍 DEBUG: About to call execute_iteration_sync for iteration {iteration_id}")
        logger.info(f"🔍 DEBUG: Parameters - task_id: {task_id}, gym_id: {gym_id}, runner_type: {runner_type}, max_wait_time: {max_wait_time}")
        
        try:
            result = unified_integration.execute_iteration_sync(
                iteration_id=iteration_id,
                task_id=task_id,
                gym_id=gym_id,
                runner_type=runner_type,
                max_wait_time=max_wait_time,
                prompt=prompt
            )
            logger.info(f"🔍 DEBUG: execute_iteration_sync completed for iteration {iteration_id}, result keys: {list(result.keys()) if result else 'None'}")
        except Exception as sync_error:
            logger.error(f"❌ CRITICAL: execute_iteration_sync failed for iteration {iteration_id}: {sync_error}")
            logger.error(f"❌ CRITICAL: Error type: {type(sync_error)}")
            logger.error(f"❌ CRITICAL: Error details: {str(sync_error)}")
            raise
        
        # TEMPORARY DEBUG: Extract and use the runner's logger for post-execution logging
        runner_logger = result.get('_debug_logger')
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Starting post-execution logging in Celery task")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Result keys: {list(result.keys())}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Task ID: {task_id}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Iteration ID: {iteration_id}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Runner type: {runner_type}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Result status: {result.get('status', 'unknown')}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Execution time from result: {result.get('execution_time', 'unknown')}")
            verification_results_temp = result.get('verification_results') or {}
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Verification results keys: {list(verification_results_temp.keys()) if isinstance(verification_results_temp, dict) else 'None'}")
        else:
            logger.warning("⚠️ No runner logger found in result for post-execution debugging")
        
        # Calculate execution time
        end_time = datetime.now()
        execution_time = int((end_time - start_time).total_seconds())
        
        # TEMPORARY DEBUG: Log execution time comparison
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Celery task execution time: {execution_time}s")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Runner reported execution time: {result.get('execution_time', 'unknown')}s")
        
        # Determine unified status based on result analysis
        unified_status = result.get("status", "crashed")
        # Handle case where verification_results might be None instead of empty dict
        verification_details = result.get("verification_results") or {}
        
        # TEMPORARY DEBUG: Log status determination
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Determined unified status: {unified_status}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Verification details type: {type(verification_details)}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Verification details keys: {list(verification_details.keys()) if isinstance(verification_details, dict) else 'Not a dict'}")
        
        # Map unified status to iteration status
        if unified_status == "passed":
            iteration_status = IterationStatus.PASSED
        elif unified_status == "failed":
            iteration_status = IterationStatus.FAILED
        elif unified_status == "timeout":
            iteration_status = IterationStatus.TIMEOUT
        else:  # crashed or unknown
            iteration_status = IterationStatus.CRASHED
        
        # TEMPORARY DEBUG: Log status mapping
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Mapped unified status '{unified_status}' to iteration status '{iteration_status}'")
        
        # Extract verification_comments from verification_details
        verification_comments = None
        if verification_details and isinstance(verification_details, dict):
            verification_comments = verification_details.get('verification_comments', '')
        
        # Extract last_model_response from task result
        last_model_response = result.get('last_model_response', '')
        
        # Extract eval_insights from task result
        eval_insights = result.get('eval_insights', '')
        
        # DEBUG: Log the model response being saved
        # if runner_logger:
        #     runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Extracted last_model_response: '{last_model_response[:100]}...' (length: {len(last_model_response)})")
        #     runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Extracted eval_insights: '{eval_insights[:100]}...' (length: {len(eval_insights)})")
        
        # Update iteration and execution status
        _update_iteration_and_execution_status(
            iteration_id,
            iteration_status,
            completed_at=end_time,
            execution_time_seconds=execution_time,
            verification_details=json.dumps(verification_details) if verification_details else None,
            verification_comments=verification_comments,
            last_model_response=last_model_response,
            total_steps=result.get("total_steps"),
            # eval_insights=eval_insights
        )
        
        # Generate execution and batch summaries after iteration completes
        try:
            from app.services.task_runners.insights.summary_service import summary_service
            
            # Get execution_id from iteration_id
            execution_id = unified_integration._get_execution_id_from_iteration(iteration_id)
            if execution_id:
                logger.info(f"🔄 Triggering summary generation for execution {execution_id}")
                summary_success = summary_service.generate_summaries_after_iteration(execution_id)
                if summary_success:
                    logger.info(f"✅ Summary generation completed for execution {execution_id}")
                else:
                    logger.warning(f"⚠️ Summary generation failed for execution {execution_id}")
            else:
                logger.warning(f"⚠️ Could not find execution_id for iteration {iteration_id}")
        except Exception as summary_error:
            # Don't let summary generation failures crash the main task
            logger.warning(f"⚠️ Summary generation failed (non-critical): {summary_error}")
        
        # TEMPORARY DEBUG: Log database update completion
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Database status update completed for iteration {iteration_id}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Updated status to: {iteration_status}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Execution time recorded: {execution_time}s")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Verification details JSON length: {len(json.dumps(verification_details) if verification_details else '{}')}")
        
        # Update task state
        self.update_state(
            state="SUCCESS",
            meta={
                "current": 100,
                "total": 100,
                "status": f"Unified iteration execution completed with status: {unified_status}",
                "execution_time": execution_time,
                "unified_status": unified_status
            }
        )
        
        # TEMPORARY DEBUG: Log final task state update
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Celery task state updated to SUCCESS")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Task meta includes execution_time: {execution_time}s")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Task meta includes unified_status: {unified_status}")
        
        logger.info(f"✅ Unified iteration execution completed: {iteration_id} with status: {unified_status}")
        
        # TEMPORARY DEBUG: Log final return
        if runner_logger:
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: About to return result to Celery")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Final result status: {result.get('status', 'unknown')}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Final result keys: {list(result.keys())}")
            runner_logger.info(f"🔍 POST-EXECUTION DEBUG: Post-execution logging completed")
        
        # Remove the debug logger from the result before returning (clean up)
        if '_debug_logger' in result:
            del result['_debug_logger']
        
        return result
        
    except SoftTimeLimitExceeded:
        logger.error(f"⏰ Unified iteration execution timed out: {iteration_id}")
        
        # Update status to timeout
        _update_iteration_and_execution_status(
            iteration_id,
            IterationStatus.TIMEOUT,
            completed_at=datetime.now(),
            execution_time=int((datetime.now() - start_time).total_seconds())
        )
        
        self.update_state(
            state="FAILURE",
            meta={"current": 0, "total": 100, "status": "Unified iteration execution timed out"}
        )
        
        return {
            'iteration_id': iteration_id,
            'task_id': task_id,
            'gym_id': gym_id,
            'runner_type': runner_type,
            'status': 'timeout',
            'error': 'Unified iteration execution timed out',
            'execution_time': int((datetime.now() - start_time).total_seconds()),
            'response': None,
            'verification_results': {},
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        execution_time_for_error = int((datetime.now() - start_time).total_seconds())
        
        # LOG IMMEDIATELY - even if it's an instant failure, we want to know about it
        logger.error(f"❌ Unified iteration execution failed: {iteration_id} - {e}")
        logger.error(f"❌ Error occurred after {execution_time_for_error} seconds")
        
        # CRITICAL: Check if log file was ever created
        # Since we create log file at the start, if it doesn't exist, something went very wrong
        has_log_file = False
        has_execution_dir = False
        execution_dir_path = None
        try:
            from pathlib import Path
            from app.core.config import settings
            results_dir = Path(settings.RESULTS_DIR)
            log_file = results_dir / "logs" / f"iteration_{iteration_id}.log"
            
            if log_file.exists():
                has_log_file = True
                logger.info(f"✅ Iteration log file exists: {log_file}")
            else:
                logger.error(f"🚨 CRITICAL: NO LOG FILE CREATED - This is a CRASH before ANY setup!")
            
            # Check if execution directory was created (batch directory structure)
            # Try to get execution folder name from database to check if directory exists
            try:
                from app.core.database_utils import get_db_session
                from sqlalchemy import text
                with get_db_session() as db:
                    query = """
                        SELECT e.execution_folder_name
                        FROM iterations i
                        JOIN executions e ON i.execution_id = e.uuid
                        WHERE i.uuid = :iteration_id
                    """
                    result = db.execute(text(query), {"iteration_id": iteration_id})
                    row = result.fetchone()
                    if row and row.execution_folder_name:
                        execution_dir_path = results_dir / row.execution_folder_name
                        if execution_dir_path.exists() and execution_dir_path.is_dir():
                            has_execution_dir = True
                            logger.info(f"✅ Execution directory exists: {execution_dir_path}")
                        else:
                            logger.error(f"🚨 CRITICAL: NO EXECUTION DIRECTORY CREATED: {execution_dir_path} - This is a CRASH!")
            except Exception as exec_dir_check_error:
                logger.warning(f"⚠️ Could not check execution directory: {exec_dir_check_error}")
                
        except Exception as dir_check_error:
            logger.warning(f"⚠️ Could not check for log file: {dir_check_error}")
        
        # Detect connection/network errors - these are always crashes
        is_connection_error = (
            "Database connection" in str(e) or
            "get_db_session" in str(e) or
            "connection" in str(e).lower() or
            "Cannot connect" in str(e) or
            "ConnectionRefusedError" in str(type(e).__name__) or
            "OperationalError" in str(type(e).__name__) or
            "timeout" in str(e).lower() and ("connection" in str(e).lower() or "database" in str(e).lower())
        )
        
        # CRITICAL: No log file = CRASH, No execution directory = CRASH, Connection errors = CRASH
        # All exceptions are crashes, but we log specific reasons
        crash_reason = "Unknown system error"
        if not has_log_file:
            crash_reason = "CRASH: No log file created - failure before setup"
            logger.error(f"🚨 {crash_reason}")
        elif execution_dir_path and not has_execution_dir:
            crash_reason = f"CRASH: Execution directory not created - {execution_dir_path} - runner failed before directory creation"
            logger.error(f"🚨 {crash_reason}")
        elif is_connection_error:
            crash_reason = f"CRASH: Connection/Database error - {str(e)}"
            logger.error(f"🚨 {crash_reason}")
        elif execution_time_for_error < 3:
            crash_reason = f"CRASH: Instant failure (<3s) - {str(e)}"
            logger.error(f"🚨 {crash_reason}")
        else:
            crash_reason = f"CRASH: {str(e)}"
        
        # Update status to crashed (always for exceptions)
        _update_iteration_and_execution_status(
            iteration_id,
            IterationStatus.CRASHED,
            completed_at=datetime.now(),
            execution_time=execution_time_for_error,
            error_message=crash_reason
        )
        
        self.update_state(
            state="FAILURE",
            meta={"current": 0, "total": 100, "status": f"Unified iteration execution failed: {str(e)}"}
        )
        
        return {
            'iteration_id': iteration_id,
            'task_id': task_id,
            'gym_id': gym_id,
            'runner_type': runner_type,
            'status': 'crashed',
            'error': str(e),
            'execution_time': execution_time_for_error,
            'response': None,
            'verification_results': {},
            'timestamp': datetime.now().isoformat()
        }
    
    finally:
        # CRITICAL: Always close and remove the file handler to prevent log file leakage
        # This ensures log files stop being written once the task completes
        if file_handler is not None:
            try:
                logger.removeHandler(file_handler)
                file_handler.close()
                logger.debug(f"✅ Closed and removed file handler for iteration {iteration_id}")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Error closing file handler: {cleanup_error}")
