from crewai import Crew, Process, LLM

from app.config import (
    validate_env,
    GROQ_API_KEY, GROQ_MODEL,
    EXA_API_KEY, ALPHAVANTAGE_API_KEY,
    BAD_DOMAINS, GOOD_NEWS_DOMAINS,
    NEWS_DAYS_BACK, NEWS_LIMIT, NEWS_MAX_SUMMARY_CHARS,
    PRICE_WINDOW_DAYS, PRICE_LAST_N,
    USE_INCLUDE_DOMAINS,
)

from app.clients.exa_client import ExaClient
from app.clients.alpha_vantage_client import AlphaVantageClient
from app.tools.news_tools import build_news_tool
from app.tools.price_tools import build_price_tool
from app.agents.build_agents import build_agents
from app.tasks.build_tasks import build_tasks


def run(symbol: str):
    validate_env()

    llm = LLM(
        model=GROQ_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0,
        # Retry configuration for transient errors
        num_retries=3,
        timeout=60,
    )

    exa_client = ExaClient(EXA_API_KEY)
    alpha_client = AlphaVantageClient(ALPHAVANTAGE_API_KEY)

    news_tool = build_news_tool(
        exa_client,
        bad_domains=BAD_DOMAINS,
        good_domains=GOOD_NEWS_DOMAINS,
        days_back=NEWS_DAYS_BACK,
        limit=NEWS_LIMIT,
        max_summary_chars=NEWS_MAX_SUMMARY_CHARS,
        use_include_domains=USE_INCLUDE_DOMAINS,
    )
    price_tool = build_price_tool(
        alpha_client,
        window_days=PRICE_WINDOW_DAYS,
        last_n=PRICE_LAST_N,
    )

    news_analyst, price_analyst, writer = build_agents(llm, news_tool=news_tool, price_tool=price_tool)
    tasks = build_tasks(symbol, news_analyst=news_analyst, price_analyst=price_analyst, writer=writer)

    crew = Crew(
        agents=[news_analyst, price_analyst, writer],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        full_output=True,
        max_iter=12,
    )

    return crew.kickoff()
