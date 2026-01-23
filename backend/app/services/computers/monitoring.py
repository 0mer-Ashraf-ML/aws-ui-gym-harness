"""
Comprehensive monitoring and logging system for computer operations.
"""

import asyncio
import logging
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@dataclass
class OperationMetrics:
    """Metrics for a single operation."""
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> Optional[float]:
        """Get operation duration in seconds."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time
    
    @property
    def is_completed(self) -> bool:
        """Check if operation is completed."""
        return self.end_time is not None


@dataclass
class HealthMetrics:
    """Health metrics for computer resources."""
    timestamp: datetime
    browser_healthy: bool = False
    page_healthy: bool = False
    playwright_healthy: bool = False
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    active_connections: int = 0
    error_count: int = 0
    success_rate: float = 0.0


class PerformanceMonitor:
    """Monitors performance metrics for computer operations."""
    
    def __init__(self, max_history: int = 1000, logger_instance: Optional[logging.Logger] = None):
        self.log = logger_instance or logger
        self.max_history = max_history
        self._operations: deque = deque(maxlen=max_history)
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._total_duration: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def start_operation(self, operation_name: str, metadata: Optional[Dict[str, Any]] = None) -> OperationMetrics:
        """Start tracking an operation."""
        metrics = OperationMetrics(
            operation_name=operation_name,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        with self._lock:
            self._operations.append(metrics)
            self._operation_counts[operation_name] += 1
        
        self.log.debug(f"Started operation: {operation_name}")
        return metrics
    
    def end_operation(self, metrics: OperationMetrics, success: bool = True, error_message: Optional[str] = None):
        """End tracking an operation."""
        metrics.end_time = time.time()
        metrics.success = success
        metrics.error_message = error_message
        
        with self._lock:
            if not success:
                self._error_counts[metrics.operation_name] += 1
            
            if metrics.duration is not None:
                self._total_duration[metrics.operation_name] += metrics.duration
        
        status = "SUCCESS" if success else "FAILED"
        self.log.info(f"Operation {metrics.operation_name} {status} in {metrics.duration:.3f}s")
        
        if error_message:
            self.log.error(f"Operation {metrics.operation_name} error: {error_message}")
    
    def get_operation_stats(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for operations."""
        with self._lock:
            if operation_name:
                # Stats for specific operation
                total_ops = self._operation_counts.get(operation_name, 0)
                total_errors = self._error_counts.get(operation_name, 0)
                total_duration = self._total_duration.get(operation_name, 0.0)
                
                if total_ops == 0:
                    return {
                        "operation_name": operation_name,
                        "total_operations": 0,
                        "success_rate": 0.0,
                        "average_duration": 0.0,
                        "error_count": 0
                    }
                
                return {
                    "operation_name": operation_name,
                    "total_operations": total_ops,
                    "success_rate": (total_ops - total_errors) / total_ops * 100,
                    "average_duration": total_duration / total_ops,
                    "error_count": total_errors
                }
            else:
                # Overall stats
                total_ops = sum(self._operation_counts.values())
                total_errors = sum(self._error_counts.values())
                total_duration = sum(self._total_duration.values())
                
                if total_ops == 0:
                    return {
                        "total_operations": 0,
                        "success_rate": 0.0,
                        "average_duration": 0.0,
                        "error_count": 0,
                        "operations": {}
                    }
                
                operations = {}
                for op_name in self._operation_counts:
                    operations[op_name] = self.get_operation_stats(op_name)
                
                return {
                    "total_operations": total_ops,
                    "success_rate": (total_ops - total_errors) / total_ops * 100,
                    "average_duration": total_duration / total_ops,
                    "error_count": total_errors,
                    "operations": operations
                }
    
    def get_recent_operations(self, count: int = 10) -> List[OperationMetrics]:
        """Get recent operations."""
        with self._lock:
            return list(self._operations)[-count:]


class HealthMonitor:
    """Monitors health of computer resources."""
    
    def __init__(self, check_interval: float = 30.0, logger_instance: Optional[logging.Logger] = None):
        self.log = logger_instance or logger
        self.check_interval = check_interval
        self._health_history: deque = deque(maxlen=100)
        self._is_monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._browser = None
        self._page = None
        self._playwright = None
    
    def set_resources(self, browser=None, page=None, playwright=None):
        """Set resources to monitor."""
        self._browser = browser
        self._page = page
        self._playwright = playwright
    
    def check_health(self) -> HealthMetrics:
        """Perform a health check."""
        metrics = HealthMetrics(timestamp=datetime.now())
        
        try:
            # Check browser health
            if self._browser:
                try:
                    if hasattr(self._browser, 'is_connected'):
                        metrics.browser_healthy = self._browser.is_connected()
                    elif hasattr(self._browser, 'contexts'):
                        metrics.browser_healthy = len(self._browser.contexts) > 0
                    else:
                        metrics.browser_healthy = True
                except SoftTimeLimitExceeded:
                    raise
                except Exception:
                    metrics.browser_healthy = False
            
            # Check page health
            if self._page:
                try:
                    if hasattr(self._page, 'is_closed'):
                        metrics.page_healthy = not self._page.is_closed()
                    else:
                        # Try to access page URL as a basic health check
                        _ = self._page.url
                        metrics.page_healthy = True
                except SoftTimeLimitExceeded:
                    raise
                except Exception:
                    metrics.page_healthy = False
            
            # Check playwright health
            if self._playwright:
                try:
                    metrics.playwright_healthy = (hasattr(self._playwright, 'chromium') or 
                                                hasattr(self._playwright, 'firefox') or 
                                                hasattr(self._playwright, 'webkit'))
                except SoftTimeLimitExceeded:
                    raise
                except Exception:
                    metrics.playwright_healthy = False
            
            # Get system metrics
            try:
                import psutil
                process = psutil.Process()
                metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024
                metrics.cpu_usage_percent = process.cpu_percent()
            except ImportError:
                # psutil not available
                pass
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                self.log.warning(f"Could not get system metrics: {e}")
            
        except SoftTimeLimitExceeded:
            raise
        except Exception as e:
            self.log.error(f"Health check failed: {e}")
        
        self._health_history.append(metrics)
        return metrics
    
    def start_monitoring(self):
        """Start continuous health monitoring."""
        if self._is_monitoring:
            return
        
        self._is_monitoring = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.log.info("Health monitoring started")
    
    def stop_monitoring(self):
        """Stop continuous health monitoring."""
        if not self._is_monitoring:
            return
        
        self._is_monitoring = False
        self._stop_event.set()
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        
        self.log.info("Health monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                health_metrics = self.check_health()
                
                # Log health status
                if not health_metrics.browser_healthy or not health_metrics.page_healthy:
                    self.log.warning(f"Health check failed - Browser: {health_metrics.browser_healthy}, Page: {health_metrics.page_healthy}")
                
                # Wait for next check
                self._stop_event.wait(self.check_interval)
                
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                self.log.error(f"Error in health monitoring loop: {e}")
                self._stop_event.wait(5.0)  # Wait 5 seconds before retrying
    
    def get_health_history(self, count: int = 10) -> List[HealthMetrics]:
        """Get recent health metrics."""
        return list(self._health_history)[-count:]
    
    def get_current_health(self) -> Optional[HealthMetrics]:
        """Get the most recent health metrics."""
        if self._health_history:
            return self._health_history[-1]
        return None


class ComputerLogger:
    """Enhanced logger for computer operations."""
    
    def __init__(self, name: str, logger_instance: Optional[logging.Logger] = None):
        self.name = name
        self.log = logger_instance or logger
        self._operation_stack: List[str] = []
    
    def push_operation(self, operation: str):
        """Push an operation onto the stack."""
        self._operation_stack.append(operation)
        self.log.debug(f"[{self.name}] Starting operation: {operation}")
    
    def pop_operation(self, operation: str, success: bool = True, duration: Optional[float] = None):
        """Pop an operation from the stack."""
        if self._operation_stack and self._operation_stack[-1] == operation:
            self._operation_stack.pop()
        
        status = "SUCCESS" if success else "FAILED"
        duration_str = f" in {duration:.3f}s" if duration is not None else ""
        self.log.info(f"[{self.name}] Operation {operation} {status}{duration_str}")
    
    def log_operation(self, operation: str, message: str, level: int = logging.INFO):
        """Log a message for a specific operation."""
        context = " -> ".join(self._operation_stack + [operation])
        self.log.log(level, f"[{self.name}] [{context}] {message}")
    
    def log_error(self, operation: str, error: Exception, context: Optional[str] = None):
        """Log an error for a specific operation."""
        context_str = f" [{context}]" if context else ""
        self.log.error(f"[{self.name}] Operation {operation}{context_str} failed: {error}")
    
    def log_performance(self, operation: str, metrics: Dict[str, Any]):
        """Log performance metrics."""
        self.log.info(f"[{self.name}] Performance metrics for {operation}: {metrics}")


def monitor_operation(operation_name: str, monitor: PerformanceMonitor, logger_instance: Optional[logging.Logger] = None):
    """Decorator to monitor an operation."""
    def decorator(func: Callable) -> Callable:
        def sync_wrapper(*args, **kwargs):
            log = logger_instance or logger
            metrics = monitor.start_operation(operation_name)
            
            try:
                result = func(*args, **kwargs)
                monitor.end_operation(metrics, success=True)
                return result
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                monitor.end_operation(metrics, success=False, error_message=str(e))
                log.error(f"Operation {operation_name} failed: {e}")
                raise
        
        async def async_wrapper(*args, **kwargs):
            log = logger_instance or logger
            metrics = monitor.start_operation(operation_name)
            
            try:
                result = await func(*args, **kwargs)
                monitor.end_operation(metrics, success=True)
                return result
            except SoftTimeLimitExceeded:
                raise
            except Exception as e:
                monitor.end_operation(metrics, success=False, error_message=str(e))
                log.error(f"Async operation {operation_name} failed: {e}")
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
