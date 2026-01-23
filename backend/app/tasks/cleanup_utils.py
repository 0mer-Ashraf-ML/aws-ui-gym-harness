"""
Utility for cleaning up leaked browser processes

This module provides functions to detect and kill leaked Chrome/Chromium
browser processes that can accumulate when Playwright cleanup fails.
"""

import logging
import subprocess
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_browser_process_count() -> int:
    """
    Get count of Chrome/Chromium browser processes
    
    Returns:
        Number of browser processes found
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "chrome|chromium"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.stdout:
            pids = [p for p in result.stdout.strip().split('\n') if p]
            return len(pids)
        
        return 0
    except Exception as e:
        logger.error(f"Failed to count browser processes: {e}")
        return 0


def get_active_celery_task_count() -> int:
    """
    Get count of currently executing Celery tasks
    
    Returns:
        Number of active tasks
    """
    try:
        from app.celery_app import celery_app
        
        # Get active tasks from Celery
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        
        if active_tasks:
            # Count total active tasks across all workers
            total = sum(len(tasks) for tasks in active_tasks.values())
            return total
        
        return 0
    except Exception as e:
        logger.error(f"Failed to get active task count: {e}")
        return -1  # Return -1 to indicate error (don't cleanup if unsure)


def kill_leaked_browsers(threshold: int = 50, aggressive_threshold: int = 200) -> Dict[str, Any]:
    """
    Safely kill leaked Chrome/Chromium browser processes
    
    Uses a two-tier approach:
    1. If browser_count > aggressive_threshold AND no active tasks: Kill all (safe)
    2. If browser_count > threshold: Kill only old orphaned processes (safer)
    
    Args:
        threshold: Normal threshold for selective cleanup (default: 50)
        aggressive_threshold: Threshold for aggressive cleanup when no tasks active (default: 200)
        
    Returns:
        Dictionary with cleanup status and count
    """
    try:
        browser_count = get_browser_process_count()
        active_tasks = get_active_celery_task_count()
        
        logger.info(f"Found {browser_count} browser processes, {active_tasks} active tasks (threshold: {threshold}, aggressive: {aggressive_threshold})")
        
        # If we can't determine active tasks, be conservative
        if active_tasks < 0:
            logger.warning("Cannot determine active task count, skipping cleanup for safety")
            return {
                "status": "skipped",
                "reason": "cannot_determine_active_tasks",
                "browser_count": browser_count
            }
        
        # AGGRESSIVE MODE: Many browsers AND no active tasks = Safe to kill all
        if browser_count > aggressive_threshold and active_tasks == 0:
            logger.warning(f"AGGRESSIVE CLEANUP: {browser_count} browsers with 0 active tasks, killing all")
            
            subprocess.run(
                ["pkill", "-9", "-f", "chrome|chromium"],
                timeout=5,
                check=False
            )
            
            logger.info(f"Killed {browser_count} leaked browser processes (aggressive mode)")
            
            return {
                "status": "cleaned_aggressive",
                "killed_count": browser_count,
                "active_tasks": active_tasks,
                "threshold": aggressive_threshold
            }
        
        # CONSERVATIVE MODE: Kill only old orphaned processes
        elif browser_count > threshold:
            logger.warning(f"CONSERVATIVE CLEANUP: {browser_count} browsers with {active_tasks} active tasks, killing only orphaned/old processes")
            
            # Kill only Chrome processes that:
            # 1. Are orphaned (parent PID = 1)
            # 2. Have been running for > 15 minutes (900 seconds)
            killed_count = 0
            
            try:
                # Get Chrome PIDs with their parent PID and running time
                result = subprocess.run(
                    ["ps", "-eo", "pid,ppid,etime,comm"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                for line in result.stdout.split('\n'):
                    if 'chrome' in line.lower() or 'chromium' in line.lower():
                        parts = line.split()
                        if len(parts) >= 4:
                            pid = parts[0]
                            ppid = parts[1]
                            etime = parts[2]  # Format: [[DD-]HH:]MM:SS
                            
                            # Parse elapsed time to seconds
                            time_seconds = 0
                            if '-' in etime:  # Days present
                                days, rest = etime.split('-')
                                time_seconds += int(days) * 86400
                                etime = rest
                            
                            time_parts = etime.split(':')
                            if len(time_parts) == 3:  # HH:MM:SS
                                time_seconds += int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                            elif len(time_parts) == 2:  # MM:SS
                                time_seconds += int(time_parts[0]) * 60 + int(time_parts[1])
                            
                            # Kill if orphaned OR running > 15 minutes
                            if ppid == '1' or time_seconds > 900:
                                try:
                                    subprocess.run(["kill", "-9", pid], timeout=2, check=False)
                                    killed_count += 1
                                    logger.debug(f"Killed orphaned/old Chrome PID {pid} (parent={ppid}, age={time_seconds}s)")
                                except Exception:
                                    pass
                
                logger.info(f"Killed {killed_count} orphaned/old browser processes (conservative mode)")
                
                return {
                    "status": "cleaned_conservative",
                    "killed_count": killed_count,
                    "active_tasks": active_tasks,
                    "browser_count": browser_count,
                    "threshold": threshold
                }
                
            except Exception as ps_error:
                logger.error(f"Failed to parse process list: {ps_error}")
                return {
                    "status": "error",
                    "error": str(ps_error)
                }
        
        # SAFE: Below threshold, no cleanup needed
        return {
            "status": "ok",
            "browser_count": browser_count,
            "active_tasks": active_tasks,
            "threshold": threshold
        }
        
    except Exception as e:
        logger.error(f"Failed to kill leaked browsers: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e)
        }


def cleanup_child_processes(parent_pid: int = None):
    """
    Clean up browser processes spawned by a specific parent PID
    
    Args:
        parent_pid: Parent process ID (defaults to current process)
    """
    try:
        if parent_pid is None:
            parent_pid = os.getpid()
        
        # Kill chrome/chromium children of this process
        subprocess.run(
            f"pkill -9 -P {parent_pid} -f 'chrome|chromium'",
            shell=True,
            timeout=5,
            check=False
        )
        
        logger.debug(f"Cleaned up browser children of PID {parent_pid}")
        
    except Exception as e:
        logger.error(f"Failed to cleanup child processes: {e}")


def get_firefox_process_count() -> int:
    """
    Get count of Firefox browser processes
    
    Note: In this system, Firefox is exclusively used by Playwright,
    so all Firefox processes are Playwright-managed processes.
    
    Returns:
        Number of Firefox processes found
    """
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.stdout:
            firefox_count = 0
            for line in result.stdout.split('\n'):
                if 'firefox' in line.lower() and 'grep' not in line.lower():
                    firefox_count += 1
            return firefox_count
        
        return 0
    except Exception as e:
        logger.error(f"Failed to count Firefox processes: {e}")
        return 0


def get_firefox_processes_with_age() -> list:
    """
    Get list of Firefox processes with their PIDs and elapsed time
    
    Note: In this system, Firefox is exclusively used by Playwright,
    so all Firefox processes are Playwright-managed processes.
    
    Returns:
        List of tuples: [(pid, elapsed_seconds, command), ...]
    """
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,etime,comm,args"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        firefox_processes = []
        
        for line in result.stdout.split('\n'):
            if 'firefox' in line.lower() and 'grep' not in line.lower():
                parts = line.split(None, 3)
                if len(parts) >= 3:
                    pid = parts[0]
                    etime = parts[1]  # Format: [[DD-]HH:]MM:SS
                    command = parts[2] if len(parts) > 2 else ""
                    full_args = parts[3] if len(parts) > 3 else ""
                    
                    # Parse elapsed time to seconds
                    time_seconds = 0
                    if '-' in etime:  # Days present
                        days, rest = etime.split('-')
                        time_seconds += int(days) * 86400
                        etime = rest
                    
                    time_parts = etime.split(':')
                    if len(time_parts) == 3:  # HH:MM:SS
                        time_seconds += int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                    elif len(time_parts) == 2:  # MM:SS
                        time_seconds += int(time_parts[0]) * 60 + int(time_parts[1])
                    
                    firefox_processes.append((pid, time_seconds, full_args))
        
        return firefox_processes
        
    except Exception as e:
        logger.error(f"Failed to get Firefox processes with age: {e}")
        return []


def get_oldest_executing_task_age() -> int:
    """
    Get the age (in seconds) of the oldest executing task from the database
    
    Returns:
        Age in seconds of the oldest executing task, or 0 if no executing tasks
    """
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        with get_db_session() as db:
            query = """
                SELECT 
                    EXTRACT(EPOCH FROM (NOW() - i.started_at)) as execution_time_seconds
                FROM iterations i
                WHERE i.status = 'executing'
                AND i.started_at IS NOT NULL
                ORDER BY i.started_at ASC
                LIMIT 1
            """
            
            result = db.execute(text(query))
            oldest = result.fetchone()
            
            if oldest and oldest.execution_time_seconds:
                return int(oldest.execution_time_seconds)
            
            return 0
            
    except Exception as e:
        logger.error(f"Failed to get oldest executing task age: {e}")
        return 0


def get_executing_task_count() -> int:
    """
    Get count of tasks currently in 'executing' state from database
    
    Returns:
        Number of executing tasks
    """
    try:
        from sqlalchemy import text
        from app.core.database_utils import get_db_session
        
        with get_db_session() as db:
            query = """
                SELECT COUNT(*) as count
                FROM iterations
                WHERE status = 'executing'
            """
            
            result = db.execute(text(query))
            count_result = result.fetchone()
            
            if count_result:
                return int(count_result.count)
            
            return 0
            
    except Exception as e:
        logger.error(f"Failed to get executing task count: {e}")
        return 0


def kill_old_firefox_processes(buffer_minutes: int = None) -> Dict[str, Any]:
    """
    Kill dangling Firefox processes older than a dynamic threshold
    
    This is a smart cleanup that only kills dangling processes:
    1. Checks if there are more Firefox processes than executing tasks
    2. Calculates dynamic threshold: oldest_executing_task_age + buffer_minutes
    3. Kills Firefox processes older than threshold
    4. Protects actively running tasks
    
    Note: In this system, Firefox is exclusively used by Playwright,
    so all Firefox processes are Playwright-managed processes.
    
    Args:
        buffer_minutes: Buffer time in minutes to add to oldest task age (default: from config, typically 10)
                       Example: oldest task is 70 min, buffer is 10 → kill processes older than 80 min
        
    Returns:
        Dictionary with cleanup status and details
    """
    try:
        # Get buffer from config if not provided
        if buffer_minutes is None:
            from app.core.config import settings
            buffer_minutes = settings.FIREFOX_CLEANUP_BUFFER_MINUTES
        
        firefox_count = get_firefox_process_count()
        executing_count = get_executing_task_count()
        oldest_task_age_seconds = get_oldest_executing_task_age()
        
        logger.info(
            f"🔍 Firefox cleanup check: {firefox_count} processes, "
            f"{executing_count} executing tasks, oldest task age: {oldest_task_age_seconds}s"
        )
        
        # Special case: If no executing tasks but Firefox processes exist
        # These are leftover processes from crashed/completed tasks
        # Use buffer threshold directly - it provides natural protection for new processes
        if executing_count == 0 and firefox_count > 0:
            logger.warning(
                f"⚠️ No executing tasks but {firefox_count} Firefox processes found - "
                f"checking for orphaned processes older than {buffer_minutes} minutes"
            )
            
            # Get all Firefox processes with their ages
            firefox_processes = get_firefox_processes_with_age()
            
            if not firefox_processes:
                return {
                    "status": "ok",
                    "firefox_count": 0,
                    "executing_count": 0,
                    "oldest_task_age_seconds": 0,
                    "killed_count": 0,
                    "message": "No processes found"
                }
            
            # Kill processes older than buffer threshold
            # The threshold itself protects new processes (they're < buffer_minutes old)
            age_threshold_seconds = buffer_minutes * 60
            killed_count = 0
            killed_pids = []
            
            for pid, age_seconds, command in firefox_processes:
                if age_seconds > age_threshold_seconds:
                    try:
                        logger.warning(
                            f"🔪 Killing orphaned Firefox process PID {pid} "
                            f"(age: {age_seconds}s = {age_seconds/60:.1f}min, threshold: {buffer_minutes}min)"
                        )
                        subprocess.run(
                            ["kill", "-9", pid],
                            timeout=2,
                            check=False
                        )
                        killed_count += 1
                        killed_pids.append(pid)
                    except Exception as kill_error:
                        logger.error(f"Failed to kill Firefox PID {pid}: {kill_error}")
            
            if killed_count > 0:
                logger.warning(
                    f"🧹 Killed {killed_count} orphaned Firefox processes (threshold: {buffer_minutes} min)"
                )
                return {
                    "status": "cleaned",
                    "firefox_count": firefox_count,
                    "executing_count": 0,
                    "oldest_task_age_seconds": 0,
                    "buffer_minutes": buffer_minutes,
                    "age_threshold_minutes": buffer_minutes,
                    "killed_count": killed_count,
                    "killed_pids": killed_pids,
                    "message": f"Killed {killed_count} orphaned processes"
                }
            else:
                logger.info(
                    f"ℹ️ All {firefox_count} processes are younger than {buffer_minutes} minutes - "
                    "allowing time for self-cleanup"
                )
                return {
                    "status": "ok",
                    "firefox_count": firefox_count,
                    "executing_count": 0,
                    "oldest_task_age_seconds": 0,
                    "buffer_minutes": buffer_minutes,
                    "killed_count": 0,
                    "message": f"Processes too young (< {buffer_minutes} min) - waiting"
                }
        
        # Safety check: If process count <= executing count, nothing to clean
        if firefox_count <= executing_count:
            logger.info("✅ Firefox process count is within expected range, no cleanup needed")
            return {
                "status": "ok",
                "firefox_count": firefox_count,
                "executing_count": executing_count,
                "oldest_task_age_seconds": oldest_task_age_seconds,
                "killed_count": 0,
                "message": "Process count within expected range"
            }
        
        # We have more processes than executing tasks - find dangling ones
        logger.warning(
            f"⚠️ Found {firefox_count - executing_count} potential dangling Firefox processes"
        )
        
        # Calculate dynamic threshold: oldest task age + buffer
        oldest_task_age_minutes = oldest_task_age_seconds / 60
        age_threshold_minutes = oldest_task_age_minutes + buffer_minutes
        age_threshold_seconds = age_threshold_minutes * 60
        
        logger.info(
            f"🎯 Dynamic threshold: {age_threshold_minutes:.1f} min "
            f"(oldest task: {oldest_task_age_minutes:.1f} min + buffer: {buffer_minutes} min)"
        )
        
        # Get all Firefox processes with their ages
        firefox_processes = get_firefox_processes_with_age()
        
        if not firefox_processes:
            logger.info("No Firefox processes found to clean")
            return {
                "status": "ok",
                "firefox_count": 0,
                "executing_count": executing_count,
                "oldest_task_age_seconds": oldest_task_age_seconds,
                "killed_count": 0,
                "message": "No processes found"
            }
        
        # Kill processes older than threshold
        killed_count = 0
        killed_pids = []
        
        for pid, age_seconds, command in firefox_processes:
            if age_seconds > age_threshold_seconds:
                try:
                    logger.info(
                        f"🔪 Killing dangling Firefox process PID {pid} "
                        f"(age: {age_seconds}s = {age_seconds/60:.1f}min, threshold: {age_threshold_minutes:.1f}min)"
                    )
                    subprocess.run(
                        ["kill", "-9", pid],
                        timeout=2,
                        check=False
                    )
                    killed_count += 1
                    killed_pids.append(pid)
                except Exception as kill_error:
                    logger.error(f"Failed to kill Firefox PID {pid}: {kill_error}")
        
        if killed_count > 0:
            logger.warning(
                f"🧹 Killed {killed_count} dangling Firefox processes older than {age_threshold_minutes:.1f} minutes"
            )
        else:
            logger.info(
                f"ℹ️ No Firefox processes older than {age_threshold_minutes:.1f} minutes found to kill"
            )
        
        return {
            "status": "cleaned" if killed_count > 0 else "ok",
            "firefox_count": firefox_count,
            "executing_count": executing_count,
            "oldest_task_age_seconds": oldest_task_age_seconds,
            "oldest_task_age_minutes": oldest_task_age_minutes,
            "buffer_minutes": buffer_minutes,
            "age_threshold_minutes": age_threshold_minutes,
            "killed_count": killed_count,
            "killed_pids": killed_pids,
            "message": f"Killed {killed_count} dangling processes"
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to kill old Firefox processes: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "killed_count": 0
        }
