import base64
import logging
import time
from typing import Any, Dict, List, Optional

from celery.exceptions import SoftTimeLimitExceeded
from playwright.sync_api import Browser, Page, sync_playwright

from app.services.computers.utils import check_blocklisted_url
from app.services.computers.error_handling import (
    retry_with_backoff, with_timeout, safe_execute, 
    BrowserError, NavigationError, ScreenshotError, TimeoutError, CriticalTimeoutError,
    HealthChecker
)
from app.services.computers.resource_manager import BrowserResourceManager
from app.services.computers.monitoring import PerformanceMonitor, HealthMonitor, ComputerLogger

# Optional: key mapping if your model uses "CUA" style keys
CUA_KEY_TO_PLAYWRIGHT_KEY = {
    "/": "Divide",
    "\\": "Backslash",
    "alt": "Alt",
    "arrowdown": "ArrowDown",
    "arrowleft": "ArrowLeft",
    "arrowright": "ArrowRight",
    "arrowup": "ArrowUp",
    "backspace": "Backspace",
    "capslock": "CapsLock",
    "cmd": "Meta",
    "ctrl": "Control",
    "delete": "Delete",
    "end": "End",
    "enter": "Enter",
    "return": "Enter",
    "esc": "Escape",
    "home": "Home",
    "insert": "Insert",
    "option": "Alt",
    "pagedown": "PageDown",
    "pageup": "PageUp",
    "shift": "Shift",
    "space": " ",
    "super": "Meta",
    "tab": "Tab",
    "win": "Meta",
}


class BasePlaywrightComputer:
    """
    Enhanced abstract base for Playwright-based computers with comprehensive error handling,
    resource management, monitoring, and fail-proof operations.

      - Subclasses override `_get_browser_and_page()` to do local or remote connection,
        returning (Browser, Page).
      - This base class handles context creation (`__enter__`/`__exit__`),
        plus standard "Computer" actions like click, scroll, etc.
      - We also have extra browser actions: `goto(url)` and `back()`.
      - Includes comprehensive error handling, retry mechanisms, and monitoring.
    """

    def get_environment(self):
        return "browser"

    def get_dimensions(self):
        return (1280, 800)

    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._context = None
        
        # Enhanced logging and monitoring
        self.logger = logger_instance or logging.getLogger(self.__class__.__name__)
        self.computer_logger = ComputerLogger(self.__class__.__name__, self.logger)
        self.performance_monitor = PerformanceMonitor(logger_instance=self.logger)
        self.health_monitor = HealthMonitor(logger_instance=self.logger)
        self.health_checker = HealthChecker(self.logger)
        self.resource_manager = BrowserResourceManager(self.logger)
        
        # State tracking
        self._is_initialized = False
        self._is_healthy = False
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds

    @retry_with_backoff(max_retries=3, base_delay=1.0, exceptions=(Exception,))
    def __enter__(self):
        """Enhanced context manager entry with comprehensive error handling."""
        self.computer_logger.push_operation("initialize")
        
        try:
            # Start Playwright with error handling
            self.logger.info("Starting Playwright...")
            self._playwright = sync_playwright().start()
            
            # Get browser and page with error handling
            self.logger.info("Initializing browser and page...")
            self._browser, self._page = self._get_browser_and_page()
            
            # Extract context from browser if available
            if self._browser and hasattr(self._browser, 'contexts') and self._browser.contexts:
                self._context = self._browser.contexts[0]
            
            # Register resources for cleanup tracking
            self.resource_manager.register_browser(
                self._browser, self._context, self._page, self._playwright
            )
            
            # Set up network interception with enhanced error handling
            self._setup_network_interception()
            
            # Set up monitoring
            self.health_monitor.set_resources(self._browser, self._page, self._playwright)
            self.health_monitor.start_monitoring()
            
            # Perform initial health check
            self._perform_health_check()
            
            self._is_initialized = True
            self._is_healthy = True
            
            self.computer_logger.pop_operation("initialize", success=True)
            self.logger.info("Computer initialized successfully")
            
            return self
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("initialize", success=False)
            self.logger.error(f"Failed to initialize computer: {e}")
            # Cleanup on failure
            self._cleanup_resources()
            raise BrowserError(f"Computer initialization failed: {e}") from e

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Enhanced context manager exit with comprehensive cleanup."""
        self.computer_logger.push_operation("cleanup")
        
        try:
            self.logger.info("Starting computer cleanup...")
            
            # Stop monitoring
            self.health_monitor.stop_monitoring()
            
            # Cleanup resources
            self._cleanup_resources()
            
            self._is_initialized = False
            self._is_healthy = False
            
            self.computer_logger.pop_operation("cleanup", success=True)
            self.logger.info("Computer cleanup completed successfully")
            
        except Exception as e:
            self.computer_logger.pop_operation("cleanup", success=False)
            self.logger.error(f"Error during cleanup: {e}")
            # Don't re-raise cleanup errors

    def _setup_network_interception(self):
        """Set up network interception with enhanced error handling."""
        if not self._page:
            return
        
        def handle_route(route, request):
            url = request.url
            try:
                check_blocklisted_url(url)
                route.continue_()
            except ValueError as e:
                self.logger.warning(f"Blocked domain: {url}")
                route.abort()
            except Exception as e:
                self.logger.error(f"Error in network interception: {e}")
                route.abort()
        
        try:
            self._page.route("**/*", handle_route)
            self.logger.debug("Network interception set up successfully")
        except Exception as e:
            self.logger.warning(f"Failed to set up network interception: {e}")
    
    def _perform_health_check(self):
        """Perform a health check on all resources."""
        try:
            browser_healthy = self.health_checker.check_browser_health(self._browser)
            page_healthy = self.health_checker.check_page_health(self._page)
            playwright_healthy = self.health_checker.check_playwright_health(self._playwright)
            
            self._is_healthy = browser_healthy and page_healthy and playwright_healthy
            self._last_health_check = time.time()
            
            if not self._is_healthy:
                self.logger.warning(f"Health check failed - Browser: {browser_healthy}, Page: {page_healthy}, Playwright: {playwright_healthy}")
            else:
                self.logger.debug("Health check passed")
                
        except Exception as e:
            self.logger.error(f"Health check failed with error: {e}")
            self._is_healthy = False
    
    def _cleanup_resources(self):
        """HARSH cleanup of all resources - force termination if needed."""
        self.logger.info("🧹 Starting HARSH cleanup of sync resources...")
        
        try:
            # Force close all pages first
            if self._browser and self._browser.contexts:
                for context in self._browser.contexts:
                    try:
                        context.close()
                        self.logger.info("✅ Context closed")
                    except Exception as e:
                        self.logger.warning(f"⚠️ Error closing context: {e}")
            
            # Force close browser
            if self._browser:
                try:
                    self._browser.close()
                    self.logger.info("✅ Browser closed")
                except Exception as e:
                    self.logger.warning(f"⚠️ Error closing browser: {e}")
            
            # Force stop Playwright
            if self._playwright:
                try:
                    self._playwright.stop()
                    self.logger.info("✅ Playwright stopped")
                except Exception as e:
                    self.logger.warning(f"⚠️ Error stopping Playwright: {e}")
            
            # Clear references
            self._page = None
            self._browser = None
            self._context = None
            self._playwright = None
            
            # Force garbage collection
            import gc
            gc.collect()
            
            self.logger.info("✅ HARSH cleanup completed")
            
        except Exception as e:
            self.logger.error(f"❌ Error during harsh cleanup: {e}")
            # Force clear everything even if errors occur
            self._page = None
            self._browser = None
            self._context = None
            self._playwright = None
    
    def _ensure_healthy(self):
        """Ensure computer is healthy before operations."""
        current_time = time.time()
        if current_time - self._last_health_check > self._health_check_interval:
            self._perform_health_check()
        
        if not self._is_healthy:
            raise BrowserError("Computer is not healthy")
        
        if not self._page:
            raise BrowserError("Page is not available")
    
    def _wait_for_page_load(self, timeout: float = 10.0):
        """Wait for page to load completely."""
        if not self._page:
            return
        
        try:
            # Use "load" instead of "networkidle" - less strict, more reliable
            self._page.wait_for_load_state("load", timeout=timeout * 1000)
        except Exception as e:
            # Don't raise critical error - just log it as a warning
            # "load" is sufficient for most cases, networkidle is too strict
            self.logger.warning(f"Page load state wait timed out: {e}")
            # This is non-critical - domcontentloaded/load is usually sufficient
    
    def get_current_url(self) -> str:
        """Get current URL with error handling."""
        self._ensure_healthy()
        try:
            return self._page.url
        except Exception as e:
            raise BrowserError(f"Failed to get current URL: {e}") from e

    # --- Enhanced "Computer" actions with comprehensive error handling ---
    
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError, ScreenshotError))
    @with_timeout(timeout_seconds=20.0, timeout_exception=ScreenshotError, critical=True)
    def screenshot(self) -> str:
        """Capture screenshot with comprehensive error handling and retry logic."""
        self._ensure_healthy()
        self.computer_logger.push_operation("screenshot")
        
        # Track consecutive screenshot failures
        if not hasattr(self, '_consecutive_screenshot_failures'):
            self._consecutive_screenshot_failures = 0
        
        # If we already have 3 consecutive failures, crash immediately
        if self._consecutive_screenshot_failures >= 3:
            from app.services.computers.error_handling import CriticalTimeoutError
            raise CriticalTimeoutError(
                f"CRITICAL: Screenshot failed {self._consecutive_screenshot_failures} consecutive times. "
                f"Task should crash immediately."
            )
        
        try:
            # Wait for page to be ready with shorter timeout
            self._wait_for_page_load(timeout=15.0)
            
            # Take screenshot with explicit timeout - this is the key fix!
            png_bytes = self._page.screenshot(full_page=False, timeout=15000)  # 15 second timeout
            if not png_bytes:
                raise ScreenshotError("Screenshot returned empty data")
            
            result = base64.b64encode(png_bytes).decode("utf-8")
            self.computer_logger.pop_operation("screenshot", success=True)
            
            # Reset consecutive failure count on success
            self._consecutive_screenshot_failures = 0
            
            return result
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("screenshot", success=False)
            
            # Increment consecutive failure count
            self._consecutive_screenshot_failures += 1
            
            # If we have 3 consecutive failures, raise CriticalTimeoutError
            if self._consecutive_screenshot_failures >= 3:
                from app.services.computers.error_handling import CriticalTimeoutError
                raise CriticalTimeoutError(
                    f"CRITICAL: Screenshot failed {self._consecutive_screenshot_failures} consecutive times. "
                    f"Task should crash immediately. Last error: {e}"
                ) from e
            
            raise ScreenshotError(f"Screenshot failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def click(self, x: int, y: int, button: str = "left") -> None:
        """Enhanced click with error handling and validation."""
        self._ensure_healthy()
        self.computer_logger.push_operation(f"click_{button}")
        
        try:
            match button:
                case "back":
                    self.back()
                case "forward":
                    self.forward()
                case "wheel":
                    self._page.mouse.wheel(x, y)
                case _:
                    button_mapping = {"left": "left", "right": "right"}
                    button_type = button_mapping.get(button, "left")
                    self._page.mouse.click(x, y, button=button_type)
            
            # Wait for any resulting page changes
            time.sleep(0.1)
            self.computer_logger.pop_operation(f"click_{button}", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation(f"click_{button}", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Click failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def double_click(self, x: int, y: int) -> None:
        """Enhanced double click with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("double_click")
        
        try:
            self._page.mouse.dblclick(x, y)
            time.sleep(0.1)  # Wait for any resulting changes
            self.computer_logger.pop_operation("double_click", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("double_click", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Double click failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def triple_click(self, x: int, y: int) -> None:
        """Enhanced triple click with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("triple_click")
        
        try:
            self._page.mouse.click(x, y, click_count=3)
            time.sleep(0.1)  # Wait for any resulting changes
            self.computer_logger.pop_operation("triple_click", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("triple_click", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Triple click failed: {e}") from e

    @retry_with_backoff(max_retries=2, base_delay=0.3, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        """Enhanced scroll with error handling - scrolls at specific coordinates using mouse.wheel()."""
        self._ensure_healthy()
        self.computer_logger.push_operation("scroll")
        
        try:
            # Move mouse to the target position first
            self._page.mouse.move(x, y)
            # Use mouse.wheel() to scroll at the mouse position (not window.scrollBy)
            # This ensures scrolling happens at the specific coordinate, matching OpenAI's expected behavior
            self._page.mouse.wheel(scroll_x, scroll_y)
            time.sleep(0.2)  # Wait for scroll animation to complete (increased from 0.1)
            self.computer_logger.pop_operation("scroll", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("scroll", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Scroll failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=300.0, timeout_exception=BrowserError, critical=True)
    def type(self, text: str) -> None:
        """Enhanced typing with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("type")
        
        try:
            if not text:
                return
            
            # Enhanced approach: Use keyboard.type() as first preference for reliability
            # The @with_timeout decorator will handle the 45-second timeout
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
                                activeElement.value = {repr(text)};
                                activeElement.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }})()
                    """)
            
            time.sleep(0.1)  # Wait for typing to complete
            self.computer_logger.pop_operation("type", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("type", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Typing failed: {e}") from e

    def wait(self, ms: int = 1000) -> None:
        """Enhanced wait with validation."""
        if ms < 0:
            self.logger.warning(f"Invalid wait time: {ms}ms, using 0ms")
            ms = 0
        
        if ms > 30000:  # Cap at 30 seconds
            self.logger.warning(f"Wait time too long: {ms}ms, capping at 30000ms")
            ms = 30000
        
        time.sleep(ms / 1000)

    @retry_with_backoff(max_retries=2, base_delay=0.3, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def move(self, x: int, y: int) -> None:
        """Enhanced mouse move with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("move")
        
        try:
            self._page.mouse.move(x, y)
            self.computer_logger.pop_operation("move", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("move", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Mouse move failed: {e}") from e

    @retry_with_backoff(max_retries=2, base_delay=0.3, exceptions=(BrowserError,))
    @with_timeout(timeout_seconds=15.0, timeout_exception=BrowserError, critical=True)
    def keypress(self, keys: List[str]) -> None:
        """Enhanced keypress with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("keypress")
        
        try:
            if not keys:
                return
            
            mapped_keys = [CUA_KEY_TO_PLAYWRIGHT_KEY.get(key.lower(), key) for key in keys]
            
            # Press keys down
            for key in mapped_keys:
                self._page.keyboard.down(key)
            
            # Release keys in reverse order
            for key in reversed(mapped_keys):
                self._page.keyboard.up(key)
            
            time.sleep(0.1)  # Wait for keypress to complete
            self.computer_logger.pop_operation("keypress", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("keypress", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Keypress failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def drag(self, path: List[Dict[str, int]]) -> None:
        """Enhanced drag with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("drag")
        
        try:
            if not path:
                self.logger.warning("Empty drag path provided")
                return
            
            if len(path) < 2:
                self.logger.warning("Drag path must have at least 2 points")
                return
            
            # Move to start position
            self._page.mouse.move(path[0]["x"], path[0]["y"])
            self._page.mouse.down()
            
            # Drag through path
            for point in path[1:]:
                self._page.mouse.move(point["x"], point["y"])
                time.sleep(0.01)  # Small delay between moves
            
            # Release mouse
            self._page.mouse.up()
            time.sleep(0.1)  # Wait for drag to complete
            self.computer_logger.pop_operation("drag", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("drag", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Drag failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def mouse_down(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> None:
        """Enhanced mouse down with error handling.
        
        Args:
            x: X coordinate (optional). If None, presses mouse at current position.
            y: Y coordinate (optional). If None, presses mouse at current position.
            button: Mouse button to press ("left", "right", or "middle").
        """
        self._ensure_healthy()
        self.computer_logger.push_operation(f"mouse_down_{button}")
        
        try:
            # If coordinates are provided, move mouse to position first
            if x is not None and y is not None:
                self._page.mouse.move(x, y)
            
            # Press mouse button down (at current position if no coordinates provided)
            button_mapping = {"left": "left", "right": "right", "middle": "middle"}
            button_type = button_mapping.get(button, "left")
            self._page.mouse.down(button=button_type)
            time.sleep(0.1)  # Wait briefly
            self.computer_logger.pop_operation(f"mouse_down_{button}", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation(f"mouse_down_{button}", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Mouse down failed: {e}") from e

    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(BrowserError,), critical=True)
    @with_timeout(timeout_seconds=10.0, timeout_exception=BrowserError, critical=True)
    def mouse_up(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> None:
        """Enhanced mouse up with error handling.
        
        Args:
            x: X coordinate (optional). If None, releases mouse at current position.
            y: Y coordinate (optional). If None, releases mouse at current position.
            button: Mouse button to release ("left", "right", or "middle").
        """
        self._ensure_healthy()
        self.computer_logger.push_operation(f"mouse_up_{button}")
        
        try:
            # If coordinates are provided, move mouse to position first
            if x is not None and y is not None:
                self._page.mouse.move(x, y)
            
            # Release mouse button (at current position if no coordinates provided)
            button_mapping = {"left": "left", "right": "right", "middle": "middle"}
            button_type = button_mapping.get(button, "left")
            self._page.mouse.up(button=button_type)
            time.sleep(0.1)  # Wait briefly
            self.computer_logger.pop_operation(f"mouse_up_{button}", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation(f"mouse_up_{button}", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise BrowserError(f"Mouse up failed: {e}") from e

    # --- Enhanced browser-oriented actions ---
    
    @retry_with_backoff(max_retries=3, base_delay=1.0, exceptions=(NavigationError, BrowserError))
    @with_timeout(timeout_seconds=45.0, timeout_exception=NavigationError)
    def goto(self, url: str) -> None:
        """Enhanced navigation with comprehensive error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("goto")
        
        try:
            if not url:
                raise NavigationError("URL cannot be empty")
            
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            self.logger.info(f"Navigating to: {url}")
            
            # Use domcontentloaded instead of networkidle - less strict, faster
            # Increase timeout to 30 seconds for first navigation
            response = self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
            
            if response and response.status >= 400:
                raise NavigationError(f"Navigation failed with status {response.status}")
            
            # Optional: Wait for load state (less strict than networkidle)
            # Only wait 5 seconds max - domcontentloaded is usually enough
            try:
                self._page.wait_for_load_state("load", timeout=5000)
            except Exception:
                # If load times out, that's okay - domcontentloaded is sufficient
                self.logger.debug("Load state wait timed out, but domcontentloaded succeeded")
            
            self.computer_logger.pop_operation("goto", success=True)
            self.logger.info(f"Successfully navigated to: {url}")
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("goto", success=False)
            raise NavigationError(f"Navigation to {url} failed: {e}") from e

    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(NavigationError, BrowserError))
    def back(self) -> None:
        """Enhanced back navigation with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("back")
        
        try:
            response = self._page.go_back()
            if response:
                self._wait_for_page_load(timeout=15.0)
            
            self.computer_logger.pop_operation("back", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("back", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise NavigationError(f"Back navigation failed: {e}") from e

    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(NavigationError, BrowserError))
    def forward(self) -> None:
        """Enhanced forward navigation with error handling."""
        self._ensure_healthy()
        self.computer_logger.push_operation("forward")
        
        try:
            response = self._page.go_forward()
            if response:
                self._wait_for_page_load(timeout=15.0)
            
            self.computer_logger.pop_operation("forward", success=True)
            
        except SoftTimeLimitExceeded:
            # Re-raise SoftTimeLimitExceeded to be handled by the caller
            raise
        except Exception as e:
            self.computer_logger.pop_operation("forward", success=False)
            # Don't catch CriticalTimeoutError - let it propagate for immediate crash
            from app.services.computers.error_handling import CriticalTimeoutError
            if isinstance(e, CriticalTimeoutError):
                raise
            raise NavigationError(f"Forward navigation failed: {e}") from e

    # --- Monitoring and Health Check Methods ---
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return self.performance_monitor.get_operation_stats()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status."""
        return {
            "is_healthy": self._is_healthy,
            "is_initialized": self._is_initialized,
            "last_health_check": self._last_health_check,
            "browser_healthy": self.health_checker.check_browser_health(self._browser),
            "page_healthy": self.health_checker.check_page_health(self._page),
            "playwright_healthy": self.health_checker.check_playwright_health(self._playwright),
            "resource_count": self.resource_manager.get_resource_count()
        }
    
    def force_health_check(self) -> bool:
        """Force a health check and return status."""
        self._perform_health_check()
        return self._is_healthy
    
    def get_monitoring_data(self) -> Dict[str, Any]:
        """Get comprehensive monitoring data."""
        return {
            "performance": self.get_performance_stats(),
            "health": self.get_health_status(),
            "health_history": self.health_monitor.get_health_history(5),
            "recent_operations": self.performance_monitor.get_recent_operations(10)
        }
    
    def is_ready(self) -> bool:
        """Check if computer is ready for operations."""
        return self._is_initialized and self._is_healthy and self._page is not None
    
    def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """Wait until computer is ready for operations."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_ready():
                return True
            time.sleep(0.5)
        return False

    # --- Subclass hook ---
    def _get_browser_and_page(self) -> tuple[Browser, Page]:
        """Subclasses must implement, returning (Browser, Page)."""
        raise NotImplementedError
