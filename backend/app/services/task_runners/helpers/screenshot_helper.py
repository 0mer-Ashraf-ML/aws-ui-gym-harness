#!/usr/bin/env python3
"""
Screenshot Helper - Independent screenshot mechanism
Extracted from V1 agents but completely independent implementation
"""

import base64
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class ScreenshotHelper:
    """Independent screenshot helper - no V1 dependencies"""
    
    def __init__(self, screenshot_dir: str, logger: logging.Logger = None):
        """
        Initialize screenshot helper
        
        Args:
            screenshot_dir: Directory to save screenshots
            logger: Logger instance
        """
        self.screenshot_dir = screenshot_dir
        self.logger = logger or logging.getLogger(__name__)
        
        # Create screenshot directory if it doesn't exist
        if screenshot_dir:
            Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    
    def save_screenshot(self, screenshot_data: str, step_name: str = "agent_screenshot") -> Optional[str]:
        """
        Save screenshot data to file - independent implementation
        
        Args:
            screenshot_data: Base64 encoded screenshot data or file path
            step_name: Name for the screenshot file
            
        Returns:
            Path to saved screenshot file or None if failed
        """
        if not self.screenshot_dir:
            self.logger.warning("⚠️ No screenshot directory available")
            return None
        
        try:
            # Generate filename with timestamp
            timestamp = int(time.time() * 1000)
            filename = f"{step_name}_{timestamp}.png"
            screenshot_path = Path(self.screenshot_dir) / filename
            
            # Handle different screenshot data formats
            if isinstance(screenshot_data, str) and Path(screenshot_data).exists():
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
                    # Assume it's base64 encoded data (from computer.screenshot())
                    base64_data = screenshot_data
                
                # Decode base64 and save
                try:
                    image_data = base64.b64decode(base64_data)
                    with open(screenshot_path, 'wb') as f:
                        f.write(image_data)
                except Exception as decode_error:
                    self.logger.error(f"❌ Failed to decode base64 screenshot data: {decode_error}")
                    return None
            else:
                self.logger.warning(f"⚠️ Unknown screenshot data format: {type(screenshot_data)}")
                return None
            
            self.logger.info(f"📸 Saved agent screenshot: {screenshot_path}")
            return str(screenshot_path)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save screenshot: {e}")
            return None
    
    def take_and_save_screenshot(self, computer, step_name: str = "agent_screenshot", wait_for_settle: bool = True) -> Optional[str]:
        """
        Take screenshot using computer and save it - independent implementation
        
        Args:
            computer: Computer instance to take screenshot
            step_name: Name for the screenshot file
            wait_for_settle: If True, wait 0.9s for DOM to settle before screenshot.
                           Set to False for "before" screenshots to capture immediate state.
            
        Returns:
            Path to saved screenshot file or None if failed
        """
        if not self.screenshot_dir:
            self.logger.warning("⚠️ No screenshot directory available")
            return None
        
        try:
            if not computer:
                self.logger.error("❌ Computer not initialized for screenshot")
                return None
            
            # ✅ For BEFORE screenshots: Use immediate capture (no waiting)
            # ✅ For AFTER screenshots: Wait then use normal capture
            if not wait_for_settle:
                # Use immediate screenshot method if available (no waiting at all)
                if hasattr(computer, 'screenshot_immediate'):
                    screenshot_data = computer.screenshot_immediate()
                    self.logger.info(f"📸 Used immediate screenshot (no wait) for {step_name}")
                else:
                    # Fallback to regular screenshot
                    screenshot_data = computer.screenshot()
                    self.logger.warning(f"⚠️ No immediate screenshot available, using regular for {step_name}")
            else:
                # AFTER screenshot: wait then capture
                time.sleep(0.9)
                screenshot_data = computer.screenshot()
            
            if not screenshot_data:
                self.logger.warning(f"⚠️ No screenshot data returned for {step_name}")
                return None
            
            # Generate filename with timestamp
            timestamp = int(time.time() * 1000)
            filename = f"{step_name}_{timestamp}.png"
            screenshot_path = Path(self.screenshot_dir) / filename
            
            # Decode base64 data and save directly
            try:
                image_data = base64.b64decode(screenshot_data)
                with open(screenshot_path, 'wb') as f:
                    f.write(image_data)
                
                self.logger.info(f"📸 Saved agent screenshot: {screenshot_path}")
                return str(screenshot_path)
                
            except Exception as decode_error:
                self.logger.error(f"❌ Failed to decode base64 screenshot data: {decode_error}")
                return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to take and save screenshot for {step_name}: {e}")
            return None
    
    def execute_action_with_screenshot(self, computer, action_type: str, action_args: Dict[str, Any], step_name: str = None) -> Optional[str]:
        """
        Execute computer action and take screenshot - independent implementation
        This replaces the V1 agent's computer call handling
        
        Args:
            computer: Computer instance
            action_type: Type of action (click, type, etc.)
            action_args: Arguments for the action
            step_name: Name for the screenshot file (defaults to action_type)
            
        Returns:
            Path to saved screenshot file or None if failed
        """
        if not computer:
            self.logger.error("❌ Computer not initialized")
            return None
        
        try:
            # Execute the computer action
            method = getattr(computer, action_type)
            method(**action_args)
            
            # Log the action
            self.logger.info(f"🔧 Executed action: {action_type}({action_args})")
            
            # Take screenshot after action (except for screenshot action itself)
            if action_type != "screenshot":
                screenshot_name = step_name or f"after_{action_type}"
                return self.take_and_save_screenshot(computer, screenshot_name)
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to execute action {action_type}: {e}")
            return None
