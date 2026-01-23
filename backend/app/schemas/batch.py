"""
Batch schemas for API requests and responses
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ModelType(str, Enum):
    """Model type enum"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class BatchStatus(str, Enum):
    """Batch status enum"""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CRASHED = "crashed"


class BatchBase(BaseModel):
    """Base batch schema"""

    name: str = Field(..., min_length=1, max_length=255, description="Batch name")
    gym_id: UUID = Field(..., description="Gym UUID")
    number_of_iterations: int = Field(
        1, ge=1, le=10, description="Number of iterations (max 10)"
    )


class BatchCreate(BatchBase):
    """Schema for creating a batch"""

    selected_models: List[ModelType] = Field(
        default_factory=lambda: [ModelType.OPENAI, ModelType.ANTHROPIC, ModelType.GEMINI],
        description="List of models to run for this batch"
    )
    selected_task_ids: Optional[List[UUID]] = Field(
        None,
        description="List of task UUIDs to run. If not provided or empty, all tasks in the gym will be used."
    )


class BatchUpdate(BaseModel):
    """Schema for updating a batch"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    number_of_iterations: Optional[int] = Field(None, ge=1, le=10)


class BatchResponse(BatchBase):
    """Schema for batch response"""

    uuid: UUID
    created_at: datetime
    updated_at: datetime
    status: BatchStatus = Field(
        ..., description="Batch status (computed from executions)"
    )
    eval_insights: Optional[dict] = None
    rerun_enabled: bool = Field(True, description="Whether manual rerun is enabled for this batch")
    created_by: Optional[UUID] = Field(None, description="UUID of user who created this batch")
    username: Optional[str] = Field(None, description="Username/email of the user who created this batch")

    class Config:
        from_attributes = True


class BatchListResponse(BaseModel):
    """Schema for batch list response"""

    batches: List[BatchResponse]
    total: int
    skip: int
    limit: int


class BatchMetadata(BaseModel):
    """Lightweight batch metadata for dropdowns/selection (no status calculation)"""
    uuid: UUID
    name: str
    created_at: datetime
    gym_id: UUID
    
    class Config:
        from_attributes = True


class BatchRerunResponse(BaseModel):
    """Schema for batch rerun response"""

    message: str = Field(..., description="Success message")
    batch_id: str = Field(..., description="Batch UUID")
    total_failed_iterations: int = Field(
        ..., description="Total number of failed iterations found"
    )
    rerun_iterations: int = Field(
        ..., description="Number of iterations successfully queued for rerun"
    )
    skipped_iterations: int = Field(
        ..., description="Number of iterations skipped (not crashed)"
    )
    failed_cleanups: int = Field(
        ..., description="Number of file cleanup operations that failed"
    )
    failed_resets: int = Field(
        ..., description="Number of database reset operations that failed"
    )
    failed_queues: int = Field(
        ..., description="Number of task queue operations that failed"
    )


# Iteration Summary Schemas


class IterationCounts(BaseModel):
    """Iteration status counts"""

    pending: int = Field(0, ge=0, description="Number of pending iterations")
    executing: int = Field(0, ge=0, description="Number of executing iterations")
    passed: int = Field(0, ge=0, description="Number of passed iterations")
    failed: int = Field(0, ge=0, description="Number of failed iterations")
    crashed: int = Field(0, ge=0, description="Number of crashed iterations")


class ExecutionIterationBreakdown(BaseModel):
    """Per-execution iteration breakdown"""

    execution_id: str = Field(..., description="Execution UUID")
    task_id: Optional[str] = Field(None, description="Task UUID")
    task_name: str = Field(..., description="Task description/name")
    model: str = Field(..., description="Model type (openai, anthropic, gemini)")
    total_iterations: int = Field(
        0, ge=0, description="Total iterations for this execution"
    )
    iteration_counts: IterationCounts = Field(
        ..., description="Iteration status counts"
    )


class OverallIterationSummary(BaseModel):
    """Overall batch iteration summary"""

    total_executions: int = Field(0, ge=0, description="Total number of executions")
    total_iterations: int = Field(
        0, ge=0, description="Total iterations across all executions"
    )
    iteration_counts: IterationCounts = Field(
        ..., description="Aggregated iteration status counts"
    )


class BatchIterationSummaryResponse(BaseModel):
    """Complete batch iteration summary response"""

    batch_id: str = Field(..., description="Batch UUID")
    batch_name: str = Field(..., description="Batch name")
    overall_summary: OverallIterationSummary = Field(
        ..., description="Overall iteration statistics"
    )
    execution_breakdowns: List[ExecutionIterationBreakdown] = Field(
        default_factory=list, description="Per-execution iteration breakdown"
    )
    generated_at: str = Field(
        ..., description="Timestamp when summary was generated (ISO format)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "123e4567-e89b-12d3-a456-426614174000",
                "batch_name": "My Test Batch",
                "overall_summary": {
                    "total_executions": 10,
                    "total_iterations": 50,
                    "iteration_counts": {
                        "pending": 5,
                        "executing": 3,
                        "passed": 30,
                        "failed": 10,
                        "crashed": 2,
                    },
                },
                "execution_breakdowns": [
                    {
                        "execution_id": "456e7890-e89b-12d3-a456-426614174001",
                        "task_id": "789e0123-e89b-12d3-a456-426614174002",
                        "task_name": "Login Test",
                        "model": "openai",
                        "total_iterations": 5,
                        "iteration_counts": {
                            "pending": 0,
                            "executing": 1,
                            "passed": 3,
                            "failed": 1,
                            "crashed": 0,
                        },
                    }
                ],
                "generated_at": "2025-10-15T10:00:00.000000",
            }
        }


# Failure Diagnostics Schemas

class FailureCategory(str, Enum):
    """Categories for iteration failures"""
    MODEL_BLOCKED = "model_blocked"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_ERROR = "verification_error"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    UNKNOWN = "unknown"


class FailedIterationDetail(BaseModel):
    """Details about a single failed iteration"""
    iteration_number: int = Field(..., description="Iteration number")
    iteration_id: str = Field(..., description="Iteration UUID")
    execution_id: str = Field(..., description="Execution UUID")
    task_id: str = Field(..., description="Task identifier")
    model: str = Field(..., description="Model used (openai, anthropic, gemini)")
    category: FailureCategory = Field(..., description="Failure category")
    reason_text: str = Field(..., description="Human-readable failure reason")
    completion_reason: Optional[str] = Field(None, description="Full completion reason if available")
    execution_time_seconds: Optional[int] = Field(None, description="Execution time in seconds")
    iteration_url: str = Field(..., description="URL to iteration details page")


class FailureCategoryGroup(BaseModel):
    """Group of iterations that failed for the same reason"""
    count: int = Field(..., description="Number of failures in this category")
    category_label: str = Field(..., description="Human-readable category name")
    iterations: List[FailedIterationDetail] = Field(default_factory=list, description="List of failed iterations")


class BatchFailureDiagnosticsResponse(BaseModel):
    """Response containing failure diagnostics for a batch"""
    batch_id: str = Field(..., description="Batch UUID")
    batch_name: str = Field(..., description="Batch name")
    total_failed: int = Field(..., description="Total number of failed iterations")
    by_category: Dict[str, FailureCategoryGroup] = Field(
        default_factory=dict, 
        description="Failures grouped by category"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "123e4567-e89b-12d3-a456-426614174000",
                "batch_name": "My Test Batch",
                "total_failed": 3,
                "by_category": {
                    "model_blocked": {
                        "count": 2,
                        "category_label": "Model Blocked",
                        "iterations": [
                            {
                                "iteration_number": 2,
                                "iteration_id": "iter-uuid",
                                "execution_id": "exec-uuid",
                                "task_id": "TASK-001",
                                "model": "openai",
                                "category": "model_blocked",
                                "reason_text": "Model stated: couldn't find direct access to restore deleted ticket",
                                "completion_reason": "After thoroughly navigating...",
                                "execution_time_seconds": 179,
                                "iteration_url": "/batches/123/runs/exec-uuid"
                            }
                        ]
                    }
                }
            }
        }
