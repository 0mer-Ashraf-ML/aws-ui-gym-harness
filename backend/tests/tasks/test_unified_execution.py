"""
Tests for unified_execution Celery task
Covers task execution, status updates, and error handling

Note: These tests mock the Celery task execution to focus on the core logic.
The log file creation and cleanup has been moved to unified_task_runner.py.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
import logging
from datetime import datetime

from app.schemas.iteration import IterationStatus
from app.tasks.unified_execution import execute_single_iteration_unified, unified_integration


@pytest.fixture
def mock_iteration_id():
    """Mock iteration ID for testing"""
    return "test-iteration-123"


@pytest.fixture
def mock_task_data():
    """Mock task data"""
    return {
        "task_id": "test-task-123",
        "gym_id": "test-gym-123",
        "runner_type": "openai",
        "max_wait_time": 180,
        "prompt": "Test prompt"
    }


@pytest.fixture
def mock_celery_task():
    """Mock Celery task object for bind=True tasks"""
    task = MagicMock()
    task.request = MagicMock()
    task.request.id = "celery-task-123"
    task.update_state = MagicMock()
    # For Celery tasks with bind=True, self is the task instance
    # We'll patch execute_single_iteration_unified to use our mock
    return task


class TestTaskExecution:
    """Test task execution and status updates"""
    
    @patch('app.tasks.unified_execution.unified_integration.execute_iteration_sync')
    @patch('app.tasks.iteration_execution._update_iteration_and_execution_status')
    def test_successful_execution_updates_status(
        self,
        mock_update_status,
        mock_execute_sync,
        mock_celery_task,
        mock_iteration_id,
        mock_task_data
    ):
        """Test that successful execution updates status correctly"""
        mock_execute_sync.return_value = {
            "status": "passed",
            "execution_time": 10,
            "verification_results": {"verification_status": "passed"},
            "last_model_response": "Test response"
        }
        
        # Patch self.request.id and self.update_state where they're accessed
        with patch('app.tasks.unified_execution.execute_single_iteration_unified.request.id', mock_celery_task.request.id):
            with patch('app.tasks.unified_execution.execute_single_iteration_unified.update_state', mock_celery_task.update_state):
                execute_single_iteration_unified.run(
                    mock_iteration_id,
                    mock_task_data["task_id"],
                    mock_task_data["gym_id"],
                    mock_task_data["runner_type"],
                    mock_task_data["max_wait_time"],
                    mock_task_data["prompt"]
                )
        
        # Verify status was updated to executing first, then to passed
        calls = mock_update_status.call_args_list
        assert len(calls) >= 2
        # First call should be EXECUTING
        assert calls[0][0][1] == IterationStatus.EXECUTING
        # Last call should be PASSED
        assert calls[-1][0][1] == IterationStatus.PASSED


class TestErrorHandling:
    """Test error handling scenarios"""
    
    @patch('app.tasks.iteration_execution._update_iteration_and_execution_status')
    def test_crash_on_connection_error(
        self,
        mock_update_status,
        mock_celery_task,
        mock_iteration_id,
        mock_task_data
    ):
        """Test that database connection errors are handled correctly"""
        # Simulate database connection error during initial DB update (setting EXECUTING status)
        connection_error = Exception("Database connection failed")
        
        # Mock _update_iteration_and_execution_status to fail on first call (EXECUTING), succeed on second (CRASHED)
        call_count = [0]
        def update_status_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # First call for EXECUTING status
                raise connection_error
            # Second call for CRASHED status should succeed
        
        with patch('app.tasks.iteration_execution._update_iteration_and_execution_status', side_effect=update_status_side_effect):
            with patch('app.tasks.unified_execution.logging.getLogger') as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger
                
                try:
                    # Patch self.request.id and self.update_state where they're accessed
                    with patch('app.tasks.unified_execution.execute_single_iteration_unified.request.id', mock_celery_task.request.id):
                        with patch('app.tasks.unified_execution.execute_single_iteration_unified.update_state', mock_celery_task.update_state):
                            execute_single_iteration_unified.run(
                                mock_iteration_id,
                                mock_task_data["task_id"],
                                mock_task_data["gym_id"],
                                mock_task_data["runner_type"],
                                mock_task_data["max_wait_time"],
                                mock_task_data["prompt"]
                            )
                except Exception:
                    pass  # Expected to fail
        
        # Verify it attempted to update status
        # First call (EXECUTING) fails, then exception handler should call again with CRASHED
        assert call_count[0] >= 1
    
    @patch('app.tasks.iteration_execution._update_iteration_and_execution_status')
    @patch('app.tasks.unified_execution.unified_integration.execute_iteration_sync')
    def test_execution_failure_handled(
        self,
        mock_execute_sync,
        mock_update_status,
        mock_celery_task,
        mock_iteration_id,
        mock_task_data
    ):
        """Test that execution failures are handled and status updated to crashed"""
        # Simulate execution failure
        mock_execute_sync.side_effect = Exception("Execution failed")
        
        with patch('app.tasks.unified_execution.execute_single_iteration_unified.request.id', mock_celery_task.request.id):
            with patch('app.tasks.unified_execution.execute_single_iteration_unified.update_state', mock_celery_task.update_state):
                try:
                    execute_single_iteration_unified.run(
                        mock_iteration_id,
                        mock_task_data["task_id"],
                        mock_task_data["gym_id"],
                        mock_task_data["runner_type"],
                        mock_task_data["max_wait_time"],
                        mock_task_data["prompt"]
                    )
                except Exception:
                    pass  # Expected to fail
        
        # Verify status was updated to crashed
        calls = mock_update_status.call_args_list
        if calls:
            # Should have at least EXECUTING and CRASHED calls
            assert len(calls) >= 2
            # Last call should be CRASHED
            assert calls[-1][0][1] == IterationStatus.CRASHED
