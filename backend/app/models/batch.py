"""
Batch database model
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class Batch(Base):
    """Batch model"""
    __tablename__ = "batches"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, index=True)
    gym_id = Column(UUID(as_uuid=True), ForeignKey("gyms.uuid"), nullable=False, index=True)
    number_of_iterations = Column(Integer, nullable=False, default=1)
    
    # Rerun control flag - when False, manual reruns are disabled (e.g., after user termination)
    rerun_enabled = Column(Boolean, nullable=False, default=True)
    
    # User who created/ran this batch
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True, index=True)
    
    # Evaluation insights
    eval_insights = Column(JSON(astext_type=String), nullable=True)  # Batch-level insights as JSON
    
    # Notification tracking - stores array of user UUIDs who have read this notification
    notification_read_by = Column(JSON(astext_type=String), nullable=True, default=list)  # Array of user UUIDs
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    gym = relationship("Gym", back_populates="batches")
    creator = relationship("User", foreign_keys=[created_by])  # Relationship to user who created the batch
    executions = relationship("Execution", back_populates="batch", cascade="all, delete-orphan", passive_deletes=True)
    
    def __repr__(self):
        try:
            return f"<Batch(uuid='{self.uuid}', name='{self.name}')>"
        except Exception:
            # Fallback if attributes are not accessible (e.g., session expired)
            return f"<Batch(id='{id(self)}')>"
