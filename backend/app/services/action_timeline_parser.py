"""
Action Timeline Parser

Parses conversation history from different model types (Anthropic, OpenAI, Gemini)
and creates a unified timeline of model thinking, responses, and actions.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.action_timeline import (
    ActionEntry,
    ActionStatus,
    ActionType,
    ModelResponseEntry,
    ModelThinkingEntry,
    TimelineEntry,
)

logger = logging.getLogger(__name__)


class ActionTimelineParser:
    """Parser for conversation history to create action timeline"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_conversation_history(self, file_path: Path) -> List[TimelineEntry]:
        """
        Parse conversation history file and create timeline entries
        
        Args:
            file_path: Path to conversation history JSON file
            
        Returns:
            List of TimelineEntry objects in chronological order
        """
        try:
            if not file_path.exists():
                self.logger.warning(f"Conversation history file not found: {file_path}")
                return []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            conversation_flow = data.get('conversation_flow', [])
            if not conversation_flow:
                self.logger.warning(f"No conversation flow in file: {file_path}")
                return []
            
            # Get task_id from the filename pattern
            task_id = file_path.parent.parent.name  # iteration_N/../task_id/
            screenshot_dir = file_path.parent.parent / "screenshots"
            
            # Get all available screenshots sorted by filename (which includes timestamp)
            available_screenshots = []
            if screenshot_dir and screenshot_dir.exists():
                # Get all PNG files except iteration_end screenshots
                all_screenshots = list(screenshot_dir.glob("*.png"))
                available_screenshots = sorted([
                    s for s in all_screenshots 
                    if not s.name.startswith("iteration_") or not "_iteration_end_" in s.name
                ], key=lambda p: p.name)
            
            entries: List[TimelineEntry] = []
            sequence_index = 0
            action_index = 0  # Separate counter for actions to map to screenshots
            
            for item in conversation_flow:
                entry = self._parse_item(item, sequence_index, task_id, screenshot_dir, available_screenshots, action_index)
                if entry:
                    entries.append(entry)
                    sequence_index += 1
                    # Increment action index only for action entries
                    if entry.entry_type == 'action':
                        action_index += 1
            
            # Add final AI remarks if present
            final_summary = data.get('final_summary') or data.get('completion_message')
            if final_summary:
                entries.append(ModelResponseEntry(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    sequence_index=sequence_index,
                    content=final_summary
                ))
            
            self.logger.info(f"Parsed {len(entries)} timeline entries from {file_path}")
            return entries
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from {file_path}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error parsing conversation history {file_path}: {e}")
            return []
    
    def _parse_item(self, item: Dict[str, Any], sequence_index: int, task_id: str = None, screenshot_dir: Path = None, available_screenshots: List[Path] = None, action_index: int = 0) -> Optional[TimelineEntry]:
        """Parse a single conversation flow item into a timeline entry"""
        try:
            item_type = item.get('type', 'unknown')
            timestamp = self._parse_timestamp(item.get('timestamp'))
            entry_id = str(uuid.uuid4())
            
            # Handle model messages (thinking/responses)
            if item_type == 'message':
                role = item.get('role', '')
                if role == 'assistant':
                    content = item.get('content', '')
                    if not content:
                        content = item.get('content_preview', '')
                    
                    if not content:
                        return None
                    
                    # Heuristic: if content is short and contains action words, it's thinking
                    # Otherwise it's a response
                    if self._is_thinking(content):
                        return ModelThinkingEntry(
                            id=entry_id,
                            timestamp=timestamp,
                            sequence_index=sequence_index,
                            content=content
                        )
                    else:
                        return ModelResponseEntry(
                            id=entry_id,
                            timestamp=timestamp,
                            sequence_index=sequence_index,
                            content=content
                        )
            
            # Handle computer actions (all models)
            elif item_type in ['computer_call_output', 'bash_output', 'editor_output', 'search_output', 'tool_use']:
                return self._parse_action(item, entry_id, timestamp, sequence_index, task_id, screenshot_dir, available_screenshots, action_index)
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Failed to parse item: {e}")
            return None
    
    def _parse_action(self, item: Dict[str, Any], entry_id: str, timestamp: datetime, sequence_index: int, task_id: str = None, screenshot_dir: Path = None, available_screenshots: List[Path] = None, action_index: int = 0) -> Optional[ActionEntry]:
        """Parse an action item into an ActionEntry"""
        try:
            item_type = item.get('type', 'unknown')
            
            # Extract action details from multiple possible formats
            # Check for tool_input first (new format)
            computer_action = None
            if 'tool_input' in item and isinstance(item['tool_input'], dict):
                tool_input = item['tool_input']
                computer_action = tool_input.get('action', None)
            
            # Try multiple field names for action
            if not computer_action:
                computer_action = (
                    item.get('computer_action') or 
                    item.get('action') or 
                    item.get('tool_name') or
                    item.get('command') or
                    item.get('args', {}).get('action') if isinstance(item.get('args'), dict) else None
                )
            
            # If still no action found, try to infer from item_type
            if not computer_action:
                if item_type == 'computer_call_output':
                    # Try to get action from previous computer_call or args
                    if 'args' in item and isinstance(item['args'], dict):
                        computer_action = item['args'].get('action', item_type)
                    else:
                        computer_action = item_type
                else:
                    computer_action = item_type
            
            self.logger.debug(f"Extracted computer_action: '{computer_action}' from item_type: '{item_type}'")
            
            # Determine action type and name
            action_type, action_name = self._determine_action_type_and_name(computer_action, item_type)
            
            # Create description
            description = self._create_action_description(computer_action, item, action_type)
            
            # INTELLIGENT SCREENSHOT MAPPING
            # The conversation history may have null/incorrect paths, so we intelligently map
            # actions to available screenshots based on naming patterns and sequence
            screenshot_path = None
            
            if available_screenshots and action_index < len(available_screenshots):
                # Use the available screenshots in order
                # Screenshots are already sorted by filename (which includes timestamp)
                screenshot_file = available_screenshots[action_index]
                screenshot_path = f"screenshots/{screenshot_file.name}"
                self.logger.debug(f"✅ Mapped action {action_index} ({computer_action}) → {screenshot_file.name}")
            else:
                # No more screenshots available, try common fallbacks
                if screenshot_dir and screenshot_dir.exists():
                    # Look for iteration_end screenshot
                    end_screenshots = list(screenshot_dir.glob("*_iteration_end_*.png"))
                    if end_screenshots:
                        screenshot_path = f"screenshots/{end_screenshots[0].name}"
                        self.logger.debug(f"⚠️ Using iteration_end screenshot for action {action_index}")
                    else:
                        # Just use the last available screenshot
                        all_screenshots = sorted(screenshot_dir.glob("*.png"), key=lambda p: p.name)
                        if all_screenshots:
                            screenshot_path = f"screenshots/{all_screenshots[-1].name}"
                            self.logger.debug(f"⚠️ Using last screenshot for action {action_index}")
            
            # Absolute final fallback (should rarely hit this)
            if not screenshot_path:
                screenshot_path = "screenshots/iteration_end_screenshot.png"
                self.logger.warning(f"❌ No screenshot found for action {action_index} ({computer_action})")
            
            # Get URL if available
            current_url = item.get('url', item.get('current_url', None))
            
            # Try to infer URL from iteration context if not available
            if not current_url and computer_action:
                action_lower = computer_action.lower()
                if 'dashdoor' in action_lower or 'doordash' in action_lower:
                    current_url = "https://app.dashdoor.rlgym.turing.com"
                elif 'zendesk' in action_lower:
                    current_url = "https://app.zendesk.rlgym.turing.com"
                elif 'mira' in action_lower or 'jira' in action_lower:
                    current_url = "https://app.mira.rlgym.turing.com"
            
            # Determine status
            status = ActionStatus.SUCCESS
            if item.get('error') or item.get('failed'):
                status = ActionStatus.FAILED
            
            # Metadata
            metadata = {
                'raw_action': computer_action,
                'item_type': item_type,
            }
            
            # Add specific metadata from multiple possible sources
            # Check tool_input first (new format)
            if 'tool_input' in item and isinstance(item['tool_input'], dict):
                tool_input = item['tool_input']
                if 'coordinate' in tool_input:
                    metadata['coordinates'] = tool_input['coordinate']
                if 'text' in tool_input:
                    metadata['text'] = tool_input['text']
                if 'key' in tool_input:
                    metadata['key'] = tool_input['key']
            
            # Also check direct fields (legacy format)
            if 'coordinates' in item:
                metadata['coordinates'] = item['coordinates']
            if 'text' in item:
                metadata['text'] = item['text']
            if 'key' in item:
                metadata['key'] = item['key']
            if 'command' in item:
                metadata['command'] = item['command']
            
            return ActionEntry(
                id=entry_id,
                timestamp=timestamp,
                sequence_index=sequence_index,
                action_type=action_type,
                action_name=action_name,
                description=description,
                screenshot_path=screenshot_path,
                current_url=current_url,
                status=status,
                metadata=metadata
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse action: {e}")
            return None
    
    def _map_action_to_screenshot_step(self, computer_action: str, action_type: ActionType) -> Optional[str]:
        """Map computer action to screenshot step name used by runner"""
        action_lower = computer_action.lower() if computer_action else ''
        
        # Map to known screenshot step names from the runner
        if 'open_web' in action_lower or 'browser' in action_lower:
            return "initial_page"
        elif action_type == ActionType.NAVIGATE:
            return "after_navigation"
        elif 'wait' in action_lower:
            return None  # Wait actions typically don't have dedicated screenshots
        
        # For other actions, use the action name itself
        return computer_action if computer_action else None
    
    def _determine_action_type_and_name(self, computer_action: str, item_type: str) -> tuple[ActionType, str]:
        """Determine action type and user-friendly name"""
        action_lower = computer_action.lower() if computer_action else ''
        
        # More specific patterns first
        if 'click' in action_lower or 'left_click' in action_lower or 'right_click' in action_lower:
            return ActionType.CLICK, "Click"
        elif 'type' in action_lower or 'key' in action_lower:
            return ActionType.TYPE, "Type Text"
        elif 'scroll' in action_lower:
            return ActionType.SCROLL, "Scroll"
        elif 'screenshot' in action_lower:
            return ActionType.SCREENSHOT, "Take Screenshot"
        elif 'navigate' in action_lower or 'goto' in action_lower or 'browser' in action_lower or 'open_web' in action_lower:
            return ActionType.NAVIGATE, "Open Browser" if 'open' in action_lower else "Navigate"
        elif 'wait' in action_lower:
            return ActionType.OTHER, "Wait"
        elif 'bash' in item_type or 'command' in action_lower:
            return ActionType.BASH_COMMAND, "Execute Command"
        elif 'editor' in item_type or 'edit' in action_lower:
            return ActionType.EDITOR_ACTION, "Edit File"
        else:
            # Try to extract a readable name from the action
            # Convert snake_case to Title Case
            readable = computer_action.replace('_', ' ').title() if computer_action else "Computer Action"
            return ActionType.COMPUTER_ACTION, readable
    
    def _create_action_description(self, computer_action: str, item: Dict, action_type: ActionType) -> str:
        """Create detailed, user-friendly action description with all relevant information"""
        
        # Extract tool_input if available (new format)
        tool_input = item.get('tool_input', {}) if isinstance(item.get('tool_input'), dict) else {}
        
        # CLICK ACTIONS - Show coordinates, button type, and what was clicked
        if action_type == ActionType.CLICK:
            coords = item.get('coordinates') or item.get('coord') or tool_input.get('coordinate')
            
            # Determine click type (left/right/double)
            click_type = "Left clicked"
            if 'right_click' in computer_action.lower():
                click_type = "Right clicked"
            elif 'double_click' in computer_action.lower():
                click_type = "Double clicked"
            elif 'middle_click' in computer_action.lower():
                click_type = "Middle clicked"
            
            if coords and len(coords) >= 2:
                return f"{click_type} at coordinates ({coords[0]}, {coords[1]})"
            return f"{click_type} on element"
        
        # TYPE ACTIONS - Show what is typed, where, and if Enter is pressed
        elif action_type == ActionType.TYPE:
            text = item.get('text') or tool_input.get('text') or ''
            coords = item.get('coordinates') or tool_input.get('coordinate')
            
            # Check if Enter key is pressed after typing (Gemini behavior)
            has_enter = False
            action_lower = computer_action.lower()
            if 'enter' in action_lower or item.get('submit', False) or tool_input.get('submit', False):
                has_enter = True
            
            # Build description
            if text:
                text_preview = f'"{text[:80]}..."' if len(text) > 80 else f'"{text}"'
                
                if coords and len(coords) >= 2:
                    base_desc = f"Typed {text_preview} at coordinates ({coords[0]}, {coords[1]})"
                else:
                    base_desc = f"Typed {text_preview} in active field"
                
                # Add Enter key info if present (important for Gemini)
                if has_enter:
                    base_desc += " and pressed Enter"
                
                return base_desc
            
            # Just key press without text
            key = item.get('key') or tool_input.get('key')
            if key:
                return f"Pressed key: {key}"
            
            return "Typed text in field"
        
        # NAVIGATE/BROWSER ACTIONS - Show URL and action type
        elif action_type == ActionType.NAVIGATE:
            url = item.get('url') or item.get('current_url') or item.get('target_url') or tool_input.get('url') or ''
            
            if 'open' in computer_action.lower() or 'browser' in computer_action.lower():
                if url:
                    return f"Opened browser and navigated to {url}"
                return "Opened browser"
            else:
                if url:
                    return f"Navigated to {url}"
                return "Navigated to page"
        
        # BASH/COMMAND ACTIONS - Show command being executed
        elif action_type == ActionType.BASH_COMMAND:
            cmd = item.get('command') or tool_input.get('command') or computer_action
            
            if cmd:
                cmd_preview = cmd[:80] + '...' if len(cmd) > 80 else cmd
                return f"Executed command: {cmd_preview}"
            return "Executed bash command"
        
        # EDITOR ACTIONS - Show file and operation
        elif action_type == ActionType.EDITOR_ACTION:
            file_path = item.get('file') or item.get('path') or tool_input.get('file') or ''
            
            if file_path:
                return f"Edited file: {file_path}"
            return f"Performed editor action"
        
        # SCREENSHOT ACTIONS
        elif action_type == ActionType.SCREENSHOT:
            return "Captured screenshot"
        
        # SCROLL ACTIONS - Show direction and amount
        elif action_type == ActionType.SCROLL:
            direction = item.get('direction', tool_input.get('direction', 'unknown'))
            amount = item.get('amount', tool_input.get('amount', ''))
            
            desc_parts = [f"Scrolled {direction}"]
            if amount:
                desc_parts.append(f"by {amount} pixels")
            
            return " ".join(desc_parts)
        
        # KEY_PRESS ACTIONS - Show which key(s) are pressed
        elif action_type == ActionType.KEY_PRESS:
            key = item.get('key') or tool_input.get('key') or item.get('text') or tool_input.get('text')
            
            if key:
                # Handle multiple keys (e.g., Ctrl+C)
                if isinstance(key, list):
                    key_str = '+'.join(str(k) for k in key)
                    return f"Pressed keys: {key_str}"
                else:
                    return f"Pressed key: {key}"
            
            return "Pressed keyboard key"
        
        # GENERIC FALLBACK - Try to make it readable
        else:
            readable = computer_action.replace('_', ' ').title() if computer_action else "Performed action"
            
            # Add coordinates if available
            coords = item.get('coordinates') or tool_input.get('coordinate')
            if coords and len(coords) >= 2:
                return f"{readable} at ({coords[0]}, {coords[1]})"
            
            return readable
    
    def _is_thinking(self, content: str) -> bool:
        """
        Heuristic to determine if content is thinking vs response
        Thinking typically contains keywords like "need to", "should", "will", etc.
        """
        thinking_keywords = [
            'need to', 'should', 'will', 'going to', 'let me', 'i see', 'i notice',
            'first', 'next', 'then', 'now i', 'i can', 'i must', 'i should'
        ]
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in thinking_keywords)
    
    def _parse_timestamp(self, timestamp_str: Any) -> datetime:
        """Parse timestamp string to datetime object"""
        if isinstance(timestamp_str, datetime):
            return timestamp_str
        
        if not timestamp_str or timestamp_str == 'N/A':
            return datetime.now()
        
        try:
            # Try ISO format first
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            try:
                # Try other common formats
                return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except:
                return datetime.now()
    
    def serialize_timeline(self, entries: List[TimelineEntry]) -> str:
        """Serialize timeline entries to JSON string"""
        try:
            entries_dict = [entry.dict() for entry in entries]
            return json.dumps(entries_dict, default=str)
        except Exception as e:
            self.logger.error(f"Failed to serialize timeline: {e}")
            return "[]"
    
    def deserialize_timeline(self, json_str: str) -> List[TimelineEntry]:
        """Deserialize JSON string to timeline entries"""
        try:
            if not json_str:
                return []
            
            data = json.loads(json_str)
            entries = []
            
            for item in data:
                entry_type = item.get('entry_type')
                
                if entry_type == 'model_thinking':
                    entries.append(ModelThinkingEntry(**item))
                elif entry_type == 'model_response':
                    entries.append(ModelResponseEntry(**item))
                elif entry_type == 'action':
                    entries.append(ActionEntry(**item))
            
            return entries
            
        except Exception as e:
            self.logger.error(f"Failed to deserialize timeline: {e}")
            return []


# Singleton instance
timeline_parser = ActionTimelineParser()

