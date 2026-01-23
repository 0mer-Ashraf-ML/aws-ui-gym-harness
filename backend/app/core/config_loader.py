"""Utility to load grader_config and simulator_config from JSON files for testing.

This module loads combined task configuration files that contain both
grader_config and simulator_config in a single JSON file per task.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Base directory for config files
CONFIG_BASE_DIR = Path(__file__).parent.parent.parent / "configs"
TASK_CONFIG_DIR = CONFIG_BASE_DIR / "task_configs"


def load_task_config_from_file(task_id: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Load combined task config from single JSON file.
    
    The file should contain both 'grader_config' and 'simulator_config' as
    top-level keys. If either key is missing, it will be set to None.
    
    Args:
        task_id: Task identifier (e.g., "ZEND-TICKET-SPAM-001")
        
    Returns:
        Dict with 'grader_config' and 'simulator_config' keys.
        Each value is either a Dict with the config or None if not found.
        Format: {'grader_config': {...}, 'simulator_config': {...}}
    """
    config_file = TASK_CONFIG_DIR / f"{task_id}.json"
    
    if not config_file.exists():
        logger.debug(f"Task config file not found: {config_file}")
        return {
            'grader_config': None,
            'simulator_config': None,
        }
    
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        # Validate structure
        if not isinstance(config_data, dict):
            logger.error(f"Invalid task config file {config_file}: root must be a dict")
            return {
                'grader_config': None,
                'simulator_config': None,
            }
        
        # Extract grader_config and simulator_config keys
        grader_config = config_data.get('grader_config')
        simulator_config = config_data.get('simulator_config')
        
        logger.info(f"✅ Loaded task config from file: {config_file}")
        
        return {
            'grader_config': grader_config,
            'simulator_config': simulator_config,
        }
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error parsing JSON in task config file {config_file}: {e}")
        return {
            'grader_config': None,
            'simulator_config': None,
        }
    except Exception as e:
        logger.error(f"❌ Error loading task config from {config_file}: {e}")
        return {
            'grader_config': None,
            'simulator_config': None,
        }


def load_configs_from_files(task_id: str) -> Dict[str, Optional[Dict[str, Any]]]:
    """Load both configs from combined task config file.
    
    Args:
        task_id: Task identifier (e.g., "ZEND-TICKET-SPAM-001")
    
    Returns:
        Dict with 'grader_config' and 'simulator_config' keys.
        Each value is either a Dict with the config or None if not found.
    """
    return load_task_config_from_file(task_id)

