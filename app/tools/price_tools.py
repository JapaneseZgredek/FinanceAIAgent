import logging
from crewai.tools import tool

from app.utils.prompt_limits import (
    enforce_tool_output_limits,
    ABSOLUTE_MAX_PRICE_HISTORY_LINES,
)
from app.utils.indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


def build_price_tool(alpha_client, *, window_days: int, last_n: int):
    @tool("price_tool")
    def price_tool(ticker_symbol: str) -> str:
        """
        Provide a comprehensive technical analysis of recent cryptocurrency prices,
        including moving averages (SMA/EMA), RSI, MACD, volatility regime, and trend summary.
        
        Args:
            ticker_symbol: The cryptocurrency ticker symbol (e.g., "BTC", "ETH", "SOL")
        
        Example call: price_tool(ticker_symbol="BTC")
        """
        df = alpha_client.get_daily_prices(ticker_symbol)

        # Enforce hard cap on price history lines
        safe_last_n = min(last_n, ABSOLUTE_MAX_PRICE_HISTORY_LINES)
        if safe_last_n < last_n:
            logger.warning(f"PRICE_LAST_N capped from {last_n} to {safe_last_n}")

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
            f"Ticker: {ticker_symbol}",
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
        
        output = "\n".join(output_parts)
        
        # Apply final output size limit
        return enforce_tool_output_limits(output, "price_tool")

    return price_tool
