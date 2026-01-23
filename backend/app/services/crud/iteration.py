"""
CRUD operations for Iteration model
"""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.iteration import Iteration
from app.schemas.iteration import (IterationCreate, IterationStatus,
                                   IterationUpdate)


class IterationCRUD:
    """CRUD operations for Iteration model"""
    
    async def create(self, db: AsyncSession, obj_in: IterationCreate) -> Iteration:
        """Create a new iteration"""
        iteration = Iteration(**obj_in.model_dump())
        db.add(iteration)
        await db.commit()
        await db.refresh(iteration)
        return iteration
    
    async def get(self, db: AsyncSession, iteration_uuid: UUID) -> Optional[Iteration]:
        """Get an iteration by UUID"""
        result = await db.execute(
            select(Iteration)
            .options(selectinload(Iteration.execution))  # task relationship removed
            .where(Iteration.uuid == iteration_uuid)
        )
        return result.scalar_one_or_none()
    
    async def update(self, db: AsyncSession, db_obj: Iteration, obj_in: Union[IterationUpdate, dict]) -> Iteration:
        """Update an iteration"""
        if hasattr(obj_in, 'model_dump'):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            # obj_in is already a dictionary
            update_data = obj_in
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj
    
    async def get_by_execution_id(
        self,
        db: AsyncSession,
        execution_id: UUID,
        skip: int = 0,
        limit: Optional[int] = None
    ) -> List[Iteration]:
        """Get all iterations for a specific execution"""
        query = select(Iteration).where(
            Iteration.execution_id == execution_id
        ).order_by(Iteration.iteration_number).offset(skip)
        if limit is not None:
            query = query.limit(limit)

        result = await db.execute(query)
        return result.scalars().all()
    
    # DEPRECATED: task_id removed from iterations
    # Use execution.task_identifier to filter iterations by task
    # async def get_by_task_id(
    #     self, 
    #     db: AsyncSession, 
    #     task_id: UUID,
    #     skip: int = 0,
    #     limit: int = 100
    # ) -> List[Iteration]:
    #     """Get all iterations for a specific task"""
    #     # This method is deprecated as iterations no longer have task_id
    #     # Query iterations through their parent executions instead
    #     raise NotImplementedError("Use execution.task_identifier to filter iterations")
    
    async def get_by_celery_task_id(
        self, 
        db: AsyncSession, 
        celery_task_id: str
    ) -> Optional[Iteration]:
        """Get iteration by Celery task ID"""
        query = select(Iteration).where(
            Iteration.celery_task_id == celery_task_id
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_execution_and_iteration_number(
        self, 
        db: AsyncSession, 
        execution_id: UUID,
        iteration_number: int
    ) -> Optional[Iteration]:
        """Get specific iteration by execution ID and iteration number"""
        query = select(Iteration).where(
            and_(
                Iteration.execution_id == execution_id,
                Iteration.iteration_number == iteration_number
            )
        )
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_execution_summary(
        self, 
        db: AsyncSession, 
        execution_id: UUID
    ) -> Dict[str, Any]:
        """Get summary statistics for an execution"""
        query = select(
            func.count(Iteration.uuid).label('total_iterations'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.PENDING).label('pending_count'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.EXECUTING).label('executing_count'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.PASSED).label('passed_count'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.FAILED).label('failed_count'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.CRASHED).label('crashed_count'),
            func.count(Iteration.uuid).filter(Iteration.status == IterationStatus.TIMEOUT).label('timeout_count'),
            func.avg(Iteration.execution_time_seconds).label('avg_execution_time')
        ).where(Iteration.execution_id == execution_id)
        
        result = await db.execute(query)
        row = result.first()
        
        return {
            'total_iterations': row.total_iterations or 0,
            'pending_count': row.pending_count or 0,
            'executing_count': row.executing_count or 0,
            'passed_count': row.passed_count or 0,
            'failed_count': row.failed_count or 0,
            'crashed_count': row.crashed_count or 0,
            'timeout_count': row.timeout_count or 0,
            'avg_execution_time': float(row.avg_execution_time) if row.avg_execution_time else None
        }
    
    async def update_status(
        self, 
        db: AsyncSession, 
        iteration_id: UUID,
        status: IterationStatus,
        **kwargs
    ) -> Optional[Iteration]:
        """Update iteration status and other fields"""
        iteration = await self.get(db, iteration_id)
        if not iteration:
            return None
        
        update_data = {"status": status}
        update_data.update(kwargs)
        
        return await self.update(db, db_obj=iteration, obj_in=update_data)
    
    async def create_batch(
        self, 
        db: AsyncSession, 
        execution_id: UUID,
        number_of_iterations: int,
        task_id: UUID = None  # Deprecated - kept for backwards compatibility but not used
    ) -> List[Iteration]:
        """Create multiple iterations for an execution
        
        Note: task_id parameter is deprecated. Iterations get task info from their parent execution.
        """
        iterations = []
        
        for i in range(1, number_of_iterations + 1):
            iteration_data = IterationCreate(
                execution_id=execution_id,
                iteration_number=i,
                status=IterationStatus.PENDING
            )
            iteration = await self.create(db, obj_in=iteration_data)
            iterations.append(iteration)
        
        return iterations
    
    async def get_with_relationships(
        self, 
        db: AsyncSession, 
        iteration_id: UUID
    ) -> Optional[Iteration]:
        """Get iteration with related execution data"""
        query = select(Iteration).options(
            selectinload(Iteration.execution)  # task relationship removed
        ).where(Iteration.uuid == iteration_id)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()

# Create instance
iteration_crud = IterationCRUD()
