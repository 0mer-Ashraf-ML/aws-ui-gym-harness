"""URL grader validates the final navigation state."""

from __future__ import annotations

import logging
from typing import Optional

from app.schemas.verification import TextGraderConfig

from .assertion_engine import AssertionEngine
from .types import GradingResult


class UrlGrader:
    """Placeholder for URL-based assertions."""

    def __init__(
        self,
        assertion_engine: Optional[AssertionEngine] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.assertion_engine = assertion_engine or AssertionEngine(logger=logger)
        self.logger = logger or logging.getLogger(__name__)

    def grade(self, final_url: str, config: TextGraderConfig) -> GradingResult:
        """Evaluate URL assertions using the shared assertion engine."""

        assertion_results = []
        detail_messages = []
        all_passed = True

        for assertion in config.assertions:
            expected_values = self.assertion_engine.resolve_expected_values(assertion, [])
            result = self.assertion_engine.evaluate_assertion(
                assertion, final_url, expected_values
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


__all__ = ["UrlGrader"]
