#!/usr/bin/env python3
"""
Insighter - Generic insight generation for all agents
Analyzes task execution through screenshots and CUA responses
Uses OpenAI GPT-4.1-mini with proper context management
"""

import json
import os
import time
import logging
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from app.services.computers.utils import create_response
from app.services.computers.error_handling import CriticalTimeoutError, CriticalAPIError


class Insighter:
    """
    Generic insight generator for all agents
    Analyzes task execution through screenshots and CUA responses
    Uses OpenAI GPT-4.1-mini with proper context management via previous_response_id
    """
    
    def __init__(self, logger=None, task_dir=None):
        """Initialize the insighter"""
        self.logger = logger or logging.getLogger(__name__)
        self.task_dir = task_dir
        
        # Context management
        self.previous_response_id = None
        self.conversation_history = []
        
        # Model configuration
        self.model = "gpt-4.1-mini"  # Best OpenAI model with vision capabilities
        self.summary_model = "gpt-4o"  # Use GPT-4o for final summary generation
        
        # File paths
        self.insight_file = None
        if task_dir:
            self.insight_file = Path(task_dir) / "insight_conversation.json"
        
        self.logger.info(f"✅ Insighter initialized with {self.model}")
    
    def initialize_task_context(self, task_description: str) -> bool:
        """
        Initialize context for a new task
        Sends the task description to establish context
        """
        try:
            self.logger.info("🎯 Initializing task context for insight generation")
            
            # Reset context for new task
            self.previous_response_id = None
            self.conversation_history = []
            
            # Create initial context message
            initial_message = f"""
You are an expert AI model performance analyst. You will analyze a Computer Using Agent (CUA) model's performance patterns and capabilities.

TASK CONTEXT: {task_description}

Your role:
1. Analyze the model's behavior patterns, not the specific task details
2. Identify the model's strengths and weaknesses in UI interaction
3. Assess the model's decision-making and problem-solving approach
4. Evaluate the model's efficiency and effectiveness

You will receive:
- Screenshots after each action
- CUA's reasoning/thinking (when available)
- Action results
- Summary/planning information

IMPORTANT: Respond with exactly 2 short sentences maximum for each interaction. Be SPECIFIC and SUBJECTIVE about what exactly went wrong or right. Focus on MODEL PERFORMANCE patterns like:
- Model struggles with specific UI elements (dropdowns, forms, buttons) - mention which exact element
- Model takes inefficient approaches or gets confused - describe the specific confusion
- Model shows good/bad decision-making patterns - explain the specific decision
- Model's speed, accuracy, or reliability issues - specify what was slow or inaccurate
- Model's ability to adapt and recover from errors - describe the specific error and recovery
- Model fails to follow instructions precisely (keeps default values, adds unwanted formatting) - specify what wasn't updated
- Model doesn't update text/values as requested in prompts - mention what value wasn't changed
- Model adds line breaks or formatting when not needed - describe the unwanted formatting
- Model ignores specific requirements or constraints - specify which requirement was ignored
- Model clicks in wrong locations (empty space instead of actual elements) - describe what it clicked vs what it should have clicked
- Model has poor spatial awareness for UI element targeting - specify which element was mis-targeted
- Model struggles with element activation and positioning - describe the specific positioning issue
- Model performs unnecessary actions that aren't required for the task - specify what action was unnecessary
- Model takes extra steps or clicks when not needed - describe the extra steps taken

Be specific about the exact UI elements, features, or actions involved. DO NOT mention specific task details, URLs, or content - only model capabilities and behaviors.
"""
            
            # Send initial context
            response = self._send_insight_request(
                message=initial_message,
                screenshot_data=None,
                message_type="task_initialization"
            )
            
            if response:
                self.logger.info("✅ Task context initialized successfully")
                return True
            else:
                self.logger.error("❌ Failed to initialize task context")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error initializing task context: {e}")
            return False
    
    def analyze_action(self, action_data: Dict[str, Any], screenshot_data: str = None) -> Optional[Dict[str, Any]]:
        """
        Analyze a single CUA action with screenshot
        """
        try:
            action_type = action_data.get('type', 'unknown')
            action_details = action_data.get('action', {})
            
            self.logger.info(f"🔍 Analyzing action: {action_type}")
            
            # Create analysis message
            analysis_message = f"""
CUA Model Performance Analysis:

Action Type: {action_type}
Action Details: {json.dumps(action_details, indent=2)}

Analyze the MODEL'S PERFORMANCE in this action. Be SPECIFIC and SUBJECTIVE about what exactly went wrong or right. Focus on:
1. How well the model interacted with UI elements - specify which exact element
2. Whether the model made good decisions - explain the specific decision made
3. Model's efficiency and approach - describe the specific approach taken
4. Any behavioral patterns or issues - specify the exact pattern or issue
5. Whether the model followed instructions precisely (updated values, formatting, requirements) - specify what wasn't followed
6. Model's attention to detail and instruction compliance - describe the specific detail missed
7. Model's spatial awareness and element targeting accuracy - specify which element was mis-targeted
8. Whether the model clicked in the right location to activate elements - describe what it clicked vs what it should have clicked
9. Whether this action was necessary for completing the task - specify why it was or wasn't necessary
10. Model's ability to avoid unnecessary steps or clicks - describe the specific unnecessary action
11. SERIOUS LOGICAL ERRORS: Watch for critical logical mistakes like working on wrong items (e.g., creating new items instead of working with existing ones, ignoring the actual requested item), failing to notice obvious visual cues or existing elements, making incorrect assumptions about what needs to be done, or following completely wrong workflows. Be precise about actions - distinguish between opening a page/form vs actually creating/submitting something, and avoid making assumptions about specific website features or workflows
12. Context awareness and task understanding - whether the model understands what it's actually supposed to accomplish vs what it's doing

Provide subjective assessment of the model's capabilities in exactly 2 short sentences maximum.
Be specific about the exact UI elements, features, or actions involved. Focus on model performance patterns, not task-specific details.
If the action was performed perfectly with no issues, acknowledge the excellent performance rather than forcing minor criticisms.

CRITICAL: Multi-step processes are NORMAL and CORRECT. Do NOT criticize the model for taking multiple steps to complete a task (e.g., opening a dropdown then selecting an option). Only criticize if the steps are wrong or unnecessary.
"""
            
            # Send analysis request
            response = self._send_insight_request(
                message=analysis_message,
                screenshot_data=screenshot_data,
                message_type="action_analysis"
            )
            
            if response:
                insight = {
                    'action_type': action_type,
                    'action_details': action_details,
                    'insight': response.get('content', ''),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Save to conversation history
                self._save_to_conversation_history(insight)
                
                self.logger.info(f"✅ Action analysis completed for {action_type}")
                return insight
            else:
                self.logger.warning(f"⚠️ Failed to analyze action: {action_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error analyzing action: {e}")
            return None
    
    def analyze_summary(self, summary_text: str, screenshot_data: str = None) -> Optional[Dict[str, Any]]:
        """
        Analyze CUA's reasoning/summary with screenshot
        This is called when CUA provides a summary/plan of next actions
        """
        try:
            self.logger.info("🧠 Analyzing CUA summary/planning")
            
            # Create summary analysis message
            summary_message = f"""
CUA Model Strategic Thinking Analysis:

The CUA model has provided the following reasoning/planning:

{summary_text}

This represents the model's strategic thinking and planning approach.

Analyze the MODEL'S REASONING CAPABILITIES:
1. Quality of the model's strategic thinking
2. Whether the model's approach is logical and efficient
3. Model's ability to plan and reason through problems
4. Any patterns in the model's decision-making process
5. Whether the model's reasoning shows attention to specific requirements
6. Model's ability to follow detailed instructions and constraints
7. SERIOUS LOGICAL ERRORS: Watch for critical reasoning mistakes like working on wrong items (e.g., creating new items instead of working with existing ones, ignoring the actual requested item), failing to notice obvious visual cues or existing elements, making incorrect assumptions about what needs to be done, or following completely wrong workflows. Be precise about actions - distinguish between opening a page/form vs actually creating/submitting something, and avoid making assumptions about specific website features or workflows
8. Context awareness and task understanding - whether the model understands what it's actually supposed to accomplish vs what it's planning to do

IMPORTANT: Remember that plans/summaries may require multiple actions to execute. Do not judge the correctness of a plan based on a single action - the plan might be correct but require several steps. Only judge the plan's logic and approach, not whether it was completed in one action. Also, if you previously thought a plan was incorrect but it turned out to be correct when executed, do not include that in negative findings.

CRITICAL: Multi-step processes are NORMAL and CORRECT. For example:
- Changing a dropdown value requires: 1) Opening the dropdown, 2) Selecting the option, 3) Confirming the selection
- Filling a form requires: 1) Clicking the field, 2) Typing the value, 3) Moving to next field
- Creating an item requires: 1) Opening the create page, 2) Filling fields, 3) Submitting

Do NOT criticize the model for taking multiple steps to complete a task - this is the correct approach. Only criticize if the steps are wrong or unnecessary.

Provide subjective assessment of the model's reasoning and planning capabilities in exactly 2 short sentences maximum.
Focus on model performance patterns, not task-specific details.
If the reasoning was excellent with no issues, acknowledge the strong strategic thinking rather than forcing minor criticisms.
"""
            
            # Send summary analysis request
            response = self._send_insight_request(
                message=summary_message,
                screenshot_data=screenshot_data,
                message_type="summary_analysis"
            )
            
            if response:
                insight = {
                    'summary_text': summary_text,
                    'insight': response.get('content', ''),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Save to conversation history
                self._save_to_conversation_history(insight)
                
                self.logger.info("✅ Summary analysis completed")
                return insight
            else:
                self.logger.warning("⚠️ Failed to analyze summary")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error analyzing summary: {e}")
            return None
    
    def generate_final_summary(self, verification_status: str = None) -> Optional[Dict[str, Any]]:
        """
        Generate final comprehensive summary of the entire task execution
        This is called at the end when no more actions are left
        
        Args:
            verification_status: Optional verification status ("pass" or "fail") to provide context
        """
        try:
            self.logger.info("📋 Generating final comprehensive summary")
            
            # Create final summary request
            verification_context = ""
            if verification_status:
                verification_context = f"\nVERIFICATION STATUS: The task was marked as '{verification_status.upper()}' during verification."
            
            final_message = f"""
FINAL MODEL PERFORMANCE SUMMARY REQUEST:

The CUA model has completed all actions. Based on the entire conversation history and all the screenshots and actions you've analyzed, provide a concise summary of the MODEL'S PERFORMANCE PATTERNS.{verification_context}

Provide exactly 2 paragraphs with different sentence counts:

PARAGRAPH 1 - MODEL STRENGTHS:
Write exactly 2 sentences about what the model did well, being SPECIFIC about which exact UI elements it handled well, what specific decisions were good, which approaches were efficient, what instructions it followed correctly, which elements it targeted accurately, and what specific areas showed excellence.

PARAGRAPH 2 - MODEL WEAKNESSES:
Write exactly 5 sentences about what the model struggled with, being SPECIFIC about which exact UI elements it had trouble with, what specific decisions were poor, which approaches were inefficient, what specific instructions it failed to follow, which elements it mis-targeted, what specific unnecessary actions it took, and if the model did not complete the task completely, explain WHY the model failed to complete the task (what specific issues prevented completion, what specific errors or confusions led to failure, what specific obstacles the model encountered that stopped progress). Include SPECIFIC EXAMPLES for each type of error or issue mentioned. Also watch for serious logical errors like: working on wrong items (e.g., creating new items instead of working with existing ones, ignoring the actual requested item), failing to notice obvious visual cues or existing elements, making incorrect assumptions about what needs to be done, or following wrong workflows entirely. Be precise about actions - distinguish between opening a page/form vs actually creating/submitting something, and avoid making assumptions about specific website features or workflows.

IMPORTANT: If the model performed exceptionally well with no significant issues, weaknesses, or errors, then write exactly 5 sentences acknowledging the excellent performance and stating that no meaningful weaknesses were observed. Do NOT force yourself to find minor issues or create artificial problems when the performance was genuinely good. Be honest about near-perfect or perfect performance.

CRITICAL: Multi-step processes are NORMAL and CORRECT. Do NOT criticize the model for taking multiple steps to complete tasks (e.g., opening dropdowns then selecting options, filling forms step by step, navigating through multiple pages). Only criticize if the steps are wrong, unnecessary, or lead to incorrect outcomes.

IMPORTANT: First paragraph must contain exactly 2 sentences. Second paragraph must contain exactly 5 sentences. No more, no less. No additional text, headers, or formatting. Focus on MODEL PERFORMANCE patterns that can be aggregated across multiple tasks.
DO NOT mention specific task details, URLs, or content - only model capabilities and behaviors.
"""
            
            # Send final summary request (no screenshot needed - context is already built)
            response = self._send_insight_request(
                message=final_message,
                screenshot_data=None,
                message_type="final_summary",
                use_summary_model=True
            )
            
            if response:
                final_summary = {
                    'summary': response.get('content', ''),
                    'timestamp': datetime.now().isoformat(),
                    'total_insights': len(self.conversation_history)
                }
                
                # Save to conversation history
                self._save_to_conversation_history(final_summary)
                
                # Save complete conversation to file
                self._save_conversation_to_file()
                
                self.logger.info("✅ Final summary generated successfully")
                return final_summary
            else:
                self.logger.warning("⚠️ Failed to generate final summary")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error generating final summary: {e}")
            return None
    
    def _send_insight_request(self, message: str, screenshot_data: str = None, message_type: str = "analysis", use_summary_model: bool = False) -> Optional[Dict[str, Any]]:
        """
        Send request to OpenAI GPT-4.1-mini with proper context management
        Uses previous_response_id for context continuity
        """
        try:
            # Prepare input items
            input_items = []
            
            # Add text message
            input_items.append({
                "type": "message",
                "role": "user",
                "content": message
            })
            
            # Add screenshot if provided
            if screenshot_data:
                # Handle different screenshot formats
                if isinstance(screenshot_data, bytes):
                    base64_data = base64.b64encode(screenshot_data).decode('utf-8')
                elif isinstance(screenshot_data, str) and screenshot_data.startswith('data:image/'):
                    base64_data = screenshot_data.split(',')[1]
                else:
                    base64_data = screenshot_data
                
                input_items.append({
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Here is the screenshot for analysis:"
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{base64_data}"
                        }
                    ]
                })
            
            # Prepare API call parameters
            model_to_use = self.summary_model if use_summary_model else self.model
            api_params = {
                "model": model_to_use,
                "input": input_items,
                "truncation": "auto"
            }
            
            # Add timeout for summary generation
            if use_summary_model:
                api_params["timeout"] = 600
            
            # Add previous_response_id for context management
            if self.previous_response_id:
                api_params["previous_response_id"] = self.previous_response_id
                self.logger.debug(f"🔗 Using previous_response_id: {self.previous_response_id}")
            
            # Make API call with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.logger.debug(f"📡 Sending insight request (attempt {attempt + 1}/{max_retries})")
                    
                    response = create_response(**api_params)
                    
                    if "output" in response and response["output"]:
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
                        
                        # Update previous_response_id for context management
                        if "id" in response:
                            self.previous_response_id = response["id"]
                            self.logger.debug(f"🔗 Updated previous_response_id: {self.previous_response_id}")
                        
                        # Log the interaction
                        self.logger.info(f"✅ Insight request successful ({message_type})")
                        
                        return {
                            "content": response_content,
                            "response_id": response.get("id"),
                            "message_type": message_type
                        }
                    else:
                        self.logger.warning(f"⚠️ No output in response for {message_type}")
                        return None
                        
                except Exception as api_error:
                    error_str = str(api_error)
                    
                    # Check for critical errors that should not be retried
                    if any(code in error_str for code in ["400", "401", "403", "429", "quota", "rate limit", "unauthorized", "forbidden"]):
                        self.logger.error(f"🚨 CRITICAL API ERROR: {api_error}")
                        raise CriticalAPIError(f"OpenAI API critical error: {api_error}") from api_error
                    
                    # Retry for other errors
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        self.logger.warning(f"⚠️ API error, retrying in {wait_time}s: {api_error}")
                        time.sleep(wait_time)
                    else:
                        self.logger.error(f"❌ API failed after {max_retries} attempts: {api_error}")
                        raise
                        
        except Exception as e:
            self.logger.error(f"❌ Error sending insight request: {e}")
            return None
    
    def _save_to_conversation_history(self, insight: Dict[str, Any]) -> None:
        """Save insight to conversation history"""
        try:
            self.conversation_history.append(insight)
            self.logger.debug(f"💾 Saved insight to conversation history (total: {len(self.conversation_history)})")
        except Exception as e:
            self.logger.warning(f"⚠️ Error saving to conversation history: {e}")
    
    def _save_conversation_to_file(self) -> None:
        """Save complete conversation to file"""
        try:
            if not self.insight_file:
                self.logger.warning("⚠️ No insight file path available")
                return
            
            # Create conversation data
            conversation_data = {
                'task_start_time': self.conversation_history[0].get('timestamp') if self.conversation_history else None,
                'task_end_time': datetime.now().isoformat(),
                'total_insights': len(self.conversation_history),
                'conversation_history': self.conversation_history,
                'model_used': self.model,
                'previous_response_id': self.previous_response_id
            }
            
            # Save to file
            with open(self.insight_file, 'w') as f:
                json.dump(conversation_data, f, indent=2, default=str)
            
            self.logger.info(f"💾 Conversation saved to: {self.insight_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving conversation to file: {e}")
    
    def has_context(self) -> bool:
        """Check if insighter has built up context for summary generation"""
        return self.previous_response_id is not None
    
    def generate_summary_if_context_exists(self, verification_status: str = None) -> Optional[str]:
        """
        Generate final summary if context exists, regardless of task completion status
        This is called when task crashes but insighter has built up context
        
        Args:
            verification_status: Optional verification status ("pass" or "fail") to provide context
        """
        if not self.has_context():
            self.logger.info("ℹ️ No context available for summary generation")
            return None
        
        try:
            self.logger.info("📋 Generating summary from existing context (task crashed but context available)")
            final_summary = self.generate_final_summary(verification_status)
            if final_summary:
                return final_summary.get('summary', '')
            else:
                return None
        except Exception as e:
            self.logger.error(f"❌ Error generating summary from context: {e}")
            return None
    
    def cleanup_resources(self) -> None:
        """Clean up insighter resources"""
        try:
            # Save any remaining conversation data
            if self.conversation_history:
                self._save_conversation_to_file()
            
            # Clear references
            self.conversation_history = []
            self.previous_response_id = None
            
            self.logger.info("🧹 Insighter resources cleaned up")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error cleaning up insighter resources: {e}")
