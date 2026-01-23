"""
Celery tasks for cleanup operations
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.cleanup.cleanup_temp_files")
def cleanup_temp_files():
    """Clean up temporary files"""
    try:
        logger.info("Starting temporary files cleanup")
        
        temp_dirs = ["results", "logs", "temp"]
        cleaned_files = 0
        
        for temp_dir in temp_dirs:
            temp_path = Path(temp_dir)
            if temp_path.exists():
                # Clean up files older than 7 days
                cutoff_date = datetime.now() - timedelta(days=7)
                
                for file_path in temp_path.rglob("*"):
                    if file_path.is_file():
                        try:
                            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                            if file_mtime < cutoff_date:
                                file_path.unlink()
                                cleaned_files += 1
                        except Exception as e:
                            logger.warning(f"Could not delete file {file_path}: {e}")
        
        logger.info(f"Cleaned up {cleaned_files} temporary files")
        return cleaned_files
        
    except Exception as e:
        logger.error(f"Temporary files cleanup failed: {e}")
        raise

@celery_app.task(name="app.tasks.cleanup.cleanup_screenshots")
def cleanup_screenshots(days_to_keep: int = 7):
    """Clean up old screenshots"""
    try:
        logger.info(f"Starting screenshots cleanup (keeping {days_to_keep} days)")
        
        results_dir = Path("results")
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cleaned_screenshots = 0
        
        if results_dir.exists():
            for screenshot_dir in results_dir.rglob("screenshots"):
                if screenshot_dir.is_dir():
                    for screenshot_file in screenshot_dir.iterdir():
                        if screenshot_file.is_file() and screenshot_file.suffix in ['.png', '.jpg', '.jpeg']:
                            try:
                                file_mtime = datetime.fromtimestamp(screenshot_file.stat().st_mtime)
                                if file_mtime < cutoff_date:
                                    screenshot_file.unlink()
                                    cleaned_screenshots += 1
                            except Exception as e:
                                logger.warning(f"Could not delete screenshot {screenshot_file}: {e}")
        
        logger.info(f"Cleaned up {cleaned_screenshots} old screenshots")
        return cleaned_screenshots
        
    except Exception as e:
        logger.error(f"Screenshots cleanup failed: {e}")
        raise

@celery_app.task(name="app.tasks.cleanup.cleanup_logs")
def cleanup_logs(days_to_keep: int = 30):
    """Clean up old log files"""
    try:
        logger.info(f"Starting logs cleanup (keeping {days_to_keep} days)")
        
        logs_dir = Path("logs")
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cleaned_logs = 0
        
        if logs_dir.exists():
            for log_file in logs_dir.iterdir():
                if log_file.is_file() and log_file.suffix == '.log':
                    try:
                        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                        if file_mtime < cutoff_date:
                            log_file.unlink()
                            cleaned_logs += 1
                    except Exception as e:
                        logger.warning(f"Could not delete log file {log_file}: {e}")
        
        logger.info(f"Cleaned up {cleaned_logs} old log files")
        return cleaned_logs
        
    except Exception as e:
        logger.error(f"Logs cleanup failed: {e}")
        raise

@celery_app.task(name="app.tasks.cleanup.cleanup_database")
def cleanup_database(days_to_keep: int = 90):
    """Clean up old database records"""
    try:
        logger.info(f"Starting database cleanup (keeping {days_to_keep} days)")
        
        from sqlalchemy import delete

        from app.core.database import AsyncSessionLocal
        from app.models.action import Action
        from app.models.response_count import ResponseCount
        from app.models.screenshot import Screenshot
        from app.models.task_execution import TaskExecution
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        async def cleanup():
            async with AsyncSessionLocal() as session:
                # Delete old executions and related records
                old_executions = await session.execute(
                    select(TaskExecution.id).where(TaskExecution.created_at < cutoff_date)
                )
                old_execution_ids = [row[0] for row in old_executions.fetchall()]
                
                if old_execution_ids:
                    # Delete related records first
                    await session.execute(
                        delete(ResponseCount).where(ResponseCount.execution_id.in_(old_execution_ids))
                    )
                    await session.execute(
                        delete(Screenshot).where(Screenshot.execution_id.in_(old_execution_ids))
                    )
                    await session.execute(
                        delete(Action).where(Action.execution_id.in_(old_execution_ids))
                    )
                    
                    # Delete executions
                    result = await session.execute(
                        delete(TaskExecution).where(TaskExecution.id.in_(old_execution_ids))
                    )
                    deleted_count = result.rowcount
                    await session.commit()
                    
                    logger.info(f"Cleaned up {deleted_count} old database records")
                    return deleted_count
                else:
                    logger.info("No old database records to clean up")
                    return 0
        
        # Run async cleanup
        import asyncio
        return asyncio.run(cleanup())
        
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        raise
