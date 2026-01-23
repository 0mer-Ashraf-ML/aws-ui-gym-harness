"""
Iteration database model - represents individual task execution iterations
"""

import uuid

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text,
                        func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Iteration(Base):
    """Iteration model - represents a single task execution iteration"""
    __tablename__ = "iterations"
    
    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.uuid", ondelete="CASCADE"), nullable=False, index=True)
    # Note: task_id removed - use execution.task_identifier instead
    iteration_number = Column(Integer, nullable=False, index=True)  # 1, 2, 3, etc.
    status = Column(String(20), nullable=False, default='pending', index=True)  # 'pending', 'executing', 'passed', 'failed', 'crashed'
    
    # Celery task tracking
    celery_task_id = Column(String(255), nullable=True, index=True)  # Celery task ID for tracking
    
    # Execution details
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    execution_time_seconds = Column(Integer, nullable=True)
    
    # Results and logs
    result_data = Column(Text, nullable=True)  # JSON string of results
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Execution logs
    
    # Step counts (per-iteration)
    total_steps = Column(Integer, nullable=True)
    
    # Verification results
    verification_details = Column(Text, nullable=True)  # JSON string of verification details
    verification_comments = Column(Text, nullable=True)  # Human-readable verification comments
    
    # Model response
    last_model_response = Column(Text, nullable=True)  # Last natural response from the model
    
    # Evaluation insights
    eval_insights = Column(Text, nullable=True)  # Insight summary from insighter
    
    # Action timeline (complete timeline with model thinking + actions)
    action_timeline_json = Column(Text, nullable=True)  # JSON string of complete action timeline
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    execution = relationship("Execution", back_populates="iterations")
    # Note: task relationship removed - use execution.task_identifier to get task info
    
    def __repr__(self):
        return f"<Iteration(uuid='{self.uuid}', execution_id='{self.execution_id}', iteration_number={self.iteration_number}, status='{self.status}')>"
