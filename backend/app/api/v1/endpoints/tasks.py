"""
Task management endpoints
"""

import logging
from typing import Optional
from uuid import UUID, uuid4
import os
from pathlib import Path
import shutil

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_current_admin_user
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskExportResponse,
    TaskListResponse,
    TaskResponse,
    TaskSyncResponse,
    TaskUpdate,
    TaskVerifierUploadResponse,
)
from app.services.crud.gym import gym_crud
from app.services.crud.task import task_crud

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/", response_model=TaskResponse)
@router.post("", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new task"""
    try:
        # Verify gym exists
        gym = await gym_crud.get(db, task_data.gym_id)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {task_data.gym_id} not found")
        
        # Check if task_id already exists in this gym
        existing_task = await task_crud.get_by_task_id_and_gym(
            db, task_data.task_id, task_data.gym_id
        )
        if existing_task:
            raise HTTPException(
                status_code=400, 
                detail=f"Task with ID '{task_data.task_id}' already exists in gym '{gym.name}'"
            )
        
        task = await task_crud.create(db, task_data)
        if task_data.verifier_path:
            logger.info(
                f"Verifier file: {task_data.verifier_path} {'Exists' if os.path.isfile(task_data.verifier_path) else 'DOES NoT Exist'}"
            )
        return task
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=TaskListResponse)
@router.get("", response_model=TaskListResponse)
async def get_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    gym_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all tasks with pagination and optional gym filtering"""
    try:
        if gym_id:
            # Verify gym exists
            gym = await gym_crud.get(db, gym_id)
            if not gym:
                raise HTTPException(status_code=404, detail=f"Gym {gym_id} not found")
            
            tasks = await task_crud.get_multi_by_gym(db, gym_id, skip=skip, limit=limit)
            total = await task_crud.count_by_gym(db, gym_id)
        else:
            tasks = await task_crud.get_multi(db, skip=skip, limit=limit)
            total = await task_crud.count(db)
        
        return TaskListResponse(
            tasks=tasks,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{task_uuid}", response_model=TaskResponse)
async def get_task(
    task_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific task by UUID"""
    try:
        task = await task_crud.get(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_uuid} not found")
        
        return task
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task {task_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{task_uuid}", response_model=TaskResponse)
async def update_task(
    task_uuid: UUID,
    task_data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a task"""
    try:
        # Get current task to check gym_id
        current_task = await task_crud.get(db, task_uuid)
        if not current_task:
            raise HTTPException(status_code=404, detail=f"Task {task_uuid} not found")
        
        # Check if task_id is being updated and if it conflicts
        if task_data.task_id:
            existing_task = await task_crud.get_by_task_id_and_gym(
                db, task_data.task_id, current_task.gym_id
            )
            if existing_task and existing_task.uuid != task_uuid:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Task with ID '{task_data.task_id}' already exists in this gym"
                )
        
        task = await task_crud.update(db, task_uuid, task_data)
        return task
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task {task_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{task_uuid}")
async def delete_task(
    task_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Delete a task.
    
    Note: Task will be re-added during the next sync if it exists in the gym's API.
    """
    try:
        # Get task details before deleting
        task = await task_crud.get(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_uuid} not found")
        
        # Delete the task
        success = await task_crud.delete(db, task_uuid)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete task {task_uuid}")
        
        await db.commit()
        
        logger.info(f"Task {task.task_id} deleted by {current_admin.email if hasattr(current_admin, 'email') else 'user'}")
        return {"message": f"Task {task.task_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync/{gym_uuid}", response_model=TaskSyncResponse)
async def sync_tasks_from_gym(
    gym_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Sync tasks from a gym's API endpoint"""
    try:
        # Get gym details
        gym = await gym_crud.get(db, gym_uuid)
        if not gym:
            raise HTTPException(status_code=404, detail=f"Gym {gym_uuid} not found")
        
        # Call gym's API to get expected state FIRST
        trimmed_base_url = gym.base_url.rstrip('/')
        endpoint = f"{trimmed_base_url}/api/v1/get_expected_state"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint)
            response.raise_for_status()
            payload = response.json()
        
        verifiers = payload.get('verifiers', {})
        
        # Get existing tasks for this gym
        existing_tasks = await task_crud.get_multi_by_gym(db, gym_uuid, skip=0, limit=1000)
        existing_task_map = {task.task_id: task for task in existing_tasks}
        
        # Get task IDs from API
        api_task_ids = set(verifiers.keys())
        
        new_tasks_count = 0
        updated_tasks_count = 0
        
        # Process each task from the API
        for task_id, details in verifiers.items():
            existing_task = existing_task_map.get(task_id)
            api_prompt = details.get('prompt', '') if isinstance(details, dict) else ''
            api_grader_config = details.get('grader_config') if isinstance(details, dict) else None
            api_simulator_config = details.get('simulator_config') if isinstance(details, dict) else None
            
            if not existing_task:
                # Task doesn't exist in DB, create it
                task_data = TaskCreate(
                    task_id=task_id,
                    gym_id=gym_uuid,
                    prompt=api_prompt,
                    grader_config=api_grader_config,
                    simulator_config=api_simulator_config
                )
                
                await task_crud.create(db, task_data)
                new_tasks_count += 1
                logger.info(f"Created new task {task_id} with grader_config={api_grader_config is not None}, simulator_config={api_simulator_config is not None}")
            else:
                # Task exists, check if anything changed
                needs_update = False
                
                if existing_task.prompt != api_prompt:
                    logger.info(f"Updating prompt for task {task_id}")
                    existing_task.prompt = api_prompt
                    needs_update = True
                
                if existing_task.grader_config != api_grader_config:
                    logger.info(f"Updating grader_config for task {task_id}")
                    existing_task.grader_config = api_grader_config
                    needs_update = True
                
                if existing_task.simulator_config != api_simulator_config:
                    logger.info(f"Updating simulator_config for task {task_id}")
                    existing_task.simulator_config = api_simulator_config
                    needs_update = True
                
                if needs_update:
                    db.add(existing_task)
                    await db.commit()
                    updated_tasks_count += 1
        
        # Delete tasks that are no longer in the API
        deleted_tasks_count = 0
        tasks_to_delete = [task for task in existing_tasks if task.task_id not in api_task_ids]
        
        for task in tasks_to_delete:
            # Delete the task
            await task_crud.delete(db, task.uuid)
            deleted_tasks_count += 1
            logger.info(f"Deleted task {task.task_id} (no longer in API for gym {gym.name})")
        
        # Get updated task count
        total_tasks_count = await task_crud.count_by_gym(db, gym_uuid)
        
        # Build message
        message_parts = []
        if new_tasks_count > 0:
            message_parts.append(f"Added {new_tasks_count} new task{'s' if new_tasks_count != 1 else ''}")
        if updated_tasks_count > 0:
            message_parts.append(f"Updated {updated_tasks_count} task{'s' if updated_tasks_count != 1 else ''}")
        if deleted_tasks_count > 0:
            message_parts.append(f"Removed {deleted_tasks_count} outdated task{'s' if deleted_tasks_count != 1 else ''}")
        
        if message_parts:
            message = f"Synced {gym.name}: {', '.join(message_parts)}"
        else:
            message = f"No changes - {gym.name} tasks are up to date"
        
        return TaskSyncResponse(
            message=message,
            new_tasks_count=new_tasks_count,
            total_tasks_count=total_tasks_count
        )
        
    except httpx.HTTPError as e:
        logger.error(f"HTTP error syncing tasks from gym {gym_uuid}: {e}")
        raise HTTPException(
            status_code=502, 
            detail=f"Failed to connect to gym API: {str(e)}"
        )
    except httpx.TimeoutException:
        logger.error(f"Timeout syncing tasks from gym {gym_uuid}")
        raise HTTPException(
            status_code=504, 
            detail="Gym API request timed out"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing tasks from gym {gym_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_uuid}/export", response_model=TaskExportResponse)
async def export_task(
    task_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export a task as downloadable JSON with task_id, prompt, and verification_script_md.
    Available to all authenticated users.
    """
    try:
        # Get task from database
        task = await task_crud.get(db, task_uuid)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_uuid} not found")
        
        # Read verification script if available
        verification_script_md = "```python\n\n```"  # Default empty script
        
        if task.verifier_path:
            verifier_path = Path(task.verifier_path)
            verifiers_dir = Path(settings.VERIFIERS_DIR).resolve()
            
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
                            logger.info(f"Successfully read verifier script for task {task.task_id}")
                    except ValueError:
                        # Path is outside verifiers directory
                        logger.warning(f"Verifier path outside VERIFIERS_DIR for task {task.task_id}: {task.verifier_path}")
                else:
                    logger.warning(f"Verifier file not found for task {task.task_id}: {task.verifier_path}")
                    
            except Exception as e:
                logger.warning(f"Error processing verifier path for task {task.task_id}: {e}")
        
        return TaskExportResponse(
            task_id=task.task_id,
            prompt=task.prompt,
            verification_script_md=verification_script_md
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting task {task_uuid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verifier", response_model=TaskVerifierUploadResponse)
async def create_verifier_file(file: UploadFile = File(...)):

    # Ensure verfiers directoriy exist
    # Path(settings.APP_TMP_DIR).resolve().mkdir(parents=True, exist_ok=True)
    Path(settings.VERIFIERS_DIR).resolve().mkdir(parents=True, exist_ok=True)
    # logger.info(f"Path {settings.VERIFIERS_DIR} created")

    # Create a unique file name
    file_created = False

    while not file_created:
        unique_id = str(uuid4())
        unique_file_name = unique_id + "__-__" + file.filename
        unique_verifier_file_path = os.path.join(
            settings.VERIFIERS_DIR, unique_file_name
        )
        if os.path.isfile(unique_verifier_file_path):
            # Not a unique file name, continue to try again
            continue
        else:
            try:
                # Open the destination file in write-binary mode
                with open(unique_verifier_file_path, "wb") as buffer:
                    # Copy the uploaded file's content to the destination
                    shutil.copyfileobj(file.file, buffer)
            except Exception as e:
                return {
                    "message": f"There was an error uploading the verifier script file: {e}"
                }
            finally:
                # Close the uploaded file stream
                file.file.close()
                file_created = True

    logger.info(
        f"Returning response file_id = {unique_id}, file_location = {unique_file_name}"
    )
    return TaskVerifierUploadResponse(
        file_id=unique_id, file_location=unique_verifier_file_path
    )
