---
name: docstring
description: Generate a Google-style docstring for a Python function or class following this project's conventions. Use when you've written a new function or modified an existing one that lacks a proper docstring.
argument-hint: [function_name or file:function_name]
allowed-tools: Read, Edit
---

# Generate Google-Style Docstring

Generate a complete, accurate docstring for `$ARGUMENTS` following this project's conventions.

## Steps

1. Read the target file to find the function/class signature and body
2. Understand what the code actually does — read the full implementation, not just the signature
3. Write the docstring and insert it immediately after the `def` / `class` line

## Docstring Format

```python
def example_function(param1: int, param2: str | None = None) -> dict[str, float]:
    """
    One-line summary in imperative mood, ending with a period.

    Extended description explaining WHY this function exists and any
    non-obvious design decisions. This project values explaining the
    *reasoning*, not just restating the code. If there's a dead band,
    a threshold, or an algorithmic choice — explain it here.

    Args:
        param1: Description of param1. Include units if numeric (e.g., "in days").
        param2: Description. State what None means explicitly if nullable.

    Returns:
        Description of the return value and its structure.
        For Series/DataFrame: mention the index and column names.
        For dataclasses: mention key fields.

    Raises:
        FinanceAgentError: When and why this is raised.
        ValueError: Only if the function explicitly raises it.

    Example:
        >>> result = example_function(14, "BTC")
        >>> result["value"]
        42.0
    """
```

## Rules

- **One-liner**: imperative mood ("Calculate...", "Return...", "Detect..."), not "Calculates"
- **Args**: every parameter documented, types NOT repeated (already in signature)
- **Returns**: always present for non-`None` return; describe structure, not just type
- **Raises**: only list exceptions the function *explicitly* raises or re-raises
- **Example**: concrete values, not `# ...` placeholders
- **Extended description**: skip if the one-liner is self-explanatory; add if there's a non-obvious design choice
- **Private functions** (`_` prefix): shorter docstring acceptable — one-liner + Args/Returns minimum

## Project-Specific Types to Know

| Type | Usage in this project |
|------|-----------------------|
| `pd.Series` | Price series, RSI series, MACD series — always mention index (datetime) |
| `pd.DataFrame` | Must have `'price'` column with datetime index |
| `FinanceAgentError` | Base exception — raise subclasses: `RateLimitError`, `NetworkError`, etc. |
| `MACDResult` | Dataclass: `macd_line`, `signal_line`, `histogram`, `trend`, plus dynamic fields |
| `TechnicalIndicators` | Full technical analysis dataclass — see `indicators.py` |
| `VolatilityRegime` | `Literal["LOW", "NORMAL", "HIGH", "EXTREME"]` |

After writing the docstring, verify it's syntactically correct by running:
```bash
.venv/bin/python3 -c "import ast; ast.parse(open('FILE').read()); print('OK')"
```
