"""
Error Recovery & Health Monitoring — auto-restart, circuit breakers, health checks.
"""
import time
import threading
import traceback
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

from core.config import config
from core.notifier import notify


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    RECOVERING = "recovering"


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: HealthStatus = HealthStatus.HEALTHY
    last_check: float = 0
    error_count: int = 0
    last_error: str = ""
    recovery_attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""
    
    def __init__(self, name: str, failure_threshold: int = 5, 
                 recovery_timeout: float = 60.0, expected_exception: type = Exception):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time = 0
        self._state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()
    
    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = "half-open"
            return self._state
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = "half-open"
                else:
                    raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = "closed"
    
    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = "open"
    
    def reset(self):
        """Manually reset the circuit breaker."""
        with self._lock:
            self._failure_count = 0
            self._state = "closed"


class HealthMonitor:
    """Monitor health of all components and trigger recovery."""
    
    def __init__(self, jarvis_instance=None):
        self.jarvis = jarvis_instance
        self.components: Dict[str, ComponentHealth] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._check_interval = 30  # seconds
        self._recovery_callbacks: Dict[str, Callable] = {}
        self._lock = threading.Lock()
    
    def register_component(self, name: str, check_func: Callable[[], bool], 
                          recovery_func: Optional[Callable] = None):
        """Register a component for health monitoring."""
        with self._lock:
            self.components[name] = ComponentHealth(name=name)
            self.circuit_breakers[name] = CircuitBreaker(name)
            if recovery_func:
                self._recovery_callbacks[name] = recovery_func
    
    def start(self):
        """Start the health monitor."""
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop(self):
        """Stop the health monitor."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._check_all_components()
            except Exception as e:
                print(f"[HealthMonitor] Error in monitor loop: {e}")
            time.sleep(self._check_interval)
    
    def _check_all_components(self):
        """Check health of all registered components."""
        with self._lock:
            components = dict(self.components)
            breakers = dict(self.circuit_breakers)
        
        for name, health in components.items():
            try:
                # Get the check function from jarvis modules
                check_func = getattr(self.jarvis, f"_check_{name}", None) if self.jarvis else None
                
                if check_func:
                    # Run check in circuit breaker
                    breaker = breakers.get(name)
                    if breaker:
                        try:
                            breaker.call(check_func, announce=False)
                            self._report_healthy(name)
                        except Exception as e:
                            self._report_unhealthy(name, str(e))
                    else:
                        check_func(announce=False)
                        self._report_healthy(name)
                else:
                    # No check function, assume healthy if module loaded
                    if name in jarvis_main.modules and jarvis_main.modules[name]:
                        self._report_healthy(name)
                    else:
                        self._report_unhealthy(name, "Module not loaded")
                        
            except Exception as e:
                self._report_unhealthy(name, str(e))
    
    def _report_healthy(self, name: str):
        with self._lock:
            if name in self.components:
                self.components[name].status = HealthStatus.HEALTHY
                self.components[name].last_check = time.time()
                self.components[name].error_count = 0
    
    def _report_unhealthy(self, name: str, error: str):
        with self._lock:
            if name in self.components:
                health = self.components[name]
                health.status = HealthStatus.UNHEALTHY
                health.last_check = time.time()
                health.error_count += 1
                health.last_error = error
                
                # Trigger recovery if needed
                if health.error_count >= 3 and health.recovery_attempts < 3:
                    self._trigger_recovery(name)
    
    def _trigger_recovery(self, name: str):
        """Attempt to recover a failed component."""
        with self._lock:
            if name in self.components:
                health = self.components[name]
                health.status = HealthStatus.RECOVERING
                health.recovery_attempts += 1
        
        print(f"[HealthMonitor] Attempting recovery for {name} (attempt {health.recovery_attempts})")
        
        recovery_func = self._recovery_callbacks.get(name)
        if recovery_func:
            try:
                recovery_func()
                time.sleep(2)  # Give time to recover
                # Re-check
                self._check_component(name)
            except Exception as e:
                print(f"[HealthMonitor] Recovery failed for {name}: {e}")
        else:
            # Default recovery: reload module
            self._reload_module(name)
    
    def _reload_module(self, name: str):
        """Reload a module."""
        try:
            # This would need integration with plugin manager
            print(f"[HealthMonitor] Module reload not implemented for {name}")
        except Exception as e:
            print(f"[HealthMonitor] Reload error: {e}")
    
    def _check_component(self, name: str):
        """Check a single component."""
        with self._lock:
            health = self.components.get(name)
            breaker = self.circuit_breakers.get(name)
        
        if health and breaker:
            check_func = getattr(self.jarvis, f"_check_{name}", None) if self.jarvis else None
            if check_func:
                try:
                    breaker.call(check_func, announce=False)
                    self._report_healthy(name)
                except Exception as e:
                    self._report_unhealthy(name, str(e))
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get health status of all components."""
        with self._lock:
            return {
                name: {
                    "status": health.status.value,
                    "last_check": health.last_check,
                    "error_count": health.error_count,
                    "last_error": health.last_error,
                    "recovery_attempts": health.recovery_attempts,
                    "circuit_breaker": self.circuit_breakers[name].state if name in self.circuit_breakers else "unknown"
                }
                for name, health in self.components.items()
            }
    
    def force_recovery(self, name: str) -> bool:
        """Manually trigger recovery for a component."""
        if name in self.components:
            self._trigger_recovery(name)
            return True
        return False


def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for automatic retry with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        print(f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
            raise last_exception
        return wrapper
    return decorator


def safe_execute(func: Callable, *args, default=None, **kwargs):
    """Execute function safely, returning default on error."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[SafeExecute] {func.__name__} failed: {e}")
        return default


# Import here to avoid circular dependency
import jarvis as jarvis_main