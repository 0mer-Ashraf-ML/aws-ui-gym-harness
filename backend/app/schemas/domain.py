"""
Domain schemas for API requests and responses
"""

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field, validator


class DomainBase(BaseModel):
    """Base domain schema"""
    domain: str = Field(..., min_length=1, max_length=255, description="Domain name (e.g., example.com)")
    is_active: bool = Field(default=True, description="Domain active status")
    
    @validator('domain')
    def validate_domain(cls, v):
        """Validate domain format"""
        if not v:
            raise ValueError('Domain cannot be empty')
        
        # Basic domain validation - should contain at least one dot and no spaces
        if ' ' in v:
            raise ValueError('Domain cannot contain spaces')
        
        if '.' not in v:
            raise ValueError('Domain must contain at least one dot (e.g., example.com)')
        
        # Convert to lowercase
        return v.lower().strip()


class DomainCreate(DomainBase):
    """Schema for creating a domain"""
    pass


class DomainUpdate(BaseModel):
    """Schema for updating a domain"""
    is_active: bool = Field(..., description="Domain active status")


class DomainResponse(DomainBase):
    """Schema for domain response"""
    uuid: UUID = Field(..., description="Domain UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True


class DomainListResponse(BaseModel):
    """Schema for domain list response"""
    domains: List[DomainResponse] = Field(..., description="List of domains")
    total: int = Field(..., description="Total number of domains")


class WhitelistDomainRequest(BaseModel):
    """Schema for whitelist domain request"""
    domain: str = Field(..., min_length=1, max_length=255, description="Domain to whitelist (e.g., example.com)")
    
    @validator('domain')
    def validate_domain(cls, v):
        """Validate domain format"""
        if not v:
            raise ValueError('Domain cannot be empty')
        
        # Basic domain validation - should contain at least one dot and no spaces
        if ' ' in v:
            raise ValueError('Domain cannot contain spaces')
        
        if '.' not in v:
            raise ValueError('Domain must contain at least one dot (e.g., example.com)')
        
        # Convert to lowercase
        return v.lower().strip()
