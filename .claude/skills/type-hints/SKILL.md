---
name: type-hints
description: Audit and fix type annotations in a Python file. Finds missing annotations, outdated Union/Optional syntax, imprecise Any types, and inconsistencies between hints and actual usage. Use when refactoring or working on code that lacks proper annotations.
argument-hint: [path/to/file.py]
allowed-tools: Read, Edit, Bash(.venv/bin/python3 *)
---

# Type Hints Audit & Fix

Audit and fix type annotations in `$ARGUMENTS`.

## Steps

1. Read the full file
2. For each function/method, check annotations against the checklist below
3. Apply fixes directly — don't just report, edit the file
4. Run a syntax check after editing

## Annotation Checklist

### Syntax — Python 3.10+ style (this project requires 3.12+)

| Old (avoid) | New (use) |
|-------------|-----------|
| `Optional[X]` | `X \| None` |
| `Union[X, Y]` | `X \| Y` |
| `List[X]` | `list[X]` |
| `Dict[K, V]` | `dict[K, V]` |
| `Tuple[X, Y]` | `tuple[X, Y]` |
| `Type[X]` | `type[X]` |
| `from __future__ import annotations` | Not needed in 3.12+ |

### Precision — no lazy `Any`

| Imprecise | Better |
|-----------|--------|
| `Any` | Specific type or `TypeVar` |
| `dict` | `dict[str, float]` |
| `list` | `list[str]` |
| `tuple` | `tuple[float, str]` |
| `object` | Actual class |

### pandas / numpy — project-specific

```python
# Always use these, not generic 'object' or 'Any'
import pandas as pd
import numpy as np

pd.Series          # price series, RSI values, ATR series
pd.DataFrame       # must have 'price' column + datetime index
np.ndarray         # raw arrays (rare in this project)
```

### Return types

```python
# Every function needs -> return_type, including None-returning functions
def setup() -> None: ...
def get_price() -> float: ...
def maybe_get() -> str | None: ...

# Tuples: be explicit about the structure
def get_stats() -> tuple[float, str]: ...     # not tuple[Any, ...]
```

### TypeAlias — for complex repeated types

```python
from typing import TypeAlias

# If the same complex type appears 3+ times, define an alias
PriceSeries: TypeAlias = pd.Series
VolatilityRegime: TypeAlias = Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
```

### Literals — for constrained values

```python
from typing import Literal

# Use Literal for string parameters that only accept specific values
def classify(regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]) -> str: ...
direction: Literal["rising", "falling", "flat"]
```

## After Editing

Run syntax check:
```bash
.venv/bin/python3 -c "import ast; ast.parse(open('$ARGUMENTS').read()); print('Syntax OK')"
```

Run import check (catches undefined types):
```bash
.venv/bin/python3 -c "import app.utils.indicators" 2>&1 || true
```

## What NOT to Change

- Don't add `from __future__ import annotations` — not needed in Python 3.12+
- Don't add `mypy` as a dependency — only use if already in requirements.txt
- Don't annotate local variables unless the type is non-obvious from context
- Don't change logic — only annotations and `TypeAlias` definitions
