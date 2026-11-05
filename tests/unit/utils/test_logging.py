"""Unit tests for app/utils/logging.py — idempotent logging setup."""

import logging
from unittest.mock import patch

import pytest

import app.utils.logging as log_module
from app.utils.logging import setup_logging


class TestSetupLogging:
    def setup_method(self):
        """Reset module state and root logger before each test."""
        log_module._CONFIGURED = False
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def teardown_method(self):
        """Duplicates setup_method to prevent global logging state from leaking into other test files after the last test in this class."""
        log_module._CONFIGURED = False
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def _clear_before_setup(self):
        """Clear handlers right before setup_logging call.

        pytest's logging plugin re-adds its own handler between setup_method and
        the test body.  basicConfig is a no-op when handlers already exist, so we
        must clear them again immediately before calling setup_logging.
        """
        logging.getLogger().handlers.clear()

    def test_debug_sets_debug_level(self):
        self._clear_before_setup()
        setup_logging(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_info_level_by_default(self):
        self._clear_before_setup()
        setup_logging(debug=False)
        assert logging.getLogger().level == logging.INFO

    def test_idempotent_second_call_is_noop(self):
        self._clear_before_setup()
        setup_logging(debug=False)
        assert logging.getLogger().level == logging.INFO

        setup_logging(debug=True)
        assert logging.getLogger().level == logging.INFO

    def test_idempotent_does_not_duplicate_handlers(self):
        self._clear_before_setup()
        setup_logging(debug=False)
        count = len(logging.getLogger().handlers)
        setup_logging(debug=False)
        assert len(logging.getLogger().handlers) == count

    def test_suppresses_httpx_and_httpcore(self):
        self._clear_before_setup()
        setup_logging(debug=False)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_rich_handler_used_when_available(self):
        pytest.importorskip("rich")
        self._clear_before_setup()
        setup_logging(debug=False)
        from rich.logging import RichHandler

        root_handlers = logging.getLogger().handlers
        assert any(isinstance(h, RichHandler) for h in root_handlers)

    def test_fallback_when_rich_unavailable(self):
        self._clear_before_setup()
        with patch.dict("sys.modules", {"rich": None, "rich.logging": None}):
            setup_logging(debug=False)

        root_handlers = logging.getLogger().handlers
        assert len(root_handlers) >= 1
        assert all(isinstance(h, logging.StreamHandler) for h in root_handlers)

    def test_configured_flag_set_after_call(self):
        assert log_module._CONFIGURED is False
        self._clear_before_setup()
        setup_logging(debug=False)
        assert log_module._CONFIGURED is True
