import time
import os
import base64
import logging
import re
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from celery.exceptions import SoftTimeLimitExceeded
from app.services.openai_cua_common.env_utils import get_int_env
from app.services.computers.utils import check_blocklisted_url
from app.services.computers.error_handling import retry_with_backoff, CriticalTimeoutError

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


def _escape_css_identifier(identifier: str) -> str:
    """Escape invalid characters in CSS identifiers for Playwright selectors."""
    return re.sub(r"([^\w-])", lambda m: "\\" + m.group(1), identifier)


class BasePlaywrightComputer:
    """
    Abstract base for Playwright-based computers:

      - Subclasses override `_get_browser_and_page()` to do local or remote connection,
        returning (Browser, Page).
      - This base class handles context creation (`__enter__`/`__exit__`),
        plus standard "Computer" actions like click, scroll, etc.
      - We also have extra browser actions: `goto(url)` and `back()`.
    """

    def get_environment(self):
        return "browser"

    def get_dimensions(self):
        return (1024, 768)

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None
        self._action_timeout_ms = get_int_env("CUA_ACTION_TIMEOUT_MS", 10_000)
        self._navigation_timeout_ms = get_int_env("CUA_NAVIGATION_TIMEOUT_MS", 15_000)
        self._log = logging.getLogger(self.__class__.__name__)
        self._last_action_details: dict[str, Optional[str]] = {}

    def inspect_point(self, x: int, y: int) -> Dict[str, Optional[str]]:
        script = """
            ([x, y]) => {
                const el = document.elementFromPoint(x, y);
                if (!el) return {};
                const info = {
                    tag: el.tagName ? el.tagName.toLowerCase() : null,
                    id: el.id || null,
                    classes: el.className || null,
                    role: el.getAttribute('role') || null,
                    type: el.getAttribute('type') || null,
                    href: el.getAttribute('href') || null,
                    text: (el.innerText || el.getAttribute('value') || '').trim().slice(0, 120)
                };
                const anchor = el.closest('a');
                if (anchor && anchor.getAttribute('href')) {
                    info.href = anchor.getAttribute('href');
                    info.tag = anchor.tagName.toLowerCase();
                }
                return info;
            }
        """
        try:
            return self._page.evaluate(script, (x, y)) or {}
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            self._log.debug("inspect_point failed at (%s, %s): %s", x, y, exc)
            return {}

    def __enter__(self):
        try:
            # Start Playwright and call the subclass hook for getting browser/page
            self._playwright = sync_playwright().start()
            self._browser, self._page = self._get_browser_and_page()

            # Set default timeouts so Playwright fails fast instead of hanging.
            context = self._page.context
            context.set_default_timeout(self._action_timeout_ms)
            context.set_default_navigation_timeout(self._navigation_timeout_ms)
            self._page.set_default_timeout(self._action_timeout_ms)
            self._page.set_default_navigation_timeout(self._navigation_timeout_ms)

            # Set up network interception to flag URLs matching domains in BLOCKED_DOMAINS
            def handle_route(route, request):
                url = request.url
                if check_blocklisted_url(url):
                    print(f"Flagging blocked domain: {url}")
                    route.abort()
                else:
                    route.continue_()

            self._page.route("**/*", handle_route)

            return self
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self._log.error("Error during browser initialization: %s", e)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def get_current_url(self) -> str:
        return self._page.url

    # --- Common "Computer" actions ---
    @retry_with_backoff(max_retries=3, base_delay=0.5, exceptions=(PlaywrightTimeoutError, Exception))
    def screenshot(self) -> str:
        """Capture only the viewport (not full_page)."""
        timeout_ms = get_int_env("CUA_SCREENSHOT_TIMEOUT_MS", 15_000)  # 15 second timeout
        try:
            png_bytes = self._page.screenshot(full_page=False, timeout=timeout_ms)
        except SoftTimeLimitExceeded:
            raise
        except PlaywrightTimeoutError as exc:
            print(f"🚨 CRITICAL: Page load timeout: Function screenshot timed out after {timeout_ms/1000:.1f} seconds")
            # Import here to avoid circular imports
            from app.services.computers.error_handling import CriticalTimeoutError
            raise CriticalTimeoutError(f"CRITICAL: Screenshot timed out after {timeout_ms/1000:.1f} seconds - task should crash immediately") from exc
        except Exception as exc:
            print(f"🚨 CRITICAL: Screenshot failed: {exc}")
            from app.services.computers.error_handling import CriticalTimeoutError
            raise CriticalTimeoutError(f"CRITICAL: Screenshot failed: {exc} - task should crash immediately") from exc
        
        self._last_action_details = {
            "action": "screenshot",
            "severity": "info",
        }
        return base64.b64encode(png_bytes).decode("utf-8")

    def _fallback_screenshot(self) -> bytes:
        """Use CDP captureScreenshot as a fallback when standard screenshot times out."""
        try:
            cdp = self._page.context.new_cdp_session(self._page)
            result = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            data = result.get("data")
            if not data:
                raise RuntimeError("CDP captureScreenshot returned no data")
            return base64.b64decode(data)
        except SoftTimeLimitExceeded:
            raise
        except Exception as fallback_exc:  # pylint: disable=broad-except
            print(f"Fallback screenshot capture failed: {fallback_exc}")
            raise

    def click(self, x: int, y: int, button: str = "left", retries: int = 3, delay: float = 0.5) -> None:
        """
        Vision-aligned click:
        - Always click at coordinates (what the agent saw in screenshot).
        - Inspect element for metadata only.
        - Ensure element is scrolled into view before clicking.
        """
        button_type = {"left": "left", "right": "right"}.get(button, "left")
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                el_info = self.inspect_point(x, y)
                self._log.debug("Element at (%s,%s): %s", x, y, el_info)

                # move first to avoid 'element not interactable'
                self._page.mouse.move(x, y)
                self._with_timing(
                    f"mouse.click({x},{y})",
                    self._page.mouse.click,
                    x, y,
                    button=button_type,
                )

                self._last_action_details = {
                    "action": "click",
                    "x": x, "y": y,
                    "element_info": el_info,
                    "severity": "info",
                }
                self._log.info("✅ Click succeeded at (%s,%s)", x, y)
                return
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                last_error = exc
                self._log.warning("❌ Click failed attempt %d/%d: %s", attempt, retries, exc)
                time.sleep(delay)

        self._last_action_details = {
            "action": "click",
            "x": x, "y": y,
            "severity": "error",
            "error": str(last_error),
        }
        self._log.error("🚨 Giving up click at (%s,%s). Last error: %s", x, y, last_error)
    
    def double_click(self, x: int, y: int) -> None:
        try:
            self._with_timing(
                f"mouse.dblclick({x}, {y})",
                self._page.mouse.dblclick,
                x,
                y,
            )
        except SoftTimeLimitExceeded:
            raise

    def triple_click(self, x: int, y: int) -> None:
        try:
            self._with_timing(
                f"mouse.click({x}, {y}, click_count=3)",
                self._page.mouse.click,
                x,
                y,
                click_count=3,
            )
        except SoftTimeLimitExceeded:
            raise

    def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        try:
            self._with_timing("mouse.move", self._page.mouse.move, x, y)
            self._with_timing(
                f"window.scrollBy({scroll_x}, {scroll_y})",
                self._page.evaluate,
                f"window.scrollBy({scroll_x}, {scroll_y})",
            )
        except SoftTimeLimitExceeded:
            raise

    def type(self, text: str, retries: int = 2, delay: float = 0.3) -> None:
        """
        Robust typing:
        - Ensure active element is focused.
        - Type slowly to mimic real input.
        - Retry if keystrokes are lost.
        """
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                # Make sure something is focused
                self._page.evaluate("el => el && el.focus()", self._page.evaluate_handle("document.activeElement"))

                for ch in text:
                    self._with_timing("keyboard.type", self._page.keyboard.type, ch, delay=0.05)

                self._last_action_details = {"action": "type", "text": text, "severity": "info"}
                self._log.info("⌨️ Typed text: %s", text)
                return
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                last_error = exc
                self._log.warning("❌ Typing failed attempt %d/%d: %s", attempt, retries, exc)
                time.sleep(delay)

        self._last_action_details = {"action": "type", "text": text, "severity": "error", "error": str(last_error)}
        self._log.error("🚨 Giving up typing '%s'. Last error: %s", text, last_error)

    def wait(self, ms: int = 1000) -> None:
        time.sleep(ms / 1000)

    def move(self, x: int, y: int) -> None:
        try:
            self._with_timing("mouse.move", self._page.mouse.move, x, y)
        except SoftTimeLimitExceeded:
            raise

    def keypress(self, keys: List[str]) -> None:
        try:
            mapped_keys = [CUA_KEY_TO_PLAYWRIGHT_KEY.get(key.lower(), key) for key in keys]
            for key in mapped_keys:
                self._with_timing("keyboard.down", self._page.keyboard.down, key)
            for key in reversed(mapped_keys):
                self._with_timing("keyboard.up", self._page.keyboard.up, key)
        except SoftTimeLimitExceeded:
            raise

    def drag(self, path: List[Dict[str, int]]) -> None:
        if not path:
            return
        try:
            self._with_timing("mouse.move", self._page.mouse.move, path[0]["x"], path[0]["y"])
            self._with_timing("mouse.down", self._page.mouse.down)
            for point in path[1:]:
                self._with_timing("mouse.move", self._page.mouse.move, point["x"], point["y"])
            self._with_timing("mouse.up", self._page.mouse.up)
        except SoftTimeLimitExceeded:
            raise

    # --- Extra browser-oriented actions ---
    def goto(self, url: str) -> None:
        try:
            return self._with_timing(
                f"page.goto({url})",
                self._page.goto,
                url,
                timeout=self._navigation_timeout_ms,
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self._log.error("Error navigating to %s: %s", url, e)
            raise

    def back(self) -> None:
        try:
            return self._with_timing(
                "page.go_back",
                self._page.go_back,
                timeout=self._navigation_timeout_ms,
            )
        except SoftTimeLimitExceeded:
            raise

    def forward(self) -> None:
        try:
            return self._with_timing(
                "page.go_forward",
                self._page.go_forward,
                timeout=self._navigation_timeout_ms,
            )
        except SoftTimeLimitExceeded:
            raise

    def get_page_content(self) -> str:
        try:
            return self._with_timing("page.content", self._page.content)
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Error getting page content: {exc}")
            return ""

    # --- Subclass hook ---
    def _get_browser_and_page(self) -> tuple[Browser, Page]:
        """Subclasses must implement, returning (Browser, Page)."""
        raise NotImplementedError

    def _with_timing(self, label: str, func, *args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
        except PlaywrightTimeoutError:
            timeout_ms = kwargs.get("timeout", self._action_timeout_ms)
            self._log.error("Playwright action %s timed out after %dms", label, timeout_ms)
            raise
        except SoftTimeLimitExceeded:
            raise
        except Exception:
            self._log.exception("Playwright action %s failed", label)
            raise
        elapsed_ms = (time.time() - start) * 1000
        slow_threshold = get_int_env("CUA_LOG_SLOW_ACTION_MS", 10_000)
        if elapsed_ms >= slow_threshold:
            self._log.warning(
                "Playwright action %s took %.1fms (>= %dms)", label, elapsed_ms, slow_threshold
            )
        else:
            self._log.debug("Playwright action %s completed in %.1fms", label, elapsed_ms)
        return result