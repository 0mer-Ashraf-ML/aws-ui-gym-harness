"""
Tests for authentication endpoints with Excel-based access control.

Tests that Google OAuth login enforces Excel sheet whitelist and assigns correct roles.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.user import GoogleAuthRequest


class DummyUser:
    """Minimal user object compatible with _build_user_response."""
    
    def __init__(self, email: str, is_admin: bool):
        self.uuid = uuid.uuid4()
        self.email = email
        self.name = "Test User"
        self.picture: Optional[str] = None
        self.is_admin = is_admin
        self.is_whitelisted = True
        self.is_active = True
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now
        self.last_login = now


@pytest.mark.asyncio
@pytest.mark.api
class TestGoogleAuthWithExcelRoles:
    """Test Google OAuth endpoint with Excel-based role assignment."""
    
    async def test_allows_admin_email_and_sets_role_admin(self, monkeypatch):
        """
        When Excel marks an email as admin:
        - user is created with is_admin=True
        - response.user.role == 'admin'
        """
        from app.api.v1.endpoints import auth as auth_module
        
        # Mock Google token verification
        async def fake_verify_google_token(token: str):
            return {
                "google_id": "gid-admin",
                "email": "admin@example.com",
                "name": "Admin User",
                "picture": None,
            }
        
        monkeypatch.setattr(
            auth_module.AuthService, "verify_google_token", fake_verify_google_token
        )
        
        # Excel access control: enabled and returns 'admin' for this email
        monkeypatch.setattr(auth_module.AccessControl, "is_enabled", lambda: True)
        monkeypatch.setattr(
            auth_module.AccessControl,
            "get_role_for_email",
            lambda email: "admin" if email.lower() == "admin@example.com" else None,
        )
        
        # No existing user; create a new admin user
        dummy_user = DummyUser(email="admin@example.com", is_admin=True)
        
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_google_id", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_email", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            auth_module.user_crud, "create", AsyncMock(return_value=dummy_user)
        )
        
        # Mock token creation
        monkeypatch.setattr(
            auth_module.AuthService,
            "create_token_pair",
            AsyncMock(return_value=("access-token", "refresh-token"))
        )
        
        db = AsyncMock()  # fake AsyncSession
        
        result = await auth_module.google_auth(
            GoogleAuthRequest(code="dummy-code"), db=db
        )
        
        assert result.user.email == "admin@example.com"
        assert result.user.is_admin is True
        assert result.user.role == "admin"
    
    async def test_allows_user_email_and_sets_role_user(self, monkeypatch):
        """
        When Excel marks an email as user:
        - user is created with is_admin=False
        - response.user.role == 'user'
        """
        from app.api.v1.endpoints import auth as auth_module
        
        async def fake_verify_google_token(token: str):
            return {
                "google_id": "gid-user",
                "email": "user@example.com",
                "name": "Normal User",
                "picture": None,
            }
        
        monkeypatch.setattr(
            auth_module.AuthService, "verify_google_token", fake_verify_google_token
        )
        
        monkeypatch.setattr(auth_module.AccessControl, "is_enabled", lambda: True)
        monkeypatch.setattr(
            auth_module.AccessControl,
            "get_role_for_email",
            lambda email: "user" if email.lower() == "user@example.com" else None,
        )
        
        dummy_user = DummyUser(email="user@example.com", is_admin=False)
        
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_google_id", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_email", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            auth_module.user_crud, "create", AsyncMock(return_value=dummy_user)
        )
        
        monkeypatch.setattr(
            auth_module.AuthService,
            "create_token_pair",
            AsyncMock(return_value=("access-token", "refresh-token"))
        )
        
        db = AsyncMock()
        
        result = await auth_module.google_auth(
            GoogleAuthRequest(code="dummy-code"), db=db
        )
        
        assert result.user.email == "user@example.com"
        assert result.user.is_admin is False
        assert result.user.role == "user"
    
    async def test_rejects_email_not_in_excel(self, monkeypatch):
        """
        When Excel access control is enabled but email is not present,
        /auth/google should return 403 and not create/login a user.
        """
        from app.api.v1.endpoints import auth as auth_module
        
        async def fake_verify_google_token(token: str):
            return {
                "google_id": "gid-unknown",
                "email": "unknown@example.com",
                "name": "Unknown User",
                "picture": None,
            }
        
        monkeypatch.setattr(
            auth_module.AuthService, "verify_google_token", fake_verify_google_token
        )
        
        # Excel enabled but no role for this email
        monkeypatch.setattr(auth_module.AccessControl, "is_enabled", lambda: True)
        monkeypatch.setattr(
            auth_module.AccessControl,
            "get_role_for_email",
            lambda email: None,
        )
        
        # Ensure no user gets created
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_google_id", AsyncMock(return_value=None)
        )
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_email", AsyncMock(return_value=None)
        )
        create_mock = AsyncMock()
        monkeypatch.setattr(auth_module.user_crud, "create", create_mock)
        
        db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await auth_module.google_auth(GoogleAuthRequest(code="dummy-code"), db=db)
        
        assert exc_info.value.status_code == 403
        assert "not in access sheet" in exc_info.value.detail.lower()
        # Verify user creation was never called
        create_mock.assert_not_called()
    
    async def test_updates_existing_user_role_from_excel(self, monkeypatch):
        """
        When an existing user logs in, their role is updated based on current Excel sheet.
        """
        from app.api.v1.endpoints import auth as auth_module
        
        async def fake_verify_google_token(token: str):
            return {
                "google_id": "gid-existing",
                "email": "existing@example.com",
                "name": "Existing User",
                "picture": None,
            }
        
        monkeypatch.setattr(
            auth_module.AuthService, "verify_google_token", fake_verify_google_token
        )
        
        # Excel says this user is now an admin (role changed)
        monkeypatch.setattr(auth_module.AccessControl, "is_enabled", lambda: True)
        monkeypatch.setattr(
            auth_module.AccessControl,
            "get_role_for_email",
            lambda email: "admin" if email.lower() == "existing@example.com" else None,
        )
        
        # Existing user (was a regular user, now should be admin)
        existing_user = DummyUser(email="existing@example.com", is_admin=False)
        
        monkeypatch.setattr(
            auth_module.user_crud, "get_by_google_id", AsyncMock(return_value=existing_user)
        )
        
        # Mock database update
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        
        monkeypatch.setattr(
            auth_module.AuthService,
            "create_token_pair",
            AsyncMock(return_value=("access-token", "refresh-token"))
        )
        
        result = await auth_module.google_auth(
            GoogleAuthRequest(code="dummy-code"), db=db
        )
        
        # User should now have admin role in response
        assert result.user.role == "admin"
        # Verify database update was called to set is_admin=True
        db.execute.assert_called()
        db.commit.assert_called()

