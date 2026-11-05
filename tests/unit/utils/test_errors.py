"""Unit tests for app/utils/errors.py — exception hierarchy, classification, formatting."""

import logging

import pytest

from app.utils.errors import (
    ConfigurationError,
    DataNotFoundError,
    FinanceAgentError,
    InvalidAPIKeyError,
    NetworkError,
    RateLimitError,
    classify_error,
    format_error,
    handle_error,
    safe_run,
)

# ===================================================================
# Exception hierarchy
# ===================================================================


class TestExceptionHierarchy:
    @pytest.mark.parametrize(
        "cls",
        [RateLimitError, InvalidAPIKeyError, NetworkError, ConfigurationError, DataNotFoundError],
    )
    def test_subclass_of_base(self, cls):
        assert issubclass(cls, FinanceAgentError)

    def test_message_and_hint_stored(self):
        err = FinanceAgentError("something broke", hint="try again")
        assert err.message == "something broke"
        assert err.hint == "try again"

    def test_hint_defaults_to_none(self):
        err = FinanceAgentError("oops")
        assert err.hint is None

    def test_display_with_hint(self):
        err = FinanceAgentError("bad thing", hint="do this instead")
        output = err.display()
        assert "bad thing" in output
        assert "do this instead" in output

    def test_display_without_hint(self):
        err = FinanceAgentError("bad thing")
        output = err.display()
        assert "bad thing" in output
        assert "Hint" not in output

    def test_str_returns_message(self):
        err = FinanceAgentError("hello")
        assert str(err) == "hello"


# ===================================================================
# classify_error
# ===================================================================


class TestClassifyError:
    @pytest.mark.parametrize(
        "message, expected_class",
        [
            ("rate limit exceeded", RateLimitError),
            ("HTTP 429 Too Many Requests", RateLimitError),
            ("quota exceeded for today", RateLimitError),
            ("invalid api key provided", InvalidAPIKeyError),
            ("401 unauthorized", InvalidAPIKeyError),
            ("authentication failed", InvalidAPIKeyError),
            ("connection refused", NetworkError),
            ("request timeout after 30s", NetworkError),
            ("dns resolution failed", NetworkError),
            ("ssl certificate verify failed", NetworkError),
            ("model not found", ConfigurationError),
            ("claude-opus-3 has been decommissioned", ConfigurationError),
            ("invalid symbol XYZ", DataNotFoundError),
            ("no data available for FAKE", DataNotFoundError),
        ],
    )
    def test_pattern_matching(self, message, expected_class):
        result = classify_error(Exception(message))
        assert isinstance(result, expected_class)

    def test_isinstance_fallback_connection_error(self):
        """ConnectionError with non-pattern message → isinstance branch catches it."""
        result = classify_error(ConnectionError("ECONNREFUSED 127.0.0.1:443"))
        assert isinstance(result, NetworkError)

    def test_isinstance_fallback_timeout_error(self):
        """TimeoutError with non-pattern message → isinstance branch catches it."""
        result = classify_error(TimeoutError("deadline of 30.0s exceeded"))
        assert isinstance(result, NetworkError)

    def test_isinstance_fallback_os_error(self):
        """OSError subclass with non-pattern message → isinstance branch catches it."""
        result = classify_error(OSError("[Errno 61] refused"))
        assert isinstance(result, NetworkError)

    def test_keyboard_interrupt(self):
        result = classify_error(KeyboardInterrupt())
        assert isinstance(result, FinanceAgentError)
        assert "cancelled" in result.message.lower()

    def test_unknown_exception(self):
        result = classify_error(ValueError("something weird"))
        assert isinstance(result, FinanceAgentError)
        assert "Unexpected error" in result.message
        assert "ValueError" in result.message

    def test_result_has_hint(self):
        result = classify_error(Exception("rate limit hit"))
        assert result.hint is not None

    def test_status_code_word_boundary_no_false_positive(self):
        """'4015' should NOT match the '401' pattern — word boundary prevents it."""
        result = classify_error(Exception("error 4015"))
        assert not isinstance(result, InvalidAPIKeyError)

    def test_status_code_429_matches(self):
        """Actual HTTP 429 status code matches correctly."""
        result = classify_error(Exception("429 Client Error: Too Many Requests"))
        assert isinstance(result, RateLimitError)

    def test_status_code_401_matches(self):
        """Actual HTTP 401 status code matches correctly."""
        result = classify_error(Exception("401 Client Error: Unauthorized"))
        assert isinstance(result, InvalidAPIKeyError)


# ===================================================================
# format_error
# ===================================================================


class TestFormatError:
    def test_with_finance_agent_error_and_hint(self):
        err = RateLimitError("too fast", hint="slow down")
        output = format_error(err)
        assert "too fast" in output
        assert "slow down" in output

    def test_with_finance_agent_error_no_hint(self):
        err = FinanceAgentError("bare error")
        output = format_error(err)
        assert "bare error" in output
        assert "Hint" not in output

    def test_with_generic_exception(self):
        output = format_error(RuntimeError("boom"))
        assert "Unexpected error" in output
        assert "RuntimeError" in output

    def test_with_pattern_matched_exception(self):
        output = format_error(Exception("rate limit exceeded"))
        assert "rate limit" in output.lower()


# ===================================================================
# handle_error
# ===================================================================


class TestHandleError:
    def test_exits_with_code_1(self):
        with pytest.raises(SystemExit) as exc_info:
            handle_error(ValueError("test"))
        assert exc_info.value.code == 1

    def test_logs_friendly_message(self, caplog):
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            handle_error(Exception("rate limit exceeded"))
        assert "API rate limit exceeded" in caplog.text
        assert "Wait a few minutes" in caplog.text

    def test_debug_mode_logs_original_exception(self, caplog):
        with caplog.at_level(logging.DEBUG), pytest.raises(SystemExit):
            handle_error(ValueError("kaboom"), debug=True)
        assert "kaboom" in caplog.text
        assert "ValueError" in caplog.text


# ===================================================================
# safe_run
# ===================================================================


class TestSafeRun:
    def test_success(self):
        result = safe_run(lambda: 42)
        assert result == 42

    def test_finance_agent_error_exits_1(self):
        with pytest.raises(SystemExit) as exc_info:
            safe_run(lambda: (_ for _ in ()).throw(RateLimitError("too fast")))
        assert exc_info.value.code == 1

    def test_finance_agent_error_logs_display(self, caplog):
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            safe_run(lambda: (_ for _ in ()).throw(RateLimitError("too fast", hint="wait")))
        assert "too fast" in caplog.text
        assert "wait" in caplog.text

    def test_keyboard_interrupt_exits_130(self):
        def interrupted():
            raise KeyboardInterrupt()

        with pytest.raises(SystemExit) as exc_info:
            safe_run(interrupted)
        assert exc_info.value.code == 130

    def test_generic_exception_exits_1(self):
        def broken():
            raise RuntimeError("unexpected")

        with pytest.raises(SystemExit) as exc_info:
            safe_run(broken)
        assert exc_info.value.code == 1

    def test_generic_exception_logs_friendly_message(self, caplog):
        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
            safe_run(lambda: (_ for _ in ()).throw(RuntimeError("unexpected")))
        assert "Unexpected error" in caplog.text

    def test_system_exit_passes_through(self):
        with pytest.raises(SystemExit) as exc_info:
            safe_run(lambda: (_ for _ in ()).throw(SystemExit(99)))
        assert exc_info.value.code == 99

    def test_passes_args_and_kwargs(self):
        def add(a, b, extra=0):
            return a + b + extra

        result = safe_run(add, 3, 4, extra=10)
        assert result == 17
