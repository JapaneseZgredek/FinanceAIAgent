"""Unit tests for app/utils/indicators.py — technical analysis indicators."""

import pandas as pd
import pytest

from app.utils.indicators import (
    MACDResult,
    TechnicalIndicators,
    _compute_atr_direction,
    _compute_histogram_trend,
    _compute_ma_slope,
    _compute_rsi_direction,
    _detect_ma_cross,
    _detect_macd_crossover,
    _detect_rsi_divergence,
    atr_from_close,
    atr_percent,
    calculate_all_indicators,
    classify_volatility_regime,
    ema,
    get_macd_result,
    interpret_rsi,
    macd,
    rsi,
    sma,
)

# ===================================================================
# SMA
# ===================================================================


class TestSMA:
    def test_basic_computation(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = sma(s, 3)
        assert result.iloc[-1] == pytest.approx(4.0)
        assert result.iloc[2] == pytest.approx(2.0)

    def test_leading_nan(self):
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = sma(s, 3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert not pd.isna(result.iloc[2])

    def test_period_larger_than_series(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = sma(s, 10)
        assert result.isna().all()

    def test_single_element(self):
        s = pd.Series([42.0])
        result = sma(s, 1)
        assert result.iloc[0] == pytest.approx(42.0)


# ===================================================================
# EMA
# ===================================================================


class TestEMA:
    def test_basic_computation(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = ema(s, 3)
        assert not pd.isna(result.iloc[0])
        assert result.iloc[-1] > result.iloc[0]

    def test_no_leading_nan(self):
        s = pd.Series([10.0, 20.0, 30.0])
        result = ema(s, 5)
        assert not result.isna().any()

    def test_weights_recent_more(self):
        s = pd.Series([100.0] * 10 + [200.0])
        result_ema = ema(s, 10)
        result_sma = sma(s, 10)
        assert result_ema.iloc[-1] > result_sma.iloc[-1]

    def test_constant_series(self):
        s = pd.Series([50.0] * 20)
        result = ema(s, 10)
        for val in result:
            assert val == pytest.approx(50.0)


# ===================================================================
# RSI
# ===================================================================


class TestRSI:
    def test_monotonically_rising(self):
        s = pd.Series(range(1, 50), dtype=float)
        result = rsi(s, 14)
        last_valid = result.dropna().iloc[-1]
        assert last_valid > 90

    def test_monotonically_falling(self):
        s = pd.Series(range(50, 1, -1), dtype=float)
        result = rsi(s, 14)
        last_valid = result.dropna().iloc[-1]
        assert last_valid < 10

    def test_constant_prices_return_nan(self):
        """Zero price changes → zero gains and losses → NaN RSI (0/0 division)."""
        s = pd.Series([100.0] * 30)
        result = rsi(s, 14)
        valid = result.dropna()
        assert len(valid) == 0

    def test_leading_nan_count(self):
        """diff() produces NaN at index 0, ewm(min_periods=14) needs 13 more → first valid at index 13."""
        s = pd.Series(range(1, 30), dtype=float)
        result = rsi(s, 14)
        nan_count = result.isna().sum()
        assert nan_count == 13

    def test_output_range(self, sample_price_df):
        result = rsi(sample_price_df["price"], 14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


# ===================================================================
# interpret_rsi
# ===================================================================


class TestInterpretRSI:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (75.0, "OVERBOUGHT"),
            (70.0, "OVERBOUGHT"),
            (25.0, "OVERSOLD"),
            (30.0, "OVERSOLD"),
            (65.0, "bullish"),
            (60.0, "bullish"),
            (35.0, "bearish"),
            (40.0, "bearish"),
            (50.0, "neutral"),
            (55.0, "neutral"),
            (41.0, "neutral"),
            (59.0, "neutral"),
        ],
    )
    def test_thresholds(self, value, expected):
        assert interpret_rsi(value) == expected

    def test_nan_input(self):
        assert interpret_rsi(float("nan")) == "N/A"


# ===================================================================
# _compute_rsi_direction
# ===================================================================


class TestComputeRSIDirection:
    def test_rising(self):
        s = pd.Series([50.0, 52.0, 54.0, 56.0, 58.0, 60.0])
        rsi_ago, direction = _compute_rsi_direction(s, lookback=5)
        assert direction == "rising"
        assert rsi_ago == pytest.approx(50.0)

    def test_falling(self):
        s = pd.Series([60.0, 58.0, 56.0, 54.0, 52.0, 50.0])
        rsi_ago, direction = _compute_rsi_direction(s, lookback=5)
        assert direction == "falling"

    def test_flat_within_dead_band(self):
        s = pd.Series([50.0, 50.5, 51.0, 51.5, 51.0, 52.0])
        _, direction = _compute_rsi_direction(s, lookback=5)
        assert direction == "flat"

    def test_exact_boundary_is_flat(self):
        """diff = exactly 3 → flat (condition is > 3, not >=)."""
        s = pd.Series([50.0, 51.0, 51.5, 52.0, 52.5, 53.0])
        _, direction = _compute_rsi_direction(s, lookback=5)
        assert direction == "flat"

    @pytest.mark.parametrize(
        "values",
        [[], [42.0], [55.0, 60.0], [50.0, 51.0, 52.0, 53.0, 54.0]],
        ids=["empty", "single", "two", "lookback_only"],
    )
    def test_insufficient_data_returns_none(self, values):
        """Fewer than lookback+1 values → (None, None), never a made-up fallback."""
        s = pd.Series(values, dtype=float)
        assert _compute_rsi_direction(s, lookback=5) == (None, None)

    def test_nan_only_returns_none(self):
        s = pd.Series([float("nan")] * 10)
        assert _compute_rsi_direction(s, lookback=5) == (None, None)

    def test_minimum_data_computes_direction(self):
        """Exactly lookback+1 values is enough."""
        s = pd.Series([50.0, 51.0, 52.0, 53.0, 54.0, 60.0])
        assert _compute_rsi_direction(s, lookback=5) == (50.0, "rising")


# ===================================================================
# _detect_rsi_divergence
# ===================================================================


class TestDetectRSIDivergence:
    """Tests use realistic price series — RSI is computed from prices, not fabricated."""

    _WARMUP = [
        100.0,
        101.0,
        99.8,
        100.8,
        99.6,
        100.6,
        99.4,
        100.4,
        99.2,
        100.2,
        99.0,
        100.0,
        98.8,
        99.8,
        98.6,
        99.6,
        98.4,
        99.4,
        98.2,
        99.2,
    ]

    def test_bullish_divergence(self):
        """Sharp crash (half1) → RSI plummets. Zigzag drift to lower price (half2) → RSI min higher."""
        prices = pd.Series(
            self._WARMUP
            + [
                99.2,
                96.2,
                93.2,
                90.2,
                87.2,
                84.2,
                81.2,
                78.2,
                75.2,
                72.2,
                74.2,
                71.2,
                73.2,
                70.2,
                71.2,
                68.2,
                70.2,
                67.7,
                68.7,
                67.7,
            ]
        )
        rsi_vals = rsi(prices)
        result = _detect_rsi_divergence(prices, rsi_vals, lookback=20)
        assert result == "BULLISH_DIVERGENCE"

    def test_bearish_divergence(self):
        """Sharp rally (half1) → RSI peaks high. Gradual climb to new high (half2) → RSI max lower."""
        prices = pd.Series(
            self._WARMUP
            + [
                99.2,
                103.2,
                107.2,
                111.2,
                115.2,
                119.2,
                123.2,
                127.2,
                131.2,
                135.2,
                131.2,
                127.2,
                123.2,
                120.2,
                118.2,
                123.2,
                128.2,
                133.2,
                138.2,
                140.2,
            ]
        )
        rsi_vals = rsi(prices)
        result = _detect_rsi_divergence(prices, rsi_vals, lookback=20)
        assert result == "BEARISH_DIVERGENCE"

    def test_no_divergence(self):
        """Steady uptrend — price and RSI both rise. No disagreement."""
        prices = pd.Series(
            self._WARMUP
            + [
                99.2,
                100.0,
                100.8,
                101.6,
                101.3,
                102.1,
                102.9,
                103.7,
                103.4,
                104.2,
                105.0,
                105.8,
                105.5,
                106.3,
                107.1,
                107.9,
                107.6,
                108.4,
                109.2,
                110.0,
            ]
        )
        rsi_vals = rsi(prices)
        result = _detect_rsi_divergence(prices, rsi_vals, lookback=20)
        assert result is None

    def test_insufficient_data(self):
        """Only 2 bars — far less than lookback=20."""
        prices = pd.Series([100.0, 110.0])
        rsi_vals = rsi(prices)
        result = _detect_rsi_divergence(prices, rsi_vals, lookback=20)
        assert result is None

    def test_nan_in_rsi(self):
        """25 identical prices — RSI is NaN for first 14 bars, contaminates the window."""
        prices = pd.Series([100.0] * 25)
        rsi_vals = rsi(prices)
        result = _detect_rsi_divergence(prices, rsi_vals, lookback=20)
        assert result is None


# ===================================================================
# MACD
# ===================================================================


class TestMACD:
    def test_constant_prices_zero_macd(self):
        s = pd.Series([100.0] * 50)
        macd_line, signal_line, histogram = macd(s)
        assert macd_line.iloc[-1] == pytest.approx(0.0)
        assert signal_line.iloc[-1] == pytest.approx(0.0)
        assert histogram.iloc[-1] == pytest.approx(0.0)

    def test_rising_prices_all_positive(self):
        """Constant uptrend → fast EMA > slow EMA → MACD > 0, MACD > Signal, histogram > 0."""
        s = pd.Series(range(1, 60), dtype=float)
        macd_line, signal_line, histogram = macd(s)
        assert macd_line.iloc[-1] > 0
        assert macd_line.iloc[-1] > signal_line.iloc[-1]
        assert histogram.iloc[-1] > 0

    def test_histogram_equals_macd_minus_signal(self, sample_price_df):
        macd_line, signal_line, histogram = macd(sample_price_df["price"])
        expected = macd_line.iloc[-1] - signal_line.iloc[-1]
        assert histogram.iloc[-1] == pytest.approx(expected)

    def test_custom_periods_differ_from_default(self):
        """Shorter periods produce different results than default (12, 26, 9)."""
        s = pd.Series(range(1, 60), dtype=float)
        default_macd, _, _ = macd(s)
        custom_macd, _, _ = macd(s, fast_period=5, slow_period=10, signal_period=3)
        assert default_macd.iloc[-1] != pytest.approx(custom_macd.iloc[-1])


# ===================================================================
# MACDResult
# ===================================================================


class TestMACDResult:
    def test_str_format(self):
        r = MACDResult(macd_line=150.5, signal_line=120.3, histogram=30.2, trend="bullish")
        s = str(r)
        assert "150.50" in s
        assert "120.30" in s
        assert "30.20" in s
        assert "bullish" in s

    def test_default_fields(self):
        r = MACDResult(macd_line=0, signal_line=0, histogram=0, trend="neutral")
        assert r.histogram_5d == []
        assert r.histogram_trend == "flat"
        assert r.crossover_type is None
        assert r.crossover_days_ago is None


# ===================================================================
# _compute_histogram_trend
# ===================================================================


class TestComputeHistogramTrend:
    def test_strongly_growing(self):
        h = pd.Series([10.0, 15.0, 20.0, 25.0, 30.0])
        values, trend = _compute_histogram_trend(h)
        assert trend == "strongly_growing"
        assert len(values) == 5

    def test_strongly_shrinking(self):
        h = pd.Series([30.0, 25.0, 20.0, 15.0, 10.0])
        _, trend = _compute_histogram_trend(h)
        assert trend == "strongly_shrinking"

    def test_growing_not_monotone(self):
        """Net increase but last 3 bars not strictly increasing → growing, not strongly."""
        h = pd.Series([10.0, 20.0, 25.0, 18.0, 22.0])
        _, trend = _compute_histogram_trend(h)
        assert trend == "growing"

    def test_shrinking_not_monotone(self):
        """Net decrease but last 3 bars not strictly decreasing → shrinking, not strongly."""
        h = pd.Series([30.0, 20.0, 15.0, 22.0, 18.0])
        _, trend = _compute_histogram_trend(h)
        assert trend == "shrinking"

    def test_flat(self):
        h = pd.Series([10.0, 11.0, 9.0, 10.5, 10.0])
        _, trend = _compute_histogram_trend(h)
        assert trend == "flat"

    def test_insufficient_data(self):
        h = pd.Series([10.0, 20.0])
        values, trend = _compute_histogram_trend(h)
        assert trend == "insufficient_data"
        assert len(values) == 2

    def test_negative_values_strongly_growing(self):
        """Becoming less negative = growing momentum."""
        h = pd.Series([-800.0, -600.0, -400.0, -200.0, -50.0])
        _, trend = _compute_histogram_trend(h)
        assert trend == "strongly_growing"

    def test_values_are_rounded_to_2dp(self):
        h = pd.Series([10.126, 20.674, 30.111])
        values, _ = _compute_histogram_trend(h)
        assert values == [10.13, 20.67, 30.11]


# ===================================================================
# _detect_macd_crossover
# ===================================================================


class TestDetectMACDCrossover:
    def test_bullish_crossover(self):
        h = pd.Series([-5.0, -3.0, -1.0, 2.0, 4.0])
        cross_type, days_ago = _detect_macd_crossover(h, lookback=5)
        assert cross_type == "bullish"
        assert days_ago == 1

    def test_bearish_crossover(self):
        h = pd.Series([5.0, 3.0, 1.0, -2.0, -4.0])
        cross_type, days_ago = _detect_macd_crossover(h, lookback=5)
        assert cross_type == "bearish"
        assert days_ago == 1

    def test_no_crossover(self):
        h = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        cross_type, days_ago = _detect_macd_crossover(h, lookback=5)
        assert cross_type is None
        assert days_ago is None

    def test_most_recent_returned(self):
        h = pd.Series([-2.0, 1.0, 3.0, -1.0, -3.0])
        cross_type, _ = _detect_macd_crossover(h, lookback=5)
        assert cross_type == "bearish"

    def test_insufficient_data(self):
        h = pd.Series([5.0])
        cross_type, days_ago = _detect_macd_crossover(h, lookback=5)
        assert cross_type is None
        assert days_ago is None

    def test_crossover_at_last_bar(self):
        h = pd.Series([1.0, 2.0, 3.0, -1.0])
        cross_type, days_ago = _detect_macd_crossover(h, lookback=5)
        assert cross_type == "bearish"
        assert days_ago == 0


# ===================================================================
# get_macd_result
# ===================================================================


class TestGetMACDResult:
    def test_returns_populated_result(self, sample_price_df):
        result = get_macd_result(sample_price_df["price"])
        assert isinstance(result, MACDResult)
        assert isinstance(result.macd_line, float)
        assert isinstance(result.signal_line, float)
        assert isinstance(result.histogram, float)
        assert result.trend in ("bullish", "bearish", "neutral", "N/A")

    def test_bullish_trend(self):
        s = pd.Series(range(1, 60), dtype=float)
        result = get_macd_result(s)
        assert result.trend == "bullish"
        assert result.histogram > 0

    def test_bearish_trend(self):
        s = pd.Series(range(60, 1, -1), dtype=float)
        result = get_macd_result(s)
        assert result.trend == "bearish"
        assert result.histogram < 0


# ===================================================================
# ATR
# ===================================================================


class TestATR:
    def test_atr_from_close_non_negative(self, sample_price_df):
        result = atr_from_close(sample_price_df["price"], 14)
        valid = result.dropna()
        assert (valid >= 0).all()

    def test_atr_constant_prices_all_zero(self):
        """No price changes → every ATR value is 0."""
        s = pd.Series([100.0] * 30)
        result = atr_from_close(s, 14)
        valid = result.dropna()
        assert (valid == 0.0).all()

    def test_atr_percent_normalization_all_values(self):
        """ATR% = (ATR / price) * 100 holds for every non-NaN row."""
        s = pd.Series([100.0, 110.0, 105.0, 115.0, 108.0] * 6)
        atr_abs = atr_from_close(s, 14)
        atr_pct = atr_percent(s, 14)
        mask = atr_abs.notna()
        expected = (atr_abs[mask] / s[mask]) * 100
        pd.testing.assert_series_equal(atr_pct[mask], expected)


# ===================================================================
# _compute_atr_direction
# ===================================================================


class TestComputeATRDirection:
    def test_rising(self):
        s = pd.Series([2.0] * 7 + [2.5])
        assert _compute_atr_direction(s, lookback=7) == "rising"

    def test_falling(self):
        s = pd.Series([3.0] * 7 + [2.5])
        assert _compute_atr_direction(s, lookback=7) == "falling"

    def test_stable(self):
        s = pd.Series([2.0] * 7 + [2.05])
        assert _compute_atr_direction(s, lookback=7) == "stable"

    def test_insufficient_data_returns_unknown(self):
        """Less data than lookback requires → 'unknown' (conservative)."""
        s = pd.Series([2.0, 2.5])
        assert _compute_atr_direction(s, lookback=7) == "unknown"

    def test_past_zero_guard(self):
        """Guard: past ATR% = 0 cannot happen on real data, but must not crash."""
        s = pd.Series([0.0] * 7 + [1.0])
        assert _compute_atr_direction(s, lookback=7) == "stable"


# ===================================================================
# classify_volatility_regime
# ===================================================================


class TestClassifyVolatilityRegime:
    def test_low_regime(self, btc_historical_atr_pct):
        p25 = btc_historical_atr_pct.quantile(0.25)
        assert classify_volatility_regime(p25 - 0.1, btc_historical_atr_pct) == "LOW"

    def test_normal_regime(self, btc_historical_atr_pct):
        median = btc_historical_atr_pct.quantile(0.50)
        assert classify_volatility_regime(median, btc_historical_atr_pct) == "NORMAL"

    def test_high_regime(self, btc_historical_atr_pct):
        p80 = btc_historical_atr_pct.quantile(0.80)
        assert classify_volatility_regime(p80, btc_historical_atr_pct) == "HIGH"

    def test_extreme_regime(self, btc_historical_atr_pct):
        p95 = btc_historical_atr_pct.quantile(0.95)
        assert classify_volatility_regime(p95, btc_historical_atr_pct) == "EXTREME"

    def test_nan_returns_normal(self, btc_historical_atr_pct):
        assert classify_volatility_regime(float("nan"), btc_historical_atr_pct) == "NORMAL"

    def test_boundary_at_p25(self, btc_historical_atr_pct):
        """Value exactly at p25 → NORMAL (condition is < p25, not <=)."""
        p25 = btc_historical_atr_pct.quantile(0.25)
        assert classify_volatility_regime(p25, btc_historical_atr_pct) == "NORMAL"

    def test_boundary_at_p90(self, btc_historical_atr_pct):
        """Value exactly at p90 → EXTREME (condition is >= p90)."""
        p90 = btc_historical_atr_pct.quantile(0.90)
        assert classify_volatility_regime(p90, btc_historical_atr_pct) == "EXTREME"

    def test_constant_history(self):
        """All historical values identical — every percentile is the same."""
        historical = pd.Series([2.5] * 100)
        assert classify_volatility_regime(2.5, historical) == "EXTREME"
        assert classify_volatility_regime(2.4, historical) == "LOW"


# ===================================================================
# _compute_ma_slope
# ===================================================================


class TestComputeMASlope:
    def test_rising(self):
        s = pd.Series([100.0, 100.2, 100.4, 100.6, 100.8, 101.0, 101.2, 101.4, 101.6, 101.8])
        slope, label = _compute_ma_slope(s, n=10)
        assert label == "rising"
        assert slope > 0

    def test_falling(self):
        s = pd.Series([101.8, 101.6, 101.4, 101.2, 101.0, 100.8, 100.6, 100.4, 100.2, 100.0])
        slope, label = _compute_ma_slope(s, n=10)
        assert label == "falling"
        assert slope < 0

    def test_flat(self):
        s = pd.Series([100.0, 100.01, 100.02, 100.01, 100.0, 100.01, 100.02, 100.01, 100.0, 100.01])
        _, label = _compute_ma_slope(s, n=10)
        assert label == "flat"

    def test_insufficient_data(self):
        s = pd.Series([100.0])
        slope, label = _compute_ma_slope(s, n=10)
        assert slope == 0.0
        assert label == "flat"


# ===================================================================
# _detect_ma_cross
# ===================================================================


class TestDetectMACross:
    def test_golden_cross(self):
        fast = pd.Series([90.0] * 5 + [110.0] * 5)
        slow = pd.Series([100.0] * 10)
        signal, days_ago = _detect_ma_cross(fast, slow, lookback=10)
        assert signal == "GOLDEN_CROSS"
        assert days_ago == 4

    def test_death_cross(self):
        fast = pd.Series([110.0] * 5 + [90.0] * 5)
        slow = pd.Series([100.0] * 10)
        signal, days_ago = _detect_ma_cross(fast, slow, lookback=10)
        assert signal == "DEATH_CROSS"
        assert days_ago == 4

    def test_no_cross(self):
        fast = pd.Series([110.0] * 10)
        slow = pd.Series([100.0] * 10)
        signal, days_ago = _detect_ma_cross(fast, slow, lookback=10)
        assert signal is None
        assert days_ago is None

    def test_insufficient_data(self):
        fast = pd.Series([100.0])
        slow = pd.Series([100.0])
        signal, _ = _detect_ma_cross(fast, slow, lookback=10)
        assert signal is None

    def test_nan_handling(self):
        fast = pd.Series([float("nan")] * 5 + [90.0, 95.0, 100.0, 105.0, 110.0])
        slow = pd.Series([float("nan")] * 5 + [100.0] * 5)
        signal, _ = _detect_ma_cross(fast, slow, lookback=10)
        assert signal == "GOLDEN_CROSS"


# ===================================================================
# calculate_all_indicators
# ===================================================================


class TestCalculateAllIndicators:
    def test_returns_correct_type(self, sample_price_df):
        result = calculate_all_indicators(sample_price_df)
        assert isinstance(result, TechnicalIndicators)

    def test_all_fields_populated(self, sample_price_df):
        result = calculate_all_indicators(sample_price_df)
        assert isinstance(result.sma_20, float)
        assert isinstance(result.rsi_14, float)
        assert isinstance(result.macd_result, MACDResult)
        assert isinstance(result.atr_14, float)
        assert result.volatility_regime in ("LOW", "NORMAL", "HIGH", "EXTREME")
        assert result.price_vs_sma_20 in ("above", "below")
        assert result.atr_direction in ("rising", "falling", "stable")

    def test_short_series_fallback(self, short_price_df):
        result = calculate_all_indicators(short_price_df)
        assert result.sma_200 == pytest.approx(short_price_df["price"].iloc[-1])

    def test_trend_summary_format(self, sample_price_df):
        result = calculate_all_indicators(sample_price_df)
        assert any(keyword in result.trend_summary for keyword in ("BULLISH", "BEARISH", "NEUTRAL", "SLIGHTLY"))

    def test_rsi_within_bounds(self, sample_price_df):
        result = calculate_all_indicators(sample_price_df)
        assert 0 <= result.rsi_14 <= 100

    def test_missing_price_column_raises(self):
        df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(KeyError):
            calculate_all_indicators(df)


# ===================================================================
# TechnicalIndicators.format_for_llm
# ===================================================================


class TestFormatForLLM:
    def test_contains_all_sections(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "MOVING AVERAGES:" in output
        assert "MOMENTUM:" in output
        assert "VOLATILITY:" in output
        assert "TREND SUMMARY:" in output

    def test_contains_sma_values(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "SMA(20):" in output
        assert "SMA(50):" in output
        assert "SMA(200):" in output

    def test_no_ma_cross(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "none detected in recent history" in output

    def test_with_ma_cross(self):
        from tests.unit.conftest import _make_indicators

        ind = _make_indicators()
        ind.ma_cross_signal = "GOLDEN_CROSS"
        ind.ma_cross_days_ago = 10
        output = ind.format_for_llm(70000.0)
        assert "GOLDEN_CROSS" in output
        assert "10d ago" in output

    def test_rsi_divergence_absent(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "RSI Divergence" not in output

    def test_rsi_divergence_present(self):
        from tests.unit.conftest import _make_indicators

        ind = _make_indicators()
        ind.rsi_divergence = "BULLISH_DIVERGENCE"
        output = ind.format_for_llm(70000.0)
        assert "BULLISH_DIVERGENCE" in output
        assert "potential reversal" in output

    def test_rsi_direction_present(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "[5d ago: 55.0, direction: rising]" in output

    def test_rsi_direction_missing(self):
        from tests.unit.conftest import _make_indicators

        ind = _make_indicators()
        ind.rsi_5d_ago = None
        ind.rsi_direction = None
        output = ind.format_for_llm(70000.0)
        assert "direction: n/a — insufficient history" in output
        assert "None" not in output

    def test_macd_crossover_present(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "bullish crossover" in output
        assert "5d ago" in output

    def test_histogram_trend_displayed(self, sample_technical_indicators):
        output = sample_technical_indicators.format_for_llm(70000.0)
        assert "GROWING" in output
