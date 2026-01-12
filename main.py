import os
from datetime import datetime, date, timedelta

import requests
import pandas as pd
from dotenv import load_dotenv
from exa_py import Exa

from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

missing = [k for k, v in {
    "GROQ_API_KEY": GROQ_API_KEY,
    "EXA_API_KEY": EXA_API_KEY,
    "ALPHAVANTAGE_API_KEY": ALPHAVANTAGE_API_KEY
}.items() if not v]

if missing:
    raise SystemExit(f"Missing env vars in .env {', '.join(missing)}")

exa = Exa(api_key=EXA_API_KEY)

llm = LLM(
    model="groq/llama-3.1-8b-instant",
    api_key=GROQ_API_KEY,
    temperature=0,
)

BAD_DOMAINS = [
    "wikipedia.org",
    "bitcoin.org",
    "coinmarketcap.com",
    "coingecko.com",
    "investopedia.com",
    "britannica.com",
    "dictionary.com",
    "medium.com",  # często definicje/SEO (opcjonalnie)
    "reddit.com",  # szum (opcjonalnie)
]


# -------------- API HELPERS --------------
def get_daily_closing_prices(ticker: str) -> pd.DataFrame:
    url = (
        "https://www.alphavantage.co/query"
        f"?function=DIGITAL_CURRENCY_DAILY&symbol={ticker}"
        f"&market=USD&apikey={ALPHAVANTAGE_API_KEY}"
    )
    resp = requests.get(url, timeout=30)
    data = resp.json()

    if "Note" in data:
        raise RuntimeError(f"AlphaVantage rate limit: {data['Note']}")
    if "Error Message" in data:
        raise RuntimeError(f"AlphaVantage error: {data['Error Message']}")
    if "Time Series (Digital Currency Daily)" not in data:
        raise RuntimeError(f"AlphaVantage unexpected response keys: {list(data.keys())}")

    ts = data["Time Series (Digital Currency Daily)"]

    # AlphaVantage bywa różny w nazewnictwie pól.
    # Najczęściej są: "4a. close (USD)" i/lub "4. close"
    def pick_close(prices: dict) -> float:
        for key in ("4a. close (USD)", "4. close", "4b. close (USD)"):
            if key in prices:
                return float(prices[key])
        # fallback: spróbuj znaleźć jakikolwiek "close"
        for k, v in prices.items():
            if "close" in k.lower():
                return float(v)
        raise KeyError(f"No close price key found. Available keys: {list(prices.keys())}")

    daily_close = {date: pick_close(prices) for date, prices in ts.items()}

    df = pd.DataFrame.from_dict(daily_close, orient="index", columns=["price"])
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()  # rosnąco po dacie (lepiej do zwrotów)
    return df


def get_crypto_news_recent(
        ticker_symbol: str,
        days_back: int = 7,
        limit: int = 5,
) -> str:
    start_date = (date.today() - timedelta(days=days_back)).isoformat()

    query = (
        f"Latest {ticker_symbol} news this week. "
        f"Focus on price drivers, regulation, ETFs, macro, exchange flows. "
        f"Avoid explanations of what {ticker_symbol} is."
    )

    result = exa.search_and_contents(
        query,
        summary=True,
        num_results=limit,
        start_published_date=start_date,
        exclude_domains=BAD_DOMAINS
    )

    if not result.results:
        return "No recent news results found."

    lines = []
    for item in result.results[:limit]:
        title = getattr(item, "title", "No Title")
        url = getattr(item, "url", "#")
        published = getattr(item, "published_date", "Unknown Date")
        summary = (getattr(item, "summary", "") or "").replace("\n", " ").strip()
        if len(summary) > 320:
            summary = summary[:317] + "..."

        lines.append(f"- {title}\n  Date: {published}\n  URL: {url}\n  Summary: {summary}")

    return "\n".join(lines)


# ---------- Tools (for agents) ----------
@tool("news_tool")
def news_tool(ticker_symbol: str) -> str:
    """Get compact latest news for a given cryptocurrency ticker (e.g., BTC)."""
    return get_crypto_news_recent(f"{ticker_symbol} cryptocurrency", limit=3)


@tool("price_tool")
def price_tool(ticker_symbol: str) -> str:
    """Get compact price summary for the given ticker (reduces tokens)."""
    df = get_daily_closing_prices(ticker_symbol)

    # weźmy ostatnie ~120 dni do statystyk (ale nie wysyłamy ich wszystkich!)
    df120 = df.tail(120).copy()
    df120["ret"] = df120["price"].pct_change()

    last = df120["price"].iloc[-1]
    first = df120["price"].iloc[0]
    change_pct = (last / first - 1.0) * 100.0

    vol_daily = df120["ret"].std() * 100.0  # % dziennie
    high = df120["price"].max()
    low = df120["price"].min()

    # momentum: ostatnie 7 i 30 dni
    df30 = df.tail(31).copy()
    mom_30 = (df30["price"].iloc[-1] / df30["price"].iloc[0] - 1.0) * 100.0 if len(df30) > 1 else 0.0

    df7 = df.tail(8).copy()
    mom_7 = (df7["price"].iloc[-1] / df7["price"].iloc[0] - 1.0) * 100.0 if len(df7) > 1 else 0.0

    # pokażmy tylko ostatnie 10 dni jako sample (żeby LLM nie “wymyślał” tabeli)
    last10 = df.tail(10)
    last10_lines = "\n".join([f"{d.strftime('%Y-%m-%d')}: {row['price']:.2f}" for d, row in last10.iterrows()])

    return (
        f"Ticker: {ticker_symbol}\n"
        f"Window: last {len(df120)} days\n"
        f"Last price: {last:.2f}\n"
        f"Change over window: {change_pct:.2f}%\n"
        f"High/Low: {high:.2f} / {low:.2f}\n"
        f"Volatility (daily std of returns): {vol_daily:.2f}%\n"
        f"Momentum 7d: {mom_7:.2f}%\n"
        f"Momentum 30d: {mom_30:.2f}%\n"
        f"Last 10 closes:\n{last10_lines}"
    )


# ---------- Main pipeline ----------
def run():
    symbol = input("Which cryptocurrency symbol do you want to analyze (e.g. BTC)? ").strip().upper()
    if not symbol:
        raise SystemExit("Empty symbol.")

    news_analyst = Agent(
        role="Cryptocurrency News Analyst",
        goal="Analyze crypto news and predict trend: up/down/neutral.",
        backstory="Expert in crypto news analysis and market sentiment",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[news_tool],
        max_iter=5,
    )

    price_analyst = Agent(
        role="Cryptocurrency Price Analyst",
        goal="Analyze historical prices and predict trend: up/down/neutral.",
        backstory="Expert in technical analysis based on historical prices.",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[price_tool],
        max_iter=5,
    )

    writer = Agent(
        role="Cryptocurrency Report Writer",
        goal="Combine analyses into a concise final report.",
        backstory="Senior analyst who writes clear, skeptical and useful summaries.",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        max_iter=5,
    )

    get_news_analysis = Task(
        description=f"""
            Use news_tool to fetch news about {symbol}.
            Today is {datetime.now().isoformat()}
            Write 1 paragraph analysis and end with  'Prediction: UP/DOWN/NEUTRAL'.""".strip()
        ,
        expected_output="One paragraph plus Prediction line.",
        agent=news_analyst,
    )

    get_price_analysis = Task(
        description=f"""
            Use price_tool to fetch recent prices for {symbol}.
            Today is {datetime.now().isoformat()}
            "Write 1 paragraph analysis and end with 'Prediction: UP/DOWN/NEUTRAL',""".strip()
        ,
        expected_output="One paragraph plus Prediction line.",
        agent=price_analyst,
    )

    write_report = Task(
        description=f"""
            Combine the news analysis and price analysis into a final report.
            Format:\n
            1) Executive summary (3 bullets)\n
            2) Final paragraph (max 6 sentences)\n
            3) Final prediction: UP/DOWN/NEUTRAL""".strip()
        ,
        expected_output="Report with bullets + paragraph + final prediction.",
        agent=writer,
        context=[get_news_analysis, get_price_analysis]
    )

    crew = Crew(
        agents=[news_analyst, price_analyst, writer],
        tasks=[get_news_analysis, get_price_analysis, write_report],
        process=Process.sequential,
        verbose=True,
        full_output=True,
        max_iter=15,
    )

    result = crew.kickoff()

    print(result)


if __name__ == "__main__":
    run()
