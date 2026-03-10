"""
Orchestrates the Finance AI Agent using Claude Code CLI subprocesses.

Three sequential `claude --print` subprocess calls:
  1. News search  — Claude uses its built-in WebSearch tool
  2. Price analysis — Claude interprets pre-computed technical indicators
  3. Final report  — Claude synthesises both into a structured report

Step 0 (local, no LLM): price data fetched from Alpha Vantage and indicators
calculated in Python before any Claude call is made.
"""

import logging
import os
import re
from datetime import datetime

from app.clients.alpha_vantage_client import AlphaVantageClient
from app.clients.cache import CacheManager
from app.clients.claude_client import ClaudeClient
from app import config
from app.prompts import build_news_prompt, build_price_analysis_prompt, build_final_report_prompt
from app.tools.price_tools import get_formatted_price_data
from app.utils.errors import FinanceAgentError

logger = logging.getLogger(__name__)

_NEWS_CACHE_DIR = os.path.join(config.CACHE_DIR, "claude_news")
_CLAUDE_TIMEOUT = 180  # seconds per subprocess call

# Module-level cache instance — reused across calls, TTL enforced by CacheManager
_news_cache = CacheManager.with_ttl_minutes(_NEWS_CACHE_DIR, config.CLAUDE_NEWS_CACHE_TTL_MINUTES)

# Valid symbol: 1–20 uppercase alphanumeric characters (e.g. BTC, ETH, SOL, USDC)
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,20}$")


def run(
    symbol: str,
    language: str = "Polish",
    *,
    alpha_client: AlphaVantageClient | None = None,
    claude_client: ClaudeClient | None = None,
) -> str:
    """
    Run the full analysis pipeline for a cryptocurrency symbol.

    Steps:
      0. Fetch price data + calculate technical indicators locally (no LLM)
      1. News search via Claude CLI + WebSearch  (always English — internal)
      2. Technical price analysis via Claude CLI  (always English — internal)
      3. Final report via Claude CLI              (output in `language`)

    Steps 1 and 2 are intermediate data fed back into Claude — the user never
    sees them. Keeping them in English gives Claude the best reasoning quality.
    Only Step 3 (what the user actually reads) is rendered in the chosen language.

    Args:
        symbol: Cryptocurrency ticker (e.g., "BTC", "ETH", "SOL").
        language: Output language for the final report (e.g., "Polish",
                  "English", "Spanish"). Passed per-request so callers —
                  including a future FastAPI frontend — can set it dynamically
                  without restarting the server.
        alpha_client: Optional AlphaVantageClient instance. If None, a default
                      instance is created from config. Pass explicitly for testing.
        claude_client: Optional ClaudeClient instance. If None, a default
                       instance is created from config. Pass explicitly for testing.

    Returns:
        Formatted market report as a string.

    Raises:
        FinanceAgentError: If the symbol is invalid or any pipeline step fails.
    """
    symbol = symbol.upper().strip()

    if not _SYMBOL_RE.match(symbol):
        raise FinanceAgentError(
            message=f"Invalid symbol: '{symbol}'",
            hint="Use alphanumeric ticker symbols like BTC, ETH, SOL.",
        )

    if alpha_client is None:
        alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY, config.CACHE_TTL_HOURS)
    if claude_client is None:
        claude_client = ClaudeClient(model=config.CLAUDE_MODEL, timeout=_CLAUDE_TIMEOUT)

    logger.info("Starting analysis for %s (output language: %s)", symbol, language)

    # Step 0: price data from Alpha Vantage + local indicators (no LLM)
    price_data = get_formatted_price_data(
        alpha_client, symbol, config.PRICE_WINDOW_DAYS, config.PRICE_LAST_N
    )

    # Step 1: news search — always English (intermediate, never shown to user)
    news_analysis = _get_news_analysis(symbol, claude_client)

    # Step 2: price analysis — always English (intermediate, never shown to user)
    price_analysis = _get_price_analysis(symbol, price_data, claude_client)

    # Step 3: final report — rendered in the requested language
    return _get_final_report(symbol, news_analysis, price_analysis, language, claude_client)


# =============================================================================
# Internal helpers
# =============================================================================

def _get_news_analysis(symbol: str, claude_client: ClaudeClient) -> str:
    """
    Fetch recent news for the symbol via Claude CLI + WebSearch. (Call 1 of 3)

    Always returns English — this output is fed into Claude in Step 3, not
    shown to the user. Keeping it in English maximises reasoning quality.
    Results are cached per symbol with TTL managed by CacheManager.

    Args:
        symbol: Cryptocurrency ticker.
        claude_client: ClaudeClient instance to use for the subprocess call.

    Returns:
        Formatted string with market events, sentiment, and news tendency (English).
    """
    cache_key = f"claude_news_{symbol}"
    cached, is_fresh = _news_cache.get(cache_key)
    if is_fresh and cached:
        logger.info("News cache hit for %s", symbol)
        return cached["analysis"]

    logger.info("Fetching fresh news for %s via Claude CLI web search", symbol)
    today = datetime.now().strftime("%Y-%m-%d")

    prompt = build_news_prompt(
        symbol=symbol,
        today=today,
        news_days_back=config.NEWS_DAYS_BACK,
        tier1_sources=config.NEWS_SOURCES_TIER1,
        tier2_sources=config.NEWS_SOURCES_TIER2,
        blocked_sources=config.NEWS_SOURCES_BLOCKED,
    )

    # WebSearch and WebFetch only for this step — the only one that needs web access
    analysis = claude_client.run(prompt, allowed_tools="WebSearch,WebFetch")
    _news_cache.set(cache_key, {"analysis": analysis})
    return analysis


def _get_price_analysis(symbol: str, price_data: str, claude_client: ClaudeClient) -> str:
    """
    Technical analysis of price data via Claude CLI. (Call 2 of 3)

    Always returns English — this output is fed into Claude in Step 3, not
    shown to the user. No web access; Claude works only on the provided data.

    Args:
        symbol: Cryptocurrency ticker.
        price_data: Formatted string with prices and indicators from get_formatted_price_data().
        claude_client: ClaudeClient instance to use for the subprocess call.

    Returns:
        Structured signal report grouped by time horizon (English).
    """
    logger.info("Running price analysis for %s", symbol)
    prompt = build_price_analysis_prompt(symbol=symbol, price_data=price_data)
    return claude_client.run(prompt)


def _get_final_report(
    symbol: str,
    news_analysis: str,
    price_analysis: str,
    language: str,
    claude_client: ClaudeClient,
) -> str:
    """
    Synthesise news and price analysis into the final market report. (Call 3 of 3)

    This is the only step whose output is shown to the user, so it renders in
    the requested language. No web access — Claude combines the two provided analyses.

    Args:
        symbol: Cryptocurrency ticker.
        news_analysis: Output from _get_news_analysis() (English).
        price_analysis: Output from _get_price_analysis() (English).
        language: Output language for the report (e.g., "Polish", "English", "Spanish").
        claude_client: ClaudeClient instance to use for the subprocess call.

    Returns:
        Formatted market report string in the requested language.
    """
    logger.info("Generating final report for %s", symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = build_final_report_prompt(
        symbol=symbol,
        news_analysis=news_analysis,
        price_analysis=price_analysis,
        language=language,
        today=today,
    )
    return claude_client.run(prompt)
