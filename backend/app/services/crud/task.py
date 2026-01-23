"""
CRUD operations for Task model
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


class TaskCRUD:
    """CRUD operations for Task"""
    
    async def create(self, db: AsyncSession, task_data: TaskCreate) -> Task:
        """Create a new task"""
        task = Task(**task_data.model_dump())
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task
    
    async def get(self, db: AsyncSession, task_uuid: UUID) -> Optional[Task]:
        """Get a task by UUID"""
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.gym))
            .where(Task.uuid == task_uuid)
        )
        return result.scalar_one_or_none()
    
    async def get_by_task_id_and_gym(
        self, 
        db: AsyncSession, 
        task_id: str, 
        gym_id: UUID
    ) -> Optional[Task]:
        """Get a task by task_id and gym_id"""
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.gym))
            .where(and_(Task.task_id == task_id, Task.gym_id == gym_id))
        )
        return result.scalar_one_or_none()
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Task]:
        """Get multiple tasks with pagination"""
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.gym))
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_gym(
        self, 
        db: AsyncSession, 
        gym_id: UUID,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Task]:
        """Get multiple tasks by gym with pagination"""
        result = await db.execute(
            select(Task)
            .options(selectinload(Task.gym))
            .where(Task.gym_id == gym_id)
            .offset(skip)
            .limit(limit)
            .order_by(Task.created_at.desc())
        )
        return result.scalars().all()
    
    async def update(
        self, 
        db: AsyncSession, 
        task_uuid: UUID, 
        task_data: TaskUpdate
    ) -> Optional[Task]:
        """Update a task"""
        task = await self.get(db, task_uuid)
        if not task:
            return None
        
        update_data = task_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        
        await db.commit()
        await db.refresh(task)
        return task
    
    async def delete(self, db: AsyncSession, task_uuid: UUID) -> bool:
        """Delete a task"""
        task = await self.get(db, task_uuid)
        if not task:
            return False
        
        await db.delete(task)
        await db.commit()
        return True
    
    async def count(self, db: AsyncSession) -> int:
        """Count total tasks"""
        result = await db.execute(select(func.count(Task.uuid)))
        return result.scalar()
    
    async def count_by_gym(self, db: AsyncSession, gym_id: UUID) -> int:
        """Count tasks by gym"""
        result = await db.execute(
            select(func.count(Task.uuid)).where(Task.gym_id == gym_id)
        )
        return result.scalar()

# Create instance
task_crud = TaskCRUD()
