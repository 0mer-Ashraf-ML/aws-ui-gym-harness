"""
CRUD operations for refresh tokens
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.refresh_token import RefreshToken


class RefreshTokenCRUD:
    """CRUD operations for refresh tokens"""
    
    @staticmethod
    async def create_refresh_token(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, RefreshToken]:
        """
        Create a new refresh token for a user.
        Returns the plain token and the database record.
        """
        # Generate a secure random token
        plain_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        
        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        # Create refresh token record
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        
        db.add(refresh_token)
        await db.commit()
        await db.refresh(refresh_token)
        
        return plain_token, refresh_token
    
    @staticmethod
    async def get_valid_refresh_token(db: AsyncSession, token: str) -> Optional[RefreshToken]:
        """
        Get a valid refresh token by plain token.
        Returns None if token is invalid, expired, or revoked.
        """
        # Hash the provided token
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Query for the token
        result = await db.execute(
            select(RefreshToken)
            .options(selectinload(RefreshToken.user))
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False,
                RefreshToken.expires_at > datetime.now(timezone.utc)
            )
        )
        
        return result.scalar_one_or_none()
    
    @staticmethod
    async def revoke_user_refresh_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
        """
        Revoke all refresh tokens for a user.
        """
        await db.execute(
            delete(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        await db.commit()
    
    @staticmethod
    async def revoke_refresh_token(db: AsyncSession, token: str) -> bool:
        """
        Revoke a specific refresh token.
        Returns True if token was found and revoked, False otherwise.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        refresh_token = result.scalar_one_or_none()
        
        if refresh_token:
            refresh_token.is_revoked = True
            await db.commit()
            return True
        
        return False
    
    @staticmethod
    async def cleanup_expired_tokens(db: AsyncSession) -> int:
        """
        Clean up expired refresh tokens.
        Returns the number of tokens deleted.
        """
        result = await db.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at < datetime.now(timezone.utc)
            )
        )
        await db.commit()
        return result.rowcount


# Create instance
refresh_token_crud = RefreshTokenCRUD()

