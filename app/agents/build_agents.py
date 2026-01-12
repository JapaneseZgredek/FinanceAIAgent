from crewai import Agent


def build_agents(llm, *, news_tool, price_tool):
    news_analyst = Agent(
        role="Cryptocurrency News Analyst",
        goal="Analyze recent crypto news and predict trend: UP/DOWN/NEUTRAL.",
        backstory="Expert in crypto news analysis and market sentiment.",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[news_tool],
        max_iter=4,
    )

    price_analyst = Agent(
        role="Cryptocurrency Price Analyst",
        goal="Analyze historical prices (stats + last closes) and predict trend: UP/DOWN/NEUTRAL.",
        backstory="Expert in technical analysis based on historical prices.",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        tools=[price_tool],
        max_iter=4,
    )

    writer = Agent(
        role="Cryptocurrency Report Writer",
        goal="Combine analyses into a concise final report.",
        backstory="Writes clear, skeptical and useful summaries.",
        llm=llm,
        verbose=True,
        memory=True,
        allow_delegation=False,
        max_iter=4,
    )

    return news_analyst, price_analyst, writer
