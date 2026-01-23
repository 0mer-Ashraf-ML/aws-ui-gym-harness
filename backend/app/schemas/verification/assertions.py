"""Pydantic models describing GraderConfig assertions and operators."""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, validator


class AssertionOperator(str, Enum):
    """Supported comparison operators for GraderConfig assertions."""

    STRING_EQUALS = "STRING_EQUALS"
    STRING_CONTAINS = "STRING_CONTAINS"
    STRING_NOT_CONTAINS = "STRING_NOT_CONTAINS"
    STRING_FUZZY_MATCH = "STRING_FUZZY_MATCH"

    JSON_EQUALS = "JSON_EQUALS"
    JSON_CONTAINS = "JSON_CONTAINS"
    JSON_PART_OF = "JSON_PART_OF"

    NUMERIC_MATCH = "NUMERIC_MATCH"
    BOOL = "BOOL"

    ARRAY_LENGTH_MATCH = "ARRAY_LENGTH_MATCH"
    ARRAY_STRING_EQUALS = "ARRAY_STRING_EQUALS"
    ARRAY_STRING_CONTAINS = "ARRAY_STRING_CONTAINS"
    ARRAY_STRING_NOT_CONTAINS = "ARRAY_STRING_NOT_CONTAINS"
    ARRAY_NUMERIC_MATCH = "ARRAY_NUMERIC_MATCH"
    ARRAY_BOOL = "ARRAY_BOOL"

    DATETIME_MATCH = "DATETIME_MATCH"

    IMAGE_FUZZY_MATCH = "IMAGE_FUZZY_MATCH"
    IMAGE_CONTENT_LLM_MATCH = "IMAGE_CONTENT_LLM_MATCH"


class Assertion(BaseModel):
    """Declarative assertion configuration."""

    operator: AssertionOperator = Field(..., description="Operator that determines comparison semantics")
    expected: Optional[List[Any]] = Field(
        default=None,
        description="Literal expected values or comparator expressions (e.g., ['>=10']).",
    )
    path_to_actual: Optional[str] = Field(
        default=None,
        description="Optional JSONPath resolving to an inner value relative to the parent actual payload.",
    )
    paths_to_expected: Optional[List[str]] = Field(
        default=None,
        description="JSONPaths evaluated against expected state objects; results extend expected values.",
    )

    class Config:
        extra = "forbid"

    @validator("paths_to_expected", always=True)
    def ensure_non_empty_paths(cls, value):  # type: ignore[override]
        if value is not None and any(path.strip() == "" for path in value):
            raise ValueError("paths_to_expected entries must be non-empty strings")
        return value


__all__ = ["Assertion", "AssertionOperator"]
