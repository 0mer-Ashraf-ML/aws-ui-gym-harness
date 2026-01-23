"""
Leaderboard schemas for API requests and responses
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class LeaderboardGymStats(BaseModel):
    """Fail percentage statistics per gym"""

    gym_id: str = Field(..., description="Gym UUID")
    gym_name: str = Field(..., description="Gym name")
    passed_count: int = Field(0, ge=0, description="Number of passed iterations")
    failed_count: int = Field(0, ge=0, description="Number of failed iterations")
    total_count: int = Field(0, ge=0, description="Total iterations (passed + failed)")
    fail_percentage: float = Field(
        0.0, ge=0.0, le=100.0, description="Fail percentage (0-100)"
    )


class LeaderboardModelGymStats(BaseModel):
    """Fail percentage statistics per (model, gym) combination"""

    model: str = Field(..., description="Model name (openai, anthropic, gemini, unified)")
    gym_id: str = Field(..., description="Gym UUID")
    gym_name: str = Field(..., description="Gym name")
    passed_count: int = Field(0, ge=0, description="Number of passed iterations")
    failed_count: int = Field(0, ge=0, description="Number of failed iterations")
    total_count: int = Field(0, ge=0, description="Total iterations (passed + failed)")
    fail_percentage: float = Field(
        0.0, ge=0.0, le=100.0, description="Fail percentage (0-100)"
    )


class LeaderboardModelStats(BaseModel):
    """Fail percentage statistics per model (overall)"""

    model: str = Field(..., description="Model name (openai, anthropic, gemini, unified)")
    passed_count: int = Field(0, ge=0, description="Number of passed iterations")
    failed_count: int = Field(0, ge=0, description="Number of failed iterations")
    total_count: int = Field(0, ge=0, description="Total iterations (passed + failed)")
    fail_percentage: float = Field(
        0.0, ge=0.0, le=100.0, description="Fail percentage (0-100)"
    )


class LeaderboardResponse(BaseModel):
    """Leaderboard response schema"""

    overall_passed_count: int = Field(
        0, ge=0, description="Total passed iterations across all filtered data"
    )
    overall_failed_count: int = Field(
        0, ge=0, description="Total failed iterations across all filtered data"
    )
    overall_total_count: int = Field(
        0, ge=0, description="Total iterations (passed + failed)"
    )
    overall_fail_percentage: float = Field(
        0.0, ge=0.0, le=100.0, description="Overall fail percentage (0-100)"
    )
    gym_stats: List[LeaderboardGymStats] = Field(
        default_factory=list, description="Fail percentage statistics per gym"
    )
    model_gym_stats: List[LeaderboardModelGymStats] = Field(
        default_factory=list, description="Fail percentage statistics per (model, gym) combination"
    )
    model_stats: List[LeaderboardModelStats] = Field(
        default_factory=list, description="Fail percentage statistics per model (overall)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "overall_passed_count": 150,
                "overall_failed_count": 50,
                "overall_total_count": 200,
                "overall_fail_percentage": 25.0,
                "gym_stats": [
                    {
                        "gym_id": "123e4567-e89b-12d3-a456-426614174000",
                        "gym_name": "Test Gym",
                        "passed_count": 100,
                        "failed_count": 25,
                        "total_count": 125,
                        "fail_percentage": 20.0,
                    }
                ],
            }
        }

