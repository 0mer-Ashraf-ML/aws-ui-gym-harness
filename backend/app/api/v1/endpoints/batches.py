"""
Batch management endpoints
"""

import asyncio
import json
import logging
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.core.auth import (
    get_current_user,
    get_current_user_from_token,
    get_current_user_optional,
    get_current_admin_user,
)
from app.core.database import get_db
from app.models.user import User
from app.schemas.batch import (
    BatchCreate,
    BatchListResponse,
    BatchResponse,
    BatchRerunResponse,
    BatchUpdate,
    BatchIterationSummaryResponse,
    BatchMetadata,
    BatchFailureDiagnosticsResponse,
    FailedIterationDetail,
    FailureCategoryGroup,
    FailureCategory,
)
from app.schemas.execution import ExecutionResponse
from app.services.crud.batch import batch_crud
from app.services.crud.gym import gym_crud
from app.services.crud.execution import execution_crud
from app.services.crud.iteration import iteration_crud
from app.services.batch_execution import batch_execution_service
from app.services.reports.batch_report import generate_batch_report, get_batch_report_data
from app.services.batch_status_manager import BatchStatusManager
from app.services.batch_iteration_summary import batch_iteration_summary_service
from app.services.batch_recovery_service import BatchRecoveryService
from app.celery_app import celery_app
from app.schemas.iteration import IterationStatus
from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
from app.services.batch_report_readiness import batch_report_readiness_service
from app.services.archive_service import archive_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def create_batch_response(batch, db: AsyncSession, current_user: Optional[User] = None, username: Optional[str] = None) -> BatchResponse:
    """Create a BatchResponse with computed status from executions"""
    # Compute status from executions
    computed_status = await BatchStatusManager.update_batch_status_from_executions(
        batch.uuid
    )

    # Determine username to display
    # If current_user matches batch creator, show "You"
    if current_user and batch.created_by and batch.created_by == current_user.uuid:
        batch_username = "You"
    elif username is not None:
        # Explicitly provided username (for new batches)
        batch_username = username
    elif batch.creator:
        # Load creator email from database
        batch_username = batch.creator.email
    else:
        # No creator info available
        batch_username = None

    # Create response object with computed status
    batch_dict = {
        "uuid": batch.uuid,
        "name": batch.name,
        "gym_id": batch.gym_id,
        "number_of_iterations": batch.number_of_iterations,
        "status": computed_status,
        "eval_insights": batch.eval_insights,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "rerun_enabled": getattr(batch, "rerun_enabled", True),
        "created_by": batch.created_by,
        "username": batch_username,
    }

    return BatchResponse(**batch_dict)


@router.post("/", response_model=BatchResponse)
@router.post("", response_model=BatchResponse)
async def create_batch(
    batch_data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new batch and automatically execute it"""
    # Verify gym exists and user has access
    gym = await gym_crud.get(db, batch_data.gym_id)
    if not gym:
        raise HTTPException(status_code=404, detail="Gym not found")

    # Create the batch with created_by set to current user
    batch = await batch_crud.create(db, batch_data, created_by=current_user.uuid)
    logger.info(f"Created batch {batch.uuid} for gym {batch.gym_id} by user {current_user.email}")

    # Automatically execute the batch
    try:
        executions = await batch_execution_service.execute_batch(
            db, batch.uuid, batch_data.selected_models, batch_data.selected_task_ids
        )
        logger.info(
            f"Automatically started batch execution for batch {batch.uuid} with {len(executions)} executions using models: {[m.value for m in batch_data.selected_models]}"
        )
    except Exception as e:
        logger.error(f"Failed to automatically execute batch {batch.uuid}: {e}")
        # Don't fail the batch creation if execution fails - batch is still created
        # The user can manually execute it later if needed

    # Pass current_user and username for immediate response (creator relationship may not be loaded yet)
    return await create_batch_response(batch, db, current_user=current_user, username=current_user.email)


@router.get("/", response_model=BatchListResponse)
@router.get("", response_model=BatchListResponse)
async def get_batches(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=50, description="Page size (10, 20, or 50)"),
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get batches with pagination and computed status"""
    # Validate size is one of allowed values
    if size not in [10, 20, 50]:
        size = 10
    
    # Convert page to skip
    skip = (page - 1) * size
    
    if gym_id:
        batches = await batch_crud.get_multi_by_gym(db, gym_id, skip=skip, limit=size)
        total = await batch_crud.count_by_gym(db, gym_id)
    else:
        batches = await batch_crud.get_multi(db, skip=skip, limit=size)
        total = await batch_crud.count(db)

    # Convert to responses with computed status (only for current page)
    batch_responses = []
    for batch in batches:
        batch_response = await create_batch_response(batch, db, current_user=current_user)
        batch_responses.append(batch_response)

    return BatchListResponse(
        batches=batch_responses, total=total, skip=skip, limit=size
    )


@router.get("/metadata", response_model=List[BatchMetadata])
async def get_batch_metadata(
    gym_id: Optional[UUID] = Query(None, description="Filter by gym ID"),
    limit: int = Query(1000, ge=1, le=5000, description="Max batches to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get lightweight batch metadata for dropdowns/selection (no status calculation)"""
    from app.models.batch import Batch
    
    query = select(Batch.uuid, Batch.name, Batch.created_at, Batch.gym_id)
    if gym_id:
        query = query.where(Batch.gym_id == gym_id)
    query = query.order_by(Batch.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        BatchMetadata(
            uuid=row.uuid,
            name=row.name,
            created_at=row.created_at,
            gym_id=row.gym_id
        )
        for row in rows
    ]


@router.get("/ready-reports")
async def get_batches_with_ready_reports(
    unread_only: bool = Query(False, description="If true, only return unread notifications"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all batches that have reports ready to be generated.
    
    This endpoint is used for notifications to show users which batches have completed
    and are ready for report generation. Shows all notifications with per-user read status.
    The count of unread notifications is calculated separately.
    """
    try:
        ready_batches = await batch_report_readiness_service.get_all_ready_batches(
            db, 
            user_id=current_user.uuid,
            unread_only=unread_only
        )
        
        # Calculate unread count for badge
        unread_count = sum(1 for batch in ready_batches if not batch.get("is_read", False))
        
        return {
            "ready_batches": ready_batches,
            "count": len(ready_batches),
            "unread_count": unread_count
        }
    except Exception as e:
        logger.error(f"Failed to get batches with ready reports: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ready reports")


@router.post("/{batch_id}/mark-notification-read")
async def mark_notification_read(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark a batch notification as read for the current user.
    
    This adds the current user's ID to the batch's notification_read_by array.
    Uses raw SQL UPDATE to avoid triggering the updated_at timestamp.
    """
    try:
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Get current read_by list
        read_by_users = batch.notification_read_by or []
        user_id_str = str(current_user.uuid)
        
        # Add user if not already in the list
        if user_id_str not in read_by_users:
            read_by_users.append(user_id_str)
            
            # Use raw SQL UPDATE to avoid triggering updated_at timestamp
            # We need to convert the Python list to a JSON string for PostgreSQL
            notification_json = json.dumps(read_by_users)
            
            await db.execute(
                text(
                    "UPDATE batches SET notification_read_by = :notification_read_by "
                    "WHERE uuid = :batch_id"
                ),
                {"notification_read_by": notification_json, "batch_id": str(batch_id)}
            )
            await db.commit()
            logger.info(f"User {current_user.email} marked batch {batch_id} notification as read")
        
        return {
            "message": "Notification marked as read",
            "batch_id": str(batch_id)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark notification as read for batch {batch_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to mark notification as read")


@router.get("/{batch_id}", response_model=BatchResponse)
async def get_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific batch by ID with computed status"""
    batch = await batch_crud.get(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return await create_batch_response(batch, db, current_user=current_user)


@router.put("/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: UUID,
    batch_update: BatchUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a batch"""
    batch = await batch_crud.get(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    updated_batch = await batch_crud.update(db, batch, batch_update)
    logger.info(f"Updated batch {batch_id}")
    return await create_batch_response(updated_batch, db, current_user=current_user)


@router.post("/{batch_id}/execute")
async def execute_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a batch by creating and running executions for all tasks in the gym with both models"""
    # Verify batch exists
    batch = await batch_crud.get(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    try:
        executions = await batch_execution_service.execute_batch(db, batch_id)
        logger.info(
            f"Started batch execution for batch {batch_id} with {len(executions)} executions"
        )
        return {
            "message": f"Batch execution started with {len(executions)} executions",
            "batch_id": str(batch_id),
            "executions_count": len(executions),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to execute batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute batch")


@router.get("/{batch_id}/executions", response_model=List[ExecutionResponse])
async def get_batch_executions(
    batch_id: UUID,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get executions for a specific batch"""
    # Verify batch exists
    batch = await batch_crud.get(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    executions = await execution_crud.get_multi_by_batch(
        db, batch_id, skip=skip, limit=limit
    )

    # Convert to ExecutionResponse to avoid circular references
    from app.api.v1.endpoints.executions import (
        create_execution_response,
        calculate_execution_durations_bulk
    )

    # Bulk calculate durations for all executions in one query
    execution_ids = [exec.uuid for exec in executions]
    durations_cache = await calculate_execution_durations_bulk(execution_ids, db)

    execution_responses = []
    for execution in executions:
        execution_response = await create_execution_response(
            execution, 
            db, 
            durations_cache=durations_cache
        )
        execution_responses.append(execution_response)

    return execution_responses


@router.get("/{batch_id}/status-summary")
async def get_batch_status_summary(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed status summary for a batch"""
    try:
        from app.services.batch_status_manager import BatchStatusManager

        summary = await BatchStatusManager.get_batch_status_summary(batch_id)
        return summary
    except Exception as e:
        logger.error(f"Failed to get batch {batch_id} status summary: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get batch status summary"
        )


@router.get("/{batch_id}/report-readiness")
async def check_batch_report_readiness(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check if a batch report is ready to be generated.
    
    Returns readiness status and any blocking items (pending, executing, crashed, or failed without directory).
    """
    try:
        readiness = await batch_report_readiness_service.is_report_ready(db, batch_id)
        return readiness
    except Exception as e:
        logger.error(f"Failed to check report readiness for batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to check report readiness")


@router.get("/{batch_id}/report")
async def generate_batch_report_endpoint(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a comprehensive report for a batch"""
    try:
        # Check batch report readiness using the new service
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # Use the new report readiness service for comprehensive checking
        readiness = await batch_report_readiness_service.is_report_ready(db, batch_id)
        
        if not readiness["ready"]:
            raise HTTPException(
                status_code=400,
                detail=readiness["reason"],
            )

        # Use async-optimized processing for all batches
        executions = await execution_crud.get_multi_by_batch(db, batch_id)
        execution_count = len(executions)

        logger.info(
            f"Using standard processing for batch with {execution_count} executions"
        )
        try:
            report = await asyncio.wait_for(
                generate_batch_report(db, batch_id), timeout=300.0  # 5 minute timeout
            )
            return report
        except asyncio.TimeoutError:
            logger.error(
                f"Batch report generation timed out after 5 minutes for batch {batch_id}"
            )
            raise HTTPException(
                status_code=408,
                detail="Batch report generation timed out. Please try again or contact support.",
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate batch report for {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate batch report")


@router.get("/{batch_id}/report-data")
async def get_batch_report_data_endpoint(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get batch report data for preview (no file generation)"""
    try:
        # Check batch report readiness using the new service
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # Use the new report readiness service for comprehensive checking
        readiness = await batch_report_readiness_service.is_report_ready(db, batch_id)
        
        if not readiness["ready"]:
            raise HTTPException(
                status_code=400,
                detail=readiness["reason"],
            )

        # Fetch report data
        try:
            report_data = await asyncio.wait_for(
                get_batch_report_data(db, batch_id), timeout=300.0  # 5 minute timeout
            )
            return report_data
        except asyncio.TimeoutError:
            logger.error(
                f"Batch report data fetch timed out after 5 minutes for batch {batch_id}"
            )
            raise HTTPException(
                status_code=408,
                detail="Report data retrieval timed out. Please try again or contact support.",
            )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get batch report data for {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get report data")


@router.post("/{batch_id}/terminate")
async def terminate_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Immediately terminate all pending/executing iterations in a batch and clean up resources"""
    
    logger.info(f"=== TERMINATE OPERATION STARTED for batch_id: {batch_id} ===")
    
    # Verify batch exists
    try:
        logger.info(f"DEBUG: Fetching batch {batch_id}")
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            logger.error(f"ERROR: Batch {batch_id} not found")
            raise HTTPException(status_code=404, detail="Batch not found")
        logger.info(f"DEBUG: Batch {batch_id} found: {batch.name}")
    except Exception as e:
        logger.error(f"ERROR: Error fetching batch {batch_id}: {e}")
        raise

    # Get all executions for the batch
    try:
        logger.info(f"DEBUG: Fetching executions for batch {batch_id}")
        executions = await execution_crud.get_multi_by_batch(db, batch_id)
        logger.info(f"DEBUG: Found {len(executions)} executions for batch {batch_id}")
    except Exception as e:
        logger.error(f"ERROR: Error fetching executions for batch {batch_id}: {e}")
        raise
    if not executions:
        return {"message": "No executions found for this batch", "terminated": 0}

    terminated = 0
    executed_terminated = 0
    pending_terminated = 0
    inspected = 0
    errors: List[str] = []
    
    # Get actual executing and pending counts from database BEFORE termination
    actual_executing_count = 0
    actual_pending_count = 0
    try:
        for execution in executions:
            iterations = await iteration_crud.get_by_execution_id(db, execution.uuid)
            for iteration in iterations:
                if iteration.status == IterationStatus.EXECUTING:
                    actual_executing_count += 1
                elif iteration.status == IterationStatus.PENDING:
                    actual_pending_count += 1
        logger.info(f"DEBUG: Actual counts from DB - Executing: {actual_executing_count}, Pending: {actual_pending_count}")
    except Exception as e:
        logger.error(f"ERROR: Failed to get counts from DB: {e}")
        actual_executing_count = 0
        actual_pending_count = 0

    # Initialize Redis client for targeted queue cleanup
    redis_client = None
    try:
        import redis
        import json
        from app.core.config import settings as app_settings
        redis_url = app_settings.REDIS_URL
        redis_client = redis.Redis.from_url(redis_url) if redis_url else None
        logger.info(f"DEBUG: Redis client initialized: {redis_client is not None}")
    except Exception as e:
        logger.error(f"ERROR: Failed to initialize Redis client: {e}")
        redis_client = None

    # Step 2: NUCLEAR TERMINATION - HARSH cleanup of ALL queues and tasks
    logger.info(f"?? NUCLEAR TERMINATION for batch {batch_id} - HARSH cleanup starting...")
    
    if redis_client:
        try:
            # Get all iteration IDs for this batch
            batch_iteration_ids = set()
            batch_task_ids = set()
            for execution in executions:
                try:
                    iterations = await iteration_crud.get_by_execution_id(db, execution.uuid)
                    for iteration in iterations:
                        batch_iteration_ids.add(str(iteration.uuid))
                        if iteration.celery_task_id:
                            batch_task_ids.add(iteration.celery_task_id)
                except Exception as e:
                    logger.warning(f"WARNING: Error collecting iteration IDs for execution {execution.uuid}: {e}")
            
            logger.info(f"DEBUG: Collected {len(batch_iteration_ids)} iteration IDs and {len(batch_task_ids)} task IDs for batch")
            
            # 1. NUCLEAR: Kill ALL active tasks for this batch
            logger.info("?? NUCLEAR: Killing ALL active tasks for this batch...")
            try:
                # Get ALL currently active tasks from Celery workers
                active_tasks = celery_app.control.inspect().active()
                if active_tasks:
                    all_active_task_ids = []
                    batch_active_task_ids = []
                    
                    for worker, tasks in active_tasks.items():
                        if tasks:
                            for task in tasks:
                                task_id = task.get('id')
                                if task_id:
                                    all_active_task_ids.append(task_id)
                                    
                                    # Check if this task belongs to our batch by checking kwargs
                                    kwargs = task.get('kwargs', {})
                                    iteration_id = kwargs.get('iteration_id')
                                    
                                    if iteration_id and iteration_id in batch_iteration_ids:
                                        batch_active_task_ids.append(task_id)
                                        logger.info(f"?? NUCLEAR: Found active task {task_id} for iteration {iteration_id}")
                    
                    # Kill only batch-specific active tasks
                    if batch_active_task_ids:
                        celery_app.control.revoke(batch_active_task_ids, terminate=True, signal="SIGKILL")
                        logger.info(f"?? NUCLEAR: Killed {len(batch_active_task_ids)} batch-specific active tasks with SIGKILL")
                    else:
                        logger.info("?? NUCLEAR: No batch-specific active tasks found to kill")
                else:
                    logger.info("?? NUCLEAR: No active tasks found")
                    
            except Exception as e:
                logger.error(f"ERROR: ?? NUCLEAR: Failed to kill active tasks: {e}")
                errors.append(f"Nuclear active task kill error: {str(e)}")
            
            # 1.5. REMOVED: Do NOT kill tasks by name as it would affect ALL batches
            # We only kill tasks that specifically belong to THIS batch via iteration_id check (step 1)
            logger.info("?? Skipping broad task name killing to preserve other batches")
            
            # 2. NUCLEAR: Clear ALL unacked tasks for this batch
            logger.info("?? NUCLEAR: Clearing ALL unacked tasks for this batch...")
            unacked_tasks = redis_client.hgetall('unacked')
            logger.info(f"DEBUG: Found {len(unacked_tasks)} unacked tasks to check")
            
            cleared_unacked = 0
            for task_id, task_data in unacked_tasks.items():
                try:
                    # Decode the task data to get iteration_id
                    import base64
                    import json
                    task_data_str = task_data.decode('utf-8')
                    task_json = json.loads(task_data_str)
                    
                    # Extract iteration_id from the task data
                    if len(task_json) >= 2 and isinstance(task_json[1], dict):
                        task_kwargs = task_json[1]
                        iteration_id = task_kwargs.get('iteration_id')
                        
                        if iteration_id and iteration_id in batch_iteration_ids:
                            # Remove this task from unacked
                            redis_client.hdel('unacked', task_id)
                            cleared_unacked += 1
                            logger.info(f"?? NUCLEAR: Cleared unacked task {task_id} for iteration {iteration_id}")
                            
                except Exception as e:
                    logger.warning(f"WARNING: Error processing unacked task {task_id}: {e}")
            
            # Only clear batch-specific unacked tasks (not ALL unacked tasks)
            logger.info(f"?? NUCLEAR: Cleared {cleared_unacked} batch-specific unacked tasks")
            
            # 2.5. NUCLEAR: Scan and clear ALL Redis queues for batch tasks
            logger.info("?? NUCLEAR: Scanning ALL Redis queues for batch tasks...")
            try:
                # Get all Redis keys
                all_keys = redis_client.keys("*")
                logger.info(f"?? NUCLEAR: Found {len(all_keys)} total Redis keys to scan")
                
                batch_tasks_found = 0
                batch_tasks_cleared = 0
                
                # Scan all keys for batch-related content
                for key in all_keys:
                    try:
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                        
                        # Check if it's a queue (list)
                        if redis_client.type(key) == b'list':
                            queue_length = redis_client.llen(key)
                            if queue_length > 0:
                                logger.info(f"?? NUCLEAR: Scanning queue '{key_str}' with {queue_length} tasks")
                                
                                # Get all tasks from the queue
                                tasks = redis_client.lrange(key, 0, -1)
                                tasks_to_remove = []
                                
                                for i, task_data in enumerate(tasks):
                                    try:
                                        task_str = task_data.decode('utf-8')
                                        
                                        # Check if this task belongs to our batch
                                        for iteration_id in batch_iteration_ids:
                                            if iteration_id in task_str:
                                                tasks_to_remove.append(i)
                                                batch_tasks_found += 1
                                                logger.info(f"?? NUCLEAR: Found batch task in queue '{key_str}': iteration {iteration_id}")
                                                break
                                    except Exception as e:
                                        logger.warning(f"WARNING: Error parsing task in queue '{key_str}': {e}")
                                
                                # Remove batch tasks from queue
                                for i in reversed(tasks_to_remove):
                                    redis_client.lrem(key, 1, tasks[i])
                                    batch_tasks_cleared += 1
                                
                                if tasks_to_remove:
                                    logger.info(f"?? NUCLEAR: Removed {len(tasks_to_remove)} batch tasks from queue '{key_str}'")
                        
                        # Check if it's a hash (like unacked)
                        elif redis_client.type(key) == b'hash':
                            hash_length = redis_client.hlen(key)
                            if hash_length > 0:
                                logger.info(f"?? NUCLEAR: Scanning hash '{key_str}' with {hash_length} entries")
                                
                                hash_data = redis_client.hgetall(key)
                                keys_to_remove = []
                                
                                for hash_key, hash_value in hash_data.items():
                                    try:
                                        hash_key_str = hash_key.decode('utf-8') if isinstance(hash_key, bytes) else str(hash_key)
                                        hash_value_str = hash_value.decode('utf-8') if isinstance(hash_value, bytes) else str(hash_value)
                                        
                                        # Check if this hash entry belongs to our batch
                                        for iteration_id in batch_iteration_ids:
                                            if iteration_id in hash_value_str:
                                                keys_to_remove.append(hash_key)
                                                batch_tasks_found += 1
                                                logger.info(f"?? NUCLEAR: Found batch task in hash '{key_str}': iteration {iteration_id}")
                                                break
                                    except Exception as e:
                                        logger.warning(f"WARNING: Error parsing hash entry in '{key_str}': {e}")
                                
                                # Remove batch tasks from hash
                                if keys_to_remove:
                                    redis_client.hdel(key, *keys_to_remove)
                                    batch_tasks_cleared += len(keys_to_remove)
                                    logger.info(f"?? NUCLEAR: Removed {len(keys_to_remove)} batch tasks from hash '{key_str}'")
                        
                        # Check if it's a string (like metadata)
                        elif redis_client.type(key) == b'string':
                            try:
                                value = redis_client.get(key)
                                if value:
                                    value_str = value.decode('utf-8')
                                    
                                    # Check if this metadata belongs to our batch
                                    for iteration_id in batch_iteration_ids:
                                        if iteration_id in value_str:
                                            redis_client.delete(key)
                                            batch_tasks_found += 1
                                            batch_tasks_cleared += 1
                                            logger.info(f"?? NUCLEAR: Deleted batch metadata '{key_str}': iteration {iteration_id}")
                                            break
                            except Exception as e:
                                logger.warning(f"WARNING: Error parsing string key '{key_str}': {e}")
                                
                    except Exception as e:
                        logger.warning(f"WARNING: Error processing Redis key '{key_str}': {e}")
                
                logger.info(f"?? NUCLEAR: Found {batch_tasks_found} batch tasks across all Redis keys")
                logger.info(f"?? NUCLEAR: Cleared {batch_tasks_cleared} batch tasks from Redis")
                
            except Exception as e:
                logger.error(f"ERROR: ?? NUCLEAR: Failed to scan Redis queues: {e}")
                errors.append(f"Nuclear Redis queue scan error: {str(e)}")
            
            # 2.7. REMOVED: Do NOT disable automatic dispatch as it would affect ALL batches
            # The monitoring task already checks iteration status and won't re-dispatch terminated tasks
            logger.info("?? Skipping automatic dispatch disabling to preserve other batches")
            
            # NOTE: We don't mark pending iterations as crashed here anymore
            # The main iteration loop (Step 3) will handle both executing AND pending iterations
            # Marking them as crashed here causes them to be skipped in Step 3, which means
            # their Celery tasks never get revoked, leading to re-dispatch after termination
            
            # 3. NUCLEAR: Clear ALL reserved tasks for this batch (pending queue)
            logger.info("?? NUCLEAR: Clearing ALL reserved tasks for this batch...")
            try:
                # Get reserved tasks from Celery
                reserved_tasks = celery_app.control.inspect().reserved()
                if reserved_tasks:
                    total_reserved_cleared = 0
                    for worker, tasks in reserved_tasks.items():
                        if tasks:
                            batch_reserved_tasks = []
                            for task in tasks:
                                try:
                                    # Check if this task belongs to our batch
                                    kwargs = task.get('kwargs', {})
                                    iteration_id = kwargs.get('iteration_id')
                                    
                                    if iteration_id and iteration_id in batch_iteration_ids:
                                        task_id = task.get('id')
                                        if task_id:
                                            batch_reserved_tasks.append(task_id)
                                            logger.info(f"?? NUCLEAR: Found reserved task {task_id} for iteration {iteration_id}")
                                except Exception as e:
                                    logger.warning(f"WARNING: Error processing reserved task: {e}")
                            
                            # Revoke reserved tasks for this batch
                            if batch_reserved_tasks:
                                celery_app.control.revoke(batch_reserved_tasks, terminate=True, signal="SIGKILL")
                                total_reserved_cleared += len(batch_reserved_tasks)
                                logger.info(f"?? NUCLEAR: Revoked {len(batch_reserved_tasks)} reserved tasks from worker {worker}")
                    
                    logger.info(f"?? NUCLEAR: Total reserved tasks cleared: {total_reserved_cleared}")
                else:
                    logger.info("?? NUCLEAR: No reserved tasks found")
                
            except Exception as e:
                logger.error(f"ERROR: ?? NUCLEAR: Failed to clear reserved tasks: {e}")
                errors.append(f"Nuclear reserved tasks cleanup error: {str(e)}")
            
            # 4. NUCLEAR: Clear ALL scheduled tasks for this batch
            logger.info("?? NUCLEAR: Clearing ALL scheduled tasks for this batch...")
            try:
                scheduled_tasks = celery_app.control.inspect().scheduled()
                if scheduled_tasks:
                    total_scheduled_cleared = 0
                    for worker, tasks in scheduled_tasks.items():
                        if tasks:
                            batch_scheduled_tasks = []
                            for task in tasks:
                                try:
                                    # Check if this task belongs to our batch
                                    kwargs = task.get('kwargs', {})
                                    iteration_id = kwargs.get('iteration_id')
                                    
                                    if iteration_id and iteration_id in batch_iteration_ids:
                                        task_id = task.get('id')
                                        if task_id:
                                            batch_scheduled_tasks.append(task_id)
                                            logger.info(f"?? NUCLEAR: Found scheduled task {task_id} for iteration {iteration_id}")
                                except Exception as e:
                                    logger.warning(f"WARNING: Error processing scheduled task: {e}")
                            
                            # Revoke scheduled tasks for this batch
                            if batch_scheduled_tasks:
                                celery_app.control.revoke(batch_scheduled_tasks, terminate=True, signal="SIGKILL")
                                total_scheduled_cleared += len(batch_scheduled_tasks)
                                logger.info(f"?? NUCLEAR: Revoked {len(batch_scheduled_tasks)} scheduled tasks from worker {worker}")
                    
                    logger.info(f"?? NUCLEAR: Total scheduled tasks cleared: {total_scheduled_cleared}")
                else:
                    logger.info("?? NUCLEAR: No scheduled tasks found")
                
            except Exception as e:
                logger.error(f"ERROR: ?? NUCLEAR: Failed to clear scheduled tasks: {e}")
                errors.append(f"Nuclear scheduled tasks cleanup error: {str(e)}")
            
            # 5. NUCLEAR: Clear ALL Redis keys related to this batch
            logger.info("?? NUCLEAR: Clearing ALL Redis keys for this batch...")
            try:
                # Clear celery-task-meta-* keys for batch tasks
                meta_keys_cleared = 0
                for task_id in batch_task_ids:
                    meta_key = f"celery-task-meta-{task_id}"
                    if redis_client.exists(meta_key):
                        redis_client.delete(meta_key)
                        meta_keys_cleared += 1
                        logger.info(f"?? NUCLEAR: Cleared metadata key {meta_key}")
                
                # Clear any other keys containing batch_id
                batch_keys = redis_client.keys(f"*{batch_id}*")
                if batch_keys:
                    redis_client.delete(*batch_keys)
                    logger.info(f"?? NUCLEAR: Cleared {len(batch_keys)} batch-specific keys")
                
                logger.info(f"?? NUCLEAR: Cleared {meta_keys_cleared} metadata keys")
                
            except Exception as e:
                logger.error(f"ERROR: ?? NUCLEAR: Failed to clear Redis keys: {e}")
                errors.append(f"Nuclear Redis keys cleanup error: {str(e)}")
            
            logger.info(f"?? NUCLEAR TERMINATION COMPLETE: {cleared_unacked} unacked tasks cleared, ALL queues checked and cleared")
            
        except Exception as e:
            logger.error(f"ERROR: ?? NUCLEAR TERMINATION FAILED: {e}")
            errors.append(f"Nuclear termination error: {str(e)}")
    
    # Step 3: NUCLEAR Redis cleanup - destroy batch-specific data

    for execution in executions:
        logger.info(f"DEBUG: Processing execution {execution.uuid}")
        try:
            iterations = await iteration_crud.get_by_execution_id(db, execution.uuid)
            logger.info(f"DEBUG: Found {len(iterations)} iterations for execution {execution.uuid}")
        except Exception as e:
            logger.error(f"ERROR: Error fetching iterations for execution {execution.uuid}: {e}")
            errors.append(f"Error fetching iterations for execution {execution.uuid}: {str(e)}")
            continue
        for iteration in iterations:
            inspected += 1
            # Terminate ALL iterations regardless of status to prevent re-dispatch
            status_value = str(iteration.status).lower() if iteration.status else ""
            logger.info(f"DEBUG: Iteration {iteration.uuid} status: '{iteration.status}' -> '{status_value}'")
            
            # Skip only if already in final states (passed, failed, crashed, timeout)
            if status_value in [
                IterationStatus.PASSED.value.lower(),
                IterationStatus.FAILED.value.lower(),
                IterationStatus.CRASHED.value.lower(),
                IterationStatus.TIMEOUT.value.lower(),
            ]:
                logger.info(f"DEBUG: Skipping iteration {iteration.uuid} with final status '{status_value}'")
                continue

            # Thoroughly terminate executing and pending iterations
            logger.info(f"DEBUG: Processing iteration {iteration.uuid} with celery_task_id: {iteration.celery_task_id}")
            
            # Safety check: Ensure this iteration belongs to the batch being terminated
            if iteration.execution_id not in [exec.uuid for exec in executions]:
                logger.warning(f"WARNING: Iteration {iteration.uuid} does not belong to batch {batch_id}, skipping")
                continue
            
            # Step 1: Revoke Celery task if it exists
            if iteration.celery_task_id:
                try:
                    if status_value == IterationStatus.EXECUTING.value.lower():
                        logger.info(f"DEBUG: Revoking EXECUTING Celery task {iteration.celery_task_id} with SIGKILL")
                        celery_app.control.revoke(
                            iteration.celery_task_id, terminate=True, signal="SIGKILL"
                        )
                    else:  # PENDING
                        logger.info(f"DEBUG: Revoking PENDING Celery task {iteration.celery_task_id}")
                        celery_app.control.revoke(
                            iteration.celery_task_id, terminate=False
                        )
                except Exception as e:
                    logger.warning(f"WARNING: Failed to revoke Celery task {iteration.celery_task_id}: {e}")
            
            # Step 2: Aggressive Redis queue cleanup for this specific task
            if redis_client and iteration.celery_task_id:
                try:
                    logger.info(f"DEBUG: Cleaning Redis queue for task {iteration.celery_task_id}")
                    task_id_bytes = iteration.celery_task_id.encode("utf-8")
                    
                    # Check all possible queue keys
                    queue_keys = ['celery', 'celery.priority.high', 'celery.priority.normal', 'celery.priority.low']
                    for queue_key in queue_keys:
                        try:
                            # Get all messages in the queue
                            messages = redis_client.lrange(queue_key, 0, -1)
                            removed_count = 0
                            
                            for i, msg in enumerate(messages):
                                try:
                                    # Parse message as JSON to find exact task ID match
                                    import json
                                    try:
                                        msg_data = json.loads(msg.decode('utf-8'))
                                        if isinstance(msg_data, dict) and msg_data.get('id') == iteration.celery_task_id:
                                            # Remove this specific message
                                            redis_client.lrem(queue_key, 1, msg)
                                            removed_count += 1
                                            logger.info(f"DEBUG: Removed task {iteration.celery_task_id} from queue {queue_key}")
                                    except (json.JSONDecodeError, UnicodeDecodeError):
                                        # If not JSON, check if task ID is in the raw message (less precise)
                                        if task_id_bytes in msg:
                                            redis_client.lrem(queue_key, 1, msg)
                                            removed_count += 1
                                            logger.info(f"DEBUG: Removed task {iteration.celery_task_id} from queue {queue_key} (raw match)")
                                except Exception as e:
                                    logger.warning(f"WARNING: Error processing message in queue {queue_key}: {e}")
                            
                            if removed_count > 0:
                                logger.info(f"DEBUG: Removed {removed_count} messages for task {iteration.celery_task_id} from queue {queue_key}")
                                
                        except Exception as e:
                            logger.warning(f"WARNING: Error cleaning queue {queue_key}: {e}")
                            
                except Exception as e:
                    logger.warning(f"WARNING: Failed Redis cleanup for task {iteration.celery_task_id}: {e}")
            
            # Step 3: Mark iteration as crashed
            logger.info(f"DEBUG: Marking iteration {iteration.uuid} as crashed")

            # Mark iteration as crashed with termination message
            try:
                await iteration_crud.update_status(
                    db,
                    iteration.uuid,
                    IterationStatus.CRASHED,
                    completed_at=datetime.utcnow(),
                    error_message=(
                        "Terminated by user (executing; killed)"
                        if status_value == IterationStatus.EXECUTING.value.lower()
                        else "Terminated by user (pending; revoked)"
                    ),
                )
                # CRITICAL: Commit the status change immediately to ensure it persists
                await db.commit()
                terminated += 1
                if status_value == IterationStatus.EXECUTING.value.lower():
                    executed_terminated += 1
                else:  # PENDING
                    pending_terminated += 1
                logger.info(f"DEBUG: Successfully marked iteration {iteration.uuid} as crashed")
            except Exception as e:
                logger.error(f"ERROR: Failed updating iteration {iteration.uuid} status: {e}")
                await db.rollback()  # Rollback on error
                errors.append(str(e))

            # Attempt to cleanup iteration directory if possible
            try:
                # Get task identifier from parent execution's snapshot field
                task_identifier = execution.task_identifier if hasattr(execution, 'task_identifier') else None
                iteration_number = iteration.iteration_number
                execution_folder_name = getattr(execution, "execution_folder_name", None)
                if task_identifier and iteration_number and execution_folder_name:
                    UnifiedTaskRunner.cleanup_iteration_directory(
                        execution_folder_name, task_identifier, iteration_number
                    )
            except Exception as e:
                logger.warning(f"WARNING: Cleanup of iteration directory failed for iteration {iteration.uuid}: {e}")

    # Best-effort: force cleanup all active containers related to computer use
    try:
        # Lazy import to avoid initializing Docker client during module import
        from app.services.container_cleanup_service import container_cleanup_service  # type: ignore
        await container_cleanup_service.force_cleanup_all()
    except Exception as e:
        logger.warning(f"WARNING: Force cleanup of containers encountered an issue: {e}")

    # Recompute batch status
    try:
        await BatchStatusManager.update_batch_status_from_executions(batch_id)
    except Exception:
        pass

    # Disable manual rerun for this batch (user intentionally terminated it)
    try:
        batch.rerun_enabled = False
        db.add(batch)
        await db.commit()
        logger.info(f"Disabled rerun for batch {batch_id} after termination")
    except Exception as e:
        logger.error(f"Failed to disable rerun for batch {batch_id}: {e}")
        await db.rollback()
        # Continue anyway - termination was successful

    # Final completion message
    logger.info(f"=== TERMINATE OPERATION COMPLETED ===")
    logger.info(f"Terminated: {terminated} iterations total")
    logger.info(f"  - Executing: {executed_terminated} iterations")
    logger.info(f"  - Pending: {pending_terminated} iterations")
    logger.info(f"Inspected: {inspected} iterations")
    logger.info(f"Errors: {len(errors)} errors")
    
    # Create detailed message using actual counts from database
    if actual_executing_count > 0 and actual_pending_count > 0:
        message = f"Batch terminated successfully. {actual_executing_count} executing and {actual_pending_count} pending iterations terminated."
    elif actual_executing_count > 0:
        message = f"Batch terminated successfully. {actual_executing_count} executing iterations terminated."
    elif actual_pending_count > 0:
        message = f"Batch terminated successfully. {actual_pending_count} pending iterations terminated."
    else:
        message = f"Batch terminated successfully. No active iterations found to terminate."
    
    response = {
        "message": message,
        "terminated": terminated,
        "executed_terminated": actual_executing_count,
        "pending_terminated": actual_pending_count,
        "inspected": inspected,
        "errors": errors,
    }
    return response

@router.get("/worker-status")
async def get_celery_worker_status(current_user: User = Depends(get_current_user)):
    """Get current Celery worker status and availability"""
    try:
        worker_status = await check_celery_worker_availability()
        return {
            "status": "success",
            "worker_status": worker_status,
            "recommendation": (
                "Use direct processing"
                if not worker_status["available"]
                else "Workers available for processing"
            ),
        }
    except Exception as e:
        logger.error(f"Failed to get Celery worker status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get worker status")


@router.get(
    "/{batch_id}/iteration-summary", response_model=BatchIterationSummaryResponse
)
async def get_batch_iteration_summary(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive iteration summary for a batch.

    Returns:
    - Overall iteration counts across all executions in the batch
    - Per-execution iteration breakdown with task and model information

    This endpoint aggregates iteration-level statistics to provide insights into
    batch execution progress and results.
    """
    try:
        # Verify batch exists
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # Generate iteration summary
        summary = await batch_iteration_summary_service.get_batch_iteration_summary(
            batch_id
        )

        logger.info(f"Generated iteration summary for batch {batch_id}")
        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get iteration summary for batch {batch_id}: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get batch iteration summary"
        )


@router.get(
    "/{batch_id}/failure-diagnostics", 
    response_model=BatchFailureDiagnosticsResponse
)
async def get_batch_failure_diagnostics(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed failure diagnostics for all failed iterations in a batch.
    
    Analyzes failed iterations and categorizes them by failure type:
    - MODEL_BLOCKED: Model explicitly stated it couldn't complete the task
    - VERIFICATION_FAILED: Model attempted but verification checks failed
    - TIMEOUT: Task exceeded time limits
    - CRASHED: System/infrastructure failure
    - UNKNOWN: Cannot determine specific reason
    
    Returns failures grouped by category with detailed information for each iteration.
    """
    try:
        from app.services.failure_diagnostics import FailureDiagnostics
        from sqlalchemy import select
        from app.models.iteration import Iteration
        from app.models.execution import Execution
        
        # Verify batch exists
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        logger.info(f"Fetching failure diagnostics for batch {batch_id}")
        
        # Query all FAILED iterations for this batch with execution info
        query = (
            select(Iteration, Execution)
            .join(Execution, Iteration.execution_id == Execution.uuid)
            .where(Execution.batch_id == batch_id)
            .where(Iteration.status == "failed")
            .order_by(Execution.created_at, Iteration.iteration_number)
        )
        
        result = await db.execute(query)
        failed_iterations = result.all()
        
        logger.info(f"Found {len(failed_iterations)} failed iterations in batch {batch_id}")
        
        if not failed_iterations:
            return BatchFailureDiagnosticsResponse(
                batch_id=str(batch_id),
                batch_name=batch.name,
                total_failed=0,
                by_category={}
            )
        
        # Categorize each failed iteration
        categorized_failures = []
        
        for iteration, execution in failed_iterations:
            # Analyze failure
            diagnosis = FailureDiagnostics.categorize_failure(iteration)
            
            # Build iteration detail
            iteration_detail = FailedIterationDetail(
                iteration_number=iteration.iteration_number,
                iteration_id=str(iteration.uuid),
                execution_id=str(execution.uuid),
                task_id=execution.task_identifier or "Unknown",
                model=execution.model or "Unknown",
                category=diagnosis["category"],
                reason_text=diagnosis["reason_text"],
                completion_reason=diagnosis.get("completion_reason"),
                execution_time_seconds=iteration.execution_time_seconds,
                iteration_url=f"/batches/{batch_id}/runs/{execution.uuid}"
            )
            
            categorized_failures.append(iteration_detail)
        
        # Group by category
        by_category = {}
        category_labels = {
            FailureCategory.MODEL_BLOCKED: "Model Blocked",
            FailureCategory.VERIFICATION_FAILED: "Verification Failed",
            FailureCategory.VERIFICATION_ERROR: "Verification Script Error",
            FailureCategory.TIMEOUT: "Timeout",
            FailureCategory.CRASHED: "Crashed",
            FailureCategory.UNKNOWN: "Unknown",
        }
        
        for failure in categorized_failures:
            category = failure.category
            if category not in by_category:
                by_category[category] = FailureCategoryGroup(
                    count=0,
                    category_label=category_labels.get(category, category),
                    iterations=[]
                )
            
            by_category[category].count += 1
            by_category[category].iterations.append(failure)
        
        logger.info(f"Categorized {len(categorized_failures)} failures into {len(by_category)} categories")
        
        return BatchFailureDiagnosticsResponse(
            batch_id=str(batch_id),
            batch_name=batch.name,
            total_failed=len(categorized_failures),
            by_category=by_category
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get failure diagnostics for batch {batch_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get failure diagnostics: {str(e)}"
        )


@router.delete("/")
@router.delete("")
async def delete_all_batches(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """Delete all batches (admin only)"""
    try:
        # First check if any batch is currently executing
        batches = await batch_crud.get_multi(db, skip=0, limit=10000)
        
        executing_batches = []
        for batch in batches:
            computed_status = await BatchStatusManager.update_batch_status_from_executions(batch.uuid)
            if computed_status.lower() == "executing":
                executing_batches.append(batch.name)
        
        if executing_batches:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete batches while {len(executing_batches)} batch(es) are executing: {', '.join(executing_batches[:3])}{'...' if len(executing_batches) > 3 else ''}"
            )
        
        # Delete all batches
        deleted_count = 0
        failed_deletions = []
        
        for batch in batches:
            try:
                await batch_crud.delete(db, batch.uuid)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete batch {batch.uuid} ({batch.name}): {e}")
                failed_deletions.append(batch.name)
        
        logger.info(f"Deleted {deleted_count} batches by admin {current_admin.email}")
        
        return {
            "message": f"Successfully deleted {deleted_count} batch(es)",
            "deleted_count": deleted_count,
            "failed_count": len(failed_deletions),
            "failed_batches": failed_deletions[:5]  # Return first 5 failures
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete all batches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete batches: {str(e)}")


@router.delete("/{batch_id}")
async def delete_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """Delete a batch"""
    try:
        batch = await batch_crud.delete(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        logger.info(f"Deleted batch {batch_id} by {current_admin.email if hasattr(current_admin, 'email') else 'user'}")
        return {"message": "Batch deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete batch {batch_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete batch: {str(e)}")


@router.get("/{batch_id}/download")
async def download_batch(
    batch_id: UUID,
    token: Optional[str] = Query(None, description="Authentication token for file access"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Download all files for all executions in a batch as a ZIP archive"""
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

        # Get batch record
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

        # Generate ZIP filename (sanitize batch name)
        sanitized_batch_name = batch.name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        zip_filename = f"batch_{sanitized_batch_name}.zip"

        # Get all executions for this batch
        executions = await execution_crud.get_multi_by_batch(db, batch_id)
        if not executions:
            raise HTTPException(status_code=404, detail=f"No executions found for batch: {batch_id}")

        # Stream the ZIP archive
        try:
            zip_stream = archive_service.stream_batch_zip_from_executions(executions)
            return StreamingResponse(
                zip_stream,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{zip_filename}"'
                }
            )
        except ValueError as e:
            logger.error(f"Error generating batch ZIP: {e}")
            raise HTTPException(status_code=404, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{batch_id}/rerun-failed-iterations", response_model=BatchRerunResponse)
async def rerun_failed_iterations(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rerun all crashed and timeout iterations in a batch

    This endpoint will:
    1. Find all crashed and timeout iterations in the batch
    2. Clean up their file directories
    3. Reset their database records to pending
    4. Queue them for re-execution
    """
    try:
        # Verify batch exists
        batch = await batch_crud.get(db, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # Check if rerun is disabled (user terminated the batch)
        # If disabled but user explicitly calls rerun, re-enable it (Option A from plan)
        if not getattr(batch, "rerun_enabled", True):
            # User explicitly clicked "Run again" - re-enable rerun and proceed
            batch.rerun_enabled = True
            db.add(batch)
            await db.commit()
            await db.refresh(batch)
            logger.info(f"Re-enabled rerun for batch {batch_id} (user explicitly requested rerun)")

        logger.info(f"?? Starting rerun of failed iterations for batch {batch_id}")

        # Get all failed iterations (crashed and timeout) from the batch
        from sqlalchemy import text

        # Query to get all crashed and timeout iterations in the batch
        # Note: After task decoupling, we get task info from execution's snapshot fields
        query = """
            SELECT 
                i.uuid as iteration_id,
                e.task_identifier as task_string_id,
                e.prompt as task_prompt,
                i.iteration_number,
                i.status,
                e.execution_folder_name,
                e.gym_id,
                e.model as runner_type
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            WHERE e.batch_id = :batch_id 
            AND i.status IN ('crashed', 'failed')
            ORDER BY i.iteration_number ASC
        """

        result = await db.execute(text(query), {"batch_id": str(batch_id)})
        iterations_to_check = result.fetchall()

        total_iterations_to_check = len(iterations_to_check)
        logger.info(f"?? Found {total_iterations_to_check} crashed/failed iterations to check")

        if total_iterations_to_check == 0:
            return BatchRerunResponse(
                message="No crashed or failed iterations found to rerun",
                batch_id=str(batch_id),
                total_failed_iterations=0,
                rerun_iterations=0,
                skipped_iterations=0,
                failed_cleanups=0,
                failed_resets=0,
                failed_queues=0,
            )

        # Import required modules for the rerun process
        from pathlib import Path
        from app.services.task_runners.unified_task_runner import UnifiedTaskRunner
        from app.tasks.unified_execution import unified_integration
        from app.core.config import settings

        # Initialize counters
        rerun_iterations = 0
        skipped_iterations = 0
        failed_cleanups = 0
        failed_resets = 0
        failed_queues = 0

        # Process each crashed/failed iteration
        iteration_ids_to_dispatch = []
        for iteration in iterations_to_check:
            iteration_id = str(iteration.iteration_id)
            task_string_id = str(
                iteration.task_string_id
            )  # String ID from execution snapshot (used for cleanup)
            iteration_number = iteration.iteration_number
            status = iteration.status
            execution_folder_name = iteration.execution_folder_name

            logger.info(f"?? Processing iteration {iteration_id} (status: {status})")

            # Check if iteration directory exists
            base_results_dir = Path(settings.RESULTS_DIR)
            execution_dir = base_results_dir / execution_folder_name
            task_dir = execution_dir / task_string_id
            iteration_dir = task_dir / f"iteration_{iteration_number}"
            
            iteration_dir_exists = iteration_dir.exists() and iteration_dir.is_dir()
            
            # Determine if we should rerun this iteration
            should_rerun = False
            
            if status == 'crashed':
                # Always rerun crashed tasks
                should_rerun = True
                logger.info(f"✅ Crashed task - will rerun")
            elif status == 'failed':
                # Only rerun failed tasks if execution directory doesn't exist (false failure)
                if not iteration_dir_exists:
                    should_rerun = True
                    logger.warning(f"⚠️  Failed task without execution directory - false failure detected, will rerun")
                else:
                    logger.info(f"ℹ️  Failed task with execution directory exists - preserving for debugging, skipping rerun")
                    skipped_iterations += 1
            
            if not should_rerun:
                continue

            # Step 1: Clean up iteration directory (if it exists)
            if iteration_dir_exists:
                logger.info(f"?? Cleaning up files for iteration {iteration_id}")
                cleanup_success = UnifiedTaskRunner.cleanup_iteration_directory(
                    execution_folder_name, task_string_id, iteration_number
                )

                if not cleanup_success:
                    logger.error(f"? Failed to cleanup files for iteration {iteration_id}")
                    failed_cleanups += 1
                    # Continue with other operations even if cleanup fails
            else:
                logger.info(f"ℹ️  No iteration directory to clean up for {iteration_id}")

            # Step 2: Reset iteration database record
            logger.info(f"?? Resetting database record for iteration {iteration_id}")
            reset_success = unified_integration.reset_iteration_for_rerun(iteration_id)

            if not reset_success:
                logger.error(
                    f"? Failed to reset database record for iteration {iteration_id}"
                )
                failed_resets += 1
                continue  # Skip queuing if database reset failed

            # Defensive check: ensure no duplicates (though SQL query should prevent this)
            if iteration_id not in iteration_ids_to_dispatch:
                rerun_iterations += 1
                iteration_ids_to_dispatch.append(iteration_id)
                logger.info(
                    f"? Iteration {iteration_id} reset for rerun and queued for dispatch task"
                )
            else:
                logger.warning(
                    f"?? Iteration {iteration_id} already in dispatch list, skipping duplicate"
                )

        # Don't dispatch directly - let the monitoring task handle dispatch
        # This ensures consistent ordering and prevents race conditions
        if iteration_ids_to_dispatch:
            logger.info(
                f"✅ Reset {len(iteration_ids_to_dispatch)} iteration(s) to pending. "
                f"They will be dispatched by the monitoring task."
            )
            # No failed_queues since we're not dispatching directly

        # Prepare response
        success_message = f"Successfully reset {rerun_iterations} iteration(s) to pending. They will be dispatched by the monitoring task."
        if skipped_iterations > 0:
            success_message += f" ({skipped_iterations} failed tasks with directories preserved)"
        if failed_cleanups > 0 or failed_resets > 0:
            success_message += f" (with {failed_cleanups + failed_resets} partial failures)"

        logger.info(
            f"✅ Batch rerun completed: {rerun_iterations} reset to pending, {failed_cleanups + failed_resets} failures"
        )

        return BatchRerunResponse(
            message=success_message,
            batch_id=str(batch_id),
            total_failed_iterations=total_iterations_to_check,
            rerun_iterations=rerun_iterations,
            skipped_iterations=skipped_iterations,
            failed_cleanups=failed_cleanups,
            failed_resets=failed_resets,
            failed_queues=0,  # No longer dispatching directly, so no queue failures
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"? Failed to rerun failed iterations for batch {batch_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to rerun failed iterations: {str(e)}"
        )


@router.post("/auto-recovery")
async def auto_recover_batches(
    days_back: int = Query(default=2, ge=1, le=7, description="Number of days to look back for batches"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Automatically recover crashed and stuck batches
    
    This endpoint will:
    1. Find all batches created within the specified time window (default: 2 days)
    2. Identify batches that are:
       - **Crashed**: No pending/executing tasks, only failed/crashed/passed tasks
       - **Stuck**: Has executing tasks but the latest iteration started >2 hours ago
    3. Automatically recover them:
       - Crashed batches ? Rerun failed iterations
       - Stuck batches ? Terminate + Rerun failed iterations
    
    **Use Cases:**
    - Run as a scheduled job (e.g., every hour via cron)
    - Manual trigger when you suspect batches are stuck
    - Part of system health monitoring
    
    **Parameters:**
    - `days_back`: How many days back to check (1-7, default: 2)
    
    **Returns:**
    - Summary of recovered batches with detailed results
    """
    try:
        logger.info(f"?? Auto-recovery endpoint triggered by user {current_user.email}")
        
        # Service is now synchronous, use thread executor to run it
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from app.core.database_utils import get_db_session
        
        def run_recovery():
            with get_db_session() as sync_db:
                return BatchRecoveryService.auto_recover_batches(sync_db, days_back)
        
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, run_recovery)
        
        return {
            "success": True,
            "summary": result
        }
    
    except Exception as e:
        logger.error(f"? Auto-recovery failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Auto-recovery failed: {str(e)}"
        )
