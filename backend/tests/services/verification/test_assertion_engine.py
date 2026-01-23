"""Comprehensive unit tests for GraderConfig verification system.

Tests align with the GraderConfig Implementation Plan testing strategy:
- Assertion Engine: exhaustive operator coverage with deterministic payloads
- Grader unit tests: edge cases (missing paths, mismatched types, multi-expected assertions)
- Integration tests: full verification cycle with mocked responses
"""

from pathlib import Path

import pytest

from app.schemas.verification import (
    Assertion,
    AssertionOperator,
    StateGraderConfig,
)
from app.services.verification import (
    AssertionEngine,
    GraderConfigVerifier,
    StateGrader,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture()
def assertion_engine() -> AssertionEngine:
    return AssertionEngine()


@pytest.fixture()
def state_grader(assertion_engine: AssertionEngine) -> StateGrader:
    return StateGrader(assertion_engine=assertion_engine)


# ============================================================================
# ASSERTION ENGINE - STRING OPERATORS
# ============================================================================

class TestStringOperators:
    """Exhaustive coverage of string assertion operators."""

    def test_string_equals_pass(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "hello", ["hello"])
        assert result.passed

    def test_string_equals_fail(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "world", ["hello"])
        assert not result.passed

    def test_string_equals_multiple_candidates(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["hello", "world"])
        result = assertion_engine.evaluate_assertion(assertion, "world", ["hello", "world"])
        assert result.passed

    def test_string_equals_case_sensitive(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["Hello"])
        result = assertion_engine.evaluate_assertion(assertion, "hello", ["Hello"])
        assert not result.passed  # Case-sensitive

    def test_string_equals_whitespace(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["  hello  "])
        result = assertion_engine.evaluate_assertion(assertion, "  hello  ", ["  hello  "])
        assert result.passed

    def test_string_contains_pass(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=["lo", "orl"])
        result = assertion_engine.evaluate_assertion(assertion, "hello world", ["lo", "orl"])
        assert result.passed

    def test_string_contains_fail(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=["xyz"])
        result = assertion_engine.evaluate_assertion(assertion, "hello", ["xyz"])
        assert not result.passed

    def test_string_contains_case_insensitive(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=["HELLO"])
        result = assertion_engine.evaluate_assertion(assertion, "hello world", ["HELLO"])
        assert result.passed  # Case-insensitive

    def test_string_contains_empty_actual(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "", ["hello"])
        assert not result.passed

    def test_string_not_contains_pass(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_NOT_CONTAINS, expected=["xyz"])
        result = assertion_engine.evaluate_assertion(assertion, "hello world", ["xyz"])
        assert result.passed

    def test_string_not_contains_fail(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_NOT_CONTAINS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "hello world", ["hello"])
        assert not result.passed

    def test_string_fuzzy_match_pass(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_FUZZY_MATCH, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "helo", ["hello"])  # Typo
        assert result.passed  # Should pass due to high similarity

    def test_string_fuzzy_match_fail(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_FUZZY_MATCH, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "xyz", ["hello"])
        assert not result.passed


# ============================================================================
# ASSERTION ENGINE - JSON OPERATORS
# ============================================================================

class TestJsonOperators:
    """Exhaustive coverage of JSON assertion operators."""

    def test_json_equals_pass(self, assertion_engine: AssertionEngine):
        actual = {"key": "value", "num": 123}
        expected = {"key": "value", "num": 123}
        assertion = Assertion(operator=AssertionOperator.JSON_EQUALS, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert result.passed

    def test_json_equals_fail(self, assertion_engine: AssertionEngine):
        actual = {"key": "value"}
        expected = {"key": "different"}
        assertion = Assertion(operator=AssertionOperator.JSON_EQUALS, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert not result.passed

    def test_json_contains_pass(self, assertion_engine: AssertionEngine):
        actual = {"key1": "value1", "key2": "value2", "nested": {"a": 1}}
        expected = {"key1": "value1", "nested": {"a": 1}}
        assertion = Assertion(operator=AssertionOperator.JSON_CONTAINS, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert result.passed

    def test_json_contains_fail(self, assertion_engine: AssertionEngine):
        actual = {"key1": "value1"}
        expected = {"key1": "value1", "missing": "key"}
        assertion = Assertion(operator=AssertionOperator.JSON_CONTAINS, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert not result.passed

    def test_json_part_of_pass(self, assertion_engine: AssertionEngine):
        actual = {"key": "value"}
        expected = {"key": "value", "extra": "data"}
        assertion = Assertion(operator=AssertionOperator.JSON_PART_OF, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert result.passed

    def test_json_part_of_fail(self, assertion_engine: AssertionEngine):
        actual = {"key": "value", "extra": "data"}
        expected = {"key": "value"}
        assertion = Assertion(operator=AssertionOperator.JSON_PART_OF, expected=[expected])
        result = assertion_engine.evaluate_assertion(assertion, actual, [expected])
        assert not result.passed


# ============================================================================
# ASSERTION ENGINE - NUMERIC OPERATORS
# ============================================================================

class TestNumericOperators:
    """Exhaustive coverage of numeric assertion operators."""

    def test_numeric_match_equals(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["==100"])
        result = assertion_engine.evaluate_assertion(assertion, 100, ["==100"])
        assert result.passed

    def test_numeric_match_not_equals(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["!=100"])
        result = assertion_engine.evaluate_assertion(assertion, 50, ["!=100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 100, ["!=100"])
        assert not result.passed

    def test_numeric_match_greater_than(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=[">100"])
        result = assertion_engine.evaluate_assertion(assertion, 150, [">100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 50, [">100"])
        assert not result.passed

    def test_numeric_match_greater_equal(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=[">=100"])
        result = assertion_engine.evaluate_assertion(assertion, 100, [">=100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 150, [">=100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 50, [">=100"])
        assert not result.passed

    def test_numeric_match_less_than(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["<100"])
        result = assertion_engine.evaluate_assertion(assertion, 50, ["<100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 150, ["<100"])
        assert not result.passed

    def test_numeric_match_less_equal(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["<=100"])
        result = assertion_engine.evaluate_assertion(assertion, 100, ["<=100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 50, ["<=100"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 150, ["<=100"])
        assert not result.passed

    def test_numeric_match_range(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=[">=1", "<=10"])
        result = assertion_engine.evaluate_assertion(assertion, 5, [">=1", "<=10"])
        assert result.passed

    def test_numeric_match_float_precision(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["==100.000001"])
        result = assertion_engine.evaluate_assertion(assertion, 100.0000009, ["==100.000001"])
        assert result.passed  # Should handle floating point precision


# ============================================================================
# ASSERTION ENGINE - BOOLEAN & ARRAY OPERATORS
# ============================================================================

class TestBooleanAndArrayOperators:
    """Exhaustive coverage of boolean and array assertion operators."""

    def test_bool_true(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.BOOL, expected=[True])
        result = assertion_engine.evaluate_assertion(assertion, True, [True])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, "true", [True])
        assert result.passed  # Should coerce string
        result = assertion_engine.evaluate_assertion(assertion, 1, [True])
        assert result.passed  # Should coerce number

    def test_bool_false(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.BOOL, expected=[False])
        result = assertion_engine.evaluate_assertion(assertion, False, [False])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, "false", [False])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, 0, [False])
        assert result.passed

    def test_array_length_match_equals(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_LENGTH_MATCH, expected=["==3"])
        result = assertion_engine.evaluate_assertion(assertion, [1, 2, 3], ["==3"])
        assert result.passed

    def test_array_length_match_greater(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_LENGTH_MATCH, expected=[">=2"])
        result = assertion_engine.evaluate_assertion(assertion, [1, 2, 3], [">=2"])
        assert result.passed

    def test_array_string_equals(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_EQUALS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "hello"], ["hello"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["hello"])
        assert not result.passed

    def test_array_string_contains(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_CONTAINS, expected=["lo"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["lo"])
        assert result.passed  # "hello" contains "lo"

    def test_array_string_not_contains_pass(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS passes when forbidden strings are absent."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["xyz", "abc"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["xyz", "abc"])
        assert result.passed

    def test_array_string_not_contains_fail_single(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS fails when one forbidden string is found."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["hello"])
        assert not result.passed
        assert "hello" in result.message.lower()

    def test_array_string_not_contains_fail_multiple(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS fails when multiple forbidden strings are found."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["hello", "world"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["hello", "world"])
        assert not result.passed

    def test_array_string_not_contains_case_insensitive(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS is case-insensitive."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["HELLO"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["HELLO"])
        assert not result.passed  # Should fail because "hello" matches "HELLO" (case-insensitive)

    def test_array_string_not_contains_substring_match(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS checks for substrings within array elements."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["ell"])
        result = assertion_engine.evaluate_assertion(assertion, ["hello", "world"], ["ell"])
        assert not result.passed  # Should fail because "hello" contains "ell"

    def test_array_string_not_contains_empty_array(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS with empty array."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, [], ["hello"])
        assert result.passed  # Empty array contains nothing, so forbidden strings are absent

    def test_array_string_not_contains_none_values(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS handles None values in expected list."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["hello", None, "world"])
        result = assertion_engine.evaluate_assertion(assertion, ["goodbye", "universe"], ["hello", None, "world"])
        assert result.passed  # None values should be filtered out

    def test_array_string_not_contains_type_error(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS fails gracefully with non-array actual value."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["hello"])
        result = assertion_engine.evaluate_assertion(assertion, "not an array", ["hello"])
        assert not result.passed
        assert "not an array" in result.message.lower()

    def test_array_string_not_contains_mixed_content(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS with mixed content types in array."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["error"])
        result = assertion_engine.evaluate_assertion(
            assertion, 
            ["success", "completed", 123, True, None], 
            ["error"]
        )
        assert result.passed  # "error" not found in any stringified element

    def test_array_string_not_contains_partial_match(self, assertion_engine: AssertionEngine):
        """Test ARRAY_STRING_NOT_CONTAINS with partial string matches."""
        assertion = Assertion(operator=AssertionOperator.ARRAY_STRING_NOT_CONTAINS, expected=["fail", "error"])
        result = assertion_engine.evaluate_assertion(
            assertion,
            ["successful", "completed", "finished"],
            ["fail", "error"]
        )
        assert result.passed  # "fail" is not in "successful" as whole word doesn't matter, but substring

    def test_array_numeric_match(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_NUMERIC_MATCH, expected=[">=10"])
        result = assertion_engine.evaluate_assertion(assertion, [10, 20, 30], [">=10"])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, [5, 20, 30], [">=10"])
        assert not result.passed

    def test_array_bool(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.ARRAY_BOOL, expected=[True])
        result = assertion_engine.evaluate_assertion(assertion, [True, True], [True])
        assert result.passed
        result = assertion_engine.evaluate_assertion(assertion, [True, False], [True])
        assert not result.passed


# ============================================================================
# ASSERTION ENGINE - DATETIME OPERATORS
# ============================================================================

class TestDatetimeOperators:
    """Exhaustive coverage of datetime assertion operators."""

    def test_datetime_match_equals(self, assertion_engine: AssertionEngine):
        assertion = Assertion(
            operator=AssertionOperator.DATETIME_MATCH, expected=["==2025-01-01T00:00:00Z"]
        )
        result = assertion_engine.evaluate_assertion(
            assertion, "2025-01-01T00:00:00Z", ["==2025-01-01T00:00:00Z"]
        )
        assert result.passed

    def test_datetime_match_greater(self, assertion_engine: AssertionEngine):
        assertion = Assertion(
            operator=AssertionOperator.DATETIME_MATCH, expected=[">=2025-01-01T00:00:00Z"]
        )
        result = assertion_engine.evaluate_assertion(
            assertion, "2025-02-01T00:00:00Z", [">=2025-01-01T00:00:00Z"]
        )
        assert result.passed


# ============================================================================
# ASSERTION ENGINE - JSONPATH EXTRACTION
# ============================================================================

class TestJsonPathExtraction:
    """Test JSONPath extraction with various scenarios."""

    def test_extract_simple_path(self, assertion_engine: AssertionEngine):
        data = {"key": "value"}
        result = assertion_engine.extract_values_by_path(data, "$.key")
        assert result == ["value"]

    def test_extract_nested_path(self, assertion_engine: AssertionEngine):
        data = {"a": {"b": {"c": "value"}}}
        result = assertion_engine.extract_values_by_path(data, "$.a.b.c")
        assert result == ["value"]

    def test_extract_array_index(self, assertion_engine: AssertionEngine):
        data = {"items": [{"id": 1}, {"id": 2}]}
        result = assertion_engine.extract_values_by_path(data, "$.items[0].id")
        assert result == [1]

    def test_extract_array_wildcard(self, assertion_engine: AssertionEngine):
        data = {"items": [{"id": 1}, {"id": 2}, {"id": 1}]}
        result = assertion_engine.extract_values_by_path(data, "$.items[*].id")
        assert len(result) == 3
        assert 1 in result
        assert 2 in result

    def test_extract_missing_path(self, assertion_engine: AssertionEngine):
        data = {"key": "value"}
        result = assertion_engine.extract_values_by_path(data, "$.missing")
        assert result == []  # Should return empty list, not raise

    def test_extract_none_path(self, assertion_engine: AssertionEngine):
        data = {"key": "value"}
        result = assertion_engine.extract_values_by_path(data, None)
        assert result == [data]  # Should return data wrapped in list


# ============================================================================
# ASSERTION ENGINE - EDGE CASES & ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_null_actual_value(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["value"])
        result = assertion_engine.evaluate_assertion(assertion, None, ["value"])
        assert not result.passed

    def test_empty_expected_values(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=[])
        result = assertion_engine.evaluate_assertion(assertion, "hello", [])
        # Should handle gracefully

    def test_type_mismatch(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.STRING_EQUALS, expected=["123"])
        result = assertion_engine.evaluate_assertion(assertion, 123, ["123"])  # Int vs string
        # Should normalize and compare

    def test_exception_handling(self, assertion_engine: AssertionEngine):
        assertion = Assertion(operator=AssertionOperator.NUMERIC_MATCH, expected=["invalid"])
        result = assertion_engine.evaluate_assertion(assertion, "not_a_number", ["invalid"])
        assert not result.passed
        assert result.message is not None  # Should have error message


# ============================================================================
# STATE GRADER - EDGE CASES
# ============================================================================

class TestStateGraderEdgeCases:
    """Test StateGrader edge cases per testing strategy."""

    def test_missing_path_to_actual(self, state_grader: StateGrader):
        """Edge case: missing path should return empty subject."""
        config = StateGraderConfig(
            path_to_actual="$.missing",
            assertions=[
                Assertion(operator=AssertionOperator.ARRAY_LENGTH_MATCH, expected=[">=1"])
            ],
        )
        actual_state = {"cart": {"items": []}}
        expected_states = []
        result = state_grader.grade(actual_state, expected_states, config)
        assert not result.passed

    def test_mismatched_types(self, state_grader: StateGrader):
        """Edge case: type mismatches should be handled gracefully."""
        config = StateGraderConfig(
            path_to_actual="$.count",
            assertions=[
                Assertion(operator=AssertionOperator.STRING_CONTAINS, expected=["123"])
            ],
        )
        actual_state = {"count": 123}  # Int, not string
        expected_states = []
        result = state_grader.grade(actual_state, expected_states, config)
        # Should handle type coercion

    def test_multi_expected_assertions(self, state_grader: StateGrader):
        """Edge case: multiple expected values."""
        config = StateGraderConfig(
            path_to_actual="$.status",
            assertions=[
                Assertion(
                    operator=AssertionOperator.STRING_CONTAINS, expected=["active", "open"]
                )
            ],
        )
        actual_state = {"status": "active"}
        expected_states = []
        result = state_grader.grade(actual_state, expected_states, config)
        assert result.passed


# ============================================================================
# INTEGRATION TESTS - EXAMPLE 1: E-COMMERCE SHOPPING CART
# ============================================================================

def test_example1_ecommerce_shopping_cart():
    """Integration test for Example 1: E-commerce Shopping Cart from spec."""
    task = {
        "task_id": "shop_001",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.cart.items",
                    "assertions": [
                        {"operator": "ARRAY_LENGTH_MATCH", "expected": ["==1"]},
                        {
                            "operator": "JSON_PART_OF",
                            "path_to_actual": "$[0]",
                            "paths_to_expected": ["$[0].product"],
                        },
                    ],
                }
            ],
            "answer_grader_config": {
                "assertions": [
                    {
                        "operator": "STRING_CONTAINS",
                        "expected": ["added"],
                        "paths_to_expected": ["$[0].product.name", "$[0].product.brand"],
                    }
                ]
            },
        },
    }

    execution_results = {
        "window_get_states_payload": {
            "actual_state": {
                "cart": {
                    "items": [{"name": "DJI Mini 3 Pro", "price": 759.99, "brand": "DJI"}]
                }
            },
            "expected_states": [
                {"product": {"name": "DJI Mini 3 Pro", "price": 759.99, "brand": "DJI"}}
            ],
        },
        "modelResponse": "Successfully added DJI Mini 3 Pro to cart",
        "final_url": "https://example.com/checkout",
    }

    verifier = GraderConfigVerifier()
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]
    assert len(payload["grader_results"]) >= 2  # State + Answer graders


# ============================================================================
# INTEGRATION TESTS - EXAMPLE 2: FLIGHT BOOKING
# ============================================================================

def test_example2_flight_booking():
    """Integration test for Example 2: Flight Booking from spec."""
    task = {
        "task_id": "flight_001",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.bookings",
                    "assertions": [
                        {"operator": "ARRAY_LENGTH_MATCH", "expected": ["==1"]},
                        {"operator": "JSON_CONTAINS", "paths_to_expected": ["$[0].flight"]},
                    ],
                }
            ],
        },
    }

    execution_results = {
        "window_get_states_payload": {
            "actual_state": {
                "bookings": [
                    {
                        "flight": {
                            "origin": "NYC",
                            "destination": "LAX",
                            "date": "2025-11-04",
                            "price": 299.99,
                        }
                    }
                ]
            },
            "expected_states": [
                {
                    "flight": {
                        "origin": "NYC",
                        "destination": "LAX",
                        "date": "2025-11-04",
                        "price": 299.99,
                    }
                }
            ],
        },
    }

    verifier = GraderConfigVerifier()
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]


# ============================================================================
# INTEGRATION TESTS - EXAMPLE 3: MULTI-LAYERED VERIFICATION
# ============================================================================

def test_example3_multi_layered_verification():
    """Integration test for Example 3: Multi-layered Verification from spec."""
    task = {
        "task_id": "complex_001",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.user_profile",
                    "assertions": [
                        {"operator": "JSON_CONTAINS", "paths_to_expected": ["$[0].user"]}
                    ],
                },
                {
                    "path_to_actual": "$.verification_status",
                    "assertions": [
                        {
                            "operator": "STRING_EQUALS",
                            "path_to_actual": "$.status",
                            "expected": ["verified"],
                        }
                    ],
                },
            ],
            "url_grader_config": {
                "assertions": [
                    {"operator": "STRING_CONTAINS", "expected": ["dashboard", "welcome"]}
                ]
            },
        },
    }

    execution_results = {
        "window_get_states_payload": {
            "actual_state": {
                "user_profile": {"user": {"email": "test@example.com", "name": "Test User"}},
                "verification_status": {"status": "verified"},
            },
            "expected_states": [
                {"user": {"email": "test@example.com", "name": "Test User"}}
            ],
        },
        "final_url": "https://example.com/dashboard/welcome",
    }

    verifier = GraderConfigVerifier()
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]
    assert len(payload["grader_results"]) >= 3  # Multiple state graders + URL grader


# ============================================================================
# INTEGRATION TESTS - EXAMPLE 4: ARRAY_STRING_NOT_CONTAINS USE CASE
# ============================================================================

def test_example4_validation_no_errors():
    """Integration test demonstrating ARRAY_STRING_NOT_CONTAINS for error checking.
    
    Use case: Verify that a form submission validation does not contain any error messages.
    This is useful for checking that unwanted strings (errors, warnings) are absent from arrays.
    """
    task = {
        "task_id": "validation_001",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.validation_messages",
                    "assertions": [
                        # Ensure no error keywords appear in validation messages
                        {
                            "operator": "ARRAY_STRING_NOT_CONTAINS",
                            "expected": ["error", "failed", "invalid", "warning"]
                        },
                        # Ensure we have some validation messages
                        {
                            "operator": "ARRAY_LENGTH_MATCH",
                            "expected": [">=1"]
                        }
                    ],
                },
                {
                    "path_to_actual": "$.form_status",
                    "assertions": [
                        {
                            "operator": "STRING_EQUALS",
                            "path_to_actual": "$.status",
                            "expected": ["submitted"]
                        }
                    ]
                }
            ],
            "answer_grader_config": {
                "assertions": [
                    {"operator": "STRING_CONTAINS", "expected": ["success", "submitted"]}
                ]
            }
        },
    }

    # Successful case - no errors in validation messages
    execution_results = {
        "window_get_states_payload": {
            "actual_state": {
                "validation_messages": [
                    "Email format is correct",
                    "Password meets requirements",
                    "All fields validated successfully"
                ],
                "form_status": {"status": "submitted"}
            },
            "expected_states": []
        },
        "modelResponse": "Form successfully submitted with all validations passing"
    }

    verifier = GraderConfigVerifier()
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]


def test_example4_validation_with_errors():
    """Test that ARRAY_STRING_NOT_CONTAINS correctly fails when error messages are present."""
    task = {
        "task_id": "validation_002",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.validation_messages",
                    "assertions": [
                        {
                            "operator": "ARRAY_STRING_NOT_CONTAINS",
                            "expected": ["error", "failed", "invalid"]
                        }
                    ],
                }
            ],
        },
    }

    # Failed case - contains error messages
    execution_results = {
        "window_get_states_payload": {
            "actual_state": {
                "validation_messages": [
                    "Email format is correct",
                    "Password validation failed",  # Contains "failed"
                    "Username is available"
                ]
            },
            "expected_states": []
        }
    }

    verifier = GraderConfigVerifier()
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "FAILED"
    assert payload["verification_completed"]


# ============================================================================
# MOCK TESTS - WINDOW.GET_STATES MOCKING
# ============================================================================

def test_window_get_states_mock_fallback():
    """Test that window_get_states_payload in execution_results is used as fallback."""
    task = {
        "task_id": "test_task",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.data",
                    "assertions": [
                        {"operator": "STRING_EQUALS", "path_to_actual": "$.value", "expected": ["test"]}
                    ],
                }
            ],
        },
    }

    execution_results = {
        "window_get_states_payload": {
            "actual_state": {"data": {"value": "test"}},
            "expected_states": [],
        }
    }

    # Create verifier without browser_page to force fallback
    verifier = GraderConfigVerifier(browser_page=None, browser_computer=None)
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]


def test_window_get_states_execution_results_fallback():
    """Test fallback to execution_results when window_get_states_payload not available."""
    task = {
        "task_id": "test_task",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.data",
                    "assertions": [
                        {"operator": "STRING_EQUALS", "path_to_actual": "$.value", "expected": ["test"]}
                    ],
                }
            ],
        },
    }

    # Use execution_results directly (no window_get_states_payload)
    execution_results = {
        "actual_state": {"data": {"value": "test"}},
        "expected_states": [],
    }

    verifier = GraderConfigVerifier(browser_page=None, browser_computer=None)
    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]


# ============================================================================
# EXISTING TESTS (KEEP THESE FOR BACKWARD COMPATIBILITY)
# ============================================================================

def test_string_contains(assertion_engine: AssertionEngine) -> None:
    assertion = Assertion(
        operator=AssertionOperator.STRING_CONTAINS,
        expected=["widget"],
    )
    result = assertion_engine.evaluate_assertion(
        assertion, actual_value="Added Widget to cart", expected_values=["widget"]
    )
    assert result.passed


def test_numeric_match(assertion_engine: AssertionEngine) -> None:
    assertion = Assertion(
        operator=AssertionOperator.NUMERIC_MATCH,
        expected=[">=1", "<=10"],
    )
    result = assertion_engine.evaluate_assertion(assertion, 5, [">=1", "<=10"])
    assert result.passed


def test_state_grader_simple_success(assertion_engine: AssertionEngine) -> None:
    grader = StateGrader(assertion_engine=assertion_engine)
    config = StateGraderConfig(
        path_to_actual="$.cart.items",
        assertions=[
            Assertion(operator=AssertionOperator.ARRAY_LENGTH_MATCH, expected=["==1"]),
            Assertion(
                operator=AssertionOperator.JSON_CONTAINS,
                path_to_actual="$[0]",
                paths_to_expected=["$[0]"],
            ),
        ],
    )
    actual_state = {"cart": {"items": [{"name": "Widget"}]}}
    expected_states = [{"name": "Widget"}]

    result = grader.grade(actual_state, expected_states, config)
    assert result.passed


def test_verifier_passes_with_all_graders() -> None:
    verifier = GraderConfigVerifier()
    task = {
        "task_id": "demo_task",
        "grader_config": {
            "state_grader_configs": [
                {
                    "path_to_actual": "$.cart.items",
                    "assertions": [
                        {"operator": "ARRAY_LENGTH_MATCH", "expected": ["==1"]},
                        {
                            "operator": "JSON_CONTAINS",
                            "path_to_actual": "$[0]",
                            "paths_to_expected": ["$[0]"],
                        },
                    ],
                }
            ],
            "answer_grader_config": {
                "assertions": [
                    {"operator": "STRING_CONTAINS", "expected": ["Widget"]}
                ]
            },
            "url_grader_config": {
                "assertions": [
                    {"operator": "STRING_CONTAINS", "expected": ["checkout"]}
                ]
            },
        },
    }
    execution_results = {
        "actual_state": {"cart": {"items": [{"name": "Widget"}]}},
        "expected_states": [{"name": "Widget"}],
        "modelResponse": "Successfully added Widget to cart",
        "final_url": "https://example.com/checkout",
    }

    results_dir = Path("./tmp")
    payload = verifier.verify_task(task, execution_results, results_dir)

    assert payload["verification_status"] == "PASSED"
    assert payload["verification_completed"]
    assert payload["verification_method"] == "grader_config"
    assert len(payload["grader_results"]) == 3
