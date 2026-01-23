"""
Comprehensive error handling and retry mechanisms for computer operations.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, Type, Union

logger = logging.getLogger(__name__)


class ComputerError(Exception):
    """Base exception for computer-related errors."""
    pass


class BrowserError(ComputerError):
    """Browser-specific errors."""
    pass


class NavigationError(ComputerError):
    """Navigation-related errors."""
    pass


class ScreenshotError(ComputerError):
    """Screenshot-related errors."""
    pass


class TimeoutError(ComputerError):
    """Timeout-related errors."""
    pass


class CriticalAPIError(ComputerError):
    """Critical API errors that should cause immediate task failure."""
    pass


class CriticalTimeoutError(ComputerError):
    """Critical timeout errors that should crash the task immediately."""
    pass


class CriticalErrorTracker:
    """Tracks critical errors and crashes iterations after threshold."""
    
    def __init__(self, max_critical_errors: int = 3):
        self.max_critical_errors = max_critical_errors
        self.critical_error_count = 0
        self.error_history = []
    
    def record_critical_error(self, error: Exception, context: str = ""):
        """Record a critical error and check if threshold is exceeded."""
        self.critical_error_count += 1
        error_info = {
            'error': str(error),
            'error_type': type(error).__name__,
            'context': context,
            'timestamp': time.time()
        }
        self.error_history.append(error_info)
        
        logger.error(f"🚨 CRITICAL ERROR #{self.critical_error_count}: {error}")
        logger.error(f"   Context: {context}")
        logger.error(f"   Error type: {type(error).__name__}")
        
        if self.critical_error_count >= self.max_critical_errors:
            logger.error(f"💥 CRITICAL ERROR THRESHOLD EXCEEDED ({self.max_critical_errors})")
            logger.error(f"   Total critical errors: {self.critical_error_count}")
            logger.error(f"   Error history: {self.error_history}")
            raise CriticalTimeoutError(
                f"CRITICAL: Task crashed after {self.max_critical_errors} critical errors. "
                f"Error history: {[e['error'] for e in self.error_history]}"
            )
    
    def reset(self):
        """Reset error tracking."""
        self.critical_error_count = 0
        self.error_history = []
    
    def get_error_summary(self) -> dict:
        """Get summary of critical errors."""
        return {
            'critical_error_count': self.critical_error_count,
            'max_critical_errors': self.max_critical_errors,
            'threshold_exceeded': self.critical_error_count >= self.max_critical_errors,
            'error_history': self.error_history
        }


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
    critical: bool = False
):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called on each retry
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            # Include CriticalTimeoutError in exceptions to catch, so we can retry it
            exceptions_to_catch = exceptions + (CriticalTimeoutError,)
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions_to_catch as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        if critical or isinstance(e, CriticalTimeoutError):
                            # If this was a critical operation or a critical timeout, raise CriticalTimeoutError on final failure
                            raise CriticalTimeoutError(f"CRITICAL: Function {func.__name__} failed after {max_retries} retries: {e} - task should crash immediately")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    if jitter:
                        import random
                        delay *= (0.5 + random.random() * 0.5)  # Add 50% jitter
                    
                    # Log retry attempt, including for critical timeouts
                    error_type = "critical timeout" if isinstance(e, CriticalTimeoutError) else "error"
                    logger.warning(f"Function {func.__name__} failed with {error_type} (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s...")
                    
                    if on_retry:
                        on_retry(attempt, e, delay)
                    
                    # Reset any signal alarms before retrying to prevent interference
                    import signal
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    
                    time.sleep(delay)
            
            raise last_exception
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            # Include CriticalTimeoutError in exceptions to catch, so we can retry it
            exceptions_to_catch = exceptions + (CriticalTimeoutError,)
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions_to_catch as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Async function {func.__name__} failed after {max_retries} retries: {e}")
                        if critical or isinstance(e, CriticalTimeoutError):
                            # If this was a critical operation or a critical timeout, raise CriticalTimeoutError on final failure
                            raise CriticalTimeoutError(f"CRITICAL: Async function {func.__name__} failed after {max_retries} retries: {e} - task should crash immediately")
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    
                    if jitter:
                        import random
                        delay *= (0.5 + random.random() * 0.5)  # Add 50% jitter
                    
                    # Log retry attempt, including for critical timeouts
                    error_type = "critical timeout" if isinstance(e, CriticalTimeoutError) else "error"
                    logger.warning(f"Async function {func.__name__} failed with {error_type} (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s...")
                    
                    if on_retry:
                        on_retry(attempt, e, delay)
                    
                    # Reset any signal alarms before retrying to prevent interference
                    import signal
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def with_timeout(timeout_seconds: float, timeout_exception: Type[Exception] = TimeoutError, critical: bool = False):
    """
    Enhanced timeout decorator with better reliability in Celery workers.
    
    Args:
        timeout_seconds: Timeout in seconds
        timeout_exception: Exception to raise on timeout
        critical: If True, raises CriticalTimeoutError instead of the specified exception
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            import signal
            import threading
            import multiprocessing
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            
            def timeout_handler(signum, frame):
                # Raise appropriate exception based on critical flag
                if critical:
                    raise CriticalTimeoutError(f"CRITICAL: Function {func.__name__} timed out after {timeout_seconds} seconds - task should crash immediately")
                else:
                    raise timeout_exception(f"Function {func.__name__} timed out after {timeout_seconds} seconds")
            
            # Try signal-based timeout first (works well in Celery workers)
            try:
                if threading.current_thread() is threading.main_thread():
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(int(timeout_seconds))
                    
                    try:
                        result = func(*args, **kwargs)
                        return result
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
                else:
                    # For worker threads, use ThreadPoolExecutor as fallback
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(func, *args, **kwargs)
                        try:
                            result = future.result(timeout=timeout_seconds)
                            return result
                        except FutureTimeoutError:
                            logger.warning(f"Function {func.__name__} timed out after {timeout_seconds}s - forcing cancellation")
                            future.cancel()
                            
                            # Force garbage collection to clean up resources
                            try:
                                import gc
                                gc.collect()
                            except Exception:
                                pass
                            
                            if critical:
                                raise CriticalTimeoutError(f"CRITICAL: Function {func.__name__} timed out after {timeout_seconds} seconds - task should crash immediately")
                            else:
                                raise timeout_exception(f"Function {func.__name__} timed out after {timeout_seconds} seconds")
                                
            except Exception as e:
                if isinstance(e, timeout_exception):
                    raise
                else:
                    # If all timeout methods fail, raise the original exception
                    logger.error(f"All timeout methods failed for {func.__name__}: {e}")
                    if critical:
                        raise CriticalTimeoutError(f"CRITICAL: Function {func.__name__} failed with timeout issues: {e}")
                    else:
                        raise timeout_exception(f"Function {func.__name__} failed with timeout issues: {e}")
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                if critical:
                    raise CriticalTimeoutError(f"CRITICAL: Async function {func.__name__} timed out after {timeout_seconds} seconds - task should crash immediately")
                else:
                    raise timeout_exception(f"Async function {func.__name__} timed out after {timeout_seconds} seconds")
        
        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def safe_execute(
    func: Callable,
    *args,
    default_return: Any = None,
    exceptions: tuple = (Exception,),
    logger_instance: Optional[logging.Logger] = None,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling.
    
    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Value to return if function fails
        exceptions: Tuple of exceptions to catch
        logger_instance: Logger instance to use
        **kwargs: Function keyword arguments
    
    Returns:
        Function result or default_return if function fails
    """
    log = logger_instance or logger
    
    try:
        return func(*args, **kwargs)
    except exceptions as e:
        log.warning(f"Safe execution of {func.__name__} failed: {e}")
        return default_return


async def safe_execute_async(
    func: Callable,
    *args,
    default_return: Any = None,
    exceptions: tuple = (Exception,),
    logger_instance: Optional[logging.Logger] = None,
    **kwargs
) -> Any:
    """
    Safely execute an async function with error handling.
    
    Args:
        func: Async function to execute
        *args: Function arguments
        default_return: Value to return if function fails
        exceptions: Tuple of exceptions to catch
        logger_instance: Logger instance to use
        **kwargs: Function keyword arguments
    
    Returns:
        Function result or default_return if function fails
    """
    log = logger_instance or logger
    
    try:
        return await func(*args, **kwargs)
    except exceptions as e:
        log.warning(f"Safe async execution of {func.__name__} failed: {e}")
        return default_return


class HealthChecker:
    """Health checker for computer resources."""
    
    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self.log = logger_instance or logger
        self.health_status = {}
    
    def check_browser_health(self, browser) -> bool:
        """Check if browser is healthy."""
        try:
            if not browser:
                return False
            
            # Check if browser is connected
            if hasattr(browser, 'is_connected'):
                return browser.is_connected()
            
            # Check if browser has contexts
            if hasattr(browser, 'contexts'):
                return len(browser.contexts) > 0
            
            return True
        except Exception as e:
            self.log.warning(f"Browser health check failed: {e}")
            return False
    
    def check_page_health(self, page) -> bool:
        """Check if page is healthy."""
        try:
            if not page:
                return False
            
            # Check if page is closed
            if hasattr(page, 'is_closed'):
                return not page.is_closed()
            
            # Try to get page URL (basic connectivity test)
            page.url
            return True
        except Exception as e:
            self.log.warning(f"Page health check failed: {e}")
            return False
    
    def check_playwright_health(self, playwright) -> bool:
        """Check if playwright instance is healthy."""
        try:
            if not playwright:
                return False
            
            # Basic check - playwright should have browser_type (chromium, firefox, or webkit)
            return (hasattr(playwright, 'chromium') or 
                    hasattr(playwright, 'firefox') or 
                    hasattr(playwright, 'webkit'))
        except Exception as e:
            self.log.warning(f"Playwright health check failed: {e}")
            return False
    
    def get_health_status(self) -> dict:
        """Get overall health status."""
        return self.health_status.copy()
