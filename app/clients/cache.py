"""
File-based cache with TTL support for API responses.

Supports different TTL configurations for various use cases:
- Alpha Vantage: 1-6 hours (price data doesn't change frequently)
- Exa News: 10-30 minutes (news updates more frequently)
"""

import json
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """File-based cache with TTL support for API responses."""

    def __init__(self, cache_dir: str | Path, ttl_seconds: float):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory to store cache files.
            ttl_seconds: Time-to-live in seconds for cache entries.
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self._ensure_cache_dir()

    @classmethod
    def with_ttl_hours(cls, cache_dir: str | Path, ttl_hours: float) -> "CacheManager":
        """Create a CacheManager with TTL specified in hours."""
        return cls(cache_dir, ttl_hours * 3600)

    @classmethod
    def with_ttl_minutes(cls, cache_dir: str | Path, ttl_minutes: float) -> "CacheManager":
        """Create a CacheManager with TTL specified in minutes."""
        return cls(cache_dir, ttl_minutes * 60)

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, identifier: str) -> str:
        """Generate a safe filename from the identifier."""
        return hashlib.md5(identifier.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get full path for a cache file."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, identifier: str) -> tuple[Any | None, bool]:
        """
        Retrieve cached data if available.

        Args:
            identifier: Unique identifier for the cached item.

        Returns:
            tuple: (data, is_fresh) where data is None if not cached,
                   and is_fresh indicates if TTL has not expired.
        """
        cache_key = self._get_cache_key(identifier)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            logger.debug("Cache miss (no file): %s", identifier)
            return None, False

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)

            cached_time = cached.get("timestamp", 0)
            age_seconds = time.time() - cached_time
            is_fresh = age_seconds < self.ttl_seconds

            if is_fresh:
                logger.debug(
                    "Cache hit for %s (age: %.0fs, TTL: %.0fs)",
                    identifier, age_seconds, self.ttl_seconds,
                )
            else:
                logger.info(
                    "Cache stale for %s (age: %.0fs, TTL: %.0fs)",
                    identifier, age_seconds, self.ttl_seconds,
                )

            return cached.get("data"), is_fresh

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to read cache for %s: %s", identifier, e)
            return None, False

    def set(self, identifier: str, data: Any) -> None:
        """
        Store data in cache with current timestamp.

        Args:
            identifier: Unique identifier for the cached item.
            data: Data to cache (must be JSON-serializable).
        """
        cache_key = self._get_cache_key(identifier)
        cache_path = self._get_cache_path(cache_key)

        cache_entry = {
            "timestamp": time.time(),
            "identifier": identifier,
            "data": data,
        }

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_entry, f)
            logger.debug("Cached response for %s", identifier)
        except IOError as e:
            logger.warning("Failed to write cache for %s: %s", identifier, e)

    def invalidate(self, identifier: str) -> bool:
        """
        Remove a specific cache entry.

        Args:
            identifier: Unique identifier for the cached item.

        Returns:
            True if cache was removed, False if it didn't exist.
        """
        cache_key = self._get_cache_key(identifier)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()
            logger.debug("Invalidated cache for %s", identifier)
            return True
        return False

    def clear_all(self) -> int:
        """
        Remove all cache entries.

        Returns:
            Number of cache files removed.
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info("Cleared %d cache entries", count)
        return count
