"""
Action Timeline schemas for iteration monitoring

This module defines the timeline entry types for displaying
iteration execution in real-time, including model thinking/responses
and actions with screenshots.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field


class TimelineEntryType(str, Enum):
    """Type of timeline entry"""
    MODEL_THINKING = "model_thinking"
    MODEL_RESPONSE = "model_response"
    ACTION = "action"


class ActionType(str, Enum):
    """Type of action performed"""
    COMPUTER_ACTION = "computer_action"
    BASH_COMMAND = "bash_command"
    EDITOR_ACTION = "editor_action"
    NAVIGATE = "navigate"
    SCREENSHOT = "screenshot"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    KEY_PRESS = "key_press"
    OTHER = "other"


class ActionStatus(str, Enum):
    """Status of action execution"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class TimelineEntry(BaseModel):
    """Base timeline entry"""
    id: str = Field(..., description="Unique identifier (UUID string)")
    timestamp: datetime = Field(..., description="Entry timestamp")
    entry_type: TimelineEntryType = Field(..., description="Type of timeline entry")
    sequence_index: int = Field(..., description="Sequence order for playback", ge=0)


class ModelThinkingEntry(TimelineEntry):
    """Model thinking/reasoning entry"""
    entry_type: Literal[TimelineEntryType.MODEL_THINKING] = TimelineEntryType.MODEL_THINKING
    content: str = Field(..., description="Model's thinking text")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-11-14T10:23:45.123456",
                "entry_type": "model_thinking",
                "sequence_index": 0,
                "content": "I need to click the submit button to log in..."
            }
        }


class ModelResponseEntry(TimelineEntry):
    """Model response/explanation entry"""
    entry_type: Literal[TimelineEntryType.MODEL_RESPONSE] = TimelineEntryType.MODEL_RESPONSE
    content: str = Field(..., description="Model's response text")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "timestamp": "2025-11-14T10:23:50.123456",
                "entry_type": "model_response",
                "sequence_index": 2,
                "content": "Login successful! Navigating to dashboard..."
            }
        }


class ActionEntry(TimelineEntry):
    """Action execution entry"""
    entry_type: Literal[TimelineEntryType.ACTION] = TimelineEntryType.ACTION
    action_type: ActionType = Field(..., description="Specific type of action")
    action_name: str = Field(..., description="User-friendly action name")
    description: str = Field(..., description="Detailed description of action")
    screenshot_path: Optional[str] = Field(None, description="Relative path to screenshot (legacy)")
    screenshot_before: Optional[str] = Field(None, description="Screenshot BEFORE action (showing what will be done)")
    screenshot_after: Optional[str] = Field(None, description="Screenshot AFTER action (showing result)")
    current_url: Optional[str] = Field(None, description="Browser URL at time of action")
    status: ActionStatus = Field(ActionStatus.SUCCESS, description="Action execution status")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional action data")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "timestamp": "2025-11-14T10:23:47.123456",
                "entry_type": "action",
                "sequence_index": 1,
                "action_type": "click",
                "action_name": "Click Submit Button",
                "description": "Clicked submit button at coordinates (245, 680)",
                "screenshot_path": "screenshots/task_submit_20251114_102347.png",
                "current_url": "https://example.com/login",
                "status": "success",
                "metadata": {
                    "coordinates": [245, 680],
                    "element": "button#submit"
                }
            }
        }


class TimelineResponse(BaseModel):
    """Response containing timeline entries"""
    entries: List[Union[ModelThinkingEntry, ModelResponseEntry, ActionEntry]] = Field(..., description="List of timeline entries")
    total_entries: int = Field(..., description="Total number of entries")
    total_actions: int = Field(..., description="Number of action entries (for playback)")
    execution_id: str = Field(..., description="Execution UUID")
    iteration_id: str = Field(..., description="Iteration UUID")
    
    class Config:
        schema_extra = {
            "example": {
                "entries": [],
                "total_entries": 25,
                "total_actions": 15,
                "execution_id": "550e8400-e29b-41d4-a716-446655440003",
                "iteration_id": "550e8400-e29b-41d4-a716-446655440004"
            }
        }

