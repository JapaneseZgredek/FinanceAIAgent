---
name: debug
description: Structured debugging for Finance AI Agent issues — API errors, unexpected output, exceptions, stale cache. Describe the problem and get a step-by-step diagnostic plan with isolation steps and a concrete fix.
argument-hint: [describe the problem or paste the error message]
allowed-tools: Read, Bash(.venv/bin/python3 *), Glob, Grep
---

# Debug: Finance AI Agent

Diagnose and fix the issue described in `$ARGUMENTS`.

## Steps

1. **Classify** the problem — which layer does it belong to? (see matrix below)
2. **Read** the relevant file(s) to understand the current implementation
3. **Isolate** with a minimal reproducer using `.venv/bin/python3 -c "..."`
4. **Identify** the root cause — don't guess, verify
5. **Fix** — propose the exact change with file + line

---

## Layer Map (where to look first)

| Symptom | Likely Layer | Files to Read |
|---------|-------------|---------------|
| `RateLimitError` / 429 | API client / retry | `app/clients/alpha_vantage_client.py`, `app/utils/retry.py` |
| `NetworkError` / connection refused | API client | `app/clients/exa_client.py`, `app/clients/alpha_vantage_client.py` |
| Stale or missing price data | Cache | `app/clients/cache.py` |
| `KeyError` / wrong price format | Alpha Vantage parser | `app/clients/alpha_vantage_client.py` |
| Empty news results | Exa client / dedup | `app/clients/exa_client.py`, `app/tools/news_tools.py` |
| Tool output too large / truncated | Prompt limits | `app/utils/prompt_limits.py` |
| Wrong indicator values | Indicators | `app/utils/indicators.py` |
| Agent loops / unexpected LLM output | Tasks / agents | `app/tasks/build_tasks.py`, `app/agents/build_agents.py` |
| Config error at startup | Config | `app/config.py` |
| `FinanceAgentError` subclass | Error hierarchy | `app/utils/errors.py` |

---

## Diagnostic Playbook

### 1. API / Network errors

```bash
# Check if Alpha Vantage key works
.venv/bin/python3 -c "
from app.config import config
from app.clients.alpha_vantage_client import AlphaVantageClient
c = AlphaVantageClient(config)
print(c.get_daily_prices('BTC'))
"

# Check if Exa key works
.venv/bin/python3 -c "
from app.config import config
from app.clients.exa_client import ExaClient
c = ExaClient(config)
print(c.search_news('Bitcoin', days_back=1, num_results=1))
"
```

### 2. Cache issues

Cache lives in `.cache/`. To inspect or clear:

```bash
# Show all cache files and their modification times
ls -la .cache/alpha_vantage/ .cache/exa_news/ 2>/dev/null || echo "No cache"

# Clear all cache (forces fresh API calls)
rm -rf .cache/

# Test cache round-trip
.venv/bin/python3 -c "
from app.clients.cache import CacheManager
cm = CacheManager('.cache/test', ttl_hours=1)
cm.set('key', {'value': 42})
print(cm.get('key'))  # Should return {'value': 42}
"
```

### 3. Indicator calculation issues

```bash
# Verify indicator output with synthetic data
.venv/bin/python3 -c "
import pandas as pd, numpy as np
from app.utils.indicators import calculate_all_indicators

prices = pd.Series(
    np.linspace(40000, 60000, 120) + np.random.default_rng(42).normal(0, 500, 120),
    index=pd.date_range('2024-01-01', periods=120, freq='D')
)
df = pd.DataFrame({'price': prices})
result = calculate_all_indicators(df)
print(result.format_for_llm())
"
```

### 4. Prompt / output size issues

```bash
# Check estimated token count for a tool output
.venv/bin/python3 -c "
from app.utils.prompt_limits import estimate_tokens
text = 'paste your tool output here'
print(f'~{estimate_tokens(text)} tokens')
"
```

### 5. Config validation

```bash
# Print effective config (shows what was loaded and any warnings)
.venv/bin/python3 -c "
from app.config import config
import json
print(json.dumps(config.__dict__, default=str, indent=2))
"
```

### 6. Full agent run with debug logging

```bash
# Enable DEBUG=true to see full stack traces
DEBUG=true .venv/bin/python3 main.py
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `RateLimitError: 429` | Alpha Vantage free tier (5 req/min) | Wait 60s, or clear cache to avoid repeated calls |
| `KeyError: 'Time Series (Digital Currency Daily)'` | API response changed format | Check `alpha_vantage_client.py` parser against actual response |
| `ValueError: not enough data` | `PRICE_WINDOW_DAYS` too small for indicator period | Increase `PRICE_WINDOW_DAYS` (min ~30 for RSI, ~60 for MACD) |
| News dedup removes all articles | Fingerprinting too aggressive | Check `_compute_topic_fingerprint` in `news_tools.py` |
| Agent doesn't call tool | Task prompt too vague | Review expected_output in `build_tasks.py` |
| `JSONDecodeError` in cache | Corrupted cache file | `rm -rf .cache/` |

---

## Execution Flow Reminder

```
main.py
  └─ crew_runner.run(symbol)
       ├─ Task 1: News Analyst
       │    └─ news_tools.py → exa_client.py → .cache/exa_news/
       ├─ Task 2: Price Analyst
       │    └─ price_tools.py → alpha_vantage_client.py → .cache/alpha_vantage/
       │                      → indicators.py (calculate_all_indicators)
       └─ Task 3: Writer (synthesizes both)
```

When isolating a bug, test the smallest unit first (client → tool → agent).
