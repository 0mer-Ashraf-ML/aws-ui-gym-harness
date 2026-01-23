"""Verifier script for DeskZen API escalation task.
Task Identifier: DESKZEN-ESCALATE-API-RATE-LIMIT-001
"""
from typing import Any, Dict, List, Optional
import time
import requests

TARGET_TICKET_SUBJECT = "API rate limiting issues"
TARGET_ASSIGNEE_NAME = "Emily Rodriguez"
EXPECTED_ASSIGNEE_ID = "28762216189002"
EXPECTED_PRIORITY = "HIGH"
EXPECTED_STATUS = "PENDING"
REQUIRED_TAG = "api_hotfix"


def _safe_get(url: str, timeout: float = 10.0):
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _get_active_tickets(base_url: str) -> List[Dict[str, Any]]:
    data = _safe_get(base_url.removesuffix("/") + "/api/v1/tickets?is_deleted=false")
    return data if isinstance(data, list) else []


def _find_ticket_by_subject(tickets: List[Dict[str, Any]], subject: str) -> Optional[Dict[str, Any]]:
    for ticket in tickets:
        if ticket.get("subject") == subject:
            return ticket
    return None


def _get_ticket_detail(base_url: str, ticket_id: str) -> Optional[Dict[str, Any]]:
    return _safe_get(base_url.removesuffix("/") + f"/api/v1/tickets/{ticket_id}")


def _get_user_by_name(base_url: str, name: str) -> Optional[Dict[str, Any]]:
    data = _safe_get(
        base_url.removesuffix("/") + "/api/v1/search/users",
        timeout=10.0,
    )
    if isinstance(data, list):
        for user in data:
            if user.get("name") == name:
                return user
    return None


def _normalize_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _normalize_tag_set(tags: Optional[List[str]]) -> set:
    if not tags:
        return set()
    return {str(tag).strip().lower() for tag in tags}


def on_start(prompt: str, base_url: str) -> Dict[str, Any]:
    tickets = _get_active_tickets(base_url)
    target_ticket = _find_ticket_by_subject(tickets, TARGET_TICKET_SUBJECT)

    ticket_id = None
    detail = None
    initial_assignee_id = None
    initial_assignee_name = None

    if target_ticket:
        ticket_id = target_ticket.get("id")
        detail = _get_ticket_detail(base_url, str(ticket_id))
        if detail and detail.get("assignee", {}).get("user"):
            user = detail["assignee"]["user"]
            initial_assignee_id = _normalize_id(user.get("id"))
            initial_assignee_name = user.get("name")

    assignee_record = _get_user_by_name(base_url, TARGET_ASSIGNEE_NAME)
    assignee_exists = assignee_record is not None

    return {
        "ticket_exists": target_ticket is not None,
        "ticket_id": ticket_id,
        "initial_assignee_id": initial_assignee_id,
        "initial_assignee_name": initial_assignee_name,
        "initial_priority": detail.get("priority") if detail else None,
        "initial_status": detail.get("status") if detail else None,
        "initial_tags": detail.get("tags") if detail else None,
        "assignee_exists": assignee_exists,
        "expected_assignee_id": EXPECTED_ASSIGNEE_ID,
        "timestamp": time.time(),
    }


def on_end(prompt: str, base_url: str, verifier_on_start_data: Dict[str, Any]) -> Dict[str, Any]:
    ticket_id = verifier_on_start_data.get("ticket_id")
    expected_id = _normalize_id(verifier_on_start_data.get("expected_assignee_id"))

    if not ticket_id:
        return {
            "result": "failed",
            "details": {"error": "Ticket not found in initial state", "ticket_subject": TARGET_TICKET_SUBJECT},
        }

    detail = _get_ticket_detail(base_url, str(ticket_id))
    if not detail:
        return {
            "result": "failed",
            "details": {"error": "Ticket could not be retrieved", "ticket_id": ticket_id},
        }
    if detail.get("is_deleted"):
        return {
            "result": "failed",
            "details": {"error": "Ticket was deleted", "ticket_id": ticket_id},
        }

    assignee = detail.get("assignee", {}).get("user")
    current_assignee_id = _normalize_id(assignee.get("id")) if assignee else None
    current_assignee_name = assignee.get("name") if assignee else None

    current_priority = str(detail.get("priority") or "").upper()
    current_status = str(detail.get("status") or "").upper()
    current_tags = _normalize_tag_set(detail.get("tags"))

    expected_priority = EXPECTED_PRIORITY.upper()
    expected_status = EXPECTED_STATUS.upper()
    has_tag = REQUIRED_TAG.lower() in current_tags

    priority_ok = current_priority == expected_priority
    status_ok = current_status == expected_status
    assignee_ok = current_assignee_id == expected_id and current_assignee_name == TARGET_ASSIGNEE_NAME
    tags_ok = has_tag

    initial_assignee_id = verifier_on_start_data.get("initial_assignee_id")
    initial_priority = str(verifier_on_start_data.get("initial_priority") or "").upper()
    initial_status = str(verifier_on_start_data.get("initial_status") or "").upper()
    initial_tags = _normalize_tag_set(verifier_on_start_data.get("initial_tags"))

    state_already_correct = (
        initial_assignee_id == expected_id
        and initial_priority == expected_priority
        and initial_status == expected_status
        and REQUIRED_TAG.lower() in initial_tags
    )

    state_changed = (
        current_assignee_id != initial_assignee_id
        or current_priority != initial_priority
        or current_status != initial_status
        or REQUIRED_TAG.lower() not in initial_tags
    )

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
                "error": "Ticket already satisfied all requirements before execution.",
                "current_assignee_id": current_assignee_id,
                "current_assignee_name": current_assignee_name,
                "current_priority": current_priority,
                "current_status": current_status,
                "current_tags": sorted(current_tags),
                "initial_assignee_id": initial_assignee_id,
                "initial_priority": initial_priority,
                "initial_status": initial_status,
                "initial_tags": sorted(initial_tags),
            },
        }

    passed = priority_ok and status_ok and assignee_ok and tags_ok
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
            "assignee_ok": assignee_ok,
            "priority_ok": priority_ok,
            "status_ok": status_ok,
            "tag_ok": tags_ok,
            "current_assignee_id": current_assignee_id,
            "current_assignee_name": current_assignee_name,
            "current_priority": current_priority,
            "current_status": current_status,
            "current_tags": sorted(current_tags),
            "expected_assignee_id": expected_id,
            "expected_priority": expected_priority,
            "expected_status": expected_status,
            "required_tag": REQUIRED_TAG,
            "initial_assignee_id": initial_assignee_id,
            "initial_priority": initial_priority,
            "initial_status": initial_status,
            "initial_tags": sorted(initial_tags),
            "state_changed": state_changed,
        },
    }
