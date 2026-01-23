"""
Execution schemas for API requests and responses
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ModelType(str, Enum):
    """Model type enum"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    UNIFIED = "unified"

class ExecutionType(str, Enum):
    """Execution type enum"""
    BATCH = "batch"
    PLAYGROUND = "playground"

class ExecutionStatus(str, Enum):
    """Execution status enum"""
    PENDING = "pending"
    EXECUTING = "executing"
    PASSED = "passed"
    FAILED = "failed"
    CRASHED = "crashed"
    TIMEOUT = "timeout"

class ExecutionBase(BaseModel):
    """Base execution schema"""
    execution_folder_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Execution folder name (auto-generated)")
    gym_id: Optional[UUID] = Field(None, description="Gym UUID (nullable for playground executions)")
    batch_id: Optional[UUID] = Field(None, description="Batch UUID (nullable)")
    number_of_iterations: int = Field(1, ge=1, description="Number of iterations")
    model: ModelType = Field(..., description="Model type")
    # Don't set a default - require it to be explicitly provided
    execution_type: ExecutionType = Field(..., description="Execution type (batch or playground) - must be explicitly provided")
    
    # Playground-specific fields
    playground_url: Optional[str] = Field(None, description="URL for playground executions (required if execution_type is playground)")
    
    # Task snapshot fields (decoupled from tasks table)
    task_identifier: Optional[str] = Field(None, max_length=255, description="Task identifier (snapshot)")
    prompt: Optional[str] = Field(None, description="Task prompt (snapshot)")
    grader_config: Optional[Dict[str, Any]] = Field(None, description="Grader config (snapshot)")
    simulator_config: Optional[Dict[str, Any]] = Field(None, description="Simulator config (snapshot)")

class ExecutionCreate(ExecutionBase):
    """Schema for creating an execution"""
    # Optional task_id for backwards compatibility - will populate snapshots from this
    task_id: Optional[UUID] = Field(None, description="Task UUID (optional, for backwards compatibility)")
    
    @model_validator(mode='before')
    @classmethod
    def infer_execution_type(cls, data):
        """Infer execution_type from other fields if not provided"""
        if isinstance(data, dict):
            # If execution_type is not provided, infer it from other fields
            if 'execution_type' not in data or data.get('execution_type') is None:
                # If playground_url is provided, it's a playground execution
                if data.get('playground_url'):
                    data['execution_type'] = ExecutionType.PLAYGROUND.value
                # If gym_id is provided, it's a batch execution
                elif data.get('gym_id'):
                    data['execution_type'] = ExecutionType.BATCH.value
                else:
                    # Default to batch if we can't infer
                    data['execution_type'] = ExecutionType.BATCH.value
        return data
    
    @model_validator(mode='after')
    def validate_playground_fields(self):
        """Validate playground execution requirements"""
        if self.execution_type == ExecutionType.PLAYGROUND:
            # For playground: playground_url and prompt are required, gym_id should be None
            if not self.playground_url:
                raise ValueError("playground_url is required for playground executions")
            if not self.prompt:
                raise ValueError("prompt is required for playground executions")
            if self.gym_id is not None:
                raise ValueError("gym_id must be None for playground executions")
        else:
            # For batch: gym_id is required, playground_url should be None
            if not self.gym_id:
                raise ValueError("gym_id is required for batch executions")
            if self.playground_url is not None:
                raise ValueError("playground_url must be None for batch executions")
        
        return self

class ExecutionUpdate(BaseModel):
    """Schema for updating an execution"""
    execution_folder_name: Optional[str] = Field(None, min_length=1, max_length=255)
    number_of_iterations: Optional[int] = Field(None, ge=1)
    model: Optional[ModelType] = None

class ExecutionResponse(ExecutionBase):
    """Schema for execution response"""
    uuid: UUID
    created_at: datetime
    updated_at: datetime
    status: ExecutionStatus = Field(..., description="Execution status (computed from iterations)")
    eval_insights: Optional[str] = None
    execution_duration_seconds: Optional[float] = Field(None, description="Total execution duration in seconds (calculated from iterations)")
    
    class Config:
        from_attributes = True

class TaskStatusSummary(BaseModel):
    """Schema for task status summary"""
    task_id: str
    task_uuid: Optional[str] = None  # Optional since task is decoupled from execution
    prompt: str
    status: ExecutionStatus
    total_iterations: int
    passed_count: int
    failed_count: int
    crashed_count: int
    timeout_count: int
    pending_count: int
    executing_count: int

class ExecutionStatusSummary(BaseModel):
    """Schema for execution status summary with counts"""
    total_iterations: int
    passed_count: int
    failed_count: int
    crashed_count: int
    timeout_count: int
    pending_count: int
    executing_count: int

class ExecutionResponseWithStatus(ExecutionResponse):
    """Enhanced execution response with task status and iteration counts"""
    status_summary: ExecutionStatusSummary
    tasks: List[TaskStatusSummary]

class ExecutionListResponse(BaseModel):
    """Schema for execution list response"""
    executions: List[ExecutionResponse]
    total: int
    skip: int
    limit: int