from crewai.tools import tool


def build_price_tool(alpha_client, *, window_days: int, last_n: int):
    @tool("price_tool")
    def price_tool(ticker_symbol: str) -> str:
        """
        Provide a compact statistical summary of recent cryptocurrency prices,
        including volatility, momentum and recent closes.
        
        Args:
            ticker_symbol: The cryptocurrency ticker symbol (e.g., "BTC", "ETH", "SOL")
        
        Example call: price_tool(ticker_symbol="BTC")
        """
        df = alpha_client.get_daily_prices(ticker_symbol)

        # bierzemy okno do statystyk, ale nie wysyłamy całego do LLM
        dfw = df.tail(window_days).copy()
        dfw["ret"] = dfw["price"].pct_change()

        last = dfw["price"].iloc[-1]
        first = dfw["price"].iloc[0]
        change_pct = (last / first - 1.0) * 100.0
        vol = dfw["ret"].std() * 100.0
        hi, lo = dfw["price"].max(), dfw["price"].min()

        # momentum
        m7_df = df.tail(8)
        mom7 = (m7_df["price"].iloc[-1] / m7_df["price"].iloc[0] - 1.0) * 100.0 if len(m7_df) > 1 else 0.0

        m30_df = df.tail(31)
        mom30 = (m30_df["price"].iloc[-1] / m30_df["price"].iloc[0] - 1.0) * 100.0 if len(m30_df) > 1 else 0.0

        last_slice = df.tail(last_n)
        last_lines = "\n".join([f"{d.strftime('%Y-%m-%d')}: {row['price']:.2f}" for d, row in last_slice.iterrows()])

        return (
            f"Ticker: {ticker_symbol}\n"
            f"Window: last {len(dfw)} days\n"
            f"Last price: {last:.2f}\n"
            f"Change over window: {change_pct:.2f}%\n"
            f"High/Low: {hi:.2f} / {lo:.2f}\n"
            f"Volatility (daily std of returns): {vol:.2f}%\n"
            f"Momentum 7d: {mom7:.2f}%\n"
            f"Momentum 30d: {mom30:.2f}%\n"
            f"Last {last_n} closes:\n{last_lines}"
        )

    return price_tool
