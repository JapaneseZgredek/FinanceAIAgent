"""
Configuration module for Finance AI Agent.

All settings are loaded from environment variables with validation.
Copy .env.example to .env and fill in your values.
"""

import os
import logging
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
        logger.warning(f"Invalid integer for {key}='{raw}', using default={default}")
        return default

    if min_val is not None and value < min_val:
        logger.warning(f"{key}={value} is below minimum {min_val}, using {min_val}")
        return min_val
    if max_val is not None and value > max_val:
        logger.warning(f"{key}={value} is above maximum {max_val}, using {max_val}")
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
        logger.warning(f"Invalid number for {key}='{raw}', using default={default}")
        return default

    if min_val is not None and value < min_val:
        logger.warning(f"{key}={value} is below minimum {min_val}, using {min_val}")
        return min_val
    if max_val is not None and value > max_val:
        logger.warning(f"{key}={value} is above maximum {max_val}, using {max_val}")
        return max_val

    return value


def _get_bool(key: str, default: bool) -> bool:
    """Get a boolean from environment."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


# =============================================================================
# API Keys (required)
# =============================================================================

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# =============================================================================
# Claude CLI Configuration
# =============================================================================

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")

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


def validate_env() -> None:
    """
    Validate required configuration on startup.

    Raises:
        ConfigurationError: If ALPHAVANTAGE_API_KEY is missing.
    """
    from app.utils.errors import ConfigurationError

    if not ALPHAVANTAGE_API_KEY:
        raise ConfigurationError(
            message="Missing required API key: ALPHAVANTAGE_API_KEY",
            hint="Get a free key from https://www.alphavantage.co/support/#api-key\n"
                 "Then add it to your .env file.",
        )

    logger.debug("Configuration validated successfully")


def print_config_summary() -> None:
    """Print a summary of current configuration (for debugging)."""
    print("\nConfiguration Summary:")
    print(f"  CLAUDE_MODEL: {CLAUDE_MODEL}")
    print(f"  NEWS_DAYS_BACK: {NEWS_DAYS_BACK}")
    print(f"  PRICE_WINDOW_DAYS: {PRICE_WINDOW_DAYS}")
    print(f"  PRICE_LAST_N: {PRICE_LAST_N}")
    print(f"  CACHE_TTL_HOURS: {CACHE_TTL_HOURS}")
    print(f"  CLAUDE_NEWS_CACHE_TTL_MINUTES: {CLAUDE_NEWS_CACHE_TTL_MINUTES}")
    print()
