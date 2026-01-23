"""
Tests for task export endpoints.

Tests per-task export (available to all users) and gym-level export (admin-only).
"""
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.models.user import User


@pytest.mark.asyncio
@pytest.mark.api
class TestTaskExport:
    """Test per-task export endpoint."""
    
    async def test_export_task_success_with_verifier(self, monkeypatch):
        """Successfully export task with verifier script."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        # Mock task with verifier
        mock_task = MagicMock()
        mock_task.uuid = task_uuid
        mock_task.task_id = "test-task"
        mock_task.prompt = "Test prompt"
        
        # Create temporary verifier file
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier_path = Path(tmpdir) / "verifier.py"
            verifier_path.write_text("def verify():\n    return True")
            mock_task.verifier_path = str(verifier_path)
            
            monkeypatch.setattr(
                tasks_module.task_crud,
                "get",
                AsyncMock(return_value=mock_task)
            )
            
            # Mock settings to use temp directory
            with patch.object(tasks_module.settings, 'VERIFIERS_DIR', tmpdir):
                db = AsyncMock()
                
                result = await tasks_module.export_task(
                    task_uuid=task_uuid,
                    db=db,
                    current_user=regular_user
                )
                
                assert result.task_id == "test-task"
                assert result.prompt == "Test prompt"
                assert "```python" in result.verification_script_md
                assert "def verify()" in result.verification_script_md
    
    async def test_export_task_success_without_verifier(self, monkeypatch):
        """Successfully export task without verifier script (returns empty python block)."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        # Mock task without verifier
        mock_task = MagicMock()
        mock_task.uuid = task_uuid
        mock_task.task_id = "test-task-no-verifier"
        mock_task.prompt = "Test prompt without verifier"
        mock_task.verifier_path = None
        
        monkeypatch.setattr(
            tasks_module.task_crud,
            "get",
            AsyncMock(return_value=mock_task)
        )
        
        db = AsyncMock()
        
        result = await tasks_module.export_task(
            task_uuid=task_uuid,
            db=db,
            current_user=regular_user
        )
        
        assert result.task_id == "test-task-no-verifier"
        assert result.prompt == "Test prompt without verifier"
        assert result.verification_script_md == "```python\n\n```"
    
    async def test_export_task_verifier_file_not_found(self, monkeypatch):
        """Export task when verifier file path exists but file doesn't exist."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        # Mock task with non-existent verifier path
        mock_task = MagicMock()
        mock_task.uuid = task_uuid
        mock_task.task_id = "test-task-missing-file"
        mock_task.prompt = "Test prompt with missing verifier"
        mock_task.verifier_path = "/nonexistent/path/verifier.py"
        
        monkeypatch.setattr(
            tasks_module.task_crud,
            "get",
            AsyncMock(return_value=mock_task)
        )
        
        db = AsyncMock()
        
        result = await tasks_module.export_task(
            task_uuid=task_uuid,
            db=db,
            current_user=regular_user
        )
        
        # Should return empty python block when file not found
        assert result.task_id == "test-task-missing-file"
        assert result.verification_script_md == "```python\n\n```"
    
    async def test_export_task_verifier_outside_verifiers_dir(self, monkeypatch):
        """Export task rejects verifier path outside VERIFIERS_DIR for security."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        # Create verifier file outside VERIFIERS_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside_verifier = Path(outside_dir) / "malicious.py"
                outside_verifier.write_text("import os; os.system('rm -rf /')")
                
                mock_task = MagicMock()
                mock_task.uuid = task_uuid
                mock_task.task_id = "test-task-security"
                mock_task.prompt = "Test security"
                mock_task.verifier_path = str(outside_verifier)
                
                monkeypatch.setattr(
                    tasks_module.task_crud,
                    "get",
                    AsyncMock(return_value=mock_task)
                )
                
                # Mock settings to use temp directory as VERIFIERS_DIR
                with patch.object(tasks_module.settings, 'VERIFIERS_DIR', tmpdir):
                    db = AsyncMock()
                    
                    result = await tasks_module.export_task(
                        task_uuid=task_uuid,
                        db=db,
                        current_user=regular_user
                    )
                    
                    # Should return empty block, not read the malicious file
                    assert result.verification_script_md == "```python\n\n```"
    
    async def test_export_task_not_found(self, monkeypatch):
        """Export task returns 404 when task doesn't exist."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        monkeypatch.setattr(
            tasks_module.task_crud,
            "get",
            AsyncMock(return_value=None)
        )
        
        db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await tasks_module.export_task(
                task_uuid=task_uuid,
                db=db,
                current_user=regular_user
            )
        
        assert exc_info.value.status_code == 404
    
    async def test_export_task_accessible_by_regular_user(self, monkeypatch):
        """Regular (non-admin) users can export tasks."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        regular_user = MagicMock(spec=User)
        regular_user.is_admin = False
        regular_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        mock_task = MagicMock()
        mock_task.uuid = task_uuid
        mock_task.task_id = "accessible-task"
        mock_task.prompt = "Accessible prompt"
        mock_task.verifier_path = None
        
        monkeypatch.setattr(
            tasks_module.task_crud,
            "get",
            AsyncMock(return_value=mock_task)
        )
        
        db = AsyncMock()
        
        result = await tasks_module.export_task(
            task_uuid=task_uuid,
            db=db,
            current_user=regular_user
        )
        
        assert result.task_id == "accessible-task"


@pytest.mark.asyncio
@pytest.mark.api
class TestGymTasksExport:
    """Test gym-level tasks export endpoint (admin-only)."""
    
    async def test_export_gym_tasks_success(self, monkeypatch):
        """Admin can successfully export all tasks for a gym."""
        from app.api.v1.endpoints import gyms as gyms_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        admin_user.email = "admin@test.com"
        
        gym_uuid = uuid.uuid4()
        
        # Mock gym
        mock_gym = MagicMock()
        mock_gym.uuid = gym_uuid
        mock_gym.name = "Test Gym"
        
        # Mock tasks
        mock_task1 = MagicMock()
        mock_task1.task_id = "task-1"
        mock_task1.prompt = "Prompt 1"
        mock_task1.verifier_path = None
        
        mock_task2 = MagicMock()
        mock_task2.task_id = "task-2"
        mock_task2.prompt = "Prompt 2"
        mock_task2.verifier_path = None
        
        monkeypatch.setattr(
            gyms_module.gym_crud,
            "get",
            AsyncMock(return_value=mock_gym)
        )
        
        monkeypatch.setattr(
            gyms_module.task_crud,
            "get_multi_by_gym",
            AsyncMock(return_value=[mock_task1, mock_task2])
        )
        
        db = AsyncMock()
        
        result = await gyms_module.export_gym_tasks(
            gym_uuid=gym_uuid,
            db=db,
            current_admin=admin_user
        )
        
        assert result.gym_id == str(gym_uuid)
        assert len(result.tasks) == 2
        assert result.tasks[0].task_id == "task-1"
        assert result.tasks[1].task_id == "task-2"
    
    async def test_export_gym_tasks_with_verifiers(self, monkeypatch):
        """Export gym tasks includes verifier scripts."""
        from app.api.v1.endpoints import gyms as gyms_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        admin_user.email = "admin@test.com"
        
        gym_uuid = uuid.uuid4()
        
        mock_gym = MagicMock()
        mock_gym.uuid = gym_uuid
        mock_gym.name = "Test Gym"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            verifier_path = Path(tmpdir) / "verifier.py"
            verifier_path.write_text("def verify():\n    return True")
            
            mock_task = MagicMock()
            mock_task.task_id = "task-with-verifier"
            mock_task.prompt = "Task with verifier"
            mock_task.verifier_path = str(verifier_path)
            
            monkeypatch.setattr(
                gyms_module.gym_crud,
                "get",
                AsyncMock(return_value=mock_gym)
            )
            
            monkeypatch.setattr(
                gyms_module.task_crud,
                "get_multi_by_gym",
                AsyncMock(return_value=[mock_task])
            )
            
            with patch.object(gyms_module.settings, 'VERIFIERS_DIR', tmpdir):
                db = AsyncMock()
                
                result = await gyms_module.export_gym_tasks(
                    gym_uuid=gym_uuid,
                    db=db,
                    current_admin=admin_user
                )
                
                assert len(result.tasks) == 1
                assert "def verify()" in result.tasks[0].verification_script_md
    
    async def test_export_gym_tasks_gym_not_found(self, monkeypatch):
        """Export gym tasks returns 404 when gym doesn't exist."""
        from app.api.v1.endpoints import gyms as gyms_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        
        gym_uuid = uuid.uuid4()
        
        monkeypatch.setattr(
            gyms_module.gym_crud,
            "get",
            AsyncMock(return_value=None)
        )
        
        db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await gyms_module.export_gym_tasks(
                gym_uuid=gym_uuid,
                db=db,
                current_admin=admin_user
            )
        
        assert exc_info.value.status_code == 404
    
    async def test_export_gym_tasks_requires_admin(self):
        """Non-admin users cannot access gym export endpoint."""
        from app.core.auth import get_current_admin_user
        
        non_admin_user = MagicMock(spec=User)
        non_admin_user.is_admin = False
        non_admin_user.uuid = uuid.uuid4()
        non_admin_user.is_whitelisted = True
        non_admin_user.is_active = True
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(current_user=non_admin_user)
        
        assert exc_info.value.status_code == 403
    
    async def test_export_gym_tasks_empty_gym(self, monkeypatch):
        """Export gym with no tasks returns empty tasks list."""
        from app.api.v1.endpoints import gyms as gyms_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        admin_user.email = "admin@test.com"
        
        gym_uuid = uuid.uuid4()
        
        mock_gym = MagicMock()
        mock_gym.uuid = gym_uuid
        mock_gym.name = "Empty Gym"
        
        monkeypatch.setattr(
            gyms_module.gym_crud,
            "get",
            AsyncMock(return_value=mock_gym)
        )
        
        monkeypatch.setattr(
            gyms_module.task_crud,
            "get_multi_by_gym",
            AsyncMock(return_value=[])
        )
        
        db = AsyncMock()
        
        result = await gyms_module.export_gym_tasks(
            gym_uuid=gym_uuid,
            db=db,
            current_admin=admin_user
        )
        
        assert result.gym_id == str(gym_uuid)
        assert len(result.tasks) == 0
