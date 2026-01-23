#!/usr/bin/env python3
"""
CLI runner for harness execution from CSV file.

Usage:
    python cli_runner.py <csv_file> [--task-id TASK_ID] [--models MODELS] [--iterations N]

Examples:
    # Run all tasks (default: all models, 1 iteration)
    # CSV file will be looked up in task_sheets directory automatically
    python cli_runner.py tasks.csv
    
    # Run specific task
    python cli_runner.py tasks.csv --task-id task_1
    
    # Run with specific models
    python cli_runner.py tasks.csv --models openai,anthropic
    
    # Run with custom iterations
    python cli_runner.py tasks.csv --iterations 5
    
    # Combine options
    python cli_runner.py tasks.csv --task-id task_1 --models gemini --iterations 3
"""

import argparse
import asyncio
import csv
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

from rich.console import Console
from rich.live import Live
from rich.text import Text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.gym import Gym, VerificationStrategy
from app.models.task import Task
from app.schemas.batch import BatchCreate, ModelType
from app.schemas.gym import GymCreate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.batch_execution import batch_execution_service
from app.services.batch_status_manager import BatchStatusManager
from app.services.crud.batch import batch_crud
from app.services.crud.gym import gym_crud
from app.services.crud.task import task_crud
from app.services.reports.batch_report import generate_batch_report

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose logs from other modules during monitoring
logging.getLogger('app.services.execution_status_manager').setLevel(logging.WARNING)
logging.getLogger('app.services.batch_status_manager').setLevel(logging.WARNING)

# Rich console for progress display
console = Console()


def normalize_base_url(url: str) -> str:
    """Normalize URL to base URL (scheme + netloc)"""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return base_url.rstrip('/')


async def find_or_create_gym(db: AsyncSession, url: str) -> Gym:
    """Find gym by base_url or create if it doesn't exist.
    
    This function normalizes the URL to extract the base URL (scheme + netloc)
    and checks if a gym exists with that base_url, regardless of the full URL path.
    If a gym exists with the same base_url, it will be reused instead of creating a new one.
    """
    # Normalize URL to base URL (scheme + netloc only)
    # This ensures that URLs like:
    # - https://example.com/page1
    # - https://example.com/page2
    # - https://example.com/any/path
    # All match the same gym with base_url: https://example.com
    normalized_base_url = normalize_base_url(url)
    
    # Try to find existing gym with same base_url (ignoring the full URL path)
    result = await db.execute(
        select(Gym).where(Gym.base_url == normalized_base_url)
    )
    existing_gym = result.scalar_one_or_none()
    
    if existing_gym:
        logger.debug(f"♻️  Reusing existing gym: {existing_gym.name} (base_url: {normalized_base_url})")
        return existing_gym
    
    # Create new gym with local storage assertions verification strategy
    gym_name = f"Gym_{normalized_base_url.replace('://', '_').replace('.', '_').replace('/', '_')}"
    gym_data = GymCreate(
        name=gym_name,
        base_url=normalized_base_url,
        verification_strategy=VerificationStrategy.LOCAL_STORAGE_ASSERTIONS,
        description=f"Auto-created gym for {normalized_base_url}"
    )
    
    gym = await gym_crud.create(db, gym_data)
    logger.debug(f"✨ Created new gym: {gym.name} (base_url: {normalized_base_url})")
    return gym


async def find_or_create_task(
    db: AsyncSession,
    gym_id: UUID,
    task_id: str,
    prompt: str
) -> Task:
    """Find task by task_id and gym_id, or create/update if it doesn't exist"""
    # Try to find existing task within this gym
    existing_task = await task_crud.get_by_task_id_and_gym(db, task_id, gym_id)
    
    if existing_task:
        # Always update prompt (even if same, to ensure it's current)
        task_update = TaskUpdate(prompt=prompt)
        updated_task = await task_crud.update(db, existing_task.uuid, task_update)
        logger.debug(f"♻️  Updated task: {task_id}")
        return updated_task
    
    # Create new task
    task_data = TaskCreate(
        task_id=task_id,
        gym_id=gym_id,
        prompt=prompt
    )
    
    task = await task_crud.create(db, task_data)
    logger.debug(f"✨ Created task: {task_id}")
    return task


async def process_csv_file(csv_path: Path, selected_task_id: Optional[str] = None) -> Dict[str, List[Task]]:
    """Process CSV file and create/update gyms and tasks"""
    gym_tasks: Dict[UUID, List[Task]] = {}
    
    async with AsyncSessionLocal() as db:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Validate required columns
            required_columns = {'task_id', 'prompt', 'url'}
            if not required_columns.issubset(reader.fieldnames or []):
                raise ValueError(
                    f"CSV must contain columns: {', '.join(required_columns)}. "
                    f"Found: {', '.join(reader.fieldnames or [])}"
                )
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 because row 1 is header
                task_id = row['task_id'].strip()
                prompt = row['prompt'].strip()
                url = row['url'].strip()
                
                if not task_id or not prompt or not url:
                    logger.warning(f"Skipping row {row_num}: missing required fields")
                    continue
                
                # Filter by selected_task_id if provided
                if selected_task_id and task_id != selected_task_id:
                    continue
                
                # Find or create gym
                gym = await find_or_create_gym(db, url)
                
                # Find or create task
                task = await find_or_create_task(db, gym.uuid, task_id, prompt)
                
                # Group tasks by gym
                if gym.uuid not in gym_tasks:
                    gym_tasks[gym.uuid] = []
                gym_tasks[gym.uuid].append(task)
    
    return gym_tasks


async def create_and_execute_batch(
    gym_id: UUID,
    tasks: List[Task],
    selected_models: List[ModelType],
    number_of_iterations: int,
    selected_task_uuids: Optional[List[UUID]] = None
) -> UUID:
    """Create a batch and execute it"""
    async with AsyncSessionLocal() as db:
        # Filter tasks if specific task UUIDs are selected
        if selected_task_uuids:
            tasks = [t for t in tasks if t.uuid in selected_task_uuids]
            if not tasks:
                raise ValueError(f"No tasks found matching selected task UUIDs: {selected_task_uuids}")
        
        # Get task UUIDs for the batch
        task_uuids = [t.uuid for t in tasks]
        
        # Create batch
        batch_data = BatchCreate(
            name=f"CLI_Batch_{int(time.time())}",
            gym_id=gym_id,
            number_of_iterations=number_of_iterations,
            selected_models=selected_models,
            selected_task_ids=task_uuids
        )
        
        batch = await batch_crud.create(db, batch_data)
        logger.debug(f"📦 Created batch: {batch.name}")
        
        # Execute batch
        executions = await batch_execution_service.execute_batch(
            db,
            batch.uuid,
            batch_data.selected_models,
            batch_data.selected_task_ids
        )
        logger.debug(f"🚀 Started {len(executions)} execution(s)")
        
        return batch.uuid


def format_progress_line(summary: dict, elapsed_str: str) -> str:
    """Format progress line for in-place display"""
    total = summary.get('total_executions', 0)
    pending = summary.get('pending_count', 0)
    executing = summary.get('executing_count', 0)
    passed = summary.get('passed_count', 0)
    failed = summary.get('failed_count', 0)
    crashed = summary.get('crashed_count', 0)
    timeout = summary.get('timeout_count', 0)
    
    # Calculate progress percentage
    completed = passed
    failed_total = failed + timeout + crashed
    finished = completed + failed_total
    
    if total > 0:
        progress_pct = int((finished / total) * 100)
        progress_bar = "█" * (progress_pct // 2) + "░" * (50 - (progress_pct // 2))
    else:
        progress_pct = 0
        progress_bar = "░" * 50
    
    # Build status string - only show non-zero counts
    parts = []
    if pending > 0:
        parts.append(f"⏳ Pending: {pending}")
    if executing > 0:
        parts.append(f"🔄 Executing: {executing}")
    if completed > 0:
        parts.append(f"✅ Completed: {completed}")
    if failed > 0:
        parts.append(f"❌ Failed: {failed}")
    if timeout > 0:
        parts.append(f"⏱️  Timeout: {timeout}")
    if crashed > 0:
        parts.append(f"💥 Crashed: {crashed}")
    
    status_str = " | ".join(parts) if parts else "No executions"
    return f"📊 [{progress_bar}] {progress_pct}% | Total: {total} | {status_str} | ⏱️  {elapsed_str}"


async def wait_for_batch_completion(batch_id: UUID, check_interval: int = 10, timeout: int = 7200) -> bool:
    """Wait for batch to complete (timeout in seconds, default 2 hours)"""
    start_time = time.time()
    
    # Suppress verbose logs during monitoring
    original_levels = {}
    verbose_loggers = [
        'app.services.execution_status_manager',
        'app.services.batch_status_manager',
        'app.services.crud',
        'app.services.batch_execution'
    ]
    for logger_name in verbose_loggers:
        log = logging.getLogger(logger_name)
        original_levels[logger_name] = log.level
        log.setLevel(logging.WARNING)
    
    try:
        with Live(console=console, refresh_per_second=2, transient=False) as live:
            while True:
                elapsed = time.time() - start_time
                elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                
                if elapsed > timeout:
                    live.update(Text(f"❌ Batch did not complete within {int(timeout // 60)}m", style="red"))
                    await asyncio.sleep(1)  # Show error briefly
                    return False
                
                async with AsyncSessionLocal() as db:
                    # Get batch status
                    status = await BatchStatusManager.update_batch_status_from_executions(batch_id)
                    
                    # Get detailed status summary
                    summary = await BatchStatusManager.get_batch_status_summary(batch_id)
                    
                    # Format and update progress line
                    progress_line = format_progress_line(summary, elapsed_str)
                    live.update(Text(progress_line))
                    
                    # Check if batch is finished
                    if status.value in ['completed', 'failed', 'crashed']:
                        # Show final status (will remain visible after context exits)
                        final_line = format_progress_line(summary, elapsed_str)
                        live.update(Text(final_line))
                        await asyncio.sleep(0.5)  # Brief pause to show final status
                        return True
                
                await asyncio.sleep(check_interval)
    finally:
        # Restore original log levels
        for logger_name, level in original_levels.items():
            logging.getLogger(logger_name).setLevel(level)


async def generate_and_save_report(batch_id: UUID, output_dir: Path) -> Path:
    """Generate batch report and save to output directory"""
    async with AsyncSessionLocal() as db:
        report_result = await generate_batch_report(db, batch_id)
        
        # Get the generated file path
        report_path = Path(report_result['filepath'])
        
        # Copy to output directory
        output_path = output_dir / report_path.name
        if report_path.exists():
            import shutil
            shutil.copy2(report_path, output_path)
            logger.debug(f"📄 Report saved: {output_path.name}")
            
            # Also copy JSON snapshot if it exists
            json_path = report_path.with_suffix('.json')
            if json_path.exists():
                json_output = output_dir / json_path.name
                shutil.copy2(json_path, json_output)
                logger.debug(f"📄 JSON snapshot saved: {json_path.name}")
            
            return output_path
        else:
            raise FileNotFoundError(f"Report file not found: {report_path}")


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Run harness tasks from CSV file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tasks in CSV (default: all models, 1 iteration)
  # CSV file will be looked up in task_sheets directory automatically
  python cli_runner.py tasks.csv
  
  # Run specific task
  python cli_runner.py tasks.csv --task-id task_1
  
  # Run with specific models (comma-separated: openai,anthropic,gemini)
  python cli_runner.py tasks.csv --models openai,anthropic
  
  # Run with custom number of iterations
  python cli_runner.py tasks.csv --iterations 5
  
  # Combine options
  python cli_runner.py tasks.csv --task-id task_1 --models gemini --iterations 3
        """
    )
    
    parser.add_argument(
        'csv_file',
        type=str,
        help='CSV filename (will be looked up in task_sheets directory). Example: tasks.csv or my_tasks.csv'
    )
    
    parser.add_argument(
        '--task-id',
        type=str,
        default=None,
        help='Run specific task by task_id (if not provided, all tasks will run)'
    )
    
    parser.add_argument(
        '--models',
        type=str,
        default='openai,anthropic,gemini',
        help='Comma-separated list of models to run (default: openai,anthropic,gemini). Options: openai, anthropic, gemini'
    )
    
    parser.add_argument(
        '--iterations',
        type=int,
        default=1,
        help='Number of iterations per task (default: 1)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=7200,
        help='Timeout for batch completion in seconds (default: 7200 = 2 hours)'
    )
    
    parser.add_argument(
        '--check-interval',
        type=int,
        default=10,
        help='Interval between status checks in seconds (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Parse and validate models
    model_mapping = {
        'openai': ModelType.OPENAI,
        'anthropic': ModelType.ANTHROPIC,
        'gemini': ModelType.GEMINI
    }
    
    selected_models = []
    model_names = [m.strip().lower() for m in args.models.split(',')]
    for model_name in model_names:
        if model_name not in model_mapping:
            logger.error(f"Invalid model: {model_name}. Valid options: {', '.join(model_mapping.keys())}")
            sys.exit(1)
        selected_models.append(model_mapping[model_name])
    
    if not selected_models:
        logger.error("At least one model must be selected")
        sys.exit(1)
    
    # Validate iterations
    if args.iterations < 1 or args.iterations > 10:
        logger.error("Number of iterations must be between 1 and 10")
        sys.exit(1)
    
    # Resolve CSV file path - automatically check in task_sheets directory
    csv_path = Path(args.csv_file)
    
    # If path is just a filename (no directory), look in task_sheets directory
    if csv_path.name == str(csv_path) and not csv_path.is_absolute():
        # Check /app/task_sheets first (Docker environment)
        docker_task_sheets_path = Path('/app/task_sheets') / csv_path.name
        if docker_task_sheets_path.exists():
            csv_path = docker_task_sheets_path
            logger.info(f"Found CSV in task_sheets directory: {csv_path}")
        else:
            # Try ./task_sheets (local development)
            local_task_sheets_path = Path('task_sheets') / csv_path.name
            if local_task_sheets_path.exists():
                csv_path = local_task_sheets_path
                logger.info(f"Found CSV in task_sheets directory: {csv_path}")
            else:
                # Try current directory as last resort
                current_dir_path = Path.cwd() / csv_path.name
                if current_dir_path.exists():
                    csv_path = current_dir_path
                    logger.info(f"Found CSV in current directory: {csv_path}")
                else:
                    logger.error(f"CSV file not found: {csv_path.name}")
                    logger.error(f"  Checked: /app/task_sheets/{csv_path.name}")
                    logger.error(f"  Checked: ./task_sheets/{csv_path.name}")
                    logger.error(f"  Checked: {current_dir_path}")
                    sys.exit(1)
    elif not csv_path.exists():
        # Path was specified but doesn't exist
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    
    try:
        # Process CSV file
        logger.info("=" * 80)
        logger.info("🚀 Starting CLI Batch Execution")
        logger.info("=" * 80)
        logger.info(f"📄 Processing CSV file: {csv_path}")
        
        gym_tasks = await process_csv_file(csv_path, args.task_id)
        
        if not gym_tasks:
            logger.error("❌ No tasks found in CSV file")
            sys.exit(1)
        
        # Count total tasks
        total_tasks = sum(len(tasks) for tasks in gym_tasks.values())
        logger.info(f"✅ Found {total_tasks} task(s) across {len(gym_tasks)} gym(s)")
        logger.info(f"🤖 Selected models: {', '.join([m.value.upper() for m in selected_models])}")
        logger.info(f"🔄 Number of iterations per task: {args.iterations}")
        logger.info(f"⏱️  Timeout: {args.timeout // 60} minutes")
        logger.info("─" * 80)
        
        # Create and execute batches for each gym
        batch_ids = []
        for gym_id, tasks in gym_tasks.items():
            logger.info(f"📦 Creating batch for {len(tasks)} task(s) in gym {gym_id}")
            
            # Filter tasks if specific task_id is selected (already filtered in process_csv_file, but double-check)
            selected_task_uuids = None
            if args.task_id:
                tasks = [t for t in tasks if t.task_id == args.task_id]
                if not tasks:
                    logger.warning(f"⚠️  Task {args.task_id} not found in gym {gym_id}")
                    continue
                selected_task_uuids = [t.uuid for t in tasks]
            
            batch_id = await create_and_execute_batch(
                gym_id,
                tasks,
                selected_models,
                args.iterations,
                selected_task_uuids
            )
            batch_ids.append(batch_id)
            logger.info(f"✅ Batch created: {batch_id}")
        
        if not batch_ids:
            logger.error("❌ No batches were created")
            sys.exit(1)
        
        logger.info("─" * 80)
        logger.info(f"⏳ Monitoring {len(batch_ids)} batch(es)...")
        logger.info("─" * 80)
        
        # Wait for all batches to complete
        all_completed = True
        for idx, batch_id in enumerate(batch_ids, 1):
            if len(batch_ids) > 1:
                logger.info(f"\n📊 Batch {idx}/{len(batch_ids)}: {batch_id}")
            completed = await wait_for_batch_completion(
                batch_id,
                args.check_interval,
                args.timeout
            )
            if not completed:
                all_completed = False
        
        if not all_completed:
            logger.warning("⚠️  Some batches did not complete within timeout")
            sys.exit(1)
        
        # Generate reports in reports directory
        # In Docker, this will be /app/reports (mounted to ./reports on host)
        # Outside Docker, this will be ./reports relative to the script
        import os
        
        # Try to use /app/reports if running in Docker, otherwise use ./reports
        if os.path.exists('/app/reports'):
            reports_dir = Path('/app/reports')
        else:
            # Fallback to ./reports relative to current working directory
            reports_dir = Path('reports')
        
        reports_dir.mkdir(parents=True, exist_ok=True)
        logger.info("─" * 80)
        logger.info(f"📊 Generating reports in: {reports_dir}")
        logger.info("─" * 80)
        
        for batch_id in batch_ids:
            try:
                report_path = await generate_and_save_report(batch_id, reports_dir)
                logger.info(f"✅ Report generated: {report_path.name}")
            except Exception as e:
                logger.error(f"❌ Failed to generate report for batch {batch_id}: {e}")
        
        logger.info("=" * 80)
        logger.info("🎉 All tasks completed successfully!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Error: {e}", exc_info=True)
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
