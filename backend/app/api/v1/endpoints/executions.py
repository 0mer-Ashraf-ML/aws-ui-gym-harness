"""
Execution management endpoints
"""

import asyncio
import json, time, re
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (get_current_user, get_current_user_from_token,
                           get_current_user_optional)
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.execution import (
    ExecutionCreate,
    ExecutionListResponse,
    ExecutionResponse,
    ExecutionResponseWithStatus,
    ExecutionType,
    ExecutionUpdate,
)
from app.services.crud.execution import execution_crud
from app.services.crud.gym import gym_crud
from app.services.crud.iteration import iteration_crud
from app.services.crud.task import task_crud
from app.services.execution_status_manager import ExecutionStatusManager
from app.services.reports.execution_report import (
    generate_execution_report,
    generate_combined_report,
    _build_summary,
    _build_snapshot,
    _write_workbook,
    _write_json_snapshot,
    MODEL_ORDER,
    RUNNER_MODELS,
    _extract_record_model_response,
    _extract_record_status,
    _extract_record_tool_usage,
    _format_seconds,
)
# Internal helpers
from app.services.reports.execution_report import collect_execution_data, IterationRecord
from app.services.action_timeline_parser import timeline_parser
from app.services.action_timeline_storage import timeline_storage
from app.schemas.action_timeline import TimelineResponse
from app.services.archive_service import archive_service

logger = logging.getLogger(__name__)
router = APIRouter()
# Helper function to convert seconds to H:M:S format
def _hms(seconds: float) -> str:
    """Convert seconds to H:M:S format"""
    if not seconds or seconds <= 0:
        return "0:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


async def _aggregate_task_data(
    task_id: str,
    iterations: Dict[str, Any],
    gym_id: UUID,
    db: AsyncSession,
    include_model_breaking: bool = False,
    execution_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Aggregate data across iterations for a single task.
    
    Args:
        task_id: Task identifier
        iterations: Dictionary of iterations for this task
        gym_id: Gym UUID for fetching task details
        db: Database session
        include_model_breaking: Whether to include model breaking columns
        execution_model: Model used for this execution (for breaking columns)
    
    Returns:
        Dictionary with aggregated task data
    """
    total_attempts = 0
    total_time_mins = 0.0
    total_timelapse_secs = 0.0
    iteration_count = 0
    failure_iterations = 0
    pass_count = 0
    prompt = None
    
    # Model tracking (if requested) - track all 2 models
    openai_total = 0
    openai_failed = 0
    anthropic_total = 0
    anthropic_failed = 0
    
    # Fetch task prompt
    try:
        task_result = await task_crud.get_by_task_id_and_gym(db, task_id, gym_id)
        if task_result:
            prompt = task_result.prompt
    except Exception as e:
        logger.error(f"Error fetching prompt for task {task_id}: {e}")
    
    # Process iterations
    for iter_key, verification in iterations.items():
        if not verification:
            verification = {}
        
        attempts = verification.get("execution_steps", 0)
        status = verification.get("verification_status") or verification.get("status") or verification.get("_iteration_status") or "pending"
        status_upper = str(status).upper()

        if status_upper not in {"PASSED", "FAILED"}:
            continue

        # Get execution time from multiple sources
        exec_secs = (
            verification.get("_iteration_execution_time_seconds") or
            verification.get("execution_time") or
            0.0
        )
        time_mins = exec_secs / 60.0 if exec_secs else 0.0
        
        # Get timestamps for timelapse
        start_ts = verification.get("_iteration_started_at") or verification.get("start_time") or 0
        end_ts = verification.get("_iteration_completed_at") or verification.get("end_time") or 0
        if start_ts and end_ts:
            elapsed = float(end_ts - start_ts)
            total_timelapse_secs += elapsed
        
        # Track model failures if requested
        if status_upper == "PASSED":
            pass_count += 1

        is_failed = status_upper in {"FAILED", "TIMEOUT", "ERROR"}
        
        if is_failed:
            failure_iterations += 1

        if include_model_breaking and execution_model:
            model_lower = execution_model.lower()

            if "openai" in model_lower or "gpt" in model_lower:
                openai_total += 1
                if is_failed:
                    openai_failed += 1
            
            if "anthropic" in model_lower or "claude" in model_lower:
                anthropic_total += 1
                if is_failed:
                    anthropic_failed += 1
        
        total_attempts += int(attempts or 0)
        total_time_mins += time_mins
        iteration_count += 1
    
    # Calculate difficulty (execution success driven)
    if iteration_count == 0:
        difficulty = "Unknown"
    else:
        pass_ratio = pass_count / iteration_count
        if pass_ratio == 1.0:
            difficulty = "Easy"
        elif pass_ratio > 0.4:
            difficulty = "Medium"
        else:
            difficulty = "Hard"
    
    avg_time = round(total_time_mins / iteration_count, 2) if iteration_count else 0.0
    total_timelapse_str = _hms(total_timelapse_secs) if total_timelapse_secs else None
    
    # Build result
    result = {
        "task_id": task_id,
        "prompt": prompt,
        "difficulty": difficulty,
        "total_time_mins": round(total_time_mins, 2),
        "avg_iteration_time_mins": avg_time,
        "total_timelapse": total_timelapse_str,
        "iteration_count": iteration_count,
        "total_attempts": total_attempts
    }
    
    # Add model breaking columns if requested (all 3 models)
    if include_model_breaking:
        # OpenAI Computer Use Preview
        if openai_total == 0:
            openai_status = "Not Tested"
        elif openai_failed > 0:
            openai_status = f"Yes, {openai_failed}/{openai_total}"
        else:
            openai_status = f"No, 0/{openai_total}"
        
        # Anthropic Claude
        if anthropic_total == 0:
            anthropic_status = "Not Tested"
        elif anthropic_failed > 0:
            anthropic_status = f"Yes, {anthropic_failed}/{anthropic_total}"
        else:
            anthropic_status = f"No, 0/{anthropic_total}"
        
        result["openai_breaking"] = openai_status
        result["anthropic_breaking"] = anthropic_status
    
    return result


async def calculate_execution_durations_bulk(
    execution_ids: List[UUID], 
    db: AsyncSession
) -> Dict[UUID, float]:
    """Calculate execution durations for multiple executions in a single query.
    
    Sums execution_time_seconds from all iterations for each execution.
    For running iterations without execution_time_seconds, calculates from started_at to NOW().
    For crashed iterations with timestamps but no execution_time_seconds, calculates completed_at - started_at.
    Returns a dictionary mapping execution_id to duration_seconds.
    """
    from sqlalchemy import func, case, select, and_
    from app.models.iteration import Iteration
    
    if not execution_ids:
        return {}
    
    # Single query to sum execution_time_seconds for all executions
    # Priority: 1) execution_time_seconds, 2) NOW() - started_at for running iterations,
    # 3) completed_at - started_at for crashed iterations with timestamps
    query = select(
        Iteration.execution_id,
        func.sum(
            func.coalesce(
                Iteration.execution_time_seconds,
                case(
                    (
                        Iteration.status.in_(['pending', 'executing']),
                        func.extract('epoch', func.now() - Iteration.started_at)
                    ),
                    (
                        # Handle crashed iterations with timestamps but no execution_time_seconds
                        and_(
                            Iteration.status == 'crashed',
                            Iteration.started_at.isnot(None),
                            Iteration.completed_at.isnot(None),
                            Iteration.execution_time_seconds.is_(None)
                        ),
                        func.extract('epoch', Iteration.completed_at - Iteration.started_at)
                    ),
                    else_=None
                )
            )
        ).label('total_duration')
    ).where(
        Iteration.execution_id.in_(execution_ids)
    ).group_by(Iteration.execution_id)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build dictionary mapping execution_id to duration
    durations = {}
    for row in rows:
        if row.total_duration is not None:
            durations[row.execution_id] = max(0.0, float(row.total_duration))
    
    return durations


async def calculate_execution_duration(execution_id: UUID, db: AsyncSession) -> Optional[float]:
    """Calculate execution duration in seconds as the sum of all iteration execution times.
    
    Sums execution_time_seconds from all iterations.
    For running iterations without execution_time_seconds, calculates from started_at to NOW().
    Returns None if no iterations exist.
    """
    # Use bulk function for single execution
    durations = await calculate_execution_durations_bulk([execution_id], db)
    return durations.get(execution_id)


async def create_execution_response(
    execution, 
    db: AsyncSession, 
    durations_cache: Optional[Dict[UUID, float]] = None
) -> ExecutionResponse:
    """Create an ExecutionResponse with computed status from iterations"""
    # Compute status from iterations
    computed_status = await ExecutionStatusManager.update_execution_status_from_iterations(str(execution.uuid))
    
    # Calculate execution duration (use cache if provided, otherwise calculate)
    if durations_cache and execution.uuid in durations_cache:
        execution_duration = durations_cache[execution.uuid]
    else:
        execution_duration = await calculate_execution_duration(execution.uuid, db)
    
    # Get execution_type value (convert enum to string if needed)
    execution_type_value = execution.execution_type
    if hasattr(execution_type_value, 'value'):
        execution_type_value = execution_type_value.value
    elif hasattr(execution_type_value, 'name'):
        # If it's an enum, get the value
        from app.models.execution import ExecutionType
        if execution_type_value == ExecutionType.BATCH:
            execution_type_value = 'batch'
        elif execution_type_value == ExecutionType.PLAYGROUND:
            execution_type_value = 'playground'
    
    # Create response object with computed status
    execution_dict = {
        "uuid": execution.uuid,
        "execution_folder_name": execution.execution_folder_name,
        "task_identifier": execution.task_identifier,
        "prompt": execution.prompt,
        "gym_id": execution.gym_id,
        "batch_id": execution.batch_id,
        "number_of_iterations": execution.number_of_iterations,
        "model": execution.model,
        "execution_type": execution_type_value,  # Include execution_type
        "playground_url": execution.playground_url,  # Include playground_url
        "status": computed_status,
        "eval_insights": execution.eval_insights,
        "created_at": execution.created_at,
        "updated_at": execution.updated_at,
        "execution_duration_seconds": execution_duration,  # Add execution duration
    }
    
    return ExecutionResponse(**execution_dict)


def parse_anthropic_response(file_path: Path) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Task ID is the parent folder (e.g., ZEND-TICKET-SPAM-001)
    task_id = file_path.parents[3].name  # 3 levels up from .txt file

    # Extract timestamp & response length from file content
    ts_match = re.search(r"Timestamp:\s*(.*)", content)
    length_match = re.search(r"Response Length:\s*(\d+)", content)

    timestamp = ts_match.group(1).strip() if ts_match else "unknown"
    resp_len = int(length_match.group(1)) if length_match else 0

    # Split header from body text
    parts = content.split("--------------------------------------------------------------------------------")
    response_text = parts[-1].strip() if len(parts) > 1 else ""

    return {
        "runner": "anthropic",
        "task_id": task_id,
        "timestamp": timestamp,
        "status": "failed",  # default, unless you track success elsewhere
        "response_length": resp_len,
        "output_preview": response_text[:200],  # first 200 chars
        "file": str(file_path)  # keep file path reference
    }

def build_hierarchical_structure(files_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build smart hierarchical structure from file metadata with optimized nesting"""
    
    # First, analyze the structure to determine what levels to include
    tasks = set()
    iterations = set()
    models = set()

    for file in files_metadata:
        path_parts = file['path'].split('/')

        if len(path_parts) >= 3:
            tasks.add(path_parts[0])
            iterations.add(path_parts[1])
            # Only add as model if it's a 4-part path AND the 3rd part is likely a model name
            # (not a folder like "screenshots", "logs", etc.)
            if len(path_parts) >= 4:
                potential_model = path_parts[2]
                # Skip common folder names that aren't models
                if potential_model not in ['screenshots', 'logs', 'conversation_history', 'task_responses']:
                    models.add(potential_model)

    # Determine which levels to include
    include_task = len(tasks) > 1
    include_iteration = len(iterations) > 1
    include_model = len(models) > 1

    structure = {}

    for file in files_metadata:
        path_parts = file['path'].split('/')

        # Parse: ZEND-TICKET-SPAM-001/iteration_1/anthropic/screenshots/file.png
        # or: ZEND-TICKET-SPAM-001/iteration_1/anthropic/verification.json
        # or: ZEND-TICKET-SPAM-001/iteration_1/verification.json (3 parts)
        if len(path_parts) >= 3:
            task_id = path_parts[0]
            iteration = path_parts[1]
            
            if len(path_parts) == 3:
                # This is a file directly under the iteration folder (e.g., verification.json)
                file_category = "files"  # Group all root files under "files"
                model = None
            elif len(path_parts) == 4:
                # Check if the 3rd part is a folder name (like screenshots, logs) or a model name
                potential_model = path_parts[2]
                if potential_model in ['screenshots', 'logs', 'conversation_history', 'task_responses']:
                    # This is a file in a subfolder (e.g., screenshots/file.png)
                    model = None
                    file_category = potential_model
                else:
                    # This is a file directly under the model folder (e.g., verification.json)
                    model = potential_model
                    file_category = "files"
            else:
                # This is a file in a subfolder (e.g., screenshots/file.png)
                model = path_parts[2]
                file_category = path_parts[3]

            # Build structure based on what levels to include
            current_level = structure

            # Add task level if needed
            if include_task:
                if task_id not in current_level:
                    current_level[task_id] = {}
                current_level = current_level[task_id]

            # Add iteration level if needed
            if include_iteration:
                if iteration not in current_level:
                    current_level[iteration] = {}
                current_level = current_level[iteration]

            # Add model level if needed
            if include_model and model is not None:
                if model not in current_level:
                    current_level[model] = {}
                current_level = current_level[model]

            # Add file category level
            if file_category not in current_level:
                current_level[file_category] = []
            current_level[file_category].append(file)

        elif len(path_parts) == 1:
            # Root level files (like detailed_results.json)
            if "root_files" not in structure:
                structure["root_files"] = []
            structure["root_files"].append(file)

    # If we have a single iteration and no task/model levels, flatten the structure
    if not include_task and not include_iteration and not include_model and len(iterations) == 1:
        # Flatten the structure - move files from iteration level to root level
        flattened_structure = {}
        for iteration_key, iteration_data in structure.items():
            if isinstance(iteration_data, dict):
                for category, files in iteration_data.items():
                    if isinstance(files, list):
                        flattened_structure[category] = files
                    else:
                        flattened_structure[category] = files
            else:
                flattened_structure[iteration_key] = iteration_data
        structure = flattened_structure

    return structure

@router.post("/", response_model=ExecutionResponse)
@router.post("", response_model=ExecutionResponse)
async def create_execution(
    execution_data: ExecutionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new execution and trigger task execution"""
    try:
        # Import execution type enum
        from app.schemas.execution import ExecutionType
        
        # Log the received execution data for debugging
        logger.info(f"📥 Received execution creation request:")
        logger.info(f"   - execution_type={execution_data.execution_type} (type: {type(execution_data.execution_type)})")
        logger.info(f"   - execution_type.value={execution_data.execution_type.value if hasattr(execution_data.execution_type, 'value') else 'N/A'}")
        logger.info(f"   - playground_url={execution_data.playground_url}")
        logger.info(f"   - gym_id={execution_data.gym_id}")
        logger.info(f"   - prompt={'present' if execution_data.prompt else 'missing'}")
        
        # Ensure task_crud is available
        from app.services.crud.task import task_crud
        
        # Handle playground vs batch executions
        # Compare by value to be safe
        exec_type_value = execution_data.execution_type.value if hasattr(execution_data.execution_type, 'value') else str(execution_data.execution_type)
        logger.info(f"📥 Comparing execution_type: {exec_type_value} == 'playground'? {exec_type_value == 'playground'}")
        
        if exec_type_value == 'playground' or execution_data.execution_type == ExecutionType.PLAYGROUND:
            # Playground execution - validate playground_url and prompt
            if not execution_data.playground_url:
                raise HTTPException(status_code=400, detail="playground_url is required for playground executions")
            if not execution_data.prompt:
                raise HTTPException(status_code=400, detail="prompt is required for playground executions")
            
            # task_identifier will be set after execution is created
            
            # Generate execution folder name for playground: playground_<timestamp>_<model>
            if not execution_data.execution_folder_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                model_name = execution_data.model.value
                execution_data.execution_folder_name = f"playground_{timestamp}_{model_name}"
                logger.info(f"Generated playground execution folder name: {execution_data.execution_folder_name}")
            else:
                logger.info(f"Using provided execution folder name: {execution_data.execution_folder_name}")
        else:
            # Batch execution - verify gym exists
            if not execution_data.gym_id:
                raise HTTPException(status_code=400, detail="gym_id is required for batch executions")
            
            gym = await gym_crud.get(db, execution_data.gym_id)
            if not gym:
                raise HTTPException(status_code=404, detail=f"Gym {execution_data.gym_id} not found")

            # Verify task exists if provided and populate snapshots
            if execution_data.task_id:
                task = await task_crud.get(db, execution_data.task_id)
                if not task:
                    raise HTTPException(status_code=404, detail=f"Task {execution_data.task_id} not found")

                # Verify task belongs to the same gym
                if task.gym_id != execution_data.gym_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Task does not belong to the specified gym"
                    )
                
                # Populate snapshot fields from task
                execution_data.task_identifier = task.task_id
                execution_data.prompt = task.prompt
                execution_data.grader_config = task.grader_config
                execution_data.simulator_config = task.simulator_config
                logger.info(
                    f"Populated snapshots: task_identifier={task.task_id}, "
                    f"prompt length={len(task.prompt) if task.prompt else 0}, "
                    f"grader_config={'present' if task.grader_config else 'null'}, "
                    f"simulator_config={'present' if task.simulator_config else 'null'}"
                )

            # Generate execution folder name if not provided (for batch)
            if not execution_data.execution_folder_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                execution_data.execution_folder_name = f"execution_iterations_{timestamp}"
                logger.info(f"Generated execution folder name: {execution_data.execution_folder_name}")
            else:
                logger.info(f"Using provided execution folder name: {execution_data.execution_folder_name}")

        # Create execution record
        execution = await execution_crud.create(db, execution_data)
        logger.info(f"✅ Created execution {execution.uuid} with execution_type={execution.execution_type}, folder_name={execution.execution_folder_name}")

        # Generate task_identifier for playground if not set (after execution is created)
        if execution_data.execution_type == ExecutionType.PLAYGROUND and not execution.task_identifier:
            execution.task_identifier = f"playground_{execution.uuid}"
            # Update the execution with task_identifier
            from app.schemas.execution import ExecutionUpdate
            update_data = ExecutionUpdate()
            # We'll update via SQL since ExecutionUpdate doesn't have task_identifier
            from sqlalchemy import text
            await db.execute(
                text("UPDATE executions SET task_identifier = :task_identifier WHERE uuid = :uuid"),
                {"task_identifier": execution.task_identifier, "uuid": execution.uuid}
            )
            await db.commit()
            # Refresh execution
            await db.refresh(execution)

        # Create iterations for this execution
        iterations = await iteration_crud.create_batch(
            db,
            execution_id=execution.uuid,
            number_of_iterations=execution_data.number_of_iterations
        )
        
        # Get task_identifier for logging
        task_identifier = execution.task_identifier or execution_data.task_identifier
        
        # Don't dispatch immediately - let the monitoring task handle dispatch (same as batches)
        # This ensures consistent ordering and prevents race conditions
        logger.info(
            f"Created {len(iterations)} iteration(s) for {'playground' if execution_data.execution_type == ExecutionType.PLAYGROUND else 'task'} {task_identifier}. "
            f"Iterations will be dispatched by the monitoring task."
        )

        # Return execution with computed status
        return await create_execution_response(execution, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=ExecutionListResponse)
@router.get("", response_model=ExecutionListResponse)
async def get_executions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    gym_id: Optional[UUID] = Query(None),
    task_id: Optional[UUID] = Query(None),
    model: Optional[str] = Query(None),
    execution_type: Optional[str] = Query(None, description="Filter by execution type: 'batch' or 'playground'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all executions with pagination and filtering"""
    try:
        from app.schemas.execution import ExecutionType
        
        if gym_id:
            # Verify gym exists
            gym = await gym_crud.get(db, gym_id)
            if not gym:
                raise HTTPException(status_code=404, detail=f"Gym {gym_id} not found")

            executions = await execution_crud.get_multi_by_gym(db, gym_id, skip=skip, limit=limit)
            total = await execution_crud.count_by_gym(db, gym_id)
        elif task_id:
            # Verify task exists and get its task_identifier
            task = await task_crud.get(db, task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

            # Filter by task_identifier (snapshot field) instead of task UUID
            executions = await execution_crud.get_multi_by_task_identifier(db, task.task_id, skip=skip, limit=limit)
            total = await execution_crud.count_by_task_identifier(db, task.task_id)
        elif model:
            executions = await execution_crud.get_multi_by_model(db, model, skip=skip, limit=limit)
            total = await execution_crud.count_by_model(db, model)
        elif execution_type:
            # Filter by execution_type (for playground)
            if execution_type not in ['batch', 'playground']:
                raise HTTPException(status_code=400, detail="execution_type must be 'batch' or 'playground'")
            executions = await execution_crud.get_multi_by_execution_type(db, execution_type, skip=skip, limit=limit)
            total = await execution_crud.count_by_execution_type(db, execution_type)
        else:
            executions = await execution_crud.get_multi(db, skip=skip, limit=limit)
            total = await execution_crud.count(db)

        # Bulk calculate durations for all executions in one query
        execution_ids = [exec.uuid for exec in executions]
        durations_cache = await calculate_execution_durations_bulk(execution_ids, db)

        # Create execution responses with computed status
        execution_responses = []
        for execution in executions:
            execution_response = await create_execution_response(
                execution, 
                db, 
                durations_cache=durations_cache
            )
            execution_responses.append(execution_response)

        return ExecutionListResponse(
            executions=execution_responses,
            total=total,
            skip=skip,
            limit=limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import pandas as pd

logger = logging.getLogger(__name__)

def _hms(seconds: float) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"

def _safe_float_minutes(sec: float | int | None) -> float:
    try:
        return round(float(sec or 0.0) / 60.0, 2)
    except Exception:
        return 0.0


def _first_non_null(*values: object) -> object | None:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _coerce_float(value: object) -> float | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    if value in (None, "", []):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except Exception:
            return None
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def _parse_timestamp(value: object) -> tuple[Optional[str], Optional[float]]:
    if value in (None, ""):
        return None, None

    if isinstance(value, (int, float)):
        try:
            epoch = float(value)
            return datetime.fromtimestamp(epoch).isoformat(), epoch
        except Exception:
            return None, None

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, None
        try:
            epoch = float(stripped)
        except Exception:
            return stripped, None
        try:
            return datetime.fromtimestamp(epoch).isoformat(), epoch
        except Exception:
            return stripped, epoch

    return None, None


def _extract_attempts(verification: dict[str, Any]) -> Optional[int]:
    attempt_keys = [
        "execution_steps",
        "_iteration_execution_step_count",
        "attempts",
        "attempt_count",
        "step_count",
        "steps_taken",
        "tool_calls_executed",
        "tools_executed",
    ]

    for key in attempt_keys:
        if key in verification:
            attempts = _coerce_int(verification.get(key))
            if attempts is not None:
                return attempts

    for candidate in (
        verification.get("actions"),
        verification.get("tool_calls"),
        verification.get("steps"),
    ):
        if isinstance(candidate, (list, tuple, set)) and candidate:
            return len(candidate)

    return None


def _extract_screenshot_count(verification: dict[str, Any]) -> Optional[int]:
    list_keys = [
        "screenshots",
        "screenshot_urls",
        "screenshotUrls",
        "images",
    ]
    for key in list_keys:
        if key in verification and isinstance(verification[key], (list, tuple, set)):
            return len([item for item in verification[key] if item is not None])

    count_keys = [
        "screenshots_count",
        "screenshot_count",
        "num_screenshots",
        "screenshotsTaken",
    ]
    for key in count_keys:
        if key in verification:
            count = _coerce_int(verification.get(key))
            if count is not None:
                return count

    return None


def _load_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
    return None

def _iter_conversation_files(iteration_dir: Path, task_id: str) -> list[Path]:
    conv_dir = iteration_dir / "openai" / "conversation_history"
    if not conv_dir.exists():
        return []
    # canonical file name used by runner
    f = conv_dir / f"{task_id}_task_execution_conversation.json"
    return [f] if f.exists() else []

def _cleanup_old_exports(export_dir: Path, max_age_hours: int = 24):
    """Remove export files older than max_age_hours"""
    try:
        now = datetime.now()
        for export_file in export_dir.glob("executions_export_*.xlsx"):
            try:
                file_age = now - datetime.fromtimestamp(export_file.stat().st_mtime)
                if file_age.total_seconds() > (max_age_hours * 3600):
                    export_file.unlink()
                    logger.info(f"Deleted old export file: {export_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete old export {export_file}: {e}")
    except Exception as e:
        logger.warning(f"Export cleanup failed: {e}")


_INVALID_SHEET_CHARS = re.compile(r"[\\/*?:\[\]]")


def _clean_sheet_name(name: str) -> str:
    """Normalize a sheet name by stripping invalid Excel characters."""
    cleaned = _INVALID_SHEET_CHARS.sub("_", (name or "").strip())
    return cleaned or "Sheet"


def _unique_sheet_name(
    base_name: str,
    used_names: set[str],
    *,
    hint: str | None = None,
    max_len: int = 31
) -> str:
    """Generate an Excel-safe, unique sheet name within 31 characters."""
    cleaned_base = _clean_sheet_name(base_name)
    base_candidate = cleaned_base[:max_len]

    if base_candidate not in used_names:
        used_names.add(base_candidate)
        return base_candidate

    if hint:
        cleaned_hint = _clean_sheet_name(hint)
        if cleaned_hint:
            suffix = f"_{cleaned_hint[: max(1, max_len // 4)]}"
            candidate = f"{cleaned_base[: max_len - len(suffix)]}{suffix}"[:max_len]
            if candidate and candidate not in used_names:
                used_names.add(candidate)
                return candidate

    for i in range(1, 1000):
        suffix = f"_{i}"
        candidate = f"{cleaned_base[: max_len - len(suffix)]}{suffix}"
        if candidate and candidate not in used_names:
            used_names.add(candidate)
            return candidate

    raise HTTPException(status_code=500, detail="Unable to generate unique sheet name for export")


def _load_summary_from_files(execution_dir: Path) -> dict[str, dict[str, Any]]:
    """Load iteration summary data from detailed_results JSON files."""
    summary: dict[str, dict[str, Any]] = {}
    detail_files = sorted(execution_dir.glob("detailed_results_*.json"), reverse=True)

    for detail_file in detail_files:
        try:
            data = json.loads(detail_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
        except Exception as exc:
            logger.warning(f"Failed to load detailed results from {detail_file}: {exc}")
            continue

        for entry in data:
            if not isinstance(entry, dict):
                continue
            task_id = entry.get("task_id")
            if not task_id:
                continue

            iteration_number = entry.get("iteration") or entry.get("iteration_number")
            if iteration_number is None:
                # fallback: ensure unique key order based on existing iterations
                existing = summary.setdefault(task_id, {})
                iteration_number = len(existing) + 1
            iteration_key = f"iteration_{iteration_number}"

            iteration_data = dict(entry)
            iteration_data.setdefault("execution_steps", entry.get("execution_steps", 0))
            iteration_data.setdefault("screenshots", entry.get("screenshots") or [])
            iteration_data.setdefault("run_id", entry.get("run_id", "N/A"))
            iteration_data.setdefault("status", entry.get("status"))
            iteration_data.setdefault("verification_status", entry.get("verification_status"))
            iteration_data.setdefault("start_time", entry.get("start_time"))
            iteration_data.setdefault("end_time", entry.get("end_time"))
            iteration_data.setdefault("execution_time", entry.get("execution_time"))
            iteration_data["_iteration_execution_time_seconds"] = entry.get("execution_time")

            summary.setdefault(task_id, {})[iteration_key] = iteration_data

        # If we successfully loaded one file, skip older ones to prevent duplicates
        if summary:
            break

    return summary


async def _process_execution_export(
    *,
    ex_folder: str,
    execution_dir: Path,
    summary_data: dict[str, dict[str, Any]] | None,
    global_rows: list[dict[str, Any]],
    task_sheets_data: dict[str, list[dict[str, Any]]],
    model: str | None,
    prompt_fetcher: Callable[[str], Awaitable[Optional[str]]] | None,
    global_seen_iterations: set[tuple[str, str, str, str]] | None = None,
    global_summary_seen: set[tuple[str, str, str]] | None = None,
) -> None:
    folder_exists = execution_dir.exists()
    if not folder_exists:
        logger.warning(f"Execution folder missing (will use summary data only): {ex_folder}")

    summary_data = summary_data or {}
    model_name = (model or "unknown")

    seen_iterations: set[tuple[str, str, str, str]] = set()

    record_tasks: dict[str, List[IterationRecord]] = {}
    if folder_exists:
        try:
            records = collect_execution_data(execution_dir)
            for rec in records:
                if rec.task_id:
                    record_tasks.setdefault(rec.task_id, []).append(rec)
        except Exception as record_exc:
            logger.debug("collect_execution_data failed for %s: %s", execution_dir, record_exc)

    all_task_ids = set(summary_data.keys()) | set(record_tasks.keys())

    for task_id in all_task_ids:
        iterations = summary_data.get(task_id) or {}
        record_entries = record_tasks.get(task_id) or []

        total_attempts = 0
        attempt_samples = 0
        total_time_mins = 0.0
        timed_samples = 0
        total_timelapse_secs = 0.0
        count = 0
        prompt: Optional[str] = None

        # Track all 2 models
        openai_total = 0
        openai_failed = 0
        anthropic_total = 0
        anthropic_failed = 0

        for rec in record_entries:
            if rec.prompt:
                prompt = rec.prompt
                break

        if not prompt:
            for verification in iterations.values():
                if isinstance(verification, dict) and verification.get("prompt"):
                    prompt = verification.get("prompt")
                    break

        if prompt is None and prompt_fetcher:
            try:
                prompt = await prompt_fetcher(task_id)
            except Exception as exc:
                logger.error(f"Error fetching prompt for task {task_id}: {exc}")

        for rec_index, rec in enumerate(record_entries, start=1):
            extra = rec.extra or {}
            iter_label = rec.iteration if rec.iteration is not None else rec_index
            iter_key = f"iteration_{iter_label}"
            if rec.runner:
                iter_key = f"{iter_key}_{rec.runner}"
            run_id = rec.run_id or extra.get("run_id") or f"record-{rec_index}-{rec.runner or 'unknown'}"

            dedupe_key = (ex_folder, task_id, iter_key, run_id)
            if dedupe_key in seen_iterations:
                logger.debug("Skipping duplicate iteration row (record): %s", dedupe_key)
                continue
            if global_seen_iterations is not None and dedupe_key in global_seen_iterations:
                logger.debug("Skipping duplicate iteration row (record global): %s", dedupe_key)
                continue
            seen_iterations.add(dedupe_key)
            if global_seen_iterations is not None:
                global_seen_iterations.add(dedupe_key)

            status = (rec.status or "unknown").upper()
            completion_reason = rec.completion_reason or extra.get("completion_reason")
            status_reason = rec.status_reason or extra.get("status_reason") or extra.get("error")

            attempts_raw = _first_non_null(
                extra.get("execution_steps"),
                extra.get("tool_calls_executed"),
                extra.get("attempts"),
                extra.get("attempt_count"),
                rec.tool_calls_total,
            )
            attempts = _coerce_int(attempts_raw)
            attempts = attempts if attempts is not None else rec.tool_calls_total or 0

            exec_secs_value = _first_non_null(
                rec.duration_seconds,
                extra.get("duration_seconds"),
                extra.get("execution_time"),
                extra.get("elapsed_time_seconds"),
            )
            exec_secs = _coerce_float(exec_secs_value)
            time_mins = round(exec_secs / 60.0, 2) if exec_secs is not None else None

            start_display = rec.start_timestamp or extra.get("started_at")
            end_display = rec.end_timestamp or extra.get("ended_at")
            timelapse_str = rec.timelapse or extra.get("timelapse")

            if timelapse_str is None and exec_secs is not None and exec_secs > 0:
                timelapse_str = _hms(exec_secs)

            if rec.file_timelapse_seconds:
                total_timelapse_secs += rec.file_timelapse_seconds
            elif exec_secs is not None and exec_secs > 0:
                total_timelapse_secs += exec_secs

            screenshots = _coerce_int(
                _first_non_null(
                    extra.get("screenshots_count"),
                    extra.get("screenshot_count"),
                    extra.get("num_screenshots"),
                    len(extra.get("screenshots", [])) if isinstance(extra.get("screenshots"), (list, tuple, set)) else None,
                )
            )
            screenshots = screenshots if screenshots is not None else 0

            iteration_model = rec.model or rec.runner or model_name
            model_lower = (iteration_model or "unknown").lower()
            is_failed = status in {"FAILED", "CRASHED", "TIMEOUT", "ERROR"}

            if "openai" in model_lower or "gpt" in model_lower:
                openai_total += 1
                if is_failed:
                    openai_failed += 1

            if "anthropic" in model_lower or "claude" in model_lower:
                anthropic_total += 1
                if is_failed:
                    anthropic_failed += 1

            total_attempts += attempts
            attempt_samples += 1
            if time_mins is not None:
                total_time_mins += time_mins
                timed_samples += 1
            count += 1

            task_row = {
                "Execution": ex_folder,
                "Task ID": task_id,
                "Prompt": prompt,
                "Iteration": iter_key,
                "Runner": iteration_model,
                "Model": iteration_model,
                "Run ID": run_id,
                "Status": status,
                "Completion Reason": completion_reason or "N/A",
                "Status Reason": status_reason or "N/A",
                "Attempts": attempts,
                "Execution Time (mins)": time_mins,
                "Execution Time (seconds)": round(exec_secs, 2) if exec_secs is not None else None,
                "Timelapse": timelapse_str,
                "Start Timestamp": start_display,
                "End Timestamp": end_display,
                "Screenshots Count": screenshots,
            }
            task_sheets_data.setdefault(task_id, []).append(task_row)

        for iter_key, verification in (iterations or {}).items():
            if not verification:
                verification = {}
                logger.debug(f"No verification data for {task_id}/{iter_key}, using empty defaults")

            iteration_model = (
                verification.get("model")
                or verification.get("runner")
                or model_name
            )
            run_id = (
                verification.get("run_id")
                or verification.get("iteration_run_id")
                or verification.get("_iteration_run_id")
                or "N/A"
            )
            dedupe_key = (ex_folder, task_id, iter_key, run_id)
            if dedupe_key in seen_iterations:
                logger.debug(f"Skipping duplicate iteration row (per execution): {dedupe_key}")
                continue
            if global_seen_iterations is not None and dedupe_key in global_seen_iterations:
                logger.debug(f"Skipping duplicate iteration row (across executions): {dedupe_key}")
                continue
            seen_iterations.add(dedupe_key)
            if global_seen_iterations is not None:
                global_seen_iterations.add(dedupe_key)
            status = (
                verification.get("verification_status")
                or verification.get("status")
                or verification.get("_iteration_status")
                or "pending"
            )
            completion_reason = (
                verification.get("completion_reason")
                or verification.get("reason")
                or verification.get("_iteration_completion_reason")
                or verification.get("failure_reason")
                or verification.get("status_reason")
            )
            status_reason = (
                verification.get("status_reason")
                or verification.get("error_reason")
                or verification.get("error_message")
                or verification.get("failure_reason")
                or verification.get("reason_detail")
                or verification.get("error")
            )
            attempts = _extract_attempts(verification)

            exec_secs_value = _first_non_null(
                verification.get("_iteration_execution_time_seconds"),
                verification.get("execution_time"),
                verification.get("duration_seconds"),
                verification.get("total_time_seconds"),
            )
            exec_secs = _coerce_float(exec_secs_value)
            time_mins = round(exec_secs / 60.0, 2) if exec_secs is not None else None

            start_raw = _first_non_null(
                verification.get("_iteration_started_at"),
                verification.get("start_time"),
                verification.get("started_at"),
            )
            end_raw = _first_non_null(
                verification.get("_iteration_completed_at"),
                verification.get("end_time"),
                verification.get("ended_at"),
            )

            start_display, start_epoch = _parse_timestamp(start_raw)
            end_display, end_epoch = _parse_timestamp(end_raw)
            timelapse_str = None
            if start_epoch is not None and end_epoch is not None:
                elapsed = end_epoch - start_epoch
                if elapsed > 0:
                    timelapse_str = _hms(elapsed)
                    total_timelapse_secs += elapsed

            screenshots = _extract_screenshot_count(verification)

            model_lower = (iteration_model or "unknown").lower()
            is_failed = isinstance(status, str) and status.upper() in {"FAILED", "CRASHED", "TIMEOUT", "ERROR"}

            if "openai" in model_lower or "gpt" in model_lower:
                openai_total += 1
                if is_failed:
                    openai_failed += 1

            if "anthropic" in model_lower or "claude" in model_lower:
                anthropic_total += 1
                if is_failed:
                    anthropic_failed += 1

            if attempts is not None:
                total_attempts += attempts
                attempt_samples += 1
            if time_mins is not None:
                total_time_mins += time_mins
                timed_samples += 1
            count += 1

            task_row = {
                "Execution": ex_folder,
                "Task ID": task_id,
                "Prompt": prompt,
                "Iteration": iter_key,
                "Runner": iteration_model,
                "Model": iteration_model,
                "Run ID": run_id,
                "Status": status,
                "Completion Reason": completion_reason or "N/A",
                "Status Reason": status_reason or "N/A",
                "Attempts": attempts if attempts is not None else 0,
                "Execution Time (mins)": time_mins,
                "Execution Time (seconds)": round(exec_secs, 2) if exec_secs is not None else None,
                "Timelapse": timelapse_str,
                "Start Timestamp": start_display,
                "End Timestamp": end_display,
                "Screenshots Count": screenshots if screenshots is not None else 0,
            }
            task_sheets_data.setdefault(task_id, []).append(task_row)

        if attempt_samples == 0 and timed_samples == 0:
            difficulty = "Unknown"
        elif total_attempts > 15 and total_time_mins > 20:
            difficulty = "High"
        elif total_attempts > 5 and total_time_mins >= 15:
            difficulty = "Medium"
        else:
            difficulty = "Low"

        avg_time = round(total_time_mins / timed_samples, 2) if timed_samples else None
        total_timelapse_str = _hms(total_timelapse_secs) if total_timelapse_secs else None

        # Format breaking columns for all 2 models
        if openai_total == 0:
            openai_status = "Not Tested"
        elif openai_failed > 0:
            openai_status = f"Yes, {openai_failed}/{openai_total}"
        else:
            openai_status = f"No, 0/{openai_total}"

        if anthropic_total == 0:
            anthropic_status = "Not Tested"
        elif anthropic_failed > 0:
            anthropic_status = f"Yes, {anthropic_failed}/{anthropic_total}"
        else:
            anthropic_status = f"No, 0/{anthropic_total}"

        summary_key = (ex_folder, task_id, prompt or "")
        if global_summary_seen is not None:
            if summary_key in global_summary_seen:
                logger.debug(f"Skipping duplicate summary row: {summary_key}")
                continue
            global_summary_seen.add(summary_key)

        global_rows.append({
            "Execution": ex_folder,
            "Task ID": task_id,
            "Prompt": prompt,
            "OpenAI Computer Use Preview breaking": openai_status,
            "Anthropic Breaking": anthropic_status,
            "Difficulty": difficulty,
            "Total Time (mins)": round(total_time_mins, 2) if timed_samples else None,
            "Average Iteration Time (mins)": avg_time,
            "Total Timelapse": total_timelapse_str,
        })


@router.get("/export", tags=["reports"])
async def export_all_executions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export ALL executions to a single Excel workbook with prompts from database.
    This collects filesystem data and injects database prompts for complete reporting.
    """
    try:
        executions = await execution_crud.list_all(db)
        if not executions:
            raise HTTPException(status_code=404, detail="No executions found")

        results_dir = Path(settings.RESULTS_DIR)
        export_dir = results_dir / "exports"
        
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            logger.error(f"Cannot create export dir {export_dir}: {e}")
            export_dir = results_dir
            export_dir.mkdir(parents=True, exist_ok=True)

        # Collect all iteration records from filesystem
        all_records = []
        for ex in executions:
            execution_dir = results_dir / ex.execution_folder_name
            if execution_dir.exists():
                try:
                    records = collect_execution_data(execution_dir)
                    # Fetch and inject prompts from database
                    for record in records:
                        if not record.prompt:
                            try:
                                task = await task_crud.get_by_task_id_and_gym(db, record.task_id, ex.gym_id)
                                if task:
                                    record.prompt = task.prompt
                            except Exception as e:
                                logger.debug(f"Could not fetch prompt for {record.task_id}: {e}")
                    all_records.extend(records)
                except Exception as e:
                    logger.warning(f"Failed to collect data from {execution_dir}: {e}")
            else:
                logger.warning("Execution folder missing, skipping: %s", ex.execution_folder_name)

        if not all_records:
            raise HTTPException(status_code=404, detail="No execution data found")

        output_path = export_dir / "executions_all_results.xlsx"
        
        # Use the report module's internal functions to build the report
        from app.services.reports.execution_report import _build_summary, _write_workbook
        summary_rows, task_rows = _build_summary(all_records)
        _write_workbook(
            summary_rows=summary_rows,
            iterations=all_records,
            task_rows=task_rows,
            workbook_path=output_path
        )
        
        logger.info(f"📊 Generated export with {len(summary_rows)} tasks, {len(all_records)} total iterations")

        download_url = f"/api/v1/executions/files/exports/{output_path.name}?t={int(time.time())}"
        return {
            "message": f"Workbook generated with {len(summary_rows)} tasks",
            "download_url": download_url,
            "total_tasks": len(summary_rows),
            "total_iterations": len(all_records),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting all executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


from fastapi import Response

@router.get("/files/exports/{filename}", tags=["reports"])
async def get_exports_file(
    filename: str,
    token: Optional[str] = Query(None, description="Authentication token for file access"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Serve a generated export (.xlsx) from RESULTS_DIR/exports or fallback RESULTS_DIR"""
    # Auth
    authenticated_user = current_user
    if token and not authenticated_user:
        try:
            authenticated_user = await get_current_user_from_token(token, db)
        except HTTPException:
            raise HTTPException(status_code=403, detail="Invalid authentication token")
    if not authenticated_user:
        raise HTTPException(status_code=403, detail="Authentication required")

    results_dir = Path(settings.RESULTS_DIR)
    export_dir = results_dir / "exports"

    # Try primary location
    full_file_path = (export_dir / filename).resolve()
    if not full_file_path.exists():
        # fallback: look directly in results/
        full_file_path = (results_dir / filename).resolve()

    if not full_file_path.exists() or not full_file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Disposition": f'attachment; filename="{full_file_path.name}"',
    }
    return FileResponse(str(full_file_path), media_type=media_type, filename=full_file_path.name, headers=headers)

@router.get("/{execution_id}/progress")
async def get_execution_progress(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed progress information for an execution including iteration status"""
    try:
        # Verify execution exists
        execution = await execution_crud.get(db, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
        
        # Get progress information
        progress = await ExecutionStatusManager.get_execution_progress(str(execution_id))
        
        return progress
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/playground-progress")
async def get_playground_executions_progress(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get progress information for all playground executions in a single request.
    Similar to batch iteration summary but for playground executions.
    Returns progress data keyed by execution_id.
    """
    try:
        from sqlalchemy import select, func
        from app.models.iteration import Iteration
        
        # Get all playground executions
        executions = await execution_crud.get_multi_by_execution_type(
            db, "playground", skip=skip, limit=limit
        )
        
        if not executions:
            return {
                "execution_progress": {},
                "total_executions": 0,
                "generated_at": datetime.utcnow().isoformat()
            }
        
        # Get progress for each execution
        execution_progress_map = {}
        
        for execution in executions:
            execution_id = str(execution.uuid)
            
            # Get iteration summary for this execution
            iteration_result = await db.execute(
                select(
                    Iteration.status,
                    func.count(Iteration.uuid).label('count')
                )
                .where(Iteration.execution_id == execution.uuid)
                .group_by(Iteration.status)
            )
            
            iteration_status_counts = {
                "pending": 0,
                "executing": 0,
                "passed": 0,
                "failed": 0,
                "crashed": 0,
                "timeout": 0
            }
            
            total_iterations = 0
            
            for row in iteration_result:
                status = row.status.lower()
                count = row.count
                
                if status in iteration_status_counts:
                    iteration_status_counts[status] = count
                    total_iterations += count
            
            # Build progress summary similar to single execution progress
            completed_iterations = (
                iteration_status_counts["passed"] +
                iteration_status_counts["failed"] +
                iteration_status_counts["crashed"] +
                iteration_status_counts["timeout"]
            )
            progress_percentage = (
                (completed_iterations / total_iterations * 100) 
                if total_iterations > 0 else 0
            )
            
            execution_progress_map[execution_id] = {
                "execution_id": execution_id,
                "total_iterations": total_iterations,
                "completed_iterations": completed_iterations,
                "progress_percentage": round(progress_percentage, 2),
                "summary": {
                    "total_iterations": total_iterations,
                    "pending_count": iteration_status_counts["pending"],
                    "executing_count": iteration_status_counts["executing"],
                    "passed_count": iteration_status_counts["passed"],
                    "failed_count": iteration_status_counts["failed"],
                    "crashed_count": iteration_status_counts["crashed"],
                    "timeout_count": iteration_status_counts["timeout"]
                }
            }
        
        return {
            "execution_progress": execution_progress_map,
            "total_executions": len(executions),
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting playground executions progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SPECIFIC ROUTES (must be before /{execution_uuid} to avoid path conflicts)
# ============================================================================

async def _collect_aggregate_data(
    db: AsyncSession,
    gym_id: Optional[UUID],
    start_date: Optional[str],
    end_date: Optional[str],
    max_executions: int,
) -> Optional[Dict[str, object]]:
    selected_gym = None
    if gym_id:
        selected_gym = await gym_crud.get(db, gym_id)
        if not selected_gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_id} not found")
    else:
        gyms = await gym_crud.get_multi(db, skip=0, limit=1)
        if not gyms:
            return None
        selected_gym = gyms[0]
        gym_id = selected_gym.uuid

    # Parse date filters
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    executions = await execution_crud.get_by_gym_and_date_range(
        db,
        gym_id=gym_id,
        start_date=start_datetime,
        end_date=end_datetime,
    )

    if not executions:
        filters = {
            "gym_id": str(selected_gym.uuid) if selected_gym else None,
            "gym_name": selected_gym.name if selected_gym else None,
            "start_date": start_date,
            "end_date": end_date,
            "default_start_date": None,
            "default_end_date": None,
            "available_filters": {},
        }
        return {
            "selected_gym": selected_gym,
            "summary_rows": [],
            "task_rows": {},
            "all_records": [],
            "snapshot": {
                "summary_table": [],
                "single_task_tables": {},
                "tasks": {},
                "filters": filters,
                "iterations": [],
            },
            "filters": filters,
            "execution_meta": {},
        }

    if len(executions) > max_executions:
        raise HTTPException(
            status_code=400,
            detail=f"Too many executions ({len(executions)}). Maximum allowed: {max_executions}"
        )

    results_dir = Path(settings.RESULTS_DIR)
    execution_meta: Dict[str, Dict[str, object]] = {}
    task_uuid_to_task_id: Dict[UUID, str] = {}
    all_records: List[IterationRecord] = []
    for ex in executions:
        execution_dir = results_dir / ex.execution_folder_name
        if execution_dir.exists():
            try:
                records = collect_execution_data(execution_dir)

                allowed_statuses = {"PASSED", "FAILED"}
                filtered_records: List[IterationRecord] = []
                for record in records:
                    status_value = record.status or ""
                    normalized_status = str(status_value).upper()
                    if normalized_status not in allowed_statuses:
                        extracted_status = _extract_record_status(record) or ""
                        normalized_status = extracted_status.upper()
                    if normalized_status not in allowed_statuses:
                        continue
                    record.status = normalized_status
                    filtered_records.append(record)

                if not filtered_records:
                    continue

                exec_uuid_str = str(ex.uuid)
                db_iterations = await iteration_crud.get_by_execution_id(db, ex.uuid, limit=None)
                iteration_uuid_map: Dict[Tuple[str, int], str] = {}
                
                # Get task_identifier from execution snapshot (not iteration.task_id)
                task_id_str = ex.task_identifier
                if task_id_str:
                    for db_iter in db_iterations:
                        iteration_uuid_map[(task_id_str, db_iter.iteration_number)] = str(db_iter.uuid)

                execution_meta[exec_uuid_str] = {
                    "execution_uuid": exec_uuid_str,
                    "execution_folder": ex.execution_folder_name,
                    "model": ex.model,
                    "number_of_iterations": ex.number_of_iterations,
                    "created_at": ex.created_at.isoformat() if ex.created_at else None,
                    "updated_at": ex.updated_at.isoformat() if ex.updated_at else None,
                    "task_id": task_id_str,  # Use snapshot field
                }
                for record in filtered_records:
                    if not record.prompt:
                        # Try execution snapshot first, then fallback to task table
                        if ex.prompt:
                            record.prompt = ex.prompt
                        else:
                            try:
                                task = await task_crud.get_by_task_id_and_gym(db, record.task_id, ex.gym_id)
                                if task:
                                    record.prompt = task.prompt
                            except Exception as e:
                                logger.debug(f"Could not fetch prompt for {record.task_id}: {e}")
                    if not isinstance(record.extra, dict):
                        record.extra = {}
                    record.extra.setdefault("execution_uuid", exec_uuid_str)
                    record.extra.setdefault("execution_model", ex.model)
                    record.extra.setdefault("execution_folder", ex.execution_folder_name)
                    record.extra.setdefault("execution_iterations_planned", ex.number_of_iterations)
                    if ex.created_at:
                        record.extra.setdefault("execution_started_at", ex.created_at.isoformat())
                    if ex.updated_at:
                        record.extra.setdefault("execution_updated_at", ex.updated_at.isoformat())
                    if not record.execution_uuid:
                        record.execution_uuid = exec_uuid_str
                    if not record.iteration_uuid and isinstance(record.extra, dict):
                        iteration_uuid = (
                            record.extra.get("iteration_uuid")
                            or (record.extra.get("backend_verification_results") or {}).get("iteration_uuid")
                            or (record.extra.get("backend_verification_results") or {}).get("iteration_id")
                        )
                        if iteration_uuid:
                            record.iteration_uuid = str(iteration_uuid)
                    if not record.iteration_uuid:
                        mapped_uuid = iteration_uuid_map.get((record.task_id, record.iteration))
                        if mapped_uuid:
                            record.iteration_uuid = mapped_uuid
                all_records.extend(filtered_records)
            except Exception as e:
                logger.warning(f"Failed to collect data from {execution_dir}: {e}")

    if not all_records:
        filters = {
            "gym_id": str(selected_gym.uuid) if selected_gym else None,
            "gym_name": selected_gym.name if selected_gym else None,
            "start_date": start_date,
            "end_date": end_date,
            "default_start_date": None,
            "default_end_date": None,
            "available_filters": {},
        }
        return {
            "selected_gym": selected_gym,
            "summary_rows": [],
            "task_rows": {},
            "all_records": [],
            "snapshot": {
                "summary_table": [],
                "single_task_tables": {},
                "tasks": {},
                "filters": filters,
                "iterations": [],
            },
            "filters": filters,
            "execution_meta": execution_meta,
        }

    filtered_records = all_records

    if start_date or end_date:
        start_bound = None
        end_bound = None
        if start_date:
            try:
                start_bound = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")
            else:
                end_bound = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

        def _record_in_range(record: IterationRecord) -> bool:
            candidates = [
                _parse_iso_datetime(record.start_timestamp),
                _parse_iso_datetime(record.end_timestamp),
            ]
            ts = next((value for value in candidates if value is not None), None)
            if ts is None:
                return True
            if start_bound and ts < start_bound:
                return False
            if end_bound and ts > end_bound:
                return False
            return True

        filtered_records = [record for record in all_records if _record_in_range(record)]

        if not filtered_records:
            filters = {
                "gym_id": str(selected_gym.uuid) if selected_gym else None,
                "gym_name": selected_gym.name if selected_gym else None,
                "start_date": start_date,
                "end_date": end_date,
                "default_start_date": None,
                "default_end_date": None,
                "available_filters": {},
            }
            return {
                "selected_gym": selected_gym,
                "summary_rows": [],
                "task_rows": {},
                "all_records": [],
                "snapshot": {
                    "summary_table": [],
                    "single_task_tables": {},
                    "tasks": {},
                    "filters": filters,
                    "iterations": [],
                },
                "filters": filters,
                "execution_meta": execution_meta,
            }

    summary_rows, task_rows = _build_summary(filtered_records)
    snapshot = _build_snapshot(summary_rows, filtered_records, task_rows)

    starts = sorted(record.start_timestamp for record in filtered_records if record.start_timestamp)
    ends = sorted(record.end_timestamp for record in filtered_records if record.end_timestamp)
    earliest_ts = starts[0] if starts else None
    latest_ts = ends[-1] if ends else None
    default_start_date = earliest_ts[:10] if earliest_ts else None
    default_end_date = latest_ts[:10] if latest_ts else None
    applied_start_date = start_date or default_start_date
    applied_end_date = end_date or default_end_date

    filters = {
        "gym_id": str(selected_gym.uuid) if selected_gym else None,
        "gym_name": selected_gym.name if selected_gym else None,
        "start_date": applied_start_date,
        "end_date": applied_end_date,
        "default_start_date": default_start_date,
        "default_end_date": default_end_date,
        "available_filters": snapshot.get("filters", {}),
    }

    return {
        "selected_gym": selected_gym,
        "summary_rows": summary_rows,
        "task_rows": task_rows,
        "all_records": filtered_records,
        "snapshot": snapshot,
        "filters": filters,
        "execution_meta": execution_meta,
    }


def _parse_iso_datetime(value: Optional[object]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value))
        except Exception:
            return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        # Handle timestamps that may have trailing Z
        normalized = stripped.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            try:
                return datetime.utcfromtimestamp(float(normalized))
            except Exception:
                return None
    return None


def _format_duration(seconds: Optional[object]) -> Optional[str]:
    if seconds is None:
        return None
    try:
        total_seconds = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def _coerce_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _round_optional(value: Optional[object], decimals: int = 2) -> Optional[float]:
    as_float = _coerce_float(value)
    if as_float is None:
        return None
    return round(as_float, decimals)


def _serialize_summary_row(row: Dict[str, object]) -> Dict[str, object]:
    prompt = row.get("Prompt") or ""
    task = row.get("Task") or ""
    prompt_id = row.get("Prompt ID") or ""

    claude_breaking = row.get("Claude Sonnet 4 Breaking") or "No data"
    openai_breaking = row.get("OpenAI Computer Use Preview Breaking") or "No data"
    gemini_breaking = row.get("Google Gemini Computer Use Breaking") or "No data"
    difficulty = row.get("Difficulty") or "Unknown"

    return {
        "prompt": prompt,
        "task": task,
        "prompt_id": prompt_id,
        "claude_sonnet_4_breaking": claude_breaking,
        "openai_computer_use_preview_breaking": openai_breaking,
        "google_gemini_computer_use_breaking": gemini_breaking,
        "difficulty": difficulty,
    }


def _serialize_iteration_row(row: Dict[str, object]) -> Dict[str, object]:
    exec_seconds = _coerce_float(row.get("ExecutionTimeSeconds"))
    return {
        "task": row.get("Task"),
        "iteration": row.get("Iteration"),
        "prompt": row.get("Prompt"),
        "prompt_id": row.get("PromptId"),
        "runner_key": row.get("RunnerKey"),
        "runner_label": row.get("RunnerLabel"),
        "status": row.get("Status"),
        "execution_time_seconds": exec_seconds,
        "execution_time_formatted": row.get("ExecutionTimeFormatted"),
        "start_time": row.get("StartTime"),
        "end_time": row.get("EndTime"),
        "run_id": row.get("RunId"),
    }


def _runner_payload_key(runner_key: str, runner_label: Optional[str] = None) -> str:
    label = runner_label or RUNNER_MODELS.get(runner_key, runner_key)
    sanitized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return sanitized or runner_key


def _serialize_task_iteration(record: IterationRecord) -> Dict[str, object]:
    duration_seconds = record.duration_seconds
    duration_formatted = _format_seconds(duration_seconds) if duration_seconds is not None else None
    status = _extract_record_status(record) or "UNKNOWN"
    tools_executed = _extract_record_tool_usage(record) or "No data"
    comments = ""

    prompt_identifier = record.prompt_id or record.task_id
    iteration_uuid = record.iteration_uuid
    if not iteration_uuid and isinstance(record.extra, dict):
        iteration_uuid = (
            record.extra.get("iteration_uuid")
            or (record.extra.get("backend_verification_results") or {}).get("iteration_uuid")
            or (record.extra.get("backend_verification_results") or {}).get("iteration_id")
        )

    execution_uuid = record.execution_uuid
    if not execution_uuid and isinstance(record.extra, dict):
        execution_uuid = record.extra.get("execution_uuid")

    return {
        "iteration": record.iteration,
        "model_response": _extract_record_model_response(record) or "",
        "tools_executed": tools_executed,
        "status": status,
        "comments": comments,
        "prompt_id": str(prompt_identifier) if prompt_identifier else None,
        "start_time": record.start_timestamp,
        "end_time": record.end_timestamp,
        "duration_seconds": duration_seconds,
        "duration_formatted": duration_formatted,
        "run_id": record.run_id,
        "iteration_uuid": str(iteration_uuid) if iteration_uuid else None,
        "execution_uuid": str(execution_uuid) if execution_uuid else None,
    }


def _build_tasks_block(
    summary_entries: Dict[str, Dict[str, object]],
    snapshot: Dict[str, object],
    task_rows: Dict[str, Dict[str, List[IterationRecord]]],
    include_task_details: bool,
    *,
    execution_meta: Optional[Dict[str, Dict[str, object]]] = None,
) -> Tuple[Dict[str, object], int]:
    tasks_payload: Dict[str, object] = {}
    overall_iterations = 0

    single_task_tables: Dict[str, List[Dict[str, object]]] = snapshot.get("single_task_tables", {})  # type: ignore[assignment]
    task_ids = set(summary_entries.keys()) | set(single_task_tables.keys()) | set(task_rows.keys())

    for task_id in sorted(task_ids):
        summary = summary_entries.get(task_id, {})
        runner_map = task_rows.get(task_id, {})

        prompt = summary.get("prompt")
        if not prompt and single_task_tables.get(task_id):
            prompt = single_task_tables[task_id][0].get("Prompt")
        prompt = prompt or ""

        per_model_iterations: Dict[str, List[Dict[str, object]]] = {}
        execution_meta = execution_meta or {}
        per_model_runs_map: Dict[str, Dict[str, Dict[str, object]]] = {}
        iteration_count = 0
        pass_count = 0
        fail_count = 0

        ordered_runner_keys = [runner_key for runner_key, _ in MODEL_ORDER]
        ordered_runner_keys.extend([key for key in runner_map.keys() if key not in ordered_runner_keys])

        seen_runner_keys: set[str] = set()

        for runner_key in ordered_runner_keys:
            if runner_key in seen_runner_keys:
                continue
            seen_runner_keys.add(runner_key)

            records = runner_map.get(runner_key, [])
            if not records:
                continue

            payload_key = _runner_payload_key(runner_key)
            serialized_records: List[Dict[str, object]] = []

            for record in records:
                status = (_extract_record_status(record) or "").upper() or "UNKNOWN"
                iteration_count += 1
                if status == "PASSED":
                    pass_count += 1
                elif status == "FAILED":
                    fail_count += 1

                if include_task_details:
                    serialized = _serialize_task_iteration(record)
                    serialized["status"] = status
                    if not serialized.get("comments"):
                        serialized["comments"] = ""
                    per_model_iterations.setdefault(payload_key, []).append(serialized)

                    execution_uuid = serialized.get("execution_uuid")
                    if not execution_uuid and isinstance(record.extra, dict):
                        extra_exec = record.extra.get("execution_uuid")
                        if extra_exec:
                            execution_uuid = str(extra_exec)

                    run_identifier = execution_uuid or serialized.get("run_id") or record.run_id
                    if not run_identifier:
                        run_identifier = f"{runner_key}_execution_{len(per_model_runs_map.get(payload_key, {})) + 1}"
                    run_identifier = str(run_identifier)

                    model_runs = per_model_runs_map.setdefault(payload_key, {})
                    run_entry = model_runs.get(run_identifier)
                    if run_entry is None:
                        execution_info = execution_meta.get(run_identifier) or execution_meta.get(execution_uuid or "")
                        run_entry = {
                            "run_id": run_identifier,
                            "execution_id": execution_uuid or (execution_info.get("execution_uuid") if execution_info else None),
                            "execution_model": execution_info.get("model") if execution_info else record.extra.get("execution_model") if isinstance(record.extra, dict) else None,
                            "iterations": [],
                            "passes": 0,
                            "fails": 0,
                            "status_counts": {},
                            "time_start": execution_info.get("created_at") if execution_info else None,
                            "time_end": execution_info.get("updated_at") if execution_info else None,
                            "duration_seconds_avg": None,
                            "duration_formatted_avg": None,
                            "execution_iterations_planned": execution_info.get("number_of_iterations") if execution_info else record.extra.get("execution_iterations_planned") if isinstance(record.extra, dict) else None,
                            "_durations": [],
                            "_iterations_seen": 0,
                        }
                        model_runs[run_identifier] = run_entry

                    run_entry["iterations"].append(serialized)
                    run_entry["_iterations_seen"] = run_entry.get("_iterations_seen", 0) + 1

                    status_counts: Dict[str, int] = run_entry.setdefault("status_counts", {})
                    status_counts[status] = status_counts.get(status, 0) + 1

                    if status == "PASSED":
                        run_entry["passes"] = run_entry.get("passes", 0) + 1
                    elif status == "FAILED":
                        run_entry["fails"] = run_entry.get("fails", 0) + 1

                    durations = run_entry.setdefault("_durations", [])
                    duration_value = serialized.get("duration_seconds")
                    if isinstance(duration_value, (int, float)):
                        durations.append(float(duration_value))

                    start_time = serialized.get("start_time")
                    if isinstance(start_time, str):
                        current_start = run_entry.get("time_start")
                        if not current_start or start_time < current_start:
                            run_entry["time_start"] = start_time

                    end_time = serialized.get("end_time")
                    if isinstance(end_time, str):
                        current_end = run_entry.get("time_end")
                        if not current_end or end_time > current_end:
                            run_entry["time_end"] = end_time

        overall_iterations += iteration_count

        totals_raw = {
            "iterations": iteration_count,
            "passes": pass_count,
            "fails": fail_count,
            "wall_clock_seconds": summary.get("wall_clock_seconds"),
            "wall_clock_formatted": summary.get("wall_clock_formatted"),
            "source_total_time_seconds": summary.get("source_total_time_seconds"),
            "source_total_time_formatted": summary.get("source_total_time_formatted"),
            "average_iteration_minutes": summary.get("average_iteration_minutes"),
        }
        totals = {key: value for key, value in totals_raw.items() if value is not None}

        per_model_runs: Dict[str, List[Dict[str, object]]] = {}
        if include_task_details:
            for model_key, runs in per_model_runs_map.items():
                run_entries: List[Dict[str, object]] = []
                for run_entry in runs.values():
                    durations = run_entry.pop("_durations", [])
                    iterations_seen = run_entry.pop("_iterations_seen", len(run_entry.get("iterations", [])))
                    if durations:
                        avg_duration = sum(durations) / len(durations)
                        run_entry["duration_seconds_avg"] = avg_duration
                        run_entry["duration_formatted_avg"] = _format_seconds(avg_duration)
                    else:
                        run_entry["duration_seconds_avg"] = None
                        run_entry["duration_formatted_avg"] = None

                    status_counts = run_entry.get("status_counts") or {}
                    run_entry["status_counts"] = dict(sorted(status_counts.items()))

                    planned_iterations = run_entry.get("execution_iterations_planned")
                    if planned_iterations is not None and isinstance(planned_iterations, (int, float)):
                        run_entry["iterations_count"] = int(planned_iterations)
                        run_entry["iterations_observed"] = iterations_seen
                    else:
                        run_entry["iterations_count"] = iterations_seen

                    run_entries.append(run_entry)

                run_entries.sort(key=lambda entry: (entry.get("time_start") or "", entry.get("run_id") or ""))
                per_model_runs[model_key] = run_entries

        tasks_payload[task_id] = {
            "prompt": prompt,
            "totals": totals,
            "per_model_iterations": per_model_iterations if include_task_details else {},
            "per_model_runs": per_model_runs if include_task_details else {},
        }

    return tasks_payload, overall_iterations


def _format_all_tasks_summary_response(
    data: Dict[str, object],
    *,
    include_task_details: bool,
) -> Dict[str, object]:
    summary_rows: List[Dict[str, object]] = data["summary_rows"]  # type: ignore[assignment]
    snapshot: Dict[str, object] = data["snapshot"]  # type: ignore[assignment]
    task_rows: Dict[str, Dict[str, List[IterationRecord]]] = data.get("task_rows", {})  # type: ignore[assignment]

    serialized_summary = [_serialize_summary_row(row) for row in summary_rows]
    summary_map = {item["task"]: item for item in serialized_summary if item.get("task")}

    single_task_tables: Dict[str, List[Dict[str, object]]] = snapshot.get("single_task_tables", {})  # type: ignore[assignment]
    all_task_ids = (
        set(summary_map.keys())
        | set(single_task_tables.keys())
        | set(task_rows.keys())
    )

    for task_id in sorted(all_task_ids):
        if task_id not in summary_map:
            iterations_source = single_task_tables.get(task_id, [])
            prompt = ""
            if iterations_source:
                prompt = iterations_source[0].get("Prompt", "")
            summary_entry = {
                "prompt": prompt,
                "task": task_id,
                "prompt_id": task_id,
                "claude_sonnet_4_breaking": "No data",
                "openai_computer_use_preview_breaking": "No data",
                "difficulty": "Unknown",
            }
            serialized_summary.append(summary_entry)
            summary_map[task_id] = summary_entry

    tasks_payload, total_iterations = _build_tasks_block(
        summary_map,
        snapshot,
        task_rows,
        include_task_details,
        execution_meta=data.get("execution_meta"),
    )

    return {
        "summary": serialized_summary,
        "tasks": tasks_payload,
    }


@router.get("/all-tasks-summary", tags=["reports"])
async def get_all_tasks_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    gym_id: UUID = Query(None, description="Filter by gym UUID"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    max_executions: int = Query(10000, description="Maximum number of executions to include"),
    include_task_details: bool = Query(True, description="Include detailed task/runner/iteration data"),
):
    """
    Get JSON export of all tasks across all executions matching the Excel export structure.
    Returns Summary sheet data + optionally Task sheet data.
    """
    try:
        data = await _collect_aggregate_data(db, gym_id, start_date, end_date, max_executions)
        if not data:
            return {
                "summary": [],
                "tasks": {},
                "total_tasks": 0,
                "total_iterations": 0,
                "filters": {
                    "gym_id": None,
                    "gym_name": None,
                    "start_date": start_date,
                    "end_date": end_date,
                    "default_start_date": None,
                    "default_end_date": None,
                    "available_filters": {},
                },
            }

        formatted = _format_all_tasks_summary_response(
            data,
            include_task_details=include_task_details,
        )

        logger.info(
            "📊 Generated JSON export with %d tasks",
            len(formatted.get("tasks", {})),
        )

        return formatted
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting all tasks summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all-tasks-summary/report", tags=["reports"])
async def download_all_tasks_summary_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    gym_id: UUID = Query(None, description="Filter by gym UUID"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    max_executions: int = Query(10000, description="Maximum number of executions to include"),
    include_snapshot: bool = Query(True, description="Also generate JSON snapshot alongside Excel"),
):
    """Generate a filtered aggregate Excel report matching the all-tasks-summary data."""
    try:
        data = await _collect_aggregate_data(db, gym_id, start_date, end_date, max_executions)
        if not data or not data["summary_rows"]:
            raise HTTPException(status_code=404, detail="No execution data found for the specified filters")

        selected_gym = data["selected_gym"]
        gym_name = selected_gym.name if selected_gym else "aggregate"
        filters = data["filters"]

        results_dir = Path(settings.RESULTS_DIR)
        export_dir = results_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        date_suffix = ""
        if filters.get("start_date") or filters.get("end_date"):
            start_part = filters.get("start_date") or "all"
            end_part = filters.get("end_date") or "all"
            date_suffix = f"_{start_part}_to_{end_part}"

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{gym_name}_summary_report{date_suffix}_{timestamp}.xlsx"
        filename = filename.replace(" ", "_").replace("/", "-")
        output_path = export_dir / filename

        _write_workbook(
            summary_rows=data["summary_rows"],
            iterations=data["all_records"],
            task_rows=data["task_rows"],
            workbook_path=output_path,
        )

        json_snapshot_name = None
        if include_snapshot:
            json_snapshot_path = output_path.with_suffix(".json")
            _write_json_snapshot(json_snapshot_path, data["snapshot"])
            json_snapshot_name = json_snapshot_path.name

        download_url = f"/api/v1/executions/files/exports/{filename}?t={int(time.time())}"

        return {
            "message": f"Aggregate report generated for gym {gym_name}",
            "download_url": download_url,
            "filename": filename,
            "json_snapshot": json_snapshot_name,
            "filters": filters,
            "total_tasks": len(data["summary_rows"]),
            "total_iterations": len(data["all_records"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating aggregate report: {e}")
        raise HTTPException(status=500, detail=str(e))


# ============================================================================
# DYNAMIC UUID ROUTES (must be after specific routes)
# ============================================================================

@router.get("/{execution_uuid}", response_model=ExecutionResponseWithStatus)
async def get_execution(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific execution by UUID with enhanced status information"""
    try:
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Return execution with enhanced status information including task status and iteration counts
        return await ExecutionStatusManager.create_execution_response_with_status(execution, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{execution_uuid}", response_model=ExecutionResponse)
async def update_execution(
    execution_uuid: UUID,
    execution_data: ExecutionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an execution"""
    try:
        execution = await execution_crud.update(db, execution_uuid, execution_data)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Return execution with computed status
        return await create_execution_response(execution, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{execution_uuid}")
async def delete_execution(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an execution"""
    try:
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")
        
        # Non-admin users cannot delete executions that belong to a batch
        if execution.batch_id and not current_user.is_admin:
            raise HTTPException(
                status_code=403, 
                detail="Only administrators can delete executions that belong to a batch"
            )

        if (
            execution.execution_type == ExecutionType.PLAYGROUND
            and execution.execution_folder_name
        ):
            execution_dir = Path(settings.RESULTS_DIR) / execution.execution_folder_name
            if execution_dir.exists() and execution_dir.is_dir():
                try:
                    shutil.rmtree(execution_dir)
                    logger.info(
                        "🗑️ Deleted playground execution directory: %s",
                        execution_dir,
                    )
                except Exception as e:
                    logger.error(
                        "❌ Failed to delete playground execution directory %s: %s",
                        execution_dir,
                        e,
                    )
            else:
                logger.info(
                    "ℹ️ Playground execution directory not found: %s",
                    execution_dir,
                )

        success = await execution_crud.delete(db, execution_uuid)
        if not success:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        return {"message": f"Execution {execution_uuid} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/files")
async def list_execution_files(
    execution_uuid: UUID,
    format: str = Query("hierarchical", description="Response format: 'flat' or 'hierarchical'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all files (logs, screenshots, JSON) for an execution with metadata in hierarchical or flat format"""
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Build results directory path
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name

        if not execution_dir.exists():
            raise HTTPException(status_code=404, detail=f"Execution directory not found: {execution.execution_folder_name}")

        files_metadata = []

        # Scan execution directory for files
        file_count = 0
        for file_path in execution_dir.rglob("*"):
            if file_path.is_file():
                file_count += 1
                try:
                    stat = file_path.stat()
                    relative_path = file_path.relative_to(execution_dir)

                    # Determine file type
                    file_type = "unknown"
                    if file_path.suffix == ".log":
                        file_type = "log"
                    elif file_path.suffix == ".png":
                        file_type = "screenshot"
                    elif file_path.suffix == ".json":
                        file_type = "json"
                    elif file_path.suffix == ".csv":
                        file_type = "csv"

                    # Calculate relative time from execution start
                    file_created_time = datetime.fromtimestamp(stat.st_ctime)
                    file_modified_time = datetime.fromtimestamp(stat.st_mtime)

                    # Get execution for relative time calculation
                    execution_start = execution.created_at
                    seconds_since_start = 0
                    
                    # Calculate seconds since execution started when file was created
                    if execution_start:
                        # Handle timezone-aware vs timezone-naive datetime comparison
                        if execution_start.tzinfo is not None and file_created_time.tzinfo is None:
                            # Make file_created_time timezone-aware (assume UTC)
                            file_created_time = file_created_time.replace(tzinfo=timezone.utc)
                        elif execution_start.tzinfo is None and file_created_time.tzinfo is not None:
                            # Make execution_start timezone-aware (assume UTC)
                            execution_start = execution_start.replace(tzinfo=timezone.utc)
                        elif execution_start.tzinfo is None and file_created_time.tzinfo is None:
                            # Both are timezone-naive, no conversion needed
                            pass
                        # If both are timezone-aware, no conversion needed
                        
                        seconds_since_start = (file_created_time - execution_start).total_seconds()
                        seconds_since_start = max(0, seconds_since_start)  # Don't show negative times

                        # Format relative time
                        if seconds_since_start < 60:
                            relative_time = f"{int(seconds_since_start)}s into execution"
                        elif seconds_since_start < 3600:
                            minutes = int(seconds_since_start // 60)
                            seconds = int(seconds_since_start % 60)
                            relative_time = f"{minutes}m {seconds}s into execution"
                        else:
                            hours = int(seconds_since_start // 3600)
                            minutes = int((seconds_since_start % 3600) // 60)
                            relative_time = f"{hours}h {minutes}m into execution"
                    else:
                        relative_time = "Unknown"

                    files_metadata.append({
                        "path": str(relative_path),
                        "name": file_path.name,
                        "type": file_type,
                        "size": stat.st_size,
                        "created_at": file_created_time.isoformat(),
                        "modified_at": file_modified_time.isoformat(),
                        "relative_created_at": relative_time,
                        "seconds_into_execution": int(seconds_since_start) if execution_start else 0,
                        "extension": file_path.suffix
                    })
                except Exception as e:
                    logger.warning(f"Error reading file metadata for {file_path}: {e}")
                    continue


        # Sort files by creation time (most recent first)
        files_metadata.sort(key=lambda x: x["created_at"], reverse=True)

        # Return response based on format
        if format == "hierarchical":
            return {
                "execution_id": str(execution_uuid),
                "execution_folder": execution.execution_folder_name,
                "total_files": len(files_metadata),
                "structure": build_hierarchical_structure(files_metadata)
            }
        else:  # flat format (backward compatibility)
            return {
                "execution_id": str(execution_uuid),
                "execution_folder": execution.execution_folder_name,
                "total_files": len(files_metadata),
                "files": files_metadata
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files for execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/iterations/{iteration_id}/files")
async def list_iteration_files(
    execution_uuid: UUID,
    iteration_id: UUID,
    format: str = Query("hierarchical", description="Response format: 'flat' or 'hierarchical'"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List files for a specific iteration within an execution."""
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Get iteration record to get iteration number
        iteration = await iteration_crud.get(db, iteration_id)
        if not iteration:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} not found")
        
        
        # Verify iteration belongs to this execution
        if str(iteration.execution_id) != str(execution_uuid):
            raise HTTPException(status_code=400, detail=f"Iteration {iteration_id} does not belong to execution {execution_uuid}")

        # Build results directory path
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name

        if not execution_dir.exists():
            raise HTTPException(status_code=404, detail=f"Execution directory not found: {execution.execution_folder_name}")

        # Get task_id from parent execution's snapshot field
        task_identifier = execution.task_identifier
        if not task_identifier:
            raise HTTPException(
                status_code=404, 
                detail=f"Task identifier not found for execution {execution.uuid}"
            )
        
        
        # Check if the specific iteration folder exists
        # Structure: execution_folder/task_id/iteration_{number}/
        iteration_key = f"iteration_{iteration.iteration_number}"
        iteration_dir = execution_dir / task_identifier / iteration_key
        
        
        if not iteration_dir.exists():
            # List available directories for debugging
            available_dirs = []
            if execution_dir.exists():
                for item in execution_dir.iterdir():
                    if item.is_dir():
                        available_dirs.append(item.name)
            logger.warning(f"Available directories in {execution_dir}: {available_dirs}")
            
            raise HTTPException(
                status_code=404, 
                detail=f"Iteration folder not found: {task_identifier}/{iteration_key} in execution {execution.execution_folder_name}. Available directories: {available_dirs}"
            )

        files_metadata = []
        

        # Iterate only files within the specific iteration folder
        for file_path in iteration_dir.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                # Calculate relative path from the execution directory
                relative_path = file_path.relative_to(execution_dir)

                stat = file_path.stat()

                # Determine file type
                file_type = "unknown"
                if file_path.suffix == ".log":
                    file_type = "log"
                elif file_path.suffix == ".png":
                    file_type = "screenshot"
                elif file_path.suffix == ".json":
                    file_type = "json"
                elif file_path.suffix == ".csv":
                    file_type = "csv"
                elif file_path.suffix == ".txt":
                    file_type = "text"
                elif file_path.suffix == ".html":
                    file_type = "html"
                elif file_path.suffix == ".xml":
                    file_type = "xml"
                elif file_path.suffix == ".yaml" or file_path.suffix == ".yml":
                    file_type = "yaml"
                else:
                    file_type = "other"

                file_created_time = datetime.fromtimestamp(stat.st_ctime)
                file_modified_time = datetime.fromtimestamp(stat.st_mtime)

                execution_start = execution.created_at
                if execution_start:
                    if execution_start.tzinfo is not None and file_created_time.tzinfo is None:
                        file_created_time = file_created_time.replace(tzinfo=timezone.utc)
                    elif execution_start.tzinfo is None and file_created_time.tzinfo is not None:
                        execution_start = execution_start.replace(tzinfo=timezone.utc)

                    seconds_since_start = (file_created_time - execution_start).total_seconds()
                    seconds_since_start = max(0, seconds_since_start)
                    if seconds_since_start < 60:
                        relative_time = f"{int(seconds_since_start)}s into execution"
                    elif seconds_since_start < 3600:
                        minutes = int(seconds_since_start // 60)
                        seconds = int(seconds_since_start % 60)
                        relative_time = f"{minutes}m {seconds}s into execution"
                    else:
                        hours = int(seconds_since_start // 3600)
                        minutes = int((seconds_since_start % 3600) // 60)
                        relative_time = f"{hours}h {minutes}m into execution"
                else:
                    relative_time = "Unknown"

                file_metadata = {
                    "path": str(relative_path),
                    "name": file_path.name,
                    "type": file_type,
                    "size": stat.st_size,
                    "created_at": file_created_time.isoformat(),
                    "modified_at": file_modified_time.isoformat(),
                    "relative_created_at": relative_time,
                    "seconds_into_execution": int(seconds_since_start) if execution_start else 0,
                    "extension": file_path.suffix,
                }
                
                files_metadata.append(file_metadata)
            except Exception as e:
                logger.warning(f"Error reading file metadata for {file_path}: {e}")
                continue

        # Sort files by creation time (most recent first)
        files_metadata.sort(key=lambda x: x["created_at"], reverse=True)
        

        # Return response based on format
        if format == "hierarchical":
            return {
                "execution_id": str(execution_uuid),
                "execution_folder": execution.execution_folder_name,
                "total_files": len(files_metadata),
                "structure": build_hierarchical_structure(files_metadata),
            }
        else:
            return {
                "execution_id": str(execution_uuid),
                "execution_folder": execution.execution_folder_name,
                "total_files": len(files_metadata),
                "files": files_metadata,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files for execution {execution_uuid}, iteration {iteration_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{execution_uuid}/files/{file_path:path}")
async def get_execution_file(
    execution_uuid: UUID,
    file_path: str,
    token: Optional[str] = Query(None, description="Authentication token for file access"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Serve a specific file from an execution (logs, screenshots, JSON, etc.)"""
    try:
        logger.info(f"Getting file for execution {execution_uuid}, file_path: {file_path}")

        # Handle authentication - either from Bearer token or query parameter
        authenticated_user = current_user
        if token and not authenticated_user:
            try:
                authenticated_user = await get_current_user_from_token(token, db)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Invalid authentication token")

        if not authenticated_user:
            raise HTTPException(status_code=403, detail="Authentication required")

        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            logger.error(f"Execution {execution_uuid} not found in database")
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        logger.info(f"Found execution: folder_name={execution.execution_folder_name}")

        # Build file path
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name
        full_file_path = execution_dir / file_path

        logger.info(f"File paths - results_dir: {results_dir}, execution_dir: {execution_dir}, full_file_path: {full_file_path}")

        # Security check: ensure file is within execution directory
        try:
            resolved_file_path = full_file_path.resolve()
            resolved_execution_dir = execution_dir.resolve()
            relative_path = resolved_file_path.relative_to(resolved_execution_dir)
            logger.info(f"Security check passed - relative_path: {relative_path}")
        except ValueError as ve:
            logger.error(f"Security check failed: {ve}")
            raise HTTPException(status_code=403, detail="Access denied: file path outside execution directory")

        logger.info(f"Checking if file exists: {full_file_path}")
        if not full_file_path.exists():
            logger.error(f"File does not exist: {full_file_path}")
            # List files in execution directory for debugging
            if execution_dir.exists():
                logger.info(f"Files in execution dir: {list(execution_dir.glob('**/*'))}")
            else:
                logger.error(f"Execution directory does not exist: {execution_dir}")
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not full_file_path.is_file():
            logger.error(f"Path exists but is not a file: {full_file_path}")
            raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

        # Determine media type based on file extension
        media_type = "application/octet-stream"
        if full_file_path.suffix == ".png":
            media_type = "image/png"
        elif full_file_path.suffix == ".jpg" or full_file_path.suffix == ".jpeg":
            media_type = "image/jpeg"
        elif full_file_path.suffix == ".json":
            media_type = "application/json"
        elif full_file_path.suffix == ".csv":
            media_type = "text/csv"
        elif full_file_path.suffix == ".log":
            media_type = "text/plain"
        elif full_file_path.suffix == ".txt":
            media_type = "text/plain"

        logger.info(f"Serving file: {full_file_path} with media_type: {media_type}")
        return FileResponse(
            path=str(full_file_path),
            media_type=media_type,
            filename=full_file_path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file {file_path} for execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/iterations/{iteration_id}/download")
async def download_iteration(
    execution_uuid: UUID,
    iteration_id: UUID,
    token: Optional[str] = Query(None, description="Authentication token for file access"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Download all files for a specific iteration as a ZIP archive"""
    try:
        # Handle authentication - either from Bearer token or query parameter
        authenticated_user = current_user
        if token and not authenticated_user:
            try:
                authenticated_user = await get_current_user_from_token(token, db)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Invalid authentication token")

        if not authenticated_user:
            raise HTTPException(status_code=403, detail="Authentication required")

        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Get iteration record
        iteration = await iteration_crud.get(db, iteration_id)
        if not iteration:
            raise HTTPException(status_code=404, detail=f"Iteration {iteration_id} not found")

        # Verify iteration belongs to this execution
        if str(iteration.execution_id) != str(execution_uuid):
            raise HTTPException(
                status_code=400,
                detail=f"Iteration {iteration_id} does not belong to execution {execution_uuid}"
            )

        # Get task identifier from execution
        task_identifier = execution.task_identifier
        if not task_identifier:
            raise HTTPException(
                status_code=404,
                detail=f"Task identifier not found for execution {execution.uuid}"
            )

        # Build execution directory path
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name

        if not execution_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Execution directory not found: {execution.execution_folder_name}"
            )

        # Generate ZIP filename
        zip_filename = f"{execution.execution_folder_name}_iteration_{iteration.iteration_number}.zip"

        # Stream the ZIP archive
        try:
            zip_stream = archive_service.stream_iteration_zip(
                execution_dir,
                task_identifier,
                iteration.iteration_number
            )
            return StreamingResponse(
                zip_stream,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{zip_filename}"'
                }
            )
        except ValueError as e:
            logger.error(f"Error generating iteration ZIP: {e}")
            raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading iteration {iteration_id} for execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/download")
async def download_execution(
    execution_uuid: UUID,
    token: Optional[str] = Query(None, description="Authentication token for file access"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Download all files for an execution as a ZIP archive"""
    try:
        # Handle authentication - either from Bearer token or query parameter
        authenticated_user = current_user
        if token and not authenticated_user:
            try:
                authenticated_user = await get_current_user_from_token(token, db)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Invalid authentication token")

        if not authenticated_user:
            raise HTTPException(status_code=403, detail="Authentication required")

        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        if not execution.execution_folder_name:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {execution_uuid} has no execution folder name"
            )

        # Build execution directory path
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name

        if not execution_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Execution directory not found: {execution.execution_folder_name}"
            )

        # Generate ZIP filename
        zip_filename = f"{execution.execution_folder_name}.zip"

        # Stream the ZIP archive
        try:
            zip_stream = archive_service.stream_execution_zip(execution_dir)
            return StreamingResponse(
                zip_stream,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{zip_filename}"'
                }
            )
        except ValueError as e:
            logger.error(f"Error generating execution ZIP: {e}")
            raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/summary")
async def get_execution_summary(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get execution summary data with iterations grouped by task_id"""
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")

        # Get all iterations for this execution
        iterations = await iteration_crud.get_by_execution_id(db, execution_uuid)
        logger.info(f"📊 get_execution_summary for {execution_uuid}: Found {len(iterations)} iterations")
        
        # Get task_identifier from parent execution (all iterations belong to same task)
        task_identifier = execution.task_identifier
        if not task_identifier:
            logger.warning(f"⚠️  No task_identifier for execution {execution_uuid}")
            return {}
        
        logger.debug(f"✅ Using task_identifier {task_identifier} from execution {execution_uuid}")
        
        # Group iterations by task_id (all iterations in this execution have same task)
        summary_data = {task_identifier: {}}
        
        for iteration in iterations:
            iteration_key = f"iteration_{iteration.iteration_number}"
            
            # Parse verification_details JSON if it exists
            verification_details = None
            if iteration.verification_details:
                try:
                    verification_details = json.loads(iteration.verification_details)
                except json.JSONDecodeError as e:
                    logger.warning(f"Error parsing verification_details for iteration {iteration.uuid}: {e}")
                    verification_details = {"error": f"Could not parse verification details: {e}"}
            
            # Merge verification_details with iteration database fields
            iteration_data = verification_details or {}
            
            # Add iteration-level fields that aren't in verification_details JSON
            iteration_data["_iteration_started_at"] = iteration.started_at.timestamp() if iteration.started_at else None
            iteration_data["_iteration_completed_at"] = iteration.completed_at.timestamp() if iteration.completed_at else None
            iteration_data["_iteration_execution_time_seconds"] = iteration.execution_time_seconds
            # Handle status - could be enum or string
            if iteration.status:
                iteration_data["_iteration_status"] = iteration.status.value if hasattr(iteration.status, 'value') else iteration.status
            else:
                iteration_data["_iteration_status"] = None
            
            # Store complete iteration data
            summary_data[task_identifier][iteration_key] = iteration_data

        logger.info(f"📊 get_execution_summary for {execution_uuid}: Returning {len(summary_data)} tasks")
        for tid, iterations_dict in summary_data.items():
            logger.debug(f"   → Task {tid}: {len(iterations_dict)} iterations")
        
        return {
            "execution_id": str(execution_uuid),
            "execution_folder": execution.execution_folder_name,
            "summary": summary_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting summary for execution {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/tasks-detail")
async def get_execution_tasks_detail(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed task data for a specific execution.
    Each task includes all its iteration details nested within it.
    
    Returns one entry per task with iteration details embedded:
    - execution: Execution folder name
    - task_id: Task identifier
    - prompt: Task prompt
    - model: Model used for this execution
    - iterations: Array of iteration details with status, attempts, time, etc.
    - summary: Aggregated metrics (total time, avg time, difficulty, etc.)
    """
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")
        
        ex_folder = execution.execution_folder_name
        logger.info(f"Fetching tasks detail for execution {ex_folder}")
        
        # Get execution summary
        summary = await get_execution_summary(execution_uuid, db, current_user)
        summary_data = (summary or {}).get("summary") or {}
        
        if not summary_data:
            logger.debug(f"No summary data for execution {ex_folder}")
            return {
                "execution": ex_folder,
                "execution_uuid": str(execution_uuid),
                "model": execution.model,
                "tasks": [],
                "total_tasks": 0
            }
        
        all_tasks = []
        
        # Process each task in this execution
        for task_id, iterations in summary_data.items():
            if not iterations:
                continue
            
            # Fetch task prompt
            prompt = None
            try:
                task_result = await task_crud.get_by_task_id_and_gym(db, task_id, execution.gym_id)
                if task_result:
                    prompt = task_result.prompt
            except Exception as e:
                logger.error(f"Error fetching prompt for task {task_id}: {e}")
            
            # Build iteration details array
            iteration_details = []
            for iter_key, verification in iterations.items():
                if not verification:
                    verification = {}
                
                status = verification.get("verification_status") or verification.get("status") or verification.get("_iteration_status") or "pending"
                attempts = verification.get("execution_steps", 0)
                
                # Get execution time
                exec_secs = (
                    verification.get("_iteration_execution_time_seconds") or
                    verification.get("execution_time") or
                    0.0
                )
                time_mins = round(exec_secs / 60.0, 2) if exec_secs else 0.0
                
                # Get timestamps for timelapse
                start_ts = verification.get("_iteration_started_at") or verification.get("start_time") or 0
                end_ts = verification.get("_iteration_completed_at") or verification.get("end_time") or 0
                timelapse_str = None
                if start_ts and end_ts:
                    elapsed = float(end_ts - start_ts)
                    timelapse_str = _hms(elapsed)
                
                screenshots = len(verification.get("screenshots", []))
                
                # Add iteration detail
                iteration_details.append({
                    "iteration": iter_key,
                    "status": status,
                    "attempts": attempts,
                    "execution_time_mins": time_mins,
                    "timelapse": timelapse_str,
                    "screenshots_count": screenshots
                })
            
            # Get aggregated task summary using shared function
            task_summary = await _aggregate_task_data(
                task_id=task_id,
                iterations=iterations,
                gym_id=execution.gym_id,
                db=db,
                include_model_breaking=False,
                execution_model=execution.model
            )
            
            # Build task entry with nested iterations
            all_tasks.append({
                "task_id": task_id,
                "prompt": prompt,
                "model": execution.model or "unknown",
                "iterations": iteration_details,
                "summary": {
                    "difficulty": task_summary["difficulty"],
                    "total_time_mins": task_summary["total_time_mins"],
                    "avg_iteration_time_mins": task_summary["avg_iteration_time_mins"],
                    "total_timelapse": task_summary["total_timelapse"],
                    "iteration_count": task_summary["iteration_count"],
                    "total_attempts": task_summary["total_attempts"]
                }
            })
        
        logger.info(f"Execution {ex_folder}: {len(all_tasks)} tasks")
        
        return {
            "execution": ex_folder,
            "execution_uuid": str(execution_uuid),
            "model": execution.model,
            "tasks": all_tasks,
            "total_tasks": len(all_tasks)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution tasks detail for {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/tasks-detail-enhanced")
async def get_execution_tasks_detail_enhanced(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed task data for a specific execution with enhanced fields.
    
    Uses the report service's data collection (DRY principle) to provide:
    - Runner information (runner, runner_label)
    - Completion and status reasons
    - All timestamps and durations
    - Timelapse calculations
    
    Note: Tool call data (tool_calls_total, tool_calls_by_tool, unique_tools) 
    is excluded from JSON API as it's too technical for UI display.
    This data is available in Excel reports for detailed analysis.
    """
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")
        
        # Get execution directory
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name
        
        if not execution_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Execution directory not found: {execution.execution_folder_name}"
            )
        
        logger.info(f"Collecting enhanced data for {execution.execution_folder_name}")
        
        # Use report service's data collection (DRY - single source of truth)
        try:
            iteration_records = collect_execution_data(execution_dir)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Error collecting execution data: {e}")
            raise HTTPException(status_code=500, detail=f"Error collecting data: {str(e)}")
        
        # Inject prompts from database
        for record in iteration_records:
            if not record.prompt:
                try:
                    task = await task_crud.get_by_task_id_and_gym(db, record.task_id, execution.gym_id)
                    if task:
                        record.prompt = task.prompt
                except Exception as e:
                    logger.debug(f"Could not fetch prompt for {record.task_id}: {e}")
        
        # Group by task
        tasks_data = {}
        for record in iteration_records:
            if record.task_id not in tasks_data:
                tasks_data[record.task_id] = {
                    "task_id": record.task_id,
                    "prompt": record.prompt,
                    "model": record.model or execution.model,
                    "iterations": []
                }
            
            # Add iteration with user-friendly fields (exclude technical tool call data)
            tasks_data[record.task_id]["iterations"].append({
                "iteration": record.iteration,
                "runner": record.runner,
                "runner_label": record.runner_label,
                "status": record.status,
                "status_reason": record.status_reason,
                "completion_reason": record.completion_reason,
                "duration_seconds": record.duration_seconds,
                "timelapse": record.timelapse,
                "run_id": record.run_id,
                "start_timestamp": record.start_timestamp,
                "end_timestamp": record.end_timestamp
                # Note: tool_calls_* fields excluded - too technical for UI
                # Available in Excel reports for detailed analysis
            })
        
        return {
            "execution": execution.execution_folder_name,
            "execution_uuid": str(execution_uuid),
            "model": execution.model,
            "tasks": list(tasks_data.values()),
            "total_tasks": len(tasks_data),
            "total_iterations": len(iteration_records)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting enhanced execution tasks detail for {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{execution_uuid}/report", tags=["reports"])
async def generate_execution_report_endpoint(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate an enhanced Excel report for a single execution using the report service.
    
    This uses the advanced report generation service which includes:
    - Tool call tracking and analysis
    - Ground truth comparison (expected vs actual)
    - Claude Sonnet 4, and OpenAI CUA support
    - Grouped column headers
    - Per-task detailed sheets
    
    Returns download URL for the generated report.
    """
    try:
        # Get execution record
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_uuid} not found")
        
        # Get execution directory
        results_dir = Path(settings.RESULTS_DIR)
        execution_dir = results_dir / execution.execution_folder_name
        
        if not execution_dir.exists():
            raise HTTPException(
                status_code=404, 
                detail=f"Execution directory not found: {execution.execution_folder_name}"
            )
        
        # Create export directory
        export_dir = results_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{execution.execution_folder_name}_report_{timestamp}.xlsx"
        output_path = export_dir / filename
        
        logger.info(f"Generating enhanced report for {execution.execution_folder_name}")
        
        # Use the report service to generate the report
        report_path = generate_execution_report(
            execution_dir=execution_dir,
            output_path=output_path,
            write_json=True  # Also generate JSON snapshot
        )
        
        download_url = f"/api/v1/executions/files/exports/{filename}?t={int(time.time())}"
        
        return {
            "message": f"Enhanced report generated for execution {execution.execution_folder_name}",
            "download_url": download_url,
            "filename": filename,
            "execution": execution.execution_folder_name,
            "json_snapshot": f"{filename.replace('.xlsx', '.json')}"
        }
    
    except HTTPException:
        raise
    except FileNotFoundError as e:
        logger.error(f"File not found generating report: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"Invalid data for report generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating execution report for {execution_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{execution_id}/iterations/{iteration_id}/timeline",
    response_model=TimelineResponse,
    summary="Get action timeline for iteration",
    description="Get the complete action timeline including model thinking and actions for an iteration"
)
async def get_iteration_timeline(
    execution_id: str,
    iteration_id: str,
    live: bool = Query(False, description="Include partial results for executing iterations"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get action timeline for iteration"""
    user_email = current_user.email if current_user else "anonymous"
    logger.info(f"Timeline request for execution={execution_id}, iteration={iteration_id}, user={user_email}")
    try:
        execution_uuid = UUID(execution_id)
        iteration_uuid = UUID(iteration_id)
        
        # Get execution and iteration from database
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        iteration = await iteration_crud.get(db, iteration_uuid)
        if not iteration:
            raise HTTPException(status_code=404, detail="Iteration not found")
        
        # Check if iteration belongs to execution
        if iteration.execution_id != execution_uuid:
            raise HTTPException(status_code=400, detail="Iteration does not belong to execution")
        
        entries = []
        
        # Build iteration directory path
        results_dir = Path(settings.RESULTS_DIR)
        iteration_path = results_dir / execution.execution_folder_name / execution.task_identifier / f"iteration_{iteration.iteration_number}"
        
        # ✅ SINGLE SOURCE OF TRUTH: action_timeline.json (works for ALL models)
        # This file is created when iteration starts and updated in real-time
        if iteration_path.exists():
            action_timeline_file = iteration_path / "action_timeline.json"
            if action_timeline_file.exists():
                try:
                    import json
                    with open(action_timeline_file, 'r') as f:
                        timeline_data = json.load(f)
                    
                    raw_entries = timeline_data.get('entries', [])
                    logger.info(f"✅ Found action_timeline.json with {len(raw_entries)} entries")
                    
                    # Parse entries into Timeline objects
                    from app.schemas.action_timeline import ModelThinkingEntry, ModelResponseEntry, ActionEntry
                    
                    for raw_entry in raw_entries:
                        try:
                            entry_type = raw_entry.get('entry_type')
                            
                            if entry_type == 'model_thinking':
                                entries.append(ModelThinkingEntry(**raw_entry))
                            elif entry_type == 'model_response':
                                entries.append(ModelResponseEntry(**raw_entry))
                            elif entry_type == 'action':
                                entries.append(ActionEntry(**raw_entry))
                        except Exception as e:
                            logger.warning(f"Failed to parse timeline entry: {e}")
                            continue
                    
                    logger.info(f"✅ Loaded {len(entries)} entries from action_timeline.json")
                except Exception as e:
                    logger.error(f"Failed to load action_timeline.json: {e}")
                    entries = []
        
        # ✅ FALLBACK 1: Try database (for completed iterations that have been processed)
        if not entries and iteration.action_timeline_json and iteration.status not in ['pending', 'executing']:
            try:
                entries = timeline_parser.deserialize_timeline(iteration.action_timeline_json)
                logger.info(f"✅ Loaded {len(entries)} entries from DATABASE")
            except Exception as e:
                logger.warning(f"Failed to load timeline from database: {e}")
                entries = []
        
        # ✅ FALLBACK 2: Parse old conversation_history file (legacy)
        if not entries and iteration_path.exists():
            conversation_dir = iteration_path / "conversation_history"
            if conversation_dir.exists():
                conversation_files = list(conversation_dir.glob("*_task_execution_conversation.json"))
                if conversation_files:
                    conversation_file = conversation_files[0]
                    entries = timeline_parser.parse_conversation_history(conversation_file)
                    logger.info(f"✅ Parsed {len(entries)} entries from legacy conversation history")
        
        # Calculate counts
        total_entries = len(entries)
        total_actions = sum(1 for e in entries if e.entry_type == 'action')
        
        return TimelineResponse(
            entries=entries,
            total_entries=total_entries,
            total_actions=total_actions,
            execution_id=execution_id,
            iteration_id=iteration_id
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting timeline for iteration {iteration_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{execution_id}/iterations/{iteration_id}/actions/{action_id}/screenshot",
    summary="Get screenshot for action",
    description="Get the screenshot image file for a specific action"
)
async def get_action_screenshot(
    execution_id: str,
    iteration_id: str,
    action_id: str,
    variant: Literal["before", "after"] = Query("after", description="Which screenshot variant to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional)
):
    """Get screenshot for specific action"""
    try:
        execution_uuid = UUID(execution_id)
        iteration_uuid = UUID(iteration_id)
        
        # Get execution and iteration
        execution = await execution_crud.get(db, execution_uuid)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        iteration = await iteration_crud.get(db, iteration_uuid)
        if not iteration:
            raise HTTPException(status_code=404, detail="Iteration not found")
        
        # Build iteration directory path
        results_dir = Path(settings.RESULTS_DIR)
        iteration_path = results_dir / execution.execution_folder_name / execution.task_identifier / f"iteration_{iteration.iteration_number}"
        
        # ✅ Load timeline from action_timeline.json FILE (for executing) or DATABASE (for completed)
        entries = []
        action_timeline_file = iteration_path / "action_timeline.json"
        
        if action_timeline_file.exists():
            # Read from file (live data)
            try:
                import json
                with open(action_timeline_file, 'r') as f:
                    timeline_data = json.load(f)
                
                raw_entries = timeline_data.get('entries', [])
                from app.schemas.action_timeline import ModelThinkingEntry, ModelResponseEntry, ActionEntry
                
                for raw_entry in raw_entries:
                    try:
                        entry_type = raw_entry.get('entry_type')
                        if entry_type == 'action':
                            entries.append(ActionEntry(**raw_entry))
                        elif entry_type == 'model_thinking':
                            entries.append(ModelThinkingEntry(**raw_entry))
                        elif entry_type == 'model_response':
                            entries.append(ModelResponseEntry(**raw_entry))
                    except Exception as e:
                        logger.warning(f"Failed to parse timeline entry: {e}")
                        continue
                
                logger.info(f"✅ Loaded {len(entries)} entries from action_timeline.json FILE")
            except Exception as e:
                logger.error(f"Failed to load action_timeline.json: {e}")
        
        # Fallback to database if file is empty
        if not entries and iteration.action_timeline_json:
            entries = timeline_parser.deserialize_timeline(iteration.action_timeline_json)
            logger.info(f"✅ Loaded {len(entries)} entries from DATABASE")
        
        # Find the action
        action = None
        for entry in entries:
            if entry.id == action_id and entry.entry_type == 'action':
                action = entry
                break
        
        if not action:
            raise HTTPException(status_code=404, detail="Screenshot not found for this action")
        
        # Determine which screenshot to return
        screenshot_rel_path: Optional[str] = None
        if variant == "before":
            screenshot_rel_path = action.screenshot_before
            if not screenshot_rel_path:
                # Fallback to after if before missing
                screenshot_rel_path = action.screenshot_after or action.screenshot_path
        else:
            screenshot_rel_path = action.screenshot_after or action.screenshot_path

        if not screenshot_rel_path:
            raise HTTPException(status_code=404, detail="Screenshot not available for this variant")
        
        # Build full path to screenshot
        results_dir = Path(settings.RESULTS_DIR)
        iteration_path = results_dir / execution.execution_folder_name / execution.task_identifier / f"iteration_{iteration.iteration_number}"
        screenshot_path = iteration_path / screenshot_rel_path
        
        logger.info(f"Looking for screenshot at: {screenshot_path}")
        
        if not screenshot_path.exists():
            # Try alternative paths
            # 1. Look for iteration_end screenshot
            iteration_end_pattern = f"iteration_{iteration.iteration_number}_iteration_end_*.png"
            end_screenshots = list(iteration_path.glob(f"screenshots/{iteration_end_pattern}"))
            
            if end_screenshots:
                screenshot_path = end_screenshots[0]
                logger.info(f"Using iteration end screenshot: {screenshot_path}")
            else:
                # 2. Try to find any screenshot in the iteration
                all_screenshots = list((iteration_path / "screenshots").glob("*.png"))
                if all_screenshots:
                    # Use the last screenshot (most recent)
                    screenshot_path = sorted(all_screenshots, key=lambda p: p.stat().st_mtime)[-1]
                    logger.info(f"Using last screenshot: {screenshot_path}")
                else:
                    logger.error(f"No screenshots found in {iteration_path / 'screenshots'}")
                    raise HTTPException(status_code=404, detail="No screenshots available for this iteration")
        
        # Create FileResponse with CORS headers
        response = FileResponse(
            path=screenshot_path,
            media_type="image/png",
            filename=screenshot_path.name
        )
        
        # Add CORS headers explicitly for file responses
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        
        return response
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting screenshot for action {action_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
