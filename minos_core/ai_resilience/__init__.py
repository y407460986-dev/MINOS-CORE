"""
AI Resilience Module

Provides fault tolerance mechanisms for AI service calls:
- Multi-endpoint service pool with automatic failover
- Exponential backoff retry strategy
- Circuit breaker pattern to prevent cascading failures
- Fallback strategies for degraded service
"""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)
from .fallback import (
    CachedResponseFallback,
    ChainedFallback,
    FallbackStrategy,
    LocalKnowledgeFallback,
    RuleBasedFallback,
)
from .retry_strategy import ExponentialBackoffRetry, RetryConfig
from .service_pool import AIEndpoint, AIServicePool

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
