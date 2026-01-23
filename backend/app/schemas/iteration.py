"""
Iteration schemas for API requests and responses
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IterationStatus(str, Enum):
    """Iteration status enum"""
    PENDING = "pending"
    EXECUTING = "executing"
    PASSED = "passed"
    FAILED = "failed"
    CRASHED = "crashed"
    TIMEOUT = "timeout"

# VerificationStatus enum removed - now using unified IterationStatus

class IterationBase(BaseModel):
    """Base iteration schema"""
    execution_id: UUID = Field(..., description="Parent execution UUID")
    # Note: task_id removed - iterations get task info from parent execution
    iteration_number: int = Field(..., ge=1, description="Iteration number (1, 2, 3, etc.)")
    status: IterationStatus = Field(IterationStatus.PENDING, description="Iteration status")
    celery_task_id: Optional[str] = Field(None, description="Celery task ID for tracking")

class IterationCreate(IterationBase):
    """Schema for creating an iteration"""
    pass

class IterationUpdate(BaseModel):
    """Schema for updating an iteration"""
    status: Optional[IterationStatus] = None
    celery_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_seconds: Optional[int] = None
    result_data: Optional[str] = None  # JSON string
    error_message: Optional[str] = None
    logs: Optional[str] = None
    verification_details: Optional[str] = None  # JSON string
    verification_comments: Optional[str] = None
    last_model_response: Optional[str] = None
    total_steps: Optional[int] = None
    action_timeline_json: Optional[str] = None  # JSON string of timeline entries

class IterationResponse(IterationBase):
    """Schema for iteration response"""
    uuid: UUID
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_seconds: Optional[int] = None
    result_data: Optional[str] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None
    verification_details: Optional[str] = None
    verification_comments: Optional[str] = None
    last_model_response: Optional[str] = None
    total_steps: Optional[int] = None
    eval_insights: Optional[str] = None
    action_timeline_json: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class IterationListResponse(BaseModel):
    """Schema for iteration list response"""
    iterations: list[IterationResponse]
    total: int
    skip: int
    limit: int

class IterationWithResults(IterationResponse):
    """Schema for iteration with parsed results"""
    parsed_result_data: Optional[Dict[str, Any]] = None
    parsed_verification_details: Optional[Dict[str, Any]] = None
