"""
Task schemas for API requests and responses
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TaskBase(BaseModel):
    """Base task schema"""
    task_id: str = Field(..., min_length=1, max_length=255, description="Task ID (unique within gym)")
    gym_id: UUID = Field(..., description="Gym UUID")
    prompt: str = Field(..., min_length=1, description="Task prompt")
    grader_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Declarative verification configuration for harness-side grading",
    )
    simulator_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Configuration payload forwarded to gyms to set up simulators",
    )
    verifier_path: Optional[str] = Field(
        default=None,
        description="Verifier python to execute when the the verifier strategy is scipt based",
    )

class TaskCreate(TaskBase):
    """Schema for creating a task"""
    pass

class TaskUpdate(BaseModel):
    """Schema for updating a task"""
    task_id: Optional[str] = Field(None, min_length=1, max_length=255)
    prompt: Optional[str] = Field(None, min_length=1)
    grader_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated grader configuration",
    )
    simulator_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Updated simulator configuration",
    )
    verifier_path: Optional[str] = Field(
        default=None,
        description="Update verifier python scipt",
    )

class TaskResponse(TaskBase):
    """Schema for task response"""
    uuid: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class TaskListResponse(BaseModel):
    """Schema for task list response"""
    tasks: List[TaskResponse]
    total: int
    skip: int
    limit: int

class TaskSyncResponse(BaseModel):
    """Schema for task sync response"""
    message: str
    new_tasks_count: int
    total_tasks_count: int

class TaskVerifierUploadResponse(BaseModel):
    """Schema for task verfier script upload response"""

    file_id: str
    file_location: str

class TaskExportResponse(BaseModel):
    """Schema for task export response (downloadable JSON)"""
    task_id: str = Field(..., description="Task identifier")
    prompt: str = Field(..., description="Task prompt text")
    verification_script_md: str = Field(..., description="Python verification script wrapped in markdown fenced code block")

class GymTasksExportResponse(BaseModel):
    """Schema for gym-level task export response"""
    gym_id: str = Field(..., description="Gym UUID")
    tasks: List[TaskExportResponse] = Field(..., description="List of exported tasks")
