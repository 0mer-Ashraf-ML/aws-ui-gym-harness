"""
User CRUD operations
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserCRUD:
    """User CRUD operations"""
    
    async def get_by_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user by UUID"""
        result = await db.execute(select(User).where(User.uuid == user_id))
        return result.scalar_one_or_none()
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email"""
        result = await db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()
    
    async def get_by_google_id(self, db: AsyncSession, google_id: str) -> Optional[User]:
        """Get user by Google ID"""
        result = await db.execute(select(User).where(User.google_id == google_id))
        return result.scalar_one_or_none()
    
    async def create(self, db: AsyncSession, user_data: UserCreate) -> User:
        """Create new user"""
        # Check if user is in admin list
        is_admin = user_data.email.lower() in settings.admin_emails_list
        
        db_user = User(
            google_id=user_data.google_id,
            email=user_data.email.lower(),
            name=user_data.name,
            picture=user_data.picture,
            is_admin=is_admin or user_data.is_admin,
            is_whitelisted=user_data.is_whitelisted,
            last_login=datetime.now(timezone.utc)
        )
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    async def update(self, db: AsyncSession, user_id: str, user_data: UserUpdate) -> Optional[User]:
        """Update user"""
        update_data = user_data.dict(exclude_unset=True)
        if not update_data:
            return await self.get_by_id(db, user_id)
        
        # Update last_login if this is a login update
        if 'last_login' not in update_data:
            update_data['last_login'] = datetime.now(timezone.utc)
        
        await db.execute(
            update(User)
            .where(User.uuid == user_id)
            .values(**update_data)
        )
        await db.commit()
        return await self.get_by_id(db, user_id)
    
    async def update_last_login(self, db: AsyncSession, user_id: str) -> Optional[User]:
        """Update user's last login timestamp"""
        await db.execute(
            update(User)
            .where(User.uuid == user_id)
            .values(last_login=datetime.now(timezone.utc))
        )
        await db.commit()
        return await self.get_by_id(db, user_id)
    
    async def delete(self, db: AsyncSession, user_id: str) -> bool:
        """Delete user"""
        result = await db.execute(delete(User).where(User.uuid == user_id))
        await db.commit()
        return result.rowcount > 0
    
    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users with pagination"""
        result = await db.execute(
            select(User)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_whitelisted_users(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all whitelisted users"""
        result = await db.execute(
            select(User)
            .where(User.is_whitelisted == True)
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_admin_users(self, db: AsyncSession) -> List[User]:
        """Get all admin users"""
        result = await db.execute(
            select(User)
            .where(User.is_admin == True)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()
    
    async def whitelist_user(self, db: AsyncSession, email: str, is_admin: bool = False) -> Optional[User]:
        """Whitelist a user by email. Creates user if doesn't exist."""
        user = await self.get_by_email(db, email)
        
        if not user:
            # Create a new user record for whitelisting with placeholder values
            from app.schemas.user import UserCreate
            user_data = UserCreate(
                google_id=f"whitelisted_{email.replace('@', '_at_').replace('.', '_dot_')}",  # Placeholder until first login
                email=email,
                name="Pending Login",  # Placeholder until first login
                picture=None,
                is_admin=is_admin,
                is_whitelisted=True
            )
            user = await self.create(db, user_data)
        else:
            # Update existing user
            await db.execute(
                update(User)
                .where(User.email == email.lower())
                .values(is_whitelisted=True, is_admin=is_admin)
            )
            await db.commit()
            user = await self.get_by_email(db, email)
        
        return user
    
    async def remove_from_whitelist(self, db: AsyncSession, email: str) -> Optional[User]:
        """Remove user from whitelist"""
        user = await self.get_by_email(db, email)
        if not user:
            return None
        
        await db.execute(
            update(User)
            .where(User.email == email.lower())
            .values(is_whitelisted=False, is_admin=False)
        )
        await db.commit()
        return await self.get_by_email(db, email)

# Create instance
user_crud = UserCRUD()
