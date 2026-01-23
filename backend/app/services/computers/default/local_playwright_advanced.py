from playwright.sync_api import Browser, Page
from app.services.computers.shared.base_playwright_advanced import BasePlaywrightComputer
from app.core.config import settings


class LocalPlaywrightBrowserAdvanced(BasePlaywrightComputer):
    """Launches a local Chromium instance using Playwright (advanced) with optional logger support."""

    def __init__(self, headless: bool = None, logger_instance=None):
        # Pass logger_instance up to the base class
        super().__init__()
        self.logger = logger_instance

        # Headless handling logic
        if headless is None:
            import os
            is_docker = not os.environ.get('DISPLAY') or os.environ.get('DOCKER_CONTAINER', '').lower() == 'true'
            if is_docker:
                self.headless = True  # Force headless in Docker
            else:
                self.headless = not settings.DEBUG
        else:
            self.headless = headless

    def _get_browser_and_page(self) -> tuple[Browser, Page]:
        """Initialize browser and page with advanced arguments and event handling."""
        width, height = self.get_dimensions()
        # Firefox-compatible launch arguments
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-background-timer-throttling",
            "--disable-blink-features=AutomationControlled",
            "--disable-logging",
            "--silent",
            "--disable-crash-reporter",
            "--disable-hang-monitor",
        ]

        browser = self._playwright.firefox.launch(
            headless=self.headless,
            args=launch_args,
        )

        context = browser.new_context()
        context.on("page", self._handle_new_page)

        page = context.new_page()
        page.set_viewport_size({"width": width, "height": height})
        page.on("close", self._handle_page_close)

        # Capture browser console output for debugging
        page.on("console", lambda msg: self.logger.info(f"🖥️  BROWSER CONSOLE [{msg.type}]: {msg.text}") if self.logger else print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: self.logger.error(f"🌋 BROWSER ERROR: {err}") if self.logger else print(f"BROWSER ERROR: {err}"))

        # Open a neutral base URL (for warm-up)
        page.goto("https://bing.com")

        return browser, page

    def _handle_new_page(self, page: Page):
        """Handle the creation of a new page."""
        if self.logger:
            self.logger.info("🆕 New page created (Advanced)")
        else:
            print("New page created")
        self._page = page
        page.on("close", self._handle_page_close)
        # Add console listeners to new pages
        page.on("console", lambda msg: self.logger.info(f"🖥️  BROWSER CONSOLE [{msg.type}]: {msg.text}") if self.logger else print(f"BROWSER CONSOLE [{msg.type}]: {msg.text}"))
        page.on("pageerror", lambda err: self.logger.error(f"🌋 BROWSER ERROR: {err}") if self.logger else print(f"BROWSER ERROR: {err}"))

    def _handle_page_close(self, page: Page):
        """Handle the closure of a page."""
        if self.logger:
            self.logger.info("📕 Page closed (Advanced)")
        else:
            print("Page closed")

        if self._page == page:
            if self._browser.contexts and self._browser.contexts[0].pages:
                self._page = self._browser.contexts[0].pages[-1]
            else:
                msg = "Warning: All pages have been closed."
                if self.logger:
                    self.logger.warning(msg)
                else:
                    print(msg)
                self._page = None