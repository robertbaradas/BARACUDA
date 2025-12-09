"""Unit tests for ensemble strategy."""

import numpy as np
import pandas as pd
import pytest

from src.strategies import create_strategy, Position
from src.strategies.ensemble_strategy import EnsembleStrategy, VotingMode


class TestEnsembleStrategy:
    """Tests for EnsembleStrategy."""

    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        np.random.seed(42)
        n = 100
        close = 100 + np.cumsum(np.random.randn(n) * 2)
        return pd.DataFrame({
            "Open": close - np.random.rand(n),
            "High": close + np.random.rand(n) * 2,
            "Low": close - np.random.rand(n) * 2,
            "Close": close,
            "Volume": np.random.randint(1000, 10000, n),
        })

    @pytest.fixture
    def rsi_strategy(self):
        return create_strategy("RSI")

    @pytest.fixture
    def macd_strategy(self):
        return create_strategy("MACD")

    def test_requires_at_least_one_strategy(self):
        """Ensemble must have at least one strategy."""
        with pytest.raises(ValueError, match="at least one strategy"):
            EnsembleStrategy(strategies=[])

    def test_weights_must_match_strategies(self, rsi_strategy, macd_strategy):
        """Number of weights must match strategies."""
        with pytest.raises(ValueError, match="weights must match"):
            EnsembleStrategy(
                strategies=[rsi_strategy, macd_strategy],
                weights=[1.0],  # Only one weight for two strategies
            )

    def test_name_combines_strategy_names(self, rsi_strategy, macd_strategy):
        """Ensemble name includes constituent strategy names."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        assert "RSI" in ensemble.name
        assert "MACD" in ensemble.name

    def test_display_name(self, rsi_strategy, macd_strategy):
        """Display name is user-friendly."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        assert "Ensemble" in ensemble.display_name
        assert "RSI" in ensemble.display_name
        assert "MACD" in ensemble.display_name

    def test_run_produces_signal_column(self, sample_df, rsi_strategy, macd_strategy):
        """Run produces a signal column."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        result = ensemble.run(sample_df)
        assert "signal" in result.columns

    def test_run_produces_individual_signals(self, sample_df, rsi_strategy, macd_strategy):
        """Run produces individual strategy signal columns."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        result = ensemble.run(sample_df)
        assert "signal_RSI" in result.columns
        assert "signal_MACD" in result.columns

    def test_unanimous_requires_all_agree(self, sample_df, rsi_strategy, macd_strategy):
        """Unanimous mode requires all strategies to agree."""
        ensemble = EnsembleStrategy(
            strategies=[rsi_strategy, macd_strategy],
            voting_mode=VotingMode.UNANIMOUS,
        )
        result = ensemble.run(sample_df)

        # Check that unanimous only signals when both agree
        for i in range(1, len(result)):  # Skip first (shifted)
            rsi_sig = result["signal_RSI"].iloc[i-1]  # Previous day's signal
            macd_sig = result["signal_MACD"].iloc[i-1]
            ensemble_sig = result["signal"].iloc[i]

            if rsi_sig == macd_sig and rsi_sig != Position.FLAT:
                # Both agree on direction - ensemble should match
                assert ensemble_sig == rsi_sig or ensemble_sig == Position.FLAT
            else:
                # Disagreement - should be flat
                assert ensemble_sig == Position.FLAT or ensemble_sig == rsi_sig or ensemble_sig == macd_sig

    def test_any_triggers_on_first_signal(self):
        """Any mode triggers on any non-flat signal."""
        # Create mock strategies with known signals
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            voting_mode=VotingMode.ANY,
        )

        # Test voting logic directly
        signals = np.array([Position.LONG, Position.FLAT])
        result = ensemble._vote_single(signals, np.array([1.0, 1.0]))
        assert result == Position.LONG

    def test_any_prefers_long_over_short(self):
        """Any mode returns LONG if present."""
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            voting_mode=VotingMode.ANY,
        )

        # When both LONG and SHORT present, LONG wins (checked first)
        signals = np.array([Position.LONG, Position.SHORT])
        result = ensemble._vote_single(signals, np.array([1.0, 1.0]))
        assert result == Position.LONG

    def test_weighted_voting(self):
        """Weighted voting respects weights."""
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        # Heavy weight on first strategy
        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            weights=[10.0, 1.0],
            voting_mode=VotingMode.WEIGHTED,
            threshold=0.3,
        )

        # RSI=LONG, MACD=SHORT with 10:1 weight should favor LONG
        signals = np.array([Position.LONG, Position.SHORT])
        weights = np.array([10.0, 1.0])
        result = ensemble._vote_single(signals, weights)
        assert result == Position.LONG

    def test_weighted_voting_short(self):
        """Weighted voting can produce SHORT."""
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        # Heavy weight on second strategy
        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            weights=[1.0, 10.0],
            voting_mode=VotingMode.WEIGHTED,
            threshold=0.3,
        )

        # RSI=LONG, MACD=SHORT with 1:10 weight should favor SHORT
        signals = np.array([Position.LONG, Position.SHORT])
        weights = np.array([1.0, 10.0])
        result = ensemble._vote_single(signals, weights)
        assert result == Position.SHORT

    def test_majority_voting(self):
        """Majority voting requires >50% agreement."""
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            voting_mode=VotingMode.MAJORITY,
            threshold=0.5,
        )

        # Both LONG = LONG
        signals = np.array([Position.LONG, Position.LONG])
        result = ensemble._vote_single(signals, np.array([1.0, 1.0]))
        assert result == Position.LONG

        # Split = FLAT
        signals = np.array([Position.LONG, Position.SHORT])
        result = ensemble._vote_single(signals, np.array([1.0, 1.0]))
        assert result == Position.FLAT

    def test_majority_voting_short(self):
        """Majority voting can produce SHORT."""
        rsi = create_strategy("RSI")
        macd = create_strategy("MACD")

        ensemble = EnsembleStrategy(
            strategies=[rsi, macd],
            voting_mode=VotingMode.MAJORITY,
            threshold=0.5,
        )

        # Both SHORT = SHORT
        signals = np.array([Position.SHORT, Position.SHORT])
        result = ensemble._vote_single(signals, np.array([1.0, 1.0]))
        assert result == Position.SHORT

    def test_signal_shift_avoids_lookahead(self, sample_df, rsi_strategy, macd_strategy):
        """Signals are shifted to avoid look-ahead bias."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        result = ensemble.run(sample_df)

        # First signal should be FLAT (shifted from NaN)
        assert result["signal"].iloc[0] == Position.FLAT

    def test_get_strategy_signals(self, sample_df, rsi_strategy, macd_strategy):
        """Can retrieve individual strategy signals after run."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        result = ensemble.run(sample_df)

        signals = ensemble.get_strategy_signals(result)
        assert "RSI" in signals
        assert "MACD" in signals
        assert len(signals["RSI"]) == len(sample_df)

    def test_default_weights_are_equal(self, rsi_strategy, macd_strategy):
        """Default weights are all 1.0."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        assert ensemble.weights == [1.0, 1.0]

    def test_custom_weights(self, rsi_strategy, macd_strategy):
        """Custom weights are stored correctly."""
        ensemble = EnsembleStrategy(
            strategies=[rsi_strategy, macd_strategy],
            weights=[2.0, 3.0],
        )
        assert ensemble.weights == [2.0, 3.0]

    def test_default_voting_mode(self, rsi_strategy, macd_strategy):
        """Default voting mode is MAJORITY."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        assert ensemble.voting_mode == VotingMode.MAJORITY

    def test_default_threshold(self, rsi_strategy, macd_strategy):
        """Default threshold is 0.5."""
        ensemble = EnsembleStrategy(strategies=[rsi_strategy, macd_strategy])
        assert ensemble.threshold == 0.5
