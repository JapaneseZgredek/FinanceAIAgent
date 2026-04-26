import logging

from app.clients.alpha_vantage_client import AlphaVantageClient
from app.utils.indicators import TechnicalIndicators, calculate_all_indicators

logger = logging.getLogger(__name__)


def compute_pre_decision(indicators: TechnicalIndicators) -> str:
    """
    Compute a deterministic trading entry decision from technical indicators.

    This function is the core of the non-determinism fix: it calculates the
    entry decision in Python before any LLM call, using objective, threshold-based
    rules. The result is injected into the Step 3 prompt as a hard constraint,
    preventing the LLM from reaching different decisions on the same data.

    Decision algorithm:
      1. Score each time horizon as bearish/bullish using objective indicator thresholds.
      2. Check ATR phase (compressing = falling direction, stable/expanding otherwise).
      3. Apply mechanical rules (no subjective interpretation):
           - < 2 aligned horizons          → NO (insufficient structure)
           - >= 2 aligned + ATR compressing → WAIT (breakout has not materialised)
           - 3/3 aligned + ATR stable/rising → ENTER (maximum confluence)
           - 2/3 aligned + ATR stable/rising → WAIT (partial alignment)

    Note: FOMC proximity and HIGH risk factor overrides are NOT applied here —
    they depend on Step 1 (news) data not yet available at this stage and remain
    in the prompt as LLM-applied overrides.

    Args:
        indicators: TechnicalIndicators dataclass from calculate_all_indicators().

    Returns:
        Formatted multi-line string summarising the pre-computed decision,
        suitable for injection into the Step 3 prompt.
    """
    # --- Short-term horizon (1–7 days): MACD snapshot trend ---
    # MACDResult.trend is "bearish" only when histogram < 0 AND MACD < Signal,
    # making it an objective, threshold-based classification with no subjectivity.
    short_bearish = indicators.macd_result.trend == "bearish"
    short_bullish = indicators.macd_result.trend == "bullish"

    # --- Medium-term horizon (2–6 weeks): price vs SMA20 + SMA50 ---
    # Both MAs must agree — single-MA crossing is ambiguous.
    medium_bearish = (
        indicators.price_vs_sma_20 == "below"
        and indicators.price_vs_sma_50 == "below"
    )
    medium_bullish = (
        indicators.price_vs_sma_20 == "above"
        and indicators.price_vs_sma_50 == "above"
    )

    # --- Long-term horizon (3–6 months): price vs SMA200 ---
    long_bearish = indicators.price_vs_sma_200 == "below"
    long_bullish = indicators.price_vs_sma_200 == "above"

    bearish_count = sum([short_bearish, medium_bearish, long_bearish])
    bullish_count = sum([short_bullish, medium_bullish, long_bullish])
    aligned = max(bearish_count, bullish_count)
    direction = "BEARISH" if bearish_count >= bullish_count else "BULLISH"

    atr_compressing = indicators.atr_direction == "falling"
    atr_phase = (
        "COMPRESSING (falling — volatility contracting, breakout pending)"
        if atr_compressing
        else f"{indicators.atr_direction.upper()} (volatility {indicators.atr_direction})"
    )

    # Horizon detail lines
    short_label = "BEARISH" if short_bearish else ("BULLISH" if short_bullish else "NEUTRAL")
    medium_label = "BEARISH" if medium_bearish else ("BULLISH" if medium_bullish else "MIXED")
    long_label = "BEARISH" if long_bearish else "BULLISH"

    # Mechanical decision rule
    if aligned < 2:
        decision = "NO"
        reasoning = (
            "Fewer than 2 horizons align — no coherent directional structure to trade."
        )
    elif atr_compressing:
        decision = "WAIT"
        reasoning = (
            f"{aligned}/3 horizons aligned ({direction.lower()}) but ATR is compressing — "
            "the directional breakout has not yet materialised. "
            "Entry now means absorbing the full compression-to-expansion range as drawdown. "
            "Wait for ATR to begin expanding (confirm the breakout direction first)."
        )
    elif aligned == 3:
        decision = "ENTER"
        reasoning = (
            "All 3 horizons aligned + ATR stable/expanding — maximum technical confluence. "
            "Directional structure is clear and volatility supports the move."
        )
    else:
        # aligned == 2, ATR not compressing
        decision = "WAIT"
        reasoning = (
            "2/3 horizons aligned but third is ambiguous — partial confluence only. "
            "Wait for the third horizon to confirm before entering."
        )

    return (
        f"Short-term  (1–7d):   {short_label}  "
        f"[MACD trend={indicators.macd_result.trend}, "
        f"histogram={indicators.macd_result.histogram:.2f}]\n"
        f"Medium-term (2–6w):   {medium_label}  "
        f"[price {indicators.price_vs_sma_20} SMA20, "
        f"price {indicators.price_vs_sma_50} SMA50]\n"
        f"Long-term   (3–6m):   {long_label}  "
        f"[price {indicators.price_vs_sma_200} SMA200]\n"
        f"ATR phase:            {atr_phase}\n"
        f"Volatility regime:    {indicators.volatility_regime}\n"
        f"\n"
        f"BASELINE DECISION: {decision}\n"
        f"Reasoning: {reasoning}"
    )


def get_formatted_price_data(
    alpha_client: AlphaVantageClient,
    symbol: str,
    window_days: int,
    last_n: int,
) -> tuple[str, str]:
    """
    Fetch price data and return a formatted string with technical indicators
    plus a deterministic pre-computed trading decision.

    Args:
        alpha_client: AlphaVantageClient instance
        symbol: Cryptocurrency ticker symbol (e.g., "BTC", "ETH")
        window_days: Number of days to use for the analysis window
        last_n: Number of recent closes to include in output

    Returns:
        Tuple of:
          - formatted_data: Formatted string with price stats, technical indicators,
            and recent closes (passed to Step 2 — price analysis prompt).
          - pre_decision: Deterministic entry decision string from compute_pre_decision()
            (passed to Step 3 — final report prompt as a hard constraint).
    """
    logger.info("Computing price data for %s (window=%dd, last_n=%d)", symbol, window_days, last_n)
    df = alpha_client.get_daily_prices(symbol)

    # Cap recent closes at 30 — beyond that the list adds noise without value
    safe_last_n = min(last_n, 30)

    # Basic stats for the analysis window
    dfw = df.tail(window_days).copy()
    dfw["ret"] = dfw["price"].pct_change()

    last = dfw["price"].iloc[-1]
    first = dfw["price"].iloc[0]
    change_pct = (last / first - 1.0) * 100.0
    vol = dfw["ret"].std() * 100.0
    hi, lo = dfw["price"].max(), dfw["price"].min()

    # Momentum (simple)
    m7_df = df.tail(8)
    mom7 = (m7_df["price"].iloc[-1] / m7_df["price"].iloc[0] - 1.0) * 100.0 if len(m7_df) > 1 else 0.0

    m30_df = df.tail(31)
    mom30 = (m30_df["price"].iloc[-1] / m30_df["price"].iloc[0] - 1.0) * 100.0 if len(m30_df) > 1 else 0.0

    # Calculate technical indicators (SMA, EMA, RSI, MACD, ATR)
    indicators = calculate_all_indicators(df)
    logger.debug(
        "Indicators for %s: RSI=%.1f, MACD trend=%s, vs SMA200=%s, volatility=%s",
        symbol, indicators.rsi_14, indicators.macd_result.trend,
        indicators.price_vs_sma_200, indicators.volatility_regime,
    )

    # Recent closes
    last_slice = df.tail(safe_last_n)
    last_lines = "\n".join([f"{d.strftime('%Y-%m-%d')}: {row['price']:.2f}" for d, row in last_slice.iterrows()])

    # Build output
    output_parts = [
        f"Ticker: {symbol}",
        f"Window: last {len(dfw)} days",
        f"Last price: {last:.2f}",
        f"Change over window: {change_pct:.2f}%",
        f"High/Low: {hi:.2f} / {lo:.2f}",
        f"Volatility (daily std): {vol:.2f}%",
        f"Momentum 7d: {mom7:.2f}%",
        f"Momentum 30d: {mom30:.2f}%",
        "",
        indicators.format_for_llm(last),
        "",
        f"Last {safe_last_n} closes:",
        last_lines,
    ]

    formatted_data = "\n".join(output_parts)
    pre_decision = compute_pre_decision(indicators)
    logger.debug("Price data formatted for %s: %d chars", symbol, len(formatted_data))
    return formatted_data, pre_decision
