"""
Gym schemas for API requests and responses
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.models.gym import VerificationStrategy


class GymBase(BaseModel):
    """Base gym schema"""
    name: str = Field(..., min_length=1, max_length=255, description="Gym name")
    base_url: str = Field(..., description="Base URL for the gym")
    verification_strategy: VerificationStrategy = Field(VerificationStrategy.GRADER_CONFIG, description="Verification strategy for the gym")
    description: Optional[str] = Field(None, description="Gym description")
    
    @field_validator('verification_strategy', mode='before')
    @classmethod
    def validate_verification_strategy(cls, v):
        """Convert lowercase string to enum value for frontend compatibility"""
        if isinstance(v, str):
            # Convert lowercase frontend values to uppercase enum values
            v_upper = v.upper()
            try:
                return VerificationStrategy[v_upper]
            except KeyError:
                # If not found, try direct match
                return VerificationStrategy(v)
        return v
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate that base_url is a valid URL format"""
        if not v:
            raise ValueError('base_url cannot be empty')
        v_stripped = v.strip()
        if not v_stripped.startswith(('http://', 'https://')):
            raise ValueError('base_url must start with http:// or https://')
        return v_stripped

class GymCreate(GymBase):
    """Schema for creating a gym"""
    pass

class GymUpdate(BaseModel):
    """Schema for updating a gym"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    base_url: Optional[str] = None
    verification_strategy: Optional[VerificationStrategy] = None
    description: Optional[str] = None
    
    @field_validator('verification_strategy', mode='before')
    @classmethod
    def validate_verification_strategy(cls, v):
        """Convert lowercase string to enum value for frontend compatibility"""
        if v is None:
            return None
        if isinstance(v, str):
            # Convert lowercase frontend values to uppercase enum values
            v_upper = v.upper()
            try:
                return VerificationStrategy[v_upper]
            except KeyError:
                # If not found, try direct match
                return VerificationStrategy(v)
        return v
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate that base_url is a valid URL format (if provided)"""
        if v is None:
            return v
        v_stripped = v.strip()
        if not v_stripped:
            raise ValueError('base_url cannot be empty')
        if not v_stripped.startswith(('http://', 'https://')):
            raise ValueError('base_url must start with http:// or https://')
        return v_stripped

class GymResponse(GymBase):
    """Schema for gym response"""
    uuid: UUID
    created_at: datetime
    updated_at: datetime
    
    @field_serializer('verification_strategy')
    def serialize_verification_strategy(self, value: VerificationStrategy) -> str:
        """Serialize verification strategy enum to lowercase string for frontend compatibility"""
        if hasattr(value, 'value'):
            return value.value.lower()
        return str(value).lower() if isinstance(value, str) else value
    
    class Config:
        from_attributes = True

class GymWithTaskCount(GymResponse):
    """Schema for gym response with task count"""
    task_count: int = Field(0, description="Number of tasks in this gym")

class GymListResponse(BaseModel):
    """Schema for gym list response"""
    gyms: List[GymResponse]
    total: int
    skip: int
    limit: int

class GymListWithTaskCountResponse(BaseModel):
    """Schema for gym list response with task counts"""
    gyms: List[GymWithTaskCount]
    total: int
    skip: int
    limit: int
