"""Helper utilities for the advanced agent."""

from __future__ import annotations

from typing import List, Set, Tuple


def update_requirement_progress(
    all_requirements: List[str],
    completed_set: Set[str],
    completion_order: List[str],
    step_completed: List[str],
    step_remaining: List[str],
) -> Tuple[Set[str], List[str], List[str], List[str]]:
    """Return updated requirement bookkeeping.

    Args:
        all_requirements: Canonical ordered list of requirements (may be empty).
        completed_set: Requirements already marked completed.
        completion_order: Ordered list of completed requirements.
        step_completed: Requirements newly reported as completed this step.
        step_remaining: Requirements still reported as missing.

    Returns:
        Tuple of (updated completed set, updated completion order, cumulative completed
        list, normalized remaining list).
    """

    merged_completed: Set[str] = set(completed_set or set())
    ordered_completed: List[str] = list(completion_order or [])

    for requirement in step_completed or []:
        if requirement and requirement not in merged_completed:
            merged_completed.add(requirement)
            ordered_completed.append(requirement)

    if all_requirements:
        normalized_remaining = [req for req in all_requirements if req not in merged_completed]
        cumulative_completed = [req for req in all_requirements if req in merged_completed]
    else:
        normalized_remaining = list(step_remaining or [])
        cumulative_completed = list(ordered_completed)

    return merged_completed, ordered_completed, cumulative_completed, normalized_remaining
