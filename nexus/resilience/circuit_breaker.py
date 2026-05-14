"""Circuit Breaker pattern implementation for tool resilience.

Prevents cascading failures by temporarily disabling failing tools.
States: CLOSED (normal) -> OPEN (failing) -> HALF_OPEN (testing recovery)
"""

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeVar

from ..utils import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout: float = 30.0
    half_open_max_calls: int = 3
    excluded_exceptions: tuple = ()


@dataclass
class CircuitBreakerStats:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_execution_time: float = 0.0


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is OPEN and rejecting calls."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker '{name}' is OPEN. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """Circuit breaker for tool calls.

    Monitors failures and opens the circuit when threshold is exceeded.
    Allows recovery testing after cooldown period.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        self.stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.config.timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0
                self.stats.state_changes += 1
                logger.info(f"Circuit breaker '{self.name}' transitioned to HALF_OPEN")
        return self._state

    def _should_record_failure(self, exception: Exception) -> bool:
        for exc_type in self.config.excluded_exceptions:
            if isinstance(exception, exc_type):
                return False
        return True

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a call through the circuit breaker."""
        async with self._lock:
            self.stats.total_calls += 1
            current_state = self.state

            if current_state == CircuitState.OPEN:
                self.stats.rejected_calls += 1
                retry_after = self.config.timeout - (time.time() - self._opened_at)
                raise CircuitBreakerOpen(self.name, max(0, retry_after))

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self.stats.rejected_calls += 1
                    raise CircuitBreakerOpen(self.name, self.config.timeout)
                self._half_open_calls += 1

        start = time.time()
        try:
            result = await func(*args, **kwargs)
            await self._record_success(time.time() - start)
            return result
        except Exception as e:
            await self._record_failure(e, time.time() - start)
            raise

    async def _record_success(self, duration: float) -> None:
        async with self._lock:
            self.stats.successful_calls += 1
            self.stats.last_success = time.time()
            self.stats.consecutive_successes += 1
            self.stats.consecutive_failures = 0
            self.stats.total_execution_time += duration

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self.stats.state_changes += 1
                    logger.info(f"Circuit breaker '{self.name}' CLOSED after recovery")

    async def _record_failure(self, exception: Exception, duration: float) -> None:
        if not self._should_record_failure(exception):
            return

        async with self._lock:
            self.stats.failed_calls += 1
            self.stats.last_failure = time.time()
            self.stats.consecutive_failures += 1
            self.stats.consecutive_successes = 0
            self.stats.total_execution_time += duration

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                self.stats.state_changes += 1
                logger.warning(f"Circuit breaker '{self.name}' OPENED from HALF_OPEN on failure")
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
                    self.stats.state_changes += 1
                    logger.warning(f"Circuit breaker '{self.name}' OPENED after {self._failure_count} consecutive failures")

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self.stats.state_changes += 1
        logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED")

    def get_health_report(self) -> dict[str, Any]:
        """Get a health report for monitoring."""
        return {
            "name": self.name,
            "state": self.state.name,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_calls": self.stats.total_calls,
            "failure_rate": (self.stats.failed_calls / self.stats.total_calls if self.stats.total_calls > 0 else 0.0),
            "avg_execution_time": (self.stats.total_execution_time / self.stats.total_calls if self.stats.total_calls > 0 else 0.0),
            "consecutive_failures": self.stats.consecutive_failures,
            "last_failure": self.stats.last_failure,
            "last_success": self.stats.last_success,
            "is_healthy": self.state == CircuitState.CLOSED and self.stats.consecutive_failures == 0,
        }


class CircuitBreakerRegistry:
    """Global registry for all circuit breakers."""

    _breakers: dict[str, CircuitBreaker] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_or_create(
        cls,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        async with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name, config)
            return cls._breakers[name]

    @classmethod
    async def get_all_health(cls) -> dict[str, dict[str, Any]]:
        return {name: cb.get_health_report() for name, cb in cls._breakers.items()}

    @classmethod
    async def reset_all(cls) -> None:
        async with cls._lock:
            for cb in cls._breakers.values():
                cb.reset()

    @classmethod
    async def remove(cls, name: str) -> None:
        async with cls._lock:
            cls._breakers.pop(name, None)

    @classmethod
    def list_all(cls) -> list[str]:
        return list(cls._breakers.keys())


class ToolCircuitBreakerManager:
    """Manages circuit breakers for all tools automatically."""

    def __init__(self):
        self._tool_breakers: dict[str, CircuitBreaker] = {}
        self._default_config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=60.0,
            half_open_max_calls=2,
        )
        self._configs: dict[str, CircuitBreakerConfig] = {}

    def configure_tool(self, tool_name: str, config: CircuitBreakerConfig) -> None:
        """Configure circuit breaker for a specific tool."""
        self._configs[tool_name] = config

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self._tool_breakers:
            config = self._configs.get(tool_name, self._default_config)
            self._tool_breakers[tool_name] = CircuitBreaker(f"tool:{tool_name}", config)
        return self._tool_breakers[tool_name]

    async def call_tool(
        self,
        tool_name: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call a tool through its circuit breaker."""
        breaker = self.get_breaker(tool_name)
        return await breaker.call(func, *args, **kwargs)

    def get_all_health(self) -> dict[str, dict[str, Any]]:
        return {name: cb.get_health_report() for name, cb in self._tool_breakers.items()}

    def get_health_summary(self) -> dict[str, Any]:
        """Get a summary of all tool health."""
        if not self._tool_breakers:
            return {"total_tools": 0, "healthy": 0, "degraded": 0, "failed": 0}

        reports = self.get_all_health()
        healthy = sum(1 for r in reports.values() if r["is_healthy"])
        degraded = sum(1 for r in reports.values() if not r["is_healthy"] and r["state"] == "HALF_OPEN")
        failed = sum(1 for r in reports.values() if r["state"] == "OPEN")

        return {
            "total_tools": len(reports),
            "healthy": healthy,
            "degraded": degraded,
            "failed": failed,
            "reports": reports,
        }


_circuit_breaker_manager: ToolCircuitBreakerManager | None = None


def get_circuit_breaker_manager() -> ToolCircuitBreakerManager:
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = ToolCircuitBreakerManager()
    return _circuit_breaker_manager
