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

13. ✅ **Macro context inputs**
    - FRED API integration: S&P 500, VIX, 10Y Treasury yield, Gold, USD Index (DXY), CPI YoY, Fed Funds Rate.
    - Fetched in Step 0 concurrently with price data via `asyncio.gather` + `asyncio.to_thread`.
    - Injected into Step 2 (price analysis prompt) with interpretation guidelines per indicator.
    - Step 2 outputs a `## Macro backdrop` section consumed by Step 3.
    - FOMC/Fed narrative covered by Step 1 news search (`## Fed / Macro Backdrop` section).
    - Graceful degradation: if `FRED_API_KEY` not set, pipeline runs without macro context.
    - *`app/clients/macro_client.py` — `MacroClient`, `MacroSnapshot`*
    - *`app/claude_runner.py` — `_fetch_macro_context()`, `run()`*
    - *`app/prompts.py` — `build_price_analysis_prompt()`*

14. ✅ **"Risk Factors" section in report**
    - Four categories: regulation, exchange incidents, liquidity, volatility spikes.
    - Severity medium/high only — low-severity rows omitted; fallback prose if no risks qualify.
    - Each block: bold category name + severity, one-sentence basis citing the specific
      signal (news event with source/date, or regime/ATR values), one-sentence expected
      market behavior in plain language.
    - Risk Factor overrides injected into Trading perspective: HIGH factors cap the entry
      decision one level (Yes → Wait, Wait → No), force position-size reductions, and
      append execution guidance (limit orders, wider stops, 50% size cut for counterparty risk).
    - Trading perspective restructured into two mutually exclusive paths:
      PATH A (Enter now) and PATH B (Wait/No) — eliminates the contradiction between
      "Enter: Yes" and "Entry condition" coexisting in the same output.
    - Derives entirely from existing Step 1 (news) and Step 2 (price/indicators) data —
      no new API calls, Python structures, or pipeline stages required.
    - *`app/prompts.py` — `build_final_report_prompt()`*

15. ✅ **"What to watch next" section**
    - Always-present forward-looking section after Trading Perspective.
    - Five subcategories (each omitted if no signal): Macro calendar (FOMC + News Tendency
      implicit catalysts), Macro environment triggers (VIX/DXY thresholds from Step 2 backdrop),
      ETF & institutional flows, On-chain & narrative catalysts, Technical triggers
      (key SMA level, ATR direction, MA cross / RSI divergence).
    - Derives entirely from existing Step 1 (news) and Step 2 (price) outputs — no new API calls.
    - *`app/prompts.py` — `build_final_report_prompt()`*

---

## Phase 3 — Output, Formatting & Persistence

16. ✅ **Save reports to disk**
    - Every successful run auto-saves to `reports/YYYY-MM-DD_<SYMBOL>.md`.
    - Same-day re-run for the same symbol overwrites the file (latest run wins).
    - `reports/` is git-ignored — generated output, not source artefacts.
    - *`main.py` — `_save_report()`*

17. ✅ **JSON output mode**
    - Structured output: events, sentiment, metrics, prediction, sources.
    - Enables downstream processing and dashboards.
    - `output_format: Literal["markdown", "json"] = "markdown"` added to `run()` — fully backward-compatible.
    - `build_json_report_prompt()` in `prompts.py`: same override rules as markdown (PRE-COMPUTED ENTRY SIGNAL, FOMC proximity, HIGH risk factors); output always English for machine consumption.
    - `_validate_json_output()` in `claude_runner.py`: strips accidental code fences, validates with `json.loads()`, re-serialises with `indent=2`; raises `FinanceAgentError` on invalid JSON.
    - CLI prompts for format selection; `_save_report()` writes `.json` extension when format is json.
    - JSON schema keys: `symbol`, `date`, `sentiment`, `events`, `metrics`, `horizons`, `macro`, `risk_factors`, `prediction` (with `pre_decision` + `final_decision` + `override_applied`), `trading`, `watch_next`, `sources`.
    - *`app/prompts.py` — `build_json_report_prompt()`, `app/claude_runner.py` — `_validate_json_output()`, `main.py` — `_save_report()`*

18. ✅ **HTML / PDF export**
    - Standalone `export_report()` function — decoupled from pipeline, ready for FastAPI.
    - Markdown → HTML via `python-markdown` (extensions: `tables`, `fenced_code`, `nl2br`).
    - HTML → PDF via `WeasyPrint` (lazily imported — optional heavy dep).
    - Templates in separate files: `report.html` (structure) + `report.css` (styling).
    - CSS: premium dark-navy design, custom bullet markers, gradient-free palette, Polish comments on every rule.
    - `_render_html()` uses chained `.replace()` — avoids `KeyError` from CSS curly braces.
    - Always writes `.html` first; converts to `.pdf` if requested.
    - *`app/exporters/report_exporter.py` — `export_report()`, `app/exporters/templates/`*

19. ✅ **Price charts**
    - Static PNG charts generated from the full Alpha Vantage history (4000+ days for BTC).
    - Chart 1: price + SMA20 / SMA50 / SMA200 overlay; window = `PRICE_WINDOW_DAYS` by default.
    - Chart 2: 30-day rolling volatility (daily return std × 100).
    - SMA computed on full df (correct warmup) then sliced to display window via `.loc[]`.
    - Base64-embedded in HTML/PDF export via `_charts_to_html()` in `report_exporter.py`.
    - PNG files also saved to `reports/YYYY-MM-DD_<SYMBOL>_price.png` and `..._volatility.png`.
    - Optional dep: `matplotlib>=3.8.0` — graceful fallback (`[]`) if not installed.
    - *`app/charts/chart_generator.py` — `generate_price_charts()`, `app/exporters/report_exporter.py` — `_charts_to_html()`*

20. ✅ **Report diff / comparison**
    - Deterministic field-level diff for JSON reports (Mode A) and section-level unified diff for
      markdown reports (Mode B), plus an optional LLM narrative drift step (4–7 sentences on *why*).
    - Mode A diffs: sentiment, final_decision, pre_decision, override_applied, metrics (RSI/MACD/SMA),
      horizons (short/medium/long), macro backdrop, risk_factors, events, trading, sources.
    - List items matched by semantic key function (not list position) → correctly identifies added/removed/unchanged items.
    - Auto-generates today's missing report before diffing; past dates raise a clear error.
    - Output saved as `comparison_<base>_<compare>_<SYMBOL>.md|json` in `reports/`.
    - Accessible from the main CLI menu via `[c] Compare two saved reports`.
    - *`app/comparators/report_comparator.py` — `compare_reports()`, `app/prompts.py` — `build_comparison_narrative_prompt()`*

---

## Phase 4 — CLI & Developer Experience

21. ✅ **CLI arguments + structural split**
    - Typer-based CLI: `analyze`, `compare`, `export`, `charts` subcommands.
    - Flags: `--symbol`, `--format`, `--out`, `--export`, `--news-days`, `--price-days`.
    - Interactive mode preserved in `app/interfaces/interactive.py` (Rich-enhanced).
    - Service layer extracted to `app/core/pipeline.py` (FastAPI-importable, no sys.exit).
    - `main.py` → thin dispatcher (argv > 1 → CLI, else → interactive).

22. ✅ **Makefile / task runner**
    - Targets: `help`, `install`, `install-dev`, `run`, `lint`, `format`, `report`, `compare`, `export`, `charts`, `clean`, `env-check`, `test` (placeholder).
    - Ruff replaces black + flake8 — single tool for linting and formatting.
    - Config: `ruff.toml` (line-length=120, py312, select E/F/W/I/UP).
    - Pre-commit hook updated from `black` to `ruff format`.
    - *`Makefile`, `ruff.toml`, `.claude/hooks/format-python.sh`*

23. ⬚ **Config profile system**
    - `profiles/dev.env`, `profiles/prod.env` — switch setups easily.

---

## Phase 5 — Testing & Reliability

24. ⬚ **Unit tests for core components**
    - Alpha Vantage JSON parsing, price stats, technical indicators.
    - *Target: `app/clients/`, `app/utils/indicators.py`, `app/tools/price_tools.py`*

25. ⬚ **Integration tests (mocked APIs)**
    - Mock Alpha Vantage responses end-to-end.
    - Assert report contains required sections.

26. ⬚ **Contract tests for Claude CLI output**
    - Assert that each `claude --print` step returns the expected format.
    - Retry generation if format check fails.

27. ⬚ **GitHub Actions CI**
    - Run lint (`ruff check` + `ruff format --check`) and tests (`pytest`) on every push/PR.
    - Block merges on failure.
    - *Requires unit tests (24) to exist first.*

28. ⬚ **Claude CLI rate-limit handling**
    - Detect API rate limit errors from `claude` subprocess stderr.
    - Backoff and retry, or surface a clear user-facing message.

29. ⬚ **Failure monitoring**
    - Track error frequency per provider (Alpha Vantage throttling, Claude CLI failures).

---

## Phase 6 — Deployment & Scheduling

30. ⬚ **Scheduled daily reports**
    - Cron / GitHub Actions schedule: daily BTC + ETH digest, results saved to `reports/`.

31. ⬚ **Dockerize the project**
    - `Dockerfile` with Claude CLI + Python dependencies pre-installed.

32. ⬚ **FastAPI service**
    - `POST /report { "symbol": "BTC" }` → Markdown / JSON response.
    - Async execution, cached results per symbol per hour.
    - *Async foundation already in place: `ClaudeClient` uses `asyncio.create_subprocess_exec`, all blocking I/O offloaded via `asyncio.to_thread`, `run()` is a native coroutine.*

33. ⬚ **Streaming Claude output (SSE)**
    - Progress events per pipeline step via Server-Sent Events.
    - Optional token-level streaming for Step 3 markdown output.
    - *Deferred until FastAPI (32) is in place — streaming has no consumer without a frontend.*

34. ⬚ **React frontend**
    - Choose symbol, see live report generation with progress events, browse saved reports.

35. ⬚ **Cloud deployment**
    - Targets: AWS ECS/Fargate, GCP Cloud Run, Azure App Service.

---

## Phase 7 — Advanced Agent System

36. ⬚ **Multi-symbol batch mode**
    - Analyze BTC, ETH, SOL, XRP in one run. One combined daily digest.

37. ✅ **Multi-timeframe analysis**
    - Resolved via configurable `PRICE_WINDOW_DAYS` + SMA20/50/200 overlay in every report.
    - Short (SMA20), medium (SMA50), and long (SMA200) trends are already synthesised by Step 2.

38. ⬚ **Report memory / short-term context**
    - Feed yesterday's report into today's prompt.
    - Detect narrative drift: "sentiment changed from Positive to Negative vs yesterday".

39. ✅ **Scoring-based final recommendation**
    - Implemented as `compute_pre_decision()` in `app/tools/price_tools.py`.
    - Combines MACD trend, price vs SMA20/50/200, and ATR phase into a deterministic
      `ENTER` / `WAIT` / `NO` signal before any LLM call.
    - Injected into Step 3 as a hard constraint — eliminates non-deterministic trading
      decisions across identical runs.

40. ⬚ **Human override / interactive steering**
    - `--focus "ETF narrative"`, `--ignore "exchange hacks"`.
    - Steer analysis interactively via CLI flags.

41. ✅ **"Verifier" pass**
    - Addressed via tiered source ranking (Tier 1/2/Blocked), mandatory corroboration rules
      in the Step 1 prompt, and `(unconfirmed — single source)` tagging on single-source events.
    - A full second LLM call would double cost for marginal gain — the prompt-level approach
      already catches the same failure modes.

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

---

> This is a living document — update statuses as features ship.
