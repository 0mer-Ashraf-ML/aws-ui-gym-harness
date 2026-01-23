#!/usr/bin/env python3
"""
One-time script to update iteration total_steps from conversation history files.

This script:
1. Reads all iteration records from the database
2. For each iteration, locates its conversation history file in the results directory
3. Extracts the step count (computer_call + tool_use) from the conversation history
4. Updates the iteration's total_steps field in the database

Run this script ONCE to backfill step counts for existing iterations.

USAGE (from host machine):
    docker exec -it rl-gym-harness-ui-fastapi-app-1 python /app/scripts/update_iteration_steps.py
"""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.database_utils import get_db_session
from app.models.iteration import Iteration
from app.models.execution import Execution

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_step_count_from_conversation_history(conversation_file_path: Path) -> Optional[int]:
    """
    Extract step count from conversation history JSON file.
    
    Counts:
    - computer_call (for Gemini and OpenAI)
    - tool_use (for Anthropic)
    
    Returns None if file doesn't exist or can't be parsed.
    """
    if not conversation_file_path.exists():
        return None
    
    try:
        with open(conversation_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        item_types = data.get('item_types', {})
        
        # Count computer_call (Gemini, OpenAI) and tool_use (Anthropic)
        computer_calls = item_types.get('computer_call', 0)
        tool_use = item_types.get('tool_use', 0)
        
        # Return the sum (only one will be non-zero for a given model)
        total_steps = computer_calls + tool_use
        
        return total_steps if total_steps > 0 else None
    
    except Exception as e:
        logger.warning(f"Failed to parse {conversation_file_path}: {e}")
        return None


def build_iteration_directory_path(execution_folder_name: str, task_identifier: str, iteration_number: int) -> Optional[Path]:
    """
    Build the iteration directory path from execution and iteration data.
    
    Expected structure (from DirectoryManager):
    - results/{execution_folder_name}/{task_identifier}/iteration_{iteration_number}/
    
    Note: No model subdirectory - conversation_history is directly under iteration folder
    """
    if not execution_folder_name or not task_identifier:
        return None
    
    results_dir = Path(settings.RESULTS_DIR)
    iteration_path = results_dir / execution_folder_name / task_identifier / f"iteration_{iteration_number}"
    
    return iteration_path if iteration_path.exists() else None


def find_conversation_history_file(iteration_path: Path) -> Optional[Path]:
    """
    Find the conversation history JSON file in the iteration directory.
    
    Looks for files matching pattern: *_task_execution_conversation.json
    in the conversation_history subdirectory.
    """
    if not iteration_path or not iteration_path.exists():
        return None
    
    # Check conversation_history subdirectory
    conversation_dir = iteration_path / "conversation_history"
    if conversation_dir.exists():
        # Find any file ending with _task_execution_conversation.json
        for file_path in conversation_dir.glob("*_task_execution_conversation.json"):
            return file_path
    
    return None


def update_iteration_steps():
    """Main function to update all iteration step counts."""
    
    # Use the existing database connection utility (same as FastAPI app)
    with get_db_session() as db:
        # Get all iterations with their executions (eager loading for efficiency)
        iterations = db.query(Iteration).join(Execution).all()
        logger.info(f"Found {len(iterations)} iterations in database")
        
        updated_count = 0
        skipped_no_execution = 0
        skipped_no_directory = 0
        skipped_no_file = 0
        skipped_already_has_steps = 0
        failed_count = 0
        
        for iteration in iterations:
            # Skip if already has total_steps
            if iteration.total_steps is not None:
                skipped_already_has_steps += 1
                continue
            
            # Get execution data
            execution = iteration.execution
            if not execution or not execution.execution_folder_name or not execution.task_identifier:
                skipped_no_execution += 1
                logger.debug(f"Iteration {iteration.uuid} has no valid execution data")
                continue
            
            # Build iteration directory path
            iteration_path = build_iteration_directory_path(
                execution.execution_folder_name,
                execution.task_identifier,
                iteration.iteration_number
            )
            
            if not iteration_path:
                skipped_no_directory += 1
                logger.debug(f"Directory not found for iteration {iteration.uuid}")
                continue
            
            # Find conversation history file
            conversation_file = find_conversation_history_file(iteration_path)
            
            if not conversation_file:
                skipped_no_file += 1
                logger.debug(f"No conversation history found for iteration {iteration.uuid}")
                continue
            
            # Extract step count
            step_count = get_step_count_from_conversation_history(conversation_file)
            
            if step_count is None:
                failed_count += 1
                logger.warning(f"Failed to extract step count for iteration {iteration.uuid}")
                continue
            
            # Update database
            try:
                iteration.total_steps = step_count
                db.commit()
                updated_count += 1
                logger.info(f"✅ Updated iteration {iteration.uuid}: {step_count} steps (task: {execution.task_identifier})")
            except Exception as e:
                db.rollback()
                failed_count += 1
                logger.error(f"Failed to update iteration {iteration.uuid}: {e}")
        
        # Print summary
        logger.info("=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total iterations: {len(iterations)}")
        logger.info(f"✅ Successfully updated: {updated_count}")
        logger.info(f"⏭️  Skipped (already has steps): {skipped_already_has_steps}")
        logger.info(f"⏭️  Skipped (no execution data): {skipped_no_execution}")
        logger.info(f"⏭️  Skipped (no directory path): {skipped_no_directory}")
        logger.info(f"⏭️  Skipped (no conversation file): {skipped_no_file}")
        logger.info(f"❌ Failed: {failed_count}")
        logger.info("=" * 80)


if __name__ == "__main__":
    logger.info("Starting iteration steps update script...")
    logger.info("")
    
    # First, count how many iterations need updating
    with get_db_session() as db:
        total_iterations = db.query(Iteration).count()
        iterations_without_steps = db.query(Iteration).filter(Iteration.total_steps == None).count()
        iterations_with_steps = total_iterations - iterations_without_steps
    
    logger.info("=" * 80)
    logger.info("DATABASE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total iterations in database: {total_iterations}")
    logger.info(f"Already have steps: {iterations_with_steps}")
    logger.info(f"Need updating: {iterations_without_steps}")
    logger.info("=" * 80)
    logger.info("")
    
    if iterations_without_steps == 0:
        logger.info("✅ All iterations already have step counts. Nothing to update!")
        sys.exit(0)
    
    # Confirm before proceeding
    response = input(f"Update {iterations_without_steps} iterations? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        logger.info("Aborted by user")
        sys.exit(0)
    
    logger.info("")
    update_iteration_steps()
    logger.info("✅ Script completed!")

