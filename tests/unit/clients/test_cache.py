"""Unit tests for app/clients/cache.py — file-based cache with TTL."""

import json
import logging
from unittest.mock import patch

from app.clients.cache import CacheManager

# ===================================================================
# Construction
# ===================================================================


class TestCacheManagerConstruction:
    def test_creates_cache_directory(self, tmp_path):
        cache_dir = tmp_path / "new_cache"
        CacheManager(cache_dir, ttl_seconds=60)
        assert cache_dir.is_dir()

    def test_with_ttl_hours(self, tmp_path):
        cm = CacheManager.with_ttl_hours(tmp_path, ttl_hours=2)
        assert cm.ttl_seconds == 7200

    def test_with_ttl_minutes(self, tmp_path):
        cm = CacheManager.with_ttl_minutes(tmp_path, ttl_minutes=30)
        assert cm.ttl_seconds == 1800


# ===================================================================
# get
# ===================================================================


class TestCacheGet:
    def test_miss_returns_none(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        data, is_fresh = cm.get("nonexistent")
        assert data is None
        assert is_fresh is False

    @patch("app.clients.cache.time.time", return_value=1000.0)
    def test_fresh_hit(self, _mock_time, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cache_key = cm._get_cache_key("test_id")
        cache_path = cm._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({"timestamp": 950.0, "data": {"price": 100}}))

        data, is_fresh = cm.get("test_id")
        assert data == {"price": 100}
        assert is_fresh is True

    @patch("app.clients.cache.time.time", return_value=2000.0)
    def test_stale_returns_data_but_not_fresh(self, _mock_time, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cache_key = cm._get_cache_key("test_id")
        cache_path = cm._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({"timestamp": 1000.0, "data": [1, 2, 3]}))

        data, is_fresh = cm.get("test_id")
        assert data == [1, 2, 3]
        assert is_fresh is False

    def test_corrupt_json_returns_none(self, tmp_path, caplog):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cache_key = cm._get_cache_key("corrupt")
        cache_path = cm._get_cache_path(cache_key)
        cache_path.write_text("not valid json {{{")

        with caplog.at_level(logging.WARNING):
            data, is_fresh = cm.get("corrupt")
        assert data is None
        assert is_fresh is False
        assert "Failed to read cache" in caplog.text

    @patch("app.clients.cache.time.time", return_value=1000.0)
    def test_missing_timestamp_treats_as_epoch_zero(self, _mock_time, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cache_key = cm._get_cache_key("no_ts")
        cache_path = cm._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({"data": "hello"}))

        data, is_fresh = cm.get("no_ts")
        assert data == "hello"
        assert is_fresh is False

    @patch("app.clients.cache.time.time", return_value=1000.0)
    def test_missing_data_key_returns_none(self, _mock_time, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cache_key = cm._get_cache_key("no_data")
        cache_path = cm._get_cache_path(cache_key)
        cache_path.write_text(json.dumps({"timestamp": 999.0}))

        data, is_fresh = cm.get("no_data")
        assert data is None
        assert is_fresh is True


# ===================================================================
# set
# ===================================================================


class TestCacheSet:
    def test_write_and_readback(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=3600)
        cm.set("mykey", {"symbol": "BTC", "price": 67000})

        data, is_fresh = cm.get("mykey")
        assert data == {"symbol": "BTC", "price": 67000}
        assert is_fresh is True

    def test_overwrite_existing(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=3600)
        cm.set("key", "old")
        cm.set("key", "new")

        data, _ = cm.get("key")
        assert data == "new"

    def test_non_serializable_logs_warning(self, tmp_path, caplog):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        with caplog.at_level(logging.WARNING):
            cm.set("bad", {"obj": object()})
        assert "Failed to serialize cache" in caplog.text
        assert list(tmp_path.glob("*.json")) == []


# ===================================================================
# invalidate
# ===================================================================


class TestCacheInvalidate:
    def test_existing_returns_true(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cm.set("to_delete", "data")
        assert cm.invalidate("to_delete") is True
        data, _ = cm.get("to_delete")
        assert data is None

    def test_missing_returns_false(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        assert cm.invalidate("never_existed") is False


# ===================================================================
# clear_all
# ===================================================================


class TestCacheClearAll:
    def test_empty_returns_zero(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        assert cm.clear_all() == 0

    def test_multiple_entries_returns_count(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        cm.set("a", 1)
        cm.set("b", 2)
        cm.set("c", 3)
        assert cm.clear_all() == 3
        assert cm.clear_all() == 0

    def test_non_json_files_untouched(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        (tmp_path / "notes.txt").write_text("keep me")
        (tmp_path / "leftover.tmp").write_text("crash artifact")
        cm.set("x", 1)
        cm.clear_all()
        assert (tmp_path / "notes.txt").exists()
        assert (tmp_path / "leftover.tmp").exists()


# ===================================================================
# _get_cache_key
# ===================================================================


class TestCacheKey:
    def test_deterministic(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        assert cm._get_cache_key("test") == cm._get_cache_key("test")

    def test_different_ids_produce_different_keys(self, tmp_path):
        cm = CacheManager(tmp_path, ttl_seconds=60)
        assert cm._get_cache_key("alpha") != cm._get_cache_key("beta")
