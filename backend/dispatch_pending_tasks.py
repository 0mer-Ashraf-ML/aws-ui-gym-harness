#!/usr/bin/env python3
"""
Script to manually dispatch pending tasks that were created but never dispatched
"""

import asyncio
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text

from app.core.database_utils import get_db_session
from app.tasks.unified_execution import execute_single_iteration_unified

def dispatch_pending_tasks():
    """Dispatch all pending iterations as Celery tasks"""
    with get_db_session() as db:
        # Get all pending iterations with their execution and task data
        query = """
            SELECT 
                i.uuid as iteration_id,
                i.execution_id,
                e.gym_id,
                e.model,
                e.execution_folder_name,
                t.uuid as task_id,
                t.prompt as task_description
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            JOIN tasks t ON i.task_id = t.uuid
            WHERE i.status = 'pending'
        """
        
        result = db.execute(text(query))
        pending_iterations = result.fetchall()
        
        print(f"Found {len(pending_iterations)} pending iterations")
        
        for iteration in pending_iterations:
            print(f"🚀 Dispatching iteration {iteration.iteration_id}")
            print(f"   Task: {iteration.task_description}")
            print(f"   Gym: {iteration.gym_id}")
            print(f"   Model: {iteration.model}")
            
            # Dispatch the task
            execute_single_iteration_unified.delay(
                iteration_id=str(iteration.iteration_id),
                task_id=str(iteration.task_id),
                gym_id=str(iteration.gym_id),
                runner_type=iteration.model,
                max_wait_time=1800  # 30 minutes timeout
            )
            
            print(f"✅ Dispatched iteration {iteration.iteration_id}")
            print()
        
        print(f"🎉 Successfully dispatched {len(pending_iterations)} pending tasks!")

if __name__ == "__main__":
    dispatch_pending_tasks()
