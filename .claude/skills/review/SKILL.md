---
name: review
description: Review a Python file for compliance with project conventions — type hints, naming, docstrings, logging, error handling, complexity. Use before committing or when doing a self-review.
argument-hint: [path/to/file.py]
allowed-tools: Read, Grep
---

# Python Code Review

Review `$ARGUMENTS` against this project's conventions and Python best practices.
Report every issue found — be specific (file + line number + what to fix).

## Checklist

### 1. Type Hints
- [ ] Every function parameter has a type annotation
- [ ] Every function has a return type annotation (including `-> None`)
- [ ] Uses Python 3.10+ union syntax: `X | Y` not `Optional[X]` or `Union[X, Y]`
- [ ] No bare `Any` — use specific types or `TypeVar`
- [ ] `pd.Series` and `pd.DataFrame` used instead of generic `object`
- [ ] `Literal["A", "B"]` for constrained string values

### 2. Naming Conventions
- [ ] Functions and variables: `snake_case`
- [ ] Classes: `PascalCase`
- [ ] Module-level constants: `UPPER_SNAKE_CASE`
- [ ] Internal/private functions and methods: `_prefix`
- [ ] No single-letter names except loop counters (`i`, `j`) and math aliases (`k`, `n`)

### 3. Docstrings
- [ ] All public functions have a Google-style docstring
- [ ] `Args:`, `Returns:`, `Raises:` sections present where applicable
- [ ] One-liner in imperative mood (not "Returns X", but "Return X")
- [ ] `Example:` section with concrete values (not `# ...`)
- [ ] Private functions (`_prefix`) have at minimum a one-liner


- [ ] No bare `except:` or `except Exception:` without re-raise or specific handling
- [ ] Custom exceptions from `FinanceAgentError` hierarchy used where appropriate
- [ ] `try/except` blocks are narrow — wrap only the failing line, not a 20-line block
- [ ] Exceptions include `message` and `hint` if using `FinanceAgentError`

### 6. Code Complexity
- [ ] Functions are ≤ 50 lines (excluding docstring and blank lines)
- [ ] Nesting depth ≤ 3 levels (if → if → if is the limit)
- [ ] No function does more than one thing (single responsibility)

### 7. Python Idioms
- [ ] Uses `dataclass` for structured data instead of plain dicts or tuples
- [ ] Uses `@decorator` pattern where applicable (`@retry_with_backoff`, `@tool`)
- [ ] List/dict comprehensions preferred over explicit loops for transformations
- [ ] `pathlib.Path` not `os.path` for file operations
- [ ] f-strings for string formatting, not `.format()` or `%`

### 8. DRY & Design
- [ ] No duplicate logic — extract to a helper if the same block appears twice
- [ ] No hardcoded values that should be constants or config
- [ ] Modules stay focused — one primary class or concept per file

## Output Format

Report issues as a numbered list:

```
REVIEW: path/to/file.py
────────────────────────

CRITICAL (must fix before commit):
1. [Line 42] Missing return type annotation on `calculate_macd()`
2. [Line 67] Bare `except Exception` swallows errors silently

WARNINGS (should fix):
3. [Line 15] `Optional[str]` → use `str | None` (Python 3.10+)
4. [Line 88] Function `process_data()` is 73 lines — consider splitting

SUGGESTIONS (nice to have):
5. [Line 31] Docstring one-liner says "Returns the..." — use imperative "Return..."

✓ No issues found in: naming, error handling, DRY
```

If no issues found in a category, state that explicitly so the review feels complete.
