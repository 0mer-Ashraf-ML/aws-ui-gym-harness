"""
CRUD operations for Gym model
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.gym import Gym, VerificationStrategy
from app.schemas.gym import GymCreate, GymUpdate
from app.utils.url_normalizer import normalize_base_url


class GymCRUD:
    """CRUD operations for Gym"""
    
    async def create(self, db: AsyncSession, gym_data: GymCreate) -> Gym:
        """Create a new gym"""
        gym = Gym(**gym_data.model_dump())
        db.add(gym)
        await db.commit()
        await db.refresh(gym)
        return gym
    
    async def get(self, db: AsyncSession, gym_uuid: UUID) -> Optional[Gym]:
        """Get a gym by UUID"""
        result = await db.execute(
            select(Gym).where(Gym.uuid == gym_uuid)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[Gym]:
        """Get a gym by name"""
        result = await db.execute(
            select(Gym).where(Gym.name == name)
        )
        return result.scalar_one_or_none()
    
    async def get_by_base_url_and_strategy(
        self, 
        db: AsyncSession, 
        base_url: str, 
        verification_strategy: VerificationStrategy
    ) -> Optional[Gym]:
        """Get a gym by base URL and verification strategy (with normalization)"""
        normalized_url = normalize_base_url(base_url)
        
        # First, try exact match (for newly created gyms with normalized URLs)
        result = await db.execute(
            select(Gym).where(
                Gym.base_url == normalized_url,
                Gym.verification_strategy == verification_strategy
            )
        )
        exact_match = result.scalar_one_or_none()
        if exact_match:
            return exact_match
        
        # Fallback: Use SQL functions to find normalized matches (handles legacy data)
        from sqlalchemy import func
        result = await db.execute(
            select(Gym).where(
                func.lower(func.trim(func.rtrim(Gym.base_url, '/'))) == normalized_url,
                Gym.verification_strategy == verification_strategy
            )
        )
        return result.scalar_one_or_none()
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Gym]:
        """Get multiple gyms with pagination"""
        result = await db.execute(
            select(Gym)
            .offset(skip)
            .limit(limit)
            .order_by(Gym.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_with_tasks(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Gym]:
        """Get multiple gyms with their tasks"""
        result = await db.execute(
            select(Gym)
            .options(selectinload(Gym.tasks))
            .offset(skip)
            .limit(limit)
            .order_by(Gym.created_at.desc())
        )
        return result.scalars().all()
    
    async def update(
        self, 
        db: AsyncSession, 
        gym_uuid: UUID, 
        gym_data: GymUpdate
    ) -> Optional[Gym]:
        """Update a gym"""
        gym = await self.get(db, gym_uuid)
        if not gym:
            return None
        
        update_data = gym_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(gym, field, value)
        
        await db.commit()
        await db.refresh(gym)
        return gym
    
    async def delete(self, db: AsyncSession, gym_uuid: UUID) -> bool:
        """Delete a gym"""
        gym = await self.get(db, gym_uuid)
        if not gym:
            return False
        
        await db.delete(gym)
        await db.commit()
        return True
    
    async def count(self, db: AsyncSession) -> int:
        """Count total gyms"""
        result = await db.execute(select(func.count(Gym.uuid)))
        return result.scalar()
    
    async def get_multi_with_task_counts(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[dict]:
        """Get multiple gyms with their task counts"""
        from app.models.task import Task
        
        # Query gyms with task counts using a subquery
        subquery = (
            select(Task.gym_id, func.count(Task.uuid).label('task_count'))
            .group_by(Task.gym_id)
            .subquery()
        )
        
        result = await db.execute(
            select(
                Gym,
                func.coalesce(subquery.c.task_count, 0).label('task_count')
            )
            .outerjoin(subquery, Gym.uuid == subquery.c.gym_id)
            .offset(skip)
            .limit(limit)
            .order_by(Gym.created_at.desc())
        )
        
        # Convert to list of dictionaries with task_count
        gyms_with_counts = []
        for row in result:
            gym_dict = {
                'uuid': row.Gym.uuid,
                'name': row.Gym.name,
                'description': row.Gym.description,
                'base_url': row.Gym.base_url,
                'verification_strategy': row.Gym.verification_strategy,
                'created_at': row.Gym.created_at,
                'updated_at': row.Gym.updated_at,
                'task_count': row.task_count
            }
            gyms_with_counts.append(gym_dict)
        
        return gyms_with_counts

# Create instance
gym_crud = GymCRUD()
