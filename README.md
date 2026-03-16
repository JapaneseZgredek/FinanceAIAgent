# Finance AI Agent

A Python-based cryptocurrency market analysis system that generates structured reports by combining:
- **recent news** (Claude's built-in WebSearch + WebFetch),
- **historical price data** (Alpha Vantage API),
- **LLM-based analysis** via Claude Code CLI (`claude --print` subprocesses).

> This project is **not** financial advice.

---

## What's implemented

### 1) Modular async architecture
Code is split into clear layers:

- **clients**: API integrations (Alpha Vantage + async Claude CLI wrapper)
- **tools**: Local data preparation (price stats + technical indicators)
- **prompts**: Prompt builders for each pipeline step
- **runner**: Async orchestrator — Steps 1 and 2 run concurrently via `asyncio.gather`
- **utils**: Retry, error handling, technical indicators

Project structure:

```
Finance_AI_Agent/
│
├── main.py                         # 🚀 Entry point - run this to start
├── requirements.txt                # Dependencies (pip install -r ...)
├── requirements.lock.txt           # Locked versions for reproducibility
├── .env.example                    # Template for environment variables
├── README.md                       # This file
│
├── docs/                           # 📚 Documentation
│   ├── TECHNICAL_ANALYSIS.md       #    └── Technical indicators guide (SMA, RSI, MACD...)
│   └── ROADMAP.md                  #    └── Prioritized feature roadmap
│
├── .cache/                         # 📦 Local cache (auto-created, gitignored)
│   ├── alpha_vantage/              #    └── Cached price data (TTL: 1-6h)
│   └── claude_news/                #    └── Cached news results (TTL: 30min)
│
└── app/                            # 📁 Main application package
    ├── __init__.py
    ├── config.py                   # ⚙️  Configuration loader + validation
    ├── claude_runner.py            # 🎯 Async pipeline orchestrator (3 Claude CLI calls)
    ├── prompts.py                  # 📝 Prompt builders for each pipeline step
    │
    ├── clients/                    # 🌐 External API clients
    │   ├── cache.py                #    └── Generic file-based cache (TTL support)
    │   ├── alpha_vantage_client.py #    └── Price data API (with caching + retry)
    │   └── claude_client.py        #    └── Async Claude CLI subprocess wrapper
    │
    ├── tools/                      # 🔧 Data preparation
    │   └── price_tools.py          #    └── Price stats + technical indicators
    │
    └── utils/                      # 🛠️  Shared utilities
        ├── __init__.py
        ├── retry.py                #    └── Exponential backoff decorator
        ├── errors.py               #    └── Custom exceptions + user-friendly messages
        └── indicators.py           #    └── Technical indicators (SMA, EMA, RSI, MACD, ATR)
```

**Data flow:**
```
User Input (BTC) → main.py → asyncio.run(claude_runner.run())
                                     │
                     Step 0: Alpha Vantage + local indicators
                             (asyncio.to_thread, no LLM)
                                     │
                    ┌────────────────┴─────────────────┐
                    ▼  asyncio.gather (concurrent)      ▼
             Step 1: Claude CLI                 Step 2: Claude CLI
             WebSearch + WebFetch               price analysis
             (news search)                      (no web access)
                    │                                   │
                    └────────────────┬──────────────────┘
                                     ▼
                             Step 3: Claude CLI
                             final report synthesis
                             (rendered in chosen language)
                                     │
                                     ▼
                            Final Report (stdout)
```


### 2) News retrieval focused on "recent market events"
The news pipeline filters signal from noise using a three-tier source ranking system:

- **Tier 1 (high trust)** — `coindesk.com`, `cointelegraph.com`, `cryptoslate.com`, `insights.glassnode.com`. Claude searches these first using the `site:` operator.
- **Tier 2 (supplementary)** — `decrypt.co`, `coinmarketcap.com`, `beincrypto.com`, `ambcrypto.com`, `finance.yahoo.com`. Only consulted when Tier 1 yields fewer than 3 events; every Tier 2 claim must be cross-checked against a Tier 1 source before inclusion.
- **Blocked** — a hardcoded list of domains that publish AI-generated price-prediction spam (`changelly.com`, `coincodex.com`, `digitalcoinprice.com`, and others). Results from these are discarded immediately regardless of headline.

The prompt also enforces four mandatory verification checks: article freshness (must be within the configured news window), domain credibility match, concrete catalyst specificity, and multi-source corroboration (single-source claims are marked as unconfirmed).

All source lists live as Python constants (`_NEWS_SOURCES_TIER1/2/BLOCKED`) in `app/claude_runner.py` — adding or removing a domain requires a one-line change that propagates to the prompt automatically.

### 3) Price analysis with technical indicators
Instead of sending long raw time series to the model, the price tool returns a comprehensive technical analysis:

**Basic Statistics:**
- Window change (%)
- High/Low range
- Volatility (daily std of returns)
- 7d/30d momentum

**Moving Averages:**
- SMA (20, 50, 200) — Simple Moving Averages
- EMA (20, 50, 200) — Exponential Moving Averages
- Price position vs MAs (above/below)

**Momentum Indicators:**
- RSI (14) — Relative Strength Index with interpretation (overbought/oversold/neutral)
- MACD — Moving Average Convergence Divergence (line, signal, histogram, trend)

**Volatility Analysis:**
- ATR (14) — Average True Range (approximated from close prices)
- ATR% — Normalized volatility as percentage of price
- Volatility regime classification (LOW / NORMAL / HIGH / EXTREME)

**Trend Summary:**
Automated assessment combining all signals into BULLISH / BEARISH / NEUTRAL with explanation.

This prevents "prompt bloat" while providing rich technical context for the LLM.

> 📖 **Deep dive:** See [docs/TECHNICAL_ANALYSIS.md](docs/TECHNICAL_ANALYSIS.md) for detailed formulas, calculations, and interpretation guide.

### 4) Async Claude CLI pipeline (3 steps, 2 concurrent)
Three `claude --print` subprocess calls — Steps 1 and 2 run concurrently:
1. **News search** (WebSearch + WebFetch enabled) ┐ concurrent via
2. **Price analysis** (no web access)             ┘ `asyncio.gather`
3. **Final report** — synthesises both, rendered in the chosen language

`ClaudeClient.run()` uses `asyncio.create_subprocess_exec` — the event loop stays
unblocked during subprocess execution, enabling concurrency and FastAPI compatibility.

---

## Requirements

- Recommended Python: **3.12** (`asyncio.to_thread` requires 3.9+)
- API keys:
  - Alpha Vantage
- Claude Code CLI installed and authenticated (`claude` in PATH)

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
Create **.env** in the repository root (copy from `.env.example`):

```
ALPHAVANTAGE_API_KEY=your_key
CLAUDE_MODEL=claude-opus-4-6
DEFAULT_LANGUAGE=Polish
NEWS_DAYS_BACK=7
PRICE_WINDOW_DAYS=120
CACHE_TTL_HOURS=4
DEBUG=false
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

### 1) `claude` command not found
Install Claude Code CLI:
```bash
npm install -g @anthropic-ai/claude-code
```
Then authenticate: `claude login`

### 2) Alpha Vantage rate limit
Alpha Vantage may return a rate-limit message. The app caches responses (TTL 4h)
and falls back to stale cache on failure. Reduce `CACHE_TTL_HOURS` if needed.

### 3) Claude CLI timeout
Increase timeout in `app/claude_runner.py` → `_CLAUDE_TIMEOUT` (default: 180s).

---

## Security

Never commit `.env`.

If secrets were pushed to a remote repository at any point, assume they may be compromised.

---

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full prioritized roadmap.

---

## Disclaimer

This software is for educational purposes only and does not constitute financial advice.
