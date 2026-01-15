from datetime import datetime
from crewai import Task


def build_tasks(symbol: str, *, news_analyst, price_analyst, writer):
    now = datetime.now().isoformat()

    get_news_analysis = Task(
        description=f"""
            Use news_tool to fetch recent news about {symbol}.
            Today is {now}.
            Output format (STRICT):
            1) Events (3-5 bullets): each bullet MUST include a URL.
            2) Sentiment: Positive/Negative/Mixed (1 line)
            3) Prediction: UP/DOWN/NEUTRAL (1 line)
            Rules:
            - No definitions of what {symbol} is.
            - No Wikipedia / official docs style content.
            """.strip(),
        expected_output="Events bullets with URLs + sentiment + prediction.",
        agent=news_analyst,
    )

    get_price_analysis = Task(
        description=f"""
            Use price_tool to fetch recent prices summary about {symbol}.
            Today is {now}.
            Write 1 paragraph analysis and end with: Prediction: UP/DOWN/NEUTRAL
            """.strip(),
        expected_output="One paragraph plus a final 'Prediction: ...' line.",
        agent=price_analyst,
    )

    write_report = Task(
        description="""
            Combine the news analysis and price analysis into a final report.
            Format:
            1) Executive summary (3 bullets max)
            2) Final paragraph (max 6 sentences)
            3) Final prediction: UP/DOWN/NEUTRAL
            """.strip(),
        expected_output="Bullets + short paragraph + final prediction line.",
        agent=writer,
        context=[get_news_analysis, get_price_analysis],
    )

    return [get_news_analysis, get_price_analysis, write_report]
