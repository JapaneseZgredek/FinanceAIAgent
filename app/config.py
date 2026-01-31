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

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# =============================================================================
# LLM Configuration
# =============================================================================

# Model name (change in .env without touching code)
GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")

# =============================================================================
# News Settings (with validation)
# =============================================================================

NEWS_DAYS_BACK = _get_int("NEWS_DAYS_BACK", default=7, min_val=1, max_val=30)
NEWS_LIMIT = _get_int("NEWS_LIMIT", default=3, min_val=1, max_val=10)
NEWS_MAX_SUMMARY_CHARS = _get_int("NEWS_MAX_SUMMARY_CHARS", default=280, min_val=50, max_val=1000)

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
EXA_CACHE_TTL_MINUTES = _get_float("EXA_CACHE_TTL_MINUTES", default=20.0, min_val=5.0, max_val=60.0)

# =============================================================================
# Domain Filtering
# =============================================================================

USE_INCLUDE_DOMAINS = _get_bool("USE_INCLUDE_DOMAINS", default=False)

BAD_DOMAINS = [
    "wikipedia.org",
    "bitcoin.org",
    "coinmarketcap.com",
    "coingecko.com",
    "investopedia.com",
    "britannica.com",
    "dictionary.com",
    "medium.com",
]

GOOD_NEWS_DOMAINS = [
    "reuters.com",
    "coindesk.com",
    "cointelegraph.com",
    "theblock.co",
    "decrypt.co",
]


def validate_env() -> None:
    """
    Validate all required configuration on startup.
    
    Checks:
    - Required API keys are present
    - GROQ_MODEL format is valid
    - Prints warnings for suboptimal settings
    
    Raises:
        ConfigurationError: If required configuration is missing or invalid
    """
    from app.utils.errors import ConfigurationError
    
    errors = []
    warnings = []
    
    # --- Check required API keys ---
    api_keys = {
        "GROQ_API_KEY": (GROQ_API_KEY, "Get from https://console.groq.com/keys"),
        "EXA_API_KEY": (EXA_API_KEY, "Get from https://exa.ai/"),
        "ALPHAVANTAGE_API_KEY": (ALPHAVANTAGE_API_KEY, "Get from https://www.alphavantage.co/support/#api-key"),
    }
    
    missing_keys = []
    for key, (value, url) in api_keys.items():
        if not value:
            missing_keys.append(f"  • {key} - {url}")
    
    if missing_keys:
        errors.append(
            "Missing required API keys:\n" + "\n".join(missing_keys)
        )
    
    # --- Validate GROQ_MODEL format ---
    if GROQ_MODEL:
        if not GROQ_MODEL.startswith("groq/"):
            warnings.append(
                f"GROQ_MODEL='{GROQ_MODEL}' should start with 'groq/' "
                f"(e.g., groq/llama-3.3-70b-versatile)"
            )
        
        # Check for known deprecated models
        deprecated_models = ["llama-3.1-70b-versatile", "llama-3.1-8b-instant"]
        for deprecated in deprecated_models:
            if deprecated in GROQ_MODEL:
                warnings.append(
                    f"GROQ_MODEL contains deprecated model '{deprecated}'. "
                    f"Consider using 'groq/llama-3.3-70b-versatile' instead."
                )
    
    # --- Print warnings ---
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")
    
    # --- Raise error if critical issues ---
    if errors:
        raise ConfigurationError(
            message="Configuration validation failed",
            hint="Fix the following issues:\n" + "\n".join(errors) + 
                 "\n\nCopy .env.example to .env and fill in your values.",
        )
    
    # --- Log successful validation ---
    logger.debug("Configuration validated successfully")


def print_config_summary() -> None:
    """Print a summary of current configuration (for debugging)."""
    print("\n📋 Configuration Summary:")
    print(f"  GROQ_MODEL: {GROQ_MODEL}")
    print(f"  NEWS_DAYS_BACK: {NEWS_DAYS_BACK}")
    print(f"  NEWS_LIMIT: {NEWS_LIMIT}")
    print(f"  PRICE_WINDOW_DAYS: {PRICE_WINDOW_DAYS}")
    print(f"  CACHE_TTL_HOURS: {CACHE_TTL_HOURS}")
    print(f"  EXA_CACHE_TTL_MINUTES: {EXA_CACHE_TTL_MINUTES}")
    print()
