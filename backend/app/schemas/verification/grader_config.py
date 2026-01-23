"""High-level GraderConfig Pydantic schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from .assertions import Assertion


class ExpectedStateFunction(BaseModel):
    """Function call definition evaluated inside the gym to compute expected state."""

    function: str = Field(..., description="Name of the gym-provided helper function")
    args: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments passed to the helper")

    class Config:
        extra = "forbid"


class ExtractStatesConfig(BaseModel):
    """Configuration describing how the gym should compute expected states."""

    expected_state_functions: List[ExpectedStateFunction] = Field(
        default_factory=list,
        description="List of helper function calls executed within the gym context",
    )

    class Config:
        extra = "forbid"


class StateGraderConfig(BaseModel):
    """Defines assertions evaluating the actual state returned by window.get_states."""

    path_to_actual: Optional[str] = Field(
        default=None,
        description="JSONPath selecting the root slice of actual_state to evaluate",
    )
    assertions: List[Assertion] = Field(..., description="Assertions applied to the selected actual state")

    class Config:
        extra = "forbid"


class TextGraderConfig(BaseModel):
    """Base config shared by textual graders (answer/url)."""

    assertions: List[Assertion] = Field(..., description="Assertions evaluated against the textual payload")

    class Config:
        extra = "forbid"


class LlmGraderConfig(BaseModel):
    """Instruction for an LLM-based secondary grader."""

    instruction: str = Field(..., description="Prompt describing the success criteria for the LLM")
    include_trajectory: bool = Field(
        default=False,
        description="When True, include the agent trajectory in the LLM grading prompt",
    )
    model: Optional[str] = Field(
        default=None,
        description="Optional override for the LLM model identifier",
    )

    class Config:
        extra = "forbid"


class GraderConfig(BaseModel):
    """Top-level configuration powering harness-side verification."""

    extract_states_config: Optional[ExtractStatesConfig] = Field(
        default=None,
        description="Instructions for the harness to retrieve expected state from the gym",
    )
    state_grader_configs: Optional[List[StateGraderConfig]] = Field(
        default=None,
        description="Collection of state-based graders",
    )
    answer_grader_config: Optional[TextGraderConfig] = Field(
        default=None,
        description="Configuration for answer/text verification",
    )
    url_grader_config: Optional[TextGraderConfig] = Field(
        default=None,
        description="Configuration for URL verification",
    )
    llm_grader_configs: Optional[List[LlmGraderConfig]] = Field(
        default=None,
        description="Collection of LLM-based graders",
    )

    class Config:
        extra = "forbid"

    @validator(
        "state_grader_configs", "llm_grader_configs", pre=True, always=True
    )
    def normalize_empty_lists(cls, value):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, list) and len(value) == 0:
            return None
        return value


__all__ = [
    "ExpectedStateFunction",
    "ExtractStatesConfig",
    "StateGraderConfig",
    "TextGraderConfig",
    "LlmGraderConfig",
    "GraderConfig",
]
