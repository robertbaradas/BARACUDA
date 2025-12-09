"""Strategy registry and factory for technical indicator strategies."""

from typing import Dict, List, Type, Any

from src.strategies.base_strategy import (
    BaseStrategy,
    ChartConfig,
    Position,
    StrategyParameter,
)
from src.strategies.rsi_strategy import RSIStrategy


# Registry mapping strategy names to classes
STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {
    "RSI": RSIStrategy,
}


def get_available_strategies() -> List[str]:
    """Return list of all registered strategy names."""
    return list(STRATEGY_REGISTRY.keys())


def create_strategy(name: str, **params) -> BaseStrategy:
    """Factory function to instantiate a strategy by name.

    Args:
        name: Strategy identifier (e.g., 'RSI')
        **params: Parameter overrides

    Returns:
        Instantiated strategy

    Raises:
        ValueError: If strategy name not found in registry
    """
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}. Available: {get_available_strategies()}")
    return STRATEGY_REGISTRY[name](**params)


__all__ = [
    "BaseStrategy",
    "ChartConfig",
    "Position",
    "StrategyParameter",
    "RSIStrategy",
    "STRATEGY_REGISTRY",
    "get_available_strategies",
    "create_strategy",
]
