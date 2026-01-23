import sys
import time
from datetime import datetime
from typing import Literal, Optional

from celery.exceptions import SoftTimeLimitExceeded
from playwright.sync_api import Browser, Page

from app.core.config import settings
from app.services.computers.shared.base_playwright import \
    BasePlaywrightComputer, with_timeout, BrowserError, ScreenshotError, retry_with_backoff
from app.services.computers.shared.env_state import EnvState


class LocalPlaywrightBrowser(BasePlaywrightComputer):
    """Enhanced local Chromium instance using Playwright with comprehensive error handling."""

    def __init__(self, headless: bool = None, logger_instance=None, video_dir: str = None):
        super().__init__(logger_instance=logger_instance)
        # If headless is not explicitly set, use DEBUG setting to determine headless mode
        # In debug mode, show browser (headless=False), in production hide browser (headless=True)
        # However, in Docker environments, always use headless mode regardless of DEBUG setting
        if headless is None:
            # Check if we're running in Docker (no DISPLAY environment variable)
            import os
            is_docker = not os.environ.get('DISPLAY') or os.environ.get('DOCKER_CONTAINER', '').lower() == 'true'
            if is_docker:
                self.headless = True  # Force headless in Docker
            else:
                self.headless = not settings.DEBUG
        else:
            self.headless = headless
        
        # Store video directory for recording
        self.video_dir = video_dir
        
        # Initialize auth token storage
        self.extracted_auth_token = None
        self._token_ready = False  # Flag for runner to check

    def _get_browser_and_page(self) -> tuple[Browser, Page]:
        width, height = self.get_dimensions()
        # Firefox-specific launch arguments (many Chromium args don't work with Firefox)
        launch_args = [
            # Basic stability for Firefox in Docker
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            
            # Firefox-specific performance optimizations
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            
            # Firefox automation settings
            "--disable-blink-features=AutomationControlled",
            
            # Logging and debugging (minimal for Docker stability)
            "--disable-logging",
            "--silent",
            
            # Firefox-specific stability settings
            "--disable-crash-reporter",
            "--disable-hang-monitor",
        ]
        browser = self._playwright.firefox.launch(
            headless=self.headless,
            args=launch_args,
        )

        # Prepare context options
        context_options = {
            # Add viewport settings
            "viewport": {"width": width, "height": height},
            # Add user agent to prevent detection
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            # Add extra HTTP headers
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        }
        
        # Add video recording if video_dir is provided
        # Note: Playwright automatically saves the video when the context closes
        # The video file will be named automatically (e.g., "video-{timestamp}.webm")
        # We'll rename it to trajectory_recording.webm after recording completes
        if self.video_dir:
            from pathlib import Path
            video_dir = Path(self.video_dir)
            video_dir.mkdir(parents=True, exist_ok=True)
            context_options["record_video_dir"] = str(video_dir)
            # Explicitly set video size to match viewport for full quality
            # Without this, Playwright may scale down videos larger than 800x800
            context_options["record_video_size"] = {"width": width, "height": height}
            if self.logger:
                self.logger.info(f"🎥 Video recording enabled: {video_dir}")
                self.logger.info(f"📹 Video resolution: {width}x{height} (matches viewport)")
                self.logger.info(f"📹 Video will be saved automatically when context closes")
        
        context = browser.new_context(**context_options)

        # Add event listeners for page creation and closure
        context.on("page", self._handle_new_page)

        page = context.new_page()
        page.set_viewport_size({"width": width, "height": height})
        page.on("close", self._handle_page_close)

        # Capture browser console output for debugging
        page.on("console", lambda msg: self.logger.info(f"🖥️  BROWSER CONSOLE [{msg.type}]: {msg.text}") if self.logger else print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: self.logger.error(f"🌋 BROWSER ERROR: {err}") if self.logger else print(f"BROWSER ERROR: {err}"))

        # Add response listener to capture auth token (for logging/debugging only)
        # Note: We now read token from localStorage instead of HTTP interception
        def handle_response(response):
            try:
                url = response.url or ""
                normalized_url = url.rstrip("/")
                
                if normalized_url.endswith("/auth/token"):
                    self.logger.info(f"[AUTH_TOKEN_RESPONSE] Detected auth token response from {url}")
                    try:
                        body = response.json()
                        if isinstance(body, dict) and ('token' in body or 'access_token' in body):
                            token = body.get('token') or body.get('access_token')
                            self.extracted_auth_token = token
                            self._token_ready = True  # Signal to runner
                            self.logger.info(f"✅ Auth token captured in real-time: {token[:8]}... (DeskZen will store it in localStorage automatically)")
                        else:
                            self.logger.warning(f"⚠️ Auth token response missing expected fields: {body}")
                    except Exception as e:
                        self.logger.error(f"❌ Failed to parse auth token response: {e}")
            except Exception as e:
                self.logger.error(f"❌ Response handler error: {e}")
        
        page.on("response", handle_response)

        # Don't navigate immediately - let the task handle navigation
        # This prevents timeouts during browser initialization
        # page.goto("https://bing.com")  # Removed to prevent initialization timeouts

        return browser, page

    def _handle_new_page(self, page: Page):
        """Handle the creation of a new page."""
        print("New page created")
        self._page = page
        page.on("close", self._handle_page_close)
        # Add console listeners to new pages
        page.on("console", lambda msg: self.logger.info(f"🖥️  BROWSER CONSOLE [{msg.type}]: {msg.text}") if self.logger else print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: self.logger.error(f"🌋 BROWSER ERROR: {err}") if self.logger else print(f"BROWSER ERROR: {err}"))

    def _handle_page_close(self, page: Page):
        """Handle the closure of a page."""
        print("Page closed")
        if self._page == page:
            if self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[-1]
            else:
                print("Warning: All pages have been closed.")
                self._page = None

    def get_auth_token(self) -> Optional[str]:
        """Get the extracted auth token from browser responses"""
        return getattr(self, 'extracted_auth_token', None)

    # ===== Gemini Computer Use Compatibility Methods =====

    def denormalize_x(self, x: int) -> int:
        """Convert normalized X coordinate (0-999) to actual pixel coordinate."""
        width, _ = self.get_dimensions()
        return int((x / 1000.0) * width)
    
    def denormalize_y(self, y: int) -> int:
        """Convert normalized Y coordinate (0-999) to actual pixel coordinate."""
        _, height = self.get_dimensions()
        return int((y / 1000.0) * height)
    
    def open_web_browser(self) -> EnvState:
        """Open web browser (no-op since browser is already open)."""
        return self.current_state()
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def click_at(self, x: int, y: int) -> EnvState:
        """Click at normalized coordinates."""
        self.computer_logger.push_operation("click_at")
        try:
            actual_x = self.denormalize_x(x)
            actual_y = self.denormalize_y(y)
            self._page.mouse.click(actual_x, actual_y)
            self._page.wait_for_load_state(timeout=5000)  # 5 second timeout
            self.computer_logger.pop_operation("click_at", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("click_at", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Click at failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def hover_at(self, x: int, y: int) -> EnvState:
        """Hover at normalized coordinates."""
        self.computer_logger.push_operation("hover_at")
        try:
            actual_x = self.denormalize_x(x)
            actual_y = self.denormalize_y(y)
            self._page.mouse.move(actual_x, actual_y)
            self._page.wait_for_load_state(timeout=5000)  # 5 second timeout
            self.computer_logger.pop_operation("hover_at", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("hover_at", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Hover at failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=300.0, timeout_exception=BrowserError, critical=True)
    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True
    ) -> EnvState:
        """Type text at normalized coordinates.
        
        Args:
            x: Normalized X coordinate (0-999)
            y: Normalized Y coordinate (0-999)
            text: Text to type
            press_enter: Whether to press Enter after typing (default: False)
            clear_before_typing: Whether to clear existing content before typing (default: True)
        """
        self.computer_logger.push_operation("type_text_at")
        try:
            actual_x = self.denormalize_x(x)
            actual_y = self.denormalize_y(y)
            self._page.mouse.click(actual_x, actual_y)
            self._page.wait_for_load_state(timeout=5000)  # 5 second timeout
            
            if clear_before_typing:
                # Clear existing content
                if sys.platform == "darwin":
                    self._page.keyboard.press("Meta+A")
                else:
                    self._page.keyboard.press("Control+A")
                self._page.keyboard.press("Delete")
            
            # Use enhanced typing approach with keyboard.type() as first preference
            try:
                # First preference: keyboard.type() - most reliable for form inputs
                for char in text:
                    self._page.keyboard.type(char, delay=50)
            except Exception:
                # Second preference: fill() method - good for most cases
                try:
                    self._page.fill('input, textarea', text)
                except Exception:
                    # Final fallback: direct value setting - fastest but least reliable
                    self._page.evaluate(f"""
                        (function() {{
                            const activeElement = document.activeElement;
                            if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {{
                                // Clear existing content first
                                activeElement.value = '';
                                activeElement.value = {repr(text)};
                                activeElement.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                activeElement.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }})()
                    """)
            self._page.wait_for_load_state(timeout=5000)  # 5 second timeout
            
            if press_enter:
                self._page.keyboard.press("Enter")
                self._page.wait_for_load_state(timeout=5000)  # 5 second timeout
            
            self.computer_logger.pop_operation("type_text_at", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("type_text_at", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Type text at failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def scroll_document(self, direction: Literal["up", "down", "left", "right"]) -> EnvState:
        """Scroll the entire document in the specified direction using mouse.wheel() for reliability.
        
        Uses mouse.wheel() instead of keyboard.press() for more reliable scrolling that works
        consistently across different browsers and page types.
        
        Args:
            direction: Direction to scroll ("up", "down", "left", "right")
        """
        self.computer_logger.push_operation("scroll_document")
        try:
            width, height = self.get_dimensions()
            
            if direction == "down":
                # Scroll down by ~80% of viewport height (similar to PageDown behavior)
                scroll_amount = int(height * 0.8)
                # Move mouse to center of viewport for reliable scrolling
                self._page.mouse.move(width // 2, height // 2)
                self._page.mouse.wheel(0, scroll_amount)
            elif direction == "up":
                # Scroll up by ~80% of viewport height (similar to PageUp behavior)
                scroll_amount = int(height * 0.8)
                # Move mouse to center of viewport for reliable scrolling
                self._page.mouse.move(width // 2, height // 2)
                self._page.mouse.wheel(0, -scroll_amount)
            elif direction == "left":
                # Scroll left by 50% of viewport width
                scroll_amount = width // 2
                # Move mouse to center of viewport for reliable scrolling
                self._page.mouse.move(width // 2, height // 2)
                self._page.mouse.wheel(-scroll_amount, 0)
            elif direction == "right":
                # Scroll right by 50% of viewport width
                scroll_amount = width // 2
                # Move mouse to center of viewport for reliable scrolling
                self._page.mouse.move(width // 2, height // 2)
                self._page.mouse.wheel(scroll_amount, 0)
            else:
                raise ValueError(f"Unsupported direction: {direction}")
            
            # Wait for scroll animation to complete and any lazy-loaded content to appear
            time.sleep(0.3)  # Increased wait time for scroll completion
            self.computer_logger.pop_operation("scroll_document", success=True)
            return self.current_state()
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("scroll_document", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Scroll document failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def scroll_at(
        self,
        x: int,
        y: int,
        direction: Literal["up", "down", "left", "right"],
        magnitude: int = 800
    ) -> EnvState:
        """Scroll at specific normalized coordinates.
        
        Args:
            x: Normalized X coordinate (0-999)
            y: Normalized Y coordinate (0-999)
            direction: Direction to scroll
            magnitude: Scroll magnitude (default: 800)
        """
        self.computer_logger.push_operation("scroll_at")
        try:
            actual_x = self.denormalize_x(x)
            actual_y = self.denormalize_y(y)
            self._page.mouse.move(actual_x, actual_y)
            
            # Denormalize magnitude based on direction
            if direction in ("up", "down"):
                actual_magnitude = self.denormalize_y(magnitude)
            elif direction in ("left", "right"):
                actual_magnitude = self.denormalize_x(magnitude)
            else:
                raise ValueError(f"Unsupported direction: {direction}")
            
            dx = 0
            dy = 0
            if direction == "up":
                dy = -actual_magnitude
            elif direction == "down":
                dy = actual_magnitude
            elif direction == "left":
                dx = -actual_magnitude
            elif direction == "right":
                dx = actual_magnitude
            
            self._page.mouse.wheel(dx, dy)
            
            # Wait briefly for scroll to complete, but don't wait for full page load
            time.sleep(0.2)  # Short wait for scroll animation
            self.computer_logger.pop_operation("scroll_at", success=True)
            return self.current_state()
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("scroll_at", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Scroll at failed: {e}") from e

    def wait_5_seconds(self) -> EnvState:
        """Wait for 5 seconds to allow unfinished webpage processes to complete."""

        time.sleep(5)
        return self.current_state()
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def go_back(self) -> EnvState:
        """Navigate back in browser history."""
        self.computer_logger.push_operation("go_back")
        try:
            self._page.go_back()
            # Wait for navigation to complete with timeout
            self._page.wait_for_load_state("domcontentloaded", timeout=10000)  # 10 second timeout
            self.computer_logger.pop_operation("go_back", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("go_back", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Go back failed: {e}") from e
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def go_forward(self) -> EnvState:
        """Navigate forward in browser history."""
        self.computer_logger.push_operation("go_forward")
        try:
            self._page.go_forward()
            # Wait for navigation to complete with timeout
            self._page.wait_for_load_state("domcontentloaded", timeout=10000)  # 10 second timeout
            self.computer_logger.pop_operation("go_forward", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("go_forward", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Go forward failed: {e}") from e
    
    def search(self) -> EnvState:
        """Navigate to Google search homepage."""
        return self.navigate("https://www.google.com")
    
    @retry_with_backoff(max_retries=3, base_delay=1.0, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=30.0, timeout_exception=BrowserError, critical=True)
    def navigate(self, url: str) -> EnvState:
        """Navigate to a URL.
        
        Args:
            url: URL to navigate to (will add https:// if no protocol specified)
        """
        self.computer_logger.push_operation("navigate")
        try:
            normalized_url = url
            if not normalized_url.startswith(("http://", "https://")):
                normalized_url = "https://" + normalized_url
            self._page.goto(normalized_url)
            # Wait for navigation to complete with timeout
            self._page.wait_for_load_state("domcontentloaded", timeout=30000)  # 30 second timeout
            self.computer_logger.pop_operation("navigate", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("navigate", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Navigate failed: {e}") from e
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def keypress(self, keys: list[str]) -> None:
        """Override keypress to intercept tab-related keyboard shortcuts.
        
        Intercepts browser tab shortcuts and maps them to Playwright tab functions:
        - Ctrl+T / Cmd+T: Switch to next tab (circular)
        - Ctrl+W / Cmd+W: Close current tab
        - Ctrl+Tab: Switch to next tab
        - Ctrl+Shift+Tab: Switch to previous tab
        - Ctrl+1-9: Switch to specific tab
        """
        self.computer_logger.push_operation("keypress")
        try:
            if not keys:
                return
            
            # Normalize keys for comparison
            normalized_keys = [key.lower() for key in keys]
            
            # Check if this is a tab-related shortcut
            has_ctrl = any(k in ['control', 'ctrl'] for k in normalized_keys)
            has_meta = any(k in ['meta', 'cmd', 'command'] for k in normalized_keys)
            has_shift = any(k in ['shift'] for k in normalized_keys)
            has_tab = any(k in ['tab'] for k in normalized_keys)
            
            # Extract non-modifier keys
            non_modifiers = [k for k in normalized_keys if k not in ['control', 'ctrl', 'meta', 'cmd', 'command', 'shift', 'alt', 'option']]
            
            # Ctrl+T or Cmd+T -> switch to NEXT tab (circular, NOT new tab)
            if (has_ctrl or has_meta) and 't' in non_modifiers and len(non_modifiers) == 1:
                self.logger.info("🔄 Intercepted Ctrl+T -> switching to next tab (circular)")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        next_idx = (current_idx + 1) % tab_count  # Wrap around (circular)
                        self.switch_tab(tab_index=next_idx)
                    self.computer_logger.pop_operation("keypress", success=True)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to switch to next tab: {e}")
                    # Fall through to normal keypress handling
            
            # Ctrl+W or Cmd+W -> close_tab
            elif (has_ctrl or has_meta) and 'w' in non_modifiers and len(non_modifiers) == 1:
                self.logger.info("🔄 Intercepted Ctrl+W -> calling close_tab()")
                self.close_tab()
                self.computer_logger.pop_operation("keypress", success=True)
                return
            
            # Ctrl+Tab -> next tab
            elif has_ctrl and has_tab and not has_shift:
                self.logger.info("🔄 Intercepted Ctrl+Tab -> switching to next tab")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        next_idx = (current_idx + 1) % tab_count
                        self.switch_tab(tab_index=next_idx)
                    self.computer_logger.pop_operation("keypress", success=True)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to switch to next tab: {e}")
                    # Fall through to normal keypress handling
            
            # Ctrl+Shift+Tab -> previous tab
            elif has_ctrl and has_shift and has_tab:
                self.logger.info("🔄 Intercepted Ctrl+Shift+Tab -> switching to previous tab")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        prev_idx = (current_idx - 1) % tab_count
                        self.switch_tab(tab_index=prev_idx)
                    self.computer_logger.pop_operation("keypress", success=True)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to switch to previous tab: {e}")
                    # Fall through to normal keypress handling
            
            # Ctrl+1 through Ctrl+9 -> switch to specific tab
            elif (has_ctrl or has_meta) and len(non_modifiers) == 1 and non_modifiers[0].isdigit():
                tab_num = int(non_modifiers[0])
                if 1 <= tab_num <= 9:
                    tab_idx = tab_num - 1
                    self.logger.info(f"🔄 Intercepted Ctrl+{tab_num} -> switching to tab {tab_idx}")
                    self.switch_tab(tab_index=tab_idx)
                    self.computer_logger.pop_operation("keypress", success=True)
                    return
            
            # If not a tab shortcut, call parent implementation
            super().keypress(keys)
            
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("keypress", success=False)
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Keypress failed: {e}") from e
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def key_combination(self, keys: list[str]) -> EnvState:
        """Press a combination of keys.
        
        Intercepts browser tab shortcuts and maps them to Playwright tab functions.
        
        Args:
            keys: List of keys to press (e.g., ["Control", "C"])
        """
        self.computer_logger.push_operation("key_combination")
        try:
            # Normalize keys to lowercase for comparison
            normalized_keys = [key.lower() for key in keys]
            
            # Map browser tab keyboard shortcuts to our tab functions
            # This allows models to use familiar keyboard shortcuts naturally
            
            # Ctrl+T or Cmd+T -> switch to NEXT tab (circular, NOT new tab)
            if len(normalized_keys) == 2 and normalized_keys[0] in ['control', 'ctrl', 'meta', 'cmd'] and normalized_keys[1] == 't':
                self.logger.info("🔄 Intercepted Ctrl+T -> switching to next tab (circular)")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        next_idx = (current_idx + 1) % tab_count  # Wrap around (circular)
                        result = self.switch_tab(tab_index=next_idx)
                        self.computer_logger.pop_operation("key_combination", success=True)
                        return result
                except Exception as e:
                    self.logger.error(f"Failed to switch to next tab: {e}")
                    # Fall through to normal key combination handling
            
            # Ctrl+W or Cmd+W -> close_tab
            elif len(normalized_keys) == 2 and normalized_keys[0] in ['control', 'ctrl', 'meta', 'cmd'] and normalized_keys[1] == 'w':
                self.logger.info("🔄 Intercepted Ctrl+W -> calling close_tab()")
                result = self.close_tab()
                self.computer_logger.pop_operation("key_combination", success=True)
                return result
            
            # Ctrl+Tab -> switch to next tab (current + 1)
            elif len(normalized_keys) == 2 and normalized_keys[0] in ['control', 'ctrl'] and normalized_keys[1] == 'tab':
                self.logger.info("🔄 Intercepted Ctrl+Tab -> switching to next tab")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        next_idx = (current_idx + 1) % tab_count  # Wrap around
                        result = self.switch_tab(tab_index=next_idx)
                        self.computer_logger.pop_operation("key_combination", success=True)
                        return result
                except Exception as e:
                    self.logger.error(f"Failed to switch to next tab: {e}")
                    # Fall through to normal key combination handling
            
            # Ctrl+Shift+Tab -> switch to previous tab (current - 1)
            elif len(normalized_keys) == 3 and normalized_keys[0] in ['control', 'ctrl'] and normalized_keys[1] == 'shift' and normalized_keys[2] == 'tab':
                self.logger.info("🔄 Intercepted Ctrl+Shift+Tab -> switching to previous tab")
                try:
                    tab_info = self.list_tabs()
                    current_idx = tab_info.get('current_tab_index', 0)
                    tab_count = tab_info.get('tab_count', 1)
                    if tab_count > 0:
                        prev_idx = (current_idx - 1) % tab_count  # Wrap around
                        result = self.switch_tab(tab_index=prev_idx)
                        self.computer_logger.pop_operation("key_combination", success=True)
                        return result
                except Exception as e:
                    self.logger.error(f"Failed to switch to previous tab: {e}")
                    # Fall through to normal key combination handling
            
            # Ctrl+1 through Ctrl+9 -> switch to specific tab
            elif len(normalized_keys) == 2 and normalized_keys[0] in ['control', 'ctrl', 'meta', 'cmd'] and normalized_keys[1].isdigit():
                tab_num = int(normalized_keys[1])
                if 1 <= tab_num <= 9:
                    tab_idx = tab_num - 1  # Convert to 0-based index
                    self.logger.info(f"🔄 Intercepted Ctrl+{tab_num} -> switching to tab {tab_idx}")
                    result = self.switch_tab(tab_index=tab_idx)
                    self.computer_logger.pop_operation("key_combination", success=True)
                    return result
            
            # If not a tab shortcut, proceed with normal key combination
            # Press all keys except the last one
            for key in keys[:-1]:
                self._page.keyboard.down(key)
            
            # Press and release the last key
            self._page.keyboard.press(keys[-1])
            
            # Release all modifier keys
            for key in reversed(keys[:-1]):
                self._page.keyboard.up(key)
            
            self._page.wait_for_load_state()
            self.computer_logger.pop_operation("key_combination", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("key_combination", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Key combination failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
        """Drag from start coordinates to destination coordinates.
        
        Args:
            x: Start normalized X coordinate (0-999)
            y: Start normalized Y coordinate (0-999)
            destination_x: Destination normalized X coordinate (0-999)
            destination_y: Destination normalized Y coordinate (0-999)
        """
        self.computer_logger.push_operation("drag_and_drop")
        try:
            actual_start_x = self.denormalize_x(x)
            actual_start_y = self.denormalize_y(y)
            actual_end_x = self.denormalize_x(destination_x)
            actual_end_y = self.denormalize_y(destination_y)
            
            self._page.mouse.move(actual_start_x, actual_start_y)
            self._page.wait_for_load_state()
            self._page.mouse.down()
            self._page.wait_for_load_state()
            
            self._page.mouse.move(actual_end_x, actual_end_y)
            self._page.wait_for_load_state()
            self._page.mouse.up()
            self._page.wait_for_load_state()
            
            self.computer_logger.pop_operation("drag_and_drop", success=True)
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("drag_and_drop", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Drag and drop failed: {e}") from e
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError, ScreenshotError))
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def screenshot_immediate(self) -> str:
        """
        Capture screenshot IMMEDIATELY without any waiting
        Used for "before" screenshots to capture true pre-action state
        Returns base64 encoded screenshot
        """
        import base64
        self.computer_logger.push_operation("screenshot_immediate")
        try:
            if not self._page or self._page.is_closed():
                raise BrowserError("Page is closed or invalid")
            
            # NO WAITING - capture immediately
            screenshot_bytes = self._page.screenshot(type='png', full_page=False, timeout=5000)
            self.computer_logger.pop_operation("screenshot_immediate", success=True)
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("screenshot_immediate", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            self.logger.error(f"Error in screenshot_immediate: {e}")
            raise BrowserError(f"Failed to capture immediate screenshot: {e}")
    
    # ===== Tab Management Methods (Playwright API - Not Keyboard Shortcuts) =====
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def new_tab(self, url: str = "") -> EnvState:
        """Open a new browser tab using Playwright API.
        
        Args:
            url: URL to navigate to in the new tab (optional)
        
        Returns:
            Current environment state in the new tab
        """
        self.computer_logger.push_operation("new_tab")
        try:
            # Use _context directly
            context = getattr(self, '_context', None)
            if not context:
                raise BrowserError("No browser context available")
            
            # Create new page using Playwright API
            new_page = context.new_page()
            new_page.set_viewport_size({"width": self.get_dimensions()[0], "height": self.get_dimensions()[1]})
            new_page.on("close", self._handle_page_close)
            
            # Switch to the new page
            self._page = new_page
            new_page.bring_to_front()
            
            # Navigate to URL if provided
            if url:
                normalized_url = url if url.startswith(("http://", "https://", "about:", "file:")) else "https://" + url
                new_page.goto(normalized_url, timeout=30000, wait_until="domcontentloaded")
                try:
                    new_page.wait_for_load_state("load", timeout=5000)
                except Exception:
                    self.logger.debug("Load state wait timed out, but domcontentloaded succeeded")
            
            self.computer_logger.pop_operation("new_tab", success=True)
            self.logger.info(f"Opened new tab{f' with URL: {url}' if url else ''}")
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("new_tab", success=False)
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"New tab failed: {e}") from e
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def switch_tab(self, tab_index: int) -> EnvState:
        """Switch to a specific tab by index using Playwright API (circular).
        
        Args:
            tab_index: Tab index to switch to (can be negative or >= tab_count, wraps around circularly)
        
        Returns:
            Current environment state after switching
        """
        self.computer_logger.push_operation("switch_tab")
        try:
            # Use _context directly
            context = getattr(self, '_context', None)
            if not context:
                raise BrowserError("No browser context available")
            
            # FIX: context.pages is a property, not a method
            pages = context.pages
            if not pages:
                raise BrowserError("No tabs available")
            
            # Make it circular - wrap around using modulo
            actual_index = tab_index % len(pages)
            self.logger.info(f"🔄 Switching to tab {tab_index} (wrapped to {actual_index} of {len(pages)} tabs)")
            
            # Switch using Playwright API
            self._page = pages[actual_index]
            self._page.bring_to_front()
            
            # Wait briefly for tab to be ready
            time.sleep(0.2)
            
            self.computer_logger.pop_operation("switch_tab", success=True)
            self.logger.info(f"Switched to tab {tab_index}")
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("switch_tab", success=False)
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Switch tab failed: {e}") from e
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def close_tab(self) -> EnvState:
        """Close the current browser tab using Playwright API.
        
        Returns:
            Current environment state after closing tab
        
        Note:
            Cannot close the last remaining tab - will raise an error
        """
        self.computer_logger.push_operation("close_tab")
        try:
            # Use _context directly
            context = getattr(self, '_context', None)
            if not context:
                raise BrowserError("No browser context available")
            
            # FIX: context.pages is a property, not a method
            pages = context.pages
            if len(pages) <= 1:
                raise BrowserError("Cannot close the last remaining tab")
            
            current_index = pages.index(self._page) if self._page in pages else -1
            self._page.close()
            
            # Switch to the next available tab
            # FIX: context.pages is a property, not a method
            new_pages = context.pages
            new_index = min(current_index, len(new_pages) - 1)
            self._page = new_pages[new_index]
            self._page.bring_to_front()
            
            self.computer_logger.pop_operation("close_tab", success=True)
            self.logger.info(f"Closed tab and switched to tab {new_index}")
            return self.current_state()
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("close_tab", success=False)
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Close tab failed: {e}") from e
    
    def list_tabs(self) -> dict:
        """Get information about all open tabs using Playwright API.
        
        Returns:
            Dict with tab count, current tab index, and list of tab info
        """
        try:
            # Use _context directly (set during initialization in base_playwright.py line 104)
            context = getattr(self, '_context', None)
            
            if not context:
                self.logger.warning(f"⚠️ list_tabs: No context available")
                return {"tab_count": 0, "current_tab_index": -1, "tabs": []}
            
            # FIX: context.pages is a property, not a method - don't call it with ()
            pages = context.pages  # This is already a list
            self.logger.info(f"🔍 list_tabs: Found {len(pages)} pages")
            current_index = pages.index(self._page) if self._page in pages else -1
            
            tab_info = {
                "tab_count": len(pages),
                "current_tab_index": current_index,
                "tabs": []
            }
            
            for i, page in enumerate(pages):
                try:
                    url = page.url
                    is_current = (i == current_index)
                    tab_info["tabs"].append({
                        "index": i,
                        "url": url,
                        "is_current": is_current
                    })
                except Exception as e:
                    self.logger.warning(f"Could not get info for tab {i}: {e}")
                    tab_info["tabs"].append({
                        "index": i,
                        "url": "unknown",
                        "is_current": (i == current_index)
                    })
            
            return tab_info
        except Exception as e:
            self.logger.error(f"Failed to list tabs: {e}")
            return {"tab_count": 0, "current_tab_index": -1, "tabs": []}
    
    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def current_state(self) -> EnvState:
        """Capture current browser state following Google's best practices."""
        self.computer_logger.push_operation("current_state")
        # Check if page is still valid before proceeding
        if not self._page or self._page.is_closed():
            self.logger.warning("⚠️ Page is closed or invalid - returning error state")
            self.computer_logger.pop_operation("current_state", success=False)
            raise BrowserError("Page is closed or invalid")
        
        try:
            # Wait for page to be loaded
            self._page.wait_for_load_state()
            # Even if Playwright reports loaded, add manual sleep for rendering
            time.sleep(0.5)
            
            screenshot_bytes = self._page.screenshot(type='png', full_page=False)
            url = self._page.url
            timestamp = datetime.now().isoformat()
            
            self.computer_logger.pop_operation("current_state", success=True)
            return EnvState(
                screenshot=screenshot_bytes,
                url=url,
                timestamp=timestamp
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.computer_logger.pop_operation("current_state", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            self.logger.error(f"Error in current_state: {e}")
            # Instead of returning empty state, raise the error so the agent can handle it
            raise BrowserError(f"Failed to capture current state: {e}")
