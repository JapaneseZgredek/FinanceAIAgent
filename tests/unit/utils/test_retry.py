"""Unit tests for app/utils/retry.py — exponential backoff decorator, retryable status codes."""

import logging
from unittest.mock import patch

import pytest

from app.utils.retry import (
    TRANSIENT_EXCEPTIONS,
    RetryableError,
    is_retryable_http_status,
    retry_with_backoff,
)

# ===================================================================
# retry_with_backoff decorator
# ===================================================================


class TestRetryWithBackoff:
    def test_success_first_try(self):
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    @patch("app.utils.retry.time.sleep")
    def test_success_after_transient_failures(self, mock_sleep, caplog):
        call_count = 0

        @retry_with_backoff(max_retries=3, jitter=False)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        with caplog.at_level(logging.WARNING):
            assert flaky() == "recovered"
        assert call_count == 3
        assert mock_sleep.call_count == 2
        assert "attempt 1/4" in caplog.text
        assert "attempt 2/4" in caplog.text
        assert "Retrying in" in caplog.text

    @patch("app.utils.retry.time.sleep")
    def test_all_retries_exhausted_raises(self, mock_sleep, caplog):
        @retry_with_backoff(max_retries=2, jitter=False)
        def always_fail():
            raise TimeoutError("still broken")

        with caplog.at_level(logging.ERROR), pytest.raises(TimeoutError, match="still broken"):
            always_fail()
        assert mock_sleep.call_count == 2
        assert "failed after 3 attempts" in caplog.text

    def test_non_retryable_exception_raises_immediately(self):
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def bad_input():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            bad_input()
        assert call_count == 1

    @patch("app.utils.retry.time.sleep")
    def test_custom_retryable_exceptions(self, mock_sleep, caplog):
        call_count = 0

        @retry_with_backoff(max_retries=2, retryable_exceptions=(ValueError,), jitter=False)
        def custom():
            nonlocal call_count
            call_count += 1
            raise ValueError("retryable here")

        with caplog.at_level(logging.WARNING), pytest.raises(ValueError):
            custom()
        assert call_count == 3
        assert "attempt 1/3" in caplog.text
        assert "attempt 2/3" in caplog.text

    def test_max_retries_zero_tries_once(self):
        call_count = 0

        @retry_with_backoff(max_retries=0)
        def once():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            once()
        assert call_count == 1

    @patch("app.utils.retry.time.sleep")
    def test_exponential_delay_growth(self, mock_sleep):
        @retry_with_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0, jitter=False)
        def always_fail():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            always_fail()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]

    @patch("app.utils.retry.time.sleep")
    def test_max_delay_caps_growth(self, mock_sleep):
        @retry_with_backoff(max_retries=4, base_delay=10.0, max_delay=25.0, exponential_base=2.0, jitter=False)
        def always_fail():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            always_fail()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [10.0, 20.0, 25.0, 25.0]

    @patch("app.utils.retry.random.random", return_value=0.5)
    @patch("app.utils.retry.time.sleep")
    def test_jitter_applies_factor(self, mock_sleep, _mock_random):
        @retry_with_backoff(max_retries=1, base_delay=4.0, jitter=True)
        def fail():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            fail()

        # jitter_factor = 0.75 + 0.5 * 0.5 = 1.0, so delay = 4.0 * 1.0 = 4.0
        assert mock_sleep.call_args_list[0].args[0] == pytest.approx(4.0)

    @patch("app.utils.retry.random.random", return_value=0.0)
    @patch("app.utils.retry.time.sleep")
    def test_jitter_minimum_factor(self, mock_sleep, _mock_random):
        @retry_with_backoff(max_retries=1, base_delay=4.0, jitter=True)
        def fail():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            fail()

        # jitter_factor = 0.75 + 0.0 * 0.5 = 0.75, so delay = 4.0 * 0.75 = 3.0
        assert mock_sleep.call_args_list[0].args[0] == pytest.approx(3.0)

    def test_wraps_preserves_function_metadata(self):
        @retry_with_backoff()
        def my_function():
            """My docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    @patch("app.utils.retry.time.sleep")
    def test_passes_args_and_kwargs(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=1, jitter=False)
        def add(a, b, extra=0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return a + b + extra

        assert add(3, 4, extra=10) == 17

    @patch("app.utils.retry.time.sleep")
    def test_retryable_error_as_custom_exception(self, mock_sleep):
        call_count = 0

        @retry_with_backoff(max_retries=1, retryable_exceptions=(RetryableError,), jitter=False)
        def processing():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RetryableError("still processing")
            return "done"

        assert processing() == "done"
        assert call_count == 2


# ===================================================================
# is_retryable_http_status
# ===================================================================


class TestIsRetryableHttpStatus:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_retryable_codes(self, status):
        assert is_retryable_http_status(status) is True

    @pytest.mark.parametrize("status", [200, 201, 301, 400, 401, 403, 404, 501])
    def test_non_retryable_codes(self, status):
        assert is_retryable_http_status(status) is False


# ===================================================================
# RetryableError
# ===================================================================


class TestRetryableError:
    def test_is_exception(self):
        assert issubclass(RetryableError, Exception)

    def test_message_stored(self):
        err = RetryableError("try again")
        assert str(err) == "try again"


# ===================================================================
# TRANSIENT_EXCEPTIONS
# ===================================================================


class TestTransientExceptions:
    def test_contains_expected_types(self):
        assert ConnectionError in TRANSIENT_EXCEPTIONS
        assert TimeoutError in TRANSIENT_EXCEPTIONS
        assert OSError in TRANSIENT_EXCEPTIONS

    def test_is_tuple(self):
        assert isinstance(TRANSIENT_EXCEPTIONS, tuple)
