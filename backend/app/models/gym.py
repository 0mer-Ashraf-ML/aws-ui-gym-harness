"""
Gym database model
"""

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class VerificationStrategy(str, enum.Enum):
    """Verification strategy enum"""
    VERIFICATION_ENDPOINT = "VERIFICATION_ENDPOINT"
    RUN_ID_ASSERTIONS = "RUN_ID_ASSERTIONS"
    LOCAL_STORAGE_ASSERTIONS = "LOCAL_STORAGE_ASSERTIONS"
    GRADER_CONFIG = "GRADER_CONFIG"
    VERIFIER_API_SCRIPT = "VERIFIER_API_SCRIPT"


class Gym(Base):
    """Gym model"""
    __tablename__ = "gyms"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, index=True)
    base_url = Column(Text, nullable=False)
    verification_strategy = Column(Enum(VerificationStrategy), nullable=False, default=VerificationStrategy.GRADER_CONFIG)
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tasks = relationship("Task", back_populates="gym", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="gym", cascade="all, delete-orphan")
    batches = relationship("Batch", back_populates="gym", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Gym(uuid='{self.uuid}', name='{self.name}')>"
