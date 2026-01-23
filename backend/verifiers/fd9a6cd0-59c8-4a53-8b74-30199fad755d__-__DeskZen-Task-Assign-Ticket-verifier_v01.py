# Verifier script for DeskZen Ticket Assignment Task
# Task Identifier: DESKZEN-ASSIGN-TICKET-TO-AGENT-001
# Verifies that a ticket has been assigned to a specific user
from typing import Any, Dict, List, Optional
import time
import requests

# Target ticket and assignee
TARGET_TICKET_SUBJECT = "SSO integration setup assistance"
TARGET_ASSIGNEE_NAME = "Sarah Johnson"
EXPECTED_ASSIGNEE_ID = "28762216189000"  # Sarah Johnson's user ID from fixtures


def _safe_get(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Helper that performs a GET request and returns the JSON list or [] on failure."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _safe_get_single(url: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """Helper that performs a GET request and returns the JSON object or None on failure."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def _get_active_tickets(base_url: str) -> List[Dict[str, Any]]:
    """Get all active (non-deleted) tickets."""
    return _safe_get(base_url.removesuffix("/") + "/api/v1/tickets?is_deleted=false")


def _find_ticket_by_subject(tickets: List[Dict[str, Any]], subject: str) -> Optional[Dict[str, Any]]:
    """Find a ticket by its subject."""
    for ticket in tickets:
        if ticket.get("subject") == subject:
            return ticket
    return None


def _get_ticket_detail(base_url: str, ticket_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed ticket information including assignee."""
    return _safe_get_single(base_url.removesuffix("/") + f"/api/v1/tickets/{ticket_id}")


def _get_user_by_name(base_url: str, name: str) -> Optional[Dict[str, Any]]:
    """Search for a user by name."""
    try:
        # Use search endpoint to find user by name
        response = requests.get(
            base_url.removesuffix("/") + "/api/v1/search/users",
            params={"q": name},
            timeout=10.0
        )
        response.raise_for_status()
        users = response.json()
        if isinstance(users, list):
            # Find exact match by name
            for user in users:
                if user.get("name") == name:
                    return user
        return None
    except Exception:
        return None


def _normalize_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def on_start(prompt: str, base_url: str) -> Dict[str, Any]:
    """
    Record the initial state before the agent runs:
    - Whether the target ticket exists
    - Current assignee of the ticket (if any)
    - Whether the target assignee user exists
    """
    active_tickets = _get_active_tickets(base_url)
    target_ticket = _find_ticket_by_subject(active_tickets, TARGET_TICKET_SUBJECT)
    
    ticket_id = None
    current_assignee_id = None
    current_assignee_name = None
    
    ticket_detail = None
    if target_ticket:
        ticket_id = target_ticket.get("id")
        ticket_detail = _get_ticket_detail(base_url, str(ticket_id))
        if ticket_detail:
            assignee = ticket_detail.get("assignee")
            if assignee and assignee.get("user"):
                current_assignee_id = _normalize_id(assignee["user"].get("id"))
                current_assignee_name = assignee["user"].get("name")
    
    # Verify target assignee exists
    target_assignee = _get_user_by_name(base_url, TARGET_ASSIGNEE_NAME)
    assignee_exists = target_assignee is not None
    assignee_id = (
        str(target_assignee.get("id")) if target_assignee and target_assignee.get("id") is not None else None
    )
    
    return {
        "ticket_exists": target_ticket is not None,
        "ticket_id": ticket_id,
        "current_assignee_id": current_assignee_id,
        "current_assignee_name": current_assignee_name,
        "initial_priority": ticket_detail.get("priority") if ticket_detail else None,
        "initial_status": ticket_detail.get("status") if ticket_detail else None,
        "assignee_exists": assignee_exists,
        "assignee_id": assignee_id,
        "expected_assignee_id": EXPECTED_ASSIGNEE_ID,
        "timestamp": time.time(),
    }


def on_end(prompt: str, base_url: str, verifier_on_start_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that the ticket has been assigned to the target user.
    Success criteria:
      1. The ticket still exists (not deleted)
      2. The ticket is now assigned to the target user (Sarah Johnson)
      3. The assignee ID matches the expected assignee ID
    """
    ticket_id = verifier_on_start_data.get("ticket_id")
    expected_raw_id = verifier_on_start_data.get("expected_assignee_id")
    expected_assignee_id = str(expected_raw_id) if expected_raw_id is not None else None
    
    if not ticket_id:
        return {
            "result": "failed",
            "details": {
                "error": "Ticket not found in initial state",
                "ticket_subject": TARGET_TICKET_SUBJECT,
            },
        }
    
    # Get current ticket state
    ticket_detail = _get_ticket_detail(base_url, str(ticket_id))
    
    if not ticket_detail:
        return {
            "result": "failed",
            "details": {
                "error": "Ticket no longer exists or cannot be retrieved",
                "ticket_id": ticket_id,
            },
        }
    
    # Check if ticket is deleted
    if ticket_detail.get("is_deleted", False):
        return {
            "result": "failed",
            "details": {
                "error": "Ticket has been deleted",
                "ticket_id": ticket_id,
            },
        }
    
    # Check assignee
    assignee = ticket_detail.get("assignee")
    assignee_user = assignee.get("user") if assignee else None
    
    if not assignee_user:
        return {
            "result": "failed",
            "details": {
                "error": "Ticket is not assigned to any user",
                "ticket_id": ticket_id,
                "ticket_subject": TARGET_TICKET_SUBJECT,
                "previous_assignee": verifier_on_start_data.get("current_assignee_name"),
            },
        }
    
    raw_assignee_id = assignee_user.get("id")
    current_assignee_id = _normalize_id(raw_assignee_id)
    current_assignee_name = assignee_user.get("name")
    
    initial_assignee_id = _normalize_id(
        verifier_on_start_data.get("current_assignee_id")
        or verifier_on_start_data.get("assignee_id")
    )
    initial_assignee_name = verifier_on_start_data.get("current_assignee_name")
    state_already_correct = (
        initial_assignee_id == expected_assignee_id
        and initial_assignee_name == TARGET_ASSIGNEE_NAME
    )

    # Verify assignment
    assignment_correct = (
        current_assignee_id == expected_assignee_id and
        current_assignee_name == TARGET_ASSIGNEE_NAME
    )
    
    state_changed = current_assignee_id != initial_assignee_id
    model_attempted = state_changed or not state_already_correct

    if state_already_correct:
        return {
            "result": "failed",
            "model_attempted": False,
            "model_succeeded": False,
            "state_already_correct": True,
            "verification_issue": False,
            "details": {
                "ticket_id": ticket_id,
                "ticket_subject": TARGET_TICKET_SUBJECT,
                "error": "Ticket was already assigned to the target agent before the iteration started.",
                "current_assignee_id": current_assignee_id,
                "current_assignee_name": current_assignee_name,
                "expected_assignee_id": expected_assignee_id,
                "previous_assignee_id": initial_assignee_id,
                "previous_assignee_name": initial_assignee_name,
            },
        }

    passed = assignment_correct
    model_succeeded = passed and model_attempted
    
    return {
        "result": "passed" if passed else "failed",
        "model_attempted": model_attempted,
        "model_succeeded": model_succeeded,
        "state_already_correct": state_already_correct,
        "verification_issue": False,
        "details": {
            "ticket_id": ticket_id,
            "ticket_subject": TARGET_TICKET_SUBJECT,
            "current_assignee_id": current_assignee_id,
            "current_assignee_name": current_assignee_name,
            "expected_assignee_id": expected_assignee_id,
            "expected_assignee_name": TARGET_ASSIGNEE_NAME,
            "assignment_correct": assignment_correct,
            "previous_assignee_id": initial_assignee_id,
            "previous_assignee_name": initial_assignee_name,
            "state_changed": state_changed,
        },
    }

