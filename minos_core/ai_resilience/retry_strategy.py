"""
Retry strategies with exponential backoff for AI service calls.

Implements configurable retry logic with exponential backoff to handle
transient failures gracefully.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from minos_core.observability.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd


class ExponentialBackoffRetry:
    """
    Implements exponential backoff retry strategy.

    Features:
    - Exponential delay increase: delay = initial_delay * (base ^ attempt)
    - Maximum delay cap to prevent excessive waiting
    - Optional jitter to prevent synchronized retries
    - Configurable retry conditions
    """

    def __init__(self, config: RetryConfig | None = None):
        """
        Initialize retry strategy.

        Args:
            config: Retry configuration (uses defaults if None)
        """
        self.config = config or RetryConfig()

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for the given retry attempt.

        Args:
            attempt: Current retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Calculate exponential delay
        delay = self.config.initial_delay * (
            self.config.exponential_base ** attempt
        )

        # Cap at max delay
        delay = min(delay, self.config.max_delay)

        # Add jitter if enabled
        if self.config.jitter:
            # Add random jitter of ±25%
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0.1, delay)  # Ensure positive delay

        return delay

    def execute(
        self,
        operation: Callable[[], T],
        should_retry: Callable[[Exception], bool] | None = None,
        on_retry: Callable[[int, Exception, float], None] | None = None,
    ) -> T:
        """
        Execute an operation with retry logic.

        Args:
            operation: The operation to execute
            should_retry: Optional function to determine if an exception should trigger retry
            on_retry: Optional callback called before each retry

        Returns:
            Result from the operation

        Raises:
            The last exception if all retries are exhausted
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = operation()
                if attempt > 0:
                    logger.info("operation_succeeded_after_retries", attempt=attempt)
                return result

            except Exception as e:
                last_exception = e

                # Check if we should retry this exception
                if should_retry and not should_retry(e):
                    logger.info(
                        "exception_not_retryable",
                        exception_type=type(e).__name__,
                    )
                    raise

                # Check if we have retries left
                if attempt >= self.config.max_retries:
                    logger.error(
                        "operation_failed_after_retries",
                        max_retries=self.config.max_retries,
                    )
                    raise

                # Calculate delay and wait
                delay = self.calculate_delay(attempt)
                logger.warning(
                    "retrying_operation",
                    attempt=attempt + 1,
                    max_retries=self.config.max_retries,
                    delay=round(delay, 2),
                    error=str(e),
                )

                # Call retry callback if provided
                if on_retry:
                    on_retry(attempt, e, delay)

                time.sleep(delay)

        # Should never reach here, but just in case
        raise last_exception  # type: ignore


def is_retryable_error(exception: Exception) -> bool:
    """
    Determine if an exception should trigger a retry.

    Retryable errors are typically transient network or service issues.
    Non-retryable errors are typically client errors (bad input, auth, etc).

    Args:
        exception: The exception to check

    Returns:
        True if the error should trigger a retry
    """
    # Import here to avoid circular dependencies
    import httpx

    # Network errors are retryable
    if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException)):
        return True

    # HTTP status codes
    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code
        # Retry on server errors (5xx) and rate limiting (429)
        # Don't retry client errors (4xx except 429)
        return status >= 500 or status == 429

    # By default, retry unknown errors
    return True


def create_default_retry_strategy() -> ExponentialBackoffRetry:
    """
    Create a retry strategy with sensible defaults for AI services.

    Returns:
        Configured retry strategy
    """
    config = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
    )
    return ExponentialBackoffRetry(config)
