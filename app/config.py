"""
Configuration module for Finance AI Agent.

All settings are loaded from environment variables with validation.
Copy .env.example to .env and fill in your values.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# Helper functions for safe config parsing
# =============================================================================


def _get_int(key: str, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    """
    Get an integer from environment with validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        min_val: Minimum allowed value (optional)
        max_val: Maximum allowed value (optional)

    Returns:
        Validated integer value
    """
    raw = os.getenv(key)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s='%s', using default=%d", key, raw, default)
        return default

    if min_val is not None and value < min_val:
        logger.warning("%s=%d is below minimum %d, using %d", key, value, min_val, min_val)
        return min_val
    if max_val is not None and value > max_val:
        logger.warning("%s=%d is above maximum %d, using %d", key, value, max_val, max_val)
        return max_val

    return value


def _get_float(key: str, default: float, min_val: float | None = None, max_val: float | None = None) -> float:
    """
    Get a float from environment with validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        min_val: Minimum allowed value (optional)
        max_val: Maximum allowed value (optional)

    Returns:
        Validated float value
    """
    raw = os.getenv(key)
    if raw is None:
        return default

    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid number for %s='%s', using default=%g", key, raw, default)
        return default

    if min_val is not None and value < min_val:
        logger.warning("%s=%g is below minimum %g, using %g", key, value, min_val, min_val)
        return min_val
    if max_val is not None and value > max_val:
        logger.warning("%s=%g is above maximum %g, using %g", key, value, max_val, max_val)
        return max_val

    return value


def _get_bool(key: str, default: bool) -> bool:
    """Get a boolean from environment."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


# =============================================================================
# API Keys
# =============================================================================

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# Optional — enables macro context (S&P 500, VIX, 10Y yield, Gold, DXY, CPI, Fed rate).
# Free key at https://fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY = os.getenv("FRED_API_KEY")

# =============================================================================
# Claude CLI Configuration
# =============================================================================

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

# Default output language for the final report. Used only as a CLI fallback —
# frontends should pass the language explicitly via run() per request.
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "Polish")

# =============================================================================
# News Settings (with validation)
# =============================================================================

NEWS_DAYS_BACK = _get_int("NEWS_DAYS_BACK", default=7, min_val=1, max_val=30)

# =============================================================================
# Price Settings (with validation)
# =============================================================================

PRICE_WINDOW_DAYS = _get_int("PRICE_WINDOW_DAYS", default=120, min_val=7, max_val=365)
PRICE_LAST_N = _get_int("PRICE_LAST_N", default=10, min_val=1, max_val=30)

# =============================================================================
# Cache Settings (with validation)
# =============================================================================

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
CACHE_TTL_HOURS = _get_float("CACHE_TTL_HOURS", default=4.0, min_val=0.5, max_val=24.0)
CLAUDE_NEWS_CACHE_TTL_MINUTES = _get_float("CLAUDE_NEWS_CACHE_TTL_MINUTES", default=30.0, min_val=5.0, max_val=120.0)


# =============================================================================
# News Source Configuration
# These are curated domain lists — edit here to add/remove sources.
# Not controllable via env vars: source quality is a code-level decision.
# =============================================================================

# Tier 1 — high-quality, analyst-attributed content with verifiable data.
# Used first via site: operator queries; should cover the bulk of searches.
NEWS_SOURCES_TIER1: list[str] = [
    "coindesk.com",  # news + market analysis, named analysts, macro context
    "cointelegraph.com",  # ETF flows (Farside data), on-chain metrics, multi-asset
    "cryptoslate.com",  # real-time data, sentiment scoring, sector categorisation
    "insights.glassnode.com",  # on-chain analytics: SOPR, MVRV, Realized Price (BTC-focused)
]

# Tier 2 — supplementary sources; treat with moderate scepticism.
# Cross-check any claim from these against a Tier 1 source before including it.
NEWS_SOURCES_TIER2: list[str] = [
    "decrypt.co",  # fast event tracking, liquidation data (CoinGlass-sourced)
    "coinmarketcap.com",  # aggregated analyst forecasts, TVL, institutional data
    "beincrypto.com",  # daily coverage of all coins; weaker analytical depth
    "ambcrypto.com",  # often surfaces for altcoins; JS-heavy, harder to parse
    "finance.yahoo.com",  # institutional analyst reports (Standard Chartered, Bernstein)
]

# Blocked — NEVER use as a source.
# These publish AI-generated price-prediction spam with zero analytical value.
NEWS_SOURCES_BLOCKED: list[str] = [
    "changelly.com",
    "coincodex.com",
    "digitalcoinprice.com",
    "investinghaven.com",
    "nftplazas.com",
    "coindcx.com",  # /blog/price-predictions/* path specifically
    "bitcoinethereumnews.com",
    "spotedcrypto.com",
]


def validate_env() -> None:
    """
    Validate required configuration on startup and log full environment state.

    Raises:
        ConfigurationError: If ALPHAVANTAGE_API_KEY is missing.
    """
    from app.utils.errors import ConfigurationError

    if not ALPHAVANTAGE_API_KEY:
        raise ConfigurationError(
            message="Missing required API key: ALPHAVANTAGE_API_KEY",
            hint="Get a free key from https://www.alphavantage.co/support/#api-key\nThen add it to your .env file.",
        )

    # Log full configuration state at startup
    logger.info("Environment validated. Active configuration:")
    logger.info("  [API]     ALPHAVANTAGE_API_KEY: configured")
    if FRED_API_KEY:
        logger.info("  [API]     FRED_API_KEY: configured (macro context enabled)")
    else:
        logger.info("  [API]     FRED_API_KEY: not set (macro context disabled)")
    logger.info("  [LLM]     CLAUDE_MODEL: %s", CLAUDE_MODEL)
    logger.info("  [LLM]     DEFAULT_LANGUAGE: %s", DEFAULT_LANGUAGE)
    logger.info("  [NEWS]    NEWS_DAYS_BACK: %d days", NEWS_DAYS_BACK)
    logger.info("  [PRICE]   PRICE_WINDOW_DAYS: %d days | PRICE_LAST_N: %d", PRICE_WINDOW_DAYS, PRICE_LAST_N)
    logger.info(
        "  [CACHE]   CACHE_TTL_HOURS: %.1fh | NEWS_CACHE_TTL: %.0fmin", CACHE_TTL_HOURS, CLAUDE_NEWS_CACHE_TTL_MINUTES
    )


def print_config_summary() -> None:
    """Log a summary of current configuration (for debugging)."""
    logger.info("Configuration summary:")
    logger.info("  CLAUDE_MODEL: %s", CLAUDE_MODEL)
    logger.info("  NEWS_DAYS_BACK: %d", NEWS_DAYS_BACK)
    logger.info("  PRICE_WINDOW_DAYS: %d", PRICE_WINDOW_DAYS)
    logger.info("  PRICE_LAST_N: %d", PRICE_LAST_N)
    logger.info("  CACHE_TTL_HOURS: %.1f", CACHE_TTL_HOURS)
    logger.info("  CLAUDE_NEWS_CACHE_TTL_MINUTES: %.1f", CLAUDE_NEWS_CACHE_TTL_MINUTES)
    if FRED_API_KEY:
        logger.info("  FRED_API_KEY: configured")
    else:
        logger.info("  FRED_API_KEY: not set (macro context disabled)")
