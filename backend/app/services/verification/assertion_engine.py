"""Assertion evaluation utilities for GraderConfig-based verification."""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence


class ConfigurationError(Exception):
    """Raised when there is a configuration error in the grader config.
    
    This error should crash the verification immediately rather than
    being treated as a test failure.
    
    Note: This inherits from Exception but should be explicitly re-raised
    in all except blocks to ensure it propagates and crashes the verification.
    """
    pass

try:  # jsonpath_ng is relatively heavy; cache import errors for graceful degradation
    from jsonpath_ng.ext import parse as jsonpath_parse
except ImportError as exc:  # pragma: no cover - handled in tests via dependency injection
    jsonpath_parse = None  # type: ignore[assignment]
    _JSONPATH_IMPORT_ERROR = exc
else:
    _JSONPATH_IMPORT_ERROR = None

from app.schemas.verification import Assertion, AssertionOperator

from .types import AssertionResult


class AssertionEngine:
    """Core evaluation logic covering all supported assertion operators."""

    _COMPARISON_PATTERN = re.compile(r"^(==|!=|>=|<=|>|<)?\s*(.+)$")

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self._jsonpath_cache = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_values_by_path(self, data: Any, jsonpath: Optional[str]) -> List[Any]:
        """Return values matching the provided JSONPath expression.

        If no path is supplied, the data itself is wrapped in a list.
        
        Raises:
            RuntimeError: If jsonpath-ng is not available or path evaluation fails.
        """
        if jsonpath is None or jsonpath == "":
            return [data]

        if jsonpath_parse is None:
            raise RuntimeError(
                "jsonpath-ng is required to evaluate JSONPath expressions."
            ) from _JSONPATH_IMPORT_ERROR

        try:
            expr = self._jsonpath_cache.get(jsonpath)
            if expr is None:
                expr = jsonpath_parse(jsonpath)
                self._jsonpath_cache[jsonpath] = expr
            matches = [match.value for match in expr.find(data)]
            return matches
        except Exception as exc:
            # Provide detailed context about what went wrong
            data_type = type(data).__name__
            data_keys = list(data.keys()) if isinstance(data, dict) else "N/A (not a dict)"
            data_length = len(data) if isinstance(data, (list, tuple, dict)) else "N/A"
            
            error_msg = (
                f"JSONPath extraction failed for path '{jsonpath}'.\n"
                f"Data type: {data_type}\n"
                f"Data keys: {data_keys}\n"
                f"Data length: {data_length}\n"
                f"Original error: {type(exc).__name__}: {exc}\n\n"
                f"Common causes:\n"
                f"  - Using array index (e.g., $[0]) on a dictionary\n"
                f"  - Using dictionary key (e.g., $.key) on a list\n"
                f"  - Path references a key that doesn't exist in the structure"
            )
            self.logger.error(error_msg)
            raise ConfigurationError(error_msg) from exc

    def resolve_expected_values(
        self,
        assertion: Assertion,
        expected_states: Sequence[Any],
    ) -> List[Any]:
        """Combine literal expected values with values extracted from expected states.
        
        Raises:
            Exception: If path extraction fails due to configuration errors.
        """
        values: List[Any] = []

        if assertion.expected is not None:
            values.extend(assertion.expected)

        if assertion.paths_to_expected:
            for path_idx, path in enumerate(assertion.paths_to_expected):
                for state_idx, state in enumerate(expected_states):
                    try:
                        extracted = self.extract_values_by_path(state, path)
                        values.extend(extracted)
                    except ConfigurationError:
                        # Re-raise configuration errors as-is
                        raise
                    except Exception as exc:
                        # Log detailed context before re-raising as ConfigurationError
                        state_type = type(state).__name__
                        state_preview = str(state)[:200] if state else "None"
                        error_msg = (
                            f"Failed to extract expected values using path '{path}' "
                            f"(paths_to_expected[{path_idx}]) from expected_states[{state_idx}].\n"
                            f"State type: {state_type}\n"
                            f"State preview: {state_preview}\n"
                            f"Error: {exc}"
                        )
                        self.logger.error(error_msg)
                        raise ConfigurationError(error_msg) from exc

        return values

    def evaluate_assertion(
        self,
        assertion: Assertion,
        actual_value: Any,
        expected_values: Sequence[Any],
    ) -> AssertionResult:
        """Evaluate a single assertion, returning structured results.
        
        Note: This method no longer catches exceptions. Any errors during assertion
        evaluation will propagate to the caller, ensuring configuration errors
        cause immediate failures rather than false positives/negatives.
        """
        operator = assertion.operator
        handler = self._get_handler(operator)

        passed, message = handler(actual_value, expected_values)

        return AssertionResult(
            assertion=assertion,
            passed=passed,
            actual=actual_value,
            expected=list(expected_values),
            message=message,
        )

    # ------------------------------------------------------------------
    # Handler registration & helpers
    # ------------------------------------------------------------------

    def _get_handler(self, operator: AssertionOperator):
        mapping = {
            AssertionOperator.STRING_EQUALS: self._handle_string_equals,
            AssertionOperator.STRING_CONTAINS: self._handle_string_contains,
            AssertionOperator.STRING_NOT_CONTAINS: self._handle_string_not_contains,
            AssertionOperator.STRING_FUZZY_MATCH: self._handle_string_fuzzy,
            AssertionOperator.JSON_EQUALS: self._handle_json_equals,
            AssertionOperator.JSON_CONTAINS: self._handle_json_contains,
            AssertionOperator.JSON_PART_OF: self._handle_json_part_of,
            AssertionOperator.NUMERIC_MATCH: self._handle_numeric_match,
            AssertionOperator.BOOL: self._handle_bool,
            AssertionOperator.ARRAY_LENGTH_MATCH: self._handle_array_length,
            AssertionOperator.ARRAY_STRING_EQUALS: self._handle_array_string_equals,
            AssertionOperator.ARRAY_STRING_CONTAINS: self._handle_array_string_contains,
            AssertionOperator.ARRAY_STRING_NOT_CONTAINS: self._handle_array_string_not_contains,
            AssertionOperator.ARRAY_NUMERIC_MATCH: self._handle_array_numeric_match,
            AssertionOperator.ARRAY_BOOL: self._handle_array_bool,
            AssertionOperator.DATETIME_MATCH: self._handle_datetime_match,
            AssertionOperator.IMAGE_FUZZY_MATCH: self._handle_image_fuzzy_match,
            AssertionOperator.IMAGE_CONTENT_LLM_MATCH: self._handle_image_content_llm_match,
        }
        if operator not in mapping:
            raise ValueError(f"Unsupported operator: {operator}")
        return mapping[operator]

    @staticmethod
    def _ensure_sequence(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        return [value]

    @classmethod
    def _parse_comparison(cls, expression: Any):
        if isinstance(expression, (int, float)):
            return "==", float(expression)
        if not isinstance(expression, str):
            raise ValueError(f"Unsupported comparator type: {type(expression)}")

        match = cls._COMPARISON_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(f"Invalid comparator expression: {expression}")
        operator, rhs = match.groups()
        operator = operator or "=="
        rhs = rhs.strip()
        try:
            return operator, float(rhs)
        except ValueError as exc:
            raise ValueError(
                f"Comparator '{expression}' is not numeric and cannot be parsed"
            ) from exc

    @staticmethod
    def _parse_datetime(expression: str) -> datetime:
        # Prefer ISO parsing via datetime.fromisoformat with graceful fallback
        expression = expression.strip()
        try:
            return datetime.fromisoformat(expression.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO datetime string: {expression}") from exc

    @staticmethod
    def _coerce_to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return bool(value)

    @staticmethod
    def _normalise_text(value: Any) -> str:
        return str(value or "").strip()

    # ------------------------------------------------------------------
    # Individual handlers
    # ------------------------------------------------------------------

    def _handle_string_equals(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_text = self._normalise_text(actual)
        candidates = [self._normalise_text(v) for v in expected_values] or [""]
        passed = actual_text in candidates
        message = None if passed else f"'{actual_text}' not in expected {candidates}"
        return passed, message

    def _handle_string_contains(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_text = self._normalise_text(actual).lower()
        if not actual_text:
            return False, "Actual value is empty"
        substrings = [self._normalise_text(v).lower() for v in expected_values if v is not None]
        missing = [sub for sub in substrings if sub not in actual_text]
        passed = len(missing) == 0
        message = None if passed else f"Missing substrings from '{actual}': {missing}"
        return passed, message

    def _handle_string_not_contains(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_text = self._normalise_text(actual).lower()
        substrings = [self._normalise_text(v).lower() for v in expected_values if v is not None]
        offending = [sub for sub in substrings if sub and sub in actual_text]
        passed = len(offending) == 0
        message = None if passed else f"Unexpected substrings present: {offending}"
        return passed, message

    def _handle_string_fuzzy(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_text = self._normalise_text(actual)
        threshold = 0.85
        for candidate in expected_values:
            candidate_text = self._normalise_text(candidate)
            ratio = SequenceMatcher(None, actual_text.lower(), candidate_text.lower()).ratio()
            if ratio >= threshold:
                return True, None
        return False, f"No fuzzy matches >= {threshold} for '{actual_text}'"

    def _handle_json_equals(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        reference = expected_values[0] if expected_values else None
        passed = actual == reference
        message = None
        if not passed:
            message = f"JSON mismatch. Actual: {json.dumps(actual, default=str)} vs Expected: {json.dumps(reference, default=str)}"
        return passed, message

    def _handle_json_contains(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        expected_objects = [self._ensure_mapping(v) for v in expected_values]
        
        # Handle lists: check if any element in the list contains the expected object
        if isinstance(actual, (list, tuple)) and not isinstance(actual, (str, bytes)):
            for expected in expected_objects:
                found = False
                for item in actual:
                    try:
                        item_mapping = self._ensure_mapping(item)
                        if self._mapping_contains(item_mapping, expected):
                            found = True
                            break
                    except ValueError:
                        # Item is not a mapping, skip
                        continue
                if not found:
                    return False, f"Actual JSON array does not contain expected subset: {expected}"
            return True, None
        
        # Handle dicts (original behavior)
        try:
            actual_mapping = self._ensure_mapping(actual)
        except ValueError as e:
            return False, str(e)
        
        for expected in expected_objects:
            if not self._mapping_contains(actual_mapping, expected):
                return False, f"Actual JSON does not contain expected subset: {expected}"
        return True, None

    def _handle_json_part_of(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_mapping = self._ensure_mapping(actual)
        expected_objects = [self._ensure_mapping(v) for v in expected_values]
        for expected in expected_objects:
            if not self._mapping_contains(expected, actual_mapping):
                return False, f"Actual JSON is not fully contained within expected: {expected}"
        return True, None

    def _handle_numeric_match(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        try:
            actual_number = float(actual)
        except (TypeError, ValueError):
            return False, f"Actual value '{actual}' is not numeric"

        comparators = [self._parse_comparison(expr) for expr in (expected_values or [actual_number])]
        for operator, target in comparators:
            if not self._compare_numeric(actual_number, operator, target):
                return False, f"Comparator '{operator} {target}' failed for value {actual_number}"
        return True, None

    def _handle_bool(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        actual_bool = self._coerce_to_bool(actual)
        if expected_values:
            expected_bool = self._coerce_to_bool(expected_values[0])
            passed = actual_bool == expected_bool
            return passed, None if passed else f"Expected {expected_bool} but received {actual_bool}"
        return actual_bool, None if actual_bool else "Expected truthy value"

    def _handle_array_length(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        length = len(actual)
        comparators = [self._parse_comparison(expr) for expr in expected_values]
        for operator, target in comparators:
            if not self._compare_numeric(length, operator, target):
                return False, f"Array length {length} failed comparator '{operator} {target}'"
        return True, None

    def _handle_array_string_equals(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        actual_strings = [self._normalise_text(item) for item in actual]
        expected_strings = [self._normalise_text(item) for item in expected_values]
        if not expected_strings:
            return False, "No expected values provided"
        
        # Always use set comparison - order doesn't matter
        passed = set(actual_strings) == set(expected_strings)
        message = None if passed else f"Array string equality failed. Actual={actual_strings}, Expected={expected_strings}"
        return passed, message

    def _handle_array_string_contains(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        haystack = " ".join(self._normalise_text(item).lower() for item in actual)
        substrings = [self._normalise_text(item).lower() for item in expected_values]
        passed = all(sub in haystack for sub in substrings)
        message = None if passed else f"Missing expected substrings in array contents: {substrings}"
        return passed, message

    def _handle_array_string_not_contains(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        haystack = " ".join(self._normalise_text(item).lower() for item in actual)
        substrings = [self._normalise_text(item).lower() for item in expected_values if item is not None]
        offending = [sub for sub in substrings if sub and sub in haystack]
        passed = len(offending) == 0
        message = None if passed else f"Unexpected substrings found in array contents: {offending}"
        return passed, message

    def _handle_array_numeric_match(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        comparators = [self._parse_comparison(expr) for expr in expected_values]
        failures = []
        for idx, item in enumerate(actual):
            try:
                numeric = float(item)
            except (TypeError, ValueError):
                return False, f"Array element at index {idx} is not numeric"
            for operator, target in comparators:
                if not self._compare_numeric(numeric, operator, target):
                    failures.append((idx, numeric, operator, target))
        if failures:
            readable = ", ".join(
                f"idx={idx} value={value} !{op} {target}" for idx, value, op, target in failures
            )
            return False, readable
        return True, None

    def _handle_array_bool(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
            return False, "Actual value is not an array"
        actual_bools = [self._coerce_to_bool(value) for value in actual]
        if expected_values:
            expected_bools = [self._coerce_to_bool(value) for value in expected_values]
            if len(expected_bools) == len(actual_bools):
                passed = all(a == e for a, e in zip(actual_bools, expected_bools))
                message = None if passed else f"Boolean array mismatch: {actual_bools} vs {expected_bools}"
                return passed, message
            benchmark = expected_bools[0]
            passed = all(value == benchmark for value in actual_bools)
            return passed, None if passed else f"Expected all booleans to be {benchmark}"
        passed = all(actual_bools)
        return passed, None if passed else f"Array contains falsy values: {actual_bools}"

    def _handle_datetime_match(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        if not isinstance(actual, str):
            return False, f"Actual datetime must be string, received {type(actual)}"
        actual_dt = self._parse_datetime(actual)
        comparators = []
        for expr in expected_values:
            if isinstance(expr, str):
                match = self._COMPARISON_PATTERN.match(expr.strip())
                if not match:
                    raise ValueError(f"Invalid datetime comparator: {expr}")
                operator, rhs = match.groups()
                operator = operator or "=="
                rhs_dt = self._parse_datetime(rhs)
                comparators.append((operator, rhs_dt))
            elif isinstance(expr, datetime):
                comparators.append(("==", expr))
            else:
                raise ValueError(f"Unsupported datetime comparator: {expr}")
        for operator, target in comparators:
            if not self._compare_datetime(actual_dt, operator, target):
                return False, f"Comparator '{operator} {target.isoformat()}' failed for {actual_dt.isoformat()}"
        return True, None

    def _handle_image_fuzzy_match(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        """Compare images using perceptual hashing.
        
        Args:
            actual: Image URL (string) or base64-encoded image
            expected_values: List of expected image URLs or base64-encoded images
            
        Returns:
            Tuple of (passed: bool, message: Optional[str])
        """
        try:
            import imagehash
            from PIL import Image
            import requests
            from io import BytesIO
            import base64
            import os
        except ImportError as e:
            return False, f"Required libraries not available: {e}. Install with: pip install imagehash pillow"
        
        if not expected_values:
            return False, "No expected images provided for comparison"
        
        # Load actual image
        try:
            actual_image = self._load_image(actual)
            if actual_image is None:
                return False, f"Failed to load actual image from: {actual[:100] if isinstance(actual, str) else 'provided data'}"
            
            actual_hash = imagehash.average_hash(actual_image)
        except Exception as e:
            return False, f"Failed to process actual image: {str(e)}"
        
        # Compare against each expected image
        best_match_distance = float('inf')
        best_match_url = None
        
        for expected_url in expected_values:
            try:
                expected_image = self._load_image(expected_url)
                if expected_image is None:
                    continue  # Skip invalid images
                
                expected_hash = imagehash.average_hash(expected_image)
                distance = actual_hash - expected_hash  # Hamming distance
                
                if distance < best_match_distance:
                    best_match_distance = distance
                    best_match_url = expected_url
                
                # Threshold: images with distance <= 5 are considered similar
                # (0 = identical, higher = more different, max = 64 for 8x8 hash)
                if distance <= 5:
                    return True, f"Image matches expected (distance: {distance})"
                    
            except Exception as e:
                self.logger.warning(f"Failed to process expected image {expected_url}: {e}")
                continue
        
        # No match found
        if best_match_url:
            return False, f"Image does not match expected. Best match distance: {best_match_distance} (threshold: 5)"
        else:
            return False, "Failed to load any expected images for comparison"

    def _handle_image_content_llm_match(
        self, actual: Any, expected_values: Sequence[Any]
    ) -> tuple[bool, Optional[str]]:
        """Compare image content using LLM based on question/answer pairs.
        
        Expected format: ["Q: What's in the image? A: A cat."]
        The LLM analyzes the actual image and checks if the answer matches.
        
        Args:
            actual: Image URL (string) or base64-encoded image
            expected_values: List of strings in format "Q: <question> A: <expected_answer>"
            
        Returns:
            Tuple of (passed: bool, message: Optional[str])
        """
        if not expected_values:
            return False, "No expected Q&A pairs provided"
        
        # Parse expected Q&A pairs
        qa_pairs = []
        for expected_str in expected_values:
            if not isinstance(expected_str, str):
                continue
            
            # Parse "Q: <question> A: <answer>" format
            if "Q:" in expected_str and "A:" in expected_str:
                parts = expected_str.split("A:", 1)
                if len(parts) == 2:
                    question = parts[0].replace("Q:", "").strip()
                    expected_answer = parts[1].strip()
                    qa_pairs.append((question, expected_answer))
                else:
                    self.logger.warning(f"Invalid Q&A format: {expected_str}")
            else:
                # Fallback: treat entire string as question, expect any reasonable answer
                qa_pairs.append((expected_str, None))
        
        if not qa_pairs:
            return False, "No valid Q&A pairs found in expected values"
        
        # Load actual image
        try:
            actual_image_data = self._load_image_data(actual)
            if actual_image_data is None:
                return False, f"Failed to load actual image from: {actual[:100] if isinstance(actual, str) else 'provided data'}"
        except Exception as e:
            return False, f"Failed to process actual image: {str(e)}"
        
        # Use LLM grader infrastructure for image analysis
        try:
            from app.services.verification.llm_grader import LlmGrader
            
            llm_grader = LlmGrader(logger=self.logger)
            
            # Test each Q&A pair
            for question, expected_answer in qa_pairs:
                # Build prompt for LLM
                if expected_answer:
                    prompt = f"""You are analyzing an image to verify if it matches a specific description.

Question: {question}
Expected Answer: {expected_answer}

Analyze the provided image and determine if the answer to the question matches the expected answer.

Respond with ONLY a JSON object:
{{"matches": true/false, "reason": "brief explanation"}}"""
                else:
                    prompt = f"""You are analyzing an image to answer a question.

Question: {question}

Analyze the provided image and provide a clear answer.

Respond with ONLY a JSON object:
{{"answer": "your answer", "reason": "brief explanation"}}"""
                
                # Call LLM with image
                result = self._call_llm_with_image(prompt, actual_image_data, llm_grader)
                
                if result is None:
                    continue  # Try next Q&A pair
                
                # Parse result
                if expected_answer:
                    # Check if answer matches
                    matches = result.get("matches", False)
                    reason = result.get("reason", "No reason provided")
                    
                    if matches:
                        return True, f"Image content matches: {reason}"
                else:
                    # Any reasonable answer is acceptable
                    answer = result.get("answer", "")
                    reason = result.get("reason", "No reason provided")
                    if answer:
                        return True, f"Image analysis successful: {reason}"
            
            # No matches found
            return False, "Image content does not match any expected Q&A pairs"
            
        except Exception as e:
            self.logger.exception(f"LLM image analysis failed: {e}")
            return False, f"LLM image analysis failed: {str(e)}"

    def _load_image(self, image_source: Any) -> Optional[Any]:
        """Load an image from URL or base64 string.
        
        Args:
            image_source: URL string, base64 string, or file path
            
        Returns:
            PIL Image object or None if loading fails
        """
        from PIL import Image
        import requests
        from io import BytesIO
        import base64
        import os
        
        try:
            if isinstance(image_source, bytes):
                return Image.open(BytesIO(image_source))
            
            if not isinstance(image_source, str):
                return None
            
            # Handle base64-encoded images
            if image_source.startswith('data:image/'):
                # data:image/png;base64,<data>
                base64_data = image_source.split(',', 1)[1]
                image_data = base64.b64decode(base64_data)
                return Image.open(BytesIO(image_data))
            elif len(image_source) > 100 and not image_source.startswith(('http://', 'https://')):
                # Likely a base64 string without data URI prefix
                try:
                    image_data = base64.b64decode(image_source)
                    return Image.open(BytesIO(image_data))
                except Exception:
                    pass
            
            # Handle URLs
            if image_source.startswith(('http://', 'https://')):
                # Check for blocked domains (reuse existing utility)
                from app.services.computers.utils import check_blocklisted_url
                try:
                    check_blocklisted_url(image_source)
                except ValueError as e:
                    self.logger.warning(f"Blocked image URL: {e}")
                    return None
                
                response = requests.get(image_source, timeout=10, stream=True)
                response.raise_for_status()
                return Image.open(BytesIO(response.content))
            
            # Handle file paths
            if os.path.exists(image_source):
                return Image.open(image_source)
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Failed to load image from {type(image_source).__name__}: {e}")
            return None

    def _load_image_data(self, image_source: Any) -> Optional[str]:
        """Load image data and return as base64 string for LLM API.
        
        Args:
            image_source: URL string, base64 string, or file path
            
        Returns:
            Base64-encoded image string (data URI format) or None
        """
        from PIL import Image
        import requests
        from io import BytesIO
        import base64
        import os
        
        try:
            image_bytes = None
            
            if isinstance(image_source, bytes):
                image_bytes = image_source
            elif isinstance(image_source, str):
                # Handle base64-encoded images
                if image_source.startswith('data:image/'):
                    # Already in data URI format
                    return image_source
                elif len(image_source) > 100 and not image_source.startswith(('http://', 'https://')):
                    # Likely a base64 string
                    try:
                        base64.b64decode(image_source)  # Validate
                        return f"data:image/png;base64,{image_source}"
                    except Exception:
                        pass
                
                # Handle URLs
                if image_source.startswith(('http://', 'https://')):
                    from app.services.computers.utils import check_blocklisted_url
                    try:
                        check_blocklisted_url(image_source)
                    except ValueError:
                        return None
                    
                    response = requests.get(image_source, timeout=10)
                    response.raise_for_status()
                    image_bytes = response.content
                
                # Handle file paths
                elif os.path.exists(image_source):
                    with open(image_source, 'rb') as f:
                        image_bytes = f.read()
            
            if image_bytes:
                # Convert to base64 data URI
                base64_data = base64.b64encode(image_bytes).decode('utf-8')
                return f"data:image/png;base64,{base64_data}"
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Failed to load image data: {e}")
            return None

    def _call_llm_with_image(
        self, prompt: str, image_data: str, llm_grader: 'LlmGrader'
    ) -> Optional[Dict[str, Any]]:
        """Call LLM with image using existing infrastructure.
        
        Args:
            prompt: Text prompt for LLM
            image_data: Base64-encoded image (data URI format)
            llm_grader: LlmGrader instance
            
        Returns:
            Parsed JSON response or None
        """
        import json
        import re
        from app.services.computers.utils import create_response
        from app.core.config import settings
        
        try:
            # Prepare input items with image (similar to insighter.py pattern)
            input_items = [
                {
                    "type": "message",
                    "role": "user",
                    "content": prompt
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Please analyze this image:"
                        },
                        {
                            "type": "input_image",
                            "image_url": image_data  # Already in data URI format
                        }
                    ]
                }
            ]
            
            # Use OpenAI API (default model for image analysis)
            api_params = {
                "model": "gpt-4o",  # Use vision-capable model
                "input": input_items,
                "truncation": "auto"
            }
            
            response = create_response(**api_params)
            
            # Extract text from response
            if "output" in response and response["output"]:
                text_parts = []
                for item in response["output"]:
                    if item.get("type") == "message" and item.get("role") == "assistant":
                        content = item.get("content", "")
                        if isinstance(content, list):
                            for content_item in content:
                                if content_item.get("type") == "output_text":
                                    text_parts.append(content_item.get("text", ""))
                        else:
                            text_parts.append(str(content))
                
                response_text = " ".join(text_parts)
                
                # Parse JSON response
                try:
                    # Try to extract JSON from response
                    json_match = json.loads(response_text)
                    return json_match
                except json.JSONDecodeError:
                    # Try to find JSON in text
                    json_pattern = r'\{[^{}]*(?:"matches"|"answer")[^{}]*\}'
                    match = re.search(json_pattern, response_text, re.DOTALL)
                    if match:
                        return json.loads(match.group())
                    
                    # Fallback: return parsed response
                    return {"answer": response_text, "reason": "LLM response parsed"}
            
            return None
            
        except Exception as e:
            self.logger.error(f"LLM API call failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compare_numeric(value: float, operator: str, target: float) -> bool:
        if operator == "==":
            return math.isclose(value, target, rel_tol=1e-6, abs_tol=1e-6)
        if operator == "!=":
            return not math.isclose(value, target, rel_tol=1e-6, abs_tol=1e-6)
        if operator == ">":
            return value > target
        if operator == ">=":
            return value >= target
        if operator == "<":
            return value < target
        if operator == "<=":
            return value <= target
        raise ValueError(f"Unsupported numeric comparator: {operator}")

    @staticmethod
    def _compare_datetime(value: datetime, operator: str, target: datetime) -> bool:
        if operator == "==":
            return value == target
        if operator == "!=":
            return value != target
        if operator == ">":
            return value > target
        if operator == ">=":
            return value >= target
        if operator == "<":
            return value < target
        if operator == "<=":
            return value <= target
        raise ValueError(f"Unsupported datetime comparator: {operator}")

    @staticmethod
    def _ensure_mapping(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as exc:
                raise ValueError(f"Expected JSON object string, received '{value}'") from exc
        raise ValueError(f"Expected mapping/dict, received {type(value)}")

    @classmethod
    def _mapping_contains(cls, container: dict, subset: dict) -> bool:
        for key, expected_value in subset.items():
            if key not in container:
                return False
            actual_value = container[key]
            if isinstance(expected_value, dict) and isinstance(actual_value, dict):
                if not cls._mapping_contains(actual_value, expected_value):
                    return False
            elif isinstance(expected_value, list) and isinstance(actual_value, list):
                if not cls._sequence_contains(actual_value, expected_value):
                    return False
            else:
                if actual_value != expected_value:
                    return False
        return True

    @staticmethod
    def _sequence_contains(container: Sequence[Any], expected: Sequence[Any]) -> bool:
        if len(expected) > len(container):
            return False
        base = list(container)
        for item in expected:
            if item not in base:
                return False
        return True


__all__ = ["AssertionEngine", "ConfigurationError"]
