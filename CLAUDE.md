# CLAUDE.md

## Project Overview

Finance AI Agent is a Python-based cryptocurrency market analysis system that generates intelligent reports by combining recent market news (via Claude's built-in WebSearch), historical price data (Alpha Vantage API), and LLM-based analysis (Claude Code CLI subprocesses). It analyzes any cryptocurrency symbol (e.g., BTC, ETH, SOL) and produces structured market reports with news sentiment, technical analysis, and price predictions.

**This is not financial advice.**

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.12+ |
| LLM / Orchestration | Claude Code CLI (`claude --print` subprocesses) |
| News Search | Claude built-in `WebSearch` + `WebFetch` tools |
| Price API | Alpha Vantage (DIGITAL_CURRENCY_DAILY) |
| Data Processing | pandas (>=2.0.0), numpy |
| HTTP | requests (>=2.31.0) |
| Configuration | python-dotenv (>=1.0.0), `.env` file |

## Project Architecture

```
Finance_AI_Agent/
├── main.py                        # Entry point - interactive CLI
├── requirements.txt               # Core dependencies
├── requirements.lock.txt          # Pinned versions
├── .env.example                   # Configuration template
│
├── app/                           # Main application package
│   ├── config.py                  # Configuration loader + validation
│   ├── claude_runner.py           # Pipeline orchestrator (3 Claude CLI subprocess calls)
│   │
│   ├── clients/                   # External API integrations
│   │   ├── cache.py               # Generic TTL-aware file-based cache
│   │   └── alpha_vantage_client.py  # Crypto price API client
│   │
│   ├── tools/                     # Data preparation tools
│   │   └── price_tools.py         # Price stats, technical indicators, trend summary
│   │
│   └── utils/                     # Shared utilities
│       ├── retry.py               # Exponential backoff decorator with jitter
│       ├── errors.py              # Custom exceptions + user-friendly error handler
│       └── indicators.py          # Technical indicators (SMA, EMA, RSI, MACD, ATR)
│
├── docs/                          # Documentation
│   ├── TECHNICAL_ANALYSIS.md      # Guide on technical indicators
│   └── ROADMAP.md                 # Prioritized feature roadmap
│
└── .cache/                        # Auto-created local cache (git-ignored)
    ├── alpha_vantage/             # Price data cache (TTL: 1-6h)
    └── claude_news/               # News results cache (TTL: 30min)
```

### Execution Flow

```
python3 main.py → User enters symbol → claude_runner.run(symbol)
  → Step 0: Alpha Vantage fetch + indicators computed locally (no LLM)
  → Step 1: claude --print --allowedTools WebSearch,WebFetch  (news search)
  → Step 2: claude --print  (price analysis, no web access)
  → Step 3: claude --print  (final report synthesis, no web access)
```

### Pipeline Architecture

Three sequential `claude --print` subprocess calls:
1. **News search** — WebSearch + WebFetch enabled; fetches and summarizes recent market-moving events
2. **Price analysis** — No web access; interprets pre-computed technical indicators from Alpha Vantage
3. **Final report** — No web access; synthesizes news and price analysis into a structured report

Step 0 (price data + indicators) runs locally in Python before any Claude call — no LLM involved.

## Code Style & Conventions

- **Functions/variables**: `snake_case` (e.g., `get_daily_prices`, `_run_claude`)
- **Classes**: `PascalCase` (e.g., `AlphaVantageClient`, `CacheManager`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `_CLAUDE_TIMEOUT`, `CACHE_DIR`)
- **Private/internal**: Prefixed with `_` (e.g., `_get_news_analysis`, `_fetch_from_api`)
- **Type hints**: Full annotations throughout, modern `|` union syntax (Python 3.10+)
- **Dataclasses**: Used for structured data (e.g., `MACDResult`)
- **Docstrings**: Google-style with `Args:`, `Returns:`, `Example:`, `Raises:` sections
- **Error handling**: Custom exception hierarchy (`FinanceAgentError` base), pattern-based error classification, graceful fallbacks (stale cache on API failure)
- **One primary class/function per file** in most modules
- **Decorators**: `@retry_with_backoff`, `@dataclass`

## Useful Commands

```bash
# Run the agent (interactive - prompts for crypto symbol)
python3 main.py

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install exact pinned versions
pip install -r requirements.lock.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in API keys.

### Required API Keys

| Key | Source |
|---|---|
| `ALPHAVANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key |

Claude Code CLI must also be installed and authenticated (`claude` in PATH).

### Key Settings (all optional, have defaults)

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_MODEL` | `claude-opus-4-6` | Claude model used for all subprocess calls |
| `DEFAULT_LANGUAGE` | `Polish` | Default report output language (CLI fallback only — frontends pass it per-request) |
| `NEWS_DAYS_BACK` | `7` | News search window (1-30 days) |
| `PRICE_WINDOW_DAYS` | `120` | Historical price window (7-365 days) |
| `PRICE_LAST_N` | `10` | Last N price rows passed to Claude (1-30) |
| `CACHE_TTL_HOURS` | `4` | Alpha Vantage cache TTL (0.5-24h) |
| `CLAUDE_NEWS_CACHE_TTL_MINUTES` | `30` | News cache TTL (5-120min) |
| `DEBUG` | `false` | Full stack traces on errors |

Config is validated at startup with type coercion and range checking. Invalid values fall back to safe defaults with warnings.

## Key Design Patterns

- **Subprocess isolation**: Each Claude call is a separate `claude --print` process. Web tools (`WebSearch`, `WebFetch`) are only granted to Step 1 — Steps 2 and 3 have no internet access.
- **Caching**: File-based JSON cache with TTL per data source. Falls back to stale cache on API failure.
- **Retry**: Exponential backoff (1s → 2s → 4s → 8s, max 30s) with ±25% jitter on Alpha Vantage calls.
- **Local pre-processing**: All technical indicators (SMA, EMA, RSI, MACD, ATR) are computed in Python before any LLM call — Claude receives a compact formatted summary, not raw time series.
- **Graceful degradation**: Network failure → cache fallback → warn and continue.

## Testing

No automated test suite yet (planned — see [docs/ROADMAP.md](docs/ROADMAP.md)). Currently tested manually by running `python3 main.py` with various symbols.

## Commit Convention

Follows conventional commits: `type(scope): description`

Examples from history:
- `feat(runner): replace CrewAI/Groq/Exa stack with Claude Code CLI pipeline`
- `feat(indicators): add technical analysis with dynamic trend signals`
- `feat(config): add strict validation with actionable hints`
- `chore(claude): add project-specific skills for Claude Code`
