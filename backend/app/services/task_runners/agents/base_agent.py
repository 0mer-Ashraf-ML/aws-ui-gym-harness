#!/usr/bin/env python3
"""
Base Agent Interface - Defines the contract for all agents
Based on the architecture defined in RUNNER_REFACTORING_PROPOSAL.md

DIVISION OF WORK:
- RUNNER: Handles Playwright initialization/termination, verification, file management
- AGENT: Only handles task execution logic (different for OpenAI vs Anthropic)
- MIXINS: Shared functionality (logging, file management, verification, cleanup)

This agent should implement these methods:
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAgent(ABC):
    """
    Base interface for all V2 agents
    
    DIVISION OF WORK:
    - RUNNER: Handles Playwright initialization/termination, verification, file management
    - AGENT: Only handles task execution logic (different for OpenAI vs Anthropic)
    - MIXINS: Shared functionality (logging, file management, verification, cleanup)
    
    This agent should implement these methods:
    """
    
    def __init__(self, computer=None, logger=None, task_dir=None):
        """
        Initialize the base agent
        
        Args:
            computer: Playwright browser instance (managed by runner)
            logger: Logger instance (managed by runner)
            task_dir: Task directory path (managed by runner)
        """
        self.computer = computer
        self.logger = logger
        self.task_dir = task_dir
        self.action_callback = None  # ✅ Callback for real-time action reporting
        self.iteration_id = None  # ✅ For DB storage
        self.execution_id = None  # ✅ For DB storage
    
    def set_action_callback(self, callback):
        """
        Set callback function to report actions in real-time during execution
        
        Args:
            callback: Function(item: Dict) -> None
        """
        self.action_callback = callback
    
    def _report_action(self, item: Dict[str, Any]):
        """
        Report an action to the callback (if set)
        
        Agents should call this after each action during execution
        Also stores model responses to database immediately when generated
        """
        # ✅ Store assistant messages to database immediately
        # BUT skip system-generated completion messages (is_completion_marker flag)
        if item and item.get('type') == 'message' and item.get('role') == 'assistant':
            # Skip storing if this is just a completion marker for UI
            if not item.get('is_completion_marker', False):
                self._store_model_response_to_db(item)
            
            # ✅ FIX: Don't report empty messages to live timeline
            # Extract and check content before sending to timeline
            content = item.get('content', '')
            if isinstance(content, list):
                # Handle list format (OpenAI/Anthropic/Gemini styles)
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        # OpenAI: {"text": "..."} OR Anthropic: {"type": "text", "text": "..."}
                        if part.get('type') == 'text':
                            text_parts.append(part.get('text', ''))
                        elif 'text' in part:
                            # OpenAI format without 'type' field
                            text_parts.append(part.get('text', ''))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = ' '.join(text_parts)
            elif not isinstance(content, str):
                content = str(content)
            
            content = content.strip()
            
            # Skip reporting empty messages to timeline
            if not content:
                if self.logger:
                    self.logger.debug(f"⏭️ Skipping empty assistant message from live timeline")
                return
            else:
                # ✅ Log that we're reporting a non-empty message
                if self.logger:
                    self.logger.info(f"✅ Reporting assistant message to timeline (length: {len(content)}, preview: {content[:100]}...)")
        
        if self.action_callback:
            try:
                self.action_callback(item)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"⚠️ Action callback failed: {e}")
    
    def _store_model_response_to_db(self, item: Dict[str, Any]):
        """
        Store model response to database immediately when generated
        Uses the same pattern as conversation history and task_responses
        """
        try:
            # Only store if we have iteration_id
            if not self.iteration_id:
                return
            
            # Extract content from assistant message
            content = item.get('content', '')
            if isinstance(content, list):
                # Handle list format (OpenAI/Anthropic/Gemini styles)
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        # OpenAI: {"text": "..."} OR Anthropic: {"type": "text", "text": "..."}
                        if part.get('type') == 'text':
                            text_parts.append(part.get('text', ''))
                        elif 'text' in part:
                            # OpenAI format without 'type' field
                            text_parts.append(part.get('text', ''))
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = ' '.join(text_parts)
            elif not isinstance(content, str):
                content = str(content)
            
            content = content.strip()
            
            # Only store non-empty responses
            if not content:
                return
            
            # Store to database immediately
            from sqlalchemy import text
            from app.core.database_utils import get_db_session
            
            with get_db_session() as db:
                # Update last_model_response for this iteration
                update_query = text("""
                    UPDATE iterations 
                    SET last_model_response = :response 
                    WHERE uuid = :iteration_id
                """)
                db.execute(update_query, {
                    "response": content,
                    "iteration_id": self.iteration_id
                })
                db.commit()
                
                if self.logger:
                    self.logger.info(f"💾 Stored model response to DB immediately ({len(content)} chars)")
                    
        except Exception as e:
            if self.logger:
                self.logger.warning(f"⚠️ Failed to store model response to DB: {e}")
    
    @abstractmethod
    def run_full_turn(self, input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full turn with the agent
        
        This is the ONLY method the runner calls on the agent.
        The agent handles all task execution logic here.
        
        Args:
            input_items: List of conversation items from the runner
            
        Returns:
            List of response items to send back to the runner
            
        Note:
            - Runner handles Playwright initialization/termination
            - Runner handles verification after this method returns
            - Runner handles file management and logging
            - Agent only handles the actual task execution
        """
        pass
    
    def get_model_type(self) -> str:
        """
        Return the model type this agent handles
        
        Returns:
            String identifier for the model type (e.g., 'openai', 'anthropic')
        """
        return getattr(self, '_model_type', 'unknown')
    
    def validate_environment(self) -> bool:
        """
        Validate that the agent has the required environment setup
        
        Returns:
            True if environment is valid, False otherwise
        """
        if not self.computer:
            if self.logger:
                self.logger.error("❌ Agent missing computer instance")
            return False
        
        if not self.logger:
            if self.logger:
                self.logger.error("❌ Agent missing logger instance")
            return False
        
        return True