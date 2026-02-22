---
name: tests
description: Generate pytest unit tests for a Python function, class, or module. Creates a complete test file with fixtures, parametrize, and edge cases. Use when adding tests for new or existing code.
argument-hint: [path/to/file.py or module.function_name]
allowed-tools: Read, Glob, Grep, Write, Bash(.venv/bin/pytest *)
---

# Generate Pytest Tests

Generate a complete pytest test file for `$ARGUMENTS`.

## Steps

1. Read the target file to understand the function/class signatures and logic
2. Identify: pure functions, side-effectful functions, exceptions, edge cases
3. Check if `tests/` directory exists — create it with `__init__.py` if not
4. Write the test file at `tests/test_<module_name>.py`
5. Run the tests to verify they pass (or fail for the right reasons)

## Test File Structure

```python
"""Tests for <module_name>."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from app.<module> import <function_or_class>


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def price_series() -> pd.Series:
    """120-day synthetic BTC price series for indicator tests."""
    dates = pd.date_range("2024-01-01", periods=120, freq="D")
    prices = pd.Series(
        np.linspace(40_000, 95_000, 120) + np.random.default_rng(42).normal(0, 500, 120),
        index=dates,
    )
    return prices


@pytest.fixture
def price_df(price_series) -> pd.DataFrame:
    """DataFrame with 'price' column — standard input for indicators."""
    return pd.DataFrame({"price": price_series})


# ── Tests ─────────────────────────────────────────────────────────────────────
```

## Patterns by Function Type

### Pure functions (no I/O, no randomness)
```python
def test_sma_length_matches_input(price_series):
    result = sma(price_series, 20)
    assert len(result) == len(price_series)

def test_sma_first_n_minus_1_are_nan(price_series):
    result = sma(price_series, 20)
    assert result.iloc[:19].isna().all()
    assert not pd.isna(result.iloc[19])
```

### Parametrize for multiple inputs
```python
@pytest.mark.parametrize("period", [10, 20, 50, 200])
def test_sma_various_periods(price_series, period):
    result = sma(price_series, period)
    assert not result.dropna().empty
```

### Functions that raise custom exceptions
```python
def test_raises_rate_limit_error_on_429(mock_requests):
    mock_requests.get.side_effect = Exception("429 rate limit")
    with pytest.raises(RateLimitError):
        client.fetch("BTC")
```

### Mocking external APIs
```python
@patch("app.clients.alpha_vantage_client.requests.get")
def test_get_prices_calls_correct_endpoint(mock_get, alpha_client):
    mock_get.return_value.json.return_value = {...}
    mock_get.return_value.raise_for_status = MagicMock()
    result = alpha_client.get_daily_prices("BTC")
    mock_get.assert_called_once()
    assert "BTC" in mock_get.call_args[1]["params"]["symbol"]
```

### Dataclass validation
```python
def test_macd_result_fields(price_df):
    result = get_macd_result(price_df["price"])
    assert isinstance(result, MACDResult)
    assert result.trend in ("bullish", "bearish", "neutral", "N/A")
    assert len(result.histogram_5d) <= 5
    assert result.histogram_trend in (
        "strongly_growing", "growing", "flat",
        "shrinking", "strongly_shrinking", "insufficient_data"
    )
```

### Edge cases to always consider
- Empty Series / DataFrame with 0 rows
- Series shorter than the indicator period (e.g., RSI with < 14 bars)
- All-NaN input
- Single-element input
- Negative values (prices can't be negative, but differences can)

## Naming Convention

```python
def test_<function>_<scenario>():
    """One-line description of what this test verifies."""
```

Examples:
- `test_rsi_returns_series_of_same_length`
- `test_rsi_values_between_0_and_100`
- `test_rsi_raises_no_exception_on_short_series`
- `test_classify_volatility_returns_extreme_above_p90`

## Running Tests

```bash
.venv/bin/pytest tests/test_<module>.py -v
.venv/bin/pytest tests/ -v --tb=short        # all tests
```

## Important

- Use `np.random.default_rng(seed)` (not `np.random.seed()`) for reproducible data
- Don't test implementation details — test observable behavior
- Each test should have exactly one reason to fail
- Don't import anything the project doesn't already use
