#!/usr/bin/env python3
"""
Summary Service - Orchestrates execution and batch summary generation
Main service that coordinates meta-summarization after each iteration
"""

import logging
import time
from typing import Dict, List, Optional, Any
from .meta_summarizer import execution_summarizer, batch_summarizer
from .summary_manager import summary_manager


class SummaryService:
    """
    Main service for generating execution and batch summaries
    """
    
    def __init__(self, logger=None):
        """Initialize the summary service"""
        self.logger = logger or logging.getLogger(__name__)
        
    def generate_summaries_after_iteration(self, execution_id: str) -> bool:
        """
        Generate both execution and batch summaries after an iteration completes
        
        Args:
            execution_id: Execution UUID
            
        Returns:
            True if both summaries generated successfully, False otherwise
        """
        try:
            self.logger.info(f"🔄 Starting summary generation for execution {execution_id}")
            
            # Get execution info to find batch_id and model
            execution_info = summary_manager.get_execution_info(execution_id)
            if not execution_info:
                self.logger.error(f"❌ Could not get execution info for {execution_id}")
                return False
            
            batch_id = execution_info["batch_id"]
            model = execution_info["model"]
            
            self.logger.info(f"📊 Execution {execution_id} belongs to batch {batch_id} with model {model}")
            
            # Generate execution summary
            execution_success = self._generate_execution_summary(execution_id)
            
            # Generate batch summary (only if batch_id is not None - skip for playground executions)
            batch_success = True  # Default to True if no batch (playground execution)
            if batch_id is not None:
                batch_success = self._generate_batch_summary(batch_id)
            else:
                self.logger.info(f"⏭️ Skipping batch summary generation for playground execution {execution_id}")
            
            if execution_success and batch_success:
                self.logger.info(f"✅ Both summaries generated successfully for execution {execution_id}")
                return True
            else:
                self.logger.warning(f"⚠️ Partial summary generation for execution {execution_id} - execution: {execution_success}, batch: {batch_success}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error generating summaries for execution {execution_id}: {e}")
            return False
    
    def _generate_execution_summary(self, execution_id: str) -> bool:
        """
        Generate execution summary from iteration insights
        
        Args:
            execution_id: Execution UUID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"📋 Generating execution summary for {execution_id}")
            
            # Get all iteration insights for this execution
            iteration_insights = summary_manager.get_execution_insights(execution_id)
            
            if not iteration_insights:
                self.logger.warning(f"No iteration insights found for execution {execution_id}")
                return False
            
            # Generate execution summary
            summary = execution_summarizer.generate_execution_summary(execution_id, iteration_insights)
            
            if not summary:
                self.logger.error(f"Failed to generate execution summary for {execution_id}")
                return False
            
            # Update database
            success = summary_manager.update_execution_summary(execution_id, summary)
            
            if success:
                self.logger.info(f"✅ Execution summary generated and saved for {execution_id}")
            else:
                self.logger.error(f"❌ Failed to save execution summary for {execution_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error generating execution summary for {execution_id}: {e}")
            return False
    
    def _generate_batch_summary(self, batch_id: str) -> bool:
        """
        Generate batch summary from execution summaries
        
        Args:
            batch_id: Batch UUID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"📊 Generating batch summary for {batch_id}")
            
            # Get execution insights grouped by model
            model_executions = summary_manager.get_batch_execution_insights(batch_id)
            
            if not model_executions:
                self.logger.warning(f"No execution summaries found for batch {batch_id}")
                return False
            
            # Generate batch summaries for each model
            model_summaries = batch_summarizer.generate_batch_summary(batch_id, model_executions)
            
            if not model_summaries:
                self.logger.error(f"Failed to generate batch summaries for {batch_id}")
                return False
            
            # Update database
            success = summary_manager.update_batch_summary(batch_id, model_summaries)
            
            if success:
                self.logger.info(f"✅ Batch summaries generated and saved for {batch_id} with {len(model_summaries)} models")
            else:
                self.logger.error(f"❌ Failed to save batch summaries for {batch_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error generating batch summary for {batch_id}: {e}")
            return False
    
    def generate_execution_summary_only(self, execution_id: str) -> bool:
        """
        Generate only execution summary (for testing or manual triggers)
        
        Args:
            execution_id: Execution UUID
            
        Returns:
            True if successful, False otherwise
        """
        return self._generate_execution_summary(execution_id)
    
    def generate_batch_summary_only(self, batch_id: str) -> bool:
        """
        Generate only batch summary (for testing or manual triggers)
        
        Args:
            batch_id: Batch UUID
            
        Returns:
            True if successful, False otherwise
        """
        return self._generate_batch_summary(batch_id)


# Global instance
summary_service = SummaryService()
