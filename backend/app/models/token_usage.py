"""
Token Usage database model - tracks API token consumption for each model
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Float, func, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class TokenUsage(Base):
    """Token usage model - tracks API token consumption per iteration"""
    __tablename__ = "token_usage"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # NO foreign keys - preserve token usage history independently
    # These just store UUIDs for historical reference/queries
    iteration_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    execution_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    gym_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
    # Snapshot fields - preserve batch context even after deletion
    batch_name = Column(String(255), nullable=True)
    gym_name = Column(String(255), nullable=True)
    task_identifier = Column(String(255), nullable=True)
    iteration_number = Column(Integer, nullable=True)
    batch_is_deleted = Column(Boolean, nullable=False, default=False)
    
    # Model information
    model_name = Column(String(100), nullable=False, index=True)  # 'openai', 'anthropic', 'gemini'
    model_version = Column(String(100), nullable=True)  # e.g., 'gpt-4', 'claude-sonnet-4', 'gemini-2.0'
    
    # Token counts
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    
    # Additional usage metrics
    api_calls_count = Column(Integer, nullable=False, default=1)  # Number of API calls
    cached_tokens = Column(Integer, nullable=True, default=0)  # For models that support caching
    
    # Cost estimation (optional, can be calculated from tokens)
    estimated_cost_usd = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # No relationships - token_usage is completely independent for historical preservation
    # No foreign keys means no automatic relationships
    
    def __repr__(self):
        return f"<TokenUsage(uuid='{self.uuid}', model='{self.model_name}', total_tokens={self.total_tokens})>"

