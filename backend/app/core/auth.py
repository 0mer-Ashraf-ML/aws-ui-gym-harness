"""
Authentication utilities for JWT tokens and Google OAuth
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests
from google.oauth2 import id_token
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.crud.refresh_token import refresh_token_crud
from app.services.crud.user import user_crud

# Security scheme for FastAPI docs
security = HTTPBearer()

async def get_dummy_user(db: AsyncSession) -> User:
    """Get or create a dummy user for authentication bypass"""
    # Try to find existing dummy user
    dummy_user = await user_crud.get_by_email(db, "dummy@auth-bypass.example.com")
    
    if not dummy_user:
        # Create dummy user if it doesn't exist
        from app.schemas.user import UserCreate
        dummy_user_data = UserCreate(
            google_id="dummy-google-id",
            email="dummy@auth-bypass.example.com",
            name="Dummy User (Auth Bypass)",
            picture=None,
            is_admin=True,
            is_whitelisted=True,
            is_active=True
        )
        dummy_user = await user_crud.create(db, dummy_user_data)
    
    return dummy_user

class AuthService:
    """Authentication service for JWT and Google OAuth"""
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    async def create_token_pair(db: AsyncSession, user: User) -> Tuple[str, str]:
        """
        Create both access token and refresh token for a user.
        Returns (access_token, refresh_token)
        """
        # Create access token
        access_token = AuthService.create_access_token(
            data={"sub": str(user.uuid), "email": user.email}
        )
        
        # Create refresh token
        refresh_token, _ = await refresh_token_crud.create_refresh_token(db, user.uuid)
        
        return access_token, refresh_token
    
    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> Tuple[str, str]:
        """
        Refresh access token using refresh token.
        Returns (new_access_token, new_refresh_token)
        """
        # Validate refresh token
        token_record = await refresh_token_crud.get_valid_refresh_token(db, refresh_token)
        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )
        
        # Check if user is still whitelisted
        if not token_record.user.is_whitelisted:
            # Revoke all tokens for this user
            await refresh_token_crud.revoke_user_refresh_tokens(db, token_record.user.uuid)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is no longer whitelisted"
            )
        
        # Revoke old refresh token
        await refresh_token_crud.revoke_refresh_token(db, refresh_token)
        
        # Create new token pair
        return await AuthService.create_token_pair(db, token_record.user)
    
    @staticmethod
    def verify_token(token: str) -> Dict[str, Any]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    async def verify_google_token(token: str) -> Dict[str, Any]:
        """Verify Google OAuth token and return user info"""
        try:
            # Verify the token with clock skew tolerance
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                settings.GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=settings.GOOGLE_CLOCK_SKEW_TOLERANCE
            )
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            return {
                'google_id': idinfo['sub'],
                'email': idinfo['email'],
                'name': idinfo['name'],
                'picture': idinfo.get('picture'),
                'email_verified': idinfo.get('email_verified', False)
            }
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google token: {str(e)}"
            )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=not settings.DISABLE_AUTH)),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    # Check if authentication is disabled
    if settings.DISABLE_AUTH:
        return await get_dummy_user(db)
    
    token = credentials.credentials
    payload = AuthService.verify_token(token)
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    result = await db.execute(select(User).where(User.uuid == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_whitelisted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not whitelisted",
        )
    
    return user

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current authenticated user from JWT token, returns None if not authenticated"""
    # Check if authentication is disabled
    if settings.DISABLE_AUTH:
        return await get_dummy_user(db)
    
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = AuthService.verify_token(token)
        
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        
        # Get user from database
        result = await db.execute(select(User).where(User.uuid == user_id))
        user = result.scalar_one_or_none()
        
        if user is None or not user.is_active or not user.is_whitelisted:
            return None
        
        return user
    except HTTPException:
        return None

async def get_current_user_from_token(
    token: str,
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token string"""
    # Check if authentication is disabled
    if settings.DISABLE_AUTH:
        return await get_dummy_user(db)
    
    payload = AuthService.verify_token(token)
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from database
    result = await db.execute(select(User).where(User.uuid == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_whitelisted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not whitelisted",
        )
    
    return user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current authenticated admin user"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (alias for get_current_user)"""
    return current_user
