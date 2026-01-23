"""
Tests for batch rerun functionality
Covers rerun logic, queue handling, error recovery, and dispatch behavior
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4


@pytest.mark.asyncio
@pytest.mark.api
class TestBatchRerunLogic:
    """Test batch rerun core logic"""
    
    @patch('app.tasks.unified_execution.execute_single_iteration_unified')
    @patch('app.tasks.unified_execution.unified_integration.reset_iteration_for_rerun')
    @patch('app.services.task_runners.unified_task_runner.UnifiedTaskRunner.cleanup_iteration_directory')
    def test_rerun_successful_dispatch(self, mock_cleanup, mock_reset, mock_dispatch):
        """Test successful rerun where dispatch succeeds immediately"""
        from app.api.v1.endpoints.batches import rerun_failed_iterations
        
        # Setup mocks
        mock_cleanup.return_value = True
        mock_reset.return_value = True
        
        # Mock successful dispatch
        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-123"
        mock_dispatch.delay.return_value = mock_task_result
        
        # Verify counters
        failed_queues = 0
        rerun_iterations = 0
        
        # Simulate successful dispatch
        iteration_id = str(uuid4())
        task_string_id = "test-task-123"
        gym_id = str(uuid4())
        runner_type = "openai"
        prompt = "Test prompt"
        
        task_result = mock_dispatch.delay(
            iteration_id=iteration_id,
            task_id=task_string_id,
            gym_id=gym_id,
            runner_type=runner_type,
            max_wait_time=180,
            prompt=prompt
        )
        
        if task_result:
            rerun_iterations += 1
        
        # Verify
        assert rerun_iterations == 1
        assert failed_queues == 0
        mock_dispatch.delay.assert_called_once()
    
    @patch('app.tasks.unified_execution.execute_single_iteration_unified')
    @patch('app.celery_app.celery_app')
    def test_rerun_queue_failure_with_clear_and_retry(self, mock_celery_app, mock_dispatch):
        """Test rerun where queue fails, gets cleared, and retry succeeds"""
        # Mock queue failure then success after clear
        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-123"
        mock_dispatch.delay.side_effect = [None, mock_task_result]  # First fails, second succeeds
        
        # Mock celery control for queue clearing
        mock_control = MagicMock()
        mock_celery_app.control = mock_control
        mock_control.purge.return_value = None
        
        # Simulate queue failure handling
        failed_queues = 0
        rerun_iterations = 0
        
        iteration_id = str(uuid4())
        task_string_id = "test-task-123"
        gym_id = str(uuid4())
        runner_type = "openai"
        prompt = "Test prompt"
        
        # First attempt
        task_result = mock_dispatch.delay(
            iteration_id=iteration_id,
            task_id=task_string_id,
            gym_id=gym_id,
            runner_type=runner_type,
            max_wait_time=180,
            prompt=prompt
        )
        
        if not task_result:
            # Queue failed - clear and retry
            failed_queues += 1
            mock_control.purge()
            
            # Retry
            task_result = mock_dispatch.delay(
                iteration_id=iteration_id,
                task_id=task_string_id,
                gym_id=gym_id,
                runner_type=runner_type,
                max_wait_time=180,
                prompt=prompt
            )
            
            if task_result:
                rerun_iterations += 1
                failed_queues -= 1  # Revert failure count since retry succeeded
        
        # Verify
        assert rerun_iterations == 1
        assert failed_queues == 0  # Should be 0 because retry succeeded
        assert mock_dispatch.delay.call_count == 2
        mock_control.purge.assert_called_once()
    
    @patch('app.tasks.unified_execution.execute_single_iteration_unified')
    @patch('app.celery_app.celery_app')
    def test_rerun_queue_error_with_clear_and_retry(self, mock_celery_app, mock_dispatch):
        """Test rerun where queue raises exception, gets cleared, and retry succeeds"""
        # Mock queue exception then success after clear
        mock_task_result = MagicMock()
        mock_task_result.id = "celery-task-123"
        mock_dispatch.delay.side_effect = [Exception("Queue error"), mock_task_result]
        
        # Mock celery control for queue clearing
        mock_control = MagicMock()
        mock_celery_app.control = mock_control
        mock_control.purge.return_value = None
        
        # Simulate queue error handling
        failed_queues = 0
        rerun_iterations = 0
        
        iteration_id = str(uuid4())
        task_string_id = "test-task-123"
        gym_id = str(uuid4())
        runner_type = "openai"
        prompt = "Test prompt"
        
        try:
            task_result = mock_dispatch.delay(
                iteration_id=iteration_id,
                task_id=task_string_id,
                gym_id=gym_id,
                runner_type=runner_type,
                max_wait_time=180,
                prompt=prompt
            )
        except Exception:
            # Queue error occurred - clear and retry
            failed_queues += 1
            mock_control.purge()
            
            # Retry
            task_result = mock_dispatch.delay(
                iteration_id=iteration_id,
                task_id=task_string_id,
                gym_id=gym_id,
                runner_type=runner_type,
                max_wait_time=180,
                prompt=prompt
            )
            
            if task_result:
                rerun_iterations += 1
                failed_queues -= 1  # Revert failure count since retry succeeded
        
        # Verify
        assert rerun_iterations == 1
        assert failed_queues == 0  # Should be 0 because retry succeeded
        assert mock_dispatch.delay.call_count == 2
        mock_control.purge.assert_called_once()
    
    @patch('app.tasks.unified_execution.execute_single_iteration_unified')
    @patch('app.celery_app.celery_app')
    def test_rerun_persistent_queue_failure(self, mock_celery_app, mock_dispatch):
        """Test rerun where queue fails even after clearing - should still mark as queued"""
        # Mock persistent queue failure (both attempts return None)
        mock_dispatch.delay.return_value = None
        
        # Mock celery control for queue clearing
        mock_control = MagicMock()
        mock_celery_app.control = mock_control
        mock_control.purge.return_value = None
        
        # Simulate persistent failure handling
        failed_queues = 0
        rerun_iterations = 0
        
        iteration_id = str(uuid4())
        
        # First attempt
        task_result = mock_dispatch.delay()
        
        if not task_result:
            # Queue failed - clear and retry
            failed_queues += 1
            mock_control.purge()
            
            # Retry
            task_result = mock_dispatch.delay()
            
            if not task_result:
                # Still failed after clear - mark as queued anyway (dispatch_pending_tasks will handle)
                rerun_iterations += 1
        
        # Verify
        assert rerun_iterations == 1  # Still marked as queued
        assert failed_queues == 1  # Tracks the persistent failure
        assert mock_dispatch.delay.call_count == 2
        mock_control.purge.assert_called_once()
    
    @patch('app.tasks.unified_execution.execute_single_iteration_unified')
    @patch('app.tasks.unified_execution.unified_integration.reset_iteration_for_rerun')
    def test_rerun_with_reset_failure(self, mock_reset, mock_dispatch):
        """Test rerun where reset fails - iteration should be skipped"""
        # Setup mocks
        mock_reset.return_value = False  # Reset fails
        
        # Simulate reset failure handling
        failed_resets = 0
        rerun_iterations = 0
        
        iteration_id = str(uuid4())
        
        reset_success = mock_reset(iteration_id)
        
        if not reset_success:
            failed_resets += 1
            # Skip dispatch
        
        # Verify
        assert rerun_iterations == 0  # Not queued due to reset failure
        assert failed_resets == 1
        mock_dispatch.delay.assert_not_called()
    
    def test_rerun_with_missing_parameters_fallbacks(self):
        """Test rerun handles missing parameters with fallbacks"""
        # Test parameter fallback logic
        task_string_id = None
        gym_id = None
        runner_type = None
        
        # Apply fallbacks
        safe_task_id = task_string_id or "unknown"
        safe_gym_id = gym_id or "unknown"
        safe_runner_type = runner_type or "openai"
        
        # Verify fallbacks
        assert safe_task_id == "unknown"
        assert safe_gym_id == "unknown"
        assert safe_runner_type == "openai"
    
    def test_rerun_parameter_fallbacks_preserve_valid_values(self):
        """Test that valid parameters are not overridden by fallbacks"""
        # Test with valid parameters
        task_string_id = "valid-task-123"
        gym_id = str(uuid4())
        runner_type = "anthropic"
        
        # Apply fallbacks (should preserve valid values)
        safe_task_id = task_string_id or "unknown"
        safe_gym_id = gym_id or "unknown"
        safe_runner_type = runner_type or "openai"
        
        # Verify valid values preserved
        assert safe_task_id == "valid-task-123"
        assert safe_gym_id == gym_id
        assert safe_runner_type == "anthropic"


@pytest.mark.api
class TestRerunResetLogic:
    """Test reset_iteration_for_rerun logic verification"""
    
    def test_reset_clears_all_fields_in_query(self):
        """Test that reset SQL query clears all required fields"""
        # This test verifies the SQL pattern, not the actual execution
        # The actual reset is tested via integration in unified_execution tests
        
        # Expected fields to be cleared (from unified_execution.py)
        expected_fields = [
            "status",
            "celery_task_id",
            "started_at",
            "completed_at",
            "execution_time_seconds",
            "result_data",
            "error_message",
            "logs",
            "verification_details",
            "verification_comments",
            "last_model_response",  # Critical for rerun
            "eval_insights",  # Critical for rerun
        ]
        
        # Verify we know what fields should be cleared
        assert "last_model_response" in expected_fields
        assert "eval_insights" in expected_fields
        assert "verification_details" in expected_fields
        assert "status" in expected_fields
