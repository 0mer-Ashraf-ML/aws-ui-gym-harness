"""
Tests for delete endpoint permissions (admin-only).

Verifies that only admin users can delete tasks and batches.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.models.user import User


@pytest.mark.asyncio
@pytest.mark.api
class TestTaskDeletePermissions:
    """Test task delete endpoint requires admin user."""
    
    async def test_delete_task_allows_admin(self, monkeypatch):
        """Admin user can delete tasks."""
        from app.api.v1.endpoints import tasks as tasks_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        
        task_uuid = uuid.uuid4()
        
        # Mock task exists and gets deleted
        mock_task = MagicMock()
        mock_task.uuid = task_uuid
        
        monkeypatch.setattr(
            tasks_module.task_crud,
            "delete",
            AsyncMock(return_value=mock_task)
        )
        
        db = AsyncMock()
        
        result = await tasks_module.delete_task(
            task_uuid=task_uuid,
            db=db,
            current_admin=admin_user
        )
        
        assert result is not None
        tasks_module.task_crud.delete.assert_called_once_with(db, task_uuid)
    
    async def test_delete_task_rejects_non_admin(self):
        """Non-admin user cannot access delete endpoint (dependency enforces this)."""
        # The endpoint uses get_current_admin_user dependency
        # which will raise 403 for non-admin users at the FastAPI dependency level
        from app.core.auth import get_current_admin_user
        
        non_admin_user = MagicMock(spec=User)
        non_admin_user.is_admin = False
        non_admin_user.uuid = uuid.uuid4()
        non_admin_user.is_whitelisted = True
        non_admin_user.is_active = True
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(current_user=non_admin_user)
        
        assert exc_info.value.status_code == 403
        assert "permissions" in exc_info.value.detail.lower() or "admin" in exc_info.value.detail.lower()


@pytest.mark.asyncio
@pytest.mark.api
class TestBatchDeletePermissions:
    """Test batch delete endpoint requires admin user."""
    
    async def test_delete_batch_allows_admin(self, monkeypatch):
        """Admin user can delete batches."""
        from app.api.v1.endpoints import batches as batches_module
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        
        batch_id = uuid.uuid4()
        
        # Mock batch exists and gets deleted
        mock_batch = MagicMock()
        mock_batch.uuid = batch_id
        
        monkeypatch.setattr(
            batches_module.batch_crud,
            "delete",
            AsyncMock(return_value=mock_batch)
        )
        
        db = AsyncMock()
        
        result = await batches_module.delete_batch(
            batch_id=batch_id,
            db=db,
            current_admin=admin_user
        )
        
        assert result is not None
        batches_module.batch_crud.delete.assert_called_once_with(db, batch_id)
    
    async def test_delete_batch_rejects_non_admin(self):
        """Non-admin user cannot access delete endpoint (dependency enforces this)."""
        from app.core.auth import get_current_admin_user
        
        non_admin_user = MagicMock(spec=User)
        non_admin_user.is_admin = False
        non_admin_user.uuid = uuid.uuid4()
        non_admin_user.is_whitelisted = True
        non_admin_user.is_active = True
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(current_user=non_admin_user)
        
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.api
class TestGetCurrentAdminUser:
    """Test the get_current_admin_user dependency directly."""
    
    async def test_get_current_admin_user_allows_admin(self):
        """Admin user passes through get_current_admin_user."""
        from app.core.auth import get_current_admin_user
        
        admin_user = MagicMock(spec=User)
        admin_user.is_admin = True
        admin_user.uuid = uuid.uuid4()
        admin_user.is_whitelisted = True
        admin_user.is_active = True
        
        result = await get_current_admin_user(current_user=admin_user)
        
        assert result == admin_user
        assert result.is_admin is True
    
    async def test_get_current_admin_user_rejects_non_admin(self):
        """Non-admin user raises 403 from get_current_admin_user."""
        from app.core.auth import get_current_admin_user
        
        non_admin_user = MagicMock(spec=User)
        non_admin_user.is_admin = False
        non_admin_user.uuid = uuid.uuid4()
        non_admin_user.is_whitelisted = True
        non_admin_user.is_active = True
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(current_user=non_admin_user)
        
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower() or "permissions" in exc_info.value.detail.lower()

