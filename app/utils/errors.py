"""
User-friendly error handling for the Finance AI Agent.

This module provides:
1. Custom exception classes for different error types
2. Error handler that catches exceptions and displays readable messages
3. Avoids long stack traces for common failures
"""

import sys
import logging
from typing import NoReturn

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exception Classes
# =============================================================================

class FinanceAgentError(Exception):
    """Base exception for Finance AI Agent errors."""
    
    def __init__(self, message: str, hint: str | None = None):
        self.message = message
        self.hint = hint
        super().__init__(message)
    
    def display(self) -> str:
        """Format error for user display."""
        lines = [f"❌ Error: {self.message}"]
        if self.hint:
            lines.append(f"💡 Hint: {self.hint}")
        return "\n".join(lines)


class RateLimitError(FinanceAgentError):
    """API rate limit exceeded."""
    pass


class InvalidAPIKeyError(FinanceAgentError):
    """Invalid or missing API key."""
    pass


class NetworkError(FinanceAgentError):
    """Network connection failed."""
    pass


class ConfigurationError(FinanceAgentError):
    """Configuration or environment error."""
    pass


class DataNotFoundError(FinanceAgentError):
    """Requested data not found (e.g., invalid ticker)."""
    pass


# =============================================================================
# Error Message Mappings
# =============================================================================

# Map common exception patterns to user-friendly messages
ERROR_PATTERNS = [
    # Rate limits
    {
        "patterns": ["rate limit", "too many requests", "429", "quota exceeded"],
        "error_class": RateLimitError,
        "message": "API rate limit exceeded",
        "hint": "Wait a few minutes before trying again, or check your API plan limits.",
    },
    # Invalid API keys
    {
        "patterns": ["invalid api key", "unauthorized", "401", "authentication", "invalid_api_key"],
        "error_class": InvalidAPIKeyError,
        "message": "Invalid or missing API key",
        "hint": "Check your .env file and ensure all API keys are correct.",
    },
    # Network errors
    {
        "patterns": ["connection", "timeout", "network", "unreachable", "dns", "ssl"],
        "error_class": NetworkError,
        "message": "Network connection failed",
        "hint": "Check your internet connection and try again.",
    },
    # Model not found / deprecated
    {
        "patterns": ["model", "decommissioned", "not found", "does not exist"],
        "error_class": ConfigurationError,
        "message": "LLM model not available",
        "hint": "Update GROQ_MODEL in .env to a valid model (e.g., groq/llama-3.3-70b-versatile).",
    },
    # Invalid ticker
    {
        "patterns": ["invalid symbol", "no data", "ticker not found"],
        "error_class": DataNotFoundError,
        "message": "Cryptocurrency symbol not found",
        "hint": "Check the ticker symbol (e.g., BTC, ETH, SOL).",
    },
]


def classify_error(exception: Exception) -> FinanceAgentError:
    """
    Classify an exception into a user-friendly error type.
    
    Analyzes the exception message and type to determine the most
    appropriate user-friendly error class and message.
    """
    error_str = str(exception).lower()
    exception_type = type(exception).__name__.lower()
    
    # Check against known patterns
    for pattern_info in ERROR_PATTERNS:
        for pattern in pattern_info["patterns"]:
            if pattern in error_str or pattern in exception_type:
                return pattern_info["error_class"](
                    message=pattern_info["message"],
                    hint=pattern_info["hint"],
                )
    
    # Check for specific exception types
    if isinstance(exception, (ConnectionError, TimeoutError, OSError)):
        return NetworkError(
            message="Network connection failed",
            hint="Check your internet connection and try again.",
        )
    
    if isinstance(exception, KeyboardInterrupt):
        return FinanceAgentError(
            message="Operation cancelled by user",
            hint=None,
        )
    
    # Unknown error - wrap it
    return FinanceAgentError(
        message=f"Unexpected error: {type(exception).__name__}",
        hint="Check the logs for more details or report this issue.",
    )


def handle_error(exception: Exception, debug: bool = False) -> NoReturn:
    """
    Handle an exception with user-friendly output.
    
    Args:
        exception: The exception to handle
        debug: If True, show full stack trace (for development)
    """
    # Classify the error
    friendly_error = classify_error(exception)
    
    # Print user-friendly message
    print("\n" + "=" * 50)
    print(friendly_error.display())
    print("=" * 50 + "\n")
    
    # Log the full error for debugging (but don't show to user by default)
    logger.debug(f"Full error details: {exception}", exc_info=True)
    
    # In debug mode, also show the original error
    if debug:
        print("\n[DEBUG] Original exception:")
        print(f"  Type: {type(exception).__name__}")
        print(f"  Message: {exception}")
    
    sys.exit(1)


def safe_run(func, *args, debug: bool = False, **kwargs):
    """
    Run a function with error handling.
    
    Catches exceptions and displays user-friendly error messages
    instead of raw stack traces.
    
    Args:
        func: Function to run
        *args: Arguments to pass to function
        debug: If True, show full stack traces
        **kwargs: Keyword arguments to pass to function
    
    Returns:
        Result of func(*args, **kwargs) if successful
    """
    try:
        return func(*args, **kwargs)
    except FinanceAgentError as e:
        # Already a friendly error, just display it
        print("\n" + "=" * 50)
        print(e.display())
        print("=" * 50 + "\n")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user.")
        sys.exit(130)
    except SystemExit:
        raise  # Let SystemExit pass through
    except Exception as e:
        handle_error(e, debug=debug)
