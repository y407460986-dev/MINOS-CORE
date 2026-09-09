"""Protected LLM calls with circuit breaker, retry, and service pool fallback.

Wraps LLM adapter functions with resilience patterns so that every
LLM call in the pipeline is covered by:
- Circuit breaker (3-state: closed/open/half-open, configurable thresholds)
- Exponential backoff retry (with jitter, conditional retry)
- Service pool (priority-based endpoint selection + health tracking + failover)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from minos_core.ai_config import load_openai_responses_config
from minos_core.ai_resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from minos_core.ai_resilience.retry_strategy import (
    ExponentialBackoffRetry,
    RetryConfig,
)
from minos_core.ai_resilience.service_pool import AIServicePool
from minos_core.observability.logging import get_logger

logger = get_logger(__name__)


def wrap_llm_call(
    fn: Callable[..., Any],
    name: str = "llm_call",
) -> Callable[..., Any]:
    """Wrap an LLM adapter function with circuit breaker + retry.

    Usage::

        protected = wrap_llm_call(generator.generate_structured, name="pfd")
        result = protected(system_prompt=..., user_prompt=...)

    The returned wrapper transparently applies:
        1. Circuit breaker ― blocks after ``failure_threshold`` consecutive
           failures and allows recovery after ``timeout`` seconds.
        2. Exponential backoff retry ― retries up to ``max_retries`` times
           with jittered delays.

    Args:
        fn: The LLM function to wrap (e.g. ``llm.generate_structured``).
        name: Circuit breaker name for monitoring & logging.

    Returns:
        Wrapped function with identical signature.
    """
    breaker = CircuitBreaker(
        name=name,
        config=CircuitBreakerConfig(failure_threshold=5, timeout=60.0),
    )
    retry = ExponentialBackoffRetry(
        config=RetryConfig(max_retries=2, initial_delay=1.0, max_delay=30.0),
    )

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return retry.execute(
            lambda: breaker.call(lambda: fn(*args, **kwargs)),
        )

    return wrapper


# ---------------------------------------------------------------------------
# Service pool ― priority-based endpoint selection + health tracking
# ---------------------------------------------------------------------------

_service_pool: AIServicePool | None = None


def create_llm_service_pool() -> AIServicePool:
    """Create a service pool populated from the configured AI endpoint.

    Reads the current ``load_openai_responses_config()`` and registers
    an endpoint so the pool can track its health across calls.

    Returns:
        A configured ``AIServicePool`` instance.
    """
    config = load_openai_responses_config()
    pool = AIServicePool(cooldown_seconds=60.0)
    pool.add_endpoint(
        url=config.base_url,
        name="primary",
        priority=10,
        timeout=240,
        max_retries=2,
    )
    logger.info(
        "llm_service_pool_created",
        base_url=config.base_url,
        cooldown_seconds=60.0,
    )
    return pool


def get_llm_service_pool() -> AIServicePool:
    """Return the singleton LLM service pool (create on first access)."""
    global _service_pool
    if _service_pool is None:
        _service_pool = create_llm_service_pool()
    return _service_pool
