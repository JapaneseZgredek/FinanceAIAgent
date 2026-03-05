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
│   └── TECHNICAL_ANALYSIS.md       #    └── Technical indicators guide (SMA, RSI, MACD...)
│
├── .cache/                         # 📦 Local cache (auto-created, gitignored)
│   ├── alpha_vantage/              #    └── Cached price data (TTL: 1-6h)
│   └── exa_news/                   #    └── Cached news results (TTL: 10-30min)
│
└── app/                            # 📁 Main application package
    ├── __init__.py
    ├── config.py                   # ⚙️  Configuration loader + validation
    ├── crew_runner.py              # 🎯 CrewAI orchestration (agents + tasks)
    │
    ├── clients/                    # 🌐 External API clients
    │   ├── __init__.py
    │   ├── cache.py                #    └── Generic file-based cache (TTL support)
    │   ├── alpha_vantage_client.py #    └── Price data API (with caching + retry)
    │   └── exa_client.py           #    └── News search API (with caching + retry)
    │
    ├── tools/                      # 🔧 CrewAI tools (callable by agents)
    │   ├── __init__.py
    │   ├── news_tools.py           #    └── News fetching + deduplication + limits
    │   └── price_tools.py          #    └── Price stats + technical indicators
    │
    ├── agents/                     # 🤖 CrewAI agent definitions
    │   ├── __init__.py
    │   └── build_agents.py         #    └── News analyst + Price analyst + Writer
    │
    ├── tasks/                      # 📋 CrewAI task definitions
    │   ├── __init__.py
    │   └── build_tasks.py          #    └── Task prompts + expected outputs
    │
    └── utils/                      # 🛠️  Shared utilities
        ├── __init__.py
        ├── retry.py                #    └── Exponential backoff decorator
        ├── errors.py               #    └── Custom exceptions + user-friendly messages
        ├── prompt_limits.py        #    └── Hard caps on LLM prompt size
        └── indicators.py           #    └── Technical indicators (SMA, EMA, RSI, MACD, ATR)
```

**Data flow:**
```
User Input (BTC) → main.py → crew_runner.py
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              news_tool      price_tool      LLM (Groq)
                    │              │              │
                    ▼              ▼              │
              exa_client   alpha_vantage_client  │
                    │              │              │
                    └──────┬───────┘              │
                           ▼                      │
                    .cache/ (local)               │
                           │                      │
                           └──────────────────────┘
                                   │
                                   ▼
                          Final Report (stdout)
```


### 2) News retrieval focused on "recent market events"
The news pipeline is designed to avoid low-signal pages (e.g., Wikipedia, "what is Bitcoin", trackers) by using:
- a **recency window** (e.g., last 7 days),
- **excluded domains** (blacklist),
- optional **include domains** mode (whitelist for trusted publishers),
- compact summaries to reduce LLM prompt size.

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

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full prioritized roadmap.

---

## Disclaimer

This software is for educational purposes only and does not constitute financial advice.
