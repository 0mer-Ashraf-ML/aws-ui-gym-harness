"""
Batch report generation service
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.services.crud.batch import batch_crud
from app.services.crud.execution import execution_crud
from app.services.reports.execution_report import generate_combined_report, IterationRecord, _build_summary, _build_snapshot, _write_workbook, _write_json_snapshot

logger = logging.getLogger(__name__)


def _get_prompt_with_fallback(task_id: str, db_task_prompt: Optional[str] = None, execution_dir_prompt: Optional[str] = None) -> str:
    """Get prompt with fallback priority: DB → Execution dir → Production tasks CSV"""
    
    # Priority 1: Database prompt
    if db_task_prompt and db_task_prompt.strip():
        return db_task_prompt.strip()
    
    # Priority 2: Execution directory prompt
    if execution_dir_prompt and execution_dir_prompt.strip():
        return execution_dir_prompt.strip()
    
    # Priority 3: Production tasks CSV (if available)
    try:
        from app.api.v1.endpoints.reports import _load_production_tasks_csv
        production_tasks = _load_production_tasks_csv()
        csv_prompt = production_tasks.get(task_id, "").strip()
        if csv_prompt:
            return csv_prompt
    except Exception:
        pass
    
    # Fallback: return empty string
    return ""


async def _collect_batch_report_data(
    db: AsyncSession,
    batch_id: UUID
) -> tuple[Dict, List[IterationRecord]]:
    """
    INTERNAL: Collect batch report data from database.
    
    This function is used by both:
    - generate_batch_report() for Excel generation
    - get_batch_report_data() for JSON preview
    
    Returns:
        tuple: (batch_info_dict, all_records_list)
    """
    # Get batch with executions
    batch = await batch_crud.get(db, batch_id)
    if not batch:
        raise ValueError(f"Batch {batch_id} not found")
    
    # Get all executions for this batch
    executions = await execution_crud.get_multi_by_batch(db, batch_id)
    
    if not executions:
        raise ValueError(f"No executions found for batch {batch_id}")
    
    logger.info(f"Collecting data for batch {batch.name} with {len(executions)} executions")
    
    # Collect data from database instead of file system
    all_records = []
    
    for execution in executions:
        # Get iterations for this execution
        # Note: After task decoupling, we get task info from execution's snapshot fields
        query = """
            SELECT i.uuid, i.iteration_number, i.status, i.error_message, i.execution_time_seconds,
                   i.verification_comments, i.last_model_response, i.eval_insights, i.total_steps
            FROM iterations i
            WHERE i.execution_id = :execution_id
            ORDER BY i.iteration_number
        """
        result = await db.execute(text(query), {"execution_id": execution.uuid})
        iterations = result.fetchall()
        
        for iteration in iterations:
            # Determine runner from execution model
            runner_name = execution.model.lower()
            if runner_name == "openai":
                runner_name = "openai"
            elif runner_name == "anthropic":
                runner_name = "anthropic"
            elif runner_name == "gemini":
                runner_name = "gemini"
            else:
                runner_name = "unknown"
            
            # Start with database data as primary source of truth
            # Get task_id from parent execution's snapshot field
            record = IterationRecord(
                task_id=execution.task_identifier,
                iteration=iteration.iteration_number,
                runner=runner_name,
                status=iteration.status,
                status_reason=iteration.error_message,  # Use error_message as status_reason
                completion_reason=None,
                duration_seconds=iteration.execution_time_seconds,  # Database duration is primary
                timelapse=None,
                file_timelapse_seconds=None,
                tool_calls_total=0,
                tool_calls_by_tool={},
                unique_tools=[],
                extra={},
                execution_uuid=str(execution.uuid),
                iteration_uuid=str(iteration.uuid),
                verification_comments=iteration.verification_comments,  # Add verification comments from DB
                last_model_response=iteration.last_model_response,  # Add model response from DB
                eval_insights=iteration.eval_insights,  # Add evaluation insights from DB
                total_steps=iteration.total_steps  # Database field for total steps
            )
            
            # Set prompt using fallback system: DB → Production tasks CSV
            # Use execution's snapshot prompt instead of iteration.prompt
            record.prompt = _get_prompt_with_fallback(
                task_id=execution.task_identifier,
                db_task_prompt=execution.prompt,
                execution_dir_prompt=None
            )
            
            # Try to enhance with file-based data if available (as fallback for additional details)
            if execution.execution_folder_name:
                try:
                    from app.services.reports.execution_report import collect_execution_data
                    results_dir = Path(settings.RESULTS_DIR)
                    exec_dir = results_dir / execution.execution_folder_name
                    if exec_dir.exists():
                        # Find the specific iteration record
                        execution_records = collect_execution_data(exec_dir)
                        for file_record in execution_records:
                            if (file_record.task_id == execution.task_identifier and 
                                file_record.iteration == iteration.iteration_number and
                                file_record.runner == runner_name):
                                
                                # Enhance database record with file-based details (but keep DB as primary)
                                if file_record.completion_reason:
                                    record.completion_reason = file_record.completion_reason
                                if file_record.tool_calls_total > 0:
                                    record.tool_calls_total = file_record.tool_calls_total
                                if file_record.tool_calls_by_tool:
                                    record.tool_calls_by_tool = file_record.tool_calls_by_tool
                                if file_record.unique_tools:
                                    record.unique_tools = file_record.unique_tools
                                if file_record.extra:
                                    record.extra = file_record.extra
                                
                                # Use file-based prompt if database prompt is empty
                                if not record.prompt and file_record.prompt:
                                    record.prompt = file_record.prompt
                                
                                # Set iteration directory for enhanced model response extraction
                                record.iteration_directory = file_record.iteration_directory
                                
                                logger.debug(f"Enhanced database record with file-based details for iteration {iteration.iteration_number}")
                                break
                except Exception as e:
                    logger.warning(f"Failed to load file-based data from execution dir for {execution.execution_folder_name}: {e}")
            
            # Use database field for model response (highest priority)
            if iteration.last_model_response:
                record.completion_reason = iteration.last_model_response
                logger.debug(f"Using database model response for iteration {iteration.iteration_number}: {len(iteration.last_model_response)} chars")
            # Apply enhanced model response extraction if we have iteration directory and no database field
            elif record.iteration_directory:
                try:
                    from app.services.reports.execution_report import _extract_record_model_response
                    enhanced_response = _extract_record_model_response(record)
                    if enhanced_response and enhanced_response != "No response captured.":
                        record.completion_reason = enhanced_response
                        logger.debug(f"Enhanced model response for iteration {iteration.iteration_number}: {len(enhanced_response)} chars")
                except Exception as e:
                    logger.warning(f"Failed to extract enhanced model response for iteration {iteration.iteration_number}: {e}")
            
            # Only include non-crashed tasks (same logic as reports endpoint)
            if record.status and record.status.upper() not in ["CRASHED"]:
                all_records.append(record)
    
    if not all_records:
        raise ValueError(f"No valid iteration records found for batch {batch.name}. All iterations may have crashed or no data is available.")
    
    batch_info = {
        "batch": batch,
        "executions": executions,
    }
    
    return batch_info, all_records


async def generate_batch_report(
    db: AsyncSession,
    batch_id: UUID
) -> Dict:
    """Generate a comprehensive Excel report for a batch using database-based data collection"""
    
    # Collect data using internal function
    batch_info, all_records = await _collect_batch_report_data(db, batch_id)
    batch = batch_info["batch"]
    executions = batch_info["executions"]
    
    # Get batch-level insights
    batch_insights = batch.eval_insights or {}
    
    logger.info(f"Generating batch report for {batch.name} with {len(all_records)} iteration records")
    
    # Create export directory
    results_dir = Path(settings.RESULTS_DIR)
    export_dir = results_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename using batch name
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize batch name for filename
    sanitized_batch_name = batch.name.replace(" ", "_").replace("/", "-").replace("\\", "-")
    filename = f"{sanitized_batch_name}_report_{timestamp}.xlsx"
    output_path = export_dir / filename
    
    try:
        # Build summary and task data
        summary_rows, task_rows = _build_summary(all_records)
        
        # Write Excel workbook
        # Derive the batch's intended iteration count for definitions
        total_iterations = int(batch.number_of_iterations or 0)

        _write_workbook(
            summary_rows=summary_rows,
            iterations=all_records,
            task_rows=task_rows,
            workbook_path=output_path,
            total_iterations=total_iterations if total_iterations > 0 else None,
            batch_insights=batch_insights,
        )
        
        # Write JSON snapshot
        snapshot_path = output_path.with_suffix(".json")
        snapshot = _build_snapshot(summary_rows, all_records, task_rows)
        _write_json_snapshot(snapshot_path, snapshot)
        
        logger.info(f"Successfully generated batch report: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to generate batch report for {batch.name}: {e}")
        # Clean up partial files if they exist
        if output_path.exists():
            output_path.unlink()
        snapshot_path = output_path.with_suffix(".json")
        if snapshot_path.exists():
            snapshot_path.unlink()
        raise ValueError(f"Failed to generate batch report: {str(e)}")
    
    download_url = f"/api/v1/executions/files/exports/{filename}"
    
    return {
        "message": f"Batch report generated successfully for {batch.name}",
        "batch_name": batch.name,
        "batch_uuid": str(batch.uuid),
        "executions_count": len(executions),
        "records_count": len(all_records),
        "download_url": download_url,
        "filepath": str(output_path),
        "filename": filename,
        "json_snapshot": f"{filename.replace('.xlsx', '.json')}"
    }


async def get_batch_report_data(
    db: AsyncSession,
    batch_id: UUID
) -> Dict:
    """Get batch report data for preview (no file generation)"""
    
    # Collect data using internal function
    batch_info, all_records = await _collect_batch_report_data(db, batch_id)
    batch = batch_info["batch"]
    executions = batch_info["executions"]
    
    # Get batch-level insights
    batch_insights = batch.eval_insights or {}
    
    logger.info(f"Fetching report data for batch {batch.name} with {len(all_records)} iteration records")
    
    # Build summary and task data (reuse existing functions)
    summary_rows, task_rows = _build_summary(all_records)
    
    return {
        "batch_name": batch.name,
        "batch_uuid": str(batch.uuid),
        "executions_count": len(executions),
        "batch_insights": batch_insights,
        "summary_rows": summary_rows,
        "task_rows": task_rows,
        "iteration_records": [
            {
                "task_id": r.task_id,
                "iteration": r.iteration,
                "runner": r.runner,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "error_message": r.status_reason,
                "completion_reason": r.completion_reason,
                "tool_calls_total": r.tool_calls_total,
                "execution_uuid": r.execution_uuid,
                "iteration_uuid": r.iteration_uuid,
                "verification_comments": r.verification_comments,
                "eval_insights": r.eval_insights,
                "iteration_url": f"/executions/{r.execution_uuid}/iterations/{r.iteration_uuid}" if r.execution_uuid and r.iteration_uuid else None,
            }
            for r in all_records
        ],
        "total_iterations": len(all_records)
    }
