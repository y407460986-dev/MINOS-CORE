"""
Fallback strategies for degraded AI service operation.

Provides alternative approaches when primary AI services are unavailable,
allowing the system to continue operating with reduced functionality.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class FallbackStrategy(ABC):
    """Base class for fallback strategies."""

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> Any:
        """
        Execute the fallback strategy.

        Args:
            context: Context information for the fallback

        Returns:
            Fallback result
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this fallback strategy is available."""
        pass


class LocalKnowledgeFallback(FallbackStrategy):
    """
    Fallback to local knowledge base when AI services are unavailable.

    Uses cached or pre-configured knowledge to provide responses without
    requiring external AI service calls.
    """

    def __init__(self, knowledge_base: Any = None):
        """
        Initialize local knowledge fallback.

        Args:
            knowledge_base: Optional knowledge base instance
        """
        self.knowledge_base = knowledge_base

    def is_available(self) -> bool:
        """Check if local knowledge base is available."""
        return self.knowledge_base is not None

    def execute(self, context: dict[str, Any]) -> Any:
        """
        Query local knowledge base.

        Args:
            context: Must contain 'query' or 'part_family' key

        Returns:
            Knowledge base result or None
        """
        if not self.is_available():
            logger.warning("Local knowledge fallback not available")
            return None

        query = context.get("query") or context.get("part_family")
        if not query:
            logger.warning("No query provided for local knowledge fallback")
            return None

        logger.info(f"Using local knowledge fallback for query: {query}")

        try:
            # Try to query the knowledge base
            if hasattr(self.knowledge_base, "query"):
                return self.knowledge_base.query(query)
            elif hasattr(self.knowledge_base, "get"):
                return self.knowledge_base.get(query)
            else:
                logger.warning("Knowledge base has no query method")
                return None

        except Exception as e:
            logger.error(f"Local knowledge fallback failed: {e}")
            return None


class RuleBasedFallback(FallbackStrategy):
    """
    Fallback to rule-based analysis when AI services are unavailable.

    Uses deterministic rules and heuristics instead of AI inference.
    """

    def __init__(self, rules: dict[str, Any] | None = None):
        """
        Initialize rule-based fallback.

        Args:
            rules: Dictionary of rules to apply
        """
        self.rules = rules or {}

    def is_available(self) -> bool:
        """Check if rules are configured."""
        return len(self.rules) > 0

    def execute(self, context: dict[str, Any]) -> Any:
        """
        Apply rule-based analysis.

        Args:
            context: Context for rule evaluation

        Returns:
            Rule-based result or None
        """
        if not self.is_available():
            logger.warning("Rule-based fallback not available")
            return None

        logger.info("Using rule-based fallback")

        try:
            # Apply rules based on context
            result = {}
            for key, rule in self.rules.items():
                if callable(rule):
                    result[key] = rule(context)
                else:
                    result[key] = rule

            return result

        except Exception as e:
            logger.error(f"Rule-based fallback failed: {e}")
            return None


class CachedResponseFallback(FallbackStrategy):
    """
    Fallback to cached responses when AI services are unavailable.

    Returns previously cached successful responses for similar requests.
    """

    def __init__(self, cache: dict[str, Any] | None = None):
        """
        Initialize cached response fallback.

        Args:
            cache: Cache dictionary (key -> response)
        """
        self.cache = cache or {}

    def is_available(self) -> bool:
        """Check if cache has entries."""
        return len(self.cache) > 0

    def execute(self, context: dict[str, Any]) -> Any:
        """
        Retrieve cached response.

        Args:
            context: Must contain 'cache_key' key

        Returns:
            Cached response or None
        """
        if not self.is_available():
            logger.warning("Cached response fallback not available")
            return None

        cache_key = context.get("cache_key")
        if not cache_key:
            logger.warning("No cache key provided for cached response fallback")
            return None

        if cache_key in self.cache:
            logger.info(f"Using cached response for key: {cache_key}")
            return self.cache[cache_key]
        else:
            logger.warning(f"No cached response for key: {cache_key}")
            return None

    def add_to_cache(self, key: str, response: Any) -> None:
        """Add a response to the cache."""
        self.cache[key] = response


class ChainedFallback(FallbackStrategy):
    """
    Chains multiple fallback strategies, trying each in order.

    Attempts each fallback strategy until one succeeds or all fail.
    """

    def __init__(self, strategies: list[FallbackStrategy]):
        """
        Initialize chained fallback.

        Args:
            strategies: List of fallback strategies to try in order
        """
        self.strategies = strategies

    def is_available(self) -> bool:
        """Check if any strategy is available."""
        return any(s.is_available() for s in self.strategies)

    def execute(self, context: dict[str, Any]) -> Any:
        """
        Try each fallback strategy in order.

        Args:
            context: Context for fallback execution

        Returns:
            First successful result or None
        """
        for i, strategy in enumerate(self.strategies):
            if not strategy.is_available():
                logger.debug(
                    f"Fallback strategy {i} ({type(strategy).__name__}) not available"
                )
                continue

            try:
                result = strategy.execute(context)
                if result is not None:
                    logger.info(
                        f"Fallback strategy {i} ({type(strategy).__name__}) succeeded"
                    )
                    return result
            except Exception as e:
                logger.warning(
                    f"Fallback strategy {i} ({type(strategy).__name__}) failed: {e}"
                )

        logger.error("All fallback strategies failed")
        return None


def create_default_fallback_chain(
    knowledge_base: Any = None,
) -> ChainedFallback:
    """
    Create a default fallback chain with common strategies.

    Args:
        knowledge_base: Optional knowledge base for local fallback

    Returns:
        Configured chained fallback
    """
    strategies = []

    # Try local knowledge first
    if knowledge_base:
        strategies.append(LocalKnowledgeFallback(knowledge_base))

    # Then try rule-based analysis
    strategies.append(RuleBasedFallback())

    # Finally try cached responses
    strategies.append(CachedResponseFallback())

    return ChainedFallback(strategies)
