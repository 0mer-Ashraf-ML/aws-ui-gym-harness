"""State grader evaluates actual_state returned by window.get_states."""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from app.schemas.verification import AssertionOperator, StateGraderConfig

from .assertion_engine import AssertionEngine
from .types import AssertionResult, GradingResult


class StateGrader:
    """Apply declarative assertions to the actual state payload."""

    def __init__(
        self,
        assertion_engine: Optional[AssertionEngine] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.assertion_engine = assertion_engine or AssertionEngine(logger=logger)
        self.logger = logger or logging.getLogger(__name__)

    def grade(
        self,
        actual_state: Any,
        expected_states: Sequence[Any],
        config: StateGraderConfig,
    ) -> GradingResult:
        """Evaluate a collection of assertions against `actual_state`."""

        subject_candidates = self.assertion_engine.extract_values_by_path(
            actual_state, config.path_to_actual
        )
        subject = subject_candidates[0] if subject_candidates else None

        assertion_results: List[AssertionResult] = []
        detail_messages: List[str] = []
        all_passed = True

        for assertion in config.assertions:
            if assertion.path_to_actual:
                actual_values = self.assertion_engine.extract_values_by_path(
                    subject, assertion.path_to_actual
                )
                # For array operators, pass the full array instead of just the first element
                if self._is_array_operator(assertion.operator):
                    actual_value = actual_values  # Pass full array
                else:
                    actual_value = actual_values[0] if actual_values else None
            else:
                actual_value = subject

            expected_values = self.assertion_engine.resolve_expected_values(
                assertion, expected_states
            )
            result = self.assertion_engine.evaluate_assertion(
                assertion, actual_value, expected_values
            )
            assertion_results.append(result)

            if result.passed:
                detail_messages.append(
                    result.message or f"{assertion.operator} assertion passed"
                )
            else:
                all_passed = False
                message = result.message or f"{assertion.operator} assertion failed"
                detail_messages.append(message)

        return GradingResult(
            passed=all_passed,
            details=detail_messages,
            assertion_results=assertion_results,
        )

    @staticmethod
    def _is_array_operator(operator: AssertionOperator) -> bool:
        """Check if the operator expects an array as actual value."""
        array_operators = {
            AssertionOperator.ARRAY_LENGTH_MATCH,
            AssertionOperator.ARRAY_STRING_EQUALS,
            AssertionOperator.ARRAY_STRING_CONTAINS,
            AssertionOperator.ARRAY_STRING_NOT_CONTAINS,
            AssertionOperator.ARRAY_NUMERIC_MATCH,
            AssertionOperator.ARRAY_BOOL,
        }
        return operator in array_operators


__all__ = ["StateGrader"]
