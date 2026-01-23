#!/usr/bin/env python3
"""
OpenAI Agent - Independent implementation extracted from V1 Agent

OpenAI Computer Use API handles all token optimization server-side via previous_response_id.
Most efficient architecture - no manual optimization needed.
"""

import json
import time
import logging
from typing import Any, Dict, List, Callable
from pathlib import Path

from app.core.config import settings
from app.services.computers import Computer
from app.services.computers.utils import (check_blocklisted_url,
                                          create_response, pp, show_image)
from app.services.computers.error_handling import CriticalTimeoutError, CriticalAPIError
from .base_agent import BaseAgent
from ..helpers.screenshot_helper import ScreenshotHelper
from ..insights.insighter import Insighter


class OpenAIAgent(BaseAgent):
    """OpenAI agent - independent implementation extracted from V1 Agent"""
    
    def __init__(self, computer=None, tools=None, acknowledge_safety_check_callback=None, logger=None, task_dir=None, critical_error_tracker=None, iteration_id=None, execution_id=None):
        """Initialize the OpenAI agent with independent implementation"""
        super().__init__(computer, logger, task_dir)
        
        # Set model type
        self._model_type = 'openai'
        
        # Store parameters
        self.tools = []
        self.print_steps = True
        self.debug = False
        self.show_images = False
        self.acknowledge_safety_check_callback = acknowledge_safety_check_callback or (lambda _: True)
        self.critical_error_tracker = critical_error_tracker
        
        # Store IDs for token tracking
        self.iteration_id = iteration_id
        self.execution_id = execution_id
        
        # Initialize tools from computer
        if computer:
            w, h = computer.get_dimensions()
            self.tools.append(
                {
                    "type": "computer_use_preview",
                    "display_width": w,
                    "display_height": h,
                    "environment": computer.get_environment(),
                }
            )
        
        # Initialize screenshot helper
        self.screenshot_helper = None
        if task_dir:
            # Create screenshots directory if it doesn't exist
            Path(task_dir).mkdir(parents=True, exist_ok=True)
            (Path(task_dir) / "screenshots").mkdir(parents=True, exist_ok=True)
            
            # Store the task directory for screenshot saving
            self.screenshot_dir = str(Path(task_dir) / "screenshots")
            
            # Initialize screenshot helper
            self.screenshot_helper = ScreenshotHelper(self.screenshot_dir, logger)
        
        # Initialize insighter for insight generation (will be initialized later if task_dir is None)
        self.insighter = None
        if task_dir:
            # self.insighter = Insighter(logger=self.logger, task_dir=task_dir)
            self.logger.info("✅ Insighter initialized for OpenAI agent")
        else:
            self.logger.info("ℹ️ Insighter will be initialized later when task directory is available")
        
        # Initialize insights storage
        self.final_insights = None
        
        # Token optimization: OpenAI Computer Use API handles everything server-side
        # No client-side optimization needed (more efficient than manual management)
        self.current_iteration = 0  # Track iteration for logging/debugging
        
        if self.logger:
            self.logger.info("✅ OpenAI agent initialized with independent implementation")
            self.logger.info("🚀 Token optimization: Server-side context management (native, most efficient)")
    
    def debug_print(self, *args):
        """Debug print method"""
        if self.debug:
            pp(*args)
    
    def update_task_directory(self, task_dir: str) -> None:
        """Update task directory and reinitialize insighter if needed"""
        if task_dir and not self.insighter:
            # Initialize insighter if it wasn't initialized before
            # self.insighter = Insighter(logger=self.logger, task_dir=task_dir)
            self.logger.info("✅ Insighter initialized for OpenAI agent (late initialization)")
        elif task_dir and self.insighter:
            # Update insighter's task directory
            self.insighter.task_dir = task_dir
            self.insighter.insight_file = Path(task_dir) / "insight_conversation.json"
            self.logger.info("✅ Insighter task directory updated")
    
    def initialize_insight_context(self, task_description: str) -> bool:
        """Initialize insight generation context for the task"""
        if self.insighter:
            return self.insighter.initialize_task_context(task_description)
        else:
            self.logger.warning("⚠️ Insighter not available for context initialization")
            return False
    
    def _create_response_with_retry(self, max_retries=3, **kwargs):
        """
        Wrapper for create_response with retry logic.
        Retries up to max_retries times for any API error.
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"API call attempt {attempt + 1}/{max_retries}")
                response = create_response(**kwargs)
                
                # ✅ Debug: Log response structure
                self.logger.debug(f"OpenAI API response keys: {list(response.keys())}")
                
                # ✅ Better error handling with detailed logging
                if "output" not in response:
                    # Log the full response to understand what went wrong
                    if "error" in response:
                        error_msg = response.get("error", {})
                        error_detail = error_msg.get("message", str(error_msg))
                        self.logger.error(f"OpenAI API error: {error_detail}")
                        raise ValueError(f"OpenAI API error: {error_detail}")
                    else:
                        self.logger.error(f"No 'output' field in response. Response keys: {list(response.keys())}")
                        self.logger.error(f"Full response: {json.dumps(response, indent=2, default=str)[:500]}")
                        raise ValueError(f"No output from model. Response structure: {list(response.keys())}")
                
                # Track token usage if IDs are available
                if self.iteration_id and self.execution_id:
                    try:
                        from app.core.database_utils import get_db_session
                        from sqlalchemy import text
                        import json
                        
                        # Extract token counts from response
                        usage = response.get('usage', {})
                        
                        # Computer-Use Preview API uses input_tokens/output_tokens
                        # Standard API uses prompt_tokens/completion_tokens
                        # Try both formats
                        input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens', 0) or 0
                        output_tokens = usage.get('output_tokens') or usage.get('completion_tokens', 0) or 0
                        total_tokens = usage.get('total_tokens', None) or (input_tokens + output_tokens)
                        
                        # Handle cached tokens (different formats)
                        if 'prompt_tokens_details' in usage:
                            cached_tokens = usage.get('prompt_tokens_details', {}).get('cached_tokens', 0) or 0
                        else:
                            cached_tokens = usage.get('cached_tokens', 0) or 0
                        
                        # Track synchronously with retry logic for connection timeouts
                        max_retries = 3
                        retry_delay = 1
                        db_succeeded = False
                        last_error = None
                        
                        for attempt in range(max_retries):
                            try:
                                with get_db_session() as db:
                                    query = text("""
                                        INSERT INTO token_usage (
                                            uuid, iteration_id, execution_id, model_name, model_version,
                                            input_tokens, output_tokens, total_tokens, api_calls_count,
                                            cached_tokens, estimated_cost_usd
                                        ) VALUES (
                                            gen_random_uuid(), :iteration_id, :execution_id, :model_name, :model_version,
                                            :input_tokens, :output_tokens, :total_tokens, :api_calls_count,
                                            :cached_tokens, :estimated_cost_usd
                                        )
                                    """)
                                    
                                    db.execute(query, {
                                        'iteration_id': str(self.iteration_id),
                                        'execution_id': str(self.execution_id),
                                        'model_name': 'openai',
                                        'model_version': 'computer-use-preview',
                                        'input_tokens': input_tokens,
                                        'output_tokens': output_tokens,
                                        'total_tokens': total_tokens,
                                        'api_calls_count': 1,
                                        'cached_tokens': cached_tokens,
                                        'estimated_cost_usd': 0.0
                                    })
                                    # Note: get_db_session() context manager handles commit automatically
                                
                                db_succeeded = True
                                self.logger.info(f"✅ Token usage tracked: {total_tokens} tokens (input: {input_tokens}, output: {output_tokens})")
                                break  # Success, exit retry loop
                                
                            except Exception as db_error:
                                last_error = db_error
                                # Check if it's a connection/timeout error that should be retried
                                is_connection_error = (
                                    "timeout" in str(db_error).lower() or
                                    "connection" in str(db_error).lower() or
                                    "OperationalError" in str(type(db_error).__name__) or
                                    "InvalidatePoolError" in str(type(db_error).__name__)
                                )
                                
                                if is_connection_error and attempt < max_retries - 1:
                                    self.logger.warning(f"⚠️ Database connection error (attempt {attempt + 1}/{max_retries}): {db_error}. Retrying in {retry_delay}s...")
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff
                                else:
                                    # DB operation failed - log with details but NEVER block execution
                                    self.logger.warning(f"⚠️ Token tracking DB operation failed: {type(db_error).__name__}: {db_error}")
                                    break  # Exit retry loop, continue execution
                        
                        # Log final failure state if operation didn't succeed (useful for debugging)
                        if not db_succeeded and last_error:
                            self.logger.debug(f"🔍 Token tracking final state: failed after {max_retries} attempts. Last error: {last_error}")
                    except Exception as track_error:
                        self.logger.error(f"❌ Failed to track token usage: {track_error}", exc_info=True)
                
                return response
            except Exception as e:
                last_exception = e
                self.logger.warning(f"API call attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    # Wait before retrying (exponential backoff)
                    wait_time = 2 ** attempt
                    self.logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"All {max_retries} API call attempts failed")
        
        # If we get here, all retries failed - raise CriticalAPIError to crash immediately
        raise CriticalAPIError(f"OpenAI API call failed after {max_retries} attempts. Last error: {str(last_exception)}") from last_exception
    
    def handle_item(self, item):
        """Handle each output item; may execute a computer action and return outputs."""
        outputs = []

        if item["type"] == "message":
            if self.print_steps:
                self.logger.info(item["content"][0]["text"])

        elif item["type"] == "function_call":
            name, args = item["name"], json.loads(item["arguments"])
            if self.print_steps:
                self.logger.info(f"{name}({args})")

            if hasattr(self.computer, name):
                # Call the method directly on the computer object to preserve decorators
                try:
                    method = getattr(self.computer, name)
                    method(**args)
                except Exception as error:
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, f"function_call_{name} failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        raise RuntimeError(f"CRITICAL FUNCTION CALL FAILURE in {name}: {error}") from error

            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": item["call_id"],
                    "output": "success",
                }
            )

        elif item["type"] == "computer_call":
            action = item["action"]
            action_type = action["type"]
            normalized_coordinate_actions = {
                'click_at',
                'type_text_at',
                'hover_at',
                'scroll_at',
                'drag_and_drop',
            }
            action_uses_normalized = action_type in normalized_coordinate_actions
            action_args = {k: v for k, v in action.items() if k != "type"}
            if self.print_steps:
                self.logger.info(f"{action_type}({action_args})")
            
            # Enrich the item with action details for conversation history
            # Extract coordinates, text, etc. from action args
            if 'x' in action_args and 'y' in action_args:
                item['coordinates'] = [action_args['x'], action_args['y']]
                item['coordinates_normalized'] = action_uses_normalized
            elif 'coordinate' in action_args:
                item['coordinates'] = action_args['coordinate']
                item['coordinates_normalized'] = action_uses_normalized
            
            if 'start_coordinate' in action_args:
                item['start_coordinates'] = action_args['start_coordinate']
            elif 'start_x' in action_args and 'start_y' in action_args:
                item['start_coordinates'] = [action_args['start_x'], action_args['start_y']]
            
            # Destination/target coordinates (drag/drop/move)
            if 'destination_x' in action_args and 'destination_y' in action_args:
                item['target_coordinates'] = [action_args['destination_x'], action_args['destination_y']]
                item['target_coordinates_normalized'] = action_uses_normalized
            elif 'target_coordinate' in action_args:
                item['target_coordinates'] = action_args['target_coordinate']
                item['target_coordinates_normalized'] = action_uses_normalized
            elif 'destination_coordinate' in action_args:
                item['target_coordinates'] = action_args['destination_coordinate']
                item['target_coordinates_normalized'] = action_uses_normalized
            
            if 'text' in action_args:
                item['text'] = action_args['text']
            
            # ✅ Extract key/keys for keypress actions
            if 'key' in action_args:
                item['key'] = action_args['key']
            elif 'keys' in action_args:
                item['key'] = action_args['keys']  # Store as 'key' for consistency
            
            # Scroll semantics: derive direction/amount from scroll_x/scroll_y when present
            if action_type == "scroll":
                scroll_x = action_args.get("scroll_x", 0)
                scroll_y = action_args.get("scroll_y", 0)
                direction = None
                amount = None
                # Prefer vertical scroll when both present
                if abs(scroll_y) >= abs(scroll_x):
                    if scroll_y > 0:
                        direction = "down"
                    elif scroll_y < 0:
                        direction = "up"
                    amount = abs(scroll_y)
                else:
                    if scroll_x > 0:
                        direction = "right"
                    elif scroll_x < 0:
                        direction = "left"
                    amount = abs(scroll_x)
                if direction:
                    item["direction"] = direction
                if amount is not None:
                    item["amount"] = amount
            else:
                if 'direction' in action_args:
                    item['direction'] = action_args['direction']
                if 'amount' in action_args:
                    item['amount'] = action_args['amount']
            if 'magnitude' in action_args:
                item['magnitude'] = action_args['magnitude']

            # Drag semantics (path-based drag). OpenAI sometimes sends:
            #   {"type": "drag", "path": [{"x": 60, "y": 680}, {"x": 464, "y": 442}]}
            # We need explicit start/target coordinates so the unified timeline
            # and BrowserView can render a drag arrow.
            if action_type == "drag" and isinstance(action_args.get("path"), list):
                path = action_args["path"]
                if path:
                    first = path[0]
                    if isinstance(first, dict) and "x" in first and "y" in first:
                        item["start_coordinates"] = [first["x"], first["y"]]
                        # Use start as the main coordinate for labels when no explicit x/y
                        item.setdefault("coordinates", item["start_coordinates"])
                if len(path) >= 2:
                    last = path[-1]
                    if isinstance(last, dict) and "x" in last and "y" in last:
                        item["target_coordinates"] = [last["x"], last["y"]]
                # Drag path uses raw pixel coordinates, do not mark as normalized
                item.setdefault("coordinates_normalized", False)
            
            item['action_type'] = action_type

            # ✅ BEFORE = Previous action's AFTER screenshot (what model saw when deciding)
            screenshot_path_before = None
            # Actions that visibly change the page and therefore should have before/after screenshots
            visible_effect_actions = [
                'click',
                'double_click',
                'triple_click',
                'type',
                'keypress',  # ✅ FIX: OpenAI uses 'keypress' not 'key' (matches computer method name)
                'scroll',
                'mouse_move',
                'move',
                # Drag-style actions
                'drag_and_drop',
                'drag',
                # Tab management actions
                'new_tab',
                'switch_tab',
                'close_tab',
                'list_tabs',
            ]
            if action_type in visible_effect_actions:
                # Use the last AFTER screenshot we captured
                if hasattr(self, '_last_after_screenshot'):
                    screenshot_path_before = self._last_after_screenshot
                    self.logger.info(f"📸 BEFORE = previous action's AFTER: {screenshot_path_before}")
                else:
                    self.logger.info(f"📸 BEFORE = None (first action)")

            # execute the action directly on computer object to preserve decorators
            method = getattr(self.computer, action_type)
            try:
                result = method(**action_args)  # Capture return value for actions like list_tabs
            except Exception as error:
                # Don't catch CriticalTimeoutError - let it propagate to crash the task
                if isinstance(error, CriticalTimeoutError):
                    self.logger.error(f"🚨 CRITICAL TIMEOUT in {action_type}: {error}")
                    raise  # This will crash the entire task
                if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                    try:
                        self.critical_error_tracker.record_critical_error(error, f"{action_type} failure")
                    except CriticalTimeoutError as critical_error:
                        # Re-raise critical timeout errors to crash the task
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in {action_type}: {critical_error}")
                        raise  # This will crash the entire task
                else:
                    # If no critical error tracker, treat as critical and crash
                    self.logger.error(f"🚨 CRITICAL COMPUTER CALL FAILURE in {action_type}: {error}")
                    raise RuntimeError(f"CRITICAL COMPUTER CALL FAILURE in {action_type}: {error}") from error

            # wait briefly to let DOM settle
            if action_type in ("click", "double_click", "triple_click", "type", "goto"):
                time.sleep(0.9)

            # screenshot evidence - use our screenshot helper
            # Note: actions that do not visibly change the page (e.g. pure "wait")
            # are still followed by a screenshot so that the next action's BEFORE
            # reflects the state after the wait.
            # Special handling for list_tabs: generate tab visualization instead of browser screenshot
            screenshot_base64 = None  # Initialize to avoid NameError
            screenshot_path = None  # Track the saved screenshot path
            
            if action_type == "list_tabs" and result:
                # Generate visual screenshot of tabs for list_tabs action
                try:
                    from app.services.computers.shared.tab_visualizer import TabVisualizer
                    visualizer = TabVisualizer()
                    tab_screenshot_bytes = visualizer.generate_tab_screenshot(result)
                    
                    if self.screenshot_helper and tab_screenshot_bytes:
                        screenshot_path = self.screenshot_helper.save_screenshot(
                            tab_screenshot_bytes,
                            "list_tabs_view"
                        )
                        if screenshot_path:
                            self.logger.info(f"📸 Saved tab visualization screenshot: {screenshot_path}")
                            
                            # Convert to base64 for API
                            import base64
                            screenshot_base64 = base64.b64encode(tab_screenshot_bytes).decode('utf-8')
                            self.logger.info(f"📸 Using tab visualization for API")
                except Exception as viz_error:
                    self.logger.warning(f"⚠️ Failed to generate tab visualization: {viz_error}")
                    # Fall back to regular screenshot if visualization fails
                    screenshot_path = None
            
            # If not list_tabs or visualization failed, take a regular screenshot
            if screenshot_path is None:
                try:
                    if self.screenshot_helper:
                        # Use our independent screenshot mechanism
                        # ✅ wait_for_settle=False because action handler already waited
                        screenshot_path = self.screenshot_helper.take_and_save_screenshot(
                            self.computer, f"after_{action_type}", wait_for_settle=False
                        )
                        if screenshot_path:
                            self.logger.info(f"📸 Saved AFTER screenshot: {screenshot_path}")
                        
                        # ✅ CRITICAL FIX: Reuse the saved screenshot instead of capturing a new one!
                        # Read the file we just saved to ensure API gets EXACT SAME screenshot
                        from pathlib import Path
                        import base64
                        screenshot_file = Path(screenshot_path)
                        if screenshot_file.exists():
                            with open(screenshot_file, 'rb') as f:
                                screenshot_bytes = f.read()
                            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                            self.logger.info(f"📸 Reusing saved screenshot for API (no double capture)")
                        else:
                            # Fallback if file doesn't exist
                            screenshot_base64 = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                            self.logger.warning(f"⚠️ Saved screenshot not found, capturing fresh one")
                    else:
                        # Fallback to direct screenshot
                        screenshot_base64 = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                except CriticalTimeoutError as e:
                    # Critical timeout errors should crash the task immediately
                    self.logger.error(f"🚨 CRITICAL TIMEOUT in screenshot: {e}")
                    raise  # This will crash the entire task
                except Exception as screenshot_error:
                    # Record screenshot failure as critical error if we have access to critical error tracker
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(screenshot_error, f"Screenshot failure after {action_type}")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in screenshot: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        raise RuntimeError(f"CRITICAL SCREENSHOT FAILURE: {screenshot_error}") from screenshot_error
                
            if self.show_images and screenshot_base64:
                show_image(screenshot_base64)

            # Generate insights for this action
            self.logger.debug(f"🔍 Checking insighter: {self.insighter is not None}, screenshot: {screenshot_base64 is not None}")
            if self.insighter and screenshot_base64:
                try:
                    action_data = {
                        'type': action_type,
                        'action': action,
                        'timestamp': time.time()
                    }
                    self.insighter.analyze_action(action_data, screenshot_base64)
                except Exception as insight_error:
                    # Don't let insight generation failures crash the task
                    self.logger.warning(f"⚠️ Insight generation failed for {action_type}: {insight_error}")

            # handle safety checks
            pending_checks = item.get("pending_safety_checks", [])
            for check in pending_checks:
                message = check["message"]
                if not self.acknowledge_safety_check_callback(message):
                    raise ValueError(
                        f"Safety check failed: {message}. "
                        "Cannot continue with unacknowledged safety checks."
                    )

            # ✅ Create CLEAN version for OpenAI API (only what API expects)
            api_call_output = {
                "type": "computer_call_output",
                "call_id": item["call_id"],
                "acknowledged_safety_checks": pending_checks,
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}",
                },
            }
            
            # Add current_url inside output for API (OpenAI expects it here)
            if self.computer.get_environment() == "browser":
                current_url = self.computer.get_current_url()
                check_blocklisted_url(current_url)
                api_call_output["output"]["current_url"] = current_url
            
            # Add tab info for list_tabs action
            if action_type == "list_tabs" and result:
                api_call_output["output"]["tab_info"] = result
                self.logger.info(f"📑 Added tab info to response: {result}")
            
            # ✅ Return CLEAN version to API
            outputs.append(api_call_output)
            
            # ✅ SEPARATELY create ENRICHED version for timeline tracking (NOT sent to API)
            # Store as instance variable to be accessed by caller for tracking
            enriched_output = api_call_output.copy()
            enriched_output["action"] = action_type
            
            # ✅ Add tool_input for timeline extraction (contains all function args)
            enriched_output['tool_input'] = action  # The original action dict with all args
            
            # ✅ Add before/after screenshots
            if screenshot_path_before:
                enriched_output['screenshot_before'] = screenshot_path_before
            if screenshot_path:
                enriched_output['screenshot_after'] = screenshot_path
                enriched_output['screenshot'] = screenshot_path  # Legacy field
                # ✅ Store this AFTER screenshot for next action's BEFORE
                self._last_after_screenshot = screenshot_path
                self.logger.info(f"📸 Stored AFTER for next action's BEFORE: {screenshot_path}")
            
            if 'coordinates' in item:
                enriched_output['coordinates'] = item['coordinates']
            if 'text' in item:
                enriched_output['text'] = item['text']
            if 'key' in item:
                enriched_output['key'] = item['key']
            elif 'keys' in item:
                enriched_output['key'] = item['keys']
            if 'direction' in item:
                enriched_output['direction'] = item['direction']
            if 'amount' in item:
                enriched_output['amount'] = item['amount']
            if 'magnitude' in item:
                enriched_output['magnitude'] = item['magnitude']
            # ✅ Add tab_info for list_tabs actions
            if action_type == 'list_tabs' and result:
                enriched_output['tab_info'] = result
                self.logger.debug(f"📑 ✅ Added tab_info to enriched: {result}")
            if 'start_coordinates' in item:
                enriched_output['start_coordinates'] = item['start_coordinates']
            if 'target_coordinates' in item:
                enriched_output['target_coordinates'] = item['target_coordinates']
            if 'coordinates_normalized' in item:
                enriched_output['coordinates_normalized'] = item['coordinates_normalized']
            if 'target_coordinates_normalized' in item:
                enriched_output['target_coordinates_normalized'] = item['target_coordinates_normalized']
            if self.computer.get_environment() == "browser":
                enriched_output["url"] = current_url
            
            # ✅ Report enriched version for timeline (NOT sent to API)
            self._report_action(enriched_output)
            self.logger.info(f"✅ Reported enriched output to timeline: before={screenshot_path_before}, after={screenshot_path}")

        return outputs
    
    def run_full_turn(self, input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run a full task until the assistant produces a final message.
        Uses previous_response_id to keep context anchored.
        Independent implementation extracted from V1 Agent.
        """
        try:
            self.logger.info("🤖 Starting OpenAI agent execution (independent implementation)")
            
            self.print_steps = True
            self.debug = False
            self.show_images = False
            parent_items = []
            
            # Reset iteration counter at start of task
            self.current_iteration = 0

            # 1) First call: send initial user/system input
            self.current_iteration += 1
            self.logger.info(f"🔄 OpenAI iteration {self.current_iteration}/{settings.MAX_STEPS_LIMIT}")
            # Note: OpenAI Computer Use API (Responses API) manages output tokens server-side
            # Dynamic token adjustment not supported by this API endpoint
            # Token optimization handled via server-side context management instead
            
            response = self._create_response_with_retry(
                model="computer-use-preview",
                input=input_items,
                tools=self.tools,
                truncation="auto",
                reasoning={"summary": "auto"}
            )

            last_id = response["id"]
            new_items = response["output"]
            parent_items.extend(new_items)
            
            # ✅ Report initial items in real-time for live timeline
            for item in new_items:
                self._report_action(item)

            while self.current_iteration < settings.MAX_STEPS_LIMIT:
                # look for calls to handle
                calls = [it for it in new_items if it.get("type") in ("computer_call", "function_call")]
                if not calls:
                    # ✅ Task complete - check if there's a final message
                    final_message_items = [it for it in new_items if it.get("type") == "message" and it.get("role") == "assistant"]
                    if not final_message_items:
                        # Model completed without sending final text message (just stopped calling tools)
                        # Create explicit completion message for live monitoring ONLY
                        # Note: is_completion_marker=True prevents this from being stored as last_model_response
                        completion_item = {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": "Task completed"}],
                            "id": f"msg_assistant_{int(time.time())}",
                            "is_completion_marker": True  # ✅ UI only, not stored as model response
                        }
                        parent_items.append(completion_item)
                        self._report_action(completion_item)
                        self.logger.info("✅ Task completed (model stopped calling tools, created UI completion marker)")
                    else:
                        # ✅ FIX: Report final message items to timeline
                        self.logger.info("✅ Task completed with final message - reporting to timeline")
                        for final_msg in final_message_items:
                            self._report_action(final_msg)
                    break  # assistant has produced a final message or stopped calling tools

                for item in calls:
                    followups = self.handle_item(item)
                    if not followups:
                        continue

                    # 2) Send just the fresh followup + thread with previous_response_id
                    self.current_iteration += 1
                    self.logger.info(f"🔄 OpenAI iteration {self.current_iteration}/{settings.MAX_STEPS_LIMIT}")
                    # Note: OpenAI Computer Use API (Responses API) manages output tokens server-side
                    # Dynamic token adjustment not supported by this API endpoint
                    
                    response = self._create_response_with_retry(
                        model="computer-use-preview",
                        previous_response_id=last_id,
                        input=followups,
                        tools=self.tools,
                        truncation="auto",
                        reasoning={"summary": "auto"}
                    )

                    summary_text = None

                    # Try to pull summary text safely
                    if "output" in response and response["output"]:
                        reasoning_items = [it for it in response["output"] if it.get("type") == "reasoning"]
                        if reasoning_items:
                            summary_chunks = reasoning_items[0].get("summary") or []
                            for ch in summary_chunks:
                                if ch.get("type") == "summary_text" and ch.get("text"):
                                    summary_text = ch["text"]
                                    break

                    if summary_text:
                        self.logger.info(f"""
======================================================================
{summary_text}
======================================================================
""")
                        
                        # Generate insights for the summary
                        self.logger.debug(f"🔍 Checking insighter for summary: {self.insighter is not None}")
                        if self.insighter:
                            try:
                                # Get current screenshot for summary analysis
                                current_screenshot = None
                                if self.computer:
                                    current_screenshot = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                                
                                self.insighter.analyze_summary(summary_text, current_screenshot)
                            except Exception as insight_error:
                                # Don't let insight generation failures crash the task
                                self.logger.warning(f"⚠️ Summary insight generation failed: {insight_error}")

                    last_id = response["id"]
                    new_items = response["output"]
                    parent_items.extend(new_items)
                    
                    # ✅ Report follow-up items in real-time for live timeline
                    for item in new_items:
                        self._report_action(item)

            self.logger.info("📸 Screenshots captured using independent mechanism")
            self.logger.info("✅ OpenAI agent execution completed successfully")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            return parent_items
            
        except Exception as e:
            self.logger.error(f"❌ OpenAI agent execution failed: {e}")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            raise
    
    def get_model_type(self) -> str:
        """Get the model type"""
        return self._model_type
    
    def _execute_with_critical_tracking(self, operation_name: str, operation_func, *args, **kwargs):
        """Execute a computer operation with critical error tracking"""
        try:
            return operation_func(*args, **kwargs)
        except Exception as error:
            if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                try:
                    self.critical_error_tracker.record_critical_error(error, f"{operation_name} failure")
                except CriticalTimeoutError as critical_error:
                    # Re-raise critical timeout errors to crash the task
                    self.logger.error(f"🚨 CRITICAL TIMEOUT in {operation_name}: {critical_error}")
                    raise  # This will crash the entire task
            raise
    
    def cleanup_resources(self):
        """Clean up agent resources"""
        try:
            # Clean up insighter if it exists
            if self.insighter:
                self.insighter.cleanup_resources()
                self.insighter = None
            
            # Clean up screenshot helper if it exists
            if self.screenshot_helper:
                self.screenshot_helper = None
            self.logger.info("🧹 OpenAI agent resources cleaned up")
        except Exception as e:
            self.logger.warning(f"⚠️ Error cleaning up OpenAI agent resources: {e}")