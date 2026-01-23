"""
CRUD operations for Batch model
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import sqlalchemy as sa

from app.core.config import settings
from app.models.batch import Batch
from app.models.token_usage import TokenUsage
from app.models.execution import Execution
from app.models.gym import Gym
from app.schemas.batch import BatchCreate, BatchUpdate

logger = logging.getLogger(__name__)


class BatchCRUD:
    """CRUD operations for Batch"""
    
    async def create(self, db: AsyncSession, batch_data: BatchCreate, created_by: UUID = None) -> Batch:
        """Create a new batch"""
        # Exclude selected_models and selected_task_ids from database record since they're not stored
        batch_dict = batch_data.model_dump()
        batch_dict.pop('selected_models', None)
        batch_dict.pop('selected_task_ids', None)
        
        # Add created_by if provided
        if created_by:
            batch_dict['created_by'] = created_by
        
        batch = Batch(**batch_dict)
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        return batch
    
    async def get(self, db: AsyncSession, batch_uuid: UUID) -> Optional[Batch]:
        """Get a batch by UUID"""
        result = await db.execute(
            select(Batch)
            .options(selectinload(Batch.gym), selectinload(Batch.executions), selectinload(Batch.creator))
            .where(Batch.uuid == batch_uuid)
        )
        return result.scalar_one_or_none()
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Batch]:
        """Get multiple batches with pagination"""
        result = await db.execute(
            select(Batch)
            .options(selectinload(Batch.gym), selectinload(Batch.executions), selectinload(Batch.creator))
            .offset(skip)
            .limit(limit)
            .order_by(Batch.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_gym(
        self, 
        db: AsyncSession, 
        gym_id: UUID,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Batch]:
        """Get multiple batches by gym with pagination"""
        result = await db.execute(
            select(Batch)
            .options(selectinload(Batch.gym), selectinload(Batch.executions), selectinload(Batch.creator))
            .where(Batch.gym_id == gym_id)
            .offset(skip)
            .limit(limit)
            .order_by(Batch.created_at.desc())
        )
        return result.scalars().all()
    
    async def update(
        self, 
        db: AsyncSession, 
        db_obj: Batch, 
        obj_in: BatchUpdate
    ) -> Batch:
        """Update a batch"""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db_obj.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def delete(self, db: AsyncSession, batch_uuid: UUID) -> Optional[Batch]:
        """Delete a batch and its associated execution directories"""
        # Load batch with executions to get execution_folder_names
        result = await db.execute(
            select(Batch)
            .options(selectinload(Batch.executions))
            .where(Batch.uuid == batch_uuid)
        )
        batch = result.scalar_one_or_none()
        
        if batch:
            # Snapshot missing fields for token_usage rows tied to this batch via executions
            try:
                # Subquery of execution IDs for this batch
                exec_ids_subq = select(Execution.uuid).where(Execution.batch_id == batch_uuid)
                # Ensure batch_id is set for usage rows referencing these executions
                await db.execute(
                    sa.update(TokenUsage)
                    .where(TokenUsage.execution_id.in_(exec_ids_subq))
                    .where(TokenUsage.batch_id.is_(None))
                    .values(batch_id=batch_uuid)
                )
                # Ensure batch_name is set
                await db.execute(
                    sa.update(TokenUsage)
                    .where(TokenUsage.execution_id.in_(exec_ids_subq))
                    .where(sa.or_(TokenUsage.batch_name.is_(None), TokenUsage.batch_name == ''))
                    .values(batch_name=batch.name)
                )
                # Ensure gym_id is set
                await db.execute(
                    sa.update(TokenUsage)
                    .where(TokenUsage.execution_id.in_(exec_ids_subq))
                    .where(TokenUsage.gym_id.is_(None))
                    .values(gym_id=batch.gym_id)
                )
                # Ensure gym_name is set
                gym_name_value = None
                try:
                    gym_row = await db.execute(select(Gym.name).where(Gym.uuid == batch.gym_id))
                    gym_name_value = gym_row.scalar_one_or_none()
                except Exception:
                    gym_name_value = None
                if gym_name_value:
                    await db.execute(
                        sa.update(TokenUsage)
                        .where(TokenUsage.execution_id.in_(exec_ids_subq))
                        .where(sa.or_(TokenUsage.gym_name.is_(None), TokenUsage.gym_name == ''))
                        .values(gym_name=gym_name_value)
                    )
                # Mark related token usage rows as deleted snapshot
                await db.execute(
                    sa.update(TokenUsage)
                    .where(TokenUsage.batch_id == batch_uuid)
                    .values(batch_is_deleted=True)
                )
                await db.flush()
            except Exception as e:
                logger.warning(f"Failed to snapshot/mark token_usage rows for batch {batch_uuid}: {e}")
            # First, delete the physical execution directories
            results_dir = Path(settings.RESULTS_DIR)
            deleted_dirs = []
            failed_dirs = []
            
            for execution in batch.executions:
                if execution.execution_folder_name:
                    execution_dir = results_dir / execution.execution_folder_name
                    if execution_dir.exists():
                        try:
                            shutil.rmtree(execution_dir)
                            deleted_dirs.append(str(execution_dir))
                            logger.info(f"🗑️ Deleted execution directory: {execution_dir}")
                        except Exception as e:
                            failed_dirs.append(str(execution_dir))
                            logger.error(f"❌ Failed to delete execution directory {execution_dir}: {e}")
            
            # Log summary
            if deleted_dirs:
                logger.info(f"✅ Deleted {len(deleted_dirs)} execution directories for batch {batch_uuid}")
            if failed_dirs:
                logger.warning(f"⚠️ Failed to delete {len(failed_dirs)} execution directories for batch {batch_uuid}")
            
            # Then delete the database records (CASCADE will handle related records)
            await db.delete(batch)
            await db.commit()
        
        return batch
    
    async def count(self, db: AsyncSession) -> int:
        """Count total batches"""
        result = await db.execute(select(func.count(Batch.uuid)))
        return result.scalar()
    
    async def count_by_gym(self, db: AsyncSession, gym_id: UUID) -> int:
        """Count batches by gym"""
        result = await db.execute(
            select(func.count(Batch.uuid)).where(Batch.gym_id == gym_id)
        )
        return result.scalar()


# Create a singleton instance
batch_crud = BatchCRUD()
