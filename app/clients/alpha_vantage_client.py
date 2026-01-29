import logging

import requests
import pandas as pd

from app.clients.cache import CacheManager
from app.config import CACHE_DIR, CACHE_TTL_HOURS
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# Exceptions that should trigger retry for Alpha Vantage
ALPHA_VANTAGE_RETRYABLE = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class AlphaVantageClient:
    def __init__(self, api_key: str, cache_ttl_hours: float | None = None):
        self.api_key = api_key
        ttl = cache_ttl_hours if cache_ttl_hours is not None else CACHE_TTL_HOURS
        self.cache = CacheManager.with_ttl_hours(CACHE_DIR, ttl)

    @retry_with_backoff(
        max_retries=3,
        base_delay=2.0,
        max_delay=30.0,
        retryable_exceptions=ALPHA_VANTAGE_RETRYABLE,
    )
    def _fetch_from_api(self, ticker: str) -> dict:
        """Make the actual API request to Alpha Vantage with retry."""
        url = (
            "https://www.alphavantage.co/query"
            f"?function=DIGITAL_CURRENCY_DAILY&symbol={ticker}"
            f"&market=USD&apikey={self.api_key}"
        )
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # Raise on HTTP errors
        return response.json()

    def _get_cache_identifier(self, ticker: str) -> str:
        """Generate cache identifier for a ticker."""
        return f"alphavantage_daily_{ticker.upper()}"

    def get_daily_prices(self, ticker: str) -> pd.DataFrame:
        cache_id = self._get_cache_identifier(ticker)

        # Check cache first
        cached_data, is_fresh = self.cache.get(cache_id)

        if cached_data and is_fresh:
            logger.info(f"Using fresh cached data for {ticker}")
            data = cached_data
        else:
            # Try to fetch from API
            try:
                data = self._fetch_from_api(ticker)

                # Check for rate limit
                if "Note" in data:
                    if cached_data:
                        logger.warning(
                            f"Rate limited by AlphaVantage, falling back to cached data for {ticker}"
                        )
                        data = cached_data
                    else:
                        raise RuntimeError(f"AlphaVantage rate limit: {data['Note']}")

                # Check for API errors
                elif "Error Message" in data:
                    if cached_data:
                        logger.warning(
                            f"API error, falling back to cached data for {ticker}: {data['Error Message']}"
                        )
                        data = cached_data
                    else:
                        raise RuntimeError(f"AlphaVantage error: {data['Error Message']}")

                # Validate response has expected data
                elif "Time Series (Digital Currency Daily)" not in data:
                    if cached_data:
                        logger.warning(
                            f"Unexpected response, falling back to cached data for {ticker}"
                        )
                        data = cached_data
                    else:
                        raise RuntimeError(f"Unexpected response keys: {list(data.keys())}")

                # Success - cache the new data
                else:
                    self.cache.set(cache_id, data)
                    logger.info(f"Fetched and cached fresh data for {ticker}")

            except requests.RequestException as e:
                # Network error - try to use stale cache
                if cached_data:
                    logger.warning(
                        f"Network error, falling back to cached data for {ticker}: {e}"
                    )
                    data = cached_data
                else:
                    raise RuntimeError(f"Network error and no cached data available: {e}")

        ts = data["Time Series (Digital Currency Daily)"]

        def pick_close(prices: dict) -> float:
            for key in ("4a. close (USD)", "4. close", "4b. close (USD)"):
                if key in prices:
                    return float(prices[key])
            for k, v in prices.items():
                if "close" in k.lower():
                    return float(v)
            raise KeyError(f"No close key found. Keys: {list(prices.keys())}")

        close = {d: pick_close(p) for d, p in ts.items()}
        df = pd.DataFrame.from_dict(close, orient="index", columns=["price"])
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()  # ascending order
        return df
