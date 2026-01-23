"""
Leaderboard endpoints - provides fail percentage statistics
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.iteration import Iteration
from app.models.execution import Execution
from app.models.batch import Batch
from app.models.gym import Gym
from app.schemas.leaderboard import (
    LeaderboardResponse,
    LeaderboardGymStats,
    LeaderboardModelGymStats,
    LeaderboardModelStats,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=LeaderboardResponse)
@router.get("", response_model=LeaderboardResponse)
async def get_leaderboard(
    batch_ids: Optional[List[UUID]] = Query(
        None, description="Filter by specific batch UUIDs"
    ),
    start_date: Optional[datetime] = Query(
        None, description="Start date for batch creation date filter (ISO format)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="End date for batch creation date filter (ISO format)"
    ),
    gym_ids: Optional[List[UUID]] = Query(
        None, description="Filter by specific gym UUIDs"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get leaderboard statistics showing fail percentage of iterations.
    
    Only includes iterations with status 'passed' or 'failed' (excludes pending, executing, crashed, timeout).
    
    Filters:
    - batch_ids: Filter by specific batch UUIDs
    - start_date/end_date: Filter batches by creation date range
    - gym_ids: Filter by specific gym UUIDs
    
    Returns overall fail percentage and per-gym fail percentages.
    """
    try:
        # Build base query: join iterations -> executions -> batches -> gyms
        # Only include iterations with status 'passed' or 'failed'
        base_query = (
            select(
                Iteration.status,
                Gym.uuid.label("gym_id"),
                Gym.name.label("gym_name"),
                Execution.model.label("model"),
            )
            .join(Execution, Iteration.execution_id == Execution.uuid)
            .join(Batch, Execution.batch_id == Batch.uuid)
            .join(Gym, Batch.gym_id == Gym.uuid)
            .where(
                Iteration.status.in_(["passed", "failed"])
            )
        )

        # Apply filters
        conditions = []

        # Filter by batch_ids
        if batch_ids:
            conditions.append(Batch.uuid.in_(batch_ids))

        # Filter by date range (batch creation date)
        if start_date:
            conditions.append(Batch.created_at >= start_date)
        if end_date:
            conditions.append(Batch.created_at <= end_date)

        # Filter by gym_ids
        if gym_ids:
            conditions.append(Gym.uuid.in_(gym_ids))

        if conditions:
            base_query = base_query.where(and_(*conditions))

        # Execute query to get all matching iterations
        result = await db.execute(base_query)
        rows = result.all()

        if not rows:
            # No data found, return empty response
            return LeaderboardResponse(
                overall_passed_count=0,
                overall_failed_count=0,
                overall_total_count=0,
                overall_fail_percentage=0.0,
                gym_stats=[],
                model_gym_stats=[],
                model_stats=[],
            )

        # Aggregate data
        overall_passed = 0
        overall_failed = 0
        gym_data = {}  # gym_id -> {name, passed, failed}
        model_gym_data = {}  # (model, gym_id) -> {gym_name, passed, failed}
        model_data = {}  # model -> {passed, failed}

        for row in rows:
            status = row.status
            gym_id = str(row.gym_id)
            gym_name = row.gym_name
            model = row.model or "unknown"

            # Initialize gym data if not exists
            if gym_id not in gym_data:
                gym_data[gym_id] = {"name": gym_name, "passed": 0, "failed": 0}

            # Initialize model-gym data if not exists
            model_gym_key = (model, gym_id)
            if model_gym_key not in model_gym_data:
                model_gym_data[model_gym_key] = {
                    "gym_name": gym_name,
                    "passed": 0,
                    "failed": 0,
                }

            # Initialize model data if not exists
            if model not in model_data:
                model_data[model] = {"passed": 0, "failed": 0}

            # Count overall
            if status == "passed":
                overall_passed += 1
                gym_data[gym_id]["passed"] += 1
                model_gym_data[model_gym_key]["passed"] += 1
                model_data[model]["passed"] += 1
            elif status == "failed":
                overall_failed += 1
                gym_data[gym_id]["failed"] += 1
                model_gym_data[model_gym_key]["failed"] += 1
                model_data[model]["failed"] += 1

        # Calculate overall fail percentage
        overall_total = overall_passed + overall_failed
        overall_fail_percentage = (
            (overall_failed / overall_total * 100) if overall_total > 0 else 0.0
        )

        # Build gym stats
        gym_stats = []
        for gym_id, data in gym_data.items():
            total = data["passed"] + data["failed"]
            fail_percentage = (data["failed"] / total * 100) if total > 0 else 0.0

            gym_stats.append(
                LeaderboardGymStats(
                    gym_id=gym_id,
                    gym_name=data["name"],
                    passed_count=data["passed"],
                    failed_count=data["failed"],
                    total_count=total,
                    fail_percentage=round(fail_percentage, 2),
                )
            )

        # Sort gym stats by fail percentage (descending)
        gym_stats.sort(key=lambda x: x.fail_percentage, reverse=True)

        # Build model-gym stats
        model_gym_stats = []
        for (model, gym_id), data in model_gym_data.items():
            total = data["passed"] + data["failed"]
            fail_percentage = (data["failed"] / total * 100) if total > 0 else 0.0

            model_gym_stats.append(
                LeaderboardModelGymStats(
                    model=model,
                    gym_id=gym_id,
                    gym_name=data["gym_name"],
                    passed_count=data["passed"],
                    failed_count=data["failed"],
                    total_count=total,
                    fail_percentage=round(fail_percentage, 2),
                )
            )

        # Sort model-gym stats by gym_name, then by model
        model_gym_stats.sort(key=lambda x: (x.gym_name, x.model))

        # Build model stats (overall)
        model_stats = []
        for model, data in model_data.items():
            total = data["passed"] + data["failed"]
            fail_percentage = (data["failed"] / total * 100) if total > 0 else 0.0

            model_stats.append(
                LeaderboardModelStats(
                    model=model,
                    passed_count=data["passed"],
                    failed_count=data["failed"],
                    total_count=total,
                    fail_percentage=round(fail_percentage, 2),
                )
            )

        # Sort model stats by fail percentage (descending)
        model_stats.sort(key=lambda x: x.fail_percentage, reverse=True)

        return LeaderboardResponse(
            overall_passed_count=overall_passed,
            overall_failed_count=overall_failed,
            overall_total_count=overall_total,
            overall_fail_percentage=round(overall_fail_percentage, 2),
            gym_stats=gym_stats,
            model_gym_stats=model_gym_stats,
            model_stats=model_stats,
        )

    except Exception as e:
        logger.error(f"Error fetching leaderboard data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch leaderboard: {str(e)}")

