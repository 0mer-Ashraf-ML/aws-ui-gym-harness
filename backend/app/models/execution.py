"""
Execution database model
"""

import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class ExecutionType(str, enum.Enum):
    """Execution type enum"""
    BATCH = "batch"
    PLAYGROUND = "playground"


class Execution(Base):
    """Execution model"""
    __tablename__ = "executions"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    execution_folder_name = Column(String(255), nullable=True, index=True)
    gym_id = Column(UUID(as_uuid=True), ForeignKey("gyms.uuid"), nullable=True, index=True)  # Nullable for playground
    batch_id = Column(UUID(as_uuid=True), ForeignKey("batches.uuid", ondelete="CASCADE"), nullable=True, index=True)
    number_of_iterations = Column(Integer, nullable=False, default=1)
    model = Column(String(50), nullable=False, index=True)  # 'openai', 'anthropic', 'gemini', or 'unified'
    
    # Execution type (batch or playground)
    # Use PostgreSQL ENUM with explicit values to match the enum values, not names
    execution_type = Column(ENUM('batch', 'playground', name='executiontype', create_type=False), nullable=False, default=ExecutionType.BATCH, index=True)
    
    # Playground-specific fields
    playground_url = Column(Text, nullable=True)  # URL for playground executions (like gyms.base_url)
    
    # Task snapshot fields (decoupled from tasks table)
    task_identifier = Column(String(255), nullable=True, index=True)  # Snapshot of task.task_id
    prompt = Column(Text, nullable=True)  # Snapshot of task.prompt
    grader_config = Column(JSONB, nullable=True)  # Snapshot of task.grader_config
    simulator_config = Column(JSONB, nullable=True)  # Snapshot of task.simulator_config
    
    # Evaluation insights
    eval_insights = Column(Text, nullable=True)  # Execution-level insight summary
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    gym = relationship("Gym", back_populates="executions")
    batch = relationship("Batch", back_populates="executions")
    iterations = relationship("Iteration", back_populates="execution", cascade="all, delete-orphan", passive_deletes=True)
    
    def __repr__(self):
        return f"<Execution(uuid='{self.uuid}', model='{self.model}', type='{self.execution_type}')>"
