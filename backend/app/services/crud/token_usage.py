"""
CRUD operations for token usage
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_usage import TokenUsage
from app.models.execution import Execution
from app.models.batch import Batch
from app.models.gym import Gym
from app.schemas.token_usage import TokenUsageCreate


class TokenUsageCRUD:
    """CRUD operations for token usage"""
    
    @staticmethod
    async def create(db: AsyncSession, token_usage: TokenUsageCreate) -> TokenUsage:
        """Create a new token usage record"""
        # Populate snapshot fields from execution/batch/gym if available and not provided
        data = token_usage.model_dump()
        exec_id = data.get("execution_id")
        batch_id = data.get("batch_id")
        gym_id = data.get("gym_id")
        batch_name = data.get("batch_name")
        gym_name = data.get("gym_name")
        batch_is_deleted = data.get("batch_is_deleted")

        if exec_id:
            # Fetch execution to derive missing gym_id/batch_id
            exec_result = await db.execute(select(Execution).where(Execution.uuid == exec_id))
            execution = exec_result.scalar_one_or_none()
            if execution:
                if not gym_id:
                    data["gym_id"] = execution.gym_id
                if not batch_id and execution.batch_id:
                    data["batch_id"] = execution.batch_id

        # Fetch batch name if batch_id present and batch_name missing
        if data.get("batch_id") and not batch_name:
            b_result = await db.execute(select(Batch).where(Batch.uuid == data["batch_id"]))
            batch = b_result.scalar_one_or_none()
            if batch:
                data["batch_name"] = batch.name
        # Fetch gym name if gym_id present and gym_name missing
        if data.get("gym_id") and not gym_name:
            g_result = await db.execute(select(Gym).where(Gym.uuid == data["gym_id"]))
            gym = g_result.scalar_one_or_none()
            if gym:
                data["gym_name"] = gym.name
        # Default deleted flag
        if batch_is_deleted is None:
            data["batch_is_deleted"] = False

        db_token_usage = TokenUsage(**data)
        db.add(db_token_usage)
        await db.commit()
        await db.refresh(db_token_usage)
        return db_token_usage
    
    @staticmethod
    async def get_by_id(db: AsyncSession, uuid: UUID) -> Optional[TokenUsage]:
        """Get token usage by UUID"""
        result = await db.execute(select(TokenUsage).where(TokenUsage.uuid == uuid))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_iteration(db: AsyncSession, iteration_id: UUID) -> List[TokenUsage]:
        """Get all token usage records for an iteration"""
        result = await db.execute(
            select(TokenUsage).where(TokenUsage.iteration_id == iteration_id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_by_execution(db: AsyncSession, execution_id: UUID) -> List[TokenUsage]:
        """Get all token usage records for an execution"""
        result = await db.execute(
            select(TokenUsage).where(TokenUsage.execution_id == execution_id)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        model_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        gym_id: Optional[UUID] = None,
        batch_id: Optional[UUID] = None
    ) -> List[TokenUsage]:
        """Get all token usage records with optional filters"""
        query = select(TokenUsage)
        
        filters = []
        if model_name:
            filters.append(TokenUsage.model_name == model_name)
        if start_date:
            filters.append(TokenUsage.created_at >= start_date)
        if end_date:
            filters.append(TokenUsage.created_at <= end_date)
        # Join to executions if we need to filter by gym or batch via execution
        if gym_id or batch_id:
            query = query.join(Execution, TokenUsage.execution_id == Execution.uuid, isouter=True)
        if gym_id:
            # Use snapshot gym_id or execution gym_id (handles deleted executions)
            filters.append(or_(TokenUsage.gym_id == gym_id, Execution.gym_id == gym_id))
        if batch_id:
            # Match either the token_usage snapshot batch_id or the execution's batch_id
            filters.append(or_(TokenUsage.batch_id == batch_id, Execution.batch_id == batch_id))
        
        if filters:
            query = query.where(and_(*filters))
        
        query = query.offset(skip).limit(limit).order_by(TokenUsage.created_at.desc())
        
        result = await db.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_aggregated_stats(
        db: AsyncSession,
        model_name: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        execution_id: Optional[UUID] = None,
        gym_id: Optional[UUID] = None,
        batch_id: Optional[UUID] = None
    ) -> dict:
        """Get aggregated token usage statistics"""
        filters = []
        if model_name:
            filters.append(TokenUsage.model_name == model_name)
        if start_date:
            filters.append(TokenUsage.created_at >= start_date)
        if end_date:
            filters.append(TokenUsage.created_at <= end_date)
        if execution_id:
            filters.append(TokenUsage.execution_id == execution_id)
        # Build base query
        query = select(
            TokenUsage.model_name,
            func.string_agg(func.distinct(TokenUsage.model_version), ', ').label('model_versions'),
            func.sum(TokenUsage.input_tokens).label('total_input_tokens'),
            func.sum(TokenUsage.output_tokens).label('total_output_tokens'),
            func.sum(TokenUsage.total_tokens).label('total_tokens'),
            func.sum(TokenUsage.api_calls_count).label('total_api_calls'),
            func.sum(TokenUsage.cached_tokens).label('total_cached_tokens'),
            func.sum(TokenUsage.estimated_cost_usd).label('total_estimated_cost_usd'),
            func.count(func.distinct(TokenUsage.execution_id)).label('execution_count'),
            func.count(func.distinct(TokenUsage.iteration_id)).label('iteration_count'),
            func.min(TokenUsage.created_at).label('first_usage'),
            func.max(TokenUsage.created_at).label('last_usage')
        ).group_by(TokenUsage.model_name)
        # Join if gym or batch filters are present
        if gym_id or batch_id:
            query = query.join(Execution, TokenUsage.execution_id == Execution.uuid, isouter=True)
        if gym_id:
            filters.append(or_(TokenUsage.gym_id == gym_id, Execution.gym_id == gym_id))
        if batch_id:
            filters.append(or_(TokenUsage.batch_id == batch_id, Execution.batch_id == batch_id))
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await db.execute(query)
        rows = result.all()
        
        # Convert to dictionary
        stats_by_model = {}
        for row in rows:
            avg_tokens_per_iteration = row.total_tokens / row.iteration_count if row.iteration_count > 0 else 0
            avg_tokens_per_api_call = row.total_tokens / row.total_api_calls if row.total_api_calls > 0 else 0
            avg_input_per_api_call = row.total_input_tokens / row.total_api_calls if row.total_api_calls > 0 else 0
            avg_output_per_api_call = row.total_output_tokens / row.total_api_calls if row.total_api_calls > 0 else 0
            
            stats_by_model[row.model_name] = {
                'model_name': row.model_name,
                'model_versions': row.model_versions or 'Unknown',
                'total_input_tokens': row.total_input_tokens or 0,
                'total_output_tokens': row.total_output_tokens or 0,
                'total_tokens': row.total_tokens or 0,
                'total_api_calls': row.total_api_calls or 0,
                'total_cached_tokens': row.total_cached_tokens or 0,
                'total_estimated_cost_usd': float(row.total_estimated_cost_usd or 0),
                'execution_count': row.execution_count,
                'iteration_count': row.iteration_count,
                'average_tokens_per_iteration': avg_tokens_per_iteration,
                'average_tokens_per_api_call': avg_tokens_per_api_call,
                'average_input_tokens_per_api_call': avg_input_per_api_call,
                'average_output_tokens_per_api_call': avg_output_per_api_call,
                'first_usage': row.first_usage,
                'last_usage': row.last_usage
            }
        
        # Calculate overall totals
        total_tokens = sum(s['total_tokens'] for s in stats_by_model.values())
        total_cost = sum(s['total_estimated_cost_usd'] for s in stats_by_model.values())
        total_api_calls = sum(s['total_api_calls'] for s in stats_by_model.values())
        
        return {
            'total_tokens': total_tokens,
            'total_cost_usd': total_cost,
            'total_api_calls': total_api_calls,
            'by_model': stats_by_model,
            'time_range_start': start_date,
            'time_range_end': end_date
        }
    
    @staticmethod
    async def get_daily_breakdown(
        db: AsyncSession,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model_name: Optional[str] = None,
        gym_id: Optional[UUID] = None,
        batch_id: Optional[UUID] = None
    ) -> List[dict]:
        """Get daily breakdown of token usage"""
        filters = []
        if start_date:
            filters.append(TokenUsage.created_at >= start_date)
        if end_date:
            filters.append(TokenUsage.created_at <= end_date)
        if model_name:
            filters.append(TokenUsage.model_name == model_name)
        # Join if we need to filter by gym or batch
        join_execution = gym_id is not None or batch_id is not None
        
        # Group by date (truncate to day)
        query = select(
            func.date(TokenUsage.created_at).label('date'),
            TokenUsage.model_name,
            func.sum(TokenUsage.input_tokens).label('input_tokens'),
            func.sum(TokenUsage.output_tokens).label('output_tokens'),
            func.sum(TokenUsage.total_tokens).label('total_tokens'),
            func.sum(TokenUsage.api_calls_count).label('api_calls'),
            func.sum(TokenUsage.estimated_cost_usd).label('cost_usd')
        ).group_by(
            func.date(TokenUsage.created_at),
            TokenUsage.model_name
        ).order_by(
            func.date(TokenUsage.created_at).desc()
        )
        if join_execution:
            query = query.join(Execution, TokenUsage.execution_id == Execution.uuid, isouter=True)
        if gym_id:
            filters.append(or_(TokenUsage.gym_id == gym_id, Execution.gym_id == gym_id))
        if batch_id:
            filters.append(or_(TokenUsage.batch_id == batch_id, Execution.batch_id == batch_id))
        
        if filters:
            query = query.where(and_(*filters))
        
        result = await db.execute(query)
        rows = result.all()
        
        return [
            {
                'date': str(row.date),
                'model_name': row.model_name,
                'input_tokens': row.input_tokens or 0,
                'output_tokens': row.output_tokens or 0,
                'total_tokens': row.total_tokens or 0,
                'api_calls': row.api_calls or 0,
                'cost_usd': float(row.cost_usd or 0)
            }
            for row in rows
        ]
    
    @staticmethod
    async def delete(db: AsyncSession, uuid: UUID) -> bool:
        """Delete a token usage record"""
        result = await db.execute(select(TokenUsage).where(TokenUsage.uuid == uuid))
        token_usage = result.scalar_one_or_none()
        
        if token_usage:
            await db.delete(token_usage)
            await db.commit()
            return True
        return False

