"""
Technical indicators for cryptocurrency price analysis.

This module provides standard technical analysis indicators:
- Moving Averages (SMA, EMA)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range) approximation
- Volatility regime classification

All functions expect a pandas DataFrame with a 'price' column and datetime index.

Design philosophy — two layers:
1. Raw indicator functions (sma, ema, rsi, macd, atr_*): return full pd.Series
   so that all historical context is preserved for downstream use.
2. Dynamic signal helpers (prefixed _): extract trend/direction from those series
   and return compact structured labels. These are what the LLM actually reads.

Why this separation matters:
  LLMs are poor at doing arithmetic on long numeric sequences. Instead of dumping
  120 daily RSI values and asking the model to "spot the trend", we do the math
  here in Python (where it is deterministic and exact) and hand the model a clear
  signal like "RSI direction: falling". The model's job is then to weigh signals
  and reason — which is what it excels at.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal


# =============================================================================
# MOVING AVERAGES
# =============================================================================

def sma(series: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average (SMA).

    SMA = sum of last N prices / N

    Each value in the returned series is the arithmetic mean of the preceding
    `period` prices. The first `period-1` values are NaN because there is not
    yet enough history to fill the window.

    Args:
        series: Price series
        period: Number of periods (e.g., 20, 50, 200)

    Returns:
        Series with SMA values (NaN for first period-1 values)
    """
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average (EMA).

    Unlike SMA, EMA weights recent prices more heavily via an exponential
    decay factor k = 2/(period+1). This makes it react faster to price
    changes than SMA of the same period, at the cost of being noisier.

    Formula: EMA_today = (Price_today * k) + (EMA_yesterday * (1-k))
    where k = 2 / (period + 1)

    Args:
        series: Price series
        period: Number of periods (e.g., 20, 50, 200)

    Returns:
        Series with EMA values (no leading NaN — pandas seeds the EMA
        from the first available price)
    """
    return series.ewm(span=period, adjust=False).mean()


# =============================================================================
# RSI (Relative Strength Index)
# =============================================================================

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (RSI).

    RSI measures the speed and magnitude of recent price changes to evaluate
    overbought or oversold conditions. It oscillates between 0 and 100.

    Interpretation:
    - RSI > 70: Overbought (potential sell signal)
    - RSI < 30: Oversold (potential buy signal)
    - RSI 30-70: Neutral

    Formula:
    RSI = 100 - (100 / (1 + RS))
    RS = Average Gain / Average Loss over period

    Implementation note — Wilder's smoothing (alpha = 1/period):
      Wilder's original RSI does NOT use a simple rolling mean for gains/losses.
      Instead it uses an EMA with alpha=1/period (slower decay than the standard
      EMA formula). This makes RSI "stickier" — it doesn't whipsaw on single
      large candles. pandas ewm(alpha=1/period) reproduces this exactly.

    Args:
        series: Price series
        period: Lookback period (default: 14)

    Returns:
        Series with RSI values (0-100 scale). First ~period values are NaN
        because Wilder's EMA needs min_periods bars to initialise.
    """
    delta = series.diff()  # day-over-day price change

    # Separate gains (positive changes) and losses (absolute negative changes).
    # Where the condition is False we set 0.0 so the EMA still "sees" a zero
    # contribution for that day — important for Wilder's smoothing to work.
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)  # losses are stored as positive numbers

    # Wilder's smoothed averages — alpha=1/period ≈ slower EMA
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_values = 100 - (100 / (1 + rs))

    return rsi_values


def interpret_rsi(value: float) -> str:
    """Interpret RSI value as a human-readable market condition label."""
    if pd.isna(value):
        return "N/A"
    if value >= 70:
        return "OVERBOUGHT"
    if value <= 30:
        return "OVERSOLD"
    if value >= 60:
        return "bullish"
    if value <= 40:
        return "bearish"
    return "neutral"


def _compute_rsi_direction(rsi_series: pd.Series, lookback: int = 5) -> tuple[float, str]:
    """
    Determine whether RSI momentum is rising, falling, or flat over `lookback` days.

    WHY this exists:
      A single RSI value (e.g. 62) tells the LLM the *current* momentum level
      but not *where it is going*. RSI = 62 falling from 74 is a bearish signal
      (momentum fading). RSI = 62 rising from 50 is a bullish signal (momentum
      building). Without direction, the LLM cannot distinguish these two situations.

    HOW the dead band works (why threshold = 3):
      RSI is computed via Wilder's EMA, which inherently smooths the series. Even
      so, day-to-day RSI fluctuates ±1–2 points purely from random price noise.
      If we used `diff > 0` as the "rising" threshold, almost every day would be
      labelled rising or falling, providing no useful signal.

      A threshold of ±3 points over 5 days means:
        - At RSI = 50, moving to 53 in 5 days = ~0.6 pts/day of consistent momentum.
        - Movements smaller than ±3 pts over 5 days are treated as flat (noise).
        - This is commonly called a "dead band" in signal processing.

      ±3 pts is appropriate for crypto (high volatility). For traditional equities
      you might lower it to ±2 pts.

    Args:
        rsi_series: Full RSI series (output of rsi())
        lookback: How many days back to compare (default: 5)

    Returns:
        Tuple of (rsi_n_days_ago, direction_label).
        direction_label is "rising", "falling", or "flat".
    """
    clean = rsi_series.dropna()

    # Guard: if we don't have enough history, return flat as a safe default.
    # iloc[-(lookback+1)] needs at least lookback+1 valid values.
    if len(clean) < lookback + 1:
        val = float(clean.iloc[0]) if len(clean) > 0 else 50.0
        return round(val, 1), "flat"

    # iloc[-(lookback+1)] is the value exactly `lookback` days before today.
    # Example: lookback=5, series length=100 → iloc[-6] = value 5 days ago.
    rsi_ago = float(clean.iloc[-(lookback + 1)])
    current = float(clean.iloc[-1])

    # Absolute difference on the 0–100 RSI scale.
    # We use absolute points (not %) because RSI is already a normalised ratio;
    # a percentage of a percentage would be meaningless.
    diff = current - rsi_ago

    # Dead band: only classify as rising/falling if the change clears ±3 pts.
    # Everything inside is labelled "flat" (noise, no meaningful direction).
    if diff > 3:
        direction = "rising"    # momentum is genuinely building
    elif diff < -3:
        direction = "falling"   # momentum is genuinely fading
    else:
        direction = "flat"      # within noise band — no clear directional signal

    return round(rsi_ago, 1), direction


def _detect_rsi_divergence(
    prices: pd.Series,
    rsi_series: pd.Series,
    lookback: int = 20,
) -> str | None:
    """
    Detect bullish or bearish RSI divergence using a split-window heuristic.

    WHY divergence matters:
      Divergence is one of the strongest reversal signals in technical analysis.
      It occurs when price and RSI "disagree" about the direction of momentum:
        - Bullish divergence: price makes a lower low while RSI makes a higher low.
          This means selling pressure is weakening even as price drops — potential
          reversal to the upside.
        - Bearish divergence: price makes a higher high while RSI makes a lower high.
          Buying pressure is weakening even as price rises — potential reversal down.

    HOW the split-window heuristic works:
      We divide the last `lookback` bars into two equal halves and compare the
      extremes (min for bullish, max for bearish) of each half:

        Half 1 (older):  bars [0 .. lookback//2 - 1]
        Half 2 (newer):  bars [lookback//2 .. lookback - 1]

      If price_min(half2) < price_min(half1) × 0.98   ← price made a lower low
      AND  rsi_min(half2)  > rsi_min(half1)  × 1.05   ← RSI made a higher low
      → BULLISH_DIVERGENCE

      Thresholds (0.98 / 1.05):
        - Price threshold 2%: filters trivial lower lows that are just noise.
          In crypto a 2% move over 10 days is a real structural low.
        - RSI threshold 5%: filters noise on the RSI side.
          RSI 30 vs RSI 31.5 is not meaningful; RSI 30 vs RSI 32+ is.

      Limitation: this is a simplified heuristic. A rigorous divergence detector
      would find actual local peaks/troughs using scipy.signal.argrelextrema or
      similar. For our purposes (LLM hint) the heuristic is good enough.

    Args:
        prices: Price series
        rsi_series: RSI series aligned with prices
        lookback: Window size in days (default: 20, split into two 10-day halves)

    Returns:
        "BULLISH_DIVERGENCE", "BEARISH_DIVERGENCE", or None
    """
    p = prices.tail(lookback)
    r = rsi_series.tail(lookback)

    # Need full window and no NaN in RSI for a reliable comparison.
    if len(p) < lookback or r.isna().any():
        return None

    half = lookback // 2
    p_first, p_second = p.iloc[:half], p.iloc[half:]
    r_first, r_second = r.iloc[:half], r.iloc[half:]

    p_min_first, p_min_second = p_first.min(), p_second.min()
    r_min_first, r_min_second = r_first.min(), r_second.min()
    p_max_first, p_max_second = p_first.max(), p_second.max()
    r_max_first, r_max_second = r_first.max(), r_second.max()

    # --- Bullish divergence ---
    # Price lower low (2% threshold) AND RSI higher low (5% threshold)
    price_lower_low = p_min_second < p_min_first * 0.98
    rsi_higher_low = r_min_second > r_min_first * 1.05
    if price_lower_low and rsi_higher_low:
        return "BULLISH_DIVERGENCE"

    # --- Bearish divergence ---
    # Price higher high (2% threshold) AND RSI lower high (5% threshold)
    price_higher_high = p_max_second > p_max_first * 1.02
    rsi_lower_high = r_max_second < r_max_first * 0.95
    if price_higher_high and rsi_lower_high:
        return "BEARISH_DIVERGENCE"

    return None


# =============================================================================
# MACD (Moving Average Convergence Divergence)
# =============================================================================

@dataclass
class MACDResult:
    """
    MACD calculation results — snapshot values plus dynamic signals.

    Static fields (macd_line, signal_line, histogram, trend) describe the
    current state. Dynamic fields (histogram_5d, histogram_trend, crossover_*)
    describe momentum direction and recent events that the LLM needs to
    correctly weight the MACD signal.
    """
    macd_line: float        # MACD line value today: EMA(12) - EMA(26)
    signal_line: float      # Signal line today: EMA(9) of MACD line
    histogram: float        # Histogram today: MACD - Signal
    trend: str              # Snapshot trend label: "bullish", "bearish", "neutral"

    # Dynamic: last 5 histogram values in chronological order (oldest → newest).
    # Gives the LLM the raw series to see momentum trajectory, not just the endpoint.
    histogram_5d: list[float] = field(default_factory=list)

    # Dynamic: direction of the histogram over the last 5 bars.
    # "STRONGLY GROWING"   = 3 consecutive increases (accelerating momentum)
    # "GROWING"            = net increase over 5 bars (momentum building)
    # "FLAT"               = negligible change (momentum stalling)
    # "SHRINKING"          = net decrease (momentum fading — key warning signal)
    # "STRONGLY SHRINKING" = 3 consecutive decreases (momentum collapsing)
    histogram_trend: str = "flat"

    # Dynamic: most recent MACD crossover within the scan window.
    # A crossover = histogram changes sign = MACD line crosses the Signal line.
    # None if no crossover was found in the lookback window.
    crossover_type: str | None = None       # "bullish" or "bearish"
    crossover_days_ago: int | None = None   # how many days ago it occurred

    def __str__(self) -> str:
        return (
            f"MACD: {self.macd_line:.2f}, Signal: {self.signal_line:.2f}, "
            f"Hist: {self.histogram:.2f} ({self.trend})"
        )


def macd(
    series: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence Divergence).

    Returns full time series for all three components so that dynamic helpers
    can inspect the history (histogram trend, crossover detection).

    Components:
    - MACD Line:   EMA(fast) - EMA(slow)  — measures distance between two EMAs
    - Signal Line: EMA(signal) of MACD line — smoothed MACD, acts as trigger
    - Histogram:   MACD - Signal — visual measure of momentum speed

    Standard periods (12, 26, 9) were defined by Gerald Appel in the 1970s.
    They remain the universal default for daily charts.

    Args:
        series: Price series
        fast_period: Fast EMA period (default: 12)
        slow_period:  Slow EMA period (default: 26)
        signal_period: Signal line period (default: 9)

    Returns:
        Tuple of (macd_line, signal_line, histogram) — each a full pd.Series
    """
    ema_fast = ema(series, fast_period)
    ema_slow = ema(series, slow_period)

    macd_line = ema_fast - ema_slow         # positive = fast above slow = bullish
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line     # positive = MACD above Signal = bullish momentum

    return macd_line, signal_line, histogram


def _compute_histogram_trend(histogram: pd.Series, n: int = 5) -> tuple[list[float], str]:
    """
    Compute the directional trend of the MACD histogram over the last `n` bars.

    WHY the histogram trend matters more than the histogram snapshot:
      The histogram value alone (e.g. +344) is nearly meaningless without context.
      The *direction* of the histogram is the real signal:
        - Histogram growing  (e.g. 200 → 300 → 344) = momentum strengthening.
        - Histogram shrinking (e.g. 800 → 600 → 344) = momentum fading.
          This is a warning of potential reversal even though histogram is still
          positive and MACD trend is still labelled "bullish".

    HOW "growing" and "shrinking" are defined for both positive and negative values:
      We compare values numerically (not their absolute magnitude). This means:
        - histogram_5d = [-800, -600, -400, -200, -50]
          → values are increasing (less negative each day)
          → trend = "strongly_growing"   (bearish momentum is collapsing — bullish signal)

        - histogram_5d = [-50, -200, -400, -600, -800]
          → values are decreasing (more negative each day)
          → trend = "strongly_shrinking" (bearish momentum accelerating — bearish signal)

      This is correct and intuitive: "growing" always means the histogram is
      moving toward more positive values, regardless of its current sign.

    WHY n=5:
      5 bars gives enough history to distinguish a genuine trend from a one-day
      spike, while keeping the LLM context footprint small.

    Args:
        histogram: Full MACD histogram series
        n: Number of recent bars to inspect (default: 5)

    Returns:
        Tuple of (last_n_values_chronological, trend_label)
    """
    recent = histogram.dropna().tail(n)
    values = [round(float(v), 2) for v in recent.tolist()]

    if len(values) < 3:
        return values, "insufficient_data"

    last3 = values[-3:]

    # Check the last 3 bars for strict monotone movement.
    # Monotone over 3 bars is a stronger signal than just comparing endpoints,
    # because it shows consistent directional pressure with no hesitation.
    if last3[2] > last3[1] > last3[0]:
        trend = "strongly_growing"      # consistent acceleration
    elif last3[2] < last3[1] < last3[0]:
        trend = "strongly_shrinking"    # consistent deceleration
    # Fall back to comparing only the 5-bar endpoints for a weaker signal.
    elif values[-1] > values[0]:
        trend = "growing"               # net gain but not monotone
    elif values[-1] < values[0]:
        trend = "shrinking"             # net loss but not monotone
    else:
        trend = "flat"

    return values, trend


def _detect_macd_crossover(
    histogram: pd.Series,
    lookback: int = 20,
) -> tuple[str | None, int | None]:
    """
    Detect the most recent MACD crossover (bullish or bearish) within `lookback` bars.

    WHY crossovers matter:
      A crossover is the most actionable MACD event — it signals that momentum
      has flipped direction. Knowing that a bullish crossover happened 3 days ago
      vs 15 days ago dramatically changes how the LLM should weight the signal:
        - Recent (≤5 days): strong, fresh signal — high weight
        - Older (>10 days): fading signal, trend may already be priced in

    HOW detection works — histogram sign change:
      The histogram = MACD - Signal. When histogram crosses zero from below,
      MACD has just crossed above Signal → bullish crossover. Vice versa for
      bearish. Scanning for sign changes in the histogram is computationally
      simple and mathematically equivalent to watching the MACD/Signal crossover.

    WHY we scan backwards (newest → oldest):
      We want the MOST RECENT crossover, not the first one in the window.
      Iterating from the end of the series toward the beginning and returning on
      the first hit gives us the most recent event.

    Args:
        histogram: Full MACD histogram series
        lookback: How many recent bars to scan (default: 20 ≈ one trading month)

    Returns:
        Tuple of (crossover_type, days_ago) or (None, None).
        crossover_type is "bullish" (histogram turned positive) or
        "bearish" (histogram turned negative).
        days_ago = 0 means it happened on the most recent bar.
    """
    recent = histogram.dropna().tail(lookback)
    if len(recent) < 2:
        return None, None

    # Scan from newest bar toward oldest (i = last index → 1).
    # days_ago = (len - 1) - i: bar at i=last has days_ago=0 (today),
    # bar at i=last-1 has days_ago=1 (yesterday), and so on.
    for i in range(len(recent) - 1, 0, -1):
        curr_positive = recent.iloc[i] > 0
        prev_positive = recent.iloc[i - 1] > 0

        if curr_positive and not prev_positive:
            # Histogram just went from negative to positive → MACD crossed above Signal
            return "bullish", len(recent) - 1 - i

        elif not curr_positive and prev_positive:
            # Histogram just went from positive to negative → MACD crossed below Signal
            return "bearish", len(recent) - 1 - i

    return None, None


def get_macd_result(series: pd.Series) -> MACDResult:
    """
    Compute full MACD result including dynamic signals for the LLM.

    Calls the raw macd() function, then extracts:
    - Latest snapshot values (macd_line, signal_line, histogram)
    - Trend label from snapshot
    - Histogram direction over last 5 bars
    - Most recent crossover event

    Args:
        series: Full price series

    Returns:
        MACDResult with static and dynamic fields populated
    """
    macd_line, signal_line, histogram = macd(series)

    latest_macd = macd_line.iloc[-1]
    latest_signal = signal_line.iloc[-1]
    latest_hist = histogram.iloc[-1]

    # Snapshot trend: requires both histogram sign AND MACD vs Signal agreement
    # to avoid labelling "bullish" when MACD just barely crossed above zero
    # but histogram is still slightly negative (transition zone).
    if pd.isna(latest_hist):
        trend = "N/A"
    elif latest_hist > 0 and latest_macd > latest_signal:
        trend = "bullish"
    elif latest_hist < 0 and latest_macd < latest_signal:
        trend = "bearish"
    else:
        trend = "neutral"   # histogram and MACD/Signal relationship disagree

    hist_5d, hist_trend = _compute_histogram_trend(histogram)
    crossover_type, crossover_days_ago = _detect_macd_crossover(histogram)

    return MACDResult(
        macd_line=latest_macd if not pd.isna(latest_macd) else 0.0,
        signal_line=latest_signal if not pd.isna(latest_signal) else 0.0,
        histogram=latest_hist if not pd.isna(latest_hist) else 0.0,
        trend=trend,
        histogram_5d=hist_5d,
        histogram_trend=hist_trend,
        crossover_type=crossover_type,
        crossover_days_ago=crossover_days_ago,
    )


# =============================================================================
# ATR (Average True Range) — Volatility Measure
# =============================================================================

def atr_from_close(series: pd.Series, period: int = 14) -> pd.Series:
    """
    ATR approximation using only close prices.

    The canonical ATR formula needs High, Low, and Close to compute the True Range:
      TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)

    Since Alpha Vantage DIGITAL_CURRENCY_DAILY gives us only close prices, we
    approximate TR as |Close_today - Close_yesterday|. This underestimates true
    volatility (ignores intraday wicks) but preserves the day-over-day volatility
    signal which is what we need for regime classification.

    Wilder's EMA smoothing (alpha=1/period) is used — same as in RSI — to
    produce a slow-moving volatility baseline that doesn't spike on single days.

    Args:
        series: Close price series
        period: ATR period (default: 14, Wilder's original)

    Returns:
        Series with ATR-like volatility values (in price units)
    """
    price_change = series.diff().abs()  # |Close_t - Close_{t-1}| ≈ True Range
    atr_values = price_change.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return atr_values


def atr_percent(series: pd.Series, period: int = 14) -> pd.Series:
    """
    ATR expressed as a percentage of the current price (ATR%).

    Why normalise by price?
      Raw ATR in dollars is not comparable across time or across assets.
      BTC ATR of $2000 at price $20,000 = 10% daily swing.
      BTC ATR of $2000 at price $100,000 = 2% daily swing.
      ATR% removes the price-level dependency, making it comparable.

    Args:
        series: Close price series
        period: ATR period (default: 14)

    Returns:
        Series with ATR% values (e.g. 2.5 means 2.5% daily volatility)
    """
    atr_values = atr_from_close(series, period)
    return (atr_values / series) * 100


def _compute_atr_direction(atr_pct_series: pd.Series, lookback: int = 7) -> str:
    """
    Determine whether volatility (ATR%) is rising, falling, or stable.

    WHY volatility direction matters:
      Current ATR% tells you how volatile the market is right now.
      ATR% direction tells you where volatility is heading:
        - Rising ATR%: volatility expanding → often precedes a breakout or
          a sharp move (could be up or down). Signals increasing risk.
        - Falling ATR%: volatility contracting → market consolidating.
          Low volatility often precedes a breakout. Can signal accumulation.

    WHY 10% dead band:
      ATR% itself is computed via Wilder's EMA, which is very smooth.
      Even so, day-to-day ATR% fluctuates. A 10% change in ATR% over 7 days
      is material (e.g. ATR% goes from 2.0% to 2.2%). Changes smaller than
      10% relative are just noise from the smoothing and don't signal a regime
      shift in volatility. Unlike RSI (which uses absolute points on 0-100),
      here we use a relative (%) threshold because ATR% values differ wildly
      between assets and market regimes.

    Args:
        atr_pct_series: Full ATR% series
        lookback: Days back to compare against (default: 7 ≈ one trading week)

    Returns:
        "rising", "falling", or "stable"
    """
    clean = atr_pct_series.dropna()

    # Need lookback+1 values: one from `lookback` days ago plus today's value.
    if len(clean) < lookback + 1:
        return "stable"

    past = float(clean.iloc[-(lookback + 1)])   # ATR% value `lookback` days ago
    current = float(clean.iloc[-1])              # ATR% value today

    if past == 0:
        return "stable"  # degenerate case: avoid division by zero

    # Relative change in ATR% over `lookback` days.
    # Example: past=2.0%, current=2.3% → change=+15% → "rising"
    # Example: past=3.0%, current=2.7% → change=-10% → "falling"
    change_pct = (current / past - 1) * 100

    # ±10% relative change = dead band for volatility direction.
    if change_pct > 10:
        return "rising"     # volatility expanding — increasing risk/opportunity
    elif change_pct < -10:
        return "falling"    # volatility contracting — consolidation likely
    else:
        return "stable"     # within noise band — no directional signal


# =============================================================================
# VOLATILITY REGIME CLASSIFICATION
# =============================================================================

VolatilityRegime = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]


def classify_volatility_regime(
    atr_pct: float,
    historical_atr_pct: pd.Series,
) -> VolatilityRegime:
    """
    Classify current volatility relative to this asset's own historical distribution.

    WHY relative classification (not absolute thresholds):
      Different assets have different "normal" volatility. BTC at 3% ATR% is
      calm. A bond ETF at 3% ATR% is extreme. Using absolute thresholds would
      always mislabel cross-asset volatility. By comparing against the asset's
      own historical percentiles, we always get a contextually correct answer.

    Uses percentile-based thresholds from the full historical ATR% series:
    - LOW:     below 25th percentile — market unusually calm, consolidating
    - NORMAL:  25th–75th percentile — typical trading conditions
    - HIGH:    75th–90th percentile — elevated volatility, increased risk
    - EXTREME: above 90th percentile — panic / euphoria conditions

    Args:
        atr_pct: Current ATR% value (scalar)
        historical_atr_pct: Full historical ATR% series for percentile computation

    Returns:
        Volatility regime classification string
    """
    if pd.isna(atr_pct):
        return "NORMAL"

    p25 = historical_atr_pct.quantile(0.25)
    p75 = historical_atr_pct.quantile(0.75)
    p90 = historical_atr_pct.quantile(0.90)

    if atr_pct < p25:
        return "LOW"
    elif atr_pct < p75:
        return "NORMAL"
    elif atr_pct < p90:
        return "HIGH"
    else:
        return "EXTREME"


# =============================================================================
# MOVING AVERAGE DYNAMICS
# =============================================================================

def _compute_ma_slope(series: pd.Series, n: int = 10) -> tuple[float, str]:
    """
    Compute whether a moving average is rising, falling, or flat.

    WHY MA slope matters (beyond price-vs-MA):
      Knowing "price is above SMA(20)" is a static snapshot. But if SMA(20)
      is itself turning downward, it signals that the trend which held price
      above it is losing strength — even before price breaks below it. MA slope
      is an early warning system for trend deterioration.

      Classic example of why static is insufficient:
        Day 1: Price = 105, SMA(20) = 100 → price above → bullish ✓
        Day 10: Price = 101, SMA(20) = 103 → price below → bearish ✓
        What happened in between? The MA turned. If we'd had slope data we'd
        have seen "SMA(20) slope: falling" while price was still above it.

    HOW slope is computed:
      We compare the MA value at the start and end of the last `n` bars and
      express the net change as % per day. This is more stable than a single
      day-over-day derivative which could spike on one anomalous day.

      slope (%/day) = ((MA_today - MA_{n_days_ago}) / MA_{n_days_ago}) / (n-1) × 100

    WHY dead band = ±0.05%/day:
      MA series are already very smooth (that's their purpose). A slope of
      0.05%/day on SMA(20) means the average moved 0.5% over 10 days — small
      but directional. Below this threshold the MA is essentially flat and we'd
      be reporting noise as signal. For reference:
        - SMA(20) slope of +0.1%/d on BTC at $100k → +$100/day → clearly rising
        - SMA(20) slope of +0.01%/d on BTC at $100k → +$10/day → noise

    Args:
        series: MA series (full pd.Series output of sma() or ema())
        n: Number of bars to compute slope over (default: 10)

    Returns:
        Tuple of (slope_pct_per_day, label) where label is
        "rising", "falling", or "flat"
    """
    recent = series.dropna().tail(n)
    if len(recent) < 2:
        return 0.0, "flat"

    # Total % change from first to last bar in the window
    pct_change = (recent.iloc[-1] / recent.iloc[0] - 1) * 100
    # Normalise to per-day rate
    per_day = pct_change / (len(recent) - 1)

    # Dead band: ±0.05%/day distinguishes meaningful slope from flat MA noise
    if per_day > 0.05:
        return round(per_day, 3), "rising"
    elif per_day < -0.05:
        return round(per_day, 3), "falling"
    else:
        return round(per_day, 3), "flat"


def _detect_ma_cross(
    fast: pd.Series,
    slow: pd.Series,
    lookback: int = 60,
) -> tuple[str | None, int | None]:
    """
    Detect the most recent Golden Cross or Death Cross within `lookback` bars.

    WHAT Golden/Death Cross means:
      Golden Cross: fast MA (SMA 50) crosses above slow MA (SMA 200).
        Widely followed as a long-term bullish regime signal. Historically
        associated with the beginning of major bull runs in crypto.
      Death Cross: fast MA (SMA 50) crosses below slow MA (SMA 200).
        Long-term bearish regime signal. Associated with bear market entries.

    WHY SMA50 vs SMA200 (not SMA20 vs SMA50):
      SMA50/200 cross is the universally recognised definition of Golden/Death
      Cross. SMA20/50 crosses are too frequent (they're intermediate signals,
      not regime-change signals). We report the regime-change version.

    HOW detection works — sign change of the difference:
      We compute (fast - slow) for each bar. When this difference changes sign:
        negative → positive = fast just crossed above slow = Golden Cross
        positive → negative = fast just crossed below slow = Death Cross
      Scanning backwards gives the most recent event first.

    WHY lookback = 60:
      SMA50/200 crosses are rare events (maybe 2–4 per year). A 60-bar window
      (≈ 2 trading months) is long enough to catch a recent one but short
      enough that the signal is still actionable. A cross from 6 months ago is
      historical context, not a live signal.

    Args:
        fast: Fast MA series (e.g. SMA 50)
        slow: Slow MA series (e.g. SMA 200)
        lookback: How many recent bars to scan (default: 60)

    Returns:
        Tuple of (signal, days_ago) or (None, None) if no cross found.
        signal is "GOLDEN_CROSS" or "DEATH_CROSS".
    """
    # Align both series, drop bars where either has NaN (SMA200 needs 200 bars)
    combined = pd.DataFrame({"fast": fast, "slow": slow}).dropna()
    recent = combined.tail(lookback)

    if len(recent) < 2:
        return None, None

    # Scan from newest bar toward oldest — return on first (= most recent) hit
    for i in range(len(recent) - 1, 0, -1):
        curr_diff = recent["fast"].iloc[i] - recent["slow"].iloc[i]
        prev_diff = recent["fast"].iloc[i - 1] - recent["slow"].iloc[i - 1]

        if curr_diff > 0 and prev_diff <= 0:
            # fast just moved above slow
            return "GOLDEN_CROSS", len(recent) - 1 - i

        elif curr_diff < 0 and prev_diff >= 0:
            # fast just moved below slow
            return "DEATH_CROSS", len(recent) - 1 - i

    return None, None


# =============================================================================
# COMPREHENSIVE ANALYSIS
# =============================================================================

@dataclass
class TechnicalIndicators:
    """
    Complete technical analysis results — both static snapshots and dynamic signals.

    Static fields answer "where are we now?"
    Dynamic fields answer "where are we going?" — the critical missing context
    that a single-value snapshot cannot provide to an LLM.
    """

    # --- Moving Averages (static) ---
    sma_20: float
    sma_50: float
    sma_200: float
    ema_20: float
    ema_50: float
    ema_200: float

    # Price position relative to MAs (static — "above" or "below")
    price_vs_sma_20: str
    price_vs_sma_50: str
    price_vs_sma_200: str

    # MA slope labels (dynamic — tells the LLM if the trend is strengthening)
    # Format: "rising (+0.123%/d)" or "falling (-0.045%/d)" or "flat (+0.001%/d)"
    sma_20_slope: str
    sma_50_slope: str

    # MA cross signal (dynamic — regime-change event)
    ma_cross_signal: str | None     # "GOLDEN_CROSS" or "DEATH_CROSS" or None
    ma_cross_days_ago: int | None   # recency of the cross

    # --- RSI (static + dynamic) ---
    rsi_14: float
    rsi_interpretation: str        # OVERBOUGHT / OVERSOLD / bullish / bearish / neutral

    rsi_5d_ago: float              # RSI value 5 days ago — baseline for direction
    rsi_direction: str             # "rising", "falling", "flat" (dead band ±3 pts)
    rsi_divergence: str | None     # "BULLISH_DIVERGENCE", "BEARISH_DIVERGENCE", None

    # --- MACD (static snapshot + dynamic signals inside MACDResult) ---
    macd_result: MACDResult

    # --- Volatility (static + dynamic) ---
    atr_14: float
    atr_pct: float
    atr_direction: str             # "rising", "falling", "stable" (dead band ±10% relative)
    volatility_regime: VolatilityRegime

    # --- Overall summary (derived) ---
    trend_summary: str

    def format_for_llm(self, current_price: float) -> str:
        """
        Render all indicators as a structured text block for LLM consumption.

        Layout mirrors a professional trading terminal report:
        MOVING AVERAGES → MOMENTUM → VOLATILITY → TREND SUMMARY
        Each section leads with static values (context) then dynamic signals (actionable).
        """

        # Build MA cross line — always include, either the event or "none"
        if self.ma_cross_signal:
            ma_cross_str = (
                f"  MA Cross: {self.ma_cross_signal} "
                f"({self.ma_cross_days_ago}d ago — recent = stronger signal)"
            )
        else:
            ma_cross_str = "  MA Cross: none detected in recent history"

        # RSI divergence line — only emitted when divergence is present
        # (keeps output clean when there's nothing to report)
        rsi_divergence_line = ""
        if self.rsi_divergence:
            rsi_divergence_line = (
                f"\n  RSI Divergence: {self.rsi_divergence} "
                f"— price and RSI momentum are diverging (potential reversal)"
            )

        # MACD crossover line — always include
        if self.macd_result.crossover_type:
            macd_cross_str = (
                f"  MACD Crossover: {self.macd_result.crossover_type} crossover "
                f"{self.macd_result.crossover_days_ago}d ago"
            )
        else:
            macd_cross_str = "  MACD Crossover: none detected recently"

        # Histogram 5d series as arrow-connected values for readability
        hist_vals = " → ".join(str(v) for v in self.macd_result.histogram_5d)
        hist_trend_label = self.macd_result.histogram_trend.upper().replace("_", " ")

        lines = [
            "=== TECHNICAL INDICATORS ===",
            "",
            "MOVING AVERAGES:",
            f"  SMA(20):  {self.sma_20:>10.2f}  (price {self.price_vs_sma_20}, slope {self.sma_20_slope})",
            f"  SMA(50):  {self.sma_50:>10.2f}  (price {self.price_vs_sma_50}, slope {self.sma_50_slope})",
            f"  SMA(200): {self.sma_200:>10.2f}  (price {self.price_vs_sma_200})",
            f"  EMA(20):  {self.ema_20:>10.2f}",
            f"  EMA(50):  {self.ema_50:>10.2f}",
            f"  EMA(200): {self.ema_200:>10.2f}",
            ma_cross_str,
            "",
            "MOMENTUM:",
            (
                f"  RSI(14): {self.rsi_14:.1f} → {self.rsi_interpretation}"
                f"  [5d ago: {self.rsi_5d_ago:.1f}, direction: {self.rsi_direction}]"
                f"{rsi_divergence_line}"
            ),
            f"  MACD: {self.macd_result.macd_line:.2f} | Signal: {self.macd_result.signal_line:.2f} | Histogram: {self.macd_result.histogram:.2f}",
            f"  MACD Histogram (5d): [{hist_vals}] → {hist_trend_label}",
            macd_cross_str,
            f"  MACD Trend: {self.macd_result.trend}",
            "",
            "VOLATILITY:",
            f"  ATR(14): {self.atr_14:.2f} ({self.atr_pct:.2f}% of price, volatility {self.atr_direction})",
            f"  Regime: {self.volatility_regime}",
            "",
            f"TREND SUMMARY: {self.trend_summary}",
        ]
        return "\n".join(lines)


def calculate_all_indicators(df: pd.DataFrame) -> TechnicalIndicators:
    """
    Calculate all technical indicators for a price DataFrame.

    Computes full time series for each indicator (using the entire df history)
    then extracts both snapshot values and dynamic signals for the LLM.

    Args:
        df: DataFrame with 'price' column and datetime index.
            Should contain the full available history (not pre-sliced) so that
            long-period indicators like SMA(200) and MA cross detection have
            sufficient data.

    Returns:
        TechnicalIndicators dataclass with all static and dynamic fields populated
    """
    prices = df["price"]
    current_price = prices.iloc[-1]

    # --- Moving Average series (full history) ---
    sma_20_series = sma(prices, 20)
    sma_50_series = sma(prices, 50)
    sma_200_series = sma(prices, 200)
    ema_20_series = ema(prices, 20)
    ema_50_series = ema(prices, 50)
    ema_200_series = ema(prices, 200)

    # Extract latest scalar, fall back to current price if NaN
    # (NaN occurs when history is shorter than the MA period)
    sma_20_val  = sma_20_series.iloc[-1]  if not pd.isna(sma_20_series.iloc[-1])  else current_price
    sma_50_val  = sma_50_series.iloc[-1]  if not pd.isna(sma_50_series.iloc[-1])  else current_price
    sma_200_val = sma_200_series.iloc[-1] if not pd.isna(sma_200_series.iloc[-1]) else current_price
    ema_20_val  = ema_20_series.iloc[-1]  if not pd.isna(ema_20_series.iloc[-1])  else current_price
    ema_50_val  = ema_50_series.iloc[-1]  if not pd.isna(ema_50_series.iloc[-1])  else current_price
    ema_200_val = ema_200_series.iloc[-1] if not pd.isna(ema_200_series.iloc[-1]) else current_price

    # Static: price position relative to each MA
    price_vs_sma_20  = "above" if current_price > sma_20_val  else "below"
    price_vs_sma_50  = "above" if current_price > sma_50_val  else "below"
    price_vs_sma_200 = "above" if current_price > sma_200_val else "below"

    # Dynamic: MA slope — passes the full series so _compute_ma_slope can take
    # a trailing window from the complete history, not just the last value
    slope_20_val, slope_20_label = _compute_ma_slope(sma_20_series)
    slope_50_val, slope_50_label = _compute_ma_slope(sma_50_series)
    sma_20_slope = f"{slope_20_label} ({slope_20_val:+.3f}%/d)"
    sma_50_slope = f"{slope_50_label} ({slope_50_val:+.3f}%/d)"

    # Dynamic: Golden / Death Cross on SMA50 vs SMA200 (regime-change signal)
    ma_cross_signal, ma_cross_days_ago = _detect_ma_cross(sma_50_series, sma_200_series)

    # --- RSI series (full history) ---
    rsi_series = rsi(prices, 14)
    rsi_val    = rsi_series.iloc[-1] if not pd.isna(rsi_series.iloc[-1]) else 50.0
    rsi_interp = interpret_rsi(rsi_val)

    # Dynamic: RSI direction and divergence
    rsi_5d_ago, rsi_direction = _compute_rsi_direction(rsi_series)
    rsi_divergence = _detect_rsi_divergence(prices, rsi_series)

    # --- MACD (all dynamics computed inside get_macd_result) ---
    macd_result = get_macd_result(prices)

    # --- ATR / Volatility series (full history) ---
    atr_series     = atr_from_close(prices, 14)
    atr_pct_series = atr_percent(prices, 14)
    atr_val        = atr_series.iloc[-1]     if not pd.isna(atr_series.iloc[-1])     else 0.0
    atr_pct_val    = atr_pct_series.iloc[-1] if not pd.isna(atr_pct_series.iloc[-1]) else 0.0

    # Volatility regime uses the FULL historical ATR% series for percentile calc
    vol_regime    = classify_volatility_regime(atr_pct_val, atr_pct_series.dropna())
    atr_direction = _compute_atr_direction(atr_pct_series)

    # --- Trend Summary: simple scoring system ---
    # Each indicator casts a bullish or bearish vote. The total score determines
    # the overall trend label. Equal weight per signal; 5 signals max per side.
    bullish_signals = 0
    bearish_signals = 0

    if current_price > sma_20_val:          bullish_signals += 1
    else:                                   bearish_signals += 1

    if current_price > sma_50_val:          bullish_signals += 1
    else:                                   bearish_signals += 1

    if current_price > sma_200_val:         bullish_signals += 1
    else:                                   bearish_signals += 1

    if rsi_val > 50:                        bullish_signals += 1
    else:                                   bearish_signals += 1

    if macd_result.trend == "bullish":      bullish_signals += 1
    elif macd_result.trend == "bearish":    bearish_signals += 1
    # "neutral" MACD adds no vote to either side

    if bullish_signals >= 4:
        trend_summary = "BULLISH - price above key MAs with positive momentum"
    elif bearish_signals >= 4:
        trend_summary = "BEARISH - price below key MAs with negative momentum"
    elif bullish_signals > bearish_signals:
        trend_summary = "SLIGHTLY BULLISH - mixed signals with bullish bias"
    elif bearish_signals > bullish_signals:
        trend_summary = "SLIGHTLY BEARISH - mixed signals with bearish bias"
    else:
        trend_summary = "NEUTRAL - conflicting signals, no clear trend"

    return TechnicalIndicators(
        sma_20=sma_20_val,
        sma_50=sma_50_val,
        sma_200=sma_200_val,
        ema_20=ema_20_val,
        ema_50=ema_50_val,
        ema_200=ema_200_val,
        price_vs_sma_20=price_vs_sma_20,
        price_vs_sma_50=price_vs_sma_50,
        price_vs_sma_200=price_vs_sma_200,
        sma_20_slope=sma_20_slope,
        sma_50_slope=sma_50_slope,
        ma_cross_signal=ma_cross_signal,
        ma_cross_days_ago=ma_cross_days_ago,
        rsi_14=rsi_val,
        rsi_interpretation=rsi_interp,
        rsi_5d_ago=rsi_5d_ago,
        rsi_direction=rsi_direction,
        rsi_divergence=rsi_divergence,
        macd_result=macd_result,
        atr_14=atr_val,
        atr_pct=atr_pct_val,
        atr_direction=atr_direction,
        volatility_regime=vol_regime,
        trend_summary=trend_summary,
    )
