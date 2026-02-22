# CLAUDE.md

## Project Overview

Finance AI Agent is a Python-based cryptocurrency market analysis system that generates intelligent reports by combining recent market news (Exa API), historical price data (Alpha Vantage API), and LLM-based analysis (CrewAI with Groq). It analyzes any cryptocurrency symbol (e.g., BTC, ETH, SOL) and produces structured market reports with news sentiment, technical analysis, and price predictions.

**This is not financial advice.**

## Tech Stack

| Category | Technology |
|---|---|
| Language | Python 3.12+ |
| Agent Orchestration | CrewAI (>=0.80.0) |
| LLM Provider | Groq (`groq/llama-3.3-70b-versatile` default) via LiteLLM |
| News API | Exa (`exa-py` >=1.0.0) |
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
│   ├── crew_runner.py             # CrewAI orchestration (agents + tasks)
│   │
│   ├── clients/                   # External API integrations
│   │   ├── cache.py               # Generic TTL-aware file-based cache
│   │   ├── alpha_vantage_client.py  # Crypto price API client
│   │   └── exa_client.py         # News search API client
│   │
│   ├── tools/                     # CrewAI-callable tools
│   │   ├── news_tools.py          # News fetching, deduplication, prompt limiting
│   │   └── price_tools.py         # Price stats, technical indicators, trend summary
│   │
│   ├── agents/                    # CrewAI agent definitions
│   │   └── build_agents.py        # 3 agents: News Analyst, Price Analyst, Writer
│   │
│   ├── tasks/                     # CrewAI task definitions
│   │   └── build_tasks.py         # Task prompts + expected output formats
│   │
│   └── utils/                     # Shared utilities
│       ├── retry.py               # Exponential backoff decorator with jitter
│       ├── errors.py              # Custom exceptions + user-friendly error handler
│       ├── prompt_limits.py       # Prompt size enforcement + token estimation
│       └── indicators.py          # Technical indicators (SMA, EMA, RSI, MACD, ATR)
│
├── docs/                          # Documentation
│   └── TECHNICAL_ANALYSIS.md      # Guide on technical indicators
│
└── .cache/                        # Auto-created local cache (git-ignored)
    ├── alpha_vantage/             # Price data cache (TTL: 1-6h)
    └── exa_news/                  # News results cache (TTL: 10-30min)
```

### Execution Flow

```
python3 main.py → User enters symbol → crew_runner.run(symbol)
  → Task 1: News Analyst fetches & deduplicates news via Exa
  → Task 2: Price Analyst calculates technical indicators via Alpha Vantage
  → Task 3: Writer synthesizes both into a final report with prediction
```

### Multi-Agent Architecture

Three sequential CrewAI agents:
1. **News Analyst** - Fetches recent news, extracts sentiment (Positive/Negative/Mixed), predicts direction
2. **Price Analyst** - Technical analysis (SMA, EMA, RSI, MACD, ATR), classifies trend
3. **Writer** - Combines both analyses into a final structured report

## Code Style & Conventions

- **Functions/variables**: `snake_case` (e.g., `get_daily_prices`, `enforce_tool_output_limits`)
- **Classes**: `PascalCase` (e.g., `AlphaVantageClient`, `CacheManager`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `ABSOLUTE_MAX_NEWS_ARTICLES`)
- **Private/internal**: Prefixed with `_` (e.g., `_fetch_from_api`)
- **Type hints**: Full annotations throughout, modern `|` union syntax (Python 3.10+)
- **Dataclasses**: Used for structured data (e.g., `MACDResult`)
- **Docstrings**: Google-style with `Args:`, `Returns:`, `Example:`, `Raises:` sections
- **Error handling**: Custom exception hierarchy (`FinanceAgentError` base), pattern-based error classification, graceful fallbacks (stale cache on API failure)
- **One primary class/function per file** in most modules
- **Decorators**: Heavy use of `@tool`, `@retry_with_backoff`, `@dataclass`

## Useful Commands

```bash
# Run the agent (interactive - prompts for crypto symbol)
python3 main.py

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
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `EXA_API_KEY` | https://exa.ai/ |
| `ALPHAVANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key |

### Key Settings (all optional, have defaults)

| Variable | Default | Description |
|---|---|---|
| `GROQ_MODEL` | `groq/llama-3.3-70b-versatile` | LLM model ID |
| `NEWS_DAYS_BACK` | `7` | News search window (1-30 days) |
| `NEWS_LIMIT` | `3` | Articles to fetch (1-10) |
| `PRICE_WINDOW_DAYS` | `120` | Historical price window (7-365) |
| `CACHE_TTL_HOURS` | `4` | Alpha Vantage cache TTL (0.5-24h) |
| `EXA_CACHE_TTL_MINUTES` | `20` | News cache TTL (5-60min) |
| `DEBUG` | `false` | Full stack traces on errors |

Config is validated at startup with type coercion and range checking. Invalid values fall back to safe defaults with warnings.

## Key Design Patterns

- **Caching**: File-based JSON cache with TTL per API. Falls back to stale cache on API failure.
- **Retry**: Exponential backoff (1s → 2s → 4s → 8s, max 30s) with ±25% jitter.
- **Prompt guardrails**: Hard caps on tool output size to prevent exceeding LLM context limits (max 10 articles, max 8000 chars per tool output).
- **News deduplication**: Title normalization, topic fingerprinting (monetary amounts + event keywords), domain limiting (max 2 per domain).
- **Graceful degradation**: Network failure → cache fallback → warn and continue.

## Testing

No automated test suite yet (planned for Phase 5 of the roadmap). Currently tested manually by running `python3 main.py` with various symbols.

## Commit Convention

Follows conventional commits: `type(scope): description`

Examples from history:
- `feat(limits): add automatic prompt size limits and suppress warnings`
- `feat(config): add strict validation with actionable hints`
- `docs(readme): update roadmap with completed Phase 1 tasks`
- `chore(documentation): Update README.md`
