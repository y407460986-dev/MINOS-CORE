"""Tests for AI resilience module."""

import pytest
import time
from unittest.mock import Mock, patch

from minos_core.ai_resilience import (
    AIEndpoint,
    AIServicePool,
    ExponentialBackoffRetry,
    RetryConfig,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    LocalKnowledgeFallback,
    RuleBasedFallback,
    CachedResponseFallback,
    ChainedFallback,
)


class TestAIEndpoint:
    """Tests for AIEndpoint class."""

    def test_endpoint_creation(self):
        """Test creating an endpoint."""
        endpoint = AIEndpoint(
            url="https://api.example.com",
            name="test-endpoint",
            priority=1,
            timeout=30.0,
        )

        assert endpoint.url == "https://api.example.com"
        assert endpoint.name == "test-endpoint"
        assert endpoint.priority == 1
        assert endpoint.is_healthy is True
        assert endpoint.consecutive_failures == 0

    def test_mark_success(self):
        """Test marking endpoint as successful."""
        endpoint = AIEndpoint(url="https://api.example.com", name="test")
        endpoint.consecutive_failures = 2
        endpoint.is_healthy = False

        endpoint.mark_success()

        assert endpoint.consecutive_failures == 0
        assert endpoint.is_healthy is True

    def test_mark_failure(self):
        """Test marking endpoint as failed."""
        endpoint = AIEndpoint(url="https://api.example.com", name="test")

        # First two failures should not mark unhealthy
        endpoint.mark_failure()
        assert endpoint.consecutive_failures == 1
        assert endpoint.is_healthy is True

        endpoint.mark_failure()
        assert endpoint.consecutive_failures == 2
        assert endpoint.is_healthy is True

        # Third failure should mark unhealthy
        endpoint.mark_failure()
        assert endpoint.consecutive_failures == 3
        assert endpoint.is_healthy is False

    def test_cooldown_period(self):
        """Test cooldown period for unhealthy endpoints."""
        endpoint = AIEndpoint(url="https://api.example.com", name="test")
        endpoint.mark_failure()
        endpoint.mark_failure()
        endpoint.mark_failure()

        assert endpoint.is_healthy is False

        # Should not retry immediately
        assert endpoint.should_retry_after_cooldown(cooldown_seconds=60.0) is False

        # Simulate time passing
        endpoint.last_failure_time = time.time() - 61.0
        assert endpoint.should_retry_after_cooldown(cooldown_seconds=60.0) is True


class TestAIServicePool:
    """Tests for AIServicePool class."""

    def test_pool_creation(self):
        """Test creating a service pool."""
        pool = AIServicePool()
        assert len(pool.endpoints) == 0

    def test_add_endpoint(self):
        """Test adding endpoints to pool."""
        pool = AIServicePool()
        pool.add_endpoint(
            url="https://api1.example.com",
            name="endpoint-1",
            priority=1,
        )
        pool.add_endpoint(
            url="https://api2.example.com",
            name="endpoint-2",
            priority=0,
        )

        assert len(pool.endpoints) == 2
        # Should be sorted by priority (lower number = higher priority)
        assert pool.endpoints[0].name == "endpoint-2"
        assert pool.endpoints[1].name == "endpoint-1"

    def test_get_next_endpoint_healthy(self):
        """Test getting next endpoint when all are healthy."""
        pool = AIServicePool()
        pool.add_endpoint("https://api1.example.com", "endpoint-1", priority=1)
        pool.add_endpoint("https://api2.example.com", "endpoint-2", priority=0)

        endpoint = pool.get_next_endpoint()
        assert endpoint is not None
        assert endpoint.name == "endpoint-2"  # Higher priority

    def test_get_next_endpoint_with_failures(self):
        """Test getting next endpoint when some are unhealthy."""
        pool = AIServicePool()
        pool.add_endpoint("https://api1.example.com", "endpoint-1", priority=0)
        pool.add_endpoint("https://api2.example.com", "endpoint-2", priority=1)

        # Mark first endpoint as unhealthy
        pool.endpoints[0].mark_failure()
        pool.endpoints[0].mark_failure()
        pool.endpoints[0].mark_failure()

        endpoint = pool.get_next_endpoint()
        assert endpoint is not None
        assert endpoint.name == "endpoint-2"  # Falls back to second

    def test_execute_with_fallback_success(self):
        """Test successful execution with fallback."""
        pool = AIServicePool()
        pool.add_endpoint("https://api.example.com", "test-endpoint")

        def operation(endpoint: AIEndpoint) -> str:
            return f"success from {endpoint.name}"

        result = pool.execute_with_fallback(operation)
        assert result == "success from test-endpoint"

    def test_execute_with_fallback_retry(self):
        """Test execution with fallback and retry."""
        pool = AIServicePool()
        pool.add_endpoint("https://api1.example.com", "endpoint-1", priority=0)
        pool.add_endpoint("https://api2.example.com", "endpoint-2", priority=1)

        call_count = 0

        def operation(endpoint: AIEndpoint) -> str:
            nonlocal call_count
            call_count += 1
            if endpoint.name == "endpoint-1" and call_count == 1:
                raise RuntimeError("endpoint-1 failed")
            return f"success from {endpoint.name}"

        result = pool.execute_with_fallback(operation)
        # Should succeed on second attempt (after first endpoint fails once)
        assert "success from" in result
        assert call_count >= 1

    def test_execute_with_fallback_all_fail(self):
        """Test execution when all endpoints fail."""
        pool = AIServicePool()
        pool.add_endpoint("https://api.example.com", "test-endpoint")

        def operation(endpoint: AIEndpoint) -> str:
            raise RuntimeError("operation failed")

        with pytest.raises(RuntimeError, match="All .* endpoint attempts failed"):
            pool.execute_with_fallback(operation)

    def test_get_health_status(self):
        """Test getting health status."""
        pool = AIServicePool()
        pool.add_endpoint("https://api1.example.com", "endpoint-1")
        pool.add_endpoint("https://api2.example.com", "endpoint-2")

        # Mark one as unhealthy
        pool.endpoints[0].mark_failure()
        pool.endpoints[0].mark_failure()
        pool.endpoints[0].mark_failure()

        status = pool.get_health_status()
        assert status["total_endpoints"] == 2
        assert status["healthy_endpoints"] == 1


class TestExponentialBackoffRetry:
    """Tests for ExponentialBackoffRetry class."""

    def test_calculate_delay(self):
        """Test delay calculation."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=60.0,
            jitter=False,
        )
        retry = ExponentialBackoffRetry(config)

        # Test exponential growth
        assert retry.calculate_delay(0) == 1.0  # 1.0 * 2^0
        assert retry.calculate_delay(1) == 2.0  # 1.0 * 2^1
        assert retry.calculate_delay(2) == 4.0  # 1.0 * 2^2
        assert retry.calculate_delay(3) == 8.0  # 1.0 * 2^3

    def test_calculate_delay_with_max(self):
        """Test delay calculation with max cap."""
        config = RetryConfig(
            initial_delay=10.0,
            exponential_base=2.0,
            max_delay=30.0,
            jitter=False,
        )
        retry = ExponentialBackoffRetry(config)

        # Should cap at max_delay
        assert retry.calculate_delay(5) == 30.0  # Would be 320, capped at 30

    def test_execute_success_first_try(self):
        """Test successful execution on first try."""
        retry = ExponentialBackoffRetry()

        def operation():
            return "success"

        result = retry.execute(operation)
        assert result == "success"

    def test_execute_success_after_retries(self):
        """Test successful execution after retries."""
        config = RetryConfig(max_retries=3, initial_delay=0.01)
        retry = ExponentialBackoffRetry(config)

        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("temporary failure")
            return "success"

        result = retry.execute(operation)
        assert result == "success"
        assert call_count == 3

    def test_execute_all_retries_exhausted(self):
        """Test when all retries are exhausted."""
        config = RetryConfig(max_retries=2, initial_delay=0.01)
        retry = ExponentialBackoffRetry(config)

        def operation():
            raise RuntimeError("persistent failure")

        with pytest.raises(RuntimeError, match="persistent failure"):
            retry.execute(operation)

    def test_execute_with_should_retry(self):
        """Test execution with custom retry condition."""
        config = RetryConfig(max_retries=3, initial_delay=0.01)
        retry = ExponentialBackoffRetry(config)

        def operation():
            raise ValueError("non-retryable error")

        def should_retry(e: Exception) -> bool:
            return not isinstance(e, ValueError)

        # Should not retry ValueError
        with pytest.raises(ValueError, match="non-retryable error"):
            retry.execute(operation, should_retry=should_retry)


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state(self):
        """Test initial circuit breaker state."""
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    def test_transition_to_open(self):
        """Test transition from closed to open."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(name="test", config=config)

        def failing_operation():
            raise RuntimeError("failure")

        # First 2 failures should keep circuit closed
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(failing_operation)
            assert cb.is_closed is True

        # Third failure should open circuit
        with pytest.raises(RuntimeError):
            cb.call(failing_operation)
        assert cb.is_open is True

    def test_open_circuit_blocks_calls(self):
        """Test that open circuit blocks calls."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(name="test", config=config)

        def failing_operation():
            raise RuntimeError("failure")

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(failing_operation)

        # Next call should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(failing_operation)

    def test_open_circuit_with_fallback(self):
        """Test open circuit with fallback."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(name="test", config=config)

        def failing_operation():
            raise RuntimeError("failure")

        def fallback():
            return "fallback result"

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(failing_operation)

        # Should use fallback
        result = cb.call(failing_operation, fallback=fallback)
        assert result == "fallback result"

    def test_half_open_transition(self):
        """Test transition to half-open after timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=0.1)
        cb = CircuitBreaker(name="test", config=config)

        def failing_operation():
            raise RuntimeError("failure")

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(failing_operation)
        assert cb.is_open is True

        # Wait for timeout
        time.sleep(0.15)

        # Next call should transition to half-open
        def success_operation():
            return "success"

        # This should work and close the circuit
        result = cb.call(success_operation)
        assert result == "success"

    def test_manual_reset(self):
        """Test manual circuit reset."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(name="test", config=config)

        def failing_operation():
            raise RuntimeError("failure")

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(failing_operation)
        assert cb.is_open is True

        # Manual reset
        cb.reset()
        assert cb.is_closed is True

    def test_get_status(self):
        """Test getting circuit breaker status."""
        cb = CircuitBreaker(name="test")
        status = cb.get_status()

        assert status["name"] == "test"
        assert status["state"] == "closed"
        assert "failure_count" in status
        assert "config" in status


class TestFallbackStrategies:
    """Tests for fallback strategies."""

    def test_local_knowledge_fallback(self):
        """Test local knowledge fallback."""
        mock_kb = Mock()
        mock_kb.query.return_value = {"result": "from knowledge base"}

        fallback = LocalKnowledgeFallback(knowledge_base=mock_kb)
        assert fallback.is_available() is True

        result = fallback.execute({"query": "test query"})
        assert result == {"result": "from knowledge base"}
        mock_kb.query.assert_called_once_with("test query")

    def test_rule_based_fallback(self):
        """Test rule-based fallback."""
        rules = {
            "rule1": lambda ctx: ctx.get("value", 0) * 2,
            "rule2": "static value",
        }

        fallback = RuleBasedFallback(rules=rules)
        assert fallback.is_available() is True

        result = fallback.execute({"value": 5})
        assert result["rule1"] == 10
        assert result["rule2"] == "static value"

    def test_cached_response_fallback(self):
        """Test cached response fallback."""
        cache = {"key1": "cached value 1"}

        fallback = CachedResponseFallback(cache=cache)
        assert fallback.is_available() is True

        result = fallback.execute({"cache_key": "key1"})
        assert result == "cached value 1"

        # Test cache miss
        result = fallback.execute({"cache_key": "key2"})
        assert result is None

    def test_chained_fallback(self):
        """Test chained fallback."""
        # First strategy fails
        strategy1 = Mock(spec=LocalKnowledgeFallback)
        strategy1.is_available.return_value = True
        strategy1.execute.return_value = None

        # Second strategy succeeds
        strategy2 = Mock(spec=RuleBasedFallback)
        strategy2.is_available.return_value = True
        strategy2.execute.return_value = "success from strategy2"

        chained = ChainedFallback([strategy1, strategy2])
        assert chained.is_available() is True

        result = chained.execute({"test": "context"})
        assert result == "success from strategy2"

    def test_chained_fallback_all_fail(self):
        """Test chained fallback when all strategies fail."""
        strategy1 = Mock(spec=LocalKnowledgeFallback)
        strategy1.is_available.return_value = True
        strategy1.execute.return_value = None

        strategy2 = Mock(spec=RuleBasedFallback)
        strategy2.is_available.return_value = True
        strategy2.execute.return_value = None

        chained = ChainedFallback([strategy1, strategy2])
        result = chained.execute({"test": "context"})
        assert result is None
