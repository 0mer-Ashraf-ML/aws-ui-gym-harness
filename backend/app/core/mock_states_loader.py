"""Utility to load mock states from JSON files for testing.

This module provides functions to load mock window.get_states() responses
from JSON files when gyms haven't implemented the function yet.

TODO: Remove this module when gyms implement window.get_states().
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Base directory for mock states files
MOCK_STATES_DIR = Path(__file__).parent.parent.parent / "configs" / "mock_states"


def load_mock_states_from_file(task_id: str) -> Optional[Dict[str, Any]]:
    """Load mock states from JSON file.
    
    Args:
        task_id: Task identifier (e.g., "ZEND-TICKET-SPAM-001")
        
    Returns:
        Dict with 'actual_state' and 'expected_states' keys, or None if file doesn't exist
        Structure matches window.get_states() response:
        {
            "actual_state": {...},
            "expected_states": [...]
        }
    """
    config_file = MOCK_STATES_DIR / f"{task_id}.json"
    
    if not config_file.exists():
        logger.debug(f"Mock states file not found: {config_file}")
        return None
    
    try:
        with open(config_file, 'r') as f:
            mock_data = json.load(f)
        
        # Validate structure
        if not isinstance(mock_data, dict):
            logger.error(f"Invalid mock states file {config_file}: root must be a dict")
            return None
        
        if "actual_state" not in mock_data:
            logger.error(f"Invalid mock states file {config_file}: missing 'actual_state' key")
            return None
        
        if "expected_states" not in mock_data:
            logger.error(f"Invalid mock states file {config_file}: missing 'expected_states' key")
            return None
        
        logger.info(f"✅ Loaded mock states from file: {config_file}")
        return mock_data
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error parsing JSON in mock states file {config_file}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error loading mock states from {config_file}: {e}")
        return None

