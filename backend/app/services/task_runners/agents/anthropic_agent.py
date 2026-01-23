#!/usr/bin/env python3
"""
Anthropic Agent - Complete independent implementation extracted from V1
No V1 dependencies - completely self-contained
"""

import json
import os
import time
import random
import logging
from typing import Callable, List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic, APIError, APIResponseValidationError, APIStatusError
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
    BetaToolUnionParam,
)

from app.core.config import settings
from app.services.computers import Computer
from app.services.computers.utils import (check_blocklisted_url,
                                           create_response, pp, show_image)
from app.services.computers.error_handling import CriticalTimeoutError, CriticalAPIError
from .base_agent import BaseAgent
from ..helpers.screenshot_helper import ScreenshotHelper
from ..insights.insighter import Insighter


class AnthropicAgent(BaseAgent):
    """
    Complete Anthropic Computer Use Agent - Independent implementation
    Extracted from V1 SimpleAnthropicAgent with no dependencies
    """

    def __init__(
        self,
        computer=None,
        tools=None,
        acknowledge_safety_check_callback=None,
        logger=None,
        task_dir=None,
        critical_error_tracker=None,
        iteration_id=None,
        execution_id=None,
    ):
        """Initialize the Anthropic agent with complete independent implementation"""
        super().__init__(computer, logger, task_dir)
        
        # Set model type
        self._model_type = 'anthropic'
        
        # Store parameters
        self.model = "claude-sonnet-4-20250514"
        self.computer = computer
        self.print_steps = True
        self.debug = False
        self.show_images = False
        self.acknowledge_safety_check_callback = acknowledge_safety_check_callback or (lambda _: False)
        self.critical_error_tracker = critical_error_tracker
        
        # Store IDs for token tracking
        self.iteration_id = iteration_id
        self.execution_id = execution_id
        if self.logger:
            self.logger.info(f"🔧 AnthropicAgent initialized with iteration_id={iteration_id}, execution_id={execution_id}")
        
        # Initialize Anthropic client
        # Use settings instead of os.getenv() to read from .env file
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required. Set it in backend/.env file or environment variables.")
        self.anthropic_client = Anthropic(api_key=api_key, max_retries=4)
        
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
            self.logger.info("✅ Insighter initialized for Anthropic agent")
        else:
            self.logger.info("ℹ️ Insighter will be initialized later when task directory is available")
        
        # Initialize insights storage
        self.final_insights = None
        
        # Simple token optimization
        self.max_tokens = settings.ANTHROPIC_MAX_TOKENS
        self.max_messages = settings.ANTHROPIC_MAX_CONVERSATION_MESSAGES
        
        if self.logger:
            self.logger.info("✅ Anthropic agent initialized with complete independent implementation")
            self.logger.info(f"💾 Token optimization: max_tokens={self.max_tokens}, keep last {self.max_messages} messages")

    def update_task_directory(self, task_dir: str) -> None:
        """Update task directory and reinitialize insighter if needed"""
        if task_dir and not self.insighter:
            # Initialize insighter if it wasn't initialized before
            # self.insighter = Insighter(logger=self.logger, task_dir=task_dir)
            self.logger.info("✅ Insighter initialized for Anthropic agent (late initialization)")
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

    def _take_screenshot(self, step_name: str, iteration: int = None, wait_for_settle: bool = True) -> str:
        """
        Take screenshot and save to task directory - matches agent.py behavior
        
        Args:
            step_name: Name of the step/action
            iteration: Optional iteration number
            wait_for_settle: If True, wait 0.9s for DOM to settle before screenshot.
                           Set to False for "before" screenshots to capture immediate state.
        """
        if not self.task_dir:
            self.logger.warning("⚠️ No task directory available for screenshot")
            return None
            
        # Convert task_dir to Path if it's a string
        task_dir_path = Path(self.task_dir) if isinstance(self.task_dir, str) else self.task_dir
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')  # Add microseconds for uniqueness
        if iteration is not None:
            filename = f"iteration_{iteration}_{step_name}_{timestamp}.png"
        else:
            filename = f"{step_name}_{timestamp}.png"
        
        screenshot_path = task_dir_path / "screenshots" / filename
        
        self.logger.info(f"📸 Taking screenshot: {filename} (wait_for_settle={wait_for_settle})")
        
        try:
            if not self.computer:
                self.logger.error("❌ Computer not initialized for screenshot")
                return None
            
            # ✅ For BEFORE screenshots: Use immediate capture (no waiting)
            # ✅ For AFTER screenshots: Wait then use normal capture
            if not wait_for_settle:
                # Use immediate screenshot method if available (no waiting at all)
                if hasattr(self.computer, 'screenshot_immediate'):
                    screenshot_data = self.computer.screenshot_immediate()
                    self.logger.info(f"📸 Used immediate screenshot (no wait) for {step_name}")
                else:
                    # Fallback to regular screenshot
                    screenshot_data = self.computer.screenshot()
                    self.logger.warning(f"⚠️ No immediate screenshot available, using regular for {step_name}")
            else:
                # AFTER screenshot: wait then capture
                time.sleep(0.9)
                screenshot_data = self.computer.screenshot()
            
            if not screenshot_data:
                self.logger.warning(f"⚠️ No screenshot data returned for {step_name}")
                return None
            
            # Handle different screenshot data formats
            if isinstance(screenshot_data, str) and os.path.exists(screenshot_data):
                # It's a file path, copy it
                import shutil
                shutil.copy2(screenshot_data, screenshot_path)
            elif isinstance(screenshot_data, bytes):
                # It's bytes, write directly
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data)
            elif isinstance(screenshot_data, str):
                # Handle base64 encoded data
                if screenshot_data.startswith('data:image/'):
                    # Extract base64 data from data URL
                    base64_data = screenshot_data.split(',')[1]
                else:
                    base64_data = screenshot_data
                
                # Decode base64 and save
                import base64
                image_data = base64.b64decode(base64_data)
                with open(screenshot_path, 'wb') as f:
                    f.write(image_data)
            else:
                self.logger.warning(f"⚠️ Unknown screenshot data format: {type(screenshot_data)}")
                return None
            
            self.logger.info(f"📸 Screenshot captured: {filename}")
            return str(screenshot_path)
                
        except Exception as e:
            self.logger.error(f"❌ Failed to capture screenshot for {step_name}: {e}")
            return None

    def _create_system_prompt(self) -> List[Dict]:
        """
        Create a stable, cached system prompt for computer use tasks.
        - Stable content (no dynamic values) to maximize prompt caching.
        - Explicit memory protocol: read first, write last each turn.
        - Strict pairing: no user messages between tool_use and tool_result.
        """
        return [
            {
                "type": "text",
                "text": """You are an expert computer automation agent. Complete tasks reliably with strict tool pairing.

- computer: Screenshots, clicks, typing, scrolling, navigation, tab management
- bash: Execute commands  
- str_replace_editor: Edit files
- memory: Store progress and findings

STRICT TOOL PAIRING:
- Every tool_use MUST be immediately followed by a user tool_result in the next message.
- Do NOT insert any other user content (text, screenshots) between tool_use and tool_result.
- If a tool fails, still return a tool_result with a concise error summary.

TAB MANAGEMENT - STAY IN CONTEXT:
CRITICAL: Before opening any new tab, ALWAYS call list_tabs() first to check what's already open!

Tab Strategy:
1. Call list_tabs() to see all open tabs and their URLs
2. If the page you need is already open → use switch_tab(index) or Ctrl+Tab to switch to it
3. Only use new_tab(url) if the page is NOT already open
4. This prevents duplicate tabs and is more efficient

Keyboard Shortcuts (for cycling through existing tabs):
- Ctrl+T: Switch to next tab (circular)
- Ctrl+W: Close current tab  
- Ctrl+Tab: Switch to next tab (same as Ctrl+T)
- Ctrl+Shift+Tab: Switch to previous tab
- Ctrl+1-9: Switch to specific tab (1-9)

Direct Functions:
- {"action": "list_tabs"} - Returns: {"tab_count": 2, "current_tab_index": 0, "tabs": [{"index": 0, "url": "...", "is_current": true}, ...]}
- {"action": "new_tab", "url": "https://example.com"} - Open a NEW tab (only if not already open!)
- {"action": "switch_tab", "tab_index": 0} - Switch to specific tab by index
- {"action": "close_tab"} - Close current tab

Example workflow for multi-site tasks:
1. list_tabs() → See tabs: [{"index": 0, "url": "https://site-a.com"}, {"index": 1, "url": "https://site-b.com"}]
2. switch_tab(1) OR press Ctrl+Tab → Switch to second site
3. Ctrl+Tab again → Switch back to first site (circular)
4. If you need a third site: Check list_tabs() first, then new_tab() only if not open
MEMORY PROTOCOL (per turn):
1) First tool: memory.read with keys: {task_id, url, anchors, last_action, subgoal}
2) Perform minimal actions required to progress the task using computer/bash/editor.
3) Last tool: memory.write with a short JSON state update:
   {
     "task_id": "...",
     "url": "...",
     "anchors": ["#cart", ".btn-primary", ...],
     "last_action": "...",
     "subgoal": "..."
   }

QUALITY STRATEGY:
- Use memory to avoid rediscovery; keep updates concise.
- Prefer short perceive–act cycles. If no progress after several actions, switch strategy (search, direct URL, alternate navigation).
- Keep natural text brief; spend tokens on precise actions and perception.
- Consider using browser tabs for complex multi-page tasks.

IMPORTANT: Do not include extra user messages between paired tool_use and tool_result. Screenshots may be included inside tool_result content when needed for verification.""",
                "cache_control": {"type": "ephemeral"}
            }
        ]

    def _has_tool_result(self, message: Dict) -> bool:
        """Check if a message contains tool_result blocks"""
        if message.get("role") != "user":
            return False
        content = message.get("content", [])
        if not isinstance(content, list):
            return False
        return any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    
    def _has_tool_use(self, message: Dict) -> bool:
        """Check if a message contains tool_use blocks"""
        if message.get("role") != "assistant":
            return False
        content = message.get("content", [])
        if not isinstance(content, list):
            return False
        return any(
            isinstance(block, dict) and block.get("type") == "tool_use"
            for block in content
        )
    
    def _trim_conversation_history(self, messages: List[Dict]) -> List[Dict]:
        """
        Keep recent messages while preserving Anthropic tool_use/tool_result pairs.
        IMPROVED Strategy (following Gemini pattern):
        - Always preserve the initial task message at index 0
        - Keep last N complete turns (assistant with tool_use + following user tool_result)
        - Never split a tool_use/tool_result pair
        - Use turn-based retention for better context preservation
        """
        if not messages or len(messages) <= 2:
            return messages
        
        # ✅ CRITICAL FIX: Always preserve the initial task message (like Gemini)
        # The first message is usually the user's task description - never lose it!
        initial_message = messages[0] if messages else None
        
        # Count tool_result messages to determine number of complete turns
        total_turns = sum(1 for msg in messages if self._has_tool_result(msg))
        
        # ✅ INCREASED: Keep more turns for better context (was 3, now 8)
        turns_to_keep = getattr(settings, 'ANTHROPIC_MAX_CONVERSATION_TURNS', 8)
        
        # If we have fewer turns than the limit, no trimming needed
        if total_turns <= turns_to_keep:
            return messages
        
        # ✅ IMPROVED: Identify start index to keep the last N turns
        # Start from index 1 (after initial task message)
        needed = turns_to_keep
        idx = len(messages) - 1
        start_index = 1  # default after initial task (index 0)
        
        while idx >= 1 and needed > 0:
            if self._has_tool_result(messages[idx]):
                # Find the preceding assistant with tool_use (scan backward more thoroughly)
                found = None
                scan = idx - 1
                # ✅ INCREASED: Larger scan window (was 6, now 15) to find tool_use pairs
                min_idx = max(1, idx - 15)  # Start from 1 to preserve initial message
                while scan >= min_idx:
                    if self._has_tool_use(messages[scan]):
                        found = scan
                        break
                    scan -= 1
                
                if found is not None:
                    # Set start_index to earliest such call for this turn
                    start_index = max(1, found)  # Ensure we don't go before index 1
                    needed -= 1
                else:
                    # No matching assistant found - this might be an orphaned tool_result
                    # Skip it and continue
                    pass
            idx -= 1
        
        # ✅ CRITICAL: Ensure we begin at a tool_use if the next is a tool_result
        # This prevents splitting pairs
        if start_index < len(messages) - 1 and self._has_tool_result(messages[start_index]):
            prev_idx = start_index - 1
            if prev_idx >= 1 and self._has_tool_use(messages[prev_idx]):
                if self.logger:
                    self.logger.debug(f"🔒 Adjusted cutoff from {start_index} to {prev_idx} to preserve tool pair")
                start_index = prev_idx
        
        # ✅ CRITICAL: Always preserve initial task message + recent turns
        trimmed = [initial_message] + messages[start_index:] if initial_message else messages[start_index:]
        
        if self.logger:
            self.logger.debug(f"💾 Turn-based trim: Keeping initial task + last {turns_to_keep} turns, messages {start_index}..{len(messages)-1} (total: {len(messages)} → {len(trimmed)})")
        
        return trimmed
    
    def _convert_input_to_anthropic_format(self, input_items: List[Dict]) -> List[Dict]:
        """Convert OpenAI-style input items to Anthropic format"""
        messages = []
        
        for item in input_items:
            if item.get('type') == 'message' and item.get('role') == 'user':
                content = item.get('content', '')
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                else:
                    text_content = str(content)
                
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": text_content}]
                })
        
        return messages

    def _strip_leading_orphaned_tool_results(self, messages: List[Dict]) -> List[Dict]:
        """
        Remove any leading user messages that contain tool_result blocks.
        Anthropic requires a preceding assistant tool_use; at index 0 that is impossible.
        This prevents 400: messages.0.content.0 unexpected tool_use_id in tool_result.
        """
        if not messages:
            return messages
        start = 0
        while start < len(messages) and self._has_tool_result(messages[start]):
            if self.logger:
                self.logger.debug(f"🧹 Stripping leading orphaned tool_result at index {start}")
            start += 1
        return messages[start:]

    def _execute_tool_call(self, tool_call: Dict) -> Dict:
        """Execute a tool call and return the result"""
        tool_name = tool_call.get('name')
        tool_input = tool_call.get('input', {})
        tool_id = tool_call.get('id')
        
        self.logger.info(f"🔧 Executing tool: {tool_name} with input: {tool_input}")
        
        try:
            if tool_name == "bash":
                # Execute bash command
                command = tool_input.get('command', '')
                if command:
                    result_text = f"Executed command: {command}"
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": [{"type": "text", "text": result_text}]
                    }
            
            elif tool_name == "str_replace_editor":
                # Handle text editing
                command = tool_input.get('command', '')
                path = tool_input.get('path', '')
                if command and path:
                    result_text = f"Text editor {command} on {path}"
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": [{"type": "text", "text": result_text}]
                    }
            
            elif tool_name == "computer":
                # Handle computer use actions (screenshots, clicks, etc.)
                return self._execute_computer_action(tool_input, tool_id)
            
            elif tool_name == "memory":
                # ✅ Handle Anthropic's memory tool (memory_20250818)
                # This is Anthropic's built-in persistent memory feature
                # Operations: read, write, delete
                operation = tool_input.get('operation', tool_input.get('command', ''))
                keys = tool_input.get('keys', [])
                data = tool_input.get('data', tool_input.get('file_text', {}))
                
                self.logger.info(f"🧠 Memory operation: {operation}, keys: {keys}")
                
                if operation == 'read':
                    # Return empty memory on first read (Anthropic expects this)
                    result_text = "{}" if not keys else f"Memory read for keys: {', '.join(keys)}"
                elif operation == 'write':
                    # Acknowledge write
                    result_text = f"Memory updated successfully"
                elif operation == 'delete':
                    # Acknowledge delete
                    result_text = f"Memory deleted successfully"
                else:
                    # Handle legacy format
                    result_text = f"Memory operation '{operation}' completed"
                
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": [{"type": "text", "text": result_text}]
                }
            
            # Generic handler for unknown tools
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": [{"type": "text", "text": f"Tool {tool_name} executed successfully"}]
            }
            
        except Exception as e:
            # Don't catch CriticalTimeoutError - let it propagate to crash the task
            if isinstance(e, CriticalTimeoutError):
                self.logger.error(f"🚨 CRITICAL TIMEOUT in tool execution: {e}")
                raise  # This will crash the entire task
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": [{"type": "text", "text": f"Error executing tool: {str(e)}"}],
                "is_error": True
            }

    def _handle_key_press(self, text: str) -> str:
        """Handle key press with proper formatting and fallbacks"""
        try:
            # Map "Return" to "Enter" for cross-platform compatibility
            if text == "Return":
                text = "Enter"
            
            # Normalize Page_Down/Page Down variants to standard format
            if text in ("Page_Down", "Page Down"):
                text = "pagedown"
            elif text in ("Page_Up", "Page Up"):
                text = "pageup"
            
            # ✅ FIX: Handle key combinations BEFORE trying single keypress
            # Common key combinations sent by Anthropic (e.g. "ctrl+a", "shift+tab")
            if "+" in text:
                # Split combination into individual keys
                keys = text.split("+")
                # Normalize key names (ctrl -> Control, shift -> Shift, alt -> Alt, etc.)
                normalized_keys = []
                for key in keys:
                    key_lower = key.lower().strip()
                    if key_lower in ["ctrl", "control"]:
                        normalized_keys.append("Control")
                    elif key_lower == "shift":
                        normalized_keys.append("Shift")
                    elif key_lower == "alt":
                        normalized_keys.append("Alt")
                    elif key_lower in ["cmd", "meta", "command"]:
                        normalized_keys.append("Meta")
                    elif key_lower in ["left", "arrowleft"]:
                        normalized_keys.append("ArrowLeft")
                    elif key_lower in ["right", "arrowright"]:
                        normalized_keys.append("ArrowRight")
                    elif key_lower in ["up", "arrowup"]:
                        normalized_keys.append("ArrowUp")
                    elif key_lower in ["down", "arrowdown"]:
                        normalized_keys.append("ArrowDown")
                    else:
                        # Keep other keys as-is (e.g. "a", "Tab", "Enter")
                        normalized_keys.append(key.strip())
                
                self.logger.info(f"⌨️ Key combination detected: {text} → {normalized_keys}")
                
                # Call keypress method directly to preserve decorators
                try:
                    self.computer.keypress(normalized_keys)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL KEYPRESS FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed keys: {'+'.join(normalized_keys)}"
            
            # General handler for ANY repeated key sequence (e.g., "Tab Tab Tab", "Down Down Down", "Enter Enter", etc.)
            # Check if text contains the same word repeated multiple times (space-separated)
            words = text.split()
            if len(words) > 1 and len(set(words)) == 1:
                # All words are the same - it's a repeated sequence
                try:
                    self.computer.keypress(words)
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL KEYPRESS FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed key: {text}"
            
            # Handle special key combinations
            if text in ['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Up', 'Down', 'Left', 'Right']:
                # Normalize arrow keys to Playwright format
                normalized_key = text
                if text == 'Down':
                    normalized_key = 'ArrowDown'
                elif text == 'Up':
                    normalized_key = 'ArrowUp'
                elif text == 'Left':
                    normalized_key = 'ArrowLeft'
                elif text == 'Right':
                    normalized_key = 'ArrowRight'
                
                # Call keypress method directly to preserve decorators
                try:
                    self.computer.keypress([normalized_key])
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL KEYPRESS FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed key: {text}"
            else:
                # Call keypress method directly to preserve decorators
                try:
                    self.computer.keypress([text])
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "keypress failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL KEYPRESS FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL KEYPRESS FAILURE: {error}") from error
                return f"Pressed key: {text}"
        except CriticalTimeoutError as timeout_error:
            # Re-raise CriticalTimeoutError to crash the task immediately
            self.logger.error(f"🚨 CRITICAL TIMEOUT in keypress: {timeout_error}")
            raise
        except Exception as key_error:
            self.logger.warning(f"⚠️ Key press failed for '{text}': {key_error}")
            
            # Try alternative key formats
            try:
                # Common key combinations
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
                    "ctrl+return": ["ctrl", "enter"],  # Map Return to Enter
                    "ctrl+end": ["ctrl", "end"],
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
                    # Add single arrow key mappings (Down, Up, Left, Right -> ArrowDown, etc.)
                    "down": ["arrowdown"],
                    "up": ["arrowup"],
                    "left": ["arrowleft"],
                    "right": ["arrowright"],
                }
                
                text_lower = text.lower()
                if text_lower in key_mappings:
                    # Call keypress method directly to preserve decorators
                    try:
                        self.computer.keypress(key_mappings[text_lower])
                    except Exception as error:
                        # Don't catch CriticalTimeoutError - let it propagate for retry handling
                        if isinstance(error, CriticalTimeoutError):
                            raise
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
                    # Try single key - Call keypress method directly to preserve decorators
                    try:
                        self.computer.keypress([text])
                    except Exception as error:
                        # Don't catch CriticalTimeoutError - let it propagate for retry handling
                        if isinstance(error, CriticalTimeoutError):
                            raise
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
                    
            except CriticalTimeoutError as timeout_error:
                # Re-raise CriticalTimeoutError to crash the task immediately
                self.logger.error(f"🚨 CRITICAL TIMEOUT in alternative keypress: {timeout_error}")
                raise
            except Exception as alt_error:
                self.logger.error(f"❌ Alternative key press also failed for '{text}': {alt_error}")
                return f"Key press failed: {text} - {str(key_error)}"

    def _execute_computer_action(self, tool_input: Dict, tool_id: str) -> Dict:
        """Execute computer actions using the computer instance"""
        action = tool_input.get('action', '')
        coordinate = tool_input.get('coordinate')
        text = tool_input.get('text', '')
        key = tool_input.get('key', '')
        scroll_direction = tool_input.get('scroll_direction', 'down')
        scroll_amount = tool_input.get('scroll_amount', 1)
        duration = tool_input.get('duration', 1.0)
        
        self.logger.info(f"🖥️ Computer tool called with action: {action}, coordinate: {coordinate}, text: {text}, key: {key}")
        
        # ✅ BEFORE = previous action's AFTER screenshot (what the model actually saw)
        screenshot_path_before = None
        # Actions we explicitly visualize with before/after in the timeline
        visible_effect_actions = [
            "left_click",
            "right_click",
            "double_click",
            "triple_click",
            "type",
            "key",
            "scroll",
            "mouse_move",
            "move",
            # Drag-style actions
            "left_click_drag",
            "drag",
            "drag_and_drop",
            "click_and_drag",
            # Tab management actions
            "switch_tab",
            "close_tab",
            "new_tab",
            "list_tabs",
        ]
        # ✅ ALWAYS capture what the model saw (previous action's AFTER)
        # This is needed for all actions, not just visible ones
        if hasattr(self, "_last_after_screenshot") and self._last_after_screenshot:
            screenshot_path_before = self._last_after_screenshot
            self._last_screenshot_before = screenshot_path_before
            self.logger.info(f"📸 BEFORE = previous action's AFTER: {screenshot_path_before}")
        else:
            self._last_screenshot_before = None
            self.logger.info(f"📸 BEFORE = None (first action or no previous screenshot)")
        
        try:
            result_text = ""
            
            # Handle different computer actions
            if action == "screenshot":
                # Take a screenshot using our computer instance with critical tracking
                # Call screenshot method directly to preserve decorators
                try:
                    screenshot_data = self.computer.screenshot()
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in screenshot: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "screenshot failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in screenshot: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL SCREENSHOT FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL SCREENSHOT FAILURE: {error}") from error
                if screenshot_data:
                    # Convert to base64 if needed
                    if isinstance(screenshot_data, bytes):
                        import base64
                        base64_data = base64.b64encode(screenshot_data).decode('utf-8')
                    elif isinstance(screenshot_data, str) and screenshot_data.startswith('data:image/'):
                        base64_data = screenshot_data.split(',')[1]
                    else:
                        base64_data = screenshot_data
                    
                    # Save screenshot to task directory
                    self._take_screenshot("screenshot_action")
                    
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": [
                            {"type": "text", "text": "Screenshot captured"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_data
                                }
                            }
                        ]
                    }
            
            elif action == "left_click" and coordinate:
                x, y = coordinate
                self.logger.info(f"🖱️ Left clicking at coordinates ({x}, {y})")
                # Call click method directly to preserve decorators
                try:
                    self.computer.click(x, y, button="left")
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in left_click: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "left_click failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in left_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL LEFT_CLICK FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL LEFT_CLICK FAILURE: {error}") from error
                result_text = f"Left clicked at coordinates ({x}, {y})"
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)
            
            elif action == "right_click" and coordinate:
                x, y = coordinate
                self.logger.info(f"🖱️ Right clicking at coordinates ({x}, {y})")
                # Call click method directly to preserve decorators
                try:
                    self.computer.click(x, y, button="right")
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in right_click: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "right_click failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in right_click: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL RIGHT_CLICK FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL RIGHT_CLICK FAILURE: {error}") from error
                result_text = f"Right clicked at coordinates ({x}, {y})"
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)
            
            elif action == "double_click" and coordinate:
                x, y = coordinate
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
            
            elif action == "triple_click" and coordinate:
                x, y = coordinate
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
            
            elif action == "type" and text:
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
            
            elif action == "key" and text:
                self.logger.info(f"⌨️ Pressing key: {text}")
                result_text = self._handle_key_press(text)
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)
            
            elif action in ("mouse_move", "move") and coordinate:
                x, y = coordinate
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
            
            elif action in ("left_click_drag", "drag", "drag_and_drop", "click_and_drag") and coordinate:
                start_coordinate = (
                    tool_input.get("start_coordinate")
                    or tool_input.get("start_coordinates")
                    or tool_input.get("start")
                )
                if not start_coordinate:
                    start_x = tool_input.get("start_x")
                    start_y = tool_input.get("start_y")
                    if start_x is not None and start_y is not None:
                        start_coordinate = [start_x, start_y]
                
                if not start_coordinate:
                    self.logger.warning("⚠️ Drag action missing start_coordinate")
                    result_text = "Drag action missing start coordinate"
                else:
                    sx, sy = start_coordinate
                    dx, dy = coordinate
                    self.logger.info(f"🖱️ Dragging from ({sx}, {sy}) to ({dx}, {dy})")
                    # Use raw pixel coordinates with the shared drag(path) helper so
                    # Playwright behavior matches exactly what we record in the timeline.
                    drag_path = [
                        {"x": sx, "y": sy},
                        {"x": dx, "y": dy},
                    ]
                    try:
                        self.computer.drag(drag_path)
                    except Exception as error:
                        if isinstance(error, CriticalTimeoutError):
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in drag: {error}")
                            raise
                        if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                            try:
                                self.critical_error_tracker.record_critical_error(error, "drag failure")
                            except CriticalTimeoutError as critical_error:
                                self.logger.error(f"🚨 CRITICAL TIMEOUT in drag: {critical_error}")
                                raise
                        else:
                            self.logger.error(f"🚨 CRITICAL DRAG FAILURE: {error}")
                            raise RuntimeError(f"CRITICAL DRAG FAILURE: {error}") from error
                    result_text = f"Dragged from ({sx}, {sy}) to ({dx}, {dy})"
            
            elif action == "scroll" and coordinate:
                x, y = coordinate
                scroll_x, scroll_y = 0, 0
                if scroll_direction == "up":
                    scroll_y = -scroll_amount * 100
                elif scroll_direction == "down":
                    scroll_y = scroll_amount * 100
                elif scroll_direction == "left":
                    scroll_x = -scroll_amount * 100
                elif scroll_direction == "right":
                    scroll_x = scroll_amount * 100
                
                self.logger.info(f"🖱️ Scrolling {scroll_direction} by {scroll_amount} at ({x}, {y})")
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
                result_text = f"Scrolled {scroll_direction} by {scroll_amount} at ({x}, {y})"
            
            elif action == "wait":
                wait_ms = int(duration * 1000) if duration else 1000
                self.logger.info(f"⏱️ Waiting for {wait_ms}ms")
                self.computer.wait(wait_ms)
                result_text = f"Waited for {wait_ms}ms"
            
            elif action == "left_mouse_down":
                # Extract coordinates if provided, otherwise pass None
                x, y = coordinate if coordinate else (None, None)
                if coordinate:
                    self.logger.info(f"🖱️ Mouse down at coordinates ({x}, {y})")
                    result_text = f"Mouse down at coordinates ({x}, {y})"
                else:
                    self.logger.info(f"🖱️ Mouse down at current position (no coordinate provided)")
                    result_text = "Mouse down at current position"
                
                # Call mouse_down method directly to preserve decorators
                # mouse_down now handles None coordinates internally
                try:
                    self.computer.mouse_down(x, y, button="left")
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in left_mouse_down: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "left_mouse_down failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in left_mouse_down: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL LEFT_MOUSE_DOWN FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL LEFT_MOUSE_DOWN FAILURE: {error}") from error
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)
            
            elif action == "left_mouse_up":
                # Extract coordinates if provided, otherwise pass None
                x, y = coordinate if coordinate else (None, None)
                if coordinate:
                    self.logger.info(f"🖱️ Mouse up at coordinates ({x}, {y})")
                    result_text = f"Mouse up at coordinates ({x}, {y})"
                else:
                    self.logger.info(f"🖱️ Mouse up at current position (no coordinate provided)")
                    result_text = "Mouse up at current position"
                
                # Call mouse_up method directly to preserve decorators
                # mouse_up now handles None coordinates internally
                try:
                    self.computer.mouse_up(x, y, button="left")
                except Exception as error:
                    # Don't catch CriticalTimeoutError - let it propagate to crash the task
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in left_mouse_up: {error}")
                        raise  # This will crash the entire task
                    if hasattr(self, 'critical_error_tracker') and self.critical_error_tracker:
                        try:
                            self.critical_error_tracker.record_critical_error(error, "left_mouse_up failure")
                        except CriticalTimeoutError as critical_error:
                            # Re-raise critical timeout errors to crash the task
                            self.logger.error(f"🚨 CRITICAL TIMEOUT in left_mouse_up: {critical_error}")
                            raise  # This will crash the entire task
                    else:
                        # If no critical error tracker, treat as critical and crash
                        self.logger.error(f"🚨 CRITICAL LEFT_MOUSE_UP FAILURE: {error}")
                        raise RuntimeError(f"CRITICAL LEFT_MOUSE_UP FAILURE: {error}") from error
                # Wait briefly to let DOM settle (like agent.py)
                time.sleep(0.9)
            
            elif action == "new_tab":
                # Open a new tab using Playwright API (not keyboard shortcut)
                url = tool_input.get('url', '')
                self.logger.info(f"➕ Opening new tab{f' with URL: {url}' if url else ''}")
                try:
                    if hasattr(self.computer, 'new_tab'):
                        self.computer.new_tab(url=url)
                        result_text = f"Opened new tab{f' with URL: {url}' if url else ''}"
                    else:
                        result_text = "Tab operations not supported on this computer"
                        self.logger.warning("⚠️ Computer does not support new tab")
                except Exception as error:
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in new_tab: {error}")
                        raise
                    self.logger.error(f"❌ Failed to open new tab: {error}")
                    result_text = f"Failed to open new tab: {str(error)}"
                time.sleep(0.5)
            
            elif action == "switch_tab":
                # Switch to a specific tab by index using Playwright API (not keyboard shortcut)
                tab_index = tool_input.get('tab_index', 0)
                self.logger.info(f"🔄 Switching to tab {tab_index}")
                try:
                    if hasattr(self.computer, 'switch_tab'):
                        self.computer.switch_tab(tab_index=tab_index)
                        result_text = f"Switched to tab {tab_index}"
                    else:
                        result_text = "Tab switching not supported on this computer"
                        self.logger.warning("⚠️ Computer does not support tab switching")
                except Exception as error:
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in switch_tab: {error}")
                        raise
                    self.logger.error(f"❌ Failed to switch tab: {error}")
                    result_text = f"Failed to switch tab: {str(error)}"
                time.sleep(0.5)
            
            elif action == "close_tab":
                # Close the current tab using Playwright API (not keyboard shortcut)
                self.logger.info(f"❌ Closing current tab")
                try:
                    if hasattr(self.computer, 'close_tab'):
                        self.computer.close_tab()
                        result_text = "Closed current tab"
                    else:
                        result_text = "Tab operations not supported on this computer"
                        self.logger.warning("⚠️ Computer does not support close tab")
                except Exception as error:
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in close_tab: {error}")
                        raise
                    self.logger.error(f"❌ Failed to close tab: {error}")
                    result_text = f"Failed to close tab: {str(error)}"
                time.sleep(0.5)
            
            elif action == "list_tabs":
                # Get information about all open tabs using Playwright API
                self.logger.info(f"📑 Listing all tabs")
                tab_info = None
                try:
                    if hasattr(self.computer, 'list_tabs'):
                        tab_info = self.computer.list_tabs()
                        self.logger.info(f"📑 Raw tab_info returned: {tab_info}")
                        tab_count = tab_info.get('tab_count', 0)
                        current_idx = tab_info.get('current_tab_index', -1)
                        tabs = tab_info.get('tabs', [])
                        self.logger.info(f"📑 Parsed: tab_count={tab_count}, current_idx={current_idx}, tabs_len={len(tabs)}")
                        
                        # Generate visual screenshot of tabs
                        try:
                            from app.services.computers.shared.tab_visualizer import TabVisualizer
                            visualizer = TabVisualizer()
                            self.logger.info(f"📸 About to generate tab visualization with tab_info: {tab_info}")
                            tab_screenshot_bytes = visualizer.generate_tab_screenshot(tab_info)
                            self.logger.info(f"📸 Tab visualization generated: {len(tab_screenshot_bytes) if tab_screenshot_bytes else 0} bytes")
                            
                            # Save the tab screenshot
                            if self.screenshot_helper and tab_screenshot_bytes:
                                screenshot_path = self.screenshot_helper.save_screenshot(
                                    tab_screenshot_bytes,
                                    "list_tabs_view"
                                )
                                if screenshot_path:
                                    self.logger.info(f"📸 Saved tab visualization screenshot: {screenshot_path}")
                                    # Store it so it gets used as AFTER screenshot
                                    self._last_after_screenshot = screenshot_path
                                    self._last_screenshot_after = screenshot_path
                                else:
                                    self.logger.error(f"❌ Failed to save tab visualization screenshot")
                            else:
                                if not self.screenshot_helper:
                                    self.logger.error(f"❌ No screenshot_helper available")
                                if not tab_screenshot_bytes:
                                    self.logger.error(f"❌ No tab_screenshot_bytes generated")
                        except Exception as viz_error:
                            self.logger.error(f"❌ Failed to generate tab visualization: {viz_error}", exc_info=True)
                        
                        # Format tab info for display
                        tab_list = []
                        for tab in tabs:
                            idx = tab.get('index', -1)
                            url = tab.get('url', 'unknown')
                            is_current = tab.get('is_current', False)
                            marker = "→ " if is_current else "  "
                            tab_list.append(f"{marker}Tab {idx}: {url}")
                        
                        result_text = f"Open tabs ({tab_count} total, current: {current_idx}):\n" + "\n".join(tab_list)
                        self.logger.info(result_text)
                        
                        # ✅ Store tab_info for timeline (like OpenAI agent does)
                        # This will be used by unified_task_runner to add to metadata
                        if not hasattr(self, '_last_action_metadata'):
                            self._last_action_metadata = {}
                        self._last_action_metadata['tab_info'] = tab_info
                    else:
                        result_text = "Tab operations not supported on this computer"
                        self.logger.warning("⚠️ Computer does not support list tabs")
                except Exception as error:
                    if isinstance(error, CriticalTimeoutError):
                        self.logger.error(f"🚨 CRITICAL TIMEOUT in list_tabs: {error}")
                        raise
                    self.logger.error(f"❌ Failed to list tabs: {error}")
                    result_text = f"Failed to list tabs: {str(error)}"
            
            else:
                result_text = f"Computer action '{action}' not implemented or missing parameters"
                self.logger.warning(f"⚠️ Unhandled computer action: {action} with input: {tool_input}")
            
            # Generate insights for this action
            self.logger.debug(f"🔍 Checking insighter: {self.insighter is not None}")
            if self.insighter:
                try:
                    # Get current screenshot for insight analysis
                    current_screenshot = None
                    if self.computer:
                        current_screenshot = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                    
                    action_data = {
                        'type': action,
                        'action': tool_input,
                        'timestamp': time.time()
                    }
                    self.insighter.analyze_action(action_data, current_screenshot)
                except Exception as insight_error:
                    # Don't let insight generation failures crash the task
                    self.logger.warning(f"⚠️ Insight generation failed for {action}: {insight_error}")
            
            # ✅ Capture AFTER screenshot to keep track of the latest page state.
            # We want this even for "wait" so that a click after a wait uses the
            # wait's screenshot as its BEFORE.
            # For list_tabs, we skip taking a new browser screenshot since the tab visualization is already the AFTER screenshot
            screenshot_path_after = None
            if action == "list_tabs":
                # We already generated the tab visualization as the AFTER screenshot
                # Use it and update _last_after_screenshot for the next action
                if hasattr(self, '_last_screenshot_after') and self._last_screenshot_after:
                    screenshot_path_after = self._last_screenshot_after
                    # CRITICAL: Update _last_after_screenshot so next action has correct BEFORE
                    self._last_after_screenshot = screenshot_path_after
                    self.logger.info(f"📸 Using tab visualization as AFTER screenshot for list_tabs: {screenshot_path_after}")
                else:
                    self.logger.warning(f"📸 No tab visualization available for list_tabs AFTER")
            else:
                try:
                    # ✅ wait_for_settle=False because action handlers already include any needed sleep
                    screenshot_path_after = self._take_screenshot(f"after_{action}", wait_for_settle=False)
                    if screenshot_path_after:
                        self.logger.info(f"📸 Saved AFTER screenshot: {screenshot_path_after}")
                        # Always track the latest page state for subsequent BEFORE shots
                        self._last_after_screenshot = screenshot_path_after
                        # Only expose explicit "after" to the timeline for visible-effect actions
                        if action in visible_effect_actions:
                            self._last_screenshot_after = screenshot_path_after
                            self.logger.info(f"📸 ✅ Action '{action}' is in visible_effect_actions - Stored AFTER for timeline: {screenshot_path_after}")
                        else:
                            self._last_screenshot_after = None
                            self.logger.warning(f"📸 ❌ Action '{action}' NOT in visible_effect_actions - No AFTER for timeline")
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to capture after screenshot: {e}")
                    self._last_screenshot_after = None

            # ✅ Return CLEAN tool_result (API format only)
            # Anthropic API strictly requires ONLY: type, tool_use_id, content
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": [{"type": "text", "text": result_text}]
            }
                
        except CriticalTimeoutError as timeout_error:
            # Re-raise CriticalTimeoutError to crash the task immediately
            self.logger.error(f"🚨 CRITICAL TIMEOUT in computer action {action}: {timeout_error}")
            raise
        except Exception as e:
            result_text = f"Computer action {action} failed: {str(e)}"
            self.logger.error(f"❌ Computer action failed: {result_text}")
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": [{"type": "text", "text": result_text}]
            }

    def run_full_turn(self, input_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run a full task until the assistant produces a final message.
        Uses the exact pattern from Anthropic documentation to avoid tool_use/tool_result mismatches.
        Complete independent implementation extracted from V1.
        """
        try:
            self.logger.info("🤖 Starting Anthropic agent execution (complete independent implementation)")
            
            self.print_steps = True
            self.debug = False
            self.show_images = False
            
            # Convert input items to Anthropic format
            messages = self._convert_input_to_anthropic_format(input_items)
            
            # Create system prompt for computer use
            system_prompt = self._create_system_prompt()
            
            # Run the conversation loop following exact Anthropic pattern
            all_items = []
            iteration = 0
            
            while iteration < settings.MAX_STEPS_LIMIT:
                iteration += 1
                self.logger.info(f"🔄 Anthropic iteration {iteration}/{settings.MAX_STEPS_LIMIT}")
                
                try:
                    # Trim conversation history to reduce tokens (pair-preserving)
                    trimmed_messages = self._trim_conversation_history(messages)
                    # Ensure we never start with a tool_result (invalid per Anthropic)
                    trimmed_messages = self._strip_leading_orphaned_tool_results(trimmed_messages)
                    
                    # Prepare API call parameters
                    api_params = {
                        "model": self.model,
                        "max_tokens": self.max_tokens,
                        "system": system_prompt,
                        "tools": [
                            {"type": "bash_20250124", "name": "bash"},
                            {"type": "text_editor_20250124", "name": "str_replace_editor"},
                            {
                                "type": "computer_20250124", 
                                "name": "computer",
                                "display_width_px": self.computer.get_dimensions()[0],
                                "display_height_px": self.computer.get_dimensions()[1],
                                "display_number": 1
                            },
                            {"type": "memory_20250818", "name": "memory"}
                        ],
                        "betas": [
                            "computer-use-2025-01-24", 
                            "context-management-2025-06-27",  # Automatic context editing
                            "token-efficient-tools-2025-02-19"  # Token-efficient tool use (saves 14-70% output tokens)
                        ],
                        "messages": trimmed_messages
                    }
                    
                    # Call Anthropic API with retry logic - all errors retry 3 times, then crash
                    response = None
                    max_api_retries = 3
                    for api_attempt in range(max_api_retries):
                        try:
                            response = self.anthropic_client.beta.messages.create(**api_params)
                            break  # Success, exit retry loop
                        except Exception as api_error:
                            error_str = str(api_error)
                            
                            # Check for 400 errors (client errors) - these should crash immediately (no retries)
                            if "400" in error_str or "invalid_request_error" in error_str:
                                self.logger.error(f"🚨 CRITICAL API ERROR (400): {api_error}")
                                raise CriticalAPIError(f"Anthropic API 400 error - invalid request: {api_error}") from api_error
                            
                            # Check for other critical errors (401, 403, 429, etc.) - these should crash immediately (no retries)
                            elif any(code in error_str for code in ["401", "403", "429", "quota", "rate limit", "unauthorized", "forbidden"]):
                                self.logger.error(f"🚨 CRITICAL API ERROR: {api_error}")
                                raise CriticalAPIError(f"Anthropic API critical error: {api_error}") from api_error
                            
                            # Check for 529 overloaded errors - retry up to 3 times
                            elif "529" in error_str or "overloaded_error" in error_str.lower():
                                if api_attempt < max_api_retries - 1:
                                    # Exponential backoff with jitter: 2, 4, 8 seconds
                                    base_wait = 2 ** (api_attempt + 1)
                                    jitter = random.uniform(0, 1)  # Add random jitter to prevent thundering herd
                                    wait_time = base_wait + jitter
                                    self.logger.warning(f"⚠️ Anthropic API overloaded (529), retrying in {wait_time:.2f}s (attempt {api_attempt + 1}/{max_api_retries})")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    self.logger.error(f"❌ Anthropic API overloaded after {max_api_retries} attempts: {api_error}")
                                    raise CriticalAPIError(f"Anthropic API overloaded after {max_api_retries} attempts: {api_error}") from api_error
                            
                            # Check for 499 errors (client closed request) - transient network issues, retry up to 3 times
                            elif "499" in error_str or "client closed request" in error_str.lower():
                                if api_attempt < max_api_retries - 1:
                                    wait_time = (api_attempt + 1) * 2  # 2, 4, 6 seconds
                                    self.logger.warning(f"⚠️ Anthropic API 499 error (client closed request), retrying in {wait_time}s (attempt {api_attempt + 1}/{max_api_retries})")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    self.logger.error(f"❌ Anthropic API 499 error after {max_api_retries} attempts: {api_error}")
                                    raise CriticalAPIError(f"Anthropic API 499 error after {max_api_retries} attempts: {api_error}") from api_error
                            
                            # Check for 500 errors (server errors) - retry up to 3 times
                            elif "500" in error_str and "Internal server error" in error_str:
                                if api_attempt < max_api_retries - 1:
                                    wait_time = (api_attempt + 1) * 2  # 2, 4, 6 seconds
                                    self.logger.warning(f"⚠️ Anthropic API 500 error, retrying in {wait_time}s (attempt {api_attempt + 1}/{max_api_retries})")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    self.logger.error(f"❌ Anthropic API failed after {max_api_retries} attempts: {api_error}")
                                    raise CriticalAPIError(f"Anthropic API failed after {max_api_retries} attempts: {api_error}") from api_error
                            
                            # All other errors - retry up to 3 times, then crash
                            else:
                                if api_attempt < max_api_retries - 1:
                                    wait_time = (api_attempt + 1) * 2  # 2, 4, 6 seconds
                                    self.logger.warning(f"⚠️ Anthropic API error, retrying in {wait_time}s (attempt {api_attempt + 1}/{max_api_retries}): {api_error}")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    self.logger.error(f"❌ Anthropic API failed after {max_api_retries} attempts: {api_error}")
                                    raise CriticalAPIError(f"Anthropic API failed after {max_api_retries} attempts: {api_error}") from api_error
                    
                    if response is None:
                        raise CriticalAPIError("Failed to get response from Anthropic API after retries")
                    
                    # Log API response for debugging
                    self.logger.info(f"🔍 API Response Debug - Iteration {iteration}:")
                    self.logger.info(f"📋 Response ID: {response.id}")
                    self.logger.info(f"📊 Response Type: {response.type}")
                    self.logger.info(f"👤 Response Role: {response.role}")
                    self.logger.info(f"📝 Content Blocks Count: {len(response.content) if response.content else 0}")
                    
                    # Log each content block and generate insights for text content
                    for i, block in enumerate(response.content):
                        self.logger.info(f"📦 Content Block {i}: {block.type if hasattr(block, 'type') else 'unknown'}")
                        if hasattr(block, 'text') and block.text:
                            self.logger.info(f"📄 Text Content: {block.text[:200]}{'...' if len(block.text) > 200 else ''}")
                            
                            # Generate insights for text content (reasoning/summary)
                            self.logger.debug(f"🔍 Checking insighter for text content: {self.insighter is not None}")
                            if self.insighter:
                                try:
                                    # Get current screenshot for summary analysis
                                    current_screenshot = None
                                    if self.computer:
                                        current_screenshot = self._execute_with_critical_tracking("screenshot", self.computer.screenshot)
                                    
                                    self.insighter.analyze_summary(block.text, current_screenshot)
                                except Exception as insight_error:
                                    # Don't let insight generation failures crash the task
                                    self.logger.warning(f"⚠️ Text content insight generation failed: {insight_error}")
                        elif hasattr(block, 'name') and hasattr(block, 'input'):
                            self.logger.info(f"🔧 Tool Use: {block.name} with input: {block.input}")
                    
                    # Log usage information if available
                    if hasattr(response, 'usage') and response.usage:
                        self.logger.info(f"📈 Token Usage: {response.usage}")
                        self.logger.info(f"🔍 Checking token tracking: iteration_id={self.iteration_id}, execution_id={self.execution_id}")
                        
                        # Track token usage if IDs are available  
                        if self.iteration_id and self.execution_id:
                            try:
                                from app.services.crud.token_usage import TokenUsageCRUD
                                from app.schemas.token_usage import TokenUsageCreate
                                from app.core.database_utils import get_db_session
                                
                                # Extract token counts
                                usage = response.usage
                                input_tokens = getattr(usage, 'input_tokens', 0) or 0
                                output_tokens = getattr(usage, 'output_tokens', 0) or 0
                                cache_read = getattr(usage, 'cache_read_input_tokens', 0) or 0
                                cache_creation = getattr(usage, 'cache_creation_input_tokens', 0) or 0
                                cached_tokens = cache_read + cache_creation
                                total_tokens = input_tokens + output_tokens
                                
                                # Track synchronously with retry logic for connection timeouts
                                max_retries = 3
                                retry_delay = 1
                                db_succeeded = False
                                last_error = None
                                
                                for attempt in range(max_retries):
                                    try:
                                        with get_db_session() as db:
                                            # Insert directly using SQL
                                            from sqlalchemy import text
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
                                                'model_name': 'anthropic',
                                                'model_version': self.model,
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
                        else:
                            self.logger.warning(f"⚠️ Cannot track tokens: iteration_id={self.iteration_id}, execution_id={self.execution_id}")
                    
                    # Convert to our format for processing
                    response_items = self._process_anthropic_response(response)
                    all_items.extend(response_items)
                    
                    # ✅ Report response items in real-time for live timeline
                    for item in response_items:
                        self._report_action(item)
                    
                    # Add assistant's response to messages (contains tool_use blocks)
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    
                    # Check if we have tool use calls to execute
                    tool_result_content = []
                    tool_metadata = []  # Track metadata for enrichment
                    tool_use_count = 0
                    
                    for content_block in response.content:
                        if hasattr(content_block, 'type') and content_block.type == "tool_use":
                            tool_use_count += 1
                            tool_id = content_block.id
                            tool_name = content_block.name
                            tool_input = content_block.input
                            
                            self.logger.info(f"🔧 Executing Tool {tool_use_count}: {tool_name} with ID: {tool_id}")
                            self.logger.info(f"📥 Tool Input: {tool_input}")
                            
                            # ✅ Capture metadata BEFORE execution for enrichment
                            coordinate = (
                                tool_input.get("coordinate")
                                or tool_input.get("coordinates")
                                or (
                                    [tool_input.get("x"), tool_input.get("y")]
                                    if tool_input.get("x") is not None and tool_input.get("y") is not None
                                    else None
                                )
                            )
                            target_coordinate = (
                                tool_input.get("target_coordinate")
                                or tool_input.get("destination_coordinate")
                                or tool_input.get("end_coordinate")
                            )
                            if not target_coordinate:
                                dest_x = tool_input.get("destination_x")
                                dest_y = tool_input.get("destination_y")
                                if dest_x is not None and dest_y is not None:
                                    target_coordinate = [dest_x, dest_y]

                            start_coordinate = (
                                tool_input.get("start_coordinate")
                                or tool_input.get("start_coordinates")
                                or tool_input.get("start")
                            )
                            if not start_coordinate:
                                start_x = tool_input.get("start_x")
                                start_y = tool_input.get("start_y")
                                if start_x is not None and start_y is not None:
                                    start_coordinate = [start_x, start_y]

                            metadata = {
                                "tool_name": tool_name,
                                "tool_input": tool_input,
                                "action": tool_input.get("action") if tool_name == "computer" else tool_name,
                                "url": None,  # Will be set after execution
                                # ✅ Extract detailed action fields for timeline
                                "coordinates": coordinate,
                                "start_coordinates": start_coordinate,
                                "target_coordinates": target_coordinate,
                                "coordinates_normalized": tool_input.get("coordinates_normalized"),
                                "text": tool_input.get("text"),
                                # ✅ For Anthropic, key value is passed in 'text' parameter for action='key'
                                # Extract key: use 'key' field if present, otherwise use 'text' if action is 'key'
                                "key": tool_input.get("key") if tool_input.get("key") else (tool_input.get("text") if tool_input.get("action") == "key" else ""),
                                "direction": tool_input.get("scroll_direction"),
                                "amount": tool_input.get("scroll_amount"),
                                "magnitude": tool_input.get("magnitude"),
                                "screenshot_before": None,  # Will be set by tool execution
                                "screenshot_after": None   # Will be set after execution
                            }
                            
                            # ✅ FIX: Debug log using 'metadata' dict directly (not tool_metadata[-1] which doesn't exist yet)
                            if tool_input.get("action") == "key":
                                self.logger.debug(
                                    f"⌨️ Anthropic keypress: action={tool_input.get('action')}, "
                                    f"text={tool_input.get('text')}, key_field={tool_input.get('key')}, "
                                    f"extracted_key={metadata['key']}"
                                )
                            
                            # Execute the tool call
                            tool_result = self._execute_tool_call({
                                "name": tool_name,
                                "input": tool_input,
                                "id": tool_id
                            })
                            
                            # ✅ Capture URL and before/after screenshots after execution
                            if tool_name == "computer" and self.computer.get_environment() == "browser":
                                try:
                                    metadata["url"] = self.computer.get_current_url()
                                except Exception:
                                    pass
                                
                                # ✅ Add tab_info for list_tabs actions
                                action_name = tool_input.get("action")
                                if action_name == "list_tabs" and hasattr(self, '_last_action_metadata'):
                                    if 'tab_info' in self._last_action_metadata:
                                        metadata["tab_info"] = self._last_action_metadata['tab_info']
                                        self.logger.info(f"📑 Added tab_info to metadata: {metadata['tab_info']}")
                                        # Clear it after using
                                        self._last_action_metadata = {}
                                
                                # ✅ For timeline: only attach explicit BEFORE/AFTER to
                                # actions that we actually visualize as before/after.
                                visible_effect_actions = {
                                    "left_click",
                                    "right_click",
                                    "double_click",
                                    "triple_click",
                                    "type",
                                    "key",
                                    "scroll",
                                    "mouse_move",
                                    "move",
                                    "left_click_drag",
                                    "drag",
                                    "drag_and_drop",
                                    "click_and_drag",
                                    # Tab management actions
                                    "switch_tab",
                                    "close_tab",
                                    "new_tab",
                                    "list_tabs",
                                }
                                if action_name in visible_effect_actions:
                                    if hasattr(self, "_last_screenshot_before") and self._last_screenshot_before:
                                        metadata["screenshot_before"] = self._last_screenshot_before
                                        self.logger.debug(f"📸 Attached BEFORE screenshot for {action_name}: {self._last_screenshot_before}")
                                    else:
                                        self.logger.debug(f"📸 No BEFORE screenshot available for {action_name}")
                                    if hasattr(self, "_last_screenshot_after") and self._last_screenshot_after:
                                        metadata["screenshot_after"] = self._last_screenshot_after
                                        self.logger.debug(f"📸 Attached AFTER screenshot for {action_name}: {self._last_screenshot_after}")
                                    else:
                                        self.logger.debug(f"📸 No AFTER screenshot available for {action_name}")
                            
                            if tool_result:
                                tool_result_content.append(tool_result)
                                tool_metadata.append(metadata)
                                self.logger.info(f"✅ Tool {tool_use_count} executed successfully")
                            else:
                                self.logger.warning(f"⚠️ Tool {tool_use_count} returned no result")
                    
                    self.logger.info(f"📊 Total tool calls executed: {tool_use_count}")
                    self.logger.info(f"📤 Tool results generated: {len(tool_result_content)}")
                    
                    # Check for natural task completion (no more tool calls)
                    task_completed = False
                    completion_text = None
                    for content_block in response.content:
                        if hasattr(content_block, 'text') and content_block.text:
                            # If there's text content and no tool calls, consider it natural completion
                            if not tool_result_content:
                                task_completed = True
                                completion_text = content_block.text
                                self.logger.info(f"✅ Natural task completion detected in iteration {iteration}")
                                break
                    
                    # If no tool results and task completed naturally, conversation is complete
                    if not tool_result_content and task_completed:
                        self.logger.info(f"🎯 Task completed naturally in {iteration} iterations")
                        
                        # ✅ Create explicit completion message for live monitoring
                        if completion_text:
                            completion_item = {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "text", "text": completion_text}],
                                "id": f"msg_assistant_{int(time.time())}"
                            }
                        else:
                            # Model completed without text (just stopped calling tools)
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
                        break
                    
                    # If no tool results, check if we should continue
                    if not tool_result_content:
                        self.logger.warning(f"⚠️ No tool calls in iteration {iteration}")
                        # Allow a few iterations without tool calls before stopping
                        if iteration > 3:
                            self.logger.warning(f"⚠️ Stopping after {iteration} iterations without tool calls")
                            break
                    
                    # ✅ Take screenshot at iteration end BEFORE reporting (for timeline)
                    iteration_screenshot_path = None
                    try:
                        if hasattr(self, 'computer') and self.computer:
                            iteration_screenshot_path = self._take_screenshot("iteration_end", iteration)
                            self.logger.info(f"📸 Saved iteration_end screenshot: {iteration_screenshot_path}")
                            # ✅ FIX: Update _last_after_screenshot for next action's BEFORE
                            # This is critical for non-computer tools (memory, bash, etc.)
                            # which don't go through _execute_computer_action
                            self._last_after_screenshot = iteration_screenshot_path
                            self.logger.info(f"📸 Updated _last_after_screenshot for next action: {iteration_screenshot_path}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to take iteration_end screenshot: {e}")
                    
                    # CRITICAL: Expose tool results to the runner for step counting
                    if tool_result_content:
                        # ✅ Create ENRICHED copies for internal tracking (with screenshot, action, url)
                        # These go to all_items and timeline but NOT to Anthropic API
                        enriched_results = []
                        for i, tool_result in enumerate(tool_result_content):
                            # Deep copy to avoid modifying the original
                            import copy
                            enriched = copy.deepcopy(tool_result)
                            
                            # ✅ Add metadata (action, url, coordinates, text, screenshots, etc.) if available
                            if i < len(tool_metadata):
                                meta = tool_metadata[i]
                                if meta.get("action"):
                                    enriched["action"] = meta["action"]
                                # ✅ Add tool_input for timeline extraction
                                if meta.get("tool_input"):
                                    enriched["tool_input"] = meta["tool_input"]
                                if meta.get("url"):
                                    enriched["url"] = meta["url"]
                                if meta.get("coordinates") is not None:
                                    enriched["coordinates"] = meta["coordinates"]
                                if meta.get("start_coordinates") is not None:
                                    enriched["start_coordinates"] = meta["start_coordinates"]
                                if meta.get("target_coordinates") is not None:
                                    enriched["target_coordinates"] = meta["target_coordinates"]
                                if meta.get("coordinates_normalized") is not None:
                                    enriched["coordinates_normalized"] = meta["coordinates_normalized"]
                                if meta.get("text"):
                                    enriched["text"] = meta["text"]
                                # ✅ Always add key field if present in metadata (even if empty string)
                                if "key" in meta:
                                    enriched["key"] = meta["key"]
                                    # Debug: Log key addition for keypress actions
                                    if meta.get("action") == "key":
                                        self.logger.debug(f"⌨️ Added key to enriched: '{enriched['key']}' for action={meta.get('action')}")
                                if meta.get("direction"):
                                    enriched["direction"] = meta["direction"]
                                if meta.get("amount"):
                                    enriched["amount"] = meta["amount"]
                                if meta.get("magnitude"):
                                    enriched["magnitude"] = meta["magnitude"]
                                # ✅ Add tab_info for list_tabs actions
                                if meta.get("tab_info"):
                                    enriched["tab_info"] = meta["tab_info"]
                                    self.logger.debug(f"📑 ✅ Added tab_info to enriched: {meta['tab_info']}")
                                # ✅ Add before/after screenshots
                                if meta.get("screenshot_before"):
                                    enriched["screenshot_before"] = meta["screenshot_before"]
                                    self.logger.debug(f"📸 ✅ Added BEFORE to enriched: {meta['screenshot_before']}")
                                if meta.get("screenshot_after"):
                                    enriched["screenshot_after"] = meta["screenshot_after"]
                                    enriched["screenshot"] = meta["screenshot_after"]  # Legacy field
                                    self.logger.debug(f"📸 ✅ Added AFTER to enriched: {meta['screenshot_after']}")
                                elif iteration_screenshot_path:
                                    # Fallback to iteration end if no specific after screenshot
                                    enriched["screenshot_after"] = iteration_screenshot_path
                                    enriched["screenshot"] = iteration_screenshot_path
                                    self.logger.debug(f"📸 ℹ️ Using iteration screenshot as fallback: {iteration_screenshot_path}")
                            
                            # Legacy: Add screenshot path if not already set by metadata
                            if "screenshot" not in enriched:
                                if iteration_screenshot_path:
                                    enriched["screenshot"] = iteration_screenshot_path
                            
                            enriched_results.append(enriched)
                        
                        # Add enriched versions to all_items and report to timeline
                        all_items.extend(enriched_results)
                        
                        # ✅ Report enriched results (with screenshots, action, url) to timeline
                        for item in enriched_results:
                            self._report_action(item)
                        
                        self.logger.info(f"✅ Reported {len(enriched_results)} tool results with metadata to timeline")
                        
                        # ✅ Add CLEAN versions (without screenshot/action/url) to API messages
                        # Anthropic API only accepts: type, tool_use_id, content
                        messages.append({
                            "role": "user",
                            "content": tool_result_content  # Original clean versions
                        })
                        self.logger.info(f"📝 Added {len(tool_result_content)} CLEAN tool results to conversation (API)")
                    
                    # Get screenshot data to send to API
                    try:
                        if hasattr(self, 'computer') and self.computer:
                            # ✅ CRITICAL FIX: Reuse the same screenshot we captured after the action
                            # Don't capture a new one - page state might have changed!
                            screenshot_data = None
                            
                            # Try to reuse the last "after" screenshot we captured
                            if hasattr(self, '_last_screenshot_after') and self._last_screenshot_after:
                                # Read the screenshot file we already saved
                                from pathlib import Path
                                screenshot_file = Path(self._last_screenshot_after)
                                if screenshot_file.exists():
                                    import base64
                                    with open(screenshot_file, 'rb') as f:
                                        screenshot_bytes = f.read()
                                    base64_data = base64.b64encode(screenshot_bytes).decode('utf-8')
                                    screenshot_data = base64_data
                                    self.logger.info(f"📸 Reusing saved after screenshot: {self._last_screenshot_after}")
                            
                            # Fallback: If no saved screenshot, capture a new one
                            if not screenshot_data:
                                screenshot_data = self.computer.screenshot()
                                self.logger.info(f"📸 No saved screenshot found, capturing fresh one")
                            
                            if screenshot_data:
                                # Convert to base64 if needed
                                if isinstance(screenshot_data, bytes):
                                    import base64
                                    base64_data = base64.b64encode(screenshot_data).decode('utf-8')
                                elif isinstance(screenshot_data, str) and screenshot_data.startswith('data:image/'):
                                    base64_data = screenshot_data.split(',')[1]
                                else:
                                    base64_data = screenshot_data
                                
                                # Add screenshot to conversation as a user message
                                messages.append({
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"Iteration {iteration} completed. Here is the current state:"
                                        },
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": "image/png",
                                                "data": base64_data
                                            }
                                        }
                                    ]
                                })
                                self.logger.info(f"📸 Sent iteration {iteration} screenshot to API")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Failed to capture/send iteration {iteration} screenshot: {e}")
                    
                except CriticalAPIError as api_error:
                    # Re-raise CriticalAPIError to crash immediately (skip verification)
                    self.logger.error(f"🚨 CRITICAL API ERROR in Anthropic iteration {iteration}: {api_error}")
                    raise
                except CriticalTimeoutError as timeout_error:
                    # Re-raise CriticalTimeoutError to crash immediately (skip verification)
                    self.logger.error(f"🚨 CRITICAL TIMEOUT in Anthropic iteration {iteration}: {timeout_error}")
                    raise
                except Exception as e:
                    self.logger.error(f"❌ Error in Anthropic iteration {iteration}: {e}")
                    # Add error information to all_items for debugging
                    all_items.append({
                        "type": "error",
                        "iteration": iteration,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
                    break
            
            # Check if the last item was an error
            if all_items and all_items[-1].get("type") == "error":
                self.logger.error(f"❌ Task execution failed due to error in iteration {iteration}")
            else:
                self.logger.info(f"🏁 Anthropic agent execution completed after {iteration} iterations")
            
            self.logger.info("📸 Screenshots captured using complete independent implementation")
            self.logger.info("✅ Anthropic agent execution completed successfully")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            return all_items
            
        except CriticalAPIError as api_error:
            # Re-raise CriticalAPIError to crash immediately (skip verification)
            self.logger.error(f"🚨 CRITICAL API ERROR in Anthropic agent execution: {api_error}")
            raise
        except CriticalTimeoutError as timeout_error:
            # Re-raise CriticalTimeoutError to crash immediately (skip verification)
            self.logger.error(f"🚨 CRITICAL TIMEOUT in Anthropic agent execution: {timeout_error}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Anthropic agent execution failed: {e}")
            
            # Note: Final summary generation moved to unified_task_runner.py
            # to include verification status context
            
            raise

    def _process_anthropic_response(self, response: BetaMessage) -> List[Dict]:
        """Process Anthropic API response and convert to our format"""
        items = []
        
        for content_block in response.content:
            if hasattr(content_block, 'text') and content_block.text:
                items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": content_block.text}],
                    "id": f"msg_{int(time.time())}"
                })
            elif hasattr(content_block, 'type') and content_block.type == "tool_use":
                items.append({
                    "type": "tool_use",
                    "name": content_block.name,
                    "input": content_block.input,
                    "id": content_block.id
                })
        
        return items
    
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
            
            # Clean up screenshot helper if it exists
            if self.screenshot_helper:
                self.screenshot_helper = None
            self.logger.info("🧹 Anthropic agent resources cleaned up")
        except Exception as e:
            self.logger.warning(f"⚠️ Error cleaning up Anthropic agent resources: {e}")
    
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
