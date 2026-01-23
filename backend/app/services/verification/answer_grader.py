"""Answer grader evaluates the model's final textual response."""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from app.schemas.verification import AssertionOperator, TextGraderConfig

from .assertion_engine import AssertionEngine
from .types import GradingResult


class AnswerGrader:
    """Apply textual assertions to the assistant's final response."""

    def __init__(
        self,
        assertion_engine: Optional[AssertionEngine] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.assertion_engine = assertion_engine or AssertionEngine(logger=logger)
        self.logger = logger or logging.getLogger(__name__)

    def grade(
        self,
        model_response: Any,
        expected_states: Sequence[Any],
        config: TextGraderConfig,
        response_context: Optional[Any] = None,
    ) -> GradingResult:
        """Evaluate assertions against the final assistant response."""

        subject = model_response
        assertion_results = []
        detail_messages = []
        all_passed = True

        for assertion in config.assertions:
            actual_value = subject
            if assertion.path_to_actual:
                target = response_context if response_context is not None else {}
                values = self.assertion_engine.extract_values_by_path(
                    target, assertion.path_to_actual
                )
                # For array operators, pass the full array instead of just the first element
                if self._is_array_operator(assertion.operator):
                    # If JSONPath returned a single array match, unwrap it once
                    if (
                        len(values) == 1
                        and isinstance(values[0], (list, tuple))
                        and not isinstance(values[0], (str, bytes))
                    ):
                        actual_value = values[0]
                    else:
                        actual_value = values
                else:
                    actual_value = values[0] if values else actual_value

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
                detail_messages.append(
                    result.message or f"{assertion.operator} assertion failed"
                )

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


__all__ = ["AnswerGrader"]
