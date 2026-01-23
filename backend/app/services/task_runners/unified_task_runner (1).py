#!/usr/bin/env python3
"""
Unified Task Runner - Clean, robust runner for both Anthropic and OpenAI
Based on V1 OpenAI CUA Task Runner architecture but simplified and unified
"""

import base64
import json
import logging
import os
import signal
import ssl
import sys
import time
import importlib.util
import importlib.machinery
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text

from app.core.config import settings
from app.core.database_utils import get_db_session
from app.services.task_runners.task_verification import TaskVerification
from app.services.computers.error_handling import (
    CriticalTimeoutError,
    CriticalAPIError,
    with_timeout,
)
from app.services.task_runners.base.directory_manager import DirectoryManager
from app.services.verification.assertion_engine import ConfigurationError

# Import V1 components that work
from app.services.computers.error_handling import CriticalErrorTracker
from app.services.computers.default import LocalPlaywrightBrowser


VERIFIER_MODULE_NAME = "verifier_module"


class UnifiedTaskRunner:
    """
    Clean, robust unified task runner for both Anthropic and OpenAI
    Handles all model types intelligently without unnecessary complexity
    """

    def __init__(self):
        """Initialize the unified task runner"""
        # Initialize centralized directory manager
        self.directory_manager = DirectoryManager()
        self.base_results_dir = self.directory_manager.base_results_dir
        self.current_task_dir = None
        self.execution_dir = None

        # Initialize computer and agent (like V1)
        self.computer = None
        self.agent = None
        self.screenshot_count = 0

        # Initialize state tracking
        self.step_counter = {
            "execution_steps": 0,
            "verification_steps": 0,
            "total_steps": 0,
        }
        self.results = []

        # Note: Each iteration gets its own UnifiedTaskRunner instance
        # This provides natural resource isolation across Celery workers

        # Setup logging with unique identifier for parallel execution
        self.logger = logging.getLogger(__name__)
        import threading

        self.logger_name = f"{__name__}_{id(self)}_{threading.current_thread().ident}_{int(time.time() * 1000)}"
        self.logger = logging.getLogger(self.logger_name)
        self._setup_logging()

        # Log runner instance creation for parallel execution tracking
        self.logger.info(
            f"🆔 Created new UnifiedTaskRunner instance: {self.logger_name}"
        )
        self.logger.info(
            f"🧵 Running in thread: {threading.current_thread().name} (ID: {threading.current_thread().ident})"
        )

        # Initialize task verification
        self.task_verification = TaskVerification(self.logger)
        self.logger.info(f"🆔 Generated Run ID: {self.task_verification.get_run_id()}")

        # Initialize critical error tracking
        self.critical_error_tracker = CriticalErrorTracker(max_critical_errors=3)
        self.logger.info("🚨 Critical error tracking initialized (max 3 errors)")

        # Track file handlers for cleanup
        self.file_handlers = []

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        self.logger.info("✅ Unified Task Runner initialized successfully")

    # Note: No need for complex iteration resource management
    # Each iteration gets its own UnifiedTaskRunner instance with natural isolation

    def _create_isolated_computer(self, computer_class, **kwargs):
        """Create a computer instance with unique identifier for parallel execution isolation"""
        # Don't pass runner_id to computer classes that don't expect it
        # The isolation is handled by creating separate instances
        self.logger.info(
            f"🔒 Creating isolated computer instance for runner: {self.logger_name}"
        )

        # Add video directory only if task directory exists AND this is a playground execution
        is_playground = getattr(self, "_is_playground", False)
        if self.current_task_dir and "video_dir" not in kwargs and is_playground:
            kwargs["video_dir"] = str(self.current_task_dir)
            self.logger.info(
                f"🎥 Video recording enabled for playground execution: {self.current_task_dir}"
            )
        elif is_playground and not self.current_task_dir:
            self.logger.warning(
                "⚠️ Playground execution detected but task directory not yet created"
            )
        elif not is_playground:
            self.logger.info("ℹ️ Video recording disabled (not a playground execution)")

        return computer_class(**kwargs)

    def _has_running_event_loop(self) -> bool:
        """
        Check if there's a running event loop in the current thread.

        Returns:
            True if there's a running event loop, False otherwise
        """
        import asyncio

        try:
            # Try to get the running loop - if this succeeds, there's a running loop
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            # No running loop - this is the expected/ideal case
            return False
        except Exception as e:
            # Any other error - assume no loop to be safe
            self.logger.warning(f"⚠️ Event loop check failed: {e}, assuming no loop")
            return False

    def _detect_model_type(self, task: Dict[str, Any]) -> str:
        """Detect model type from task data"""
        # Check explicit model_type field first (from execution context)
        if "model_type" in task:
            model_type = task["model_type"].lower()
            self.logger.info(f"🔍 Using explicit model_type from task: {model_type}")
            return model_type

        # Check runner_type field (from execution context)
        if "runner_type" in task:
            runner_type = task["runner_type"].lower()
            self.logger.info(f"🔍 Using runner_type from task: {runner_type}")
            return runner_type

        # Check for model hints in task description
        task_desc = task.get("task_description", "").lower()
        if "anthropic" in task_desc or "claude" in task_desc:
            self.logger.info("🔍 Detected Anthropic from task description")
            return "anthropic"
        elif "openai" in task_desc or "gpt" in task_desc:
            self.logger.info("🔍 Detected OpenAI from task description")
            return "openai"
        elif "gemini" in task_desc or "google" in task_desc:
            self.logger.info("🔍 Detected Gemini from task description")
            return "gemini"

        # Check for API key availability
        # Use settings instead of os.environ to read from .env file
        anthropic_key = settings.ANTHROPIC_API_KEY
        openai_key = settings.OPENAI_API_KEY
        gemini_key = settings.GOOGLE_API_KEY or settings.GEMINI_API_KEY

        if anthropic_key and not openai_key and not gemini_key:
            self.logger.info("🔍 Only Anthropic API key available")
            return "anthropic"
        elif openai_key and not anthropic_key and not gemini_key:
            self.logger.info("🔍 Only OpenAI API key available")
            return "openai"
        elif gemini_key and not anthropic_key and not openai_key:
            self.logger.info("🔍 Only Gemini API key available")
            return "gemini"
        elif anthropic_key and openai_key:
            # Both available, default to openai for now
            self.logger.info("🔍 Both API keys available, defaulting to OpenAI")
            return "openai"
        else:
            # No API keys, default to openai
            self.logger.info("🔍 No API keys available, defaulting to OpenAI")
            return "openai"

    def _setup_logging(self):
        """Setup basic logging for the runner"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler()],
        )
        self.logger.info("📝 Basic logging setup complete")

    def _setup_signal_handlers(self):
        """Setup signal handlers to ensure computer cleanup on unexpected termination"""

        def signal_handler(signum, frame):
            self.logger.info(
                f"🛑 Received signal {signum}, cleaning up computer resources..."
            )
            try:
                self.cleanup_computer()
            except Exception as e:
                self.logger.error(f"❌ Error during signal-based cleanup: {e}")
            sys.exit(1)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, signal_handler)
            self.logger.info(
                "🛡️ Signal handlers registered for graceful computer cleanup"
            )
        except ValueError as e:
            if "signal only works in main thread" in str(e):
                self.logger.info("🛡️ Signal handlers skipped (not in main thread)")
            else:
                raise

    def create_execution_directory(self, execution_type: str = "single_task") -> Path:
        """Create execution-level directory structure for consolidated results"""
        self.execution_dir = self.directory_manager.create_execution_directory()
        return self.execution_dir

    def create_task_directory(
        self, task_id: str = None, iteration: int = 1, model_type: str = "openai"
    ) -> Path:
        """Create a new task directory with organized subdirectories"""
        if not task_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_id = f"task_{timestamp}"

        # Use centralized directory manager
        self.directory_manager.set_execution_directory(self.execution_dir)
        iteration_dir = self.directory_manager.create_task_directory(task_id, iteration)

        # Update local references
        self.current_task_dir = iteration_dir
        self.results_dir = iteration_dir

        # Setup logging for this task
        self._setup_task_logging()

        # ✅ Initialize action_timeline.json file (SINGLE SOURCE OF TRUTH for all models)
        self._initialize_action_timeline_file(iteration_dir)

        self.logger.info(f"📁 Created isolated task directory: {iteration_dir}")
        import threading

        self.logger.info(
            f"🆔 Runner instance: {self.logger_name} - Thread: {threading.current_thread().ident}"
        )

        # Update agent screenshot directory if agent exists
        if self.agent:
            # Update screenshot directory for independent agents
            if hasattr(self.agent, "screenshot_dir"):
                self.logger.info(
                    f"🔧 Updating agent screenshot directory to: {iteration_dir / 'screenshots'}"
                )
                self.agent.screenshot_dir = str(iteration_dir / "screenshots")

            # Update task directory for independent agents
            if hasattr(self.agent, "task_dir"):
                self.logger.info(f"🔧 Updating agent task_dir to: {iteration_dir}")
                self.agent.task_dir = str(iteration_dir)

            # Update screenshot helper if it exists, or create it if it doesn't
            if hasattr(self.agent, "screenshot_helper"):
                if self.agent.screenshot_helper:
                    self.logger.info(
                        f"🔧 Updating screenshot helper directory to: {iteration_dir / 'screenshots'}"
                    )
                    self.agent.screenshot_helper.screenshot_dir = str(
                        iteration_dir / "screenshots"
                    )
                else:
                    # Initialize screenshot helper if it doesn't exist
                    from .helpers.screenshot_helper import ScreenshotHelper

                    self.logger.info(
                        f"🔧 Initializing screenshot helper with directory: {iteration_dir / 'screenshots'}"
                    )
                    self.agent.screenshot_helper = ScreenshotHelper(
                        str(iteration_dir / "screenshots"), self.logger
                    )

            # For Gemini agent, also update the inner OptimizedGeminiAgent
            if hasattr(self.agent, "optimized_agent"):
                self.logger.info(
                    f"🔧 Updating Gemini OptimizedGeminiAgent screenshot directory"
                )
                self.agent.optimized_agent.screenshot_dir = str(
                    iteration_dir / "screenshots"
                )

                # Update or create screenshot helper for OptimizedGeminiAgent
                if not self.agent.optimized_agent.screenshot_helper:
                    from .helpers.screenshot_helper import ScreenshotHelper

                    self.logger.info(
                        f"🔧 Initializing OptimizedGeminiAgent screenshot helper"
                    )
                    self.agent.optimized_agent.screenshot_helper = ScreenshotHelper(
                        str(iteration_dir / "screenshots"), self.logger
                    )
                else:
                    self.agent.optimized_agent.screenshot_helper.screenshot_dir = str(
                        iteration_dir / "screenshots"
                    )
        else:
            self.logger.warning("⚠️ No agent exists to update screenshot directory")

        return iteration_dir

    def _setup_task_logging(self):
        """Setup comprehensive logging for current task"""
        if not self.current_task_dir:
            raise ValueError(
                "Task directory not created. Call create_task_directory() first."
            )

        # Ensure the directory structure exists even if initial creation failed midway
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = self.current_task_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Use centralized directory manager for log path
        log_file = self.directory_manager.get_log_path("unified")
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Clear any existing file handlers to prevent accumulation
        # self._cleanup_file_handlers()

        # Create a file handler for this task
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Create a formatter
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)

        # Add the file handler to the logger and track it
        self.logger.addHandler(file_handler)
        self.file_handlers.append(file_handler)

        self.logger.info(f"📝 Task logging setup complete: {log_file}")

    def _cleanup_file_handlers(self):
        """Clean up file handlers to prevent log mixing and memory leaks"""
        try:
            for handler in self.file_handlers:
                if handler in self.logger.handlers:
                    self.logger.removeHandler(handler)
                handler.close()
            self.file_handlers.clear()
            self.logger.info("🧹 File handlers cleaned up successfully")
        except Exception as e:
            self.logger.warning(f"⚠️ Error cleaning up file handlers: {e}")

    def _take_screenshot(self, step_name: str, task_id: str) -> str:
        """Capture screenshot and save to iteration directory"""
        if not self.current_task_dir:
            self.logger.warning("⚠️ No iteration directory available for screenshot")
            return None

        # Ensure screenshot directory exists (iteration creation may have been interrupted)
        self.current_task_dir.mkdir(parents=True, exist_ok=True)
        screenshot_dir = self.current_task_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Use centralized directory manager for screenshot path
        screenshot_path = self.directory_manager.get_screenshot_path(step_name, task_id)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"📸 Taking screenshot: {screenshot_path.name}")

        try:
            time.sleep(1)  # Wait for page to stabilize

            if not self.computer:
                self.logger.error("❌ Computer not initialized for screenshot")
                return None

            # Take screenshot using computer - let the decorators handle timeout and retry
            screenshot_data = self.computer.screenshot()

            if not screenshot_data:
                self.logger.warning(f"⚠️ No screenshot data returned for {step_name}")
                return None

            # Handle different screenshot data formats
            if isinstance(screenshot_data, str) and os.path.exists(screenshot_data):
                import shutil

                shutil.copy2(screenshot_data, screenshot_path)
            elif isinstance(screenshot_data, bytes):
                with open(screenshot_path, "wb") as f:
                    f.write(screenshot_data)
            elif isinstance(screenshot_data, str):
                if screenshot_data.startswith("data:image/"):
                    base64_data = screenshot_data.split(",")[1]
                else:
                    base64_data = screenshot_data

                image_data = base64.b64decode(base64_data)
                with open(screenshot_path, "wb") as f:
                    f.write(image_data)
            else:
                self.logger.warning(
                    f"⚠️ Unknown screenshot data format: {type(screenshot_data)}"
                )
                return None

            self.screenshot_count += 1
            self.logger.info(f"📸 Screenshot captured: {screenshot_path.name}")
            return str(screenshot_path)

        except Exception as e:
            self.logger.error(f"❌ Failed to capture screenshot for {step_name}: {e}")
            return None

    def _initialize_playwright_directly(self):
        """Initialize enhanced Playwright with comprehensive error handling"""
        import threading

        current_thread = threading.current_thread()
        self.logger.info(
            f"🧵 Initializing enhanced Playwright in thread: {current_thread.name} (ID: {current_thread.ident})"
        )
        self.logger.info(
            f"🆔 Runner instance: {self.logger_name} - Creating isolated Playwright browser"
        )

        # Check for environment variable to force sync mode
        force_sync = os.environ.get("FORCE_SYNC_PLAYWRIGHT", "").lower() in (
            "true",
            "1",
            "yes",
        )
        if force_sync:
            self.logger.info(
                "🔧 FORCE_SYNC_PLAYWRIGHT environment variable detected, using sync mode"
            )
            self._initialize_sync_playwright()
            return

        # CRITICAL FIX: Check for running event loop BEFORE attempting Playwright initialization
        # If a loop exists, run Playwright in a separate thread without an event loop
        if self._has_running_event_loop():
            self.logger.warning(
                "⚠️ Detected running event loop - initializing Playwright in isolated thread without event loop"
            )
            self._initialize_playwright_in_isolated_thread()
            return

        # Use sync Playwright for Celery compatibility (no event loop issues)
        self.logger.info("🎭 Using LocalPlaywrightBrowser for Celery compatibility...")

        try:
            # Create computer with unique identifier for parallel execution isolation
            # Video directory will be added by _create_isolated_computer if current_task_dir exists
            self.computer = self._create_isolated_computer(
                LocalPlaywrightBrowser, headless=True, logger_instance=self.logger
            )

            self.logger.info("🚀 Starting enhanced sync Playwright browser...")

            # Use sync context manager for LocalPlaywrightBrowser
            self.computer.__enter__()

            self.logger.info(
                "✅ Enhanced sync Playwright browser initialized successfully"
            )

            if hasattr(self.computer, "wait_until_ready"):
                try:
                    ready = self.computer.wait_until_ready(timeout=15.0)
                    if ready:
                        self.logger.info("✅ Computer is ready for operations")
                    else:
                        self.logger.warning(
                            "⚠️ Computer ready check timed out, but continuing anyway"
                        )
                        if hasattr(self.computer, "_page") and self.computer._page:
                            self.logger.info(
                                "✅ Page is available, proceeding despite health check timeout"
                            )
                        else:
                            self.logger.error(
                                "❌ Page is not available, this may cause issues"
                            )
                except Exception as ready_error:
                    self.logger.warning(f"⚠️ Computer ready check failed: {ready_error}")
                    if hasattr(self.computer, "_page") and self.computer._page:
                        self.logger.info(
                            "✅ Page is available, proceeding despite ready check failure"
                        )
                    else:
                        self.logger.error(
                            "❌ Page is not available, this may cause issues"
                        )
            else:
                self.logger.info("✅ Computer is ready for operations")

        except RuntimeError as e:
            if "no running event loop" in str(e) or "asyncio loop" in str(e).lower():
                self.logger.warning(f"⚠️ Event loop conflict detected: {e}")
                self.logger.info(
                    "🔄 Retrying Playwright initialization in isolated thread..."
                )
                self._initialize_playwright_in_isolated_thread()
            else:
                raise
        except Exception as e:
            # Check if it's the Playwright async/sync error
            if "asyncio loop" in str(e).lower() or "sync api inside" in str(e).lower():
                self.logger.warning(f"⚠️ Event loop conflict detected: {e}")
                self.logger.info(
                    "🔄 Retrying Playwright initialization in isolated thread..."
                )
                self._initialize_playwright_in_isolated_thread()
            else:
                raise

    def _initialize_sync_playwright(self):
        """Initialize sync Playwright browser as fallback"""
        try:
            # Create computer with unique identifier for parallel execution isolation
            # Video directory will be added by _create_isolated_computer if current_task_dir exists
            self.computer = self._create_isolated_computer(
                LocalPlaywrightBrowser, headless=True, logger_instance=self.logger
            )
            self.computer.__enter__()
            self.logger.info(
                "✅ Enhanced sync Playwright browser initialized successfully"
            )

            if hasattr(self.computer, "wait_until_ready"):
                try:
                    ready = self.computer.wait_until_ready(timeout=15.0)
                    if ready:
                        self.logger.info("✅ Computer is ready for operations")
                    else:
                        self.logger.warning(
                            "⚠️ Computer ready check timed out, but continuing anyway"
                        )
                        if hasattr(self.computer, "_page") and self.computer._page:
                            self.logger.info(
                                "✅ Page is available, proceeding despite health check timeout"
                            )
                        else:
                            self.logger.error(
                                "❌ Page is not available, this may cause issues"
                            )
                except Exception as ready_error:
                    self.logger.warning(f"⚠️ Computer ready check failed: {ready_error}")
                    if hasattr(self.computer, "_page") and self.computer._page:
                        self.logger.info(
                            "✅ Page is available, proceeding despite ready check failure"
                        )
                    else:
                        self.logger.error(
                            "❌ Page is not available, this may cause issues"
                        )

        except Exception as init_error:
            # Log the error but don't fall back to async computer in sync context
            self.logger.error(f"❌ Computer initialization failed: {init_error}")
            raise RuntimeError(
                f"Computer initialization failed: {init_error}"
            ) from init_error

    def _initialize_playwright_in_isolated_thread(self):
        """
        Initialize Playwright in a separate thread without an event loop.
        This is used when the current thread has a running asyncio event loop
        that conflicts with Playwright's sync API.
        """
        import threading
        import queue

        self.logger.info(
            "🔒 Initializing Playwright in isolated thread (no event loop)..."
        )

        # Use a queue to pass the computer instance and any exceptions back
        result_queue = queue.Queue()
        exception_queue = queue.Queue()

        def init_playwright_in_thread():
            """Initialize Playwright in a thread without an event loop"""
            try:
                # Ensure no event loop exists in this thread
                import asyncio

                try:
                    # Try to clear any event loop reference
                    asyncio.set_event_loop(None)
                except Exception:
                    pass

                # Create computer in this isolated thread
                # Video directory will be added by _create_isolated_computer if current_task_dir exists
                computer = self._create_isolated_computer(
                    LocalPlaywrightBrowser, headless=True, logger_instance=self.logger
                )

                # Initialize the computer
                computer.__enter__()

                # Put the computer instance in the result queue
                result_queue.put(computer)

                self.logger.info(
                    "✅ Playwright initialized successfully in isolated thread"
                )

            except Exception as e:
                # Put the exception in the exception queue
                exception_queue.put(e)
                self.logger.error(
                    f"❌ Playwright initialization failed in isolated thread: {e}"
                )

        # Start the thread
        init_thread = threading.Thread(
            target=init_playwright_in_thread, name="PlaywrightInitThread"
        )
        init_thread.daemon = False  # Don't make it a daemon thread
        init_thread.start()

        # Wait for the thread to complete (with timeout)
        init_thread.join(timeout=60.0)  # 60 second timeout for initialization

        if init_thread.is_alive():
            self.logger.error(
                "❌ Playwright initialization thread timed out after 60 seconds"
            )
            raise RuntimeError("Playwright initialization timed out in isolated thread")

        # Check for exceptions first
        if not exception_queue.empty():
            exception = exception_queue.get()
            raise RuntimeError(
                f"Computer initialization failed in isolated thread: {exception}"
            ) from exception

        # Get the computer instance
        if not result_queue.empty():
            self.computer = result_queue.get()
            self.logger.info(
                "✅ Playwright browser initialized successfully in isolated thread"
            )

            # Verify the computer is ready
            if hasattr(self.computer, "wait_until_ready"):
                try:
                    ready = self.computer.wait_until_ready(timeout=15.0)
                    if ready:
                        self.logger.info("✅ Computer is ready for operations")
                    else:
                        self.logger.warning(
                            "⚠️ Computer ready check timed out, but continuing anyway"
                        )
                        if hasattr(self.computer, "_page") and self.computer._page:
                            self.logger.info(
                                "✅ Page is available, proceeding despite health check timeout"
                            )
                        else:
                            self.logger.error(
                                "❌ Page is not available, this may cause issues"
                            )
                except Exception as ready_error:
                    self.logger.warning(f"⚠️ Computer ready check failed: {ready_error}")
                    if hasattr(self.computer, "_page") and self.computer._page:
                        self.logger.info(
                            "✅ Page is available, proceeding despite ready check failure"
                        )
                    else:
                        self.logger.error(
                            "❌ Page is not available, this may cause issues"
                        )
            else:
                self.logger.info("✅ Computer is ready for operations")
        else:
            raise RuntimeError(
                "Playwright initialization failed - no computer instance returned from isolated thread"
            )

    def _initialize_agent(self):
        """Initialize agent with enhanced computer and monitoring"""
        if not self.computer:
            raise RuntimeError("Computer must be initialized before agent")

        # Get model type from current task or default to openai
        model_type = getattr(self, "_current_model_type", "openai")

        # Log IDs before creating agent
        iteration_id = getattr(self, "current_iteration_id", None)
        execution_id = getattr(self, "current_execution_id", None)
        self.logger.info(
            f"🔍 About to initialize {model_type} agent with iteration_id={iteration_id}, execution_id={execution_id}"
        )

        if model_type == "anthropic":
            # Initialize Anthropic agent (wrapper around V1 SimpleAnthropicAgent)
            from .agents.anthropic_agent import AnthropicAgent

            self.agent = AnthropicAgent(
                computer=self.computer,
                logger=self.logger,
                task_dir=str(self.current_task_dir) if self.current_task_dir else None,
                critical_error_tracker=self.critical_error_tracker,
                iteration_id=iteration_id,
                execution_id=execution_id,
            )
        elif model_type == "gemini":
            # Initialize Gemini agent
            from .agents.gemini_agent import GeminiAgent

            # Create a proper safety check callback
            def safety_check_callback(message):
                self.logger.info(f"Safety check: {message}")
                return True

            self.agent = GeminiAgent(
                computer=self.computer,
                acknowledge_safety_check_callback=safety_check_callback,
                logger=self.logger,
                task_dir=str(self.current_task_dir) if self.current_task_dir else None,
                critical_error_tracker=self.critical_error_tracker,
                iteration_id=iteration_id,
                execution_id=execution_id,
            )
        else:
            # Initialize OpenAI agent
            from .agents.openai_agent import OpenAIAgent

            dimensions = self.computer.get_dimensions()
            tools = [
                {
                    "type": "computer_use_preview",
                    "display_width": dimensions[0],
                    "display_height": dimensions[1],
                    "environment": self.computer.get_environment(),
                },
            ]

            # Create a proper safety check callback
            def safety_check_callback(message):
                self.logger.info(f"Safety check: {message}")
                return True

            # Create OpenAI agent
            self.agent = OpenAIAgent(
                computer=self.computer,
                tools=tools,
                acknowledge_safety_check_callback=safety_check_callback,
                logger=self.logger,
                task_dir=str(self.current_task_dir) if self.current_task_dir else None,
                critical_error_tracker=self.critical_error_tracker,
                iteration_id=getattr(self, "current_iteration_id", None),
                execution_id=getattr(self, "current_execution_id", None),
            )

        # ✅ Set real-time action callback for live timeline updates
        self.agent.set_action_callback(self._handle_agent_action)

        self.logger.info("✅ Agent initialized successfully")

    def initialize_computer(self):
        """Initialize computer environment - Always use Playwright for web tasks"""
        try:
            self.logger.info("Initializing Local Playwright Browser...")

            # Always use direct initialization with nest_asyncio for compatibility
            try:
                self._initialize_playwright_directly()
            except Exception as playwright_error:
                self.critical_error_tracker.record_critical_error(
                    playwright_error, "Playwright initialization"
                )
                raise

            # Initialize agent after computer is ready
            try:
                self._initialize_agent()
            except Exception as agent_error:
                self.critical_error_tracker.record_critical_error(
                    agent_error, "Agent initialization"
                )
                raise

            self.logger.info("✅ Playwright browser and agent initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize computer: {e}")
            raise

    def cleanup_computer(self):
        """Cleanup computer and agent resources with proper async Playwright handling"""
        cleanup_errors = []

        # Clean up agent resources first
        if self.agent:
            try:
                self.logger.info("Cleaning up agent resources...")
                if hasattr(self.agent, "cleanup_resources"):
                    self.agent.cleanup_resources()
                self.agent = None
                self.logger.info("✅ Agent resources cleaned up")
            except Exception as e:
                cleanup_errors.append(f"Agent cleanup error: {e}")
                self.logger.error(f"❌ Error cleaning up agent resources: {e}")

        # Clean up computer resources (async Playwright)
        if self.computer:
            try:
                self.logger.info("Starting computer cleanup...")

                # Check if it's an async browser
                if hasattr(self.computer, "__aexit__"):
                    self.logger.info("Cleaning up async Playwright browser...")
                    import asyncio

                    try:
                        # Check if we're already in an event loop
                        try:
                            loop = asyncio.get_running_loop()
                            # We're in an event loop, so we can't use run_until_complete
                            # Instead, we'll schedule the cleanup and let it run
                            self.logger.warning(
                                "Already in event loop, scheduling async cleanup..."
                            )
                            # Create a task but don't wait for it
                            task = loop.create_task(
                                self.computer.__aexit__(None, None, None)
                            )
                            # Give it a moment to start
                            time.sleep(0.1)
                            # Force cleanup by setting computer to None
                            self.computer = None
                        except RuntimeError:
                            # No event loop running, create a new one
                            asyncio.run(self.computer.__aexit__(None, None, None))
                    except Exception as e:
                        cleanup_errors.append(f"Async cleanup error: {e}")
                        self.logger.warning(f"Error during async cleanup: {e}")
                        # Force cleanup by setting computer to None
                        self.computer = None
                else:
                    # Sync browser cleanup
                    self.logger.info("Cleaning up sync Playwright browser...")

                    # Close all pages first
                    try:
                        if hasattr(self.computer, "page") and self.computer.page:
                            self.logger.info("Closing Playwright page...")
                            self.computer.page.close()
                    except Exception as e:
                        cleanup_errors.append(f"Page close error: {e}")
                        self.logger.warning(f"Error closing page: {e}")

                    # Close browser with proper cleanup
                    try:
                        if hasattr(self.computer, "browser") and self.computer.browser:
                            self.logger.info("Closing Playwright browser...")
                            time.sleep(2)
                            self.computer.browser.close()
                    except Exception as e:
                        cleanup_errors.append(f"Browser close error: {e}")
                        self.logger.warning(f"Error closing browser: {e}")

                    # Call the context manager exit method
                    try:
                        self.computer.__exit__(None, None, None)
                    except Exception as e:
                        cleanup_errors.append(f"Computer exit error: {e}")
                        self.logger.warning(f"Error calling computer __exit__: {e}")

                # Clear the computer reference
                self.computer = None
                self.logger.info("Computer resources cleaned up successfully")

            except Exception as e:
                cleanup_errors.append(f"Computer cleanup error: {e}")
                self.logger.warning(f"Error during computer cleanup: {e}")
                try:
                    self.computer = None
                except SoftTimeLimitExceeded:
                    raise
                except:
                    pass
        else:
            self.logger.debug("🧹 No computer to cleanup")

        # Check if cleanup errors should be treated as critical
        if cleanup_errors and len(cleanup_errors) >= 3:
            self.logger.warning(f"⚠️ Multiple cleanup errors detected: {cleanup_errors}")
            # Don't raise critical error for cleanup failures, just log them

        # Clean up file handlers to prevent log mixing
        # self._cleanup_file_handlers()

        # Additional cleanup to prevent resource leaks
        self._cleanup_additional_resources()

    def _cleanup_additional_resources(self):
        """Clean up additional resources to prevent leaks"""
        try:
            # Reset step counters
            self.step_counter = {
                "execution_steps": 0,
                "verification_steps": 0,
                "total_steps": 0,
            }

            # Clear current task references
            self.current_task_id = None
            self.current_task_dir = None
            self._current_model_type = None

            # Force garbage collection
            import gc

            gc.collect()

            self.logger.debug("🧹 Additional resources cleaned up")

        except Exception as e:
            self.logger.warning(f"⚠️ Error during additional resource cleanup: {e}")

    def create_execution_prompt(self, task: Dict[str, Any]) -> str:
        """Create a prompt for the agent to execute the task."""
        execution_prompt = f"""
You are an expert computer-using agent in a safe test environment. Work autonomously. Never ask for confirmation. If something expected is missing, adapt using the best available signals. If you encounter a hard external blocker that prevents completion, explain the issue naturally.

Goal: Complete the task accurately and efficiently with minimal actions.
Task: {task['task_description']}

Constraints:
- The browser is already at the required URL; begin now.
- Stay within allowed domains; avoid unrelated sites.
- Prefer the fewest steps needed to reach the goal.

Operating rules:
1) Navigate if needed, then take the smallest next action toward completion.
2) After actions that change the page, pause briefly until the UI is stable.
3) Use clear selectors, labels, or visible text for clicks and typing.
4) If something is missing, search on the page, use site navigation, or refine inputs.
5) Capture screenshots at key milestones (arrival, after critical submission, final state).
6) Verify completion against the task's success criteria before finishing.
7) Do not halt early and do not ask for confirmation.

Output (natural conversational style):
- When the task is complete, provide a comprehensive summary of what you accomplished, including key steps taken, any significant changes made, and how you verified the completion
- For action tasks (do/create/change): explain in detail what you did, the impact of your actions, and the final state
- For observation tasks (check/find/analyze): share your findings thoroughly, including any data points, observations, or conclusions
- If blocked by a hard external issue, explain the problem naturally, detailing the nature of the blocker, why it prevents completion, and any relevant error messages or observations
- Do not use any special formatting, headers, or structured responses

Begin now.
"""
        return execution_prompt

    def _get_complete_task_data(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get complete task data with gym information.
        If task already has base_url and verification_strategy (from execution snapshot),
        we don't need to query the database (supports decoupling).
        Otherwise, query for gym data (legacy support).
        """
        # Check if we already have the necessary gym data (from execution snapshot)
        if task.get("base_url") and task.get("verification_strategy"):
            self.logger.info(
                f"✅ Using task data from execution snapshot (decoupled) for {task.get('task_id')}"
            )
            # Ensure all required fields are present
            return {
                "task_id": task.get("task_id"),
                "prompt": task.get("prompt") or task.get("task_description", ""),
                "task_description": task.get("task_description")
                or task.get("prompt", ""),
                "grader_config": task.get("grader_config"),  # Preserve grader_config
                "simulator_config": task.get(
                    "simulator_config"
                ),  # Preserve simulator_config
                "gym_id": task.get("gym_id"),
                "base_url": task.get("base_url"),
                "verification_strategy": task.get("verification_strategy"),
                "verifier_path": task.get("verifier_path", ""),
                "task_link": task.get("task_link") or task.get("base_url"),
                "max_steps": task.get("max_steps", 100),
                "max_wait_time": task.get(
                    "max_wait_time", 7200
                ),  # 120 minutes (2 hours) default
                "priority": task.get("priority", "medium"),
                **{
                    k: v
                    for k, v in task.items()
                    if k
                    not in [
                        "prompt",
                        "task_description",
                        "gym_id",
                        "base_url",
                        "verification_strategy",
                        "verifier_path",
                        "task_link",
                        "max_steps",
                        "max_wait_time",
                        "priority",
                        "grader_config",
                        "simulator_config",
                    ]
                },
            }

        # Legacy path: Query database for gym data
        try:
            self.logger.info(
                "⚠️ Querying database for gym data (legacy path) for task %s",
                task.get("task_id"),
            )

            with get_db_session() as db:
                query = """
                    SELECT uuid, base_url, verification_strategy
                    FROM gyms
                    WHERE uuid = :gym_id
                """
                row = db.execute(
                    text(query), {"gym_id": task.get("gym_id", "")}
                ).fetchone()

                if not row:
                    self.logger.error(
                        "❌ Gym %s not found for task %s",
                        task.get("gym_id", ""),
                        task.get("task_id"),
                    )
                    return None

                verification_strategy = row.verification_strategy
                if hasattr(verification_strategy, "value"):
                    verification_strategy = verification_strategy.value

                complete_task_data = {
                    "task_id": task.get("task_id"),
                    "prompt": task.get("prompt") or task.get("task_description", ""),
                    "task_description": task.get("task_description")
                    or task.get("prompt", ""),
                    "grader_config": task.get(
                        "grader_config"
                    ),  # Preserve grader_config from task
                    "simulator_config": task.get(
                        "simulator_config"
                    ),  # Preserve simulator_config from task
                    "gym_id": str(row.uuid),
                    "base_url": row.base_url,
                    "verification_strategy": verification_strategy,
                    "verifier_path": task.get("verifier_path", ""),
                    "task_link": row.base_url,
                    "max_steps": task.get("max_steps", 100),
                    "max_wait_time": task.get("max_wait_time", 7200),
                    "priority": task.get("priority", "medium"),
                    **{
                        k: v
                        for k, v in task.items()
                        if k
                        not in [
                            "task_id",
                            "prompt",
                            "task_description",
                            "gym_id",
                            "grader_config",
                            "simulator_config",
                            "verifier_path",
                        ]
                    },
                }

                self.logger.info(
                    "✅ Retrieved gym data from database for task: %s",
                    task.get("task_id"),
                )
                self.logger.info(f"📋 Gym base URL: {row.base_url}")
                self.logger.info(f"🔍 Verification strategy: {verification_strategy}")
                return complete_task_data

        except Exception as e:
            self.logger.error(f"❌ Error getting complete task data from database: {e}")
            return None

    def execute_task(
        self, task: Dict[str, Any], iteration_number: int = 1
    ) -> Dict[str, Any]:
        """Execute a single task using unified approach with comprehensive logging and verification"""
        start_time = time.time()
        task_id = task["task_id"]

        # Get complete task data from database (like V1 runners do)
        complete_task_data = self._get_complete_task_data(task)
        if not complete_task_data:
            self.logger.error(f"❌ Failed to get complete task data for {task_id}")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": "Failed to get complete task data from database",
                "execution_time": time.time() - start_time,
                "run_id": None,
            }

        # Use complete task data
        task = complete_task_data
        self.logger.info(
            f"✅ Using complete task data: {task.get('task_link', 'No task_link')}"
        )

        # Store playground flag for video recording decision
        is_playground = task.get("is_playground", False)
        self._is_playground = is_playground
        if is_playground:
            self.logger.info(
                "🎮 Playground execution detected - video recording will be enabled"
            )

        # Use model type from execution context (already determined at execution level)
        # This ensures all iterations in one execution use the same model
        # But respect already-set model type from execute_single_iteration_from_db
        if hasattr(self, "_current_model_type") and self._current_model_type:
            model_type = self._current_model_type
            self.logger.info(
                f"🤖 Using already-set model type: {model_type} (from execute_single_iteration_from_db)"
            )
        else:
            model_type = (
                task.get("model_type")
                or task.get("runner_type")
                or self._detect_model_type(task)
            )
            self.logger.info(
                f"🤖 Using model type: {model_type} (from execution context)"
            )
            # Store model type for agent initialization
            self._current_model_type = model_type

        # Create task directory with correct iteration number (passed as parameter)
        # Skip if already created (e.g., by execute_single_iteration_from_db)
        if not self.current_task_dir:
            self.create_task_directory(task_id, iteration_number, model_type)
        else:
            self.logger.info(
                f"📁 Task directory already created: {self.current_task_dir}"
            )

        # Update agent's task directory if agent exists (for insighter initialization)
        if self.agent and hasattr(self.agent, "update_task_directory"):
            try:
                self.agent.update_task_directory(str(self.current_task_dir))
                self.logger.info("✅ Agent task directory updated for insighter")
            except Exception as update_error:
                self.logger.warning(
                    f"⚠️ Failed to update agent task directory: {update_error}"
                )

        # Set current task ID for agent use
        self.current_task_id = task_id

        # Initialize computer only if not already initialized (for single iteration execution)
        if self.computer is None:
            self.logger.info("🖥️  Initializing fresh computer instance for this task...")
            try:
                self.initialize_computer()
            except Exception as init_error:
                self.logger.error(f"❌ Failed to initialize computer: {init_error}")
                raise
        else:
            self.logger.info("🖥️  Computer already initialized, skipping initialization")

        self.logger.info(f"🚀  Starting task: {task_id}")
        self.logger.info(f"📋  Task description: {task['task_description']}")

        # Reset step counter for new task
        self.reset_step_counter()

        # Initialize task tracking
        task_start_time = time.time()
        task_screenshots = []
        verifier_on_start_data = {}

        try:
            # Navigate to the base URL with run_id parameter (like V1)
            base_url = task.get("task_link", "")
            verifier_path = task.get("verifier_path", "")
            if verifier_path:  # Script based verification
                self.logger.info(f"🚀  Verifier path: {verifier_path}")
                self.logger.info(
                    f"🚀  Verifier exitsts: {'Yes' if os.path.isfile(verifier_path) else 'No'}"
                )
                script_moduile_path = os.path.dirname(verifier_path)
                self.logger.info(f"🚀  script_moduile_path: {script_moduile_path}")
                # Define the module name (can be any unique name) and the full file path
                # Create a module specification
                spec = importlib.util.spec_from_file_location(
                    VERIFIER_MODULE_NAME, verifier_path
                )
                # Create a new module object from the specification
                verifier_module = importlib.util.module_from_spec(spec)

                # Register the module in sys.modules to make it discoverable by other imports
                sys.modules[VERIFIER_MODULE_NAME] = verifier_module
                # Execute the module's code in its own namespace
                spec.loader.exec_module(verifier_module)
                self.logger.info(f"🚀  Running verifier on_start method")
                # The module is now available for use
                from urllib.parse import urlparse
                parsed_url = urlparse(base_url)
                backend_url = base_url.replace(str(parsed_url.port), "8765")
                verifier_on_start_data = verifier_module.on_start(
                    prompt=task.get("prompt"), base_url=backend_url
                )
                self.logger.info(f"🚀  Verifier on_start method completed")

            if base_url:
                verification_strategy = task.get(
                    "verification_strategy", "verification_endpoint"
                )
                url_with_run_id = self.task_verification._add_run_id_to_url(
                    base_url, verification_strategy
                )
                self.logger.info(f"🌐 Navigating to base URL: {base_url}")
                self.logger.info(f"🆔 URL with run_id: {url_with_run_id}")
                self.logger.info(f"🔍 Verification strategy: {verification_strategy}")

                # Navigate to the URL with manual retry and critical error tracking
                navigation_successful = False
                for attempt in range(3):  # 3 total attempts
                    try:
                        self.logger.info(
                            f"Navigating to: {url_with_run_id} (attempt {attempt + 1}/3)"
                        )

                        # Add explicit timeout protection for navigation in worker threads
                        # Navigate using computer - let the decorators handle timeout and retry
                        self.computer.goto(url_with_run_id)

                        time.sleep(3)  # Wait for page load
                        self.logger.info(
                            f"✅ Navigation successful to: {url_with_run_id}"
                        )
                        navigation_successful = True
                        break
                    except TimeoutError as timeout_error:
                        self.logger.error(
                            f"🚨 CRITICAL: Navigation timeout for {url_with_run_id}: {timeout_error}"
                        )
                        self.critical_error_tracker.record_critical_error(
                            timeout_error,
                            f"Navigation timeout attempt {attempt + 1} to {url_with_run_id}",
                        )
                        if attempt < 2:  # Not the last attempt
                            self.logger.warning(
                                f"⚠️ Navigation attempt {attempt + 1} timed out, retrying..."
                            )
                            time.sleep(1)  # Brief delay before retry
                        else:
                            # Last attempt failed - do cleanup before raising exception
                            self.logger.error(
                                f"❌ All navigation attempts timed out for {url_with_run_id}"
                            )
                            self.logger.info(
                                f"🧹 Performing cleanup before raising navigation timeout exception"
                            )
                            try:
                                self.cleanup_computer()
                            except Exception as cleanup_error:
                                self.logger.warning(
                                    f"⚠️ Cleanup error during navigation timeout (non-critical): {cleanup_error}"
                                )
                            raise RuntimeError(
                                f"CRITICAL NAVIGATION TIMEOUT: {timeout_error}"
                            ) from timeout_error
                    except Exception as nav_error:
                        # Record each navigation failure as a critical error
                        self.critical_error_tracker.record_critical_error(
                            nav_error,
                            f"Navigation attempt {attempt + 1} to {url_with_run_id}",
                        )
                        if attempt < 2:  # Not the last attempt
                            self.logger.warning(
                                f"⚠️ Navigation attempt {attempt + 1} failed, retrying..."
                            )
                            time.sleep(1)  # Brief delay before retry
                        else:
                            self.logger.error(
                                f"❌ All navigation attempts failed for {url_with_run_id}"
                            )
                            raise

                if not navigation_successful:
                    raise Exception("Navigation failed after 3 attempts")

                # Take initial screenshot
                initial_screenshot = self._take_screenshot("initial_page", task_id)
                if initial_screenshot:
                    task_screenshots.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "type": "initial",
                            "filepath": initial_screenshot,
                            "note": "Initial page screenshot",
                        }
                    )

                # Take a screenshot after navigation to capture the loaded page
                time.sleep(2)
                navigation_screenshot = self._take_screenshot(
                    "after_navigation", task_id
                )
                if navigation_screenshot:
                    task_screenshots.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "type": "after_navigation",
                            "filepath": navigation_screenshot,
                            "note": "Page after navigation and loading",
                        }
                    )
            else:
                self.logger.info(
                    "ℹ️ No task_link provided, agent will start from current page (like V1)"
                )
                # Take a screenshot of the current page (blank page)
                initial_screenshot = self._take_screenshot("initial_page", task_id)
                if initial_screenshot:
                    task_screenshots.append(
                        {
                            "timestamp": datetime.now().isoformat(),
                            "type": "initial",
                            "filepath": initial_screenshot,
                            "note": "Initial page screenshot (no task_link)",
                        }
                    )

            # Create task execution prompt
            execution_prompt = self.create_execution_prompt(task)

            # Execute task with agent - using proper conversation structure
            # Use different content formats based on agent type (matching V1 behavior)
            if self.agent and hasattr(self.agent, "get_model_type"):
                model_type = self.agent.get_model_type()
                if model_type == "anthropic":
                    # V1 Anthropic format: content as list
                    execution_items = [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "text", "text": execution_prompt}],
                            "id": f"msg_{task_id}_{int(time.time())}",
                        }
                    ]
                else:
                    # V1 OpenAI format: content as string
                    execution_items = [
                        {
                            "type": "message",
                            "role": "user",
                            "content": execution_prompt,
                            "id": f"msg_{task_id}_{int(time.time())}",
                        }
                    ]
            else:
                # Fallback to OpenAI format
                execution_items = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": execution_prompt,
                        "id": f"msg_{task_id}_{int(time.time())}",
                    }
                ]

            # Initialize insight context for OpenAI agent
            if self.agent and hasattr(self.agent, "initialize_insight_context"):
                try:
                    task_description = task.get("task_description", "")
                    if task_description:
                        self.logger.info(
                            "🎯 Initializing insight context for task analysis"
                        )
                        success = self.agent.initialize_insight_context(
                            task_description
                        )
                        if success:
                            self.logger.info(
                                "✅ Insight context initialized successfully"
                            )
                        else:
                            self.logger.warning(
                                "⚠️ Failed to initialize insight context"
                            )
                    else:
                        self.logger.warning(
                            "⚠️ No task description available for insight context"
                        )
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error initializing insight context: {insight_error}"
                    )

            self.logger.info(f"🤖 Executing task with agent...")

            # Execute with agent - agents use the same call pattern
            try:
                items = self.agent.run_full_turn(execution_items)
                self.logger.info(f"✅ Agent execution completed successfully")

                # ✅ NOTE: action_timeline.json is now written in REAL-TIME via callback
                # The agent calls _report_action() after each action during execution
                # This ensures live monitoring sees progress as it happens
                self.logger.info(
                    f"✅ Agent returned {len(items) if items else 0} items (already written to timeline)"
                )

                # Validate that items have the expected structure
                if not items:
                    self.logger.warning(f"⚠️ Agent returned empty items")
                    items = []
                elif not isinstance(items, list):
                    self.logger.warning(
                        f"⚠️ Agent returned non-list items: {type(items)}"
                    )
                    items = [items] if items else []
                else:
                    self.logger.info(f"📊 Agent returned {len(items)} items")

            except (
                ConnectionError,
                TimeoutError,
                OSError,
                ssl.SSLError,
            ) as network_error:
                self.logger.error(
                    f"🚨 Network/SSL error during agent execution: {network_error}"
                )
                raise
            except SoftTimeLimitExceeded:
                raise
            except CriticalTimeoutError as critical_error:
                self.logger.error(f"🚨 CRITICAL TIMEOUT: {critical_error}")
                raise
            except CriticalAPIError as critical_api_error:
                self.logger.error(f"🚨 CRITICAL API ERROR: {critical_api_error}")
                raise
            except RuntimeError as runtime_error:
                # Check if this is an API error from agents (OpenAI/Gemini raise RuntimeError with "API call failed")
                error_str = str(runtime_error).lower()
                if "api call failed" in error_str and "attempts" in error_str:
                    # This is an API error after retries - convert to CriticalAPIError to crash immediately
                    self.logger.error(f"🚨 API ERROR after retries: {runtime_error}")
                    raise CriticalAPIError(
                        f"API call failed after retries: {runtime_error}"
                    ) from runtime_error
                else:
                    # Other RuntimeError - re-raise as is
                    self.logger.error(
                        f"❌ Runtime error during agent execution: {runtime_error}"
                    )
                    raise
            except Exception as agent_error:
                self.logger.error(f"❌ Agent execution failed: {agent_error}")
                # Re-raise the exception to crash the task instead of continuing
                raise

            # Track execution steps
            execution_steps_count = 0
            for i, item in enumerate(items):
                if not item:
                    continue

                item_type = item.get("type", "unknown")

                # Count concrete action events from different agents:
                # - OpenAI/Gemini emit 'computer_call' (request) and 'computer_call_output' (result)
                # - Anthropic emits 'tool_use' (request) and 'tool_result' (result)
                if item_type in ["computer_call", "tool_use"]:
                    execution_steps_count += 1
                    self.increment_step_counter("execution")

            self.logger.info(
                f"📊 Total execution steps counted: {execution_steps_count}"
            )

            # Capture conversation history and task response (even if items is empty)
            self.capture_conversation_history(task_id, "task_execution", items)
            self.save_task_response(task_id, "task_execution", items)

            # Check for task completion - Enhanced logic for agents
            completion_detected = False
            completion_reason = "Unknown"
            last_model_response_actual = (
                None  # ✅ Keep actual model response separate from completion_reason
            )

            # Check for natural completion - look for the last assistant message
            if items and len(items) > 0:
                # Look for the last assistant message to get natural completion
                last_assistant_message = None
                for item in reversed(items):
                    if (
                        item.get("type") == "message"
                        and item.get("role") == "assistant"
                    ):
                        last_assistant_message = item
                        break

                if last_assistant_message:
                    # Extract the natural response from the last assistant message
                    content = last_assistant_message.get("content", "")
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict) and "text" in first_content:
                            completion_reason = first_content.get("text", "")
                        elif isinstance(first_content, str):
                            completion_reason = first_content
                        else:
                            completion_reason = str(first_content)
                    elif isinstance(content, str):
                        completion_reason = content
                    else:
                        completion_reason = str(content)

                    # ✅ Store the ACTUAL model response before completion_reason gets overwritten
                    last_model_response_actual = completion_reason

                    completion_detected = True
                    self.logger.info(
                        f"✅ Task completed naturally with model response: {completion_reason[:100]}..."
                    )
                    self.logger.info(
                        f"🔍 DEBUG: Extracted model response length: {len(completion_reason)} chars"
                    )
                else:
                    # ✅ No assistant message found - model completed by not calling more tools
                    # This is NORMAL when the model finishes without sending a final text message
                    # Check if there were any actions executed (computer_call, tool_result, etc)
                    has_actions = any(
                        item.get("type")
                        in [
                            "computer_call_output",
                            "tool_result",
                            "computer_call",
                            "bash_output",
                            "editor_output",
                        ]
                        for item in items
                    )

                    if has_actions:
                        # Model completed by stopping tool calls (common pattern)
                        completion_detected = True
                        completion_reason = (
                            "Task completed (model stopped calling tools)"
                        )
                        last_model_response_actual = (
                            None  # Explicitly None - no final text message
                        )
                        self.logger.info(
                            "✅ Task completed naturally (model stopped calling tools, no final message)"
                        )
                    else:
                        # Set completion_detected = True to allow verification to run
                        # Verification will determine if task actually completed
                        completion_detected = True
                        completion_reason = "No natural response from model - verification will determine status"
                        self.logger.warning(
                            f"⚠️ No assistant message found - setting completion_detected=True for verification"
                        )
            else:
                # No items returned - but task might still be complete
                # Set completion_detected = True to allow verification to run
                completion_detected = True
                completion_reason = (
                    "No items returned - verification will determine status"
                )
                self.logger.warning(
                    f"⚠️ No items returned - setting completion_detected=True for verification"
                )

            # Calculate execution time FIRST (needed for workaround logic)
            execution_time = time.time() - start_time

            # Apply temporary workaround for completion detection if needed
            # Check for proper task completion
            self.logger.info(
                f"🔍 Debug: completion_detected={completion_detected}, execution_time={execution_time:.1f}s"
            )

            # Check for timeout as a fallback
            if not completion_detected and execution_time > 300:  # 5 minutes timeout
                completion_detected = True
                completion_reason = (
                    f"Task timeout after {execution_time:.1f}s - model blocked"
                )
                self.logger.warning(f"⚠️ Task timeout reached: {completion_reason}")

            self.logger.info(
                f"🔍 Debug: completion_detected={completion_detected}, execution_time={execution_time:.1f}s"
            )

            # Check if this is a playground execution (skip verification)
            is_playground = task.get("is_playground", False)

            # Execute verification step - skip for playground executions
            verification_results = None
            if is_playground:
                self.logger.info(
                    f"🎮 Playground execution detected - skipping verification step for task: {task_id}"
                )
                verification_results = {
                    "verification_status": "skipped",
                    "verification_completed": False,
                    "verification_method": "playground_skip",
                    "timestamp": datetime.now().isoformat(),
                    "note": "Verification skipped for playground execution",
                }
            else:
                self.logger.info(f"🔍 Executing verification step for task: {task_id}")
                try:
                    # ✅ Use actual model response for verification, not completion_reason (which might be error message)
                    model_response_for_verification = (
                        last_model_response_actual or completion_reason
                    )

                    # Build execution_results with all keys that verification might need
                    execution_results = {
                        "completion_reason": completion_reason,
                        "execution_steps": self.step_counter["execution_steps"],
                        "total_time": execution_time,
                        # Map model response to expected keys for GraderConfigVerifier
                        "modelResponse": model_response_for_verification,
                        "finalModelResponse": model_response_for_verification,
                        "final_response": model_response_for_verification,
                        "assistant_message": model_response_for_verification,
                        "finalMessage": model_response_for_verification,
                        "verifier_on_start_data": verifier_on_start_data,
                        "verifier_module_name": VERIFIER_MODULE_NAME,
                    }

                    # Try to extract final URL from browser if available
                    if (
                        self.computer
                        and hasattr(self.computer, "_page")
                        and self.computer._page
                    ):
                        try:
                            if not (
                                hasattr(self.computer._page, "is_closed")
                                and self.computer._page.is_closed()
                            ):
                                final_url = self.computer._page.url
                                execution_results["final_url"] = final_url
                                execution_results["last_url"] = final_url
                                execution_results["current_url"] = final_url
                        except Exception as url_error:
                            self.logger.warning(
                                f"⚠️ Could not extract final URL: {url_error}"
                            )

                    verification_results = self.execute_verification_step(
                        task, execution_results
                    )
                except ConfigurationError:
                    # Configuration errors should crash immediately
                    self.logger.error(
                        "❌ Configuration error during verification - re-raising",
                        exc_info=True,
                    )
                    raise
                except Exception as e:
                    self.logger.error(f"❌ Verification step failed: {e}")
                    verification_results = {
                        "status": "failed",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    }

            # Determine status based on completion and verification
            # For playground: always mark as passed if task completed (no verification)
            # For batch: Only mark as PASSED/FAILED if verification actually ran
            if is_playground:
                # Playground execution - mark as passed if task completed
                if completion_detected:
                    status = "passed"
                    self.logger.info(
                        f"✅ Playground task {task_id} completed (verification skipped)"
                    )
                else:
                    status = "crashed"
                    self.logger.error(f"❌ Playground task {task_id} did not complete")
            elif completion_detected and verification_results:
                # Task completed AND verification ran - check the result
                if (
                    verification_results.get("verification_status", "failed").lower()
                    == "passed"
                ):
                    status = "passed"
                    self.logger.info(
                        f"✅ Task {task_id} completed and verification passed"
                    )
                elif (
                    verification_results.get("verification_status", "failed").lower()
                    == "failed"
                ):
                    status = "failed"
                    self.logger.info(
                        f"❌ Task {task_id} completed but verification failed"
                    )
                else:
                    status = "crashed"  # Completed but verification failed
                    self.logger.info(
                        f"❌ Task {task_id} completed but verification crashed"
                    )
            else:
                # Determine if this is a model failure or system failure
                # CRITICAL: Check if verification ran even without completion_detected
                # Sometimes the task completes but without a natural response
                if verification_results:
                    # Verification ran - check if it passed or failed
                    if (
                        verification_results.get(
                            "verification_status", "failed"
                        ).lower()
                        == "passed"
                    ):
                        status = "passed"
                        self.logger.info(
                            f"✅ Task {task_id} passed verification despite no completion detected"
                        )
                    elif (
                        verification_results.get(
                            "verification_status", "failed"
                        ).lower()
                        == "failed"
                    ):
                        status = "failed"
                        self.logger.info(f"❌ Task {task_id} failed verification")
                    else:
                        status = "crashed"
                        self.logger.error(f"💥 Task {task_id} verification crashed")
                elif not completion_detected:
                    # No verification ran AND no completion detected - this is a failure
                    # Check if this is a model failure based on real database patterns
                    # Also check for model failure flags from agents
                    is_model_failure = False

                    if completion_reason:
                        is_model_failure = (
                            "model failure" in completion_reason.lower()
                            or "model blocked" in completion_reason.lower()
                            or "task timeout" in completion_reason.lower()
                            or "blocking" in completion_reason.lower()
                            or "task blocked" in completion_reason.lower()
                            or "no response" in completion_reason.lower()
                            or "no natural response" in completion_reason.lower()
                        )

                    # Check if agent detected model failure
                    if (
                        hasattr(self.agent, "_model_failure_detected")
                        and self.agent._model_failure_detected
                    ):
                        is_model_failure = True

                    if is_model_failure:
                        status = "failed"  # Model's fault
                        self.logger.error(
                            f"❌ Task {task_id} failed - model issue: {completion_reason}"
                        )
                    else:
                        status = "crashed"  # System's fault
                        self.logger.error(
                            f"💥 Task {task_id} crashed - system failure: {completion_reason}"
                        )
                else:
                    self.logger.error(
                        f"💥 Task {task_id} crashed - verification never ran (system failure)"
                    )

            # Generate final summary with verification status context
            eval_insights = None
            if (
                hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # Determine verification status for summary context
                    verification_status = None
                    if completion_detected and verification_results:
                        verification_status = verification_results.get(
                            "verification_status", "failed"
                        )
                    elif not completion_detected:
                        # If task didn't complete, it's a failure
                        verification_status = "failed"

                    self.logger.info(
                        f"📋 Generating final comprehensive summary with verification status: {verification_status}"
                    )
                    final_summary = self.agent.insighter.generate_final_summary(
                        verification_status
                    )
                    if final_summary:
                        eval_insights = final_summary.get("summary", "")
                        self.logger.info(
                            "✅ Final comprehensive summary generated successfully"
                        )
                    else:
                        self.logger.warning(
                            "⚠️ Failed to generate final comprehensive summary"
                        )
                except Exception as insight_error:
                    # Don't let insight generation failures crash the task
                    self.logger.warning(
                        f"⚠️ Final summary generation failed: {insight_error}"
                    )

            # Save task results
            task_result = {
                "task_id": task_id,
                "status": status,
                "execution_time": execution_time,
                "completion_reason": completion_reason,
                "last_model_response": last_model_response_actual
                or completion_reason,  # ✅ Use actual model response, fallback to completion_reason
                "execution_steps": self.step_counter["execution_steps"],
                "verification_steps": self.step_counter["verification_steps"],
                "total_steps": self.step_counter["total_steps"],
                "screenshots_count": len(task_screenshots),
                "start_time": task_start_time,
                "end_time": time.time(),
                "start_timestamp": datetime.fromtimestamp(task_start_time).isoformat(),
                "end_timestamp": datetime.now().isoformat(),
                "verification_results": verification_results,
                "run_id": self.task_verification.get_run_id(),
                "screenshots": task_screenshots,
                "iteration_directory": str(self.current_task_dir),
                "eval_insights": eval_insights,
            }

            # Add to results list
            self.results.append(task_result)

            self.logger.info(
                f"✅ Task {task_id} completed in {execution_time:.2f} seconds with status: {status}"
            )

            # Clean up resources after successful task completion
            self.cleanup_computer()

            return task_result

        except CriticalTimeoutError as e:
            execution_time = time.time() - start_time
            status = "crashed"
            error_msg = f"CRITICAL TIMEOUT: {str(e)}"

            # Generate final summary if context exists, even if task crashed
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For critical timeout, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (critical timeout)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite critical timeout"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            timeout_result = {
                "task_id": task_id,
                "status": status,
                "error": error_msg,
                "execution_time": execution_time,
                "execution_steps": self.step_counter["execution_steps"],
                "verification_steps": self.step_counter["verification_steps"],
                "total_steps": self.step_counter["total_steps"],
                "start_time": task_start_time,
                "end_time": time.time(),
                "start_timestamp": datetime.fromtimestamp(task_start_time).isoformat(),
                "end_timestamp": datetime.now().isoformat(),
                "verification_results": None,
                "run_id": self.task_verification.get_run_id(),
                "screenshots": task_screenshots,
                "iteration_directory": str(self.current_task_dir),
                "eval_insights": eval_insights,
            }

            self.results.append(timeout_result)
            self.logger.error(
                f"🚨 Task {task_id} crashed due to critical timeout after {execution_time:.2f} seconds: {e}"
            )
            return timeout_result

        except SoftTimeLimitExceeded as e:
            execution_time = time.time() - start_time
            status = "timeout"
            error_msg = str(e)

            # Generate final summary if context exists, even if task timed out
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For soft timeout, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (soft timeout)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite soft timeout"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            timeout_result = {
                "task_id": task_id,
                "status": status,
                "error": error_msg,
                "execution_time": execution_time,
                "execution_steps": self.step_counter["execution_steps"],
                "verification_steps": self.step_counter["verification_steps"],
                "total_steps": self.step_counter["total_steps"],
                "start_time": task_start_time,
                "end_time": time.time(),
                "start_timestamp": datetime.fromtimestamp(task_start_time).isoformat(),
                "end_timestamp": datetime.now().isoformat(),
                "verification_results": None,
                "run_id": self.task_verification.get_run_id(),
                "screenshots": task_screenshots,
                "iteration_directory": str(self.current_task_dir),
                "eval_insights": eval_insights,
            }

            self.results.append(timeout_result)
            self.logger.warning(
                f"⏰ Task {task_id} timed out after {execution_time:.2f} seconds: {e}"
            )
            self.cleanup_computer()
            return timeout_result

        except Exception as e:
            execution_time = time.time() - start_time

            # Check if this is a critical timeout error that should skip cleanup
            error_str = str(e).lower()
            is_critical_timeout = (
                "critical:" in error_str
                and "task should crash immediately" in error_str
                or "timed out after" in error_str
                and "task should crash immediately" in error_str
                or isinstance(e, CriticalTimeoutError)
                or "critical timeout" in error_str
                or "critical:" in error_str
                and "task crashed after" in error_str
                or "critical:" in error_str
                and "error history" in error_str
                or "critical:" in error_str
                and "critical errors" in error_str
                or "navigation failed" in error_str
                or "api call failed" in error_str
                or "screenshot failed" in error_str
                or "screenshot timed out" in error_str
                or "critical: screenshot" in error_str
            )

            # Check if this is an API error (400, 401, 403, 404, 500, etc.) - these should be "crashed"
            # Also check for API errors after retries (agents raise RuntimeError or CriticalAPIError)
            is_api_error = (
                isinstance(e, CriticalAPIError)
                or "error code: 400" in error_str
                or "error code: 401" in error_str
                or "error code: 403" in error_str
                or "error code: 404" in error_str
                or "error code: 500" in error_str
                or "api error" in error_str
                or "api call failed" in error_str
                or "api failed after" in error_str
                or "anthropic api" in error_str
                or "openai api" in error_str
                or "gemini api" in error_str
                or "invalid_request_error" in error_str
                or "authentication_error" in error_str
                or "permission_error" in error_str
                or "not found" in error_str
                or "unauthorized" in error_str
                or "api_key" in error_str
                or "environment variable is required" in error_str
                or "api key" in error_str
                or "authentication" in error_str
                or "invalid_request_error" in error_str
                or "overloaded" in error_str
                and "api" in error_str
            )

            # DEFAULT TO CRASHED unless specifically determined to be a task failure
            status = "crashed"  # Default: system crash

            # Generate final summary if context exists, even if task crashed
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For general exceptions, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (general exception)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite general exception"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            error_result = {
                "task_id": task_id,
                "status": status,
                "error": str(e),
                "execution_time": execution_time,
                "execution_steps": self.step_counter["execution_steps"],
                "verification_steps": self.step_counter["verification_steps"],
                "total_steps": self.step_counter["total_steps"],
                "start_time": task_start_time,
                "end_time": time.time(),
                "start_timestamp": datetime.fromtimestamp(task_start_time).isoformat(),
                "end_timestamp": datetime.now().isoformat(),
                "verification_results": None,
                "run_id": self.task_verification.get_run_id(),
                "screenshots": task_screenshots,
                "iteration_directory": str(self.current_task_dir),
                "eval_insights": eval_insights,
            }

            self.results.append(error_result)

            if is_critical_timeout:
                self.logger.error(
                    f"🚨 Task {task_id} crashed due to critical timeout after {execution_time:.2f} seconds: {e}"
                )
                return error_result
            elif is_api_error:
                self.logger.error(
                    f"💥 Task {task_id} crashed due to API error after {execution_time:.2f} seconds: {e}"
                )
                self.cleanup_computer()
                return error_result
            else:
                self.logger.error(
                    f"💥 Task {task_id} crashed after {execution_time:.2f} seconds: {e}"
                )
                self.cleanup_computer()
                return error_result

    def execute_single_iteration_from_db(
        self,
        task_data: Dict[str, Any],
        iteration_number: int = 1,
        max_wait_time: int = None,
        execution_folder_name: str = None,
        iteration_id: str = None,
        execution_id: str = None,
    ) -> Dict[str, Any]:
        """Execute a single iteration for a task from database data"""
        task_id = task_data["task_id"]

        try:
            self.logger.info(
                f"🔄 Starting iteration {iteration_number} for task: {task_id}"
            )
            import threading

            self.logger.info(
                f"🆔 Runner instance: {self.logger_name} - Thread: {threading.current_thread().ident}"
            )
            self.logger.info(
                f"🔒 This iteration gets its own isolated async Playwright instance"
            )

            # Reset critical error tracking for this iteration
            self.critical_error_tracker.reset()
            self.logger.info("🚨 Critical error tracking reset for new iteration")

            # CRITICAL: Store IDs for token tracking BEFORE initializing agent
            self.current_iteration_id = iteration_id
            self.current_execution_id = execution_id
            self.logger.info(
                f"📊 Tracking IDs set: iteration_id={iteration_id}, execution_id={execution_id}"
            )

            # Use provided execution folder name or create one
            if execution_folder_name:
                # Use centralized directory manager to set the execution directory
                self.execution_dir = self.base_results_dir / execution_folder_name
                self.execution_dir.mkdir(parents=True, exist_ok=True)
                self.directory_manager.set_execution_directory(self.execution_dir)
                self.logger.info(f"📁 Using execution directory: {self.execution_dir}")
            else:
                self.create_execution_directory("single_iteration")

            # CRITICAL: Set model type BEFORE initializing computer/agent
            model_type = (
                task_data.get("model_type")
                or task_data.get("runner_type")
                or self._detect_model_type(task_data)
            )
            self._current_model_type = model_type
            self.logger.info(
                f"🤖 Set model type for iteration {iteration_number}: {model_type}"
            )
            self.logger.info(f"🔍 Task data keys: {list(task_data.keys())}")
            self.logger.info(f"🔍 Task data model_type: {task_data.get('model_type')}")
            self.logger.info(
                f"🔍 Task data runner_type: {task_data.get('runner_type')}"
            )

            # CRITICAL: Set playground flag BEFORE creating task directory and initializing computer
            is_playground = task_data.get("is_playground", False)
            self._is_playground = is_playground
            if is_playground:
                self.logger.info(
                    "🎮 Playground execution detected - video recording will be enabled"
                )

            # Create task directory and setup task-specific logger BEFORE computer initialization
            self.logger.info(
                f"📁 Creating task directory and setting up task-specific logger for iteration {iteration_number}"
            )
            self.create_task_directory(task_id, iteration_number, model_type)

            # Initialize fresh async Playwright instance for this iteration
            self.logger.info(
                f"🎭 Initializing fresh async Playwright instance for iteration {iteration_number}"
            )
            try:
                self.initialize_computer()
            except Exception as init_error:
                self.critical_error_tracker.record_critical_error(
                    init_error, "Computer initialization"
                )
                raise

            # Execute the task (task directory already created above)
            try:
                result = self.execute_task(task_data, iteration_number)
            except Exception as exec_error:
                self.critical_error_tracker.record_critical_error(
                    exec_error, "Task execution"
                )
                raise

            # Clean up this iteration's Playwright instance (skip for critical timeouts)
            if (
                result.get("status") != "crashed"
                or "critical" not in str(result.get("error", "")).lower()
            ):
                self.logger.info(
                    f"🧹 Cleaning up async Playwright instance for iteration {iteration_number}"
                )
                try:
                    self.cleanup_computer()
                except Exception as cleanup_error:
                    self.logger.warning(
                        f"⚠️ Cleanup error (non-critical): {cleanup_error}"
                    )
            else:
                self.logger.info(
                    f"🚨 Skipping cleanup for critical timeout in iteration {iteration_number}"
                )

            self.logger.info(f"✅ Completed single iteration for task: {task_id}")

            # Add critical error summary to result
            error_summary = self.critical_error_tracker.get_error_summary()
            result["critical_error_summary"] = error_summary

            # Return the task result directly with iteration info added
            result["iteration_number"] = iteration_number
            # TEMPORARY DEBUG: Return logger for post-execution logging
            result["_debug_logger"] = self.logger
            return result

        except CriticalTimeoutError as e:
            self.logger.error(
                f"🚨 Task {task_id} iteration {iteration_number} crashed due to critical timeout: {e}"
            )

            # Generate final summary if context exists, even if task crashed
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For critical timeout in iteration, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (critical timeout in iteration)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite critical timeout"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            return {
                "task_id": task_id,
                "status": "crashed",
                "error": f"CRITICAL TIMEOUT: {str(e)}",
                "execution_time": 0,
                "iteration_number": iteration_number,
                "run_id": (
                    self.task_verification.get_run_id()
                    if hasattr(self, "task_verification")
                    else "N/A"
                ),
                "iteration_directory": (
                    str(self.current_task_dir)
                    if hasattr(self, "current_task_dir")
                    else "N/A"
                ),
                "eval_insights": eval_insights,
                "_debug_logger": self.logger,
            }

        except SoftTimeLimitExceeded as e:
            self.logger.warning(
                f"⏰ Task {task_id} iteration {iteration_number} timed out: {e}"
            )

            # Generate final summary if context exists, even if task timed out
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For soft timeout in iteration, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (soft timeout in iteration)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite soft timeout"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            try:
                self.cleanup_computer()
            except Exception as cleanup_error:
                self.logger.error(
                    f"❌ Error during timeout cleanup for task {task_id}: {cleanup_error}"
                )

            return {
                "task_id": task_id,
                "status": "timeout",
                "error": f"Task timed out: {str(e)}",
                "execution_time": 0,
                "iteration_number": iteration_number,
                "run_id": (
                    self.task_verification.get_run_id()
                    if hasattr(self, "task_verification")
                    else "N/A"
                ),
                "iteration_directory": (
                    str(self.current_task_dir)
                    if hasattr(self, "current_task_dir")
                    else "N/A"
                ),
                "eval_insights": eval_insights,
                "_debug_logger": self.logger,
            }

        except ConfigurationError:
            # Configuration errors should crash immediately - don't catch them
            self.logger.error(
                "❌ Configuration error in iteration - re-raising", exc_info=True
            )
            raise
        except Exception as e:
            error_str = str(e).lower()
            is_critical_timeout = (
                "critical:" in error_str
                and "task should crash immediately" in error_str
                or "timed out after" in error_str
                and "task should crash immediately" in error_str
                or isinstance(e, CriticalTimeoutError)
                or "critical timeout" in error_str
                or "critical:" in error_str
                and "task crashed after" in error_str
                or "critical:" in error_str
                and "error history" in error_str
                or "critical:" in error_str
                and "critical errors" in error_str
                or "navigation failed" in error_str
                or "api call failed" in error_str
                or "screenshot failed" in error_str
                or "screenshot timed out" in error_str
                or "critical: screenshot" in error_str
            )

            # Check if this is an API error (400, 401, 403, 404, 500, etc.) - these should be "crashed"
            # Also check for API errors after retries (agents raise RuntimeError or CriticalAPIError)
            is_api_error = (
                isinstance(e, CriticalAPIError)
                or "error code: 400" in error_str
                or "error code: 401" in error_str
                or "error code: 403" in error_str
                or "error code: 404" in error_str
                or "error code: 500" in error_str
                or "api error" in error_str
                or "api call failed" in error_str
                or "api failed after" in error_str
                or "anthropic api" in error_str
                or "openai api" in error_str
                or "gemini api" in error_str
                or "invalid_request_error" in error_str
                or "authentication_error" in error_str
                or "permission_error" in error_str
                or "not found" in error_str
                or "unauthorized" in error_str
                or "api_key" in error_str
                or "environment variable is required" in error_str
                or "api key" in error_str
                or "authentication" in error_str
                or "invalid_request_error" in error_str
                or "overloaded" in error_str
                and "api" in error_str
            )

            # Generate final summary if context exists, even if task crashed
            eval_insights = None
            if (
                self.agent
                and hasattr(self.agent, "insighter")
                and self.agent.insighter
                and self.agent.insighter.has_context()
            ):
                try:
                    # For general exception in iteration, mark as failed since task didn't complete
                    verification_status = "failed"
                    self.logger.info(
                        "📋 Generating final summary from existing context (general exception in iteration)"
                    )
                    eval_insights = (
                        self.agent.insighter.generate_summary_if_context_exists(
                            verification_status
                        )
                    )
                    if eval_insights:
                        self.logger.info(
                            "✅ Final summary generated from context despite general exception"
                        )
                    else:
                        self.logger.warning("⚠️ Failed to generate summary from context")
                except Exception as insight_error:
                    self.logger.warning(
                        f"⚠️ Error generating summary from context: {insight_error}"
                    )

            if is_critical_timeout:
                self.logger.error(
                    f"🚨 Single iteration crashed due to critical timeout: {e}"
                )
                status = "crashed"
                # Skip cleanup for critical timeouts - crash immediately
            else:
                self.logger.error(f"❌ Single iteration execution failed: {e}")
                status = "crashed"
                self.cleanup_computer()

            return {
                "task_id": task_id,
                "status": status,
                "error": str(e),
                "execution_time": 0,
                "iteration_number": iteration_number,
                "run_id": (
                    self.task_verification.get_run_id()
                    if hasattr(self, "task_verification")
                    else "N/A"
                ),
                "iteration_directory": (
                    str(self.current_task_dir)
                    if hasattr(self, "current_task_dir")
                    else "N/A"
                ),
                "eval_insights": eval_insights,
                "_debug_logger": self.logger,
            }

    def reset_step_counter(self):
        """Reset the step counter for a new task"""
        self.step_counter = {
            "execution_steps": 0,
            "verification_steps": 0,
            "total_steps": 0,
        }
        self.logger.info("🔄 Step counter reset for new task")

    def increment_step_counter(self, step_type: str):
        """Increment the appropriate step counter"""
        if step_type == "execution":
            self.step_counter["execution_steps"] += 1
        elif step_type == "verification":
            self.step_counter["verification_steps"] += 1

        self.step_counter["total_steps"] += 1
        self.logger.info(
            f"📊 Step counter updated - {step_type}: {self.step_counter[f'{step_type}_steps']}, Total: {self.step_counter['total_steps']}"
        )

    def execute_verification_step(
        self, task: Dict[str, Any], execution_results: Dict
    ) -> Dict[str, Any]:
        """Execute verification step using the shared TaskVerification helper"""
        self.logger.info(
            f"🔍 Starting API-based verification step for task: {task['task_id']}"
        )

        # Extract localStorage dump at the beginning of verification (non-blocking)
        # Only extract for LOCAL_STORAGE_ASSERTIONS strategy
        local_storage_result = None
        verification_strategy = task.get(
            "verification_strategy", "verification_endpoint"
        )

        # Handle both string and enum comparisons (case-insensitive)
        strategy_str = (
            str(verification_strategy).upper() if verification_strategy else ""
        )
        self.logger.info(f"🔍 Verification strategy detected: {strategy_str}")

        if "LOCAL_STORAGE_ASSERTIONS" in strategy_str:
            # Only extract localStorage for LOCAL_STORAGE_ASSERTIONS strategy
            gym_url = task.get("gym_url") or task.get("task_link")

            if not gym_url:
                self.logger.warning(
                    "⚠️ No gym_url or task_link available for localStorage extraction"
                )
                local_storage_result = {
                    "error": "No gym URL available",
                    "status": "failed",
                }
            else:
                self.logger.info(
                    f"📦 Extracting localStorage dump for task: {task['task_id']}"
                )
                try:
                    local_storage_result = self._extract_local_storage(
                        task_id=task["task_id"], gym_url=gym_url
                    )

                    if (
                        local_storage_result
                        and local_storage_result.get("status") == "success"
                    ):
                        self.logger.info(
                            f"✅ localStorage dump saved: {local_storage_result.get('dump_filename')} "
                            f"({local_storage_result.get('keys_count')} keys)"
                        )
                    else:
                        error_msg = (
                            local_storage_result.get("error", "Unknown error")
                            if local_storage_result
                            else "Unknown error"
                        )
                        self.logger.warning(
                            f"⚠️ localStorage extraction failed: {error_msg}"
                        )

                except Exception as e:
                    self.logger.warning(
                        f"⚠️ Failed to extract localStorage (non-blocking): {e}"
                    )
                    local_storage_result = {"error": str(e), "status": "failed"}
        else:
            # Skip localStorage extraction for all other strategies
            # (VERIFICATION_ENDPOINT, RUN_ID_ASSERTIONS, GRADER_CONFIG)
            skip_reason = {
                "VERIFICATION_ENDPOINT": "verification_endpoint does not use localStorage",
                "RUN_ID_ASSERTIONS": "run_id_assertions does not use localStorage",
                "GRADER_CONFIG": "grader_config uses window.get_states instead",
            }.get(strategy_str, f"{strategy_str} does not require localStorage")

            self.logger.info(
                f"⏭️ Skipping localStorage extraction for {strategy_str} strategy ({skip_reason})"
            )
            local_storage_result = {"status": "skipped", "reason": skip_reason}

        try:
            verification_results = self.task_verification.execute_api_verification_step(
                task=task,
                execution_results=execution_results,
                results_dir=self.current_task_dir,
                browser_computer=self.computer,  # Pass computer for window.get_states() calls
            )

            # Save verification results as verification.json in the task directory
            self._save_verification_results(verification_results)

            return verification_results

        except SoftTimeLimitExceeded:
            raise
        except ConfigurationError:
            # Configuration errors should crash immediately - don't catch them
            self.logger.error(
                "❌ Configuration error in verification - re-raising", exc_info=True
            )
            raise
        except Exception as e:
            self.logger.error(f"❌ Verification step failed: {e}")

            error_results = {
                "task_id": task["task_id"],
                "verification_completed": False,
                "verification_status": "failed",
                "verification_time": 0,
                "verification_steps": 0,
                "verification_method": "api_error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

            # Save error results as verification.json as well
            self._save_verification_results(error_results)

            return error_results

    def _save_verification_results(self, verification_results: Dict[str, Any]) -> str:
        """Save verification results as verification.json in the task directory"""
        try:
            if not self.current_task_dir:
                self.logger.warning(
                    "⚠️ No iteration directory available for verification results save"
                )
                return None

            # Use centralized directory manager for verification path
            verification_file = self.directory_manager.get_verification_path()

            self.logger.info(f"💾 Saving verification results to: {verification_file}")

            with open(verification_file, "w") as f:
                json.dump(verification_results, f, indent=2, default=str)

            self.logger.info(
                f"✅ Verification results successfully saved to: {verification_file}"
            )

            return str(verification_file)

        except Exception as e:
            self.logger.error(f"❌ Failed to save verification results: {e}")
            return None

    def save_task_response(
        self, task_id: str, step_name: str, items: List[Dict]
    ) -> str:
        """Save individual task response to task_responses directory"""
        try:
            if not self.current_task_dir:
                self.logger.warning(
                    "⚠️ No iteration directory available for task response save"
                )
                return None

            # Ensure the task_responses directory exists even if initial setup was interrupted
            response_dir = self.current_task_dir / "task_responses"
            response_dir.mkdir(parents=True, exist_ok=True)

            # Use centralized directory manager for response path
            response_file = self.directory_manager.get_response_path(step_name, task_id)
            response_file.parent.mkdir(parents=True, exist_ok=True)

            # Create a clean summary without large content or image URLs
            item_summary = []
            for item in items or []:  # Handle empty items gracefully
                if not item:  # Skip None/empty items
                    continue

                item_type = item.get("type", "unknown")
                summary_item = {
                    "type": item_type,
                    "timestamp": item.get("timestamp", "N/A"),
                }

                # Add relevant info based on item type
                if item_type == "message":
                    summary_item["role"] = item.get("role", "unknown")
                    if item.get("content"):
                        content = (
                            item["content"][0].get("text", "")
                            if item["content"]
                            else ""
                        )
                        summary_item["content"] = content
                        summary_item["content_preview"] = (
                            content[:100] + "..." if len(content) > 100 else content
                        )

                elif item_type in [
                    "computer_call_output",
                    "bash_output",
                    "editor_output",
                    "search_output",
                    "tool_result",
                ]:
                    summary_item["action"] = item.get(
                        "action", item.get("command", item.get("tool_name", "unknown"))
                    )
                    summary_item["has_screenshot"] = (
                        "image_url" in item or "screenshot" in item
                    )

                elif item_type == "text":
                    summary_item["text_preview"] = (
                        str(item.get("text", ""))[:100] + "..."
                        if len(str(item.get("text", ""))) > 100
                        else str(item.get("text", ""))
                    )

                item_summary.append(summary_item)

            # Calculate item types distribution
            item_types = {}
            for item in items or []:
                if item:
                    item_type = item.get("type", "unknown")
                    item_types[item_type] = item_types.get(item_type, 0) + 1

            response_data = {
                "task_id": task_id,
                "step_name": step_name,
                "timestamp": datetime.now().isoformat(),
                "total_items": len(items or []),
                "item_summary": item_summary,
                "item_types": item_types,
                "execution_status": "completed" if items else "failed_no_items",
            }

            with open(response_file, "w") as f:
                json.dump(response_data, f, indent=2, default=str)

            self.logger.info(f"💾 Task response saved: {response_file}")
            return str(response_file)

        except Exception as e:
            self.logger.error(f"❌ Failed to save task response: {e}")
            return None

    def capture_conversation_history(
        self, task_id: str, step_name: str, items: List[Dict]
    ) -> Dict[str, Any]:
        """Capture conversation history for analysis and debugging"""
        try:
            self.logger.info(f"📥 Capturing conversation history for {step_name}...")

            # Create conversation summary
            conversation_summary = {
                "timestamp": datetime.now().isoformat(),
                "step_name": step_name,
                "task_id": task_id,
                "total_items": len(items or []),
                "item_types": {},
                "conversation_flow": [],
                "execution_status": "completed" if items else "failed_no_items",
            }

            # Analyze conversation structure
            for i, item in enumerate(items or []):
                if not item:  # Skip None/empty items
                    continue

                item_type = item.get("type", "unknown")
                conversation_summary["item_types"][item_type] = (
                    conversation_summary["item_types"].get(item_type, 0) + 1
                )

                # Track conversation flow with proper timestamp
                flow_entry = {
                    "index": i,
                    "type": item_type,
                    "timestamp": datetime.now().isoformat(),  # Use actual timestamp
                }

                # Handle messages (includes model thinking and responses)
                if item_type == "message":
                    role = item.get("role", "unknown")
                    flow_entry["role"] = role

                    # Handle content (can be list of text blocks)
                    if item.get("content"):
                        if isinstance(item["content"], list):
                            # Multiple content blocks (text + tool_use)
                            full_content = []
                            for block in item["content"]:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        full_content.append(block.get("text", ""))
                                    elif block.get("type") == "tool_use":
                                        # Store tool use info separately
                                        flow_entry["tool_name"] = block.get(
                                            "name", "unknown"
                                        )
                                        flow_entry["tool_input"] = block.get(
                                            "input", {}
                                        )
                                elif isinstance(block, str):
                                    full_content.append(block)

                            content = "\n".join(full_content)
                            flow_entry["content"] = content
                            flow_entry["content_preview"] = (
                                content[:100] + "..." if len(content) > 100 else content
                            )
                        else:
                            # Simple string content
                            flow_entry["content"] = str(item["content"])
                            flow_entry["content_preview"] = str(item["content"])[:100]

                    # Capture OpenAI reasoning if present
                    if "reasoning_content" in item:
                        flow_entry["reasoning"] = item["reasoning_content"]

                # Handle tool_use entries (Anthropic format)
                elif item_type == "tool_use":
                    flow_entry["tool_name"] = item.get("name", "unknown")
                    flow_entry["tool_input"] = item.get("input", {})
                    flow_entry["tool_id"] = item.get("id", None)

                    # Extract action details if it's a computer tool
                    if item.get("name") == "computer":
                        tool_input = item.get("input", {})
                        flow_entry["action"] = tool_input.get("action", "unknown")
                        if "coordinate" in tool_input:
                            flow_entry["coordinates"] = tool_input["coordinate"]
                        if "text" in tool_input:
                            flow_entry["text"] = tool_input["text"]
                        if "key" in tool_input:
                            flow_entry["key"] = tool_input["key"]
                        # Capture submit flag (Gemini types with Enter by default)
                        if "submit" in tool_input:
                            flow_entry["submit"] = tool_input["submit"]

                # Handle tool results
                elif item_type == "tool_result":
                    flow_entry["tool_use_id"] = item.get("tool_use_id", None)
                    if "output" in item:
                        output = item["output"]
                        if isinstance(output, str):
                            flow_entry["output"] = output[:200]  # Truncate long outputs
                        else:
                            flow_entry["output"] = str(output)[:200]

                # Handle computer actions (unified format) - includes Anthropic's tool_result
                elif item_type in [
                    "computer_call_output",
                    "bash_output",
                    "editor_output",
                    "search_output",
                    "tool_result",
                ]:
                    # Capture full action details
                    flow_entry["computer_action"] = item.get(
                        "action", item.get("command", item.get("tool_name", "unknown"))
                    )

                    # Capture screenshot path (CRITICAL for frontend!)
                    screenshot_file = item.get("screenshot") or item.get("image_url")
                    if screenshot_file:
                        if isinstance(
                            screenshot_file, str
                        ) and not screenshot_file.startswith("data:"):
                            # It's a path, not base64 - extract just the filename
                            flow_entry["screenshot"] = Path(screenshot_file).name
                            flow_entry["has_screenshot"] = True
                            self.logger.debug(
                                f"✅ Captured screenshot: {Path(screenshot_file).name}"
                            )
                        else:
                            # It's base64 or something else
                            flow_entry["has_screenshot"] = True
                            self.logger.debug(
                                f"✅ Has screenshot (base64 or other format)"
                            )
                    else:
                        flow_entry["has_screenshot"] = False
                        self.logger.warning(
                            f"⚠️ Screenshot field is None for {item_type} at index {i}"
                        )

                    # Capture URL
                    url = item.get("url") or item.get("current_url")
                    if url:
                        flow_entry["url"] = url
                        self.logger.debug(f"✅ Captured URL: {url[:50]}...")
                    else:
                        self.logger.warning(
                            f"⚠️ URL field is None for {item_type} at index {i}"
                        )

                    # Capture coordinates for click/type actions
                    coordinates = item.get("coordinates") or item.get("coordinate")
                    if coordinates:
                        flow_entry["coordinates"] = coordinates

                    # Capture text for type actions
                    text = item.get("text")
                    if text:
                        flow_entry["text"] = text

                    # Capture key for keyboard actions
                    key = item.get("key")
                    if key:
                        flow_entry["key"] = key

                    # Capture submit flag (important for Gemini)
                    submit = item.get("submit")
                    if submit is not None:
                        flow_entry["submit"] = submit

                    # Capture command for bash actions
                    command = item.get("command")
                    if command:
                        flow_entry["command"] = command

                    # Capture result/output
                    result = item.get("result")
                    if result:
                        if isinstance(result, str):
                            flow_entry["result"] = result[:200]
                        else:
                            flow_entry["result"] = str(result)[:200]

                conversation_summary["conversation_flow"].append(flow_entry)

            # Save conversation summary
            conversation_file = (
                self.current_task_dir
                / "conversation_history"
                / f"{task_id}_{step_name}_conversation.json"
            )
            conversation_file.parent.mkdir(exist_ok=True)

            with open(conversation_file, "w") as f:
                json.dump(conversation_summary, f, indent=2, default=str)

            self.logger.info(f"💾 Conversation history saved: {conversation_file}")

            # Note: Timeline is now written in REAL-TIME via callback during execution
            # No need to write here - it's already been written by the agent callbacks

            return conversation_summary

        except Exception as e:
            self.logger.error(f"❌ Error capturing conversation history: {e}")
            return {}

    def _initialize_action_timeline_file(self, iteration_dir: Path):
        """
        ✅ Initialize action_timeline.json file at iteration start

        This is the SINGLE SOURCE OF TRUTH for all models.
        Format: Unified timeline format (same for Gemini, OpenAI, Anthropic)
        """
        try:
            # ✅ Reset sequence counter for new iteration
            self._timeline_sequence_index = 0

            action_timeline_file = iteration_dir / "action_timeline.json"

            # Create empty timeline
            initial_timeline = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "entries": [],
            }

            with open(action_timeline_file, "w") as f:
                json.dump(initial_timeline, f, indent=2)

            self.logger.info(
                f"✅ Initialized action_timeline.json (single source of truth)"
            )

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize action_timeline.json: {e}")

    def _append_to_action_timeline(self, entry: Dict[str, Any]):
        """
        ✅ Append entry to action_timeline.json in REAL-TIME

        This is called after each action/response to keep the timeline live.
        Format: Unified timeline format (works for all models)
        """
        if not self.current_task_dir:
            self.logger.warning("⚠️ Cannot append to timeline: no current_task_dir")
            return

        try:
            action_timeline_file = self.current_task_dir / "action_timeline.json"
            self.logger.info(f"📂 Writing to: {action_timeline_file}")

            # Read current timeline
            if action_timeline_file.exists():
                with open(action_timeline_file, "r") as f:
                    timeline = json.load(f)
                self.logger.info(
                    f"📖 Read existing timeline with {len(timeline.get('entries', []))} entries"
                )
            else:
                timeline = {
                    "version": "1.0",
                    "created_at": datetime.now().isoformat(),
                    "entries": [],
                }
                self.logger.info(f"📄 Created new timeline file")

            # Append new entry
            timeline["entries"].append(entry)

            # Write back
            with open(action_timeline_file, "w") as f:
                json.dump(timeline, f, indent=2, default=str)

            self.logger.info(
                f"✅ Appended to action_timeline.json: {len(timeline['entries'])} total entries (entry_type={entry.get('entry_type')}, screenshot={entry.get('screenshot_path', 'N/A')})"
            )

        except Exception as e:
            self.logger.error(
                f"❌ Failed to append to action_timeline: {e}", exc_info=True
            )

    def _handle_agent_action(self, item: Dict[str, Any]):
        """
        ✅ Callback handler for real-time action reporting from agents

        This is called by agents DURING execution after each action.
        It immediately writes the action to action_timeline.json.

        For Gemini: Merges computer_call + computer_call_output into single action
        """
        try:
            self.logger.info(f"🔔 CALLBACK TRIGGERED: {item.get('type', 'unknown')}")

            item_type = item.get("type", "unknown")

            # ✅ Handle Gemini's two-part action reporting (computer_call + computer_call_output)
            if not hasattr(self, "_pending_computer_call"):
                self._pending_computer_call = None

            if item_type == "computer_call":
                # Buffer the call details (before action)
                self._pending_computer_call = item
                self.logger.info(f"📦 Buffered computer_call for merging")
                return  # Don't write yet, wait for output

            if item_type == "computer_call_output" and self._pending_computer_call:
                # ✅ Only merge actions with visible effects (click, type, scroll, key)
                # Skip merging for: screenshot, wait, navigate (no before/after needed)
                action_name = self._pending_computer_call.get("action", "")
                # ✅ Include action names from ALL agents: Gemini, OpenAI, Anthropic
                visible_effect_actions = [
                    # Gemini: click_at, type_text_at, scroll_at, etc.
                    "click_at",
                    "type_text_at",
                    "hover_at",
                    "scroll_at",
                    "scroll_document",
                    "keypress",
                    "key_combination",
                    "drag_and_drop",
                    # OpenAI/Anthropic: click, type, scroll, etc.
                    "computer_action",
                    "left_click",
                    "right_click",
                    "double_click",
                    "triple_click",
                    "click",
                    "type",
                    "type_text",
                    "key",
                    "scroll_up",
                    "scroll_down",
                    "scroll",
                    "mouse_move",
                    "mouse_down",
                    "mouse_up",
                    "mouse_click",
                    "move",
                ]

                if action_name in visible_effect_actions:
                    # Merge with buffered call (before/after screenshots)
                    merged_item = {**self._pending_computer_call, **item}
                    merged_item["type"] = "computer_action"  # Mark as merged
                    # ✅ Get before/after screenshots from BOTH call and output (prefer non-None values)
                    merged_item["screenshot_before"] = item.get(
                        "screenshot_before"
                    ) or self._pending_computer_call.get("screenshot_before")
                    merged_item["screenshot_after"] = (
                        item.get("screenshot_after")
                        or item.get("screenshot")
                        or self._pending_computer_call.get("screenshot_after")
                    )
                    self._pending_computer_call = None  # Clear buffer
                    item = merged_item
                    self.logger.info(
                        f"🔗 Merged computer_call + computer_call_output (visible effect: {action_name}, before: {merged_item.get('screenshot_before')}, after: {merged_item.get('screenshot_after')})"
                    )
                else:
                    # Don't merge - just use output with single screenshot
                    self._pending_computer_call = None  # Clear buffer
                    self.logger.info(
                        f"⏭️ Skipped merge for non-visible action: {action_name}"
                    )

            # Convert item to unified timeline format
            unified_entry = self._convert_item_to_timeline_entry(item)
            if unified_entry:
                # Write to action_timeline.json immediately
                self._append_to_action_timeline(unified_entry)
                self.logger.info(
                    f"✅ Real-time action written: {unified_entry.get('entry_type')} - {unified_entry.get('action_name', unified_entry.get('content', '')[:50])}"
                )
            else:
                self.logger.warning(
                    f"⚠️ Callback received item but conversion returned None: {item.get('type')}"
                )
        except Exception as e:
            self.logger.error(
                f"❌ Failed to handle agent action callback: {e}", exc_info=True
            )

    def _convert_item_to_timeline_entry(
        self, item: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        ✅ Convert agent item to unified timeline format

        Works for ALL models (Gemini, OpenAI, Anthropic)
        Returns entry in the format: {entry_type, sequence_index, timestamp, ...}
        """
        import uuid

        # Only Gemini-style computer-use actions are implicitly normalized (0–1000).
        # OpenAI / Anthropic actions use pixel coordinates and must set coordinates_normalized explicitly if needed.
        normalized_coordinate_actions = {
            "click_at",
            "type_text_at",
            "type_text",
            "hover_at",
            "scroll_at",
            "drag_and_drop",
        }

        def _compute_scroll_metrics(
            start_coords, direction, amount_value, magnitude_value, normalized
        ):
            if not start_coords or not direction:
                return None
            axis = None
            if direction in ["up", "down"]:
                axis = "vertical"
            elif direction in ["left", "right"]:
                axis = "horizontal"
            if not axis:
                return None

            # Determine base distance
            distance_raw = None
            if magnitude_value is not None:
                distance_raw = abs(magnitude_value)
            elif amount_value is not None:
                distance_raw = abs(amount_value)
            else:
                distance_raw = 150 if normalized else 200

            if normalized:
                distance_raw = max(10, min(1000, distance_raw))
            else:
                if distance_raw <= 10:
                    distance_raw *= 120  # treat as scroll "steps"
                distance_raw = max(40, min(2000, distance_raw))

            sign = 1 if direction in ["down", "right"] else -1
            base_x, base_y = start_coords

            if axis == "vertical":
                end_y = base_y + sign * distance_raw
                if normalized:
                    end_y = max(0, min(1000, end_y))
                distance = abs(end_y - base_y)
                end_point = [base_x, end_y]
            else:
                end_x = base_x + sign * distance_raw
                if normalized:
                    end_x = max(0, min(1000, end_x))
                distance = abs(end_x - base_x)
                end_point = [end_x, base_y]

            units = "normalized" if normalized else "pixels"
            display_units = "pts" if normalized else "px"
            return {
                "axis": axis,
                "start": list(start_coords),
                "end": end_point,
                "distance": distance,
                "units": units,
                "display": f"{int(distance)}{display_units}",
                "start_normalized": normalized,
                "end_normalized": normalized,
            }

        # ✅ Track sequence index (incremented for each entry)
        if not hasattr(self, "_timeline_sequence_index"):
            self._timeline_sequence_index = 0

        item_type = item.get("type", "unknown")
        role = item.get("role", "")
        # ✅ Always use current timestamp when action is reported (not old cached timestamps)
        timestamp = datetime.now().isoformat()

        # 1. GEMINI: type="text" with role="assistant" → thinking/response
        if item_type == "text" and role == "assistant":
            text_content = item.get("text", "")
            entry = {
                "id": str(uuid.uuid4()),
                "entry_type": "model_response",
                "sequence_index": self._timeline_sequence_index,
                "timestamp": timestamp,
                "content": text_content,
                "metadata": {},
            }
            self._timeline_sequence_index += 1
            return entry

        # 2. Model thinking/reasoning (OpenAI)
        if role == "assistant" and item.get("reasoning"):
            entry = {
                "id": str(uuid.uuid4()),
                "entry_type": "model_thinking",
                "sequence_index": self._timeline_sequence_index,
                "timestamp": timestamp,
                "content": item.get("reasoning", ""),
                "metadata": {},
            }
            self._timeline_sequence_index += 1
            return entry

        # 3. GEMINI: type="message" with role="assistant"
        if item_type == "message" and role == "assistant":
            # Extract text from content array
            content = item.get("content", "")
            if isinstance(content, list):
                # ✅ Handle both OpenAI {"text": "..."} and Anthropic {"type": "text", "text": "..."} formats
                text_parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            text_parts.append(c.get("text", ""))
                        elif "text" in c:
                            # OpenAI format without 'type' field
                            text_parts.append(c.get("text", ""))
                content = " ".join(text_parts)

            # ✅ Debug: Log message conversion
            self.logger.debug(
                f"📝 Converting assistant message to timeline: type={item_type}, role={role}, content_length={len(str(content))}"
            )

            entry = {
                "id": str(uuid.uuid4()),
                "entry_type": "model_response",
                "sequence_index": self._timeline_sequence_index,
                "timestamp": timestamp,
                "content": str(content),
                "metadata": {},
            }
            self._timeline_sequence_index += 1
            self.logger.debug(
                f"✅ Created model_response timeline entry with sequence_index={entry['sequence_index']}"
            )
            return entry

        # 4. Actions (computer_call, tool_result, bash_output, etc., computer_action [merged])
        if item_type in [
            "computer_call",
            "computer_call_output",
            "tool_result",
            "bash_output",
            "editor_output",
            "search_output",
            "computer_action",
        ]:
            # ✅ Extract tool_input early for fallback lookups
            tool_input = (
                item.get("tool_input", {})
                if isinstance(item.get("tool_input"), dict)
                else {}
            )

            # Extract action details
            screenshot = item.get("screenshot", item.get("image_url", ""))
            url = (
                item.get("url") or item.get("current_url") or tool_input.get("url", "")
            )

            # ✅ Handle before/after screenshots (for merged Gemini actions with visible effects)
            screenshot_before = item.get("screenshot_before")
            screenshot_after = item.get("screenshot_after")

            # Debug logging
            self.logger.debug(
                f"📸 Screenshot extraction: item_type={item_type}, before={screenshot_before}, after={screenshot_after}, main={screenshot}"
            )

            # If no before/after, use main screenshot as single screenshot
            if not screenshot_before and not screenshot_after:
                screenshot_after = screenshot  # Single screenshot goes to "after"
                self.logger.debug(
                    f"📸 Using main screenshot as after: {screenshot_after}"
                )

            # ✅ Safely extract action (handle dict/non-string types)
            action = item.get("action", item.get("computer_action", "other"))
            if not isinstance(action, str):
                # If action is dict/list/other, convert to string or use default
                if isinstance(action, dict):
                    # Try to extract 'type' or 'name' field from dict
                    action = action.get("type", action.get("name", "other"))
                else:
                    action = "other"

            coordinates = (
                item.get("coordinates")
                or item.get("coordinate")
                or tool_input.get("coordinate")
            )
            target_coordinates = (
                item.get("target_coordinates")
                or item.get("destination_coordinate")
                or item.get("end_coordinate")
                or tool_input.get("target_coordinate")
                or tool_input.get("destination_coordinate")
            )
            if not target_coordinates:
                dest_x = item.get("destination_x")
                dest_y = item.get("destination_y")
                if dest_x is not None and dest_y is not None:
                    target_coordinates = [dest_x, dest_y]

            start_coordinates = (
                item.get("start_coordinates")
                or item.get("start_coordinate")
                or item.get("origin_coordinate")
            )
            if not start_coordinates:
                start_x = item.get("start_x")
                start_y = item.get("start_y")
                if start_x is not None and start_y is not None:
                    start_coordinates = [start_x, start_y]

            # Special-case Anthropic-style left_click_drag / drag / click_and_drag:
            # they often provide start_coordinates + coordinates, but no explicit target_coordinates.
            # In that case, treat `coordinates` as the drag target so we can render a full drag path.
            if (
                not target_coordinates
                and start_coordinates
                and coordinates
                and action in ("left_click_drag", "drag", "click_and_drag")
            ):
                target_coordinates = coordinates

            text = item.get("text", "") or tool_input.get("text", "")
            # ✅ Extract key/keys (OpenAI uses 'keys' as list, Anthropic uses 'text' for action='key')
            key = (
                item.get("key", "")
                or tool_input.get("key", "")
                or tool_input.get("keys", "")
            )
            # ✅ For Anthropic: if action is 'key' and no key found, use text as key value
            if not key and action == "key" and text:
                self.logger.debug(
                    f"⌨️ Fallback: Using text as key for action='key': text='{text}'"
                )
                key = text

            # Debug: Log key extraction for key_press actions
            if action == "key" or "key" in str(action).lower():
                self.logger.debug(
                    f"⌨️ Timeline key extraction: action='{action}', "
                    f"item.key='{item.get('key', '')}', tool_input.key='{tool_input.get('key', '')}', "
                    f"tool_input.keys='{tool_input.get('keys', '')}', text='{text}', final_key='{key}'"
                )

            amount_value = item.get("amount") or item.get("scroll_amount")
            magnitude_value = item.get("magnitude")

            # ✅ Helper function to convert absolute to relative path
            def to_relative_path(path):
                if not path:
                    return None
                from pathlib import Path

                screenshot_path = Path(path)
                if screenshot_path.is_absolute() and "screenshots" in str(
                    screenshot_path
                ):
                    # Extract relative path from screenshots directory onwards
                    parts = screenshot_path.parts
                    if "screenshots" in parts:
                        idx = parts.index("screenshots")
                        return str(Path(*parts[idx:]))
                return path

            # Convert paths to relative
            screenshot = to_relative_path(screenshot)
            screenshot_before = to_relative_path(screenshot_before)
            screenshot_after = to_relative_path(screenshot_after)

            # Debug: Log screenshot value
            self.logger.info(
                f"📸 Screenshot extracted: '{screenshot}' from item type '{item_type}'"
            )

            # ✅ Map to valid enum values: click, type, scroll, key_press, screenshot, navigate, other
            action_type_map = {
                # Generic / OpenAI
                "left_click": "click",
                "right_click": "click",
                "double_click": "click",
                "click": "click",
                "type": "type",
                "type_text": "type",
                "key": "key_press",
                "key_press": "key_press",
                "hover": "other",
                "hover_at": "other",
                "mouse_move": "other",
                "move": "other",
                "scroll": "scroll",
                "scroll_down": "scroll",
                "scroll_up": "scroll",
                "mouse_down": "click",
                "mouse_up": "click",
                "mouse_click": "click",
                "navigate": "navigate",
                "goto": "navigate",
                "screenshot": "screenshot",
                "bash": "bash_command",
                "bash_output": "bash_command",
                "editor": "editor_action",
                "editor_output": "editor_action",
                # Gemini-specific names
                "click_at": "click",
                "type_text_at": "type",
                "key_combination": "key_press",
                "keypress": "key_press",
                "scroll_at": "scroll",
                "scroll_document": "scroll",
                "open_web_browser": "navigate",
                "wait_5_seconds": "other",
                "drag_and_drop": "other",
                "left_click_drag": "other",
                "click_and_drag": "other",
                "drag": "other",
            }

            action_type = action_type_map.get(action, "other")
            action_name = action if action else item_type

            coordinates_normalized = bool(item.get("coordinates_normalized"))
            # Only auto-mark Gemini-style normalized actions; OpenAI/Anthropic use pixel coordinates
            if (
                not coordinates_normalized
                and action_name in normalized_coordinate_actions
            ):
                coordinates_normalized = True
            target_coordinates_normalized = item.get("target_coordinates_normalized")
            if target_coordinates_normalized is None:
                target_coordinates_normalized = coordinates_normalized
            else:
                target_coordinates_normalized = bool(target_coordinates_normalized)
            start_coordinates_normalized = item.get("start_coordinates_normalized")
            if start_coordinates_normalized is None:
                start_coordinates_normalized = coordinates_normalized
            else:
                start_coordinates_normalized = bool(start_coordinates_normalized)

            scroll_metrics = None
            if action_type == "scroll":
                scroll_origin = (
                    coordinates or item.get("scroll_start") or item.get("scroll_origin")
                )
                scroll_direction = item.get("direction") or item.get("scroll_direction")
                scroll_metrics = _compute_scroll_metrics(
                    scroll_origin,
                    scroll_direction,
                    amount_value,
                    magnitude_value,
                    coordinates_normalized,
                )

            # Create description
            description = f"{action_name}"
            if coordinates:
                description += f" at ({coordinates})"
            if text:
                description += f": {text[:50]}"
            # ✅ Add key information for key_press actions
            if key and action_type == "key_press":
                if isinstance(key, list):
                    key_str = "+".join(str(k) for k in key)
                    description = f"Pressed keys: {key_str}"
                else:
                    description = f"Pressed key: {key}"
            if url:
                description += f" on {url}"

            submit = item.get("submit") or item.get("press_enter")
            metadata = {
                "coordinates": coordinates,
                "start_coordinates": start_coordinates,
                "target_coordinates": target_coordinates,
                "coordinates_normalized": coordinates_normalized,
                "start_coordinates_normalized": (
                    start_coordinates_normalized
                    if start_coordinates is not None
                    else None
                ),
                "target_coordinates_normalized": (
                    target_coordinates_normalized
                    if target_coordinates is not None
                    else None
                ),
                "text": text,
                "key": key,
                "raw_type": item_type,
                "direction": item.get("direction"),
                "amount": item.get("amount"),
                "magnitude": magnitude_value,
                "submit": submit,
            }

            if (start_coordinates or coordinates) and target_coordinates:
                drag_start = start_coordinates or coordinates
                metadata["drag_path"] = {
                    "start": drag_start,
                    "end": target_coordinates,
                    "coordinates_normalized": (
                        start_coordinates_normalized
                        if start_coordinates is not None
                        else coordinates_normalized
                    ),
                    "target_coordinates_normalized": target_coordinates_normalized,
                }

            if scroll_metrics:
                metadata.update(
                    {
                        "scroll_start": scroll_metrics["start"],
                        "scroll_end": scroll_metrics["end"],
                        "scroll_distance": scroll_metrics["distance"],
                        "scroll_units": scroll_metrics["units"],
                        "scroll_distance_display": scroll_metrics["display"],
                        "scroll_axis": scroll_metrics["axis"],
                        "scroll_start_normalized": scroll_metrics.get(
                            "start_normalized"
                        ),
                        "scroll_end_normalized": scroll_metrics.get("end_normalized"),
                    }
                )

            entry = {
                "id": str(uuid.uuid4()),
                "entry_type": "action",
                "sequence_index": self._timeline_sequence_index,
                "timestamp": timestamp,
                "action_type": action_type,
                "action_name": action_name,
                "description": description,
                "screenshot_path": screenshot if screenshot else None,
                "screenshot_before": screenshot_before,
                "screenshot_after": screenshot_after,
                "current_url": url if url else None,
                "status": "success",
                "metadata": metadata,
            }
            self._timeline_sequence_index += 1
            self.logger.info(
                f"📸 Action entry: before={screenshot_before}, after={screenshot_after}, main={screenshot}"
            )
            return entry

        # 5. OpenAI/Anthropic reasoning type
        if item_type == "reasoning":
            summary_chunks = item.get("summary", [])
            reasoning_text = ""
            for ch in summary_chunks:
                if (
                    isinstance(ch, dict)
                    and ch.get("type") == "summary_text"
                    and ch.get("text")
                ):
                    reasoning_text = ch["text"]
                    break

            if reasoning_text:
                entry = {
                    "id": str(uuid.uuid4()),
                    "entry_type": "model_thinking",
                    "sequence_index": self._timeline_sequence_index,
                    "timestamp": timestamp,
                    "content": reasoning_text,
                    "metadata": {},
                }
                self._timeline_sequence_index += 1
                return entry

        # Unknown type - log and skip
        self.logger.debug(
            f"⚠️ Unknown item type not converted: {item_type}, role={role}"
        )
        return None

    def _extract_local_storage(
        self, task_id: str, gym_url: str = None
    ) -> Dict[str, Any]:
        """Extract localStorage from gym by navigating to download endpoint"""
        if not self.current_task_dir:
            self.logger.warning(
                "⚠️ No task directory available for localStorage extraction"
            )
            return {"error": "No task directory available"}

        if not gym_url:
            self.logger.error("❌ No gym_url provided for localStorage extraction")
            return {"error": "gym_url is required for localStorage extraction"}

        if (
            not self.computer
            or not hasattr(self.computer, "_page")
            or not self.computer._page
        ):
            self.logger.error(
                "❌ No browser page available for localStorage extraction"
            )
            return {"error": "No browser available"}

        # Try download approach first (3 retries)
        for attempt in range(3):
            try:
                result = self._try_download_approach(task_id, gym_url, attempt + 1)
                if result and result.get("status") == "success":
                    return result
            except Exception as e:
                self.logger.warning(f"⚠️ Download attempt {attempt + 1} failed: {e}")
                if attempt == 2:
                    self.logger.error("❌ All download attempts failed")

        # Try JavaScript-based fallback method
        try:
            result = self._try_javascript_fallback(task_id, gym_url)
            if result and result.get("status") == "success":
                return result
        except Exception as e:
            self.logger.warning(f"⚠️ JavaScript fallback failed: {e}")

        # Return failure
        self.logger.error("❌ All localStorage extraction methods failed")
        return {
            "status": "failed",
            "error": "All localStorage extraction methods failed",
            "dump_filename": None,
            "keys_count": 0,
        }

    def _try_download_approach(
        self, task_id: str, gym_url: str, attempt: int
    ) -> Dict[str, Any]:
        """Try to download localStorage using the download endpoint approach"""
        import json

        page = self.computer._page

        # Set up final file path
        dump_filename = "local_storage_dump.json"
        dump_path = self.current_task_dir / dump_filename

        # Construct the localStorage download URL
        download_url = f"{gym_url.rstrip('/')}/localStorage"
        self.logger.info(f"📦 Download attempt {attempt}: {download_url}")

        # Use Playwright's download API to handle the download properly
        # Since we're using LocalPlaywrightBrowser (sync), we'll use sync methods
        try:
            # Sync Playwright - use sync context manager
            with page.expect_download() as download_info:
                page.goto(download_url, wait_until="networkidle", timeout=30000)

            # Get the download object
            download = download_info.value

            # Save the downloaded file to our task directory
            download.save_as(str(dump_path))
            self.logger.info(f"📁 Downloaded file saved to: {dump_path}")

        except Exception as download_error:
            self.logger.warning(f"⚠️ Download API failed: {download_error}")
            raise Exception(f"Download failed: {download_error}")

        # Get file info
        file_size = dump_path.stat().st_size

        # Try to count keys in the JSON file
        keys_count = 0
        try:
            with open(dump_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                keys_count = len(data) if isinstance(data, dict) else 0
        except Exception as e:
            self.logger.warning(f"⚠️ Could not parse downloaded JSON file: {e}")
            raise Exception(f"Downloaded file is not valid JSON: {e}")

        self.logger.info(
            f"💾 localStorage dump saved to: {dump_path} "
            f"({file_size:,} bytes, {keys_count} keys)"
        )

        result = {
            "status": "success",
            "dump_path": str(dump_path),
            "dump_filename": dump_filename,
            "keys_count": keys_count,
            "gym_url": gym_url,
            "download_url": download_url,
            "method": "download_endpoint",
            "attempt": attempt,
            "extracted_at": datetime.now().isoformat(),
            "task_id": task_id,
        }

        self.logger.info(
            f"✅ localStorage downloaded from endpoint (attempt {attempt}): "
            f"{keys_count} keys saved to {dump_filename}"
        )

        return result

    @with_timeout(
        timeout_seconds=300.0, timeout_exception=CriticalTimeoutError, critical=True
    )
    def _try_javascript_fallback(self, task_id: str, gym_url: str) -> Dict[str, Any]:
        """Extract localStorage using JavaScript evaluation as fallback method"""
        import json
        import time
        from pathlib import Path
        from datetime import datetime

        page = self.computer._page

        # Set up final file path
        dump_filename = "local_storage_dump.json"
        dump_path = self.current_task_dir / dump_filename

        self.logger.info(
            f"🔍 JavaScript fallback localStorage extraction for: {gym_url}"
        )

        try:
            # JavaScript code to extract localStorage (similar to the React component)
            js_code = """
            () => {
                try {
                    const storage = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key) {
                            storage[key] = localStorage.getItem(key);
                        }
                    }

                    // Also try to trigger a download programmatically (like the React component)
                    try {
                        const dataBlob = new Blob([JSON.stringify(storage, null, 2)]);
                        const url = URL.createObjectURL(dataBlob);
                        const link = document.createElement("a");
                        link.href = url;
                        link.download = "localStorage-dump.json";
                        link.style.display = "none";
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        URL.revokeObjectURL(url);
                    } catch (downloadError) {
                        console.warn("Download trigger failed:", downloadError);
                    }

                    return {
                        success: true,
                        data: storage,
                        keysCount: Object.keys(storage).length
                    };
                } catch (error) {
                    return {
                        success: false,
                        error: error.message,
                        data: {},
                        keysCount: 0
                    };
                }
            }
            """

            # Execute JavaScript to get localStorage (sync Playwright)
            result = page.evaluate(js_code)

            if not result.get("success", False):
                raise Exception(
                    f"JavaScript extraction failed: {result.get('error', 'Unknown error')}"
                )

            localStorage_data = result.get("data", {})
            keys_count = result.get("keysCount", 0)

            # Save the extracted data to file
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(localStorage_data, f, indent=2, ensure_ascii=False)

            # Get file info
            file_size = dump_path.stat().st_size

            self.logger.info(
                f"💾 localStorage extracted via JavaScript fallback: {dump_path} "
                f"({file_size:,} bytes, {keys_count} keys)"
            )

            result = {
                "status": "success",
                "dump_path": str(dump_path),
                "dump_filename": dump_filename,
                "keys_count": keys_count,
                "gym_url": gym_url,
                "method": "javascript_fallback",
                "extracted_at": datetime.now().isoformat(),
                "task_id": task_id,
            }

            self.logger.info(
                f"✅ localStorage extracted via JavaScript fallback: "
                f"{keys_count} keys saved to {dump_filename}"
            )

            return result

        except Exception as e:
            self.logger.warning(f"⚠️ JavaScript fallback extraction failed: {e}")
            raise Exception(f"JavaScript fallback extraction failed: {e}")

    @staticmethod
    def cleanup_iteration_directory(
        execution_folder_name: str, task_id: str, iteration_number: int
    ) -> bool:
        """
        Safely clean up iteration directory content for rerun

        Args:
            execution_folder_name: Name of the execution folder (e.g., "batch_Zen_Desk_Gym_-_0001_20251017_082035_ZEND-TICKET-CREATE-001_anthropic")
            task_id: Task ID (e.g., "ZEND-TICKET-CREATE-001")
            iteration_number: Iteration number to clean up

        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        import shutil
        import logging
        from pathlib import Path
        from app.core.config import settings

        logger = logging.getLogger(__name__)

        try:
            # Construct the iteration directory path
            # Structure: results/execution_folder_name/task_id/iteration_N/
            base_results_dir = Path(settings.RESULTS_DIR)
            execution_dir = base_results_dir / execution_folder_name
            task_dir = execution_dir / task_id
            iteration_dir = task_dir / f"iteration_{iteration_number}"

            logger.info(f"🧹 Starting cleanup of iteration directory: {iteration_dir}")
            logger.info(f"🔍 Execution folder: {execution_folder_name}")
            logger.info(f"🔍 Task ID: {task_id}")
            logger.info(f"🔍 Iteration number: {iteration_number}")

            # Safety check: Ensure we're only deleting inside iteration_N folder
            if not iteration_dir.exists():
                logger.info(f"ℹ️ Iteration directory does not exist: {iteration_dir}")
                return True  # Not an error if directory doesn't exist

            # Double-check that this is actually an iteration directory
            if not iteration_dir.name.startswith("iteration_"):
                logger.error(
                    f"❌ Safety check failed: Directory name doesn't start with 'iteration_': {iteration_dir}"
                )
                return False

            # Check that we're inside the results directory
            try:
                iteration_dir.relative_to(base_results_dir)
            except ValueError:
                logger.error(
                    f"❌ Safety check failed: Directory is outside results directory: {iteration_dir}"
                )
                return False

            # Additional safety check: ensure we're in a batch or playground directory
            if not (
                execution_folder_name.startswith("batch_")
                or execution_folder_name.startswith("playground_")
            ):
                logger.error(
                    f"❌ Safety check failed: Execution folder doesn't start with 'batch_' or 'playground_': {execution_folder_name}"
                )
                return False

            # Remove all contents of the iteration directory
            if iteration_dir.is_dir():
                shutil.rmtree(iteration_dir)
                logger.info(
                    f"✅ Successfully cleaned up iteration directory: {iteration_dir}"
                )
            else:
                logger.warning(f"⚠️ Path exists but is not a directory: {iteration_dir}")
                return False

            return True

        except Exception as e:
            logger.error(
                f"❌ Failed to cleanup iteration directory {iteration_dir}: {e}"
            )
            return False
