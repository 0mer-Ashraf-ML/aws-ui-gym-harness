"""
Gemini Agent - Wraps Google's genai SDK for Computer Use

Simple token optimization: Keep recent conversation history only to reduce token usage.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from google import genai
from google.genai import types
from google.genai.types import (
    Content,
    Part,
    GenerateContentConfig,
    Candidate,
    FunctionResponse,
    FinishReason,
)

from app.core.config import settings
from app.services.computers.shared.env_state import EnvState
from app.services.computers.error_handling import CriticalAPIError

# List of predefined Computer Use functions (Google's specification)
PREDEFINED_COMPUTER_USE_FUNCTIONS = [
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "keypress",
    "key_combination",
    "drag_and_drop",
    "new_tab",
    "switch_tab",
    "close_tab",
    "list_tabs",
]


class GeminiAgent:
    """
    Agent for executing tasks using Google Gemini Computer Use model.
    Follows Google's reference implementation pattern.

    Google's recommendations (preserved):
    - Temperature: 0.0 (deterministic)
    - Max recent screenshots: 3 (token optimization)
    - ComputerUse tool with all predefined functions enabled
    """

    def __init__(
        self,
        computer,  # Type: LocalPlaywrightBrowser or any browser with Gemini methods
        model_name: str = None,
        api_key: str = None,
        logger: logging.Logger = None,
        screenshot_dir: Path = None,
        screenshot_helper=None,  # ScreenshotHelper instance (matches OpenAI pattern)
    ):
        self.computer = computer
        self.model_name = model_name or settings.GEMINI_MODEL
        self.logger = logger or logging.getLogger(__name__)
        self.screenshot_dir = screenshot_dir
        self.screenshot_count = 0
        self.screenshot_helper = screenshot_helper  # Use same helper as OpenAI

        # Use settings if not provided
        api_key = api_key or settings.GEMINI_API_KEY

        # API key mode - default configuration for Gemini Computer Use
        self.logger.info("🔧 Initializing Gemini client in API key mode")
        self.client = genai.Client(
            api_key=api_key,
        )

        # Conversation history
        self.contents: List[Content] = []

        # Configuration for API calls (Google's recommendations)
        self.generate_content_config = GenerateContentConfig(
            temperature=settings.GEMINI_TEMPERATURE,  # 0.0 - Deterministic (Google recommendation)
            top_p=settings.GEMINI_TOP_P,
            top_k=settings.GEMINI_TOP_K,
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
            tools=[
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER,
                        excluded_predefined_functions=[],  # Use all functions (Google recommendation)
                    ),
                ),
            ],
        )
        
        # Add retry configuration for model blocking issues
        self.max_retries = 3
        self.retry_delay = 2.0
        
        # Track browser context issues for model guidance
        self.browser_context_issues = 0
        self.max_context_issues = 5  # Increased to 5 retries
        
        # Track model blocking issues
        self.model_blocking_issues = 0
        self.max_model_blocking_issues = 3
        
        # Simple token optimization: keep recent conversation history
        self.max_conversation_turns = settings.GEMINI_MAX_CONVERSATION_TURNS
        self.logger.info(f"💾 Token optimization: keeping last {self.max_conversation_turns} turns")
        self.logger.info(f"✅ Gemini Agent initialized with model: {self.model_name}")

        # Lightweight memory protocol and progress gating (computer-use friendly)
        self.memory_enabled = True
        self.memory_state: Dict[str, Any] = {
            "task": None,
            "last_url": None,
            "anchors": [],
            "last_action": None,
            "subgoal": None,
            "last_updated": None,
        }
        self.no_progress_count = 0
        self.max_no_progress_turns = 3

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup Gemini client resources"""
        self.close()

    def close(self):
        """Close Gemini client and cleanup resources"""
        try:
            self.logger.info("🧹 Closing Gemini client...")

            # Clear conversation history to free memory
            if hasattr(self, "contents"):
                self.contents.clear()
                self.logger.debug("Cleared conversation history")

            # Close the Gemini client if it has a close method
            if hasattr(self, "client") and self.client:
                if hasattr(self.client, "close"):
                    self.client.close()
                    self.logger.info("✅ Gemini client closed")
                elif hasattr(self.client, "__exit__"):
                    self.client.__exit__(None, None, None)
        except Exception as e:
            self.logger.warning(f"⚠️ Error closing Gemini client: {e}")
    
    def _is_function_response(self, content: Content) -> bool:
        """Check if a content message contains function responses"""
        if not content.parts:
            return False
        return any(part.function_response for part in content.parts)
    
    def _is_function_call(self, content: Content) -> bool:
        """Check if a content message contains function calls"""
        if not content.parts:
            return False
        return any(part.function_call for part in content.parts)
    
    def _trim_conversation_history(self):
        """
        Quality-first retention: keep last N complete turns (assistant function_call + user function_response).
        - Always preserve the initial task message at index 0.
        - Never split a function_call/function_response pair.
        - Allow up to +2 messages to preserve a pair.
        """
        if not self.contents or len(self.contents) <= 2:
            return
        # Count function_response messages to determine number of turns
        total_turns = sum(1 for c in self.contents if self._is_function_response(c))
        if total_turns <= self.max_conversation_turns:
            return
        # Identify start index to keep the last N turns
        turns_to_keep = self.max_conversation_turns
        needed = turns_to_keep
        idx = len(self.contents) - 1
        start_index = 1  # default after initial task
        while idx >= 1 and needed > 0:
            if self._is_function_response(self.contents[idx]):
                # Find the preceding function_call (scan backward skipping memory/text)
                j = idx - 1
                while j >= 1 and not self._is_function_call(self.contents[j]):
                    j -= 1
                # If found, set start_index to earliest such call for this turn
                start_index = max(1, j)
                needed -= 1
            idx -= 1
        # Ensure we begin at a function_call if the next is a function_response
        if start_index < len(self.contents) - 1 and self._is_function_response(self.contents[start_index]):
            prev_idx = start_index - 1
            if prev_idx >= 1 and self._is_function_call(self.contents[prev_idx]):
                self.logger.debug(f"🔒 Adjusted cutoff from {start_index} to {prev_idx} to preserve function pair")
                start_index = prev_idx
        # Apply trimming while preserving initial task
        kept_len_before = len(self.contents)
        self.contents = [self.contents[0]] + self.contents[start_index:]
        self.logger.debug(f"💾 Trimmed conversation history: {kept_len_before} → {len(self.contents)} (kept from index {start_index})")

    def _append_memory_read_prompt(self):
        """Inject a compact memory snapshot before each model call (as user text)."""
        if not self.memory_enabled:
            return
        try:
            mem = {
                "task": self.memory_state.get("task"),
                "last_url": self.memory_state.get("last_url"),
                "anchors": self.memory_state.get("anchors") or [],
                "last_action": self.memory_state.get("last_action"),
                "subgoal": self.memory_state.get("subgoal"),
            }
            self.contents.append(Content(role="user", parts=[Part(text=f"MEMORY_READ: {mem}")]))
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to append memory read prompt: {e}")

    def _append_memory_write_update(self, last_action: Optional[str], current_url: Optional[str]):
        """Append a compact memory update after actions (as user text)."""
        if not self.memory_enabled:
            return
        try:
            self.memory_state["last_action"] = last_action or self.memory_state.get("last_action")
            if current_url:
                self.memory_state["last_url"] = current_url
            self.memory_state["last_updated"] = time.time()
            update = {
                "last_action": self.memory_state["last_action"],
                "last_url": self.memory_state.get("last_url"),
                "subgoal": self.memory_state.get("subgoal"),
            }
            self.contents.append(Content(role="user", parts=[Part(text=f"MEMORY_WRITE: {update}")]))
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to append memory write update: {e}")

    def handle_action(self, action: types.FunctionCall) -> EnvState:
        """Execute a computer action and return the new environment state"""
        action_name = action.name
        args = action.args or {}

        self.logger.info(f"🖥️ Executing action: {action_name}({args})")

        try:
            # Route action to appropriate computer method
            if action_name == "open_web_browser":
                result = self.computer.open_web_browser()
                # Reset context issue counter on successful browser action
                self.browser_context_issues = 0
                return result
            elif action_name == "click_at":
                return self.computer.click_at(x=args["x"], y=args["y"])
            elif action_name == "hover_at":
                return self.computer.hover_at(x=args["x"], y=args["y"])
            elif action_name == "type_text_at":
                return self.computer.type_text_at(
                    x=args["x"],
                    y=args["y"],
                    text=args["text"],
                    press_enter=args.get("press_enter", False),
                    clear_before_typing=args.get("clear_before_typing", True),
                )
            elif action_name == "scroll_document":
                return self.computer.scroll_document(direction=args["direction"])
            elif action_name == "scroll_at":
                return self.computer.scroll_at(
                    x=args["x"],
                    y=args["y"],
                    direction=args["direction"],
                    magnitude=args.get("magnitude", 800),
                )
            elif action_name == "wait_5_seconds":
                return self.computer.wait_5_seconds()
            elif action_name == "go_back":
                return self.computer.go_back()
            elif action_name == "go_forward":
                return self.computer.go_forward()
            elif action_name == "search":
                return self.computer.search()
            elif action_name == "navigate":
                result = self.computer.navigate(url=args["url"])
                # Reset context issue counter on successful navigation
                self.browser_context_issues = 0
                return result
            elif action_name == "keypress":
                keys = (
                    args["keys"].split("+")
                    if isinstance(args["keys"], str)
                    else args["keys"]
                )
                # Map common key names for compatibility
                key_mappings = {
                    "control": "ctrl",
                    "cmd": "meta",
                    "command": "meta",
                    "option": "alt",
                    "escape": "esc",
                    "return": "enter",
                    "spacebar": "space",
                    "left": "arrowleft",
                    "right": "arrowright",
                    "up": "arrowup",
                    "down": "arrowdown",
                }
                keys = [key_mappings.get(key.lower(), key) for key in keys]
                return self.computer.keypress(keys=keys)
            elif action_name == "key_combination":
                keys = (
                    args["keys"].split("+")
                    if isinstance(args["keys"], str)
                    else args["keys"]
                )
                # Map common key names for compatibility
                key_mappings = {
                    "control": "ctrl",
                    "cmd": "meta",
                    "command": "meta",
                    "option": "alt",
                    "escape": "esc",
                    "return": "enter",
                    "spacebar": "space",
                    "left": "arrowleft",
                    "right": "arrowright",
                    "up": "arrowup",
                    "down": "arrowdown",
                }
                keys = [key_mappings.get(key.lower(), key) for key in keys]
                return self.computer.keypress(keys=keys)
            elif action_name == "drag_and_drop":
                # Validate required coordinates to avoid KeyError like "'destination_x'"
                for key in ("x", "y", "destination_x", "destination_y"):
                    if key not in args:
                        raise ValueError(
                            f"drag_and_drop missing required argument '{key}'; got keys={list(args.keys())}"
                        )
                return self.computer.drag_and_drop(
                    x=args["x"],
                    y=args["y"],
                    destination_x=args["destination_x"],
                    destination_y=args["destination_y"],
                )
            elif action_name == "new_tab":
                # Open a new tab (Playwright API, not keyboard shortcut)
                url = args.get("url", "")
                result = self.computer.new_tab(url=url)
                self.browser_context_issues = 0
                return result
            elif action_name == "switch_tab":
                # Switch to a specific tab by index (Playwright API, not keyboard shortcut)
                # Gemini uses 'index' parameter, not 'tab_index'
                tab_index = args.get("index", args.get("tab_index", 0))
                result = self.computer.switch_tab(tab_index=tab_index)
                self.browser_context_issues = 0
                return result
            elif action_name == "close_tab":
                # Close the current tab (Playwright API, not keyboard shortcut)
                result = self.computer.close_tab()
                self.browser_context_issues = 0
                return result
            elif action_name == "list_tabs":
                # Get information about all open tabs
                tab_info = self.computer.list_tabs()
                self.logger.info(f"📑 Tab info: {tab_info}")
                
                # Generate visual screenshot of tabs for the model to see
                tab_screenshot_bytes = None
                try:
                    from app.services.computers.shared.tab_visualizer import TabVisualizer
                    import base64
                    from datetime import datetime
                    visualizer = TabVisualizer()
                    tab_screenshot_bytes = visualizer.generate_tab_screenshot(tab_info)
                    
                    # Save the tab screenshot
                    if tab_screenshot_bytes:
                        screenshot_path = self._take_screenshot_from_bytes(
                            tab_screenshot_bytes,
                            "list_tabs_view"
                        )
                        if screenshot_path:
                            self.logger.info(f"📸 Saved tab visualization screenshot: {screenshot_path}")
                except Exception as viz_error:
                    self.logger.warning(f"⚠️ Failed to generate tab visualization: {viz_error}")
                
                # Return the tab visualization in the state so the model can SEE it
                # Create a special EnvState with the tab visualization screenshot
                if tab_screenshot_bytes:
                    import base64
                    from datetime import datetime
                    tab_screenshot_base64 = base64.b64encode(tab_screenshot_bytes).decode('utf-8')
                    
                    # Get current URL
                    current_url = self.computer.get_current_url() if hasattr(self.computer, 'get_current_url') else "about:tabs"
                    
                    # Create EnvState with tab visualization screenshot
                    # EnvState only accepts: screenshot, url, timestamp
                    state = EnvState(
                        screenshot=tab_screenshot_base64,
                        url=current_url,
                        timestamp=datetime.now().isoformat()
                    )
                    self.logger.info(f"✅ Returning tab visualization screenshot to model with {tab_info.get('tab_count', 0)} tabs")
                    return state
                else:
                    # Fallback to regular state if visualization failed
                    self.logger.warning(f"⚠️ Tab visualization failed, falling back to regular screenshot")
                    return self.computer.current_state()
            else:
                raise ValueError(f"Unsupported action: {action_name}")
        except Exception as e:
            # Import CriticalTimeoutError here to avoid circular imports
            from app.services.computers.error_handling import CriticalTimeoutError
            
            # Don't catch CriticalTimeoutError - let it propagate to crash the task
            if isinstance(e, CriticalTimeoutError):
                self.logger.error(f"🚨 CRITICAL TIMEOUT in {action_name}: {e}")
                raise  # This will crash the entire task
            else:
                # Re-raise other exceptions as-is
                raise

    def get_model_response(
        self, max_retries: int = None
    ) -> types.GenerateContentResponse:
        """Generate content with retry logic"""
        max_retries = max_retries or settings.GEMINI_MAX_API_RETRIES
        retry_delay = settings.GEMINI_API_RETRY_DELAY
        
        # Prepend memory snapshot for state grounding
        self._append_memory_read_prompt()

        # Trim conversation history before API call
        self._trim_conversation_history()

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=self.contents,
                    config=self.generate_content_config,
                )
                return response
            except Exception as e:
                self.logger.error(f"API call attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    delay = retry_delay * (2**attempt)
                    self.logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    self.logger.error(f"All {max_retries} API attempts failed")
                    # Raise CriticalAPIError to crash immediately (skip verification)
                    raise CriticalAPIError(f"Gemini API call failed after {max_retries} attempts. Last error: {str(e)}") from e

    def get_text(self, candidate: Candidate) -> Optional[str]:
        """Extract text from candidate response"""
        if not candidate.content or not candidate.content.parts:
            return None
        text = []
        for part in candidate.content.parts:
            if part.text:
                text.append(part.text)
        return " ".join(text) or None

    def extract_function_calls(self, candidate: Candidate) -> List[types.FunctionCall]:
        """Extract function calls from candidate response"""
        if not candidate.content or not candidate.content.parts:
            return []
        function_calls = []
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append(part.function_call)
        return function_calls

    def _get_safety_confirmation(
        self, safety: Dict[str, Any]
    ) -> Literal["CONTINUE", "TERMINATE"]:
        """Handle safety confirmation (for automation, we auto-approve)"""
        if safety["decision"] != "require_confirmation":
            raise ValueError(f"Unknown safety decision: {safety['decision']}")

        self.logger.warning(
            f"⚠️ Safety check: {safety.get('explanation', 'No explanation')}"
        )

        # For automated testing, we auto-approve (similar to OpenAI implementation)
        self.logger.info("✅ Auto-approving safety check for automated testing")
        return "CONTINUE"

    def _take_screenshot(self, step_name: str, wait_for_settle: bool = True) -> Optional[str]:
        """
        Take a screenshot and save to screenshot directory
        Uses ScreenshotHelper if available (matches OpenAI pattern)
        
        Args:
            step_name: Name for the screenshot file
            wait_for_settle: If True, wait 0.9s for DOM to settle before screenshot.
                           Set to False for "before" screenshots to capture immediate state.
        """
        # Debug logging to diagnose screenshot issues
        self.logger.debug(
            f"🔍 _take_screenshot called: step_name={step_name}, wait_for_settle={wait_for_settle}, screenshot_helper={self.screenshot_helper is not None}, screenshot_dir={self.screenshot_dir}"
        )

        # If screenshot_helper is provided (OpenAI pattern), use it
        if self.screenshot_helper:
            try:
                screenshot_path = self.screenshot_helper.take_and_save_screenshot(
                    self.computer, step_name, wait_for_settle=wait_for_settle
                )
                if screenshot_path:
                    self.logger.info(f"📸 Saved screenshot: {screenshot_path}")
                return screenshot_path
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to save screenshot via helper: {e}")
                return None

        # Fallback to original implementation if no helper
        if not self.screenshot_dir:
            self.logger.warning(
                f"⚠️ Cannot take screenshot '{step_name}': screenshot_helper={self.screenshot_helper is not None}, screenshot_dir={self.screenshot_dir}"
            )
            self.logger.debug(
                f"Cannot take screenshot '{step_name}': screenshot_helper={self.screenshot_helper is not None}, screenshot_dir={self.screenshot_dir}"
            )
            return None

        try:
            from datetime import datetime

            screenshot_dir = Path(self.screenshot_dir)
            screenshot_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.screenshot_count += 1
            filename = f"{step_name}_{timestamp}_{self.screenshot_count:03d}.png"
            screenshot_path = screenshot_dir / filename

            # ✅ Get screenshot from computer: use immediate for BEFORE, normal for AFTER
            if not wait_for_settle and hasattr(self.computer, 'screenshot_immediate'):
                # BEFORE: capture immediately
                screenshot_base64 = self.computer.screenshot_immediate()
                import base64
                screenshot_bytes = base64.b64decode(screenshot_base64)
                self.logger.info(f"📸 Used immediate screenshot (no wait) for {step_name}")
            else:
                # AFTER: use normal current_state (includes wait)
                state = self.computer.current_state()
                screenshot_bytes = state.screenshot
            
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)

            self.logger.info(f"📸 Saved screenshot: {screenshot_path}")
            return str(screenshot_path)

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to save screenshot: {e}")
            return None

    def _take_screenshot_from_bytes(self, screenshot_bytes: bytes, step_name: str) -> Optional[str]:
        """
        Save screenshot from bytes data
        
        Args:
            screenshot_bytes: The screenshot as bytes
            step_name: Name for the screenshot file
            
        Returns:
            Path to saved screenshot file or None if failed
        """
        if not self.screenshot_dir:
            self.logger.warning(f"⚠️ Cannot save screenshot '{step_name}': no screenshot_dir set")
            return None
        
        try:
            from datetime import datetime
            from pathlib import Path
            
            screenshot_dir = Path(self.screenshot_dir)
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.screenshot_count += 1
            filename = f"{step_name}_{timestamp}_{self.screenshot_count:03d}.png"
            screenshot_path = screenshot_dir / filename
            
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)
            
            self.logger.info(f"📸 Saved screenshot from bytes: {screenshot_path}")
            return str(screenshot_path)
            
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to save screenshot from bytes: {e}")
            return None

    def run_one_iteration(self) -> Literal["COMPLETE", "CONTINUE"]:
        """Run one iteration of the agent loop"""
        try:
            # Generate response from model
            self.logger.info("🤖 Generating response from Gemini...")
            response = self.get_model_response()

            if not response.candidates:
                self.logger.error("❌ No candidates in response")
                return "COMPLETE"

            candidate = response.candidates[0]

            # Append model response to conversation
            if candidate.content:
                self.contents.append(candidate.content)

            # Extract reasoning and function calls
            reasoning = self.get_text(candidate)
            function_calls = self.extract_function_calls(candidate)

            # Handle model blocking (no response)
            if not reasoning and not function_calls:
                self.model_blocking_issues += 1
                self.logger.warning(f"⚠️ Model blocking detected ({self.model_blocking_issues}/{self.max_model_blocking_issues}) - no response from model")
                
                # Crash if exceeded max (using > allows max retries, then crashes on max+1)
                if self.model_blocking_issues > self.max_model_blocking_issues:
                    self.logger.error(f"❌ CRITICAL: Model blocked {self.model_blocking_issues} times (exceeded max {self.max_model_blocking_issues}) - crashing task")
                    raise RuntimeError(f"Model blocked {self.model_blocking_issues} times - task crashed")
                
                # Add a prompt to encourage the model to respond
                self.contents.append(Content(
                    role="user",
                    parts=[Part(text="Please provide a response. If you're stuck, try a simple action like clicking or typing.")]
                ))
                return "CONTINUE"

            # Handle malformed function calls
            if (
                not function_calls
                and not reasoning
                and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL
            ):
                self.logger.warning("⚠️ Malformed function call, retrying...")
                return "CONTINUE"

            # If no function calls, task is complete
            if not function_calls:
                self.logger.info(f"✅ Task complete: {reasoning}")
                # Reset blocking counter on successful completion
                self.model_blocking_issues = 0
                return "COMPLETE"

            # Log reasoning and function calls
            if reasoning:
                self.logger.info(f"💭 Reasoning: {reasoning}")
            
            # Reset model blocking counter on successful function calls
            self.model_blocking_issues = 0

            # Execute function calls
            function_responses = []
            last_action_name: Optional[str] = None
            last_seen_url: Optional[str] = None
            for function_call in function_calls:
                extra_fields = {}

                # Log action in OpenAI format: action_type(args)
                self.logger.info(f"{function_call.name}({function_call.args})")
                last_action_name = function_call.name

                # Handle safety checks
                if function_call.args and "safety_decision" in function_call.args:
                    decision = self._get_safety_confirmation(
                        function_call.args["safety_decision"]
                    )
                    if decision == "TERMINATE":
                        self.logger.warning("🛑 Terminating due to safety check denial")
                        return "COMPLETE"
                    extra_fields["safety_acknowledgement"] = "true"

                # Execute action
                env_state = self.handle_action(function_call)

                # Capture screenshot after action (matches OpenAI/Anthropic pattern)
                screenshot_path_after = self._take_screenshot(
                    f"after_{function_call.name}"
                )
                if screenshot_path_after:
                    self.logger.info(f"📸 Saved screenshot: {screenshot_path_after}")

                # ✅ CRITICAL FIX: Reuse the saved screenshot instead of capturing a new one!
                # Read the file we just saved to ensure API gets EXACT SAME screenshot
                current_screenshot = b""
                if screenshot_path_after:
                    from pathlib import Path
                    screenshot_file = Path(screenshot_path_after)
                    if screenshot_file.exists():
                        with open(screenshot_file, 'rb') as f:
                            current_screenshot = f.read()
                        self.logger.info(f"📸 Reusing saved screenshot for API (no double capture)")
                
                # Get current state for URL (but NOT screenshot - we already have it!)
                if not env_state:
                    try:
                        # Only get URL, not screenshot (we already have it from saved file)
                        current_url = self.computer.get_current_url() if hasattr(self.computer, 'get_current_url') else "about:blank"
                        # ✅ Keep current_screenshot from saved file (don't overwrite!)
                        # current_screenshot already set above from saved file
                    except Exception as e:
                        self.logger.warning(f"⚠️ Could not get current state: {e}")
                        # Check if this is a browser context error - let model handle it
                        if "Page is closed or invalid" in str(e) or "NoneType" in str(e):
                            self.browser_context_issues += 1
                            self.logger.warning(f"🔄 Browser context issue detected ({self.browser_context_issues}/{self.max_context_issues}) - asking model for guidance")
                            
                            # Try to get a screenshot anyway for the model to see
                            try:
                                if hasattr(self.computer, '_page') and self.computer._page:
                                    current_screenshot = self.computer._page.screenshot(type='png', full_page=False)
                                else:
                                    current_screenshot = b""
                            except:
                                current_screenshot = b""
                            
                            # Crash if exceeded max (using > allows max retries, then crashes on max+1)
                            if self.browser_context_issues > self.max_context_issues:
                                self.logger.error(f"❌ CRITICAL: Browser context lost {self.browser_context_issues} times (exceeded max {self.max_context_issues}) - crashing task")
                                raise RuntimeError(f"Browser context lost {self.browser_context_issues} times - task crashed")
                            
                            # Provide context to the model about the issue
                            if self.browser_context_issues >= self.max_context_issues:
                                current_url = f"CRITICAL: Browser context lost {self.browser_context_issues} times. Task may need to be restarted. Consider using open_web_browser() to restart."
                            else:
                                current_url = f"Browser context lost (attempt {self.browser_context_issues}/{self.max_context_issues}). Available recovery actions: open_web_browser(), navigate(url), or search()."
                        else:
                            # Fallback to ensure we always have a URL (Gemini requirement)
                            current_url = "about:blank"
                            current_screenshot = b""
                else:
                    current_url = env_state.url if hasattr(env_state, "url") else "about:blank"
                    # ✅ Keep current_screenshot from saved file (don't use env_state.screenshot)
                    # current_screenshot already set above from saved file
                    # This ensures API gets EXACT SAME screenshot we saved for tracking
                
                # Ensure URL is never None (Gemini API requirement)
                if current_url is None:
                    current_url = "about:blank"

                # Create function response
                last_seen_url = current_url
                function_responses.append(
                    FunctionResponse(
                        name=function_call.name,
                        response={
                            "url": current_url,
                            **extra_fields,
                        },
                        parts=[
                            types.FunctionResponsePart(
                                inline_data=types.FunctionResponseBlob(
                                    mime_type="image/png",
                                    data=current_screenshot,
                                )
                            )
                        ],
                    )
                )

            # Append function responses to conversation
            self.contents.append(
                Content(
                    role="user",
                    parts=[Part(function_response=fr) for fr in function_responses],
                )
            )

            # NOTE: Screenshot trimming disabled to match OpenAI/Anthropic behavior
            # We keep all screenshots for complete task evidence and verification
            # (Google recommends trimming to 3 for token optimization, but we prioritize completeness)

            # Update memory and progress gating after turn actions
            try:
                previous_url = self.memory_state.get("last_url")
                self._append_memory_write_update(last_action_name, last_seen_url)
                if last_seen_url and previous_url and last_seen_url == previous_url:
                    self.no_progress_count += 1
                else:
                    self.no_progress_count = 0
                if self.no_progress_count >= self.max_no_progress_turns:
                    # Hint the model to change strategy on next turn
                    self.contents.append(Content(role="user", parts=[Part(text="NO_PROGRESS_DETECTED: Consider search(), navigate(url), or alternative navigation to change state.")]))
                    # Do not spam; reset counter
                    self.no_progress_count = 0
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to update memory/progress: {e}")

            return "CONTINUE"

        except Exception as e:
            self.logger.error(f"❌ Error in iteration: {e}")
            raise

    def agent_loop(
        self, query: str, initial_screenshot: bytes = None, max_turns: int = None
    ) -> Dict[str, Any]:
        """
        Run the full agent loop for a task.

        Args:
            query: Task description
            initial_screenshot: Optional initial screenshot
            max_turns: Maximum number of iterations (defaults to settings)

        Returns:
            Dictionary with execution results
        """
        max_turns = max_turns or settings.GEMINI_MAX_TURNS
        self.logger.info(f"🚀 Starting agent loop for task: {query}")

        # Initialize conversation with user query
        parts = [Part(text=query)]
        if initial_screenshot:
            parts.append(
                Part.from_bytes(data=initial_screenshot, mime_type="image/png")
            )

        self.contents = [Content(role="user", parts=parts)]
        # Initialize memory with task
        try:
            if self.memory_enabled:
                self.memory_state["task"] = query
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to initialize memory task: {e}")

        # Run agent loop
        turn = 0
        status = "CONTINUE"

        while status == "CONTINUE" and turn < max_turns:
            turn += 1
            self.logger.info(f"🔄 Turn {turn}/{max_turns}")
            status = self.run_one_iteration()

        if turn >= max_turns:
            self.logger.warning(f"⚠️ Max turns ({max_turns}) reached")

        self.logger.info(f"✅ Agent loop completed after {turn} turns")

        # Get final URL safely using current_state()
        final_url = None
        try:
            state = self.computer.current_state()
            final_url = state.url if state and hasattr(state, "url") else None
        except Exception as e:
            self.logger.warning(f"⚠️ Could not get final URL: {e}")

        return {
            "status": "completed" if status == "COMPLETE" else "max_turns_reached",
            "total_turns": turn,
            "final_url": final_url,
        }

    def export_conversation(self) -> List[Dict[str, Any]]:
        """Return a JSON-serializable view of the conversation history."""
        export: List[Dict[str, Any]] = []

        for idx, content in enumerate(self.contents or []):
            item: Dict[str, Any] = {"index": idx, "role": content.role, "parts": []}

            for part in content.parts or []:
                part_payload: Dict[str, Any] = {}

                if part.text:
                    part_payload.update({"type": "text", "text": part.text})
                elif part.function_call:
                    args = dict(part.function_call.args or {})
                    part_payload.update(
                        {
                            "type": "function_call",
                            "function_call": {
                                "name": part.function_call.name,
                                "args": args,
                            },
                        }
                    )
                elif part.function_response:
                    response = dict(part.function_response.response or {})
                    has_inline_image = False
                    for response_part in part.function_response.parts or []:
                        inline_data = getattr(response_part, "inline_data", None)
                        if inline_data and getattr(inline_data, "data", None):
                            has_inline_image = True
                            break

                    part_payload.update(
                        {
                            "type": "function_response",
                            "function_response": {
                                "name": part.function_response.name,
                                "response": response,
                                "has_image": has_inline_image,
                            },
                        }
                    )

                if part_payload:
                    item["parts"].append(part_payload)

            export.append(item)

        return export
