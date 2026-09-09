"""
Circuit breaker pattern implementation for AI services.

Prevents cascading failures by temporarily blocking calls to failing services,
allowing them time to recover.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from minos_core.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests pass through
    OPEN = "open"  # Circuit is open, requests are blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening circuit
    success_threshold: int = 2  # Successes in half-open before closing
    timeout: float = 60.0  # Seconds to wait before trying half-open
    expected_exception: type[Exception] | None = None  # Exception type to track


class CircuitBreaker:
    """
    Implements the circuit breaker pattern.

    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Too many failures, all requests are blocked
    - HALF_OPEN: Testing recovery, limited requests pass through

    Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After timeout period
    - HALF_OPEN -> CLOSED: After success_threshold consecutive successes
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(
        self,
        name: str = "default",
        config: CircuitBreakerConfig | None = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Name for logging and identification
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._last_state_change = time.time()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._last_state_change = time.time()

        logger.info(
            "circuit_breaker_transitioned",
            name=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

        # Reset counters on state change
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return False

        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout

    def _record_success(self) -> None:
        """Record a successful call."""
        self._failure_count = 0

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            logger.debug(
                "circuit_breaker_success_progress",
                name=self.name,
                success_count=self._success_count,
                success_threshold=self.config.success_threshold,
            )

            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def _record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens the circuit
            logger.warning(
                "circuit_breaker_half_open_failure",
                name=self.name,
            )
            self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.CLOSED:
            logger.debug(
                "circuit_breaker_failure_progress",
                name=self.name,
                failure_count=self._failure_count,
                failure_threshold=self.config.failure_threshold,
            )

            if self._failure_count >= self.config.failure_threshold:
                logger.warning(
                    "circuit_breaker_threshold_reached",
                    name=self.name,
                )
                self._transition_to(CircuitState.OPEN)

    def call(
        self,
        operation: Callable[[], T],
        fallback: Callable[[], T] | None = None,
    ) -> T:
        """
        Execute an operation through the circuit breaker.

        Args:
            operation: The operation to execute
            fallback: Optional fallback to use when circuit is open

        Returns:
            Result from operation or fallback

        Raises:
            CircuitBreakerOpenError: If circuit is open and no fallback provided
            Exception: Any exception from the operation
        """
        # Check if we should attempt reset
        if self._state == CircuitState.OPEN and self._should_attempt_reset():
            logger.info(
                "circuit_breaker_attempting_reset",
                name=self.name,
            )
            self._transition_to(CircuitState.HALF_OPEN)

        # Block if circuit is open
        if self._state == CircuitState.OPEN:
            logger.warning(
                "circuit_breaker_blocking_call",
                name=self.name,
            )
            if fallback:
                logger.info("circuit_breaker_using_fallback", name=self.name)
                return fallback()
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is open"
                )

        # Attempt the operation
        try:
            result = operation()
            self._record_success()
            return result

        except Exception as e:
            # Only track expected exceptions if configured
            if self.config.expected_exception is None or isinstance(
                e, self.config.expected_exception
            ):
                self._record_failure()

            # Re-raise the exception
            raise

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        logger.info("circuit_breaker_manual_reset", name=self.name)
        self._transition_to(CircuitState.CLOSED)

    def get_status(self) -> dict[str, Any]:
        """Get current status of the circuit breaker."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            },
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocks a call."""

    pass
