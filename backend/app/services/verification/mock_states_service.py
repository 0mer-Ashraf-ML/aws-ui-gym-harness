"""Mock states service for GraderConfig verification (temporary for testing).

This service provides mock data by loading from JSON files.
Can be easily removed when gyms implement window.get_states().

TODO: Remove this module when gyms implement window.get_states().
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.mock_states_loader import load_mock_states_from_file

logger = logging.getLogger(__name__)


def get_mock_states(
    task_id: Optional[str],
    expected_state_functions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Get mock states for a task (loaded from JSON files).
    
    This loads mock data from JSON files matching the exact structure
    that the gym's window.get_states() will return.
    
    Args:
        task_id: Task identifier (e.g., "ZEND-TICKET-SPAM-001")
        expected_state_functions: List of function calls for expected states
            (kept for API compatibility, but not used since JSON files are static)
    
    Returns:
        {
            "actual_state": {...},
            "expected_states": [...]
        }
        
    Example:
        >>> get_mock_states(
        ...     task_id="ZEND-TICKET-SPAM-001",
        ...     expected_state_functions=[
        ...         {"function": "get_ticket_by_id", "args": {"ticket_id": "2"}}
        ...     ]
        ... )
        {
            "actual_state": {"tickets": [...], "users": [...]},
            "expected_states": [{"ticket": {"id": "2", "is_spam": True, ...}}]
        }
    """
    if not task_id:
        logger.warning("No task_id provided, returning empty mock states")
        return {
            "actual_state": {},
            "expected_states": [],
        }
    
    logger.info(
        f"Loading mock states from JSON file for task {task_id}, "
        f"functions: {len(expected_state_functions)}"
    )
    
    # Load from JSON file
    mock_data = load_mock_states_from_file(task_id)
    
    if mock_data is None:
        logger.warning(
            f"No mock states JSON file found for task {task_id}. "
            "Returning empty structure."
        )
        return {
            "actual_state": {},
            "expected_states": [],
        }
    
    return mock_data


__all__ = ["get_mock_states"]

