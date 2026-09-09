"""
Multi-endpoint AI service pool with automatic failover.

Manages multiple AI service endpoints and provides automatic failover
when primary endpoints fail or become unhealthy.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from minos_core.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AIEndpoint:
    """Represents a single AI service endpoint."""

    url: str
    name: str
    priority: int = 0  # Lower number = higher priority
    timeout: float = 30.0
    max_retries: int = 3

    # Health tracking
    consecutive_failures: int = 0
    last_failure_time: float | None = None
    is_healthy: bool = True

    def mark_success(self) -> None:
        """Mark endpoint as successful, resetting failure count."""
        self.consecutive_failures = 0
        self.is_healthy = True
        logger.debug("endpoint_marked_healthy", name=self.name)

    def mark_failure(self) -> None:
        """Mark endpoint as failed, incrementing failure count."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        # Mark unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            logger.warning(
                "endpoint_marked_unhealthy",
                name=self.name,
                consecutive_failures=self.consecutive_failures,
            )

    def should_retry_after_cooldown(self, cooldown_seconds: float = 60.0) -> bool:
        """Check if enough time has passed to retry an unhealthy endpoint."""
        if self.is_healthy:
            return True

        if self.last_failure_time is None:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= cooldown_seconds


@dataclass
class AIServicePool:
    """
    Manages a pool of AI service endpoints with automatic failover.

    Features:
    - Automatic endpoint selection based on priority and health
    - Health tracking and automatic recovery
    - Cooldown period for unhealthy endpoints
    """

    endpoints: list[AIEndpoint] = field(default_factory=list)
    cooldown_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Sort endpoints by priority after initialization."""
        self.endpoints.sort(key=lambda e: e.priority)

    def add_endpoint(
        self,
        url: str,
        name: str,
        priority: int = 0,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        """Add a new endpoint to the pool."""
        endpoint = AIEndpoint(
            url=url,
            name=name,
            priority=priority,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.endpoints.append(endpoint)
        self.endpoints.sort(key=lambda e: e.priority)
        logger.info("endpoint_added", name=name, priority=priority)

    def get_next_endpoint(self) -> AIEndpoint | None:
        """
        Get the next available endpoint to try.

        Returns the highest priority healthy endpoint, or the highest priority
        unhealthy endpoint that has passed its cooldown period.
        """
        # First try healthy endpoints
        for endpoint in self.endpoints:
            if endpoint.is_healthy:
                return endpoint

        # If no healthy endpoints, try unhealthy ones after cooldown
        for endpoint in self.endpoints:
            if endpoint.should_retry_after_cooldown(self.cooldown_seconds):
                logger.info(
                    "retrying_unhealthy_endpoint",
                    name=endpoint.name,
                )
                return endpoint

        # No endpoints available
        logger.error("No available endpoints in pool")
        return None

    def execute_with_fallback(
        self,
        operation: Callable[[AIEndpoint], Any],
        max_attempts: int | None = None,
    ) -> Any:
        """
        Execute an operation with automatic endpoint fallback.

        Args:
            operation: Callable that takes an AIEndpoint and returns a result
            max_attempts: Maximum number of endpoints to try (None = try all)

        Returns:
            Result from the operation

        Raises:
            RuntimeError: If all endpoints fail
        """
        if not self.endpoints:
            raise RuntimeError("No endpoints configured in service pool")

        attempts = 0
        max_attempts = max_attempts or len(self.endpoints)
        last_error = None

        while attempts < max_attempts:
            endpoint = self.get_next_endpoint()
            if endpoint is None:
                break

            try:
                logger.info("attempting_operation", name=endpoint.name)
                result = operation(endpoint)
                endpoint.mark_success()
                return result

            except Exception as e:
                last_error = e
                endpoint.mark_failure()
                logger.warning(
                    "operation_failed",
                    name=endpoint.name,
                    error=str(e),
                )
                attempts += 1

        # All endpoints failed
        logger.error(
            "all_endpoints_failed",
            attempts=attempts,
            last_error=str(last_error),
        )
        raise RuntimeError(
            f"All {attempts} endpoint attempts failed. "
            f"Last error: {last_error}"
        ) from last_error

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of all endpoints."""
        return {
            "total_endpoints": len(self.endpoints),
            "healthy_endpoints": sum(1 for e in self.endpoints if e.is_healthy),
            "endpoints": [
                {
                    "name": e.name,
                    "url": e.url,
                    "priority": e.priority,
                    "is_healthy": e.is_healthy,
                    "consecutive_failures": e.consecutive_failures,
                }
                for e in self.endpoints
            ],
        }
