"""
Monitoring endpoints for token usage and cost tracking
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.token_usage import (
    TokenUsageResponse,
    TokenUsageSummary,
    TokenUsageReport,
    TokenUsageStatsRequest
)
from app.services.crud.token_usage import TokenUsageCRUD


router = APIRouter()
token_usage_crud = TokenUsageCRUD()


@router.get("/usage/summary", response_model=TokenUsageSummary)
async def get_usage_summary(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    execution_id: Optional[UUID] = Query(None, description="Filter by execution ID"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary of token usage across all models.
    
    This endpoint provides aggregated statistics including:
    - Total tokens used
    - Total estimated cost
    - Total API calls
    - Breakdown by model
    """
    stats = await token_usage_crud.get_aggregated_stats(
        db=db,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        execution_id=execution_id,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    return TokenUsageSummary(**stats)


@router.get("/usage/daily", response_model=List[dict])
async def get_daily_usage(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get daily breakdown of token usage.
    
    Returns token usage aggregated by day and model.
    """
    daily_stats = await token_usage_crud.get_daily_breakdown(
        db=db,
        start_date=start_date,
        end_date=end_date,
        model_name=model_name,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    return daily_stats


@router.get("/usage/report", response_model=TokenUsageReport)
async def generate_usage_report(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a comprehensive usage report.
    
    This endpoint generates a detailed report including:
    - Overall summary
    - Daily breakdown
    - Model breakdown
    - Execution breakdown
    """
    # Get summary stats
    summary_stats = await token_usage_crud.get_aggregated_stats(
        db=db,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    # Get daily breakdown
    daily_breakdown = await token_usage_crud.get_daily_breakdown(
        db=db,
        start_date=start_date,
        end_date=end_date,
        model_name=model_name,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    # Create model breakdown from summary
    model_breakdown = [
        {
            'model_name': model,
            **stats
        }
        for model, stats in summary_stats['by_model'].items()
    ]
    
    # Get execution breakdown (top executions by token usage)
    usage_records = await token_usage_crud.get_all(
        db=db,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        gym_id=gym_id,
        batch_id=batch_id,
        limit=100
    )
    
    # Aggregate by execution
    execution_map = {}
    for record in usage_records:
        exec_id = str(record.execution_id)
        if exec_id not in execution_map:
            execution_map[exec_id] = {
                'execution_id': exec_id,
                'model_name': record.model_name,
                'total_tokens': 0,
                'total_cost_usd': 0,
                'api_calls': 0
            }
        execution_map[exec_id]['total_tokens'] += record.total_tokens
        execution_map[exec_id]['total_cost_usd'] += record.estimated_cost_usd or 0
        execution_map[exec_id]['api_calls'] += record.api_calls_count
    
    execution_breakdown = sorted(
        execution_map.values(),
        key=lambda x: x['total_tokens'],
        reverse=True
    )[:20]  # Top 20 executions
    
    return TokenUsageReport(
        summary=TokenUsageSummary(**summary_stats),
        daily_breakdown=daily_breakdown,
        model_breakdown=model_breakdown,
        execution_breakdown=execution_breakdown,
        generated_at=datetime.now()
    )

@router.get("/usage/gyms", response_model=List[dict])
async def get_usage_gyms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get distinct gyms from token_usage snapshots.
    """
    from sqlalchemy import select, func
    from app.models.token_usage import TokenUsage
    result = await db.execute(
        select(
            TokenUsage.gym_id,
            func.max(TokenUsage.gym_name).label("gym_name")
        ).where(TokenUsage.gym_id.is_not(None)
        ).group_by(TokenUsage.gym_id
        ).order_by(func.max(TokenUsage.gym_name))
    )
    rows = result.all()
    return [
        {
            "gym_id": str(r.gym_id),
            "gym_name": r.gym_name or "Unknown Gym"
        }
        for r in rows
    ]

@router.get("/usage/batches", response_model=List[dict])
async def get_usage_batches(
    gym_id: Optional[UUID] = Query(None, description="Filter batches by gym ID (from snapshots)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get distinct batches with optional gym filter.
    
    Includes:
    - Snapshot batches from token_usage (preserves deleted batches)
    - Live batches from batches table (so brand-new batches appear before any usage)
    """
    from sqlalchemy import select, func, and_
    from app.models.token_usage import TokenUsage
    from app.models.batch import Batch
    
    # 1) Snapshot batches from token_usage
    filters = []
    if gym_id:
        filters.append(TokenUsage.gym_id == gym_id)
    query = select(
        TokenUsage.batch_id,
        func.max(TokenUsage.batch_name).label("batch_name"),
        func.bool_or(TokenUsage.batch_is_deleted).label("batch_is_deleted")
    ).where(
        TokenUsage.batch_id.is_not(None)
    ).group_by(
        TokenUsage.batch_id
    ).order_by(func.max(TokenUsage.batch_name))
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query)
    snapshot_rows = result.all()
    merged: dict[str, dict] = {}
    for r in snapshot_rows:
        if r.batch_id:
            merged[str(r.batch_id)] = {
                "batch_id": str(r.batch_id),
                "batch_name": r.batch_name or "Unknown Batch",
                "batch_is_deleted": bool(r.batch_is_deleted),
            }
    
    # 2) Live batches from batches table (ensure new batches show up)
    live_query = select(Batch.uuid, Batch.name)
    if gym_id:
        live_query = live_query.where(Batch.gym_id == gym_id)
    live_result = await db.execute(live_query)
    for uuid_val, name_val in live_result.all():
        key = str(uuid_val)
        if key not in merged:
            merged[key] = {
                "batch_id": key,
                "batch_name": name_val or "Unknown Batch",
                "batch_is_deleted": False,
            }
    
    # Return sorted list by name
    return sorted(merged.values(), key=lambda x: (x["batch_name"] or "").lower())


@router.get("/usage/execution/{execution_id}", response_model=List[TokenUsageResponse])
async def get_execution_usage(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get token usage for a specific execution.
    
    Returns all token usage records associated with the given execution.
    """
    usage_records = await token_usage_crud.get_by_execution(db, execution_id)
    
    if not usage_records:
        raise HTTPException(status_code=404, detail="No usage records found for this execution")
    
    return usage_records


@router.get("/usage/iteration/{iteration_id}", response_model=List[TokenUsageResponse])
async def get_iteration_usage(
    iteration_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get token usage for a specific iteration.
    
    Returns all token usage records associated with the given iteration.
    """
    usage_records = await token_usage_crud.get_by_iteration(db, iteration_id)
    
    if not usage_records:
        raise HTTPException(status_code=404, detail="No usage records found for this iteration")
    
    return usage_records


@router.get("/usage/models", response_model=List[str])
async def get_available_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of all models that have usage records.
    
    Returns a list of unique model names that have been tracked.
    """
    # Get all usage records (just model names)
    usage_records = await token_usage_crud.get_all(db, limit=10000)
    
    # Extract unique model names
    models = sorted(set(record.model_name for record in usage_records))
    
    return models


@router.get("/usage/all", response_model=List[TokenUsageResponse])
async def get_all_usage(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all token usage records with pagination and filtering.
    
    Supports filtering by:
    - Model name
    - Date range
    - Pagination (skip/limit)
    """
    usage_records = await token_usage_crud.get_all(
        db=db,
        skip=skip,
        limit=limit,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    return usage_records


@router.get("/usage/cost-breakdown", response_model=dict)
async def get_cost_breakdown(
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get cost breakdown by model and time period.
    
    Returns detailed cost analysis including:
    - Total cost per model
    - Cost trends over time
    - Cost per API call
    - Cost per 1K tokens
    """
    stats = await token_usage_crud.get_aggregated_stats(
        db=db,
        start_date=start_date,
        end_date=end_date,
        gym_id=gym_id,
        batch_id=batch_id
    )
    
    cost_analysis = {
        'total_cost_usd': stats['total_cost_usd'],
        'models': []
    }
    
    for model_name, model_stats in stats['by_model'].items():
        total_tokens = model_stats['total_tokens']
        total_cost = model_stats['total_estimated_cost_usd']
        api_calls = model_stats['total_api_calls']
        
        cost_analysis['models'].append({
            'model_name': model_name,
            'total_cost_usd': total_cost,
            'total_tokens': total_tokens,
            'api_calls': api_calls,
            'cost_per_call': total_cost / api_calls if api_calls > 0 else 0,
            'cost_per_1k_tokens': (total_cost / total_tokens * 1000) if total_tokens > 0 else 0,
            'percentage_of_total': (total_cost / stats['total_cost_usd'] * 100) if stats['total_cost_usd'] > 0 else 0
        })
    
    # Sort by cost descending
    cost_analysis['models'] = sorted(
        cost_analysis['models'],
        key=lambda x: x['total_cost_usd'],
        reverse=True
    )
    
    return cost_analysis


@router.get("/usage/export/csv")
async def export_usage_csv(
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    batch_id: Optional[UUID] = Query(None, description="Filter by batch ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export token usage data as CSV.
    
    Downloads a CSV file containing all token usage records with the applied filters.
    """
    import csv
    from io import StringIO
    
    usage_records = await token_usage_crud.get_all(
        db=db,
        model_name=model_name,
        start_date=start_date,
        end_date=end_date,
        gym_id=gym_id,
        batch_id=batch_id,
        limit=10000  # Max export limit
    )
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'UUID', 'Model', 'Model Version', 'Execution ID', 'Iteration ID',
        'Input Tokens', 'Output Tokens', 'Total Tokens', 
        'API Calls', 'Cached Tokens',
        'Created At'
    ])
    
    # Write data
    for record in usage_records:
        writer.writerow([
            str(record.uuid),
            record.model_name,
            record.model_version or '',
            str(record.execution_id),
            str(record.iteration_id),
            record.input_tokens,
            record.output_tokens,
            record.total_tokens,
            record.api_calls_count,
            record.cached_tokens or 0,
            record.created_at.isoformat()
        ])
    
    # Return CSV as response
    csv_content = output.getvalue()
    output.close()
    
    filename = f"token_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

