"""
Resource management and cleanup utilities for computer operations.
"""

import asyncio
import logging
import threading
import time
import weakref
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manages computer resources and ensures proper cleanup."""
    
    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self.log = logger_instance or logger
        self._resources: Dict[str, Any] = {}
        self._cleanup_callbacks: List[callable] = []
        self._lock = threading.Lock()
        self._is_cleaning_up = False
    
    def register_resource(self, name: str, resource: Any, cleanup_callback: Optional[callable] = None):
        """Register a resource for tracking and cleanup."""
        with self._lock:
            self._resources[name] = resource
            if cleanup_callback:
                self._cleanup_callbacks.append(cleanup_callback)
            self.log.debug(f"Registered resource: {name}")
    
    def unregister_resource(self, name: str):
        """Unregister a resource."""
        with self._lock:
            if name in self._resources:
                del self._resources[name]
                self.log.debug(f"Unregistered resource: {name}")
    
    def get_resource(self, name: str) -> Optional[Any]:
        """Get a registered resource."""
        with self._lock:
            return self._resources.get(name)
    
    def cleanup_all(self):
        """Clean up all registered resources."""
        if self._is_cleaning_up:
            return
        
        self._is_cleaning_up = True
        self.log.info("Starting resource cleanup...")
        
        try:
            # Run cleanup callbacks
            for callback in self._cleanup_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.log.warning(f"Cleanup callback failed: {e}")
            
            # Clear resources
            with self._lock:
                self._resources.clear()
                self._cleanup_callbacks.clear()
            
            self.log.info("Resource cleanup completed")
        except Exception as e:
            self.log.error(f"Error during resource cleanup: {e}")
        finally:
            self._is_cleaning_up = False
    
    def get_resource_count(self) -> int:
        """Get the number of registered resources."""
        with self._lock:
            return len(self._resources)


class BrowserResourceManager(ResourceManager):
    """Specialized resource manager for browser resources."""
    
    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        super().__init__(logger_instance)
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
    
    def register_browser(self, browser, context=None, page=None, playwright=None):
        """Register browser resources."""
        self._browser = browser
        self._context = context
        self._page = page
        self._playwright = playwright
        
        self.register_resource("browser", browser)
        if context:
            self.register_resource("context", context)
        if page:
            self.register_resource("page", page)
        if playwright:
            self.register_resource("playwright", playwright)
    
    def cleanup_browser(self):
        """Clean up browser resources safely."""
        self.log.info("Starting browser cleanup...")
        
        try:
            # Close page first
            if self._page:
                try:
                    if hasattr(self._page, 'close') and not self._page.is_closed():
                        self._page.close()
                        self.log.debug("Page closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing page: {e}")
                finally:
                    self._page = None
            
            # Close context
            if self._context:
                try:
                    if hasattr(self._context, 'close'):
                        self._context.close()
                        self.log.debug("Context closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing context: {e}")
                finally:
                    self._context = None
            
            # Close browser
            if self._browser:
                try:
                    if hasattr(self._browser, 'close'):
                        self._browser.close()
                        self.log.debug("Browser closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing browser: {e}")
                finally:
                    self._browser = None
            
            # Stop playwright
            if self._playwright:
                try:
                    if hasattr(self._playwright, 'stop'):
                        self._playwright.stop()
                        self.log.debug("Playwright stopped successfully")
                except Exception as e:
                    self.log.warning(f"Error stopping playwright: {e}")
                finally:
                    self._playwright = None
            
            self.log.info("Browser cleanup completed")
        except Exception as e:
            self.log.error(f"Error during browser cleanup: {e}")
        finally:
            self.cleanup_all()


class AsyncBrowserResourceManager(BrowserResourceManager):
    """Async version of browser resource manager."""
    
    async def cleanup_browser_async(self):
        """Clean up browser resources asynchronously."""
        self.log.info("Starting async browser cleanup...")
        
        try:
            # Close page first
            if self._page:
                try:
                    if hasattr(self._page, 'close') and not self._page.is_closed():
                        await self._page.close()
                        self.log.debug("Page closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing page: {e}")
                finally:
                    self._page = None
            
            # Close context
            if self._context:
                try:
                    if hasattr(self._context, 'close'):
                        await self._context.close()
                        self.log.debug("Context closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing context: {e}")
                finally:
                    self._context = None
            
            # Close browser
            if self._browser:
                try:
                    if hasattr(self._browser, 'close'):
                        await self._browser.close()
                        self.log.debug("Browser closed successfully")
                except Exception as e:
                    self.log.warning(f"Error closing browser: {e}")
                finally:
                    self._browser = None
            
            # Stop playwright
            if self._playwright:
                try:
                    if hasattr(self._playwright, 'stop'):
                        await self._playwright.stop()
                        self.log.debug("Playwright stopped successfully")
                except Exception as e:
                    self.log.warning(f"Error stopping playwright: {e}")
                finally:
                    self._playwright = None
            
            self.log.info("Async browser cleanup completed")
        except Exception as e:
            self.log.error(f"Error during async browser cleanup: {e}")
        finally:
            self.cleanup_all()


@contextmanager
def managed_browser_resources(logger_instance: Optional[logging.Logger] = None):
    """Context manager for browser resources."""
    manager = BrowserResourceManager(logger_instance)
    try:
        yield manager
    finally:
        manager.cleanup_browser()


@asynccontextmanager
async def managed_async_browser_resources(logger_instance: Optional[logging.Logger] = None):
    """Async context manager for browser resources."""
    manager = AsyncBrowserResourceManager(logger_instance)
    try:
        yield manager
    finally:
        await manager.cleanup_browser_async()


class ConnectionPool:
    """Simple connection pool for managing browser connections."""
    
    def __init__(self, max_connections: int = 5, logger_instance: Optional[logging.Logger] = None):
        self.max_connections = max_connections
        self.log = logger_instance or logger
        self._connections: List[Any] = []
        self._lock = threading.Lock()
    
    def get_connection(self) -> Optional[Any]:
        """Get an available connection from the pool."""
        with self._lock:
            if self._connections:
                return self._connections.pop()
            return None
    
    def return_connection(self, connection: Any):
        """Return a connection to the pool."""
        with self._lock:
            if len(self._connections) < self.max_connections:
                self._connections.append(connection)
            else:
                # Pool is full, close the connection
                try:
                    if hasattr(connection, 'close'):
                        connection.close()
                except Exception as e:
                    self.log.warning(f"Error closing connection: {e}")
    
    def cleanup_all(self):
        """Clean up all connections in the pool."""
        with self._lock:
            for connection in self._connections:
                try:
                    if hasattr(connection, 'close'):
                        connection.close()
                except Exception as e:
                    self.log.warning(f"Error closing connection: {e}")
            self._connections.clear()
    
    def get_pool_size(self) -> int:
        """Get the current pool size."""
        with self._lock:
            return len(self._connections)
