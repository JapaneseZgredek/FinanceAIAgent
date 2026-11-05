"""Unit tests for app/clients/alpha_vantage_client.py — price data fetching + caching."""

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from app.clients.alpha_vantage_client import AlphaVantageClient
from app.clients.cache import CacheManager
from app.config import CACHE_DIR, CACHE_TTL_HOURS

_TEST_API_KEY = "test-alpha-vantage-key"


# ---------------------------------------------------------------------------
# Fixtures (specific to alpha_vantage — not reusable across clients)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_cache():
    with patch("app.clients.alpha_vantage_client.CacheManager") as MockCache:
        cache = MockCache.with_ttl_hours.return_value
        cache.get.return_value = (None, False)
        cache.mock_add_spec(CacheManager)
        yield cache


@pytest.fixture
def client(mock_cache):
    return AlphaVantageClient(api_key=_TEST_API_KEY)


def _make_response(payload: dict) -> MagicMock:
    """Build a mock requests.Response returning the given JSON payload."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def valid_http_response(alpha_vantage_response):
    """Wrap shared alpha_vantage_response into a spec'd requests.Response mock."""
    return _make_response(alpha_vantage_response)


@pytest.fixture
def mock_http_get():
    with patch("app.clients.alpha_vantage_client.requests.get") as mock_get:
        yield mock_get


@pytest.fixture
def stale_cache(mock_cache, alpha_vantage_response):
    """Cache returns data but is_fresh=False — simulates expired cache."""
    mock_cache.get.return_value = (alpha_vantage_response, False)
    return mock_cache


# ===================================================================
# Construction
# ===================================================================


class TestConstruction:
    @patch("app.clients.alpha_vantage_client.CacheManager")
    def test_default_ttl_uses_config_value(self, MockCache):
        AlphaVantageClient(api_key="key")
        MockCache.with_ttl_hours.assert_called_once_with(CACHE_DIR, CACHE_TTL_HOURS)

    @patch("app.clients.alpha_vantage_client.CacheManager")
    def test_custom_ttl_passed_through(self, MockCache):
        AlphaVantageClient(api_key="key", cache_ttl_hours=8.0)
        MockCache.with_ttl_hours.assert_called_once_with(CACHE_DIR, 8.0)


# ===================================================================
# get_daily_prices — cache scenarios
# ===================================================================


class TestGetDailyPricesCaching:
    def test_fresh_cache_skips_http_and_write(self, mock_http_get, client, mock_cache, alpha_vantage_response):
        mock_cache.get.return_value = (alpha_vantage_response, True)

        df = client.get_daily_prices("BTC")
        mock_http_get.assert_not_called()
        mock_cache.set.assert_not_called()
        assert isinstance(df, pd.DataFrame)
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    def test_cache_miss_fetches_and_caches(
        self, mock_http_get, client, mock_cache, valid_http_response, alpha_vantage_response
    ):
        mock_http_get.return_value = valid_http_response

        df = client.get_daily_prices("BTC")
        mock_http_get.assert_called_once()
        mock_cache.set.assert_called_once_with("alphavantage_daily_BTC", alpha_vantage_response)
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    def test_stale_cache_with_successful_fetch_refreshes(self, mock_http_get, client, stale_cache, valid_http_response):
        mock_http_get.return_value = valid_http_response

        client.get_daily_prices("BTC")
        mock_http_get.assert_called_once()
        stale_cache.set.assert_called_once()


# ===================================================================
# get_daily_prices — API error fallbacks
# ===================================================================


class TestGetDailyPricesErrors:
    def test_rate_limit_with_stale_cache(self, mock_http_get, client, stale_cache, alpha_vantage_response, caplog):
        mock_http_get.return_value = _make_response({"Note": "API call frequency limit reached"})

        with caplog.at_level(logging.WARNING):
            df = client.get_daily_prices("BTC")
        assert "Rate limited by AlphaVantage, falling back to cached data" in caplog.text
        stale_cache.set.assert_not_called()
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    def test_rate_limit_no_cache_raises(self, mock_http_get, client, mock_cache):
        mock_http_get.return_value = _make_response({"Note": "API call frequency limit reached"})

        with pytest.raises(RuntimeError, match="AlphaVantage rate limit"):
            client.get_daily_prices("BTC")
        mock_cache.set.assert_not_called()

    def test_error_message_with_stale_cache(self, mock_http_get, client, stale_cache, alpha_vantage_response, caplog):
        mock_http_get.return_value = _make_response({"Error Message": "Invalid ticker"})

        with caplog.at_level(logging.WARNING):
            df = client.get_daily_prices("BTC")
        assert "API error, falling back to cached data" in caplog.text
        stale_cache.set.assert_not_called()
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    def test_error_message_no_cache_raises(self, mock_http_get, client, mock_cache):
        mock_http_get.return_value = _make_response({"Error Message": "Invalid ticker XYZ"})

        with pytest.raises(RuntimeError, match="AlphaVantage error"):
            client.get_daily_prices("XYZ")
        mock_cache.set.assert_not_called()

    def test_unexpected_response_with_stale_cache(
        self, mock_http_get, client, stale_cache, alpha_vantage_response, caplog
    ):
        mock_http_get.return_value = _make_response({"unexpected_key": "???"})

        with caplog.at_level(logging.WARNING):
            df = client.get_daily_prices("BTC")
        assert "Unexpected response, falling back to cached data" in caplog.text
        stale_cache.set.assert_not_called()
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    def test_unexpected_response_no_cache_raises(self, mock_http_get, client, mock_cache):
        mock_http_get.return_value = _make_response({"unexpected_key": "???"})

        with pytest.raises(RuntimeError, match="Unexpected response"):
            client.get_daily_prices("BTC")
        mock_cache.set.assert_not_called()

    @patch("app.utils.retry.time.sleep")
    def test_network_error_with_stale_cache(
        self, _sleep, mock_http_get, client, stale_cache, alpha_vantage_response, caplog
    ):
        mock_http_get.side_effect = requests.ConnectionError("DNS failed")

        with caplog.at_level(logging.WARNING):
            df = client.get_daily_prices("BTC")
        assert "Network error, falling back to cached data" in caplog.text
        stale_cache.set.assert_not_called()
        expected_rows = len(alpha_vantage_response["Time Series (Digital Currency Daily)"])
        assert len(df) == expected_rows

    @patch("app.utils.retry.time.sleep")
    def test_network_error_no_cache_raises(self, _sleep, mock_http_get, client, mock_cache):
        mock_http_get.side_effect = requests.ConnectionError("DNS failed")

        with pytest.raises(RuntimeError, match="Network error and no cached data"):
            client.get_daily_prices("BTC")
        mock_cache.set.assert_not_called()


# ===================================================================
# get_daily_prices — DataFrame structure
# ===================================================================


class TestGetDailyPricesDataFrame:
    def test_columns_and_index_type(self, mock_http_get, client, valid_http_response):
        mock_http_get.return_value = valid_http_response

        df = client.get_daily_prices("BTC")
        assert "price" in df.columns
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_ascending_sort_order(self, mock_http_get, client, valid_http_response):
        mock_http_get.return_value = valid_http_response

        df = client.get_daily_prices("BTC")
        assert df.index.is_monotonic_increasing

    def test_close_key_variant_4a(self, mock_http_get, client):
        ts = {
            "2026-05-01": {"4a. close (USD)": "67000.12345678"},
            "2026-05-02": {"4a. close (USD)": "67500.00000000"},
        }
        mock_http_get.return_value = _make_response(
            {
                "Meta Data": {},
                "Time Series (Digital Currency Daily)": ts,
            }
        )

        df = client.get_daily_prices("BTC")
        assert len(df) == 2
        assert df["price"].iloc[0] == pytest.approx(67000.12345678)

    def test_close_key_variant_4b(self, mock_http_get, client):
        ts = {
            "2026-05-01": {"4b. close (USD)": "68000.00000000"},
        }
        mock_http_get.return_value = _make_response(
            {
                "Meta Data": {},
                "Time Series (Digital Currency Daily)": ts,
            }
        )

        df = client.get_daily_prices("BTC")
        assert df["price"].iloc[0] == pytest.approx(68000.0)

    def test_close_key_fuzzy_fallback(self, mock_http_get, client, caplog):
        # Klucz spoza jawnej listy, ale zawiera "close" → druga pętla + warning
        ts = {"2026-05-01": {"8. close USD (legacy)": "70000.0"}}
        mock_http_get.return_value = _make_response({"Meta Data": {}, "Time Series (Digital Currency Daily)": ts})

        with caplog.at_level(logging.WARNING):
            df = client.get_daily_prices("BTC")
        assert df["price"].iloc[0] == pytest.approx(70000.0)
        assert "fuzzy match" in caplog.text

    def test_no_close_key_raises_keyerror(self, mock_http_get, client):
        ts = {"2026-05-01": {"1. open": "100", "2. high": "110"}}
        mock_http_get.return_value = _make_response({"Meta Data": {}, "Time Series (Digital Currency Daily)": ts})

        with pytest.raises(KeyError, match="No close key"):
            client.get_daily_prices("BTC")

    def test_close_key_prefers_usd_over_market_currency(self, mock_http_get, client):
        # Stary format AV: close w walucie rynku ORAZ w USD. EUR jest pierwszy
        # w dict — fuzzy wzięłaby JEGO. Jawna lista musi wybrać USD.
        ts = {"2026-05-01": {"4a. close (EUR)": "61000.0", "4b. close (USD)": "67000.0"}}
        mock_http_get.return_value = _make_response({"Meta Data": {}, "Time Series (Digital Currency Daily)": ts})

        df = client.get_daily_prices("BTC")
        assert df["price"].iloc[0] == pytest.approx(67000.0)  # NIE 61000

    def test_close_key_explicit_order_wins_over_dict_order(self, mock_http_get, client):
        # "4. close" pierwszy w dict, ale krotka priorytetowa stawia 4a wyżej
        ts = {"2026-05-01": {"4. close": "60000.0", "4a. close (USD)": "67000.0"}}
        mock_http_get.return_value = _make_response({"Meta Data": {}, "Time Series (Digital Currency Daily)": ts})

        df = client.get_daily_prices("BTC")
        assert df["price"].iloc[0] == pytest.approx(67000.0)

    def test_empty_time_series_raises(self, mock_http_get, client):
        # Pusty time series → jasny RuntimeError zamiast IndexError z linii loga
        mock_http_get.return_value = _make_response({"Meta Data": {}, "Time Series (Digital Currency Daily)": {}})

        with pytest.raises(RuntimeError, match="No price data"):
            client.get_daily_prices("BTC")


# ===================================================================
# _fetch_from_api
# ===================================================================


class TestFetchFromApi:
    def test_success_returns_dict_and_calls_raise_for_status(self, mock_http_get, client, valid_http_response):
        mock_http_get.return_value = valid_http_response
        result = client._fetch_from_api("BTC")
        assert "Time Series (Digital Currency Daily)" in result
        valid_http_response.raise_for_status.assert_called_once()
        _, kwargs = mock_http_get.call_args
        assert kwargs["timeout"] == 30

    def test_http_error_not_retried(self, mock_http_get, client):
        mock_http_get.return_value.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with pytest.raises(requests.HTTPError):
            client._fetch_from_api("BTC")
        assert mock_http_get.call_count == 1

    def test_url_contains_all_query_params(self, mock_http_get, client, valid_http_response):
        mock_http_get.return_value = valid_http_response
        client._fetch_from_api("ETH")
        url = mock_http_get.call_args.args[0]
        assert "function=DIGITAL_CURRENCY_DAILY" in url
        assert "symbol=ETH" in url
        assert "market=USD" in url
        assert f"apikey={_TEST_API_KEY}" in url
