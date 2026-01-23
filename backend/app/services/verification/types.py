"""Shared datatypes for verification services."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.verification import Assertion


@dataclass
class AssertionResult:
    """Outcome of evaluating a single assertion."""

    assertion: Assertion
    passed: bool
    actual: Any
    expected: List[Any]
    message: Optional[str] = None


@dataclass
class GradingResult:
    """Aggregated result returned by a grader."""

    passed: bool
    details: List[str] = field(default_factory=list)
    assertion_results: List[AssertionResult] = field(default_factory=list)


@dataclass
class GradingContext:
    """Contextual payload shared across graders."""

    task: Dict[str, Any]
    execution_results: Dict[str, Any]
    results_dir: Optional[str] = None


__all__ = ["AssertionResult", "GradingContext", "GradingResult"]
