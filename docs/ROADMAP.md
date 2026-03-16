# Roadmap — Finance AI Agent

Prioritized list of improvements to grow this PoC into a production-ready system.

**Legend:** ✅ Done | 🔄 In Progress | ⬚ Planned

---

## Phase 1 — Stability & Quality

1. ✅ **Caching for Alpha Vantage**
   - File-based JSON cache with TTL (1h–6h), fallback to stale on API failure.
   - *`app/clients/cache.py` — `CacheManager`*

2. ✅ **Caching for news results**
   - Cache per symbol + hour window (TTL 20–30 min).
   - *`app/claude_runner.py` — `_NEWS_CACHE_DIR`*

3. ✅ **Retry + exponential backoff**
   - Handles transient errors for all external API calls.
   - *`app/utils/retry.py` — `@retry_with_backoff`*

4. ✅ **Error handling + user-friendly messages**
   - Custom exception hierarchy, readable output, no raw stack traces by default.
   - *`app/utils/errors.py`*

5. ✅ **Config validation on startup**
   - Range checks, type coercion, actionable hints on bad values.
   - *`app/config.py`*

6. ✅ **Structured logging**
   - Python `logging` throughout, `DEBUG=true` for full traces.
   - *Configured in `main.py`*

7. ✅ **Pre-commit hooks (Claude Code)**
   - Auto-format Python with `black`, detect `print()` anti-pattern, block dangerous bash commands.
   - *`.claude/hooks/`*

8. ✅ **Replace CrewAI / Groq / Exa with Claude Code CLI pipeline**
   - Three sequential `claude --print` subprocess calls replace the entire multi-framework stack.
   - News uses Claude's built-in `WebSearch` + `WebFetch` — no Exa API key needed.
   - `requirements.txt` reduced from ~10 deps to 4.
   - *`app/claude_runner.py`*

---

## Phase 2 — Stronger Analytics & Better Reports

9. ✅ **Technical indicators for price analysis**
   - SMA/EMA (20/50/200), RSI (14), MACD, ATR, volatility regimes.
   - *`app/utils/indicators.py`, `app/tools/price_tools.py`*

10. ✅ **Automated trend classification**
    - BULLISH / BEARISH / NEUTRAL combining all indicator signals.
    - *`price_tools.py` — `get_formatted_price_data()`*

11. ✅ **Configurable report language**
    - `language` is a runtime parameter passed through the call stack (`run()` → `_get_final_report()`).
    - Steps 1 & 2 (internal, not shown to user) stay in English for best reasoning quality.
    - Only Step 3 (the user-facing report) renders in the chosen language.
    - CLI prompts the user with a default from `DEFAULT_LANGUAGE` env var.
    - Frontends pass `language` per-request to `run()` — no server restart needed.
    - *`app/claude_runner.py`, `app/config.py`, `main.py`*

12. ✅ **News source ranking**
    - Three-tier domain classification: Tier 1 (high trust), Tier 2 (supplementary), Blocked (never use).
    - Step 1 prompt builds `site:` operator queries dynamically from Python lists; Tier 2 consulted only when Tier 1 < 3 events.
    - Mandatory verification rules injected into prompt: freshness, domain credibility, catalyst specificity, cross-source corroboration.
    - Single-source events marked `(unconfirmed — single source)` in output.
    - *`app/claude_runner.py` — `_NEWS_SOURCES_TIER1/2/BLOCKED`, `_get_news_analysis()`*

13. ⬚ **Macro context inputs**
    - Optional: DXY (USD index), S&P 500 trend, CPI / Fed announcements.
    - Let the final report include macro reasoning.

14. ⬚ **"Risk Factors" section in report**
    - Explicit risks: regulation, exchange incidents, liquidity, volatility spikes.
    - Severity: low / medium / high.

15. ⬚ **"What to watch next" section**
    - Upcoming macro events, ETF flow signals, on-chain narratives.

---

## Phase 3 — Output, Formatting & Persistence

16. ⬚ **Save reports to disk**
    - `reports/YYYY-MM-DD_<SYMBOL>.md` — clean history of runs.

17. ⬚ **JSON output mode**
    - Structured output: events, sentiment, metrics, prediction, sources.
    - Enables downstream processing and dashboards.

18. ⬚ **HTML / PDF export**
    - Render Markdown → HTML → PDF (`WeasyPrint` or similar).

19. ⬚ **Price charts**
    - Generate: 90-day price chart, volatility chart, MA overlay (matplotlib / plotly).

20. ⬚ **Report diff / comparison**
    - Compare today's report vs yesterday's saved version.
    - Highlight sentiment shifts and changed indicators.

---

## Phase 4 — CLI & Developer Experience

21. ⬚ **CLI arguments**
    - `--symbol BTC`, `--days 7`, `--format md|json`, `--out reports/`
    - Remove interactive prompt mode — make it scriptable.

22. ⬚ **Streaming Claude output**
    - Stream `claude --print` output progressively instead of waiting for the full response.
    - Better UX for long analysis steps.

23. ⬚ **Makefile / task runner**
    - `make run`, `make lint`, `make test`, `make report SYMBOL=BTC`

24. ⬚ **Config profile system**
    - `profiles/dev.env`, `profiles/prod.env` — switch setups easily.

25. ⬚ **GitHub Actions CI**
    - Run lint (`flake8`) and tests on every push/PR.
    - Block merges on failure.

---

## Phase 5 — Testing & Reliability

26. ⬚ **Unit tests for core components**
    - Alpha Vantage JSON parsing, price stats, technical indicators.
    - *Target: `app/clients/`, `app/utils/indicators.py`, `app/tools/price_tools.py`*

27. ⬚ **Integration tests (mocked APIs)**
    - Mock Alpha Vantage responses end-to-end.
    - Assert report contains required sections.

28. ⬚ **Contract tests for Claude CLI output**
    - Assert that each `claude --print` step returns the expected format.
    - Retry generation if format check fails.

29. ⬚ **Claude CLI rate-limit handling**
    - Detect API rate limit errors from `claude` subprocess stderr.
    - Backoff and retry, or surface a clear user-facing message.

30. ⬚ **Failure monitoring**
    - Track error frequency per provider (Alpha Vantage throttling, Claude CLI failures).

---

## Phase 6 — Deployment & Scheduling

31. ⬚ **Scheduled daily reports**
    - Cron / GitHub Actions schedule: daily BTC + ETH digest, results saved to `reports/`.

32. ⬚ **Dockerize the project**
    - `Dockerfile` with Claude CLI + Python dependencies pre-installed.

33. ⬚ **FastAPI service**
    - `POST /report { "symbol": "BTC" }` → Markdown / JSON response.
    - Async execution, cached results per symbol per hour.
    - *Async foundation already in place: `ClaudeClient` uses `asyncio.create_subprocess_exec`, all blocking I/O offloaded via `asyncio.to_thread`, `run()` is a native coroutine.*

34. ⬚ **Minimal frontend (Streamlit)**
    - Choose symbol, see live report generation, browse saved reports.

35. ⬚ **Cloud deployment**
    - Targets: AWS ECS/Fargate, GCP Cloud Run, Azure App Service.

---

## Phase 7 — Advanced Agent System

36. ⬚ **Multi-symbol batch mode**
    - Analyze BTC, ETH, SOL, XRP in one run. One combined daily digest.

37. ⬚ **Multi-timeframe analysis**
    - Combine 7d / 30d / 120d trends into one coherent view.

38. ⬚ **Report memory / short-term context**
    - Feed yesterday's report into today's prompt.
    - Detect narrative drift: "sentiment changed from Positive to Negative vs yesterday".

39. ⬚ **Scoring-based final recommendation**
    - Combine news sentiment + price momentum + volatility → single score.
    - Output: "Bullish 72% confidence" style signal.

40. ⬚ **Human override / interactive steering**
    - `--focus "ETF narrative"`, `--ignore "exchange hacks"`.
    - Steer analysis interactively via CLI flags.

41. ⬚ **"Verifier" pass**
    - Second Claude call that cross-checks if news claims are consistent across sources.
    - Flags low-confidence or single-source narratives.

42. ⬚ **Cost + token tracking**
    - Estimate prompt sizes, token usage, and rate-limit risk per run.
    - Print a brief cost summary after each analysis.

---

## Phase 8 — Data Engineering (Optional)

43. ⬚ **Persist raw data to SQLite / Postgres**
    - Tables: news articles, price snapshots, report history.

44. ⬚ **Alerting**
    - Notify (email / webhook) when: volatility spikes, major news appears, strong trend change.

45. ⬚ **Analytics dashboard**
    - Report history, sentiment timeline, volatility trend over time.

46. ⬚ **Event tagging**
    - Tag events: regulation / macro / exchange incident / institutional flow / on-chain.

47. ⬚ **Dataset for ML experiments**
    - Store daily news + price outcomes.
    - Later: predict trend direction with a lightweight classifier.

---

## Phase 9 — Future Ideas

48. ⬚ **On-chain data integration**
    - Whale wallet tracking, exchange inflow/outflow, miner activity.

49. ⬚ **Social sentiment**
    - X/Twitter crypto sentiment, Reddit mentions, Fear & Greed index.

50. ⬚ **Portfolio tracking mode**
    - Track multiple holdings, portfolio-level reports, risk exposure analysis.

51. ⬚ **Backtesting framework**
    - Test historical prediction accuracy.
    - Compare news sentiment vs actual price moves.

52. ⬚ **Real-time streaming mode**
    - WebSocket price feeds, live news monitoring, alert on significant changes.

---

> This is a living document — update statuses as features ship.
