#!/usr/bin/env python3
"""
Meta-Summarizer - Generates execution and batch-level summaries
Analyzes multiple iteration insights to create higher-level performance summaries
Uses OpenAI GPT-4.1-mini for meta-analysis
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.services.computers.utils import create_response
from app.services.computers.error_handling import CriticalAPIError


def _track_summarizer_token_usage(usage_data: Dict, execution_id: str, model_version: str = "gpt-4.1-mini"):
    """
    Track token usage for summarizer API calls
    
    Args:
        usage_data: Usage dictionary from OpenAI response
        execution_id: Execution UUID
        model_version: Model version used for the summary
    """
    try:
        from app.core.database_utils import get_db_session
        from sqlalchemy import text
        
        # Extract token counts (handle both input_tokens and prompt_tokens)
        input_tokens = usage_data.get('input_tokens') or usage_data.get('prompt_tokens', 0)
        output_tokens = usage_data.get('output_tokens') or usage_data.get('completion_tokens', 0)
        total_tokens = usage_data.get('total_tokens', input_tokens + output_tokens)
        cached_tokens = usage_data.get('cached_tokens', 0)
        
        # Get first iteration_id from this execution for tracking
        with get_db_session() as db:
            # Get first iteration from execution
            iter_query = text("""
                SELECT uuid FROM iterations 
                WHERE execution_id = :execution_id 
                ORDER BY iteration_number ASC 
                LIMIT 1
            """)
            result = db.execute(iter_query, {'execution_id': execution_id})
            row = result.fetchone()
            
            if not row:
                logging.warning(f"No iterations found for execution {execution_id}, skipping token tracking")
                return
            
            iteration_id = str(row.uuid)
            
            # Fetch execution, batch, and gym to snapshot context
            exec_row = db.execute(text("""
                SELECT e.batch_id, e.gym_id, b.name AS batch_name, g.name AS gym_name
                FROM executions e
                LEFT JOIN batches b ON b.uuid = e.batch_id
                LEFT JOIN gyms g ON g.uuid = e.gym_id
                WHERE e.uuid = :execution_id
            """), {'execution_id': execution_id}).fetchone()
            snap_batch_id = exec_row.batch_id if exec_row else None
            snap_gym_id = exec_row.gym_id if exec_row else None
            snap_batch_name = exec_row.batch_name if exec_row else None
            snap_gym_name = exec_row.gym_name if exec_row else None

            # Insert token usage with snapshot fields so monitoring sees new batches immediately
            insert_query = text("""
                INSERT INTO token_usage (
                    uuid, iteration_id, execution_id, batch_id, gym_id, batch_name, gym_name,
                    model_name, model_version,
                    input_tokens, output_tokens, total_tokens, api_calls_count,
                    cached_tokens, estimated_cost_usd
                ) VALUES (
                    gen_random_uuid(), :iteration_id, :execution_id, :batch_id, :gym_id, :batch_name, :gym_name,
                    :model_name, :model_version,
                    :input_tokens, :output_tokens, :total_tokens, :api_calls_count,
                    :cached_tokens, :estimated_cost_usd
                )
            """)
            
            db.execute(insert_query, {
                'iteration_id': iteration_id,
                'execution_id': str(execution_id),
                'batch_id': str(snap_batch_id) if snap_batch_id else None,
                'gym_id': str(snap_gym_id) if snap_gym_id else None,
                'batch_name': snap_batch_name,
                'gym_name': snap_gym_name,
                'model_name': 'openai',
                'model_version': model_version,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'api_calls_count': 1,
                'cached_tokens': cached_tokens,
                'estimated_cost_usd': 0.0
            })
            db.commit()
            
            logging.info(f"✅ Summarizer token usage tracked: {total_tokens} tokens (input: {input_tokens}, output: {output_tokens})")
            
    except Exception as e:
        logging.error(f"❌ Failed to track summarizer token usage: {e}")


class ExecutionSummarizer:
    """
    Generates execution-level summaries by analyzing all iteration insights
    """
    
    def __init__(self, logger=None):
        """Initialize the execution summarizer"""
        self.logger = logger or logging.getLogger(__name__)
        self.model = "gpt-4.1-mini"
        
    def generate_execution_summary(self, execution_id: str, iteration_insights: List[str]) -> Optional[str]:
        """
        Generate execution summary from iteration insights
        
        Args:
            execution_id: Execution UUID
            iteration_insights: List of eval_insights strings from iterations
            
        Returns:
            Generated summary string or None if failed
        """
        try:
            if not iteration_insights or not any(insights.strip() for insights in iteration_insights):
                self.logger.warning(f"No valid insights found for execution {execution_id}")
                return None
            
            # Filter out empty insights
            valid_insights = [insights.strip() for insights in iteration_insights if insights and insights.strip()]
            
            if not valid_insights:
                self.logger.warning(f"No valid insights to summarize for execution {execution_id}")
                return None
            
            self.logger.info(f"Generating execution summary for {execution_id} from {len(valid_insights)} iterations")
            
            # Create prompt for execution summary
            insights_text = "\n\n--- ITERATION INSIGHTS ---\n\n".join([
                f"ITERATION {i+1}:\n{insight}" for i, insight in enumerate(valid_insights)
            ])
            
            prompt = f"""
You are analyzing execution summaries from multiple iterations of the same task performed by a Computer Using Agent (CUA) model.

EXECUTION CONTEXT: This execution ran {len(valid_insights)} iterations of the same task.

ITERATION INSIGHTS TO ANALYZE:
{insights_text}

Your task is to provide a meta-analysis of the model's performance across all iterations.

Provide exactly 2 paragraphs with different sentence counts:

PARAGRAPH 1 - MODEL STRENGTHS ACROSS ITERATIONS:
Write exactly 2 sentences about what the model did well consistently across iterations, being SPECIFIC about which UI elements it handled well, what specific decisions were good, which approaches were efficient, what instructions it followed correctly, and what specific areas showed excellence across multiple attempts.

PARAGRAPH 2 - MODEL WEAKNESSES ACROSS ITERATIONS:
Write exactly 5 sentences about what the model struggled with consistently across iterations, being SPECIFIC about which UI elements it had trouble with, what specific decisions were poor, which approaches were inefficient, what specific instructions it failed to follow, and what specific patterns of failure or confusion emerged across multiple attempts. Include SPECIFIC EXAMPLES for each type of error or issue mentioned. Also watch for serious logical errors like: working on wrong items (e.g., creating new items instead of working with existing ones, ignoring the actual requested item), failing to notice obvious visual cues or existing elements, making incorrect assumptions about what needs to be done, or following wrong workflows entirely. Be precise about actions - distinguish between opening a page/form vs actually creating/submitting something, and avoid making assumptions about specific website features or workflows.

IMPORTANT: If the model performed exceptionally well across iterations with no significant issues, weaknesses, or errors, then write exactly 5 sentences acknowledging the excellent performance and stating that no meaningful weaknesses were observed across iterations. Do NOT force yourself to find minor issues or create artificial problems when the performance was genuinely good. Be honest about near-perfect or perfect performance.

CRITICAL: Multi-step processes are NORMAL and CORRECT. Do NOT criticize the model for taking multiple steps to complete tasks (e.g., opening dropdowns then selecting options, filling forms step by step, navigating through multiple pages). Only criticize if the steps are wrong, unnecessary, or lead to incorrect outcomes.

IMPORTANT: 
- First paragraph must contain exactly 2 sentences. Second paragraph must contain exactly 5 sentences. No more, no less.
- Be subjective and focus on MODEL PERFORMANCE patterns that can be aggregated across multiple tasks.
- Focus on consistency and patterns across iterations, not individual iteration details.
- DO NOT mention specific task details, URLs, or content - only model capabilities and behaviors.
"""
            
            # Send request to OpenAI with token tracking
            response = self._send_summary_request(prompt, "execution_summary", execution_id)
            
            if response:
                self.logger.info(f"✅ Execution summary generated for {execution_id}")
                return response
            else:
                self.logger.error(f"❌ Failed to generate execution summary for {execution_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error generating execution summary for {execution_id}: {e}")
            return None
    
    def _send_summary_request(self, prompt: str, summary_type: str, execution_id: str = None) -> Optional[str]:
        """
        Send request to OpenAI for summary generation
        
        Args:
            prompt: The prompt to send
            summary_type: Type of summary for logging
            execution_id: Execution UUID for token tracking
            
        Returns:
            Generated summary or None if failed
        """
        try:
            # Prepare input items
            input_items = [{
                "type": "message",
                "role": "user",
                "content": prompt
            }]
            
            # Prepare API call parameters
            api_params = {
                "model": self.model,
                "input": input_items,
                "truncation": "auto"
            }
            
            # Make API call with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.logger.debug(f"📡 Sending {summary_type} request (attempt {attempt + 1}/{max_retries})")
                    
                    response = create_response(**api_params)
                    
                    if "output" in response and response["output"]:
                        # Track token usage if execution_id provided
                        if execution_id and "usage" in response:
                            try:
                                _track_summarizer_token_usage(response["usage"], execution_id, self.model)
                            except Exception as track_error:
                                self.logger.warning(f"⚠️ Failed to track token usage: {track_error}")
                        
                        # Extract response content
                        response_content = ""
                        for item in response["output"]:
                            if item.get("type") == "message" and item.get("role") == "assistant":
                                content = item.get("content", "")
                                if isinstance(content, list):
                                    for content_item in content:
                                        if content_item.get("type") == "output_text":
                                            response_content += content_item.get("text", "")
                                else:
                                    response_content += str(content)
                        
                        self.logger.info(f"✅ {summary_type} request successful")
                        return response_content.strip()
                    else:
                        self.logger.warning(f"⚠️ No output in response for {summary_type}")
                        return None
                        
                except Exception as api_error:
                    error_str = str(api_error)
                    
                    # Check for critical errors that should not be retried
                    if any(code in error_str for code in ["400", "401", "403", "429", "quota", "rate limit", "unauthorized", "forbidden"]):
                        self.logger.error(f"🚨 CRITICAL API ERROR for {summary_type}: {api_error}")
                        raise CriticalAPIError(f"OpenAI API critical error: {api_error}") from api_error
                    
                    # Retry for other errors
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        self.logger.warning(f"⚠️ API error for {summary_type}, retrying in {wait_time}s: {api_error}")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(f"❌ API failed after {max_retries} attempts for {summary_type}: {api_error}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"❌ Error sending {summary_type} request: {e}")
            return None


class BatchSummarizer:
    """
    Generates batch-level summaries by analyzing all execution summaries for each model
    """
    
    def __init__(self, logger=None):
        """Initialize the batch summarizer"""
        self.logger = logger or logging.getLogger(__name__)
        self.model = "gpt-4.1-mini"
        
    def generate_batch_summary(self, batch_id: str, model_executions: Dict[str, List[str]]) -> Optional[Dict[str, str]]:
        """
        Generate batch summary for each model
        
        Args:
            batch_id: Batch UUID
            model_executions: Dict mapping model names to lists of execution summaries
            
        Returns:
            Dict mapping model names to their summaries, or None if failed
        """
        try:
            if not model_executions:
                self.logger.warning(f"No execution summaries found for batch {batch_id}")
                return None
            
            batch_summaries = {}
            
            for model_name, execution_summaries in model_executions.items():
                if not execution_summaries or not any(summary.strip() for summary in execution_summaries):
                    self.logger.warning(f"No valid execution summaries found for model {model_name} in batch {batch_id}")
                    continue
                
                # Filter out empty summaries
                valid_summaries = [summary.strip() for summary in execution_summaries if summary and summary.strip()]
                
                if not valid_summaries:
                    self.logger.warning(f"No valid summaries to analyze for model {model_name} in batch {batch_id}")
                    continue
                
                self.logger.info(f"Generating batch summary for model {model_name} in batch {batch_id} from {len(valid_summaries)} executions")
                
                # Create prompt for batch summary
                summaries_text = "\n\n--- EXECUTION SUMMARIES ---\n\n".join([
                    f"EXECUTION {i+1}:\n{summary}" for i, summary in enumerate(valid_summaries)
                ])
                
                prompt = f"""
You are analyzing execution summaries from different executions of the same tasks performed by a {model_name.upper()} Computer Using Agent (CUA) model.

BATCH CONTEXT: This batch ran {len(valid_summaries)} executions with the {model_name.upper()} model across different tasks.

EXECUTION SUMMARIES TO ANALYZE:
{summaries_text}

Your task is to provide a meta-analysis of the {model_name.upper()} model's performance across all executions in this batch.

Provide exactly 2 paragraphs with different sentence counts:

PARAGRAPH 1 - {model_name.upper()} MODEL STRENGTHS ACROSS EXECUTIONS:
Write exactly 2 sentences about what the {model_name.upper()} model did well consistently across executions, being SPECIFIC about which UI elements it handled well, what specific decisions were good, which approaches were efficient, what instructions it followed correctly, and what specific areas showed excellence across multiple tasks.

PARAGRAPH 2 - {model_name.upper()} MODEL WEAKNESSES ACROSS EXECUTIONS:
Write exactly 5 sentences about what the {model_name.upper()} model struggled with consistently across executions, being SPECIFIC about which UI elements it had trouble with, what specific decisions were poor, which approaches were inefficient, what specific instructions it failed to follow, and what specific patterns of failure or confusion emerged across multiple tasks. Include SPECIFIC EXAMPLES for each type of error or issue mentioned. Also watch for serious logical errors like: working on wrong items (e.g., creating new items instead of working with existing ones, ignoring the actual requested item), failing to notice obvious visual cues or existing elements, making incorrect assumptions about what needs to be done, or following wrong workflows entirely. Be precise about actions - distinguish between opening a page/form vs actually creating/submitting something, and avoid making assumptions about specific website features or workflows.

IMPORTANT: If the {model_name.upper()} model performed exceptionally well across executions with no significant issues, weaknesses, or errors, then write exactly 5 sentences acknowledging the excellent performance and stating that no meaningful weaknesses were observed across executions. Do NOT force yourself to find minor issues or create artificial problems when the performance was genuinely good. Be honest about near-perfect or perfect performance.

CRITICAL: Multi-step processes are NORMAL and CORRECT. Do NOT criticize the model for taking multiple steps to complete tasks (e.g., opening dropdowns then selecting options, filling forms step by step, navigating through multiple pages). Only criticize if the steps are wrong, unnecessary, or lead to incorrect outcomes.

IMPORTANT: 
- First paragraph must contain exactly 2 sentences. Second paragraph must contain exactly 5 sentences. No more, no less.
- Be subjective and focus on {model_name.upper()} MODEL PERFORMANCE patterns that can be aggregated across multiple tasks.
- Focus on consistency and patterns across executions, not individual execution details.
- DO NOT mention specific task details, URLs, or content - only model capabilities and behaviors.
- This summary is specifically for the {model_name.upper()} model's performance in this batch.
"""
                
                # Send request to OpenAI with token tracking (use batch_id as execution_id for tracking)
                response = self._send_summary_request(prompt, f"batch_summary_{model_name}", batch_id)
                
                if response:
                    batch_summaries[model_name] = response
                    self.logger.info(f"✅ Batch summary generated for model {model_name} in batch {batch_id}")
                else:
                    self.logger.error(f"❌ Failed to generate batch summary for model {model_name} in batch {batch_id}")
            
            if batch_summaries:
                self.logger.info(f"✅ Batch summaries generated for {len(batch_summaries)} models in batch {batch_id}")
                return batch_summaries
            else:
                self.logger.error(f"❌ No batch summaries generated for batch {batch_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error generating batch summary for {batch_id}: {e}")
            return None
    
    def _send_summary_request(self, prompt: str, summary_type: str, batch_id: str = None) -> Optional[str]:
        """
        Send request to OpenAI for summary generation
        
        Args:
            prompt: The prompt to send
            summary_type: Type of summary for logging
            batch_id: Batch UUID for token tracking
            
        Returns:
            Generated summary or None if failed
        """
        try:
            # Prepare input items
            input_items = [{
                "type": "message",
                "role": "user",
                "content": prompt
            }]
            
            # Prepare API call parameters
            api_params = {
                "model": self.model,
                "input": input_items,
                "truncation": "auto"
            }
            
            # Make API call with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.logger.debug(f"📡 Sending {summary_type} request (attempt {attempt + 1}/{max_retries})")
                    
                    response = create_response(**api_params)
                    
                    if "output" in response and response["output"]:
                        # Track token usage if batch_id provided
                        # For batch summaries, get first execution from batch for tracking
                        if batch_id and "usage" in response:
                            try:
                                from app.core.database_utils import get_db_session
                                from sqlalchemy import text
                                
                                # Get first execution from batch
                                with get_db_session() as db:
                                    exec_query = text("""
                                        SELECT uuid FROM executions 
                                        WHERE batch_id = :batch_id 
                                        ORDER BY created_at ASC 
                                        LIMIT 1
                                    """)
                                    result = db.execute(exec_query, {'batch_id': batch_id})
                                    row = result.fetchone()
                                    
                                    if row:
                                        execution_id = str(row.uuid)
                                        _track_summarizer_token_usage(response["usage"], execution_id, self.model)
                            except Exception as track_error:
                                self.logger.warning(f"⚠️ Failed to track token usage: {track_error}")
                        
                        # Extract response content
                        response_content = ""
                        for item in response["output"]:
                            if item.get("type") == "message" and item.get("role") == "assistant":
                                content = item.get("content", "")
                                if isinstance(content, list):
                                    for content_item in content:
                                        if content_item.get("type") == "output_text":
                                            response_content += content_item.get("text", "")
                                else:
                                    response_content += str(content)
                        
                        self.logger.info(f"✅ {summary_type} request successful")
                        return response_content.strip()
                    else:
                        self.logger.warning(f"⚠️ No output in response for {summary_type}")
                        return None
                        
                except Exception as api_error:
                    error_str = str(api_error)
                    
                    # Check for critical errors that should not be retried
                    if any(code in error_str for code in ["400", "401", "403", "429", "quota", "rate limit", "unauthorized", "forbidden"]):
                        self.logger.error(f"🚨 CRITICAL API ERROR for {summary_type}: {api_error}")
                        raise CriticalAPIError(f"OpenAI API critical error: {api_error}") from api_error
                    
                    # Retry for other errors
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        self.logger.warning(f"⚠️ API error for {summary_type}, retrying in {wait_time}s: {api_error}")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(f"❌ API failed after {max_retries} attempts for {summary_type}: {api_error}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"❌ Error sending {summary_type} request: {e}")
            return None


# Global instances
execution_summarizer = ExecutionSummarizer()
batch_summarizer = BatchSummarizer()
