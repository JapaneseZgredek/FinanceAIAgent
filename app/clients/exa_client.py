from datetime import date, timedelta
from exa_py import Exa


class ExaClient:
    def __init__(self, api_key: str):
        self.exa = Exa(api_key=api_key)

    def search_recent_news(
        self,
        query: str,
        days_back: int,
        limit: int,
        exclude_domains: list[str],
        include_domains: list[str] | None = None,
    ):
        start_date = (date.today() - timedelta(days=days_back)).isoformat()

        kwargs = dict(
            query=query,
            summary=True,
            num_results=limit,
            start_published_date=start_date,
            exclude_domains=exclude_domains,
        )
        if include_domains:
            kwargs["include_domains"] = include_domains

        return self.exa.search_and_contents(**kwargs)
