"""
User schemas for API requests and responses
"""

from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr = Field(..., description="User email address")
    name: str = Field(..., min_length=1, description="User full name")
    picture: Optional[str] = Field(None, description="User profile picture URL")

class UserCreate(UserBase):
    """Schema for creating a user"""
    google_id: str = Field(..., description="Google OAuth ID")
    is_admin: bool = Field(default=False, description="Admin privileges")
    is_whitelisted: bool = Field(default=False, description="Whitelist status")

class UserUpdate(BaseModel):
    """Schema for updating a user"""
    name: Optional[str] = Field(None, min_length=1, description="User full name")
    picture: Optional[str] = Field(None, description="User profile picture URL")
    is_admin: Optional[bool] = Field(None, description="Admin privileges")
    is_whitelisted: Optional[bool] = Field(None, description="Whitelist status")
    is_active: Optional[bool] = Field(None, description="Active status")

class UserResponse(UserBase):
    """Schema for user response"""
    uuid: UUID = Field(..., description="User UUID")
    is_admin: bool = Field(..., description="Admin privileges")
    is_whitelisted: bool = Field(..., description="Whitelist status")
    is_active: bool = Field(..., description="Active status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_login: Optional[datetime] = Field(None, description="Last login timestamp")
    role: Optional[Literal["admin", "user"]] = Field(
        None, description="Computed role based on Excel access control"
    )
    
    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    """Schema for user list response"""
    users: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")

class GoogleAuthRequest(BaseModel):
    """Schema for Google OAuth request"""
    code: str = Field(..., description="Google OAuth authorization code")

class TokenResponse(BaseModel):
    """Schema for authentication token response"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserResponse = Field(..., description="User information")

class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")

class WhitelistRequest(BaseModel):
    """Schema for whitelist user request"""
    email: EmailStr = Field(..., description="Email to whitelist")
    is_admin: bool = Field(default=False, description="Grant admin privileges")
