"""
CRUD operations for Execution model
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.execution import Execution
from app.models.task import Task
from app.schemas.execution import ExecutionCreate, ExecutionUpdate


class ExecutionCRUD:
    """CRUD operations for Execution"""
    
    async def create(self, db: AsyncSession, execution_data: ExecutionCreate) -> Execution:
        """Create a new execution with task snapshot fields"""
        # Log execution_type BEFORE model_dump for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 CRUD create: execution_type from execution_data={execution_data.execution_type}, type={type(execution_data.execution_type)}")
        
        # Get execution_type value directly from execution_data before dumping
        from app.models.execution import ExecutionType
        execution_type_value = execution_data.execution_type
        if hasattr(execution_type_value, 'value'):
            execution_type_value = execution_type_value.value
        logger.info(f"🔧 CRUD create: execution_type value={execution_type_value}")
        
        # Use model_dump with mode='python' to ensure enums are serialized as values
        execution_dict = execution_data.model_dump(mode='python')
        
        logger.info(f"🔧 CRUD create: execution_type from dict={execution_dict.get('execution_type')}, type={type(execution_dict.get('execution_type'))}")
        
        # Remove task_id from dict (backwards compatibility field, not in Execution model)
        execution_dict.pop('task_id', None)
        
        # Force execution_type to be set correctly - use the value we extracted
        if execution_type_value == 'playground':
            execution_dict['execution_type'] = ExecutionType.PLAYGROUND
        elif execution_type_value == 'batch':
            execution_dict['execution_type'] = ExecutionType.BATCH
        else:
            # Fallback to what's in execution_data
            execution_dict['execution_type'] = execution_data.execution_type
        
        logger.info(f"🔧 CRUD create: execution_type final={execution_dict.get('execution_type')}, type={type(execution_dict.get('execution_type'))}")
        
        # If task_identifier is provided but snapshot fields are missing, try to fetch from task
        if execution_dict.get('task_identifier'):
            # Check if any snapshot fields are missing
            missing_fields = []
            if not execution_dict.get('prompt'):
                missing_fields.append('prompt')
            if not execution_dict.get('grader_config'):
                missing_fields.append('grader_config')
            if not execution_dict.get('simulator_config'):
                missing_fields.append('simulator_config')
            
            # If any fields are missing, fetch from task
            if missing_fields:
                # Look up task by task_identifier AND gym_id to get missing snapshot fields
                result = await db.execute(
                    select(Task).where(
                        and_(
                            Task.task_id == execution_dict['task_identifier'],
                            Task.gym_id == execution_dict['gym_id']
                        )
                    )
                )
                task = result.scalar_one_or_none()
                if task:
                    if 'prompt' in missing_fields:
                        execution_dict['prompt'] = task.prompt
                    if 'grader_config' in missing_fields:
                        execution_dict['grader_config'] = task.grader_config
                    if 'simulator_config' in missing_fields:
                        execution_dict['simulator_config'] = task.simulator_config
        
        execution = Execution(**execution_dict)
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        return execution
    
    async def get(self, db: AsyncSession, execution_uuid: UUID) -> Optional[Execution]:
        """Get an execution by UUID"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.uuid == execution_uuid)
        )
        return result.scalar_one_or_none()
    
    
    async def get_multi(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions with pagination"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_gym(
        self, 
        db: AsyncSession, 
        gym_id: UUID,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions by gym with pagination"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.gym_id == gym_id)
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_task_identifier(
        self, 
        db: AsyncSession, 
        task_identifier: str,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions by task identifier with pagination"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.task_identifier == task_identifier)
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_model(
        self, 
        db: AsyncSession, 
        model: str,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions by model with pagination"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.model == model)
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_multi_by_execution_type(
        self, 
        db: AsyncSession, 
        execution_type: str,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions by execution_type with pagination"""
        from app.models.execution import ExecutionType
        # Normalize to lowercase and convert to enum
        execution_type_lower = execution_type.lower()
        if execution_type_lower == "batch":
            type_enum = ExecutionType.BATCH
        elif execution_type_lower == "playground":
            type_enum = ExecutionType.PLAYGROUND
        else:
            raise ValueError(f"Invalid execution_type: {execution_type}. Must be 'batch' or 'playground'")
        
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.execution_type == type_enum)
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def count_by_execution_type(self, db: AsyncSession, execution_type: str) -> int:
        """Count executions by execution_type"""
        from app.models.execution import ExecutionType
        # Normalize to lowercase and convert to enum
        execution_type_lower = execution_type.lower()
        if execution_type_lower == "batch":
            type_enum = ExecutionType.BATCH
        elif execution_type_lower == "playground":
            type_enum = ExecutionType.PLAYGROUND
        else:
            raise ValueError(f"Invalid execution_type: {execution_type}. Must be 'batch' or 'playground'")
        
        result = await db.execute(
            select(func.count(Execution.uuid)).where(Execution.execution_type == type_enum)
        )
        return result.scalar()
    
    async def update(
        self, 
        db: AsyncSession, 
        execution_uuid: UUID, 
        execution_data: ExecutionUpdate
    ) -> Optional[Execution]:
        """Update an execution"""
        execution = await self.get(db, execution_uuid)
        if not execution:
            return None
        
        update_data = execution_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(execution, field, value)
        
        await db.commit()
        await db.refresh(execution)
        return execution
    
    async def delete(self, db: AsyncSession, execution_uuid: UUID) -> bool:
        """Delete an execution"""
        execution = await self.get(db, execution_uuid)
        if not execution:
            return False
        
        await db.delete(execution)
        await db.commit()
        return True
    
    async def count(self, db: AsyncSession) -> int:
        """Count total executions"""
        result = await db.execute(select(func.count(Execution.uuid)))
        return result.scalar()
    
    async def count_by_gym(self, db: AsyncSession, gym_id: UUID) -> int:
        """Count executions by gym"""
        result = await db.execute(
            select(func.count(Execution.uuid)).where(Execution.gym_id == gym_id)
        )
        return result.scalar()
    
    async def count_by_task_identifier(self, db: AsyncSession, task_identifier: str) -> int:
        """Count executions by task identifier"""
        result = await db.execute(
            select(func.count(Execution.uuid)).where(Execution.task_identifier == task_identifier)
        )
        return result.scalar()
    
    async def count_by_model(self, db: AsyncSession, model: str) -> int:
        """Count executions by model"""
        result = await db.execute(
            select(func.count(Execution.uuid)).where(Execution.model == model)
        )
        return result.scalar()
    
    async def get_multi_by_batch(
        self, 
        db: AsyncSession, 
        batch_id: UUID,
        skip: int = 0, 
        limit: int = 100
    ) -> List[Execution]:
        """Get multiple executions by batch with pagination"""
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym), selectinload(Execution.batch))
            .where(Execution.batch_id == batch_id)
            .offset(skip)
            .limit(limit)
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def count_by_batch(self, db: AsyncSession, batch_id: UUID) -> int:
        """Count executions by batch"""
        result = await db.execute(
            select(func.count(Execution.uuid)).where(Execution.batch_id == batch_id)
        )
        return result.scalar()
    
    async def get_by_gym_and_date_range(
        self,
        db: AsyncSession,
        gym_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: Optional[int] = None
    ) -> List[Execution]:
        """Get executions by gym with optional date range filter"""
        query = (
            select(Execution)
            .options(selectinload(Execution.gym))
            .where(Execution.gym_id == gym_id)
        )
        
        if start_date:
            query = query.where(Execution.created_at >= start_date)
        if end_date:
            query = query.where(Execution.created_at <= end_date)
        
        query = query.order_by(Execution.created_at.desc()).offset(skip)
        
        if limit:
            query = query.limit(limit)
        
        result = await db.execute(query)
        return result.scalars().all()
    
    async def list_all(self, db: AsyncSession) -> List[Execution]:
        """
        Return all executions (no pagination), newest first.
        NOTE: If you expect a very large table, consider a chunked/streaming variant (see below).
        """
        result = await db.execute(
            select(Execution)
            .options(selectinload(Execution.gym))
            .order_by(Execution.created_at.desc())
        )
        return result.scalars().all()
    
    async def list_all_chunked(self, db: AsyncSession, chunk_size: int = 100):
        """
        Generator that yields executions in chunks to reduce memory usage.
        Use this for large exports to avoid loading all executions at once.
        
        Example:
            async for chunk in execution_crud.list_all_chunked(db, chunk_size=100):
                for execution in chunk:
                    # process execution
        """
        offset = 0
        while True:
            chunk = await self.get_multi(db, skip=offset, limit=chunk_size)
            if not chunk:
                break
            yield chunk
            offset += chunk_size
            
# Create instance
execution_crud = ExecutionCRUD()
