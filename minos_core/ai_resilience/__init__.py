"""
AI Resilience Module

Provides fault tolerance mechanisms for AI service calls:
- Multi-endpoint service pool with automatic failover
- Exponential backoff retry strategy
- Circuit breaker pattern to prevent cascading failures
- Fallback strategies for degraded service
"""

from .service_pool import AIEndpoint, AIServicePool
from .retry_strategy import ExponentialBackoffRetry, RetryConfig
from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from .fallback import (
    FallbackStrategy,
    LocalKnowledgeFallback,
    RuleBasedFallback,
    CachedResponseFallback,
    ChainedFallback,
)

__all__ = [
    "AIEndpoint",
    "AIServicePool",
    "ExponentialBackoffRetry",
    "RetryConfig",
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "FallbackStrategy",
    "LocalKnowledgeFallback",
    "RuleBasedFallback",
    "CachedResponseFallback",
    "ChainedFallback",
]
