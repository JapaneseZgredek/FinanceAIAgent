import logging
from dataclasses import dataclass
from datetime import date, timedelta

from exa_py import Exa

from app.clients.cache import CacheManager
from app.config import CACHE_DIR, EXA_CACHE_TTL_MINUTES
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Exceptions that should trigger retry for Exa
EXA_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


@dataclass
class CachedNewsItem:
    """Simple dataclass to hold cached news item data."""
    title: str
    url: str
    published_date: str | None
    summary: str | None


@dataclass
class CachedNewsResponse:
    """Wrapper for cached news results."""
    results: list[CachedNewsItem]


class ExaClient:
    def __init__(self, api_key: str, cache_ttl_minutes: float | None = None):
        self.exa = Exa(api_key=api_key)
        ttl = cache_ttl_minutes if cache_ttl_minutes is not None else EXA_CACHE_TTL_MINUTES
        self.cache = CacheManager.with_ttl_minutes(CACHE_DIR, ttl)

    def _serialize_results(self, response) -> list[dict]:
        """Convert Exa response to serializable format."""
        items = []
        for item in response.results:
            items.append({
                "title": getattr(item, "title", None),
                "url": getattr(item, "url", None),
                "published_date": getattr(item, "published_date", None),
                "summary": getattr(item, "summary", None),
            })
        return items

    def _deserialize_results(self, data: list[dict]) -> CachedNewsResponse:
        """Convert cached data back to response-like object."""
        items = [CachedNewsItem(**item) for item in data]
        return CachedNewsResponse(results=items)

    def _get_cache_identifier(self, ticker_symbol: str, days_back: int, limit: int) -> str:
        """Generate cache identifier for news query."""
        return f"exa_news_{ticker_symbol.upper()}_{days_back}d_{limit}"

    @retry_with_backoff(
        max_retries=3,
        base_delay=2.0,
        max_delay=30.0,
        retryable_exceptions=EXA_RETRYABLE,
    )
    def search_recent_news(
        self,
        query: str,
        days_back: int,
        limit: int,
        exclude_domains: list[str],
        include_domains: list[str] | None = None,
    ):
        """Search for recent news with retry on transient errors."""
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

    def search_recent_news_strict(
        self,
        ticker_symbol: str,
        days_back: int,
        limit: int,
        exclude_domains: list[str],
        include_domains: list[str] | None = None,
    ):
        """
        Strict query tuned to avoid definitional pages and focus on market-moving events.
        Uses caching to prevent repeated API calls during frequent runs.
        """
        cache_id = self._get_cache_identifier(ticker_symbol, days_back, limit)

        # Check cache first
        cached_data, is_fresh = self.cache.get(cache_id)

        if cached_data and is_fresh:
            logger.info(f"Using cached news for {ticker_symbol} (TTL: {EXA_CACHE_TTL_MINUTES} min)")
            return self._deserialize_results(cached_data)

        # Build query
        query = (
            f"{ticker_symbol} news last {days_back} days "
            "ETF OR SEC OR regulation OR lawsuit OR hack OR exploit OR inflows OR outflows "
            "OR miners OR exchange OR CPI OR Fed OR rate OR liquidity OR macro "
            "-wikipedia -investopedia -guide -tutorial -what is -explained -definition"
        )

        try:
            response = self.search_recent_news(
                query=query,
                days_back=days_back,
                limit=limit,
                exclude_domains=exclude_domains,
                # include_domains=include_domains,
            )

            # Cache the results
            serialized = self._serialize_results(response)
            self.cache.set(cache_id, serialized)
            logger.info(f"Fetched and cached news for {ticker_symbol}")

            return response

        except Exception as e:
            # On error, try to use stale cache
            if cached_data:
                logger.warning(f"API error, falling back to cached news for {ticker_symbol}: {e}")
                return self._deserialize_results(cached_data)
            raise
