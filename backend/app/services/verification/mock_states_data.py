"""Mock states data generators for GraderConfig verification (temporary for testing).

This module provides task-specific mock data generators that simulate window.get_states()
responses when gyms haven't implemented the function yet.

TODO: Remove this module when gyms implement window.get_states().
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Registry for task-specific mock data generators
_MOCK_DATA_REGISTRY: Dict[str, Callable[[List[Dict[str, Any]]], Dict[str, Any]]] = {}


def register_mock_data(
    task_id: str, generator_func: Callable[[List[Dict[str, Any]]], Dict[str, Any]]
) -> None:
    """Register a mock data generator for a specific task.
    
    Args:
        task_id: Task identifier (e.g., "ZEND-TICKET-SPAM-001")
        generator_func: Function that generates mock data given expected_state_functions
    """
    _MOCK_DATA_REGISTRY[task_id] = generator_func
    logger.debug(f"Registered mock data generator for task: {task_id}")


def get_mock_states_for_task(
    task_id: str, expected_state_functions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Retrieve mock states for a specific task.
    
    Args:
        task_id: Task identifier
        expected_state_functions: List of function calls for expected states
        
    Returns:
        Dictionary with 'actual_state' and 'expected_states' keys
    """
    if task_id not in _MOCK_DATA_REGISTRY:
        logger.warning(
            f"No mock data generator registered for task {task_id}. "
            "Returning empty structure."
        )
        return {
            "actual_state": {},
            "expected_states": [],
        }
    
    generator_func = _MOCK_DATA_REGISTRY[task_id]
    logger.info(
        f"Generating mock states for task {task_id} with {len(expected_state_functions)} function call(s)"
    )
    
    try:
        return generator_func(expected_state_functions)
    except Exception as e:
        logger.error(f"Error generating mock states for task {task_id}: {e}", exc_info=True)
        return {
            "actual_state": {},
            "expected_states": [],
        }


def clear_mock_data_registry() -> None:
    """Clear all registered mock data generators (useful for testing)."""
    _MOCK_DATA_REGISTRY.clear()
    logger.debug("Cleared mock data registry")


# ============================================================================
# Task-Specific Mock Data Generators
# ============================================================================


def _generate_zend_ticket_spam_001_mock(
    expected_state_functions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mock data generator for ZEND-TICKET-SPAM-001.
    
    Task: Open ticket #2, suspend user with phone +1 (702) 988-6613, mark ticket as spam.
    
    Returns mock data reflecting successful task completion:
    - Ticket #2 is marked as spam
    - User with phone +1 (702) 988-6613 is suspended
    """
    # Actual state reflects the completed task
    actual_state = {
        "tickets": [
            {
                "id": "2",
                "requester_phone": "+1 (702) 988-6613",
                "subject": "Test ticket for spam marking",
                "status": "open",
                "is_spam": True,  # Task completed: marked as spam
                "spam_reason": "marked as spam",
                "created_at": "2025-11-01T10:00:00Z",
            }
        ],
        "users": [
            {
                "user_id": "user_caller_702_988_6613",
                "phone": "+1 (702) 988-6613",
                "name": "Caller",
                "is_suspended": True,  # Task completed: user suspended
                "suspension_reason": "Uncooperative",
                "email": "caller7029886613@example.com",
            }
        ],
    }
    
    # Generate expected_states from expected_state_functions
    expected_states = []
    for func_call in expected_state_functions:
        func_name = func_call.get("function", "")
        func_args = func_call.get("args", {})
        
        if func_name == "get_ticket_by_id":
            ticket_id = func_args.get("ticket_id")
            expected_states.append(
                {
                    "ticket": {
                        "id": ticket_id,
                        "is_spam": True,
                        "spam_reason": "marked as spam",
                    }
                }
            )
        elif func_name == "get_user_by_phone":
            phone = func_args.get("phone")
            expected_states.append(
                {
                    "user": {
                        "phone": phone,
                        "is_suspended": True,
                        "suspension_reason": "Uncooperative",
                    }
                }
            )
        else:
            # Unknown function, generate empty expected state
            logger.warning(
                f"Unknown function '{func_name}' in expected_state_functions, "
                "generating empty expected state"
            )
            expected_states.append({})
    
    return {
        "actual_state": actual_state,
        "expected_states": expected_states,
    }


def _generate_zend_ticket_restore_001_mock(
    expected_state_functions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mock data generator for ZEND-TICKET-RESTORE-001.
    
    Task: Restore the deleted ticket with subject 'Unable to reset password via email'.
    
    Returns mock data reflecting successful task completion:
    - Ticket is restored (no longer deleted)
    """
    # Actual state reflects the restored ticket
    actual_state = {
        "tickets": [
            {
                "id": "1",
                "subject": "Unable to reset password via email",
                "status": "open",  # Restored and open
                "is_deleted": False,  # Task completed: ticket restored
                "deleted_at": None,
                "restored_at": "2025-11-01T10:00:00Z",
                "created_at": "2025-10-25T08:00:00Z",
            }
        ],
    }
    
    # Generate expected_states from expected_state_functions
    expected_states = []
    for func_call in expected_state_functions:
        func_name = func_call.get("function", "")
        func_args = func_call.get("args", {})
        
        if func_name == "get_ticket_by_subject":
            subject = func_args.get("subject")
            if subject == "Unable to reset password via email":
                expected_states.append(
                    {
                        "ticket": {
                            "subject": subject,
                            "is_deleted": False,
                            "status": "open",
                        }
                    }
                )
        elif func_name == "get_ticket_by_id":
            ticket_id = func_args.get("ticket_id")
            expected_states.append(
                {
                    "ticket": {
                        "id": ticket_id,
                        "is_deleted": False,
                        "status": "open",
                    }
                }
            )
        else:
            # Unknown function, generate empty expected state
            logger.warning(
                f"Unknown function '{func_name}' in expected_state_functions, "
                "generating empty expected state"
            )
            expected_states.append({})
    
    return {
        "actual_state": actual_state,
        "expected_states": expected_states,
    }


# Register mock data generators at module level
register_mock_data("ZEND-TICKET-SPAM-001", _generate_zend_ticket_spam_001_mock)
register_mock_data("ZEND-TICKET-RESTORE-001", _generate_zend_ticket_restore_001_mock)

__all__ = [
    "get_mock_states_for_task",
    "register_mock_data",
    "clear_mock_data_registry",
]

