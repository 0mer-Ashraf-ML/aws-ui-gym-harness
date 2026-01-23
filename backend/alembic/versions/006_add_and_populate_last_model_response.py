"""add and populate last_model_response for iterations

Revision ID: 006
Revises: 005
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
import json
import os
from pathlib import Path


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def _safe_load_json(file_path: Path) -> dict:
    """Safely load JSON file, return empty dict on error - matches execution_report.py"""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _extract_task_completion_response(model_response: str) -> str:
    """Extract the natural response from the model - matches execution_report.py"""
    if not model_response or not isinstance(model_response, str):
        return model_response or ""
    
    # Return the full natural response without any special parsing
    return model_response


def _extract_model_response_from_iteration(iteration_uuid: str, result_data: str, logs: str, error_message: str) -> str:
    """Extract model response using the same strategy as _extract_record_model_response"""
    
    # First try to extract from result_data
    if result_data:
        try:
            result_json = json.loads(result_data)
            if isinstance(result_json, dict):
                # Look for completion_reason first (highest priority)
                completion_reason = result_json.get('completion_reason')
                if completion_reason and completion_reason.strip():
                    return _extract_task_completion_response(completion_reason)
                
                # Look for iteration_directory to extract from conversation files
                iteration_directory = result_json.get('iteration_directory')
                if iteration_directory:
                    extracted_response = _extract_model_response_from_conversation_files(iteration_directory)
                    if extracted_response != "No response captured.":
                        return extracted_response
        except (json.JSONDecodeError, Exception):
            pass
    
    # Try to extract from logs
    if logs:
        try:
            logs_json = json.loads(logs)
            if isinstance(logs_json, dict):
                # Look for any assistant messages in logs
                for key, value in logs_json.items():
                    if isinstance(value, str) and ("assistant" in key.lower() or "response" in key.lower()):
                        if value.strip():
                            return _extract_task_completion_response(value)
        except (json.JSONDecodeError, Exception):
            pass
    
    # Use error_message as fallback
    if error_message:
        return f"Error: {error_message}"
    
    return "No response captured."


def _extract_model_response_from_conversation_files(iteration_directory: str) -> str:
    """Extract model response from conversation files - matches execution_report.py logic"""
    if not iteration_directory:
        return "No response captured."
    
    runner_path = Path(iteration_directory)
    
    # Look in conversation_history for files ending with _task_execution_conversation.json
    conversation_dir = runner_path / "conversation_history"
    if conversation_dir.exists():
        for conv_file in sorted(conversation_dir.glob("*_task_execution_conversation.json")):
            conv_data = _safe_load_json(conv_file) or {}
            # Handle both direct message arrays and conversation_flow format
            messages = conv_data if isinstance(conv_data, list) else conv_data.get("messages", [])
            conversation_flow = conv_data.get("conversation_flow", [])
            
            # Try conversation_flow first (newer format)
            if conversation_flow:
                for item in reversed(conversation_flow):
                    if item.get("role") == "assistant" and item.get("content"):
                        content = item["content"]
                        if content and content.strip():
                            return _extract_task_completion_response(content)  # Full message, no truncation
            
            # Fallback to messages array
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    content = msg["content"]
                    if isinstance(content, str) and content.strip():
                        return _extract_task_completion_response(content)  # Full message, no truncation
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text and text.strip():
                                    return _extract_task_completion_response(text)  # Full message
            break
    
    return "No response captured."


def upgrade():
    """Add last_model_response column and populate it for existing iterations"""
    connection = op.get_bind()
    
    # Step 1: Check if last_model_response column exists, if not add it
    print("Checking if last_model_response column exists...")
    result = connection.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='iterations' AND column_name='last_model_response'
    """))
    
    if result.fetchone() is None:
        print("Adding last_model_response column to iterations table...")
        op.add_column('iterations', sa.Column('last_model_response', sa.Text(), nullable=True))
    else:
        print("Column already exists, skipping add_column...")
    
    # Step 2: Populate existing iterations
    print("Populating last_model_response for existing iterations...")
    
    # Get all iterations that need to be populated with execution folder info
    query = text("""
        SELECT 
            i.uuid,
            i.result_data,
            i.logs,
            i.error_message,
            i.iteration_number,
            e.execution_folder_name,
            e.task_id
        FROM iterations i
        JOIN executions e ON i.execution_id = e.uuid
        ORDER BY i.created_at
    """)
    
    result = connection.execute(query)
    iterations = result.fetchall()
    
    updated_count = 0
    
    for iteration in iterations:
        iteration_uuid = iteration.uuid
        result_data = iteration.result_data
        logs = iteration.logs
        error_message = iteration.error_message
        iteration_number = iteration.iteration_number
        execution_folder_name = iteration.execution_folder_name
        task_id_uuid = iteration.task_id
        
        model_response = "No response captured."
        
        # First try to extract from result_data
        model_response = _extract_model_response_from_iteration(
            str(iteration_uuid), 
            result_data, 
            logs, 
            error_message
        )
        
        # If no response found, try to extract from conversation files on disk
        if model_response == "No response captured." and execution_folder_name:
            # Try to find the task_id from the execution folder name or from the execution's task_id
            task_id_str = None
            
            if task_id_uuid:
                # Get task_id string from tasks table
                task_query = text("""
                    SELECT task_id FROM tasks WHERE uuid = :task_id_uuid
                """)
                task_result = connection.execute(task_query, {"task_id_uuid": task_id_uuid}).fetchone()
                if task_result:
                    task_id_str = task_result[0]
            else:
                # Try to extract task_id from execution folder name
                # Format: batch_NAME_TIMESTAMP_TASK-ID_model
                parts = execution_folder_name.split('_')
                if len(parts) >= 2:
                    # The task_id might be in different positions, try to find it
                    for i, part in enumerate(parts):
                        # Look for patterns like "ZEND-TICKET-SPAM-001" or "CAL-001"
                        if any(x in part for x in ['ZEND', 'CAL', 'TICKET', 'FOCUS']):
                            task_id_str = '_'.join(parts[i:-1])  # Take from this part until model suffix
                            break
            
            if task_id_str:
                # Construct iteration directory path
                results_dir = Path("/app/results")
                iteration_dir = results_dir / execution_folder_name / task_id_str / f"iteration_{iteration_number}"
                
                # Try to extract from conversation files
                if iteration_dir.exists():
                    extracted = _extract_model_response_from_conversation_files(str(iteration_dir))
                    if extracted != "No response captured.":
                        model_response = extracted
        
        # Update the iteration with the extracted model response
        update_query = text("""
            UPDATE iterations 
            SET last_model_response = :model_response
            WHERE uuid = :iteration_uuid
        """)
        
        connection.execute(update_query, {
            'model_response': model_response,
            'iteration_uuid': iteration_uuid
        })
        
        updated_count += 1
        
        if updated_count % 100 == 0:
            print(f"Updated {updated_count} iterations...")
    
    print(f"Migration completed: Added column and updated {updated_count} iterations with last_model_response")


def downgrade():
    """Remove last_model_response column from iterations table"""
    print("Removing last_model_response column from iterations table...")
    op.drop_column('iterations', 'last_model_response')
    print("Migration downgrade completed")
