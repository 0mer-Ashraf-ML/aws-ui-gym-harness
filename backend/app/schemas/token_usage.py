"""
Token Usage schemas for API requests and responses
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TokenUsageBase(BaseModel):
    """Base schema for token usage"""
    model_name: str = Field(..., description="Model name (openai, anthropic, gemini)")
    model_version: Optional[str] = Field(None, description="Model version (e.g., gpt-4, claude-sonnet-4)")
    input_tokens: int = Field(0, description="Number of input tokens")
    output_tokens: int = Field(0, description="Number of output tokens")
    total_tokens: int = Field(0, description="Total number of tokens")
    api_calls_count: int = Field(1, description="Number of API calls made")
    cached_tokens: Optional[int] = Field(0, description="Number of cached tokens (if supported)")
    estimated_cost_usd: Optional[float] = Field(None, description="Estimated cost in USD")


class TokenUsageCreate(TokenUsageBase):
    """Schema for creating token usage record"""
    iteration_id: Optional[UUID] = Field(None, description="Associated iteration UUID")
    execution_id: Optional[UUID] = Field(None, description="Associated execution UUID")
    batch_id: Optional[UUID] = Field(None, description="Associated batch UUID")
    gym_id: Optional[UUID] = Field(None, description="Associated gym UUID (snapshot)")
    # Snapshot fields - preserve context even after parent records are deleted
    batch_name: Optional[str] = Field(None, description="Batch name snapshot")
    gym_name: Optional[str] = Field(None, description="Gym name snapshot")
    task_identifier: Optional[str] = Field(None, description="Task identifier snapshot")
    iteration_number: Optional[int] = Field(None, description="Iteration number snapshot")
    batch_is_deleted: Optional[bool] = Field(False, description="Snapshot flag indicating batch was deleted")


class TokenUsageResponse(TokenUsageBase):
    """Schema for token usage response"""
    uuid: UUID
    iteration_id: Optional[UUID]
    execution_id: Optional[UUID]
    batch_id: Optional[UUID]
    gym_id: Optional[UUID]
    batch_name: Optional[str]
    gym_name: Optional[str]
    task_identifier: Optional[str]
    iteration_number: Optional[int]
    batch_is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenUsageAggregation(BaseModel):
    """Schema for aggregated token usage statistics"""
    model_name: str
    model_versions: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_api_calls: int
    total_cached_tokens: int
    total_estimated_cost_usd: float
    execution_count: int
    iteration_count: int
    average_tokens_per_iteration: float
    average_tokens_per_api_call: float
    average_input_tokens_per_api_call: float
    average_output_tokens_per_api_call: float
    first_usage: datetime
    last_usage: datetime


class TokenUsageSummary(BaseModel):
    """Schema for overall token usage summary"""
    total_tokens: int
    total_cost_usd: float
    total_api_calls: int
    by_model: dict[str, TokenUsageAggregation]
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None


class TokenUsageReport(BaseModel):
    """Schema for token usage report"""
    summary: TokenUsageSummary
    daily_breakdown: list[dict]
    model_breakdown: list[dict]
    execution_breakdown: list[dict]
    generated_at: datetime


class TokenUsageStatsRequest(BaseModel):
    """Schema for requesting token usage stats with filters"""
    model_name: Optional[str] = Field(None, description="Filter by model name")
    start_date: Optional[datetime] = Field(None, description="Start date for filtering")
    end_date: Optional[datetime] = Field(None, description="End date for filtering")
    execution_id: Optional[UUID] = Field(None, description="Filter by execution ID")
    limit: int = Field(100, description="Limit number of results", ge=1, le=1000)

