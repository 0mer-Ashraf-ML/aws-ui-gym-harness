# Verifier script tuned for DeskZen Task 01
from typing import Any, Dict, List, Optional
import requests

TARGET_SUBJECT = "Unable to reset password via email"


def _safe_get(url: str, run_id: Optional[str] = None, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Helper that performs a GET request and returns the JSON list or [] on failure."""
    try:
        headers = {}
        if run_id:
            headers["X-Run-ID"] = run_id
        
        # Also add run_id as query param for compatibility
        if run_id and "?" in url:
            url = f"{url}&run_id={run_id}"
        elif run_id:
            url = f"{url}?run_id={run_id}"
        
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _get_active_tickets(base_url: str, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    url = base_url.removesuffix("/") + "/api/v1/tickets?is_deleted=false"
    return _safe_get(url, run_id=run_id)


def _get_deleted_tickets(base_url: str, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    url = base_url.removesuffix("/") + "/api/v1/tickets/deleted"
    return _safe_get(url, run_id=run_id)


def _find_ticket(tickets: List[Dict[str, Any]], subject: str) -> Optional[Dict[str, Any]]:
    for ticket in tickets:
        if ticket.get("subject") == subject:
            return ticket
    return None


def on_start(prompt: str, base_url: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Record whether the target ticket exists (and where) before the agent runs.
    Uses run_id to query the correct database clone for state isolation.
    """
    active_tickets = _get_active_tickets(base_url, run_id=run_id)
    deleted_tickets = _get_deleted_tickets(base_url, run_id=run_id)

    target_in_active = _find_ticket(active_tickets, TARGET_SUBJECT) is not None
    target_in_deleted = _find_ticket(deleted_tickets, TARGET_SUBJECT) is not None

    return {
        "active_count": len(active_tickets),
        "deleted_count": len(deleted_tickets),
        "target_in_active": target_in_active,
        "target_in_deleted": target_in_deleted,
        "run_id": run_id,  # Store run_id for reference
    }


def on_end(prompt: str, base_url: str, verifier_on_start_data: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify that the deleted ticket has been restored.
    Success criteria:
      1. The ticket exists in the active ticket list.
      2. The ticket no longer appears in the deleted ticket list.
    Uses run_id to query the correct database clone for state isolation.
    """
    # Use run_id from verifier_on_start_data if not provided directly
    if not run_id:
        run_id = verifier_on_start_data.get("run_id")
    
    active_tickets = _get_active_tickets(base_url, run_id=run_id)
    deleted_tickets = _get_deleted_tickets(base_url, run_id=run_id)

    target_in_active = _find_ticket(active_tickets, TARGET_SUBJECT) is not None
    target_in_deleted = _find_ticket(deleted_tickets, TARGET_SUBJECT) is not None

    passed = target_in_active and not target_in_deleted

    return {
        "result": "passed" if passed else "failed",
        "details": {
            "target_in_active": target_in_active,
            "target_in_deleted": target_in_deleted,
            "active_count_before": verifier_on_start_data.get("active_count"),
            "deleted_count_before": verifier_on_start_data.get("deleted_count"),
            "active_count_after": len(active_tickets),
            "deleted_count_after": len(deleted_tickets),
            "run_id": run_id,  # Include run_id in details for debugging
        },
    }