"""
Reports endpoints (static paths) to avoid conflicts with dynamic execution UUID routes.
"""

from typing import Optional, Dict, List, Any
from uuid import UUID
import logging
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.core.auth import get_current_user
from app.core.config import settings

# Reuse the aggregate data collector from executions endpoints
from app.api.v1.endpoints.executions import (
    _collect_aggregate_data,  # type: ignore
    _format_all_tasks_summary_response,
)
from app.services.reports.execution_report import _write_workbook, _load_iteration_record, _build_summary, _build_snapshot
from app.services.crud import gym_crud, execution_crud, task_crud, iteration_crud
import csv

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache for production tasks CSV to avoid repeated file reads
_production_tasks_cache = None

def _load_production_tasks_csv() -> Dict[str, str]:
    """Load prompts from production_tasks.csv file with caching"""
    global _production_tasks_cache
    
    if _production_tasks_cache is not None:
        return _production_tasks_cache
    
    _production_tasks_cache = {}
    csv_path = Path(__file__).parent.parent.parent.parent / "tasks" / "production_tasks.csv"
    
    try:
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    task_id = row.get('task_id', '').strip()
                    task_description = row.get('task_description', '').strip()
                    if task_id and task_description:
                        _production_tasks_cache[task_id] = task_description
            logger.info(f"Loaded {len(_production_tasks_cache)} prompts from production_tasks.csv")
        else:
            logger.warning(f"Production tasks CSV not found at {csv_path}")
    except Exception as e:
        logger.error(f"Error loading production_tasks.csv: {e}")
    
    return _production_tasks_cache

def _normalize_runner_name(model_name: str) -> str:
    """Normalize runner names from database to match expected format"""
    if not model_name:
        return "unknown"
    
    # Map database model names to expected runner names
    model_mapping = {
        "openai": "openai", 
        "anthropic": "anthropic",
        "gemini": "gemini"
    }
    
    return model_mapping.get(model_name.lower(), model_name.lower())

def _get_prompt_with_fallback(task_id: str, db_task_prompt: Optional[str] = None, execution_dir_prompt: Optional[str] = None) -> str:
    """Get prompt with fallback priority: DB → Execution dir → Production tasks CSV"""
    
    # Priority 1: Database prompt
    if db_task_prompt and db_task_prompt.strip():
        return db_task_prompt.strip()
    
    # Priority 2: Execution directory prompt
    if execution_dir_prompt and execution_dir_prompt.strip():
        return execution_dir_prompt.strip()
    
    # Priority 3: Production tasks CSV
    production_tasks = _load_production_tasks_csv()
    csv_prompt = production_tasks.get(task_id, "").strip()
    if csv_prompt:
        return csv_prompt
    
    # Fallback: return empty string
    logger.warning(f"No prompt found for task_id: {task_id}")
    return ""


async def _collect_aggregate_data_from_db(
    db: AsyncSession,
    gym_id: Optional[UUID],
    start_date: Optional[str],
    end_date: Optional[str],
    max_executions: int,
) -> Optional[Dict[str, object]]:
    """
    Collect aggregate data from database instead of file system.
    This replaces the file-based _collect_aggregate_data function.
    """
    from app.services.reports.execution_report import IterationRecord
    from app.services.reports.execution_report import _aggregate_runner_stats
    from app.services.reports.execution_report import _extract_record_status
    
    # Get gym
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

    # Get executions for this gym with date filters
    executions = await execution_crud.get_by_gym_and_date_range(
        db,
        gym_id=gym_id,
        start_date=start_datetime,
        end_date=end_datetime,
    )

    if not executions:
        return None

    # Limit executions if specified
    if max_executions and len(executions) > max_executions:
        executions = executions[:max_executions]

    logger.info(f"Processing {len(executions)} executions for gym {selected_gym.name}")

    # Collect all iteration records from database
    all_records: List[IterationRecord] = []
    execution_meta: Dict[str, Dict[str, Any]] = {}
    
    for execution in executions:
        # Get iterations for this execution
        db_iterations = await iteration_crud.get_by_execution_id(db, execution.uuid, limit=None)
        
        if not db_iterations:
            continue
            
        # Convert database iterations to IterationRecord format
        execution_records: List[IterationRecord] = []
        
        for db_iter in db_iterations:
            # Get task details from execution snapshot (not task table)
            task_identifier = execution.task_identifier
            task_prompt = execution.prompt
            
            if not task_identifier:
                logger.warning(f"Execution {execution.uuid} missing task_identifier snapshot, skipping")
                continue
                
            # Try to get additional data from execution directory
            execution_dir = Path(settings.RESULTS_DIR) / execution.execution_folder_name
            runner_name = _normalize_runner_name(execution.model)  # Normalize runner name
            
            # Try to get detailed data from execution directory
            detailed_data = None
            if execution_dir.exists():
                try:
                    # Look for the specific iteration directory
                    task_dir = execution_dir / task_identifier
                    if task_dir.exists():
                        iteration_dir = task_dir / f"iteration_{db_iter.iteration_number}"
                        if iteration_dir.exists():
                            # Find the runner directory (should match normalized runner name)
                            for runner_dir in iteration_dir.iterdir():
                                if runner_dir.is_dir() and runner_dir.name.lower() == runner_name.lower():
                                    detailed_data = _load_iteration_record(
                                        task_id=task_identifier,
                                        iteration_index=db_iter.iteration_number,
                                        runner_name=runner_name,  # Use normalized name
                                        runner_path=runner_dir,
                                    )
                                    break
                except Exception as e:
                    logger.warning(f"Failed to load detailed data from execution dir for {execution.execution_folder_name}: {e}")
            
            # Start with database data as primary source of truth
            record = IterationRecord(
                task_id=task_identifier,
                iteration=db_iter.iteration_number,
                runner=runner_name,
                status=db_iter.status,
                status_reason=db_iter.error_message,  # Use error_message as status_reason
                completion_reason=None,
                duration_seconds=db_iter.execution_time_seconds,  # Database duration is primary
                timelapse=None,
                file_timelapse_seconds=None,
                tool_calls_total=0,
                tool_calls_by_tool={},
                unique_tools=[],
                extra={},
                execution_uuid=str(execution.uuid),
                iteration_uuid=str(db_iter.uuid),
                total_steps=db_iter.total_steps  # Database field for total steps
            )
            
            # Set prompt using fallback system: Execution snapshot → Production tasks CSV
            record.prompt = _get_prompt_with_fallback(
                task_id=task_identifier,
                db_task_prompt=task_prompt,
                execution_dir_prompt=None
            )
            
            # Try to enhance with file-based data if available (as fallback for additional details)
            if detailed_data:
                # Enhance database record with file-based details (but keep DB as primary)
                if detailed_data.completion_reason:
                    record.completion_reason = detailed_data.completion_reason
                if detailed_data.tool_calls_total > 0:
                    record.tool_calls_total = detailed_data.tool_calls_total
                if detailed_data.tool_calls_by_tool:
                    record.tool_calls_by_tool = detailed_data.tool_calls_by_tool
                if detailed_data.unique_tools:
                    record.unique_tools = detailed_data.unique_tools
                if detailed_data.extra:
                    record.extra = detailed_data.extra
                
                # Use file-based prompt if database prompt is empty
                if not record.prompt and detailed_data.prompt:
                    record.prompt = detailed_data.prompt
                
                logger.debug(f"Enhanced database record with file-based details for iteration {db_iter.iteration_number}")
            
            # Apply the same status filtering logic as the original function
            allowed_statuses = {"PASSED", "FAILED"}
            
            # Get the current status from the record
            current_status = record.status or ""
            
            # Apply the simplified status classification
            simplified_status = _extract_record_status(record) or ""
            
            # If we couldn't extract a status, try to normalize the current status
            if not simplified_status:
                simplified_status = str(current_status).upper()
            
            # Apply the simplified status rules
            if simplified_status in ["PASSED", "SUCCESS", "SUCCEEDED", "COMPLETED", "COMPLETE", "DONE", "OK", "VERIFIED"]:
                final_status = "PASSED"
            elif simplified_status in ["FAILED", "FAIL", "FAILURE", "VERIFICATION_FAILED", "VERIFICATION-FAILED", "VERIFICATION ERROR", "TIMEOUT", "TIMED_OUT", "TIMED-OUT", "TIMED OUT", "TIME_OUT"]:
                final_status = "FAILED"
            else:
                # For CRASHED, PENDING, EXECUTING, UNKNOWN, etc. - exclude from reports
                continue
                
            # Only include if it's in our allowed statuses
            if final_status not in allowed_statuses:
                continue
                
            record.status = final_status
            execution_records.append(record)
        
        if execution_records:
            all_records.extend(execution_records)
            execution_meta[str(execution.uuid)] = {
                "execution_folder_name": execution.execution_folder_name,
                "model": execution.model,
                "created_at": execution.created_at.isoformat() if execution.created_at else None,
                "record_count": len(execution_records)
            }

    if not all_records:
        return None

    logger.info(f"Collected {len(all_records)} iteration records from database")

    # Use the same data structure building as the original function
    summary_rows, task_rows = _build_summary(all_records)
    snapshot = _build_snapshot(summary_rows, all_records, task_rows)

    # Create filters dict (same as original)
    starts = sorted(record.start_timestamp for record in all_records if record.start_timestamp)
    ends = sorted(record.end_timestamp for record in all_records if record.end_timestamp)
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
        "all_records": all_records,
        "snapshot": snapshot,
        "filters": filters,
        "execution_meta": execution_meta,
    }


@router.get("/all-tasks-summary")
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
    Uses database data instead of file system for improved performance and accuracy.
    """
    try:
        # Use database-based data collection instead of file system
        data = await _collect_aggregate_data_from_db(db, gym_id, start_date, end_date, max_executions)
        if not data:
            return {
                "summary": [],
                "tasks": {},
            }

        formatted = _format_all_tasks_summary_response(
            data,
            include_task_details=include_task_details,
        )

        logger.info(
            "📊 Generated JSON export with %d tasks from database",
            len(formatted["summary"]),
        )

        return formatted

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting all tasks summary (reports): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all-tasks-summary/report")
async def download_all_tasks_summary_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    gym_id: UUID = Query(None, description="Filter by gym UUID"),
    start_date: str = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(None, description="End date in YYYY-MM-DD format"),
    max_executions: int = Query(10000, description="Maximum number of executions to include"),
    include_snapshot: bool = Query(True, description="Also generate JSON snapshot alongside Excel"),
):
    """Generate a filtered aggregate Excel report matching the all-tasks-summary data using database."""
    try:
        # Use database-based data collection instead of file system
        data = await _collect_aggregate_data_from_db(db, gym_id, start_date, end_date, max_executions)
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

        # (Optional) JSON snapshot step omitted; serve Excel via downloads endpoint
        download_url = f"/api/v1/executions/files/exports/{filename}?t={int(time.time())}"

        return {
            "message": f"Aggregate report generated for gym {gym_name} (database-based)",
            "download_url": download_url,
            "filename": filename,
            "filters": filters,
            "total_tasks": len(data["summary_rows"]),
            "total_iterations": len(data["all_records"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating aggregate report (reports): {e}")
        raise HTTPException(status_code=500, detail=str(e))

