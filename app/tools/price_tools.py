import logging

from app.clients.alpha_vantage_client import AlphaVantageClient
from app.utils.indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


def get_formatted_price_data(alpha_client: AlphaVantageClient, symbol: str, window_days: int, last_n: int) -> str:
    """
    Fetch price data and return a formatted string with technical indicators.

    Args:
        alpha_client: AlphaVantageClient instance
        symbol: Cryptocurrency ticker symbol (e.g., "BTC", "ETH")
        window_days: Number of days to use for the analysis window
        last_n: Number of recent closes to include in output

    Returns:
        Formatted string with price stats, technical indicators, and recent closes.
    """
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

    return "\n".join(output_parts)
