"""
Authentication endpoints
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthService, get_current_admin_user, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.access_control import AccessControl, Role
from app.models.user import User
from app.schemas.user import (
    GoogleAuthRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
    WhitelistRequest,
)
from app.services.crud.user import user_crud
from app.services.crud.domain import domain_crud

router = APIRouter()


def _build_user_response(user: User) -> UserResponse:
    """
    Build a UserResponse including the role based on ADMIN_EMAILS.
    """
    role: Optional[Role] = AccessControl.get_role_for_email(user.email) if AccessControl.is_enabled() else "user"
    return UserResponse(
        uuid=user.uuid,
        email=user.email,
        name=user.name,
        picture=user.picture,
        is_admin=user.is_admin,
        is_whitelisted=user.is_whitelisted,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        role=role,
    )

@router.post("/google", response_model=TokenResponse)
async def google_auth(
    auth_request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user with Google OAuth token
    Only allows login for users who have been pre-whitelisted by an admin.
    """
    try:
        # Verify Google token and get user info
        user_info = await AuthService.verify_google_token(auth_request.code)
        email = user_info["email"].lower()

        # Get role from ADMIN_EMAILS (admin if in list, user otherwise)
        role: Optional[Role] = AccessControl.get_role_for_email(email) if AccessControl.is_enabled() else "user"
        if role is None:
            role = "user"  # Default to user if role lookup fails
        
        # First, check if user exists by google_id (for returning users)
        user = await user_crud.get_by_google_id(db, user_info['google_id'])
        
        if not user:
            # Check if user exists by email (for whitelisted users logging in for the first time)
            user = await user_crud.get_by_email(db, email)
        
        # WHITELIST ENFORCEMENT: User must exist in database AND be whitelisted
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your email is not whitelisted. Please contact an administrator to request access."
            )
        
        if not user.is_whitelisted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Your account is not whitelisted. Please contact an administrator for access."
            )
        
        # User is whitelisted - update their Google info and last login
        await db.execute(
            update(User)
            .where(User.uuid == user.uuid)
            .values(
                google_id=user_info['google_id'],
                name=user_info['name'],
                picture=user_info.get('picture'),
                last_login=datetime.now(timezone.utc),
                is_admin=(role == "admin"),
            )
        )
        await db.commit()
        await db.refresh(user)
        
        # Create token pair (access + refresh)
        access_token, refresh_token = await AuthService.create_token_pair(db, user)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=_build_user_response(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token
    """
    try:
        access_token, refresh_token = await AuthService.refresh_access_token(
            db, refresh_request.refresh_token
        )
        
        # Get user info from the new access token
        payload = AuthService.verify_token(access_token)
        user = await user_crud.get_by_id(db, payload["sub"])
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=_build_user_response(user)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user information
    """
    return _build_user_response(current_user)

@router.post("/whitelist", response_model=UserResponse)
async def whitelist_user(
    whitelist_request: WhitelistRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Whitelist a user (admin only)
    """
    user = await user_crud.whitelist_user(
        db, 
        whitelist_request.email, 
        whitelist_request.is_admin
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return _build_user_response(user)

@router.delete("/whitelist/{email}")
async def remove_from_whitelist(
    email: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Remove user from whitelist (admin only)
    """
    user = await user_crud.remove_from_whitelist(db, email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": f"User {email} removed from whitelist"}

@router.get("/users", response_model=list[UserResponse])
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get all users (admin only)
    """
    users = await user_crud.get_all(db, skip=skip, limit=limit)
    return [_build_user_response(user) for user in users]

@router.get("/users/whitelisted", response_model=list[UserResponse])
async def get_whitelisted_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get all whitelisted users (admin only)
    """
    users = await user_crud.get_whitelisted_users(db, skip=skip, limit=limit)
    return [_build_user_response(user) for user in users]
