"""
Task database model
"""

import uuid

from sqlalchemy import (Column, DateTime, ForeignKey, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Task(Base):
    """Task model"""
    __tablename__ = "tasks"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    task_id = Column(String(255), nullable=False, index=True)
    gym_id = Column(UUID(as_uuid=True), ForeignKey("gyms.uuid"), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    grader_config = Column(JSONB, nullable=True)
    simulator_config = Column(JSONB, nullable=True)
    verifier_path = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    gym = relationship("Gym", back_populates="tasks")
    # Note: executions relationship removed - executions are now decoupled from tasks
    # Executions use task_identifier snapshot field instead of FK relationship
    # Note: iterations relationship removed - iterations get task info from execution parent
    
    # Unique constraint: task_id must be unique within a gym
    __table_args__ = (
        UniqueConstraint('task_id', 'gym_id', name='unique_task_id_per_gym'),
    )
    
    def __repr__(self):
        return f"<Task(uuid='{self.uuid}', task_id='{self.task_id}', gym_id='{self.gym_id}')>"
