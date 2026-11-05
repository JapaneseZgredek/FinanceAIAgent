"""Shared fixtures for unit tests."""

import numpy as np
import pandas as pd
import pytest

from app.clients.macro_client import MacroSnapshot
from app.utils.indicators import MACDResult, TechnicalIndicators

# ---------------------------------------------------------------------------
# Price DataFrames
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_price_df() -> pd.DataFrame:
    """~250 rows of deterministic BTC-like price data (seed=42)."""
    rng = np.random.default_rng(42)
    n = 250
    dates = pd.bdate_range(end="2026-05-01", periods=n)
    prices = 60_000 + np.cumsum(rng.normal(50, 800, n))
    prices = np.maximum(prices, 1000)
    return pd.DataFrame({"price": prices}, index=dates)


@pytest.fixture(scope="session")
def short_price_df() -> pd.DataFrame:
    """10 rows — too short for SMA200; useful for edge-case tests."""
    dates = pd.bdate_range(end="2026-05-01", periods=10)
    prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 110]
    return pd.DataFrame({"price": prices}, index=dates)


@pytest.fixture(scope="session")
def btc_historical_atr_pct() -> pd.Series:
    """120 days of realistic BTC ATR% values for volatility regime tests."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(loc=2.8, scale=0.9, size=120).clip(0.5, 8.0))


# ---------------------------------------------------------------------------
# TechnicalIndicators fixtures for compute_pre_decision
# ---------------------------------------------------------------------------


def _make_indicators(
    *,
    macd_trend: str = "bullish",
    price_vs_sma_20: str = "above",
    price_vs_sma_50: str = "above",
    price_vs_sma_200: str = "above",
    atr_direction: str = "stable",
    volatility_regime: str = "NORMAL",
) -> TechnicalIndicators:
    """Helper to build TechnicalIndicators with specified signals; other fields are realistic defaults."""
    macd = MACDResult(
        macd_line=150.0,
        signal_line=120.0,
        histogram=30.0,
        trend=macd_trend,
        histogram_5d=[10.0, 15.0, 20.0, 25.0, 30.0],
        histogram_trend="growing",
        crossover_type="bullish",
        crossover_days_ago=5,
    )
    return TechnicalIndicators(
        sma_20=68000.0,
        sma_50=65000.0,
        sma_200=55000.0,
        ema_20=68500.0,
        ema_50=65500.0,
        ema_200=55500.0,
        price_vs_sma_20=price_vs_sma_20,
        price_vs_sma_50=price_vs_sma_50,
        price_vs_sma_200=price_vs_sma_200,
        sma_20_slope="rising (+0.15%/d)",
        sma_50_slope="rising (+0.08%/d)",
        ma_cross_signal=None,
        ma_cross_days_ago=None,
        rsi_14=58.0,
        rsi_interpretation="bullish",
        rsi_5d_ago=55.0,
        rsi_direction="rising",
        rsi_divergence=None,
        macd_result=macd,
        atr_14=1500.0,
        atr_pct=2.1,
        atr_direction=atr_direction,
        volatility_regime=volatility_regime,
        trend_summary="BULLISH (3/5 signals aligned)",
    )


@pytest.fixture
def bullish_indicators() -> TechnicalIndicators:
    """3/3 bullish + ATR stable → ENTER."""
    return _make_indicators()


@pytest.fixture
def bearish_indicators() -> TechnicalIndicators:
    """3/3 bearish + ATR stable → ENTER (bearish direction)."""
    return _make_indicators(
        macd_trend="bearish",
        price_vs_sma_20="below",
        price_vs_sma_50="below",
        price_vs_sma_200="below",
    )


@pytest.fixture
def neutral_indicators() -> TechnicalIndicators:
    """0/3 alignment → NO."""
    return _make_indicators(
        macd_trend="neutral",
        price_vs_sma_20="above",
        price_vs_sma_50="below",
        price_vs_sma_200="below",
    )


@pytest.fixture
def partial_indicators() -> TechnicalIndicators:
    """2/3 bullish + ATR falling → WAIT."""
    return _make_indicators(
        price_vs_sma_200="below",
        atr_direction="falling",
    )


@pytest.fixture
def sample_technical_indicators() -> TechnicalIndicators:
    """Fully populated TechnicalIndicators with known values."""
    return _make_indicators()


# ---------------------------------------------------------------------------
# Alpha Vantage mock response
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def alpha_vantage_response() -> dict:
    """Dict matching the real DIGITAL_CURRENCY_DAILY response schema (~30 dates).

    Key format matches actual API: "4. close" (not "4a. close (USD)").
    """
    base = pd.bdate_range(end="2026-05-01", periods=30)
    ts = {}
    price = 67000.0
    for d in base:
        key = d.strftime("%Y-%m-%d")
        ts[key] = {
            "1. open": f"{price - 200:.8f}",
            "2. high": f"{price + 500:.8f}",
            "3. low": f"{price - 500:.8f}",
            "4. close": f"{price:.8f}",
            "5. volume": "109.68348435",
        }
        price += 150.0
    return {
        "Meta Data": {
            "1. Information": "Daily Prices (Digital Currency)",
            "2. Digital Currency Code": "BTC",
            "3. Digital Currency Name": "Bitcoin",
            "4. Market Code": "USD",
        },
        "Time Series (Digital Currency Daily)": ts,
    }


# ---------------------------------------------------------------------------
# JSON report fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sample_json_report() -> dict:
    """JSON report matching the real pipeline output schema (based on reports/2026-05-10_BTC.json)."""
    return {
        "symbol": "BTC",
        "date": "2026-05-10",
        "sentiment": {
            "label": "Positive",
            "summary": "Sustained ETF inflows and strong institutional buy-side absorption signal bullish conviction.",
        },
        "events": [
            {
                "description": "Spot BTC ETF inflows exceed $500M in a single week",
                "source": "coindesk.com",
                "date": "2026-05-05",
                "tier": 1,
                "corroborated": True,
            },
        ],
        "metrics": {
            "rsi": 63.8,
            "macd_position": "above_signal",
            "price_vs_sma20": "above",
            "price_vs_sma50": "above",
            "price_vs_sma200": "below",
            "atr_direction": "contracting",
            "volatility_regime": "LOW",
            "volume_vs_30d_avg": None,
        },
        "horizons": {
            "short_term": {
                "signal_state": "RSI 63.8, MACD above signal, histogram shrinking",
                "direction": "Bullish with fading momentum",
                "reasoning": "MACD histogram declining, price flattening near resistance",
            },
            "medium_term": {
                "signal_state": "Price above SMA20 and SMA50, below SMA200",
                "direction": "Constructive recovery structure",
                "reasoning": "Rising MA slopes indicate orderly recovery",
            },
            "long_term": {
                "signal_state": "Price below SMA200, 120d return negative",
                "direction": "Bearish until SMA200 reclaimed",
                "reasoning": "Broader downtrend technically intact",
            },
        },
        "macro": {
            "fed_funds_rate": "3.50%-3.75%",
            "next_fomc_date": "2026-06-16",
            "fomc_days_away": 37,
            "expected_action": "hold",
            "backdrop_summary": "Mixed macro with hawkish tilt. CPI above target, DXY elevated.",
        },
        "risk_factors": [],
        "prediction": {
            "pre_decision": "WAIT",
            "final_decision": "WAIT",
            "override_applied": False,
            "override_reason": None,
        },
        "trading": {
            "direction": "long",
            "leverage_min": 2,
            "leverage_max": 5,
            "entry_notes": None,
            "wait_conditions": "Wait for sustained daily close above SMA(200) with ATR expanding.",
        },
        "watch_next": {
            "macro_calendar": ["Next FOMC meeting 2026-06-16"],
            "macro_triggers": ["DXY movement above 118.4"],
            "etf_flows": ["Monitor weekly spot BTC ETF flow data"],
            "on_chain": ["Futures funding rates currently neutral"],
            "technical_triggers": ["Daily close above SMA(200) at $82,700"],
        },
        "sources": [
            {"domain": "coindesk.com", "tier": 1},
            {"domain": "cointelegraph.com", "tier": 1},
        ],
    }


# ---------------------------------------------------------------------------
# Macro fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fred_sp500_observations() -> list[dict]:
    """FRED SP500 series — 10 entries desc, includes YTD baseline (Jan entry)."""
    return [
        {"date": "2026-05-08", "value": "5500.00"},
        {"date": "2026-05-07", "value": "5480.00"},
        {"date": "2026-05-06", "value": "5470.00"},
        {"date": "2026-05-05", "value": "5460.00"},
        {"date": "2026-05-02", "value": "5440.00"},
        {"date": "2026-05-01", "value": "5420.00"},
        {"date": "2026-04-30", "value": "5400.00"},
        {"date": "2026-04-29", "value": "5380.00"},
        {"date": "2026-04-28", "value": "5360.00"},
        {"date": "2026-01-02", "value": "5200.00"},
    ]


@pytest.fixture(scope="session")
def fred_vix_observations() -> list[dict]:
    """FRED VIXCLS series — single entry (limit=1)."""
    return [{"date": "2026-05-08", "value": "14.50"}]


@pytest.fixture(scope="session")
def fred_dgs10_observations() -> list[dict]:
    """FRED DGS10 (10Y yield) — 5 entries for 1-week change calc."""
    return [
        {"date": "2026-05-08", "value": "4.25"},
        {"date": "2026-05-07", "value": "4.27"},
        {"date": "2026-05-06", "value": "4.28"},
        {"date": "2026-05-05", "value": "4.29"},
        {"date": "2026-05-02", "value": "4.30"},
    ]


@pytest.fixture(scope="session")
def fred_dxy_observations() -> list[dict]:
    """FRED DTWEXBGS (USD Index) — 5 weekly entries for 1-month change calc."""
    return [
        {"date": "2026-05-08", "value": "104.20"},
        {"date": "2026-05-01", "value": "104.50"},
        {"date": "2026-04-24", "value": "104.80"},
        {"date": "2026-04-17", "value": "105.00"},
        {"date": "2026-04-10", "value": "105.04"},
    ]


@pytest.fixture(scope="session")
def fred_cpi_observations() -> list[dict]:
    """FRED CPIAUCSL — 13 monthly entries for YoY calc (index 0 vs index 12)."""
    return [
        {"date": "2026-04-01", "value": "332.407"},
        {"date": "2026-03-01", "value": "331.50"},
        {"date": "2026-02-01", "value": "330.80"},
        {"date": "2026-01-01", "value": "330.00"},
        {"date": "2025-12-01", "value": "329.20"},
        {"date": "2025-11-01", "value": "328.50"},
        {"date": "2025-10-01", "value": "327.80"},
        {"date": "2025-09-01", "value": "327.00"},
        {"date": "2025-08-01", "value": "326.30"},
        {"date": "2025-07-01", "value": "325.60"},
        {"date": "2025-06-01", "value": "324.90"},
        {"date": "2025-05-01", "value": "324.20"},
        {"date": "2025-04-01", "value": "319.785"},
    ]


@pytest.fixture(scope="session")
def fred_fedfunds_observations() -> list[dict]:
    """FRED FEDFUNDS — single entry (limit=1)."""
    return [{"date": "2026-04-01", "value": "3.64"}]


@pytest.fixture
def sample_macro_snapshot() -> MacroSnapshot:
    """Values consistent with fred_*_observations fixtures above."""
    return MacroSnapshot(
        sp500=5500.0,
        sp500_chg_1w_pct=1.47,
        sp500_chg_ytd_pct=5.77,
        vix=14.5,
        yield_10y=4.25,
        yield_10y_chg_1w_bp=-5.0,
        dxy=104.2,
        dxy_chg_1m_pct=-0.8,
        cpi_yoy_pct=3.95,
        cpi_date="2026-04",
        fed_funds_rate=3.64,
    )
