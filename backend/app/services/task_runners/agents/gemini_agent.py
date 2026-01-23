#!/usr/bin/env python3
"""
Gemini Agent - Wrapper around optimized Gemini CUA implementation
Follows Google's recommendations for performance and efficiency
Enhanced with localStorage extraction and safety check support
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from app.services.agent.gemini_agent import GeminiAgent as OptimizedGeminiAgent
from app.core.config import settings
from app.services.computers.error_handling import CriticalTimeoutError, CriticalAPIError
from .base_agent import BaseAgent
from ..helpers.screenshot_helper import ScreenshotHelper
from ..insights.insighter import Insighter


class GeminiAgent(BaseAgent):
    """
    Gemini agent wrapper - delegates to optimized Gemini CUA implementation

    This wrapper:
    - Implements BaseAgent interface for unified runner compatibility
    - Preserves all Google-recommended optimizations (screenshot trimming, single-tab, etc.)
    - Delegates actual execution to the well-optimized GeminiAgent implementation
    - Supports localStorage extraction for verification workflows
    - Includes safety check callback support
    """

    def __init__(
        self,
        computer=None,
        acknowledge_safety_check_callback: Optional[Callable[[str], bool]] = None,
        logger=None,
        task_dir=None,
        critical_error_tracker=None,
        iteration_id=None,
        execution_id=None,
    ):
        """Initialize Gemini agent wrapper

        Args:
            computer: Browser computer instance
            acknowledge_safety_check_callback: Callback for safety checks (optional)
            logger: Logger instance
            task_dir: Task directory for saving results
            iteration_id: Iteration ID for token tracking
            execution_id: Execution ID for token tracking
        """
        super().__init__(computer, logger, task_dir)

        # Set model type
        self._model_type = "gemini"

        # Store safety check callback
        self.acknowledge_safety_check_callback = acknowledge_safety_check_callback or (
            lambda _: True
        )
        self.critical_error_tracker = critical_error_tracker
        
        # Store IDs for token tracking
        self.iteration_id = iteration_id
        self.execution_id = execution_id

        # Verify API key
        # Use settings instead of os.getenv() to read from .env file
        api_key = settings.GOOGLE_API_KEY or settings.GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required. Set it in backend/.env file or environment variables."
            )

        # Initialize screenshot helper FIRST (before OptimizedGeminiAgent)
        self.screenshot_helper = None
        self.screenshot_dir = None  # Always initialize to prevent AttributeError
        if task_dir:
            Path(task_dir).mkdir(parents=True, exist_ok=True)
            (Path(task_dir) / "screenshots").mkdir(parents=True, exist_ok=True)
            self.screenshot_dir = str(Path(task_dir) / "screenshots")
            self.screenshot_helper = ScreenshotHelper(self.screenshot_dir, logger)

        # Initialize the optimized Gemini agent AFTER screenshot_helper is ready
        # LocalPlaywrightBrowser now has all Gemini-specific methods (open_web_browser, click_at, etc.)
        # Pass screenshot_dir as string (already created in self.screenshot_dir)
        self.optimized_agent = OptimizedGeminiAgent(
            computer=computer,
            logger=logger or logging.getLogger(__name__),
            screenshot_dir=self.screenshot_dir,  # Use the string path we already created
            screenshot_helper=self.screenshot_helper,  # Already initialized above
        )

        # Initialize model failure tracking flag
        self._model_failure_detected = False

        # Initialize insighter for insight generation (will be initialized later if task_dir is None)
        self.insighter = None
        if task_dir:
            # self.insighter = Insighter(logger=self.logger, task_dir=task_dir)
            self.logger.info("✅ Insighter initialized for Gemini agent")
        else:
            self.logger.info("ℹ️ Insighter will be initialized later when task directory is available")
        
        # Initialize insights storage
        self.final_insights = None
        if self.logger:
            self.logger.info(
                "✅ Gemini agent initialized with localStorage extraction and safety check support"
            )

    def update_task_directory(self, task_dir: str) -> None:
        """Update task directory and reinitialize insighter if needed"""
        if task_dir and not self.insighter:
            # Initialize insighter if it wasn't initialized before
            # self.insighter = Insighter(logger=self.logger, task_dir=task_dir)
            self.logger.info("✅ Insighter initialized for Gemini agent (late initialization)")
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

    def _handle_key_press(self, text: str) -> str:
        """Handle key press with proper formatting and fallbacks - following Anthropic pattern"""
        try:
            # Handle special key combinations
            if "+" in text:
                # Handle key combinations like "ctrl+a", "shift+tab", etc.
                keys = text.split("+")
                # Call keypress method directly to preserve decorators
                try:
                    self.computer.keypress(keys)
                except Exception as error:
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed key combination: {text}"
            else:
                # Call keypress method directly to preserve decorators
                try:
                    self.computer.keypress([text])
                except Exception as error:
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed key: {text}"
        except Exception as key_error:
            self.logger.warning(f"⚠️ Key press failed for '{text}': {key_error}")

            # Try alternative key formats
            try:
                # Common key combinations - following Anthropic pattern
                key_mappings = {
                    "ctrl+a": ["ctrl", "a"],
                    "ctrl+c": ["ctrl", "c"],
                    "ctrl+v": ["ctrl", "v"],
                    "ctrl+z": ["ctrl", "z"],
                    "ctrl+y": ["ctrl", "y"],
                    "ctrl+s": ["ctrl", "s"],
                    "ctrl+f": ["ctrl", "f"],
                    "ctrl+r": ["ctrl", "r"],
                    "ctrl+w": ["ctrl", "w"],
                    "ctrl+t": ["ctrl", "t"],
                    "ctrl+l": ["ctrl", "l"],
                    "ctrl+h": ["ctrl", "h"],
                    "ctrl+n": ["ctrl", "n"],
                    "ctrl+o": ["ctrl", "o"],
                    "ctrl+p": ["ctrl", "p"],
                    "ctrl+shift+i": ["ctrl", "shift", "i"],
                    "ctrl+shift+j": ["ctrl", "shift", "j"],
                    "ctrl+shift+c": ["ctrl", "shift", "c"],
                    "ctrl+shift+r": ["ctrl", "shift", "r"],
                    "ctrl+shift+t": ["ctrl", "shift", "t"],
                    "ctrl+shift+n": ["ctrl", "shift", "n"],
                    "ctrl+shift+delete": ["ctrl", "shift", "delete"],
                    "alt+tab": ["alt", "tab"],
                    "alt+f4": ["alt", "f4"],
                    "shift+tab": ["shift", "tab"],
                    "enter": ["enter"],
                    "return": ["enter"],
                    "escape": ["escape"],
                    "tab": ["tab"],
                    "backspace": ["backspace"],
                    "delete": ["delete"],
                    "home": ["home"],
                    "end": ["end"],
                    "pageup": ["pageup"],
                    "pagedown": ["pagedown"],
                    "arrowup": ["arrowup"],
                    "arrowdown": ["arrowdown"],
                    "arrowleft": ["arrowleft"],
                    "arrowright": ["arrowright"],
                    # Add missing directional keys that were causing errors
                    "down": ["arrowdown"],
                    "up": ["arrowup"],
                    "left": ["arrowleft"],
                    "right": ["arrowright"],
                    "control": ["ctrl"],
                }

                text_lower = text.lower()
                if text_lower in key_mappings:
                    # Call keypress method directly to preserve decorators
                    try:
                        self.computer.keypress(key_mappings[text_lower])
                    except Exception as error:
                        if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                            try:
                                self.critical_error_tracker.record_critical_error(error, "keypress failure")
                            except CriticalTimeoutError as critical_error:
                                # Re-raise critical timeout errors to crash the task
                                raise  # This will crash the entire task
                        else:
                            # If no critical error tracker, treat as critical and crash
                            raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                    return f"Pressed key: {text} (mapped format)"
                else:
                    # Try single key
                    # Call keypress method directly to preserve decorators
                    try:
                        self.computer.keypress([text])
                    except Exception as error:
                        if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                            try:
                                self.critical_error_tracker.record_critical_error(error, "keypress failure")
                            except CriticalTimeoutError as critical_error:
                                # Re-raise critical timeout errors to crash the task
                                raise  # This will crash the entire task
                        else:
                            # If no critical error tracker, treat as critical and crash
                            raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                    return f"Pressed key: {text} (single key)"

            except Exception as alt_error:
                self.logger.error(
                    f"❌ Alternative key press also failed for '{text}': {alt_error}"
                )
                return f"Key press failed: {text} - {str(key_error)}"

    def _create_response_with_retry(self, max_retries=3, **kwargs):
        """
        Wrapper for API calls with retry logic - following OpenAI pattern
        Retries up to max_retries times for any API error.
        """
        last_exception = None

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"API call attempt {attempt + 1}/{max_retries}")
                # This would be the actual API call - for now we'll delegate to optimized agent
                # In a real implementation, this would handle the Gemini API calls directly
                return self.optimized_agent._make_api_call(**kwargs)
            except Exception as e:
                last_exception = e
                self.logger.warning(f"API call attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    # Wait before retrying (exponential backoff)
                    wait_time = 2**attempt
                    self.logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"All {max_retries} API call attempts failed")

        # If we get here, all retries failed - raise CriticalAPIError to crash immediately
        raise CriticalAPIError(
            f"Gemini API call failed after {max_retries} attempts. Last error: {str(last_exception)}"
        ) from last_exception

    def _execute_computer_action(self, action: str, **kwargs) -> str:
        """Execute computer actions with timeout handling - following Anthropic pattern"""
        try:
            result_text = ""

            # Handle different computer actions
            if action == "screenshot":
                # Take a screenshot using our computer instance with critical tracking
                # Call screenshot method directly to preserve decorators
                try:
                    screenshot_data = self.computer.screenshot()
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate for retry handling
                    if isinstance(error, CriticalTimeoutError):
                        raise
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "screenshot failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        raise RuntimeError(f"CRITICAL SCREENSHOT FAILURE: {error}") from error
                if screenshot_data:
                    # Save screenshot to task directory
                    self._take_screenshot("screenshot_action")
                    result_text = "Screenshot captured"
                else:
                    result_text = "Screenshot failed"

            elif action == "left_click" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                self.logger.info(f"🖱️ Left clicking at coordinates ({x}, {y})")
                try:
                    self.computer.click(x, y, button="left")
                    result_text = f"Left clicked at coordinates ({x}, {y})"
                except Exception as click_error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(click_error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in left_click: {click_error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(click_error, f"Left click failure at ({x}, {y})")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in left_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        self.logger.error(f"🚨 CRITICAL CLICK FAILURE: {click_error}")
                        raise RuntimeError(f"CRITICAL CLICK FAILURE: {click_error}") from click_error
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "right_click" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                self.logger.info(f"🖱️ Right clicking at coordinates ({x}, {y})")
                try:
                    self.computer.click(x, y, button="right")
                    result_text = f"Right clicked at coordinates ({x}, {y})"
                except Exception as click_error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(click_error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in right_click: {click_error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(click_error, f"Right click failure at ({x}, {y})")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in right_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        self.logger.error(f"🚨 CRITICAL CLICK FAILURE: {click_error}")
                        raise RuntimeError(f"CRITICAL CLICK FAILURE: {click_error}") from click_error
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "double_click" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                self.logger.info(f"🖱️ Double clicking at coordinates ({x}, {y})")
                # Call double_click method directly to preserve decorators
                try:
                    self.computer.double_click(x, y)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in double_click: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "double_click failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in double_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL DOUBLE_CLICK FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL DOUBLE_CLICK FAILURE: {error}") from error
                result_text = f"Double clicked at coordinates ({x}, {y})"
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "triple_click" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                self.logger.info(f"🖱️ Triple clicking at coordinates ({x}, {y})")
                # Call triple_click method directly to preserve decorators
                try:
                    self.computer.triple_click(x, y)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in triple_click: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "triple_click failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in triple_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL TRIPLE_CLICK FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL TRIPLE_CLICK FAILURE: {error}") from error
                result_text = f"Triple clicked at coordinates ({x}, {y})"
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "type" and "text" in kwargs:
                text = kwargs["text"]
                self.logger.info(f"⌨️ Typing text: {text}")
                # Call type method directly to preserve decorators
                try:
                    self.computer.type(text)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in type: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "type failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in type: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL TYPE FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL TYPE FAILURE: {error}") from error
                result_text = f"Typed: {text}"
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "key" and "text" in kwargs:
                text = kwargs["text"]
                self.logger.info(f"⌨️ Pressing key: {text}")
                result_text = self._handle_key_press(text)
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)

            elif action == "mouse_move" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                self.logger.info(f"🖱️ Moving mouse to coordinates ({x}, {y})")
                # Call mouse_move method directly to preserve decorators
                try:
                    self.computer.move(x, y)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in mouse_move: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "mouse_move failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in mouse_move: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL MOUSE_MOVE FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL MOUSE_MOVE FAILURE: {error}") from error
                result_text = f"Moved mouse to coordinates ({x}, {y})"

            elif action == "scroll" and "coordinate" in kwargs:
                x, y = kwargs["coordinate"]
                scroll_direction = kwargs.get("scroll_direction", "down")
                scroll_amount = kwargs.get("scroll_amount", 1)
                scroll_x, scroll_y = 0, 0
                if scroll_direction == "up":
                    scroll_y = -scroll_amount * 100
                elif scroll_direction == "down":
                    scroll_y = scroll_amount * 100
                elif scroll_direction == "left":
                    scroll_x = -scroll_amount * 100
                elif scroll_direction == "right":
                    scroll_x = scroll_amount * 100

                self.logger.info(
                    f"🖱️ Scrolling {scroll_direction} by {scroll_amount} at ({x}, {y})"
                )
                # Call scroll method directly to preserve decorators
                try:
                    self.computer.scroll(x, y, scroll_x, scroll_y)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in scroll: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "scroll failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in scroll: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL SCROLL FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL SCROLL FAILURE: {error}") from error
                result_text = (
                    f"Scrolled {scroll_direction} by {scroll_amount} at ({x}, {y})"
                )

            elif action == "wait":
                duration = kwargs.get("duration", 1.0)
                wait_ms = int(duration * 1000) if duration else 1000
                self.logger.info(f"⏱️ Waiting for {wait_ms}ms")
                self.computer.wait(wait_ms)
                result_text = f"Waited for {wait_ms}ms"

            else:
                result_text = (
                    f"Computer action '{action}' not implemented or missing parameters"
                )
                self.logger.warning(
                    f"⚠️ Unhandled computer action: {action} with input: {kwargs}"
                )

            # Take a screenshot after the action (except for screenshot action) - like agent.py
            if action != "screenshot":
                try:
                    screenshot_data = self.computer.screenshot()
                    if screenshot_data:
                        # Save screenshot after action
                        self._take_screenshot(f"after_{action}")
                        
                        # Generate insights for this action
                        self.logger.debug(f"🔍 Checking insighter: {self.insighter is not None}")
                        if self.insighter:
                            try:
                                action_data = {
                                    'type': action,
                                    'action': kwargs,
                                    'timestamp': time.time()
                                }
                                self.insighter.analyze_action(action_data, screenshot_data)
                            except Exception as insight_error:
                                # Don't let insight generation failures crash the task
                                self.logger.warning(f"⚠️ Insight generation failed for {action}: {insight_error}")
                except CriticalTimeoutError as e:
                    # Critical timeout errors should crash the task immediately - re-raise directly
                    self.logger.error(f"🚨 CRITICAL TIMEOUT in post-action screenshot: {e}")
                    raise  # This will crash the entire task
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to take post-action screenshot: {e}")

            return result_text

        except CriticalTimeoutError as e:
            # Critical timeout errors should crash the task immediately - re-raise directly
            self.logger.error(f"🚨 CRITICAL TIMEOUT in {action}: {e}")
            raise  # This will crash the entire task
        except Exception as e:
            self.logger.error(f"❌ Computer action '{action}' failed: {e}")
            raise

    def _take_screenshot(self, step_name: str) -> Optional[str]:
        """
        Take screenshot using ScreenshotHelper - matches OpenAI/Anthropic pattern

        This is a wrapper around screenshot_helper.take_and_save_screenshot()
        to maintain consistency with OpenAI and Anthropic agents.
        """
        if not self.screenshot_helper:
            self.logger.warning("⚠️ No screenshot helper available")
            return None

        try:
            screenshot_path = self.screenshot_helper.take_and_save_screenshot(
                self.computer, step_name
            )
            if screenshot_path:
                self.logger.info(f"📸 Saved screenshot: {screenshot_path}")
            return screenshot_path
        except CriticalTimeoutError as e:
            # Critical timeout errors should crash the task immediately - following OpenAI pattern
            raise  # This will crash the entire task
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to take screenshot: {e}")
            return None

    def run_full_turn(self, input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute a full turn with the Gemini agent
        
        This method:
        1. Extracts the task query from input_items
        2. Runs the agent loop with proper item tracking
        3. Returns individual action items like OpenAI/Anthropic agents
        
        Args:
            input_items: List of conversation items (unified format)
            
        Returns:
            List of response items (unified format) - individual actions and responses
        """
        try:
            self.logger.info("🤖 Starting Gemini agent execution (optimized implementation)")
            
            # Extract query from input_items
            query = self._extract_query_from_input(input_items)
            if not query:
                self.logger.error("❌ No query found in input items")
                return []
            
            self.logger.info(f"📋 Task query: {query[:200]}{'...' if len(query) > 200 else ''}")
            
            # Get initial screenshot if available (for sending to model, not saving)
            initial_screenshot = None
            if self.computer and hasattr(self.computer, 'page') and self.computer.page:
                try:
                    initial_screenshot = self.computer.page.screenshot(type="png", full_page=False)
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to get initial screenshot: {e}")
            
            # Execute using optimized Gemini agent with item tracking
            self.logger.info(f"🔄 Running Gemini agent loop (no turn limit)")
            
            # Run the agent loop and collect all items
            all_items = self._run_agent_loop_with_tracking(
                query=query,
                initial_screenshot=initial_screenshot,
                max_turns=None
            )
            
            # Export conversation history for debugging
            try:
                conversation = self.optimized_agent.export_conversation()
                self._save_conversation_export(conversation)
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to export conversation: {e}")
            
            self.logger.info("✅ Gemini agent execution completed successfully")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            return all_items
            
        except Exception as e:
            self.logger.error(f"❌ Gemini agent execution failed: {e}")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            raise

    def _extract_query_from_input(
        self, input_items: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Extract task query from input items"""
        for item in input_items:
            if item.get("type") == "message" and item.get("role") == "user":
                content = item.get("content", "")

                # Handle different content formats
                if isinstance(content, list) and len(content) > 0:
                    first_content = content[0]
                    if isinstance(first_content, dict) and "text" in first_content:
                        return first_content["text"]
                    elif isinstance(first_content, str):
                        return first_content
                elif isinstance(content, str):
                    return content

        return None
    
    def _run_agent_loop_with_tracking(self, query: str, initial_screenshot: bytes = None, max_turns: int = None) -> List[Dict[str, Any]]:
        """
        Run the agent loop while tracking individual items like OpenAI/Anthropic agents
        
        This method:
        1. Runs the optimized agent loop
        2. Tracks each action and response as individual items
        3. Logs reasoning text like OpenAI agent
        4. Returns a list of items representing the full conversation
        
        Args:
            query: Task description
            initial_screenshot: Optional initial screenshot
            max_turns: Maximum number of iterations (deprecated, no longer enforced)
            
        Returns:
            List of individual action items (unified format)
        """
        # Import Gemini types at the top of the method
        from google.genai.types import (
            Part, Content, FinishReason, FunctionResponse, 
            FunctionResponsePart, FunctionResponseBlob
        )
        
        all_items = []
        
        # Initialize conversation with user query
        parts = [Part(text=query)]
        if initial_screenshot:
            parts.append(Part.from_bytes(data=initial_screenshot, mime_type="image/png"))
            
        self.optimized_agent.contents = [Content(role="user", parts=parts)]
        
        # Add initial user message to items
        all_items.append({
            "type": "message",
            "role": "user", 
            "content": [{"type": "text", "text": query}],
            "id": f"msg_user_{int(time.time())}"
        })
        
        # Run agent loop with tracking
        turn = 0
        status = "CONTINUE"
        consecutive_empty_responses = 0  # Track consecutive turns with no function calls
        MIN_TURNS_BEFORE_COMPLETION = 1  # Minimum turns before allowing completion
        MAX_CONSECUTIVE_EMPTY = 3  # Maximum consecutive empty responses before warning
        
        while status == "CONTINUE" and turn < settings.MAX_STEPS_LIMIT:
            try:
                # Generate response from model
                self.logger.info("🤖 Generating response from Gemini...")
                response = self.optimized_agent.get_model_response()
                
                # Track token usage if IDs are available
                if self.iteration_id and self.execution_id and response:
                    try:
                        from app.core.database_utils import get_db_session
                        from sqlalchemy import text
                        
                        # Extract token counts from Gemini response
                        usage_metadata = getattr(response, 'usage_metadata', None)
                        if usage_metadata:
                            input_tokens = getattr(usage_metadata, 'prompt_token_count', 0) or 0
                            output_tokens = getattr(usage_metadata, 'candidates_token_count', 0) or 0
                            total_tokens = getattr(usage_metadata, 'total_token_count', None) or (input_tokens + output_tokens)
                            cached_tokens = getattr(usage_metadata, 'cached_content_token_count', 0) or 0
                            
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
                                            'model_name': 'gemini',
                                            'model_version': self.optimized_agent.model_name,
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
                
                if not response or not response.candidates:
                    self.logger.error("❌ No candidates in response - model failure")
                    # Set status to indicate model failure (not system crash)
                    status = "MODEL_FAILURE"
                    self._model_failure_detected = True  # Set flag for categorization
                    break
                    
                candidate = response.candidates[0]
                
                # Append model response to conversation
                if candidate.content:
                    self.optimized_agent.contents.append(candidate.content)
                    
                # Extract reasoning and function calls
                reasoning = self.optimized_agent.get_text(candidate)
                function_calls = self.optimized_agent.extract_function_calls(candidate)
                
                # Log reasoning text like OpenAI agent
                if reasoning:
                    self.logger.info(f"""
======================================================================
{reasoning}
======================================================================
""")
                    
                    # Generate insights for text content (reasoning/summary)
                    self.logger.debug(f"🔍 Checking insighter for text content: {self.insighter is not None}")
                    if self.insighter:
                        try:
                            # Get current screenshot for summary analysis
                            current_screenshot = None
                            if self.computer:
                                current_screenshot = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                            
                            self.insighter.analyze_summary(reasoning, current_screenshot)
                        except Exception as insight_error:
                            # Don't let insight generation failures crash the task
                            self.logger.warning(f"⚠️ Text content insight generation failed: {insight_error}")
                    
                    # Add reasoning as a text item
                    reasoning_item = {
                        "type": "text",
                        "text": reasoning,
                        "timestamp": datetime.now().isoformat(),
                        "role": "assistant"
                    }
                    all_items.append(reasoning_item)
                    
                    # ✅ Report reasoning in real-time for live timeline
                    self._report_action(reasoning_item)
                
                # Handle malformed function calls - RETRY without incrementing turn
                if (not function_calls and not reasoning and 
                    candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL):
                    self.logger.warning("⚠️ Malformed function call, retrying...")
                    continue  # Retry without counting as a turn
                
                # Valid response - increment turn counter
                turn += 1
                self.logger.info(f"🔄 Turn {turn}/{settings.MAX_STEPS_LIMIT} (valid response)")
                
                # Get finish_reason to check for explicit completion
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None
                self.logger.info(f"🔍 Model finish_reason: {finish_reason}")
                    
                # Check if no function calls - but don't immediately exit
                if not function_calls:
                    consecutive_empty_responses += 1
                    self.logger.info(f"⚠️ No function calls in response (consecutive: {consecutive_empty_responses}/{MAX_CONSECUTIVE_EMPTY})")
                    
                    # Check for explicit completion signals in reasoning
                    is_explicit_completion = False
                    completion_phrases = [
                        "task complete", "task completed", "task is complete", "task is completed",
                        "successfully completed", "have completed", "finished the task",
                        "all done", "task done", "completed successfully"
                    ]
                    
                    if reasoning:
                        reasoning_lower = reasoning.lower()
                        is_explicit_completion = any(phrase in reasoning_lower for phrase in completion_phrases)
                        if is_explicit_completion:
                            self.logger.info(f"✅ Explicit completion phrase found in reasoning")
                    
                    # Check finish_reason for explicit stop
                    is_finish_stop = finish_reason == FinishReason.STOP
                    if is_finish_stop:
                        self.logger.info(f"✅ Model finish_reason is STOP - explicit completion signal")
                    
                    # Only exit if we have strong completion signals
                    should_complete = False
                    completion_reason_detail = ""
                    
                    if is_finish_stop and turn >= MIN_TURNS_BEFORE_COMPLETION:
                        # Model explicitly stopped AND we've done minimum turns
                        should_complete = True
                        completion_reason_detail = f"Model STOP signal after {turn} turns"
                    elif is_explicit_completion and turn >= MIN_TURNS_BEFORE_COMPLETION:
                        # Explicit completion phrase in reasoning AND minimum turns
                        should_complete = True
                        completion_reason_detail = f"Explicit completion phrase after {turn} turns"
                    elif consecutive_empty_responses >= MAX_CONSECUTIVE_EMPTY and turn >= MIN_TURNS_BEFORE_COMPLETION:
                        # Multiple consecutive empty responses - model may be stuck or done
                        should_complete = True
                        completion_reason_detail = f"No function calls for {consecutive_empty_responses} consecutive turns"
                        self.logger.warning(f"⚠️ Completing due to {consecutive_empty_responses} consecutive empty responses")
                    elif not reasoning and consecutive_empty_responses >= 2 and turn >= MIN_TURNS_BEFORE_COMPLETION:
                        # No reasoning and multiple empty responses - model likely stuck
                        should_complete = True
                        completion_reason_detail = f"No reasoning and {consecutive_empty_responses} empty responses"
                        self.logger.warning(f"⚠️ Model returned no reasoning and no function calls for {consecutive_empty_responses} turns")
                    else:
                        # Don't exit yet - give the model more chances
                        self.logger.info(f"🔄 Continuing loop - no strong completion signal yet (turn={turn}, consecutive_empty={consecutive_empty_responses})")
                        # Continue to next iteration without breaking
                        continue
                    
                    if should_complete:
                        self.logger.info(f"✅ Task completion detected: {completion_reason_detail}")
                        
                        # Use the model's natural reasoning as the completion message
                        # Don't add any hardcoded completion text - let the model's response be natural
                        if reasoning:
                            completion_item = {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "text", "text": reasoning}],
                                "id": f"msg_assistant_{int(time.time())}"
                            }
                            all_items.append(completion_item)
                            
                            # ✅ Report final completion in real-time for live timeline
                            self._report_action(completion_item)
                        else:
                            # ✅ Model completed silently (no reasoning) - create completion message for live monitoring ONLY
                            # Note: is_completion_marker=True prevents this from being stored as last_model_response
                            completion_item = {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "text", "text": "Task completed"}],
                                "id": f"msg_assistant_{int(time.time())}",
                                "is_completion_marker": True  # ✅ UI only, not stored as model response
                            }
                            all_items.append(completion_item)
                            self._report_action(completion_item)
                            self.logger.info("✅ Task completed (no reasoning text, created UI completion marker)")
                        break
                else:
                    # Reset consecutive empty counter when we have function calls
                    consecutive_empty_responses = 0
                    
                # Execute function calls and track each one
                function_responses = []
                normalized_coordinate_actions = {
                    'click_at',
                    'type_text_at',
                    'hover_at',
                    'scroll_at',
                    'drag_and_drop',
                }

                for function_call in function_calls:
                    # Log action in OpenAI format: action_type(args)
                    self.logger.info(f"{function_call.name}({function_call.args})")
                    
                    # Extract action details from args for better logging
                    action_details = {
                        "type": "computer_call",
                        "action": function_call.name,
                        "args": function_call.args,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Extract specific fields for action timeline
                    action_name = function_call.name
                    is_normalized_action = action_name in normalized_coordinate_actions

                    if function_call.args:
                        # For click actions: extract coordinates
                        if 'x' in function_call.args and 'y' in function_call.args:
                            action_details['coordinates'] = [function_call.args['x'], function_call.args['y']]
                            action_details['coordinates_normalized'] = is_normalized_action
                        elif 'coordinate' in function_call.args:
                            action_details['coordinates'] = function_call.args['coordinate']
                            action_details['coordinates_normalized'] = is_normalized_action
                        
                        # Start coordinates for drag actions
                        if 'start_coordinate' in function_call.args:
                            action_details['start_coordinates'] = function_call.args['start_coordinate']
                        elif 'start_x' in function_call.args and 'start_y' in function_call.args:
                            action_details['start_coordinates'] = [function_call.args['start_x'], function_call.args['start_y']]
                        
                        # Secondary/target coordinates (drag, drop, etc.)
                        target_coordinates = None
                        if 'destination_x' in function_call.args and 'destination_y' in function_call.args:
                            target_coordinates = [function_call.args['destination_x'], function_call.args['destination_y']]
                        elif 'target_coordinate' in function_call.args:
                            target_coordinates = function_call.args['target_coordinate']
                        elif 'destination_coordinate' in function_call.args:
                            target_coordinates = function_call.args['destination_coordinate']
                        if target_coordinates:
                            action_details['target_coordinates'] = target_coordinates
                            action_details['target_coordinates_normalized'] = is_normalized_action
                        
                        # For type actions: extract text and submit flag
                        if 'text' in function_call.args:
                            action_details['text'] = function_call.args['text']
                        
                        # Gemini automatically submits (presses Enter) when typing
                        # This is important to track!
                        if function_call.name == 'type' or function_call.name == 'type_text':
                            action_details['submit'] = True  # Gemini's default behavior
                        
                        # For scroll actions
                        if 'direction' in function_call.args:
                            action_details['direction'] = function_call.args['direction']
                        if 'amount' in function_call.args:
                            action_details['amount'] = function_call.args['amount']
                        if 'magnitude' in function_call.args:
                            action_details['magnitude'] = function_call.args['magnitude']
                        
                        # For key press
                        if 'key' in function_call.args:
                            action_details['key'] = function_call.args['key']
                    
                    # Handle safety checks
                    extra_fields = {}
                    if function_call.args and "safety_decision" in function_call.args:
                        decision = self.optimized_agent._get_safety_confirmation(function_call.args["safety_decision"])
                        if decision == "TERMINATE":
                            self.logger.warning("🛑 Terminating due to safety check denial")
                            status = "COMPLETE"
                            break
                        extra_fields["safety_acknowledgement"] = "true"
                    
                    # ✅ BEFORE = Previous action's AFTER screenshot (what model saw when deciding)
                    screenshot_path_before = None
                    # ✅ Gemini's actual function names
                    visible_effect_actions = ['click_at', 'type_text_at', 'hover_at', 'scroll_at', 'scroll_document', 'keypress', 'key_combination', 'drag_and_drop', 'mouse_move', 'move', 'new_tab', 'switch_tab', 'close_tab', 'list_tabs']
                    if action_name in visible_effect_actions:
                        # Use the last AFTER screenshot we captured
                        if hasattr(self, '_last_after_screenshot'):
                            screenshot_path_before = self._last_after_screenshot
                            action_details['screenshot_before'] = screenshot_path_before
                            self.logger.info(f"📸 BEFORE = previous action's AFTER: {screenshot_path_before}")
                        else:
                            self.logger.info(f"📸 BEFORE = None (first action)")
                    
                    # ✅ Report action AFTER capturing before screenshot
                    all_items.append(action_details)
                    self._report_action(action_details)
                        
                    # Execute action
                    env_state = self.optimized_agent.handle_action(function_call)
                    
                    # Capture screenshot after action (action handler already waited)
                    # ✅ wait_for_settle=False because action handler already waited
                    screenshot_path_after = self.optimized_agent._take_screenshot(f"after_{function_call.name}", wait_for_settle=False)
                    if screenshot_path_after:
                        self.logger.info(f"📸 Saved AFTER screenshot: {screenshot_path_after}")
                        # ✅ Store this AFTER screenshot for next action's BEFORE
                        self._last_after_screenshot = screenshot_path_after
                        self.logger.info(f"📸 Stored AFTER for next action's BEFORE: {screenshot_path_after}")
                    
                    # Get current state for URL and screenshot if env_state is None
                    # This ensures we always have a valid URL for Gemini's function response
                    if not env_state:
                        try:
                            current_state = self.computer.current_state()
                            url = current_state.url if current_state else "about:blank"
                            screenshot_data = current_state.screenshot if current_state else b""
                        except Exception as e:
                            self.logger.warning(f"⚠️ Could not get current state: {e}")
                            # Fallback to ensure we always have a URL (Gemini requirement)
                            url = "about:blank"
                            screenshot_data = b""
                    else:
                        url = env_state.url if hasattr(env_state, 'url') else "about:blank"
                        screenshot_data = env_state.screenshot if hasattr(env_state, 'screenshot') else b""
                    
                    # Ensure URL is never None (Gemini API requirement)
                    if url is None:
                        url = "about:blank"
                    
                    # Add computer call output item with action details
                    output_details = {
                        "type": "computer_call_output",
                        "action": function_call.name,
                        "url": url,
                        "screenshot": screenshot_path_after,
                        "screenshot_after": screenshot_path_after,  # Explicit after screenshot
                        "timestamp": datetime.now().isoformat(),
                        **extra_fields
                    }
                    
                    # ✅ Add tool_input for timeline extraction (contains all function args)
                    if function_call.args:
                        output_details["tool_input"] = function_call.args
                    
                    # ✅ Add before screenshot if captured
                    if screenshot_path_before:
                        output_details["screenshot_before"] = screenshot_path_before
                    
                    # Copy action details to output as well
                    if function_call.args:
                        if 'x' in function_call.args and 'y' in function_call.args:
                            output_details['coordinates'] = [function_call.args['x'], function_call.args['y']]
                            output_details['coordinates_normalized'] = is_normalized_action
                        elif 'coordinate' in function_call.args:
                            output_details['coordinates'] = function_call.args['coordinate']
                            output_details['coordinates_normalized'] = is_normalized_action
                        
                        if 'start_coordinate' in function_call.args:
                            output_details['start_coordinates'] = function_call.args['start_coordinate']
                        elif 'start_x' in function_call.args and 'start_y' in function_call.args:
                            output_details['start_coordinates'] = [function_call.args['start_x'], function_call.args['start_y']]
                        
                        target_coordinates = None
                        if 'destination_x' in function_call.args and 'destination_y' in function_call.args:
                            target_coordinates = [function_call.args['destination_x'], function_call.args['destination_y']]
                        elif 'target_coordinate' in function_call.args:
                            target_coordinates = function_call.args['target_coordinate']
                        elif 'destination_coordinate' in function_call.args:
                            target_coordinates = function_call.args['destination_coordinate']
                        if target_coordinates:
                            output_details['target_coordinates'] = target_coordinates
                            output_details['target_coordinates_normalized'] = is_normalized_action
                        
                        if 'text' in function_call.args:
                            output_details['text'] = function_call.args['text']
                        
                        if function_call.name == 'type' or function_call.name == 'type_text':
                            output_details['submit'] = True
                        
                        if 'direction' in function_call.args:
                            output_details['direction'] = function_call.args['direction']
                        if 'amount' in function_call.args:
                            output_details['amount'] = function_call.args['amount']
                        if 'magnitude' in function_call.args:
                            output_details['magnitude'] = function_call.args['magnitude']
                        
                        if 'key' in function_call.args:
                            output_details['key'] = function_call.args['key']
                    
                    # ✅ Add tab_info for list_tabs actions (outside args check since list_tabs has no args)
                    if function_call.name == 'list_tabs':
                        # The inner optimized_agent returns EnvState, but we need the tab_info
                        # Get it directly from the computer
                        try:
                            tab_info = self.computer.list_tabs()
                            output_details['tab_info'] = tab_info
                            self.logger.debug(f"📑 ✅ Added tab_info to output_details: {tab_info}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Failed to get tab_info for timeline: {e}")
                    
                    all_items.append(output_details)
                    
                    # ✅ Report action output in real-time for live timeline
                    self._report_action(output_details)
                    
                    # Create function response for Gemini
                    function_responses.append(
                        FunctionResponse(
                            name=function_call.name,
                            response={
                                "url": url,
                                **extra_fields,
                            },
                            parts=[
                                FunctionResponsePart(
                                    inline_data=FunctionResponseBlob(
                                        mime_type="image/png",
                                        data=screenshot_data,
                                    )
                                )
                            ],
                        )
                    )
                    
                # Append function responses to conversation
                if function_responses:
                    self.optimized_agent.contents.append(
                        Content(
                            role="user",
                            parts=[Part(function_response=fr) for fr in function_responses],
                        )
                    )
                
            except CriticalAPIError as api_error:
                # Re-raise CriticalAPIError to crash immediately (skip verification)
                self.logger.error(f"🚨 CRITICAL API ERROR in iteration {turn}: {api_error}")
                raise
            except CriticalTimeoutError as timeout_error:
                # Re-raise CriticalTimeoutError to crash immediately (skip verification)
                self.logger.error(f"🚨 CRITICAL TIMEOUT ERROR in iteration {turn}: {timeout_error}")
                raise
            except Exception as e:
                self.logger.error(f"❌ Error in iteration {turn}: {e}")
                # Add error item
                all_items.append({
                    "type": "text",
                    "text": f"Error in iteration {turn}: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })
                # Check if this is a model failure
                if "MODEL_FAILURE" in str(status) or "No candidates" in str(e):
                    self.logger.error("🛑 Model failure detected - categorizing as model failure, not system crash")
                break
        
        # Log final status for debugging
        if hasattr(self, '_model_failure_detected') and self._model_failure_detected:
            self.logger.error("🛑 MODEL FAILURE - This should be categorized as 'failed' not 'crashed'")
        
        self.logger.info(f"✅ Agent loop completed after {turn} turns")
        return all_items


    def _save_conversation_export(self, conversation: List[Dict[str, Any]]):
        """Save exported conversation for debugging"""
        if not self.task_dir:
            return

        try:
            conversation_file = (
                Path(self.task_dir)
                / "conversation_history"
                / "gemini_conversation_export.json"
            )
            conversation_file.parent.mkdir(parents=True, exist_ok=True)

            with open(conversation_file, "w") as f:
                json.dump(conversation, f, indent=2, default=str)

            self.logger.info(f"💾 Gemini conversation exported to: {conversation_file}")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to save conversation export: {e}")

    def _extract_local_storage(
        self, task_id: str, gym_url: str = None
    ) -> Dict[str, Any]:
        """
        Extract localStorage from gym by delegating to the unified runner's method.
        
        This ensures consistency across all agents and uses the runner's robust
        implementation with proper error handling and fallback mechanisms.
        """
        # Delegate to the runner's implementation
        if hasattr(self, 'runner') and self.runner:
            return self.runner._extract_local_storage(task_id, gym_url)
        else:
            self.logger.error("❌ No runner available for localStorage extraction")
            return {
                "status": "failed",
                "error": "No runner available",
                "dump_filename": None,
                "keys_count": 0,
            }

    def get_model_type(self) -> str:
        """Get the model type"""
        return self._model_type

    def cleanup_resources(self):
        """Clean up agent resources"""
        try:
            # Clean up insighter if it exists
            if self.insighter:
                self.insighter.cleanup_resources()
                self.insighter = None
            
            # Clean up optimized agent
            if hasattr(self, "optimized_agent") and self.optimized_agent:
                self.optimized_agent.close()

            # Clean up screenshot helper
            if self.screenshot_helper:
                self.screenshot_helper = None

            self.logger.info("🧹 Gemini agent resources cleaned up")
        except Exception as e:
            self.logger.warning(f"⚠️ Error cleaning up Gemini agent resources: {e}")
    
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
