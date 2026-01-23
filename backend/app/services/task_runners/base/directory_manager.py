#!/usr/bin/env python3
"""
Centralized Directory Manager for Task Runners

This module provides a single, consistent way to manage all task directories
and file operations across the entire task runner system.

DIRECTORY STRUCTURE:
```
execution_folder/
├── task_id/
│   ├── iteration_1/
│   │   ├── screenshots/
│   │   ├── logs/
│   │   ├── conversation_history/
│   │   ├── task_responses/
│   │   ├── db_instance/
│   │   └── verification.json
│   ├── iteration_2/
│   │   ├── screenshots/
│   │   ├── logs/
│   │   ├── conversation_history/
│   │   ├── task_responses/
│   │   ├── db_instance/
│   │   └── verification.json
│   └── iteration_3/
│       ├── screenshots/
│       ├── logs/
│       ├── conversation_history/
│       ├── task_responses/
│       ├── db_instance/
│       └── verification.json
└── task_id_2/
    ├── iteration_1/
    └── ...
```

USAGE:
```python
from app.services.task_runners.base.directory_manager import DirectoryManager

# Initialize
dm = DirectoryManager(base_results_dir="/app/results")

# Create execution directory
execution_dir = dm.create_execution_directory("batch_name")

# Create task directory
task_dir = dm.create_task_directory("TASK-001", iteration=1)

# Get paths for different file types
screenshot_path = dm.get_screenshot_path("step_name")
log_path = dm.get_log_path("runner_type")
conversation_path = dm.get_conversation_path("step_name")
response_path = dm.get_response_path("step_name")
verification_path = dm.get_verification_path()
```

This ensures:
1. Consistent directory structure across all runners
2. Centralized file path management
3. Easy to maintain and modify
4. No conflicts between different directory creation methods
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.config import settings


class DirectoryManager:
    """
    Centralized directory manager for all task runner operations
    
    This class provides a single source of truth for:
    - Directory structure creation
    - File path generation
    - Directory validation
    - File operations
    """
    
    def __init__(self, base_results_dir: Optional[Path] = None):
        """
        Initialize the directory manager
        
        Args:
            base_results_dir: Base directory for all results (defaults to settings.RESULTS_DIR)
        """
        self.base_results_dir = Path(base_results_dir) if base_results_dir else Path(settings.RESULTS_DIR).resolve()
        self.execution_dir = None
        self.current_task_dir = None
        self.current_iteration = None
        
        # Setup logger
        self.logger = logging.getLogger(__name__)
        
        # Ensure base directory exists
        self.base_results_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"📁 DirectoryManager initialized with base dir: {self.base_results_dir}")
    
    def create_execution_directory(self, execution_name: str = None, model_type: str = None) -> Path:
        """
        Create execution-level directory structure
        
        Args:
            execution_name: Name for the execution directory (auto-generated if None)
            model_type: Model type (anthropic, openai) to append to execution name
            
        Returns:
            Path to the created execution directory
        """
        if execution_name:
            # If model_type is provided, append it to the execution name
            if model_type:
                execution_name = f"{execution_name}_{model_type}"
            self.execution_dir = self.base_results_dir / execution_name
        else:
            # Generate unique execution name with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # Include milliseconds
            execution_name = f"execution_iterations_{timestamp}"
            if model_type:
                execution_name = f"{execution_name}_{model_type}"
            self.execution_dir = self.base_results_dir / execution_name
        
        # Create execution directory
        self.execution_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"📁 Created execution directory: {self.execution_dir}")
        return self.execution_dir
    
    def set_execution_directory(self, execution_dir: Path) -> None:
        """
        Set the execution directory (for existing executions)
        
        Args:
            execution_dir: Path to existing execution directory
        """
        self.execution_dir = Path(execution_dir)
        self.logger.info(f"📁 Set execution directory: {self.execution_dir}")
    
    def create_task_directory(self, task_id: str, iteration: int = 1) -> Path:
        """
        Create task directory structure for a specific iteration
        
        Args:
            task_id: Task identifier
            iteration: Iteration number
            
        Returns:
            Path to the created task directory
        """
        if not self.execution_dir:
            raise ValueError("Execution directory must be set before creating task directories")
        
        # Create task directory structure
        task_dir = self.execution_dir / task_id / f"iteration_{iteration}"
        
        # Create all required subdirectories
        subdirectories = [
            task_dir / "screenshots",
            task_dir / "logs", 
            task_dir / "conversation_history",
            task_dir / "task_responses",
            task_dir / "db_instance"
        ]
        
        for subdir in subdirectories:
            subdir.mkdir(parents=True, exist_ok=True)
        
        # Set current task directory
        self.current_task_dir = task_dir
        self.current_iteration = iteration
        
        self.logger.info(f"📁 Created task directory: {task_dir}")
        return task_dir
    
    def get_screenshot_path(self, step_name: str, task_id: str = None) -> Path:
        """
        Get path for saving a screenshot
        
        Args:
            step_name: Name of the step (e.g., "initial_page", "after_navigation")
            task_id: Task identifier (uses current task if None)
            
        Returns:
            Path for the screenshot file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{task_id or 'task'}_{step_name}_{timestamp}.png"
        return self.current_task_dir / "screenshots" / filename
    
    def get_log_path(self, runner_type: str = "unified") -> Path:
        """
        Get path for saving a log file
        
        Args:
            runner_type: Type of runner (e.g., "unified", "openai", "anthropic")
            
        Returns:
            Path for the log file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{runner_type}_runner_{timestamp}.log"
        return self.current_task_dir / "logs" / filename
    
    def get_conversation_path(self, step_name: str, task_id: str = None) -> Path:
        """
        Get path for saving conversation history
        
        Args:
            step_name: Name of the step
            task_id: Task identifier (uses current task if None)
            
        Returns:
            Path for the conversation file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{task_id or 'task'}_{step_name}_conversation_{timestamp}.json"
        return self.current_task_dir / "conversation_history" / filename
    
    def get_response_path(self, step_name: str, task_id: str = None) -> Path:
        """
        Get path for saving task response
        
        Args:
            step_name: Name of the step
            task_id: Task identifier (uses current task if None)
            
        Returns:
            Path for the response file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{task_id or 'task'}_{step_name}_{timestamp}.json"
        return self.current_task_dir / "task_responses" / filename
    
    def get_verification_path(self) -> Path:
        """
        Get path for saving verification results
        
        Returns:
            Path for the verification file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        return self.current_task_dir / "verification.json"
    
    def get_local_storage_path(self, task_id: str = None) -> Path:
        """
        Get path for saving localStorage dump
        
        Args:
            task_id: Task identifier (uses current task if None)
            
        Returns:
            Path for the localStorage dump file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        return self.current_task_dir / "local_storage_dump.json"
    
    def get_actual_state_path(self) -> Path:
        """
        Get path for saving actual state during verification
        
        Returns:
            Path for the actual state file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        return self.current_task_dir / "actual_state.json"
    
    def get_expected_state_path(self) -> Path:
        """
        Get path for saving expected state during verification
        
        Returns:
            Path for the expected state file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        return self.current_task_dir / "expected_state.json"
    
    def get_db_snapshot_dir(self) -> Path:
        """
        Get path to the db_instance directory for database snapshots
        
        Returns:
            Path to the db_instance directory
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        return self.current_task_dir / "db_instance"
    
    def get_db_snapshot_path(self, when: str = "before") -> Path:
        """
        Get path for saving database snapshot
        
        Args:
            when: "before" or "after" to indicate snapshot timing
            
        Returns:
            Path for the database snapshot file
        """
        if not self.current_task_dir:
            raise ValueError("No current task directory set")
        
        filename = f"db_snapshot_{when}.json"
        return self.current_task_dir / "db_instance" / filename
    
    def validate_directory_structure(self) -> bool:
        """
        Validate that the current task directory has the correct structure
        
        Returns:
            True if structure is valid, False otherwise
        """
        if not self.current_task_dir:
            return False
        
        required_dirs = [
            "screenshots",
            "logs", 
            "conversation_history",
            "task_responses",
            "db_instance"
        ]
        
        for dir_name in required_dirs:
            dir_path = self.current_task_dir / dir_name
            if not dir_path.exists() or not dir_path.is_dir():
                self.logger.error(f"❌ Missing required directory: {dir_path}")
                return False
        
        return True
    
    def get_directory_info(self) -> Dict[str, Any]:
        """
        Get information about the current directory setup
        
        Returns:
            Dictionary with directory information
        """
        return {
            "base_results_dir": str(self.base_results_dir),
            "execution_dir": str(self.execution_dir) if self.execution_dir else None,
            "current_task_dir": str(self.current_task_dir) if self.current_task_dir else None,
            "current_iteration": self.current_iteration,
            "structure_valid": self.validate_directory_structure() if self.current_task_dir else False
        }
    
    def cleanup(self) -> None:
        """
        Clean up current task directory references
        """
        self.current_task_dir = None
        self.current_iteration = None
        self.logger.info("🧹 DirectoryManager cleaned up")
