"""
Retry utilities with exponential backoff for API calls.

This module provides a decorator that automatically retries failed function calls
with increasing delays between attempts. This is essential for handling transient
network errors and API rate limits gracefully.

KEY CONCEPTS:
-------------
1. Exponential Backoff: Each retry waits longer than the previous one.
   Example: 1s -> 2s -> 4s -> 8s (doubles each time)

2. Jitter: Random variation in delay to prevent "thundering herd" problem
   where many clients retry at exactly the same time.

3. Transient Errors: Temporary failures that may succeed on retry
   (network timeouts, temporary server errors, rate limits).
"""

import logging
import random
import time
from functools import wraps
from typing import Callable, Type

logger = logging.getLogger(__name__)

# Default transient exceptions that should trigger retry.
# These are typically temporary network/connection issues.
TRANSIENT_EXCEPTIONS: tuple[Type[Exception], ...] = (
    ConnectionError,  # Network connection failed
    TimeoutError,     # Request took too long
    OSError,          # Low-level I/O errors (includes network issues)
)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] | None = None,
):
    """
    Decorator that retries a function with exponential backoff.

    HOW IT WORKS:
    -------------
    1. Call the decorated function
    2. If it succeeds, return the result immediately
    3. If it fails with a retryable exception:
       a. Calculate wait time using exponential backoff
       b. Add random jitter to spread out retries
       c. Wait, then retry
    4. After max_retries failures, raise the last exception

    EXPONENTIAL BACKOFF FORMULA:
    ----------------------------
    delay = min(base_delay * (exponential_base ^ attempt), max_delay)

    With base_delay=1.0 and exponential_base=2.0:
    - Attempt 0 fails: wait 1.0 * (2^0) = 1.0 seconds
    - Attempt 1 fails: wait 1.0 * (2^1) = 2.0 seconds
    - Attempt 2 fails: wait 1.0 * (2^2) = 4.0 seconds
    - Attempt 3 fails: wait 1.0 * (2^3) = 8.0 seconds
    - ... capped at max_delay

    JITTER EXPLANATION:
    -------------------
    Without jitter: If 100 clients fail at the same time, they all retry
    at exactly the same moments, potentially overloading the server again.

    With jitter (±25%): Each client waits a slightly different time,
    spreading the load across the retry window.
    - delay = delay * (0.75 + random(0, 0.5))
    - Example: 4.0s becomes random value between 3.0s and 5.0s

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
                     Total attempts = max_retries + 1 (initial + retries)
        base_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
                   Prevents extremely long waits for high retry counts
        exponential_base: Multiplier for each subsequent delay (default: 2.0)
                          Higher = faster growth, lower = slower growth
        jitter: Add random variation to delay (default: True)
                Highly recommended for distributed systems
        retryable_exceptions: Tuple of exception types that should trigger retry
                              Non-matching exceptions are raised immediately

    Returns:
        A decorator function that wraps the target function with retry logic

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            return requests.get(url).json()

        # This will:
        # 1. Try to fetch data
        # 2. On ConnectionError/Timeout: wait ~1s, retry
        # 3. On second failure: wait ~2s, retry
        # 4. On third failure: wait ~4s, retry
        # 5. On fourth failure: raise the exception
    """
    # Use default transient exceptions if none specified
    if retryable_exceptions is None:
        retryable_exceptions = TRANSIENT_EXCEPTIONS

    # This is the actual decorator that receives the function
    def decorator(func: Callable):
        # @wraps preserves the original function's name and docstring
        # Without it, func.__name__ would be "wrapper" instead of original name
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Track the last exception for re-raising after all retries fail
            last_exception = None

            # Loop through all attempts (initial attempt + retries)
            # range(max_retries + 1) gives us [0, 1, 2, 3] for max_retries=3
            for attempt in range(max_retries + 1):
                try:
                    # Attempt to call the original function
                    # If successful, return immediately - no retry needed
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    # Caught a retryable exception - decide whether to retry or give up
                    last_exception = e

                    # Check if we've exhausted all retries
                    if attempt == max_retries:
                        # No more retries left - log error and raise
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    # --- CALCULATE DELAY WITH EXPONENTIAL BACKOFF ---
                    # Formula: base_delay * (exponential_base ^ attempt)
                    # Example with base=1.0, exp_base=2.0:
                    #   attempt 0: 1.0 * (2^0) = 1.0s
                    #   attempt 1: 1.0 * (2^1) = 2.0s
                    #   attempt 2: 1.0 * (2^2) = 4.0s
                    # min() caps the delay at max_delay to prevent excessive waits
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)

                    # --- ADD JITTER TO PREVENT THUNDERING HERD ---
                    # Multiply delay by random factor between 0.75 and 1.25
                    # This spreads out retry attempts from multiple clients
                    # random.random() returns float in [0.0, 1.0)
                    # So: 0.75 + (0.0 to 0.5) = 0.75 to 1.25
                    if jitter:
                        jitter_factor = 0.75 + random.random() * 0.5
                        delay = delay * jitter_factor

                    # Log the retry attempt for debugging/monitoring
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    # Wait before next retry
                    time.sleep(delay)

            # This code should never be reached because:
            # - Success: returns from try block
            # - All retries failed: raises from the if attempt == max_retries block
            # But just in case, raise the last exception
            if last_exception:
                raise last_exception

        # Return the wrapped function
        return wrapper

    # Return the decorator
    return decorator


def is_retryable_http_status(status_code: int) -> bool:
    """
    Check if an HTTP status code indicates a retryable error.

    Retryable status codes:
    - 429: Too Many Requests (rate limited) - retry after backing off
    - 500: Internal Server Error - server might recover
    - 502: Bad Gateway - upstream server issue, might be temporary
    - 503: Service Unavailable - server overloaded, might recover
    - 504: Gateway Timeout - upstream timeout, might succeed on retry

    NOT retryable:
    - 4xx (except 429): Client errors - request is wrong, retry won't help
    - 501: Not Implemented - server doesn't support this, retry won't help

    Args:
        status_code: HTTP response status code

    Returns:
        True if the request should be retried, False otherwise
    """
    return status_code == 429 or (status_code >= 500 and status_code != 501)


class RetryableError(Exception):
    """
    Custom exception to signal that an operation should be retried.

    Use this when you want to manually trigger a retry from within
    a function, even for conditions that aren't standard exceptions.

    Example:
        @retry_with_backoff(retryable_exceptions=(RetryableError,))
        def fetch_with_validation():
            response = requests.get(url)
            if response.json().get("status") == "processing":
                raise RetryableError("Still processing, retry later")
            return response.json()
    """
    pass
