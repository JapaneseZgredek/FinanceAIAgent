from crewai.tools import tool


def build_news_tool(exa_client, *, bad_domains, good_domains, days_back, limit, max_summary_chars, use_include_domains: bool):
    @tool("news_tool")
    def news_tool(ticker_symbol: str) -> str:
        """
        Fetch recent, non-definitional cryptocurrency news for the given ticker symbol.
        Filters out encyclopedic and tracking websites and focuses on recent market-moving events.
        """
        query = f"""Latest {ticker_symbol} news this week. 
            Focus on price drivers, regulation, ETFs, macro, exchange flows.
            Avoid explanations of what {ticker_symbol} is.""".strip()

        include = good_domains if use_include_domains else None
        res = exa_client.search_recent_news(
            query=query,
            days_back=days_back,
            limit=limit,
            exclude_domains=bad_domains,
            include_domains=include,
        )

        if not res.results:
            return "No recent news results found."

        # dodatkowo wycinamy wyniki bez daty (często evergreen/encyklopedia)
        items = [x for x in res.results if getattr(x, "published_date", None)]
        if not items:
            items = res.results

        out = []
        for item in items[:limit]:
            title = getattr(item, "title", "No Title")
            url = getattr(item, "url", "#")
            published = getattr(item, "published_date", "Unknown Date")
            summary = (getattr(item, "summary", "") or "").replace("\n", " ").strip()

            if len(summary) > max_summary_chars:
                summary = summary[: max_summary_chars - 3] + "..."

            out.append(f"- {title}\n  Date: {published}\n  URL: {url}\n  Summary: {summary}")

        return "\n".join(out)

    return news_tool
