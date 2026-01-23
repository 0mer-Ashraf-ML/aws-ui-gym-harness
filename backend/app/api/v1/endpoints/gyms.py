"""
Gym management endpoints
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_current_admin_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.gym import GymCreate, GymListResponse, GymListWithTaskCountResponse, GymResponse, GymUpdate
from app.schemas.task import TaskExportResponse, GymTasksExportResponse
from app.services.crud.execution import execution_crud
from app.services.crud.gym import gym_crud
from app.services.crud.task import task_crud
from app.services.reports import generate_combined_report, collect_execution_data
from app.utils.url_normalizer import normalize_base_url

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=GymResponse)
@router.post("", response_model=GymResponse)
async def create_gym(
    gym_data: GymCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new gym"""
    try:
        # Check if gym with same name already exists
        existing_gym = await gym_crud.get_by_name(db, gym_data.name)
        if existing_gym:
            raise HTTPException(
                status_code=400, 
                detail=f"Gym with name '{gym_data.name}' already exists"
            )
        
        # Normalize and check for duplicate base_url + verification_strategy
        normalized_url = normalize_base_url(gym_data.base_url)
        existing_gym = await gym_crud.get_by_base_url_and_strategy(
            db, normalized_url, gym_data.verification_strategy
        )
        if existing_gym:
            raise HTTPException(
                status_code=400,
                detail=f"A gym with base URL '{normalized_url}' and verification strategy '{gym_data.verification_strategy.value}' already exists (Gym: '{existing_gym.name}')"
            )
        
        # Normalize base_url before saving
        gym_data_dict = gym_data.model_dump()
        gym_data_dict['base_url'] = normalized_url
        gym_data_normalized = GymCreate(**gym_data_dict)
        
        gym = await gym_crud.create(db, gym_data_normalized)
        return gym
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating gym: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=GymListResponse)
@router.get("", response_model=GymListResponse)
async def get_gyms(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_tasks: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all gyms with pagination"""
    try:
        if include_tasks:
            gyms = await gym_crud.get_multi_with_tasks(db, skip=skip, limit=limit)
        else:
            gyms = await gym_crud.get_multi(db, skip=skip, limit=limit)
        
        total = await gym_crud.count(db)
        
        return GymListResponse(
            gyms=gyms,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error getting gyms: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/with-task-counts", response_model=GymListWithTaskCountResponse)
async def get_gyms_with_task_counts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all gyms with their task counts"""
    try:
        gyms_with_counts = await gym_crud.get_multi_with_task_counts(db, skip=skip, limit=limit)
        total = await gym_crud.count(db)
        
        return GymListWithTaskCountResponse(
            gyms=gyms_with_counts,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error getting gyms with task counts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{gym_uuid}", response_model=GymResponse)
async def get_gym(
    gym_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific gym by UUID"""
    try:
        gym = await gym_crud.get(db, gym_uuid)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        return gym
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting gym {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{gym_uuid}", response_model=GymResponse)
async def update_gym(
    gym_uuid: UUID,
    gym_data: GymUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a gym"""
    try:
        # Check if name is being updated and if it conflicts
        if gym_data.name:
            existing_gym = await gym_crud.get_by_name(db, gym_data.name)
            if existing_gym and existing_gym.uuid != gym_uuid:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Gym with name '{gym_data.name}' already exists"
                )
        
        # Check if base_url or verification_strategy is being updated and if it conflicts
        if gym_data.base_url or gym_data.verification_strategy:
            # Get current gym to determine what to check
            current_gym = await gym_crud.get(db, gym_uuid)
            if not current_gym:
                raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
            
            # Use new values or keep existing ones
            check_url = normalize_base_url(gym_data.base_url) if gym_data.base_url else current_gym.base_url
            check_strategy = gym_data.verification_strategy if gym_data.verification_strategy else current_gym.verification_strategy
            
            existing_gym = await gym_crud.get_by_base_url_and_strategy(db, check_url, check_strategy)
            # Exclude current gym from duplicate check (allow keeping same URL + strategy)
            if existing_gym and existing_gym.uuid != gym_uuid:
                raise HTTPException(
                    status_code=400,
                    detail=f"A gym with base URL '{check_url}' and verification strategy '{check_strategy.value}' already exists (Gym: '{existing_gym.name}')"
                )
            
            # Normalize base_url before saving if provided
            if gym_data.base_url:
                gym_data_dict = gym_data.model_dump(exclude_unset=True)
                gym_data_dict['base_url'] = normalize_base_url(gym_data.base_url)
                gym_data = GymUpdate(**gym_data_dict)
        
        gym = await gym_crud.update(db, gym_uuid, gym_data)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        return gym
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating gym {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{gym_uuid}")
async def delete_gym(
    gym_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a gym"""
    try:
        success = await gym_crud.delete(db, gym_uuid)
        if not success:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        return {"message": f"Gym {gym_uuid} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting gym {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{gym_uuid}/report")
async def generate_gym_report(
    gym_uuid: UUID,
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a combined Excel report for all executions in a gym.
    
    Args:
        gym_uuid: UUID of the gym
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
    
    Returns:
        Download URL for the generated report and JSON snapshot
    """
    try:
        # Verify gym exists
        gym = await gym_crud.get(db, gym_uuid)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        # Parse date filters if provided
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
                # Set to end of day
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")
        
        # Get executions for this gym with date filters
        executions = await execution_crud.get_by_gym_and_date_range(
            db,
            gym_id=gym_uuid,
            start_date=start_datetime,
            end_date=end_datetime
        )
        
        if not executions:
            raise HTTPException(
                status_code=404,
                detail=f"No executions found for gym {gym.name}" + 
                       (f" between {start_date} and {end_date}" if start_date or end_date else "")
            )
        
        # Get execution directories
        results_dir = Path(settings.RESULTS_DIR)
        execution_dirs = []
        
        for execution in executions:
            exec_dir = results_dir / execution.execution_folder_name
            if exec_dir.exists():
                execution_dirs.append(exec_dir)
            else:
                logger.warning(f"Execution directory not found: {execution.execution_folder_name}")
        
        if not execution_dirs:
            raise HTTPException(
                status_code=404,
                detail=f"No valid execution directories found for gym {gym.name}"
            )
        
        # Create export directory
        export_dir = results_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        date_suffix = f"_{start_date}_to_{end_date}" if start_date or end_date else ""
        filename = f"{gym.name}_report{date_suffix}_{timestamp}.xlsx"
        # Sanitize filename
        filename = filename.replace(" ", "_").replace("/", "-")
        output_path = export_dir / filename
        
        logger.info(f"Generating gym report for {gym.name} with {len(execution_dirs)} executions")
        
        # Generate combined report
        report_path = generate_combined_report(
            execution_dirs=execution_dirs,
            output_path=output_path,
            write_json=True
        )
        
        download_url = f"/api/v1/executions/files/exports/{filename}?t={int(time.time())}"
        
        return {
            "message": f"Report generated for gym {gym.name}",
            "gym_name": gym.name,
            "gym_uuid": str(gym_uuid),
            "executions_count": len(executions),
            "execution_dirs_count": len(execution_dirs),
            "start_date": start_date,
            "end_date": end_date,
            "download_url": download_url,
            "filename": filename,
            "json_snapshot": f"{filename.replace('.xlsx', '.json')}"
        }
    
    except HTTPException:
        raise
    except FileNotFoundError as e:
        logger.error(f"File not found generating gym report: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        logger.error(f"Invalid data for gym report generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating gym report for {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{gym_uuid}/executions-data")
async def get_gym_executions_data(
    gym_uuid: UUID,
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed execution data for a gym in JSON format (without generating Excel).
    
    Args:
        gym_uuid: UUID of the gym
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
    
    Returns:
        JSON with execution data matching the report structure
    """
    try:
        # Verify gym exists
        gym = await gym_crud.get(db, gym_uuid)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
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
        
        # Get executions
        executions = await execution_crud.get_by_gym_and_date_range(
            db,
            gym_id=gym_uuid,
            start_date=start_datetime,
            end_date=end_datetime
        )
        
        if not executions:
            return {
                "gym_name": gym.name,
                "gym_uuid": str(gym_uuid),
                "start_date": start_date,
                "end_date": end_date,
                "executions": [],
                "total_executions": 0,
                "message": "No executions found for the specified filters"
            }
        
        # Collect data from all executions
        results_dir = Path(settings.RESULTS_DIR)
        all_records = []
        
        for execution in executions:
            exec_dir = results_dir / execution.execution_folder_name
            if exec_dir.exists():
                try:
                    records = collect_execution_data(exec_dir)
                    all_records.extend(records)
                except Exception as e:
                    logger.warning(f"Failed to collect data from {execution.execution_folder_name}: {e}")
        
        # Group by task
        tasks_data = {}
        for record in all_records:
            if record.task_id not in tasks_data:
                tasks_data[record.task_id] = {
                    "task_id": record.task_id,
                    "prompt": record.prompt,
                    "iterations": []
                }
            
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
                "end_timestamp": record.end_timestamp,
                "model": record.model
            })
        
        return {
            "gym_name": gym.name,
            "gym_uuid": str(gym_uuid),
            "start_date": start_date,
            "end_date": end_date,
            "executions_count": len(executions),
            "tasks": list(tasks_data.values()),
            "total_tasks": len(tasks_data),
            "total_iterations": len(all_records)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting gym executions data for {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{gym_uuid}/tasks/export", response_model=GymTasksExportResponse)
async def export_gym_tasks(
    gym_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Export all tasks for a gym as downloadable JSON.
    Admin-only endpoint.
    
    Returns:
        JSON with gym_id and list of tasks, each containing task_id, prompt, and verification_script_md
    """
    try:
        # Verify gym exists
        gym = await gym_crud.get(db, gym_uuid)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        # Get all tasks for this gym
        tasks = await task_crud.get_multi_by_gym(db, gym_uuid, skip=0, limit=1000)
        
        # Export each task
        exported_tasks = []
        verifiers_dir = Path(settings.VERIFIERS_DIR).resolve()
        
        for task in tasks:
            # Read verification script if available
            verification_script_md = "```python\n\n```"  # Default empty script
            
            if task.verifier_path:
                verifier_path = Path(task.verifier_path)
                
                # Security check: ensure verifier_path is within VERIFIERS_DIR
                try:
                    resolved_verifier_path = verifier_path.resolve()
                    
                    # Check if file exists and is within verifiers directory
                    if resolved_verifier_path.exists() and resolved_verifier_path.is_file():
                        # Check if it's within the verifiers directory
                        try:
                            resolved_verifier_path.relative_to(verifiers_dir)
                            # File is safe to read
                            with open(resolved_verifier_path, 'r', encoding='utf-8', errors='replace') as f:
                                script_content = f.read().rstrip()
                                verification_script_md = f"```python\n{script_content}\n```"
                        except ValueError:
                            # Path is outside verifiers directory
                            logger.warning(f"Verifier path outside VERIFIERS_DIR for task {task.task_id}: {task.verifier_path}")
                    else:
                        logger.warning(f"Verifier file not found for task {task.task_id}: {task.verifier_path}")
                        
                except Exception as e:
                    logger.warning(f"Error processing verifier path for task {task.task_id}: {e}")
            
            exported_tasks.append(TaskExportResponse(
                task_id=task.task_id,
                prompt=task.prompt,
                verification_script_md=verification_script_md
            ))
        
        logger.info(f"Exported {len(exported_tasks)} tasks for gym {gym.name} by admin {current_admin.email if hasattr(current_admin, 'email') else 'user'}")
        
        return GymTasksExportResponse(
            gym_id=str(gym_uuid),
            tasks=exported_tasks
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting tasks for gym {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
