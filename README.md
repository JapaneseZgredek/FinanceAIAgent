# Finance AI Agent

A modular Python project that generates a short cryptocurrency market report by combining:
- **recent news** (Exa API),
- **historical price data** (Alpha Vantage),
- **LLM-based analysis** orchestrated with **CrewAI** using **Groq** models (via LiteLLM).

> This project is **not** financial advice.

---

## What's implemented

### 1) Modular architecture
Code is split into clear layers:

- **clients**: API integrations (Exa, Alpha Vantage)
- **tools**: CrewAI tools wrapping client calls (news + price)
- **agents**: agent definitions (news analyst, price analyst, writer)
- **tasks**: task definitions and prompt formats
- **runner**: wiring everything together and executing the Crew sequentially

Typical structure:
```
Finance_AI_Agent/
├── app/
│   ├── config.py              # Configuration with validation
│   ├── crew_runner.py         # Crew orchestration
│   │
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── cache.py           # File-based caching system
│   │   ├── exa_client.py      # Exa API client (with caching)
│   │   └── alpha_vantage_client.py  # Alpha Vantage client (with caching)
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── news_tools.py      # News tool with deduplication
│   │   └── price_tools.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   └── build_agents.py
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── build_tasks.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── retry.py           # Exponential backoff retry decorator
│       └── errors.py          # User-friendly error handling
│
├── .cache/                    # Local cache directory (gitignored)
├── main.py
├── requirements.txt
├── .env.example
└── README.md
```


### 2) News retrieval focused on "recent market events"
The news pipeline is designed to avoid low-signal pages (e.g., Wikipedia, "what is Bitcoin", trackers) by using:
- a **recency window** (e.g., last 7 days),
- **excluded domains** (blacklist),
- optional **include domains** mode (whitelist for trusted publishers),
- compact summaries to reduce LLM prompt size.

### 3) Price analysis (compact, token-safe)
Instead of sending long raw time series to the model, the price tool returns a compact summary:
- window change (%),
- high/low range,
- volatility estimate,
- 7d/30d momentum,


This prevents "prompt bloat" and reduces Groq token usage.

### 4) Multi-agent sequential report generation (CrewAI)
The Crew runs sequentially:
1. **News Analyst** → extracts market-moving events and sentiment + prediction
2. **Price Analyst** → technical/statistical summary + prediction
3. **Writer** → merges both into a final report

---

## Requirements

- Recommended Python: **3.12** (best compatibility for current LLM ecosystem)
- API keys:
  - Groq
  - Exa
  - Alpha Vantage

---

## Setup

### 1) Create and activate venv
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
````

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment variables
Create **.env** in the repository root:

```
GROQ_API_KEY=your_key
EXA_API_KEY=your_key
ALPHAVANTAGE_API_KEY=your_key
LITELLM_LOG=ERROR
NEWS_LIMIT=4
NEWS_MAX_SUMMARY_CHARS=220
USE_INCLUDE_DOMAINS=true
NEWS_DAYS_BACK=7 
```

> Do not commit **.env**. Keep **.env.example** in the repo instead

## Run

From the project root:
```bash
python3 main.py
```

You will be prompted:
```text
Which cryptocurrency symbol do you want to analyze (e.g. BTC)?
```
The final report is printed to sdtout

---

## Troubleshooting

### 1) Groq token rate limit (TPM) / request too large
Reduce the prompt size via `.env`:

- decrease `NEWS_LIMIT`
- decrease `NEWS_MAX_SUMMARY_CHARS`


### 2) Alpha Vantage rate limit
Alpha Vantage may return a rate-limit message ("Note").  
The app now has caching (TTL 4h) and will use cached data when rate-limited.

---

## Security

Never commit `.env`.

If secrets were pushed to a remote repository at any point, assume they may be compromised.

---

## Roadmap

Below is a prioritized list of improvements to grow this PoC into a production-ready system.

**Legend:** ✅ Done | 🔄 In Progress | ⬚ Planned

---

### Phase 1 — Stability & Quality (high ROI, low effort)

1. ✅ **Add caching for Alpha Vantage**
   - Store responses locally (TTL 1h–6h) to avoid rate limits and speed up runs.
   - Fallback to last cached response if API throttles.
   - *Implemented: `app/clients/cache.py` + `CacheManager` class*

2. ✅ **Add caching for Exa news results**
   - Cache per `(symbol, days_back, query)` for 10–30 minutes.
   - Prevent repeated news fetching during frequent runs.
   - *Implemented: TTL 20min, with serialization/deserialization*

3. ✅ **Retry + exponential backoff for all API calls**
   - Add retry logic for Exa, Alpha Vantage, and Groq requests.
   - Handle transient errors without failing the whole run.
   - *Implemented: `app/utils/retry.py` with `@retry_with_backoff` decorator*

4. ✅ **Better error handling and user-friendly messages**
   - Provide readable error output (rate limit, invalid key, network error).
   - Avoid long stack traces for common failures.
   - *Implemented: `app/utils/errors.py` with custom exception classes*

5. ✅ **Strict validation of configuration (.env)**
   - Validate required keys and numeric settings on startup.
   - Print actionable hints if configuration is missing/wrong.
   - *Implemented: Range validation, deprecated model detection, URL hints*

6. ✅ **Improved logging**
   - Replace prints with Python `logging`.
   - Add debug logs for request timing and tool outputs.
   - Support `DEBUG=true` for full stack traces.
   - *Implemented: Configured in `main.py`, suppressed noisy loggers*

7. ✅ **Topic-based news deduplication**
   - Detect repeated articles about the same event from different sources.
   - Extract "topic fingerprint" from title/summary.
   - *Implemented: `_extract_topic_fingerprint()` in `news_tools.py`*

8. ⬚ **Prevent oversized LLM prompts automatically**
   - Enforce hard caps on:
     - number of news articles
     - summary length
     - price sample size
   - Auto-truncate long tool outputs before sending to the LLM.

---

### Phase 2 — Stronger Analytics & Better Reports

9. ⬚ **Add technical indicators for price analysis**
   - SMA/EMA (20/50/200)
   - RSI (14)
   - MACD
   - ATR / volatility regimes
   - Provide these metrics to the price analyst agent.

10. ⬚ **Add trend classification**
    - Define rules like:
      - "Bullish / bearish / sideways"
      - based on moving averages + momentum + volatility.

11. ⬚ **Improve news signal extraction**
    - Extract 3–5 "market moving events" with:
      - event summary
      - impact explanation
      - source URL
      - confidence score

12. ⬚ **News source ranking system**
    - Score domains by trust level (Reuters > random blog).
    - Prefer multi-source confirmation.
    - Drop low-quality sources automatically.

13. ⬚ **Include market context and macro drivers**
    - Add optional context inputs like:
      - USD strength (DXY)
      - S&P500 trend
      - CPI / interest rate announcements
    - Let the writer agent include macro reasoning in final report.

14. ⬚ **Add "Risk Factors" section to the report**
    - Risks: regulation, exchange incidents, liquidity, volatility spikes.
    - Explicitly list risks with severity (low/medium/high).

15. ⬚ **Add "What to watch next" section**
    - Upcoming macro events
    - ETF flow signals
    - on-chain narratives
    - exchange reserve trends

---

### Phase 3 — Output, Formatting & Persistence

16. ⬚ **Save reports to disk**
    - Write outputs into:
      - `reports/YYYY-MM-DD_<SYMBOL>.md`
    - Keep a clean history of reports.

17. ⬚ **Generate HTML version of the report**
    - Render Markdown → HTML.
    - Prepare a simple "report viewer" page.

18. ⬚ **Export to PDF**
    - Use `WeasyPrint` or similar.
    - Useful for sharing/reporting.

19. ⬚ **Add JSON output mode**
    - Make the report available in structured JSON:
      - events
      - sentiment
      - metrics
      - prediction
      - sources

20. ⬚ **Add charts and visualization outputs**
    - Generate:
      - price chart (last 90 days)
      - volatility chart
      - moving averages overlay

---

### Phase 4 — CLI & Developer Experience

21. ⬚ **Add CLI arguments**
    - Example:
      - `--symbol BTC`
      - `--days 7`
      - `--news-limit 3`
      - `--out reports/`
      - `--format md|json|pdf`

22. ⬚ **Add a config profile system**
    - Example:
      - `profiles/dev.env`
      - `profiles/prod.env`
    - Switch setups easily.

23. ⬚ **Add Makefile or task runner commands**
    - `make run`
    - `make lint`
    - `make test`

24. ⬚ **Pin a working dependency lock**
    - Keep `requirements.txt` flexible
    - Add `requirements.lock.txt` for reproducible builds

25. ⬚ **Pre-commit hooks**
    - Prevent committing `.env`
    - Run linting/tests automatically

---

### Phase 5 — Testing & Reliability

26. ⬚ **Unit tests for core components**
    - Alpha Vantage JSON parsing
    - Exa filtering and deduplication
    - price stats calculations

27. ⬚ **Integration tests (mocked external APIs)**
    - Mock Exa responses
    - Mock AlphaVantage responses
    - Confirm report pipeline output structure

28. ⬚ **Contract tests for tool outputs**
    - Ensure tools always return predictable formats
    - Avoid breaking prompts when refactoring

29. ⬚ **Add monitoring of failure modes**
    - Track error frequency per provider:
      - Exa errors
      - AlphaVantage throttling
      - Groq TPM limits

---

### Phase 6 — Deployment & Scheduling

30. ⬚ **Scheduled daily reports**
    - Run a daily report at fixed time:
      - BTC / ETH daily digest
    - Store results automatically.

31. ⬚ **Dockerize the project**
    - Create `Dockerfile`
    - Make the pipeline runnable anywhere.

32. ⬚ **Deploy as a lightweight API service**
    - FastAPI endpoint:
      - `POST /report { "symbol": "BTC" }`
    - Response formats: Markdown, JSON, HTML.

33. ⬚ **Add a minimal frontend**
    - Small UI to choose symbol and see reports
    - View latest saved reports

34. ⬚ **Deploy on cloud**
    - Example targets:
      - Azure App Service
      - AWS ECS/Fargate
      - GCP Cloud Run

---

### Phase 7 — Advanced / "Real" Agent System

35. ⬚ **Add an additional "Verifier Agent"**
    - Checks if news claims are consistent across sources.
    - Flags low-confidence or single-source narratives.

36. ⬚ **Add a "Prompt Guard / Output Validator"**
    - Validate that final output always includes:
      - events list
      - prediction
      - sources
    - Retry generation if format is incorrect.

37. ⬚ **Add memory / short-term context**
    - Compare today's report vs yesterday's.
    - Track changes in sentiment and narrative.

38. ⬚ **Add multi-symbol batch mode**
    - Analyze a list of symbols:
      - BTC, ETH, SOL, XRP, etc.
    - Produce one combined daily report.

39. ⬚ **Add multi-timeframe analysis**
    - Combine:
      - 7d trends
      - 30d trends
      - 120d trends

40. ⬚ **Add scoring-based final recommendation**
    - Combine news sentiment + price momentum + volatility into one score.
    - Output:
      - "Bullish / Neutral / Bearish" confidence score.

41. ⬚ **Add a "Human override" mode**
    - Allow user input like:
      - "focus on ETF narrative"
      - "ignore hacks and focus on macro"
    - Steer analysis interactively.

42. ⬚ **Add provider fallback logic**
    - If Groq fails, optionally fallback to another provider (if configured).
    - Keep the run successful when one provider is down.

43. ⬚ **Add cost and token tracking**
    - Track:
      - prompt size
      - estimated token usage
      - rate-limit risks
    - Print a cost summary at the end.

---

### Phase 8 — Data Engineering Extensions (optional)

44. ⬚ **Store raw data in a database**
    - SQLite/Postgres tables:
      - news articles
      - price series snapshots
      - reports history

45. ⬚ **Create a small analytics dashboard**
    - Report history
    - sentiment timeline
    - volatility trend over time

46. ⬚ **Add alerting**
    - Notify when:
      - volatility spikes
      - major news appears
      - strong trend change detected

47. ⬚ **Add event tagging**
    - Tag events as:
      - regulation
      - macro
      - exchange incidents
      - institutional flows
      - on-chain activity

48. ⬚ **Build a dataset for later ML experiments**
    - Store daily news + outcomes
    - later: predict trend direction with ML

---

### Phase 9 — Future Ideas

49. ⬚ **On-chain data integration**
    - Add whale wallet tracking
    - Exchange inflow/outflow metrics
    - Miner activity monitoring

50. ⬚ **Sentiment from social media**
    - Twitter/X crypto sentiment
    - Reddit mentions tracking
    - Fear & Greed index integration

51. ⬚ **Portfolio tracking mode**
    - Track multiple holdings
    - Generate portfolio-level reports
    - Risk exposure analysis

52. ⬚ **Backtesting framework**
    - Test historical prediction accuracy
    - Compare news sentiment vs actual price moves
    - Build confidence metrics

53. ⬚ **Real-time streaming mode**
    - WebSocket price feeds
    - Live news monitoring
    - Alert on significant changes

54. ⬚ **Multi-language support**
    - Reports in different languages
    - News from non-English sources
    - i18n for UI

---

## Disclaimer

This software is for educational purposes only and does not constitute financial advice.
