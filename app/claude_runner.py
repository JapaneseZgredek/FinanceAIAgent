"""
Orchestrates the Finance AI Agent using Claude Code CLI subprocesses.

Replaces the CrewAI + Groq pipeline with three sequential `claude --print`
subprocess calls:
  1. News search  — Claude uses its built-in WebSearch tool
  2. Price analysis — Claude interprets pre-computed technical indicators
  3. Final report  — Claude synthesises both into a structured report

Step 0 (local, no LLM): price data fetched from Alpha Vantage and indicators
calculated in Python before any Claude call is made.
"""

import logging
import os
import subprocess
from datetime import datetime

from app.clients.alpha_vantage_client import AlphaVantageClient
from app.clients.cache import CacheManager
from app import config
from app.tools.price_tools import get_formatted_price_data
from app.utils.errors import FinanceAgentError

logger = logging.getLogger(__name__)

# Absolute path — consistent regardless of working directory
_NEWS_CACHE_DIR = os.path.join(config.CACHE_DIR, "claude_news")
_CLAUDE_TIMEOUT = 180  # seconds per subprocess call

# ---------------------------------------------------------------------------
# News source ranking — used in Step 1 prompt to guide WebSearch behaviour
# ---------------------------------------------------------------------------

# Tier 1 — high-quality, analyst-attributed content with verifiable data.
# Use site: operator first; these should cover the bulk of searches.
_NEWS_SOURCES_TIER1 = [
    "coindesk.com",          # news + market analysis, named analysts, macro context
    "cointelegraph.com",     # ETF flows (Farside data), on-chain metrics, multi-asset
    "cryptoslate.com",       # real-time data, sentiment scoring, sector categorisation
    "insights.glassnode.com",# on-chain analytics: SOPR, MVRV, Realized Price (BTC-focused)
]

# Tier 2 — useful supplementary sources; treat with moderate scepticism.
# Cross-check any claim from these against a Tier 1 source before including it.
_NEWS_SOURCES_TIER2 = [
    "decrypt.co",            # fast event tracking, liquidation data (CoinGlass-sourced)
    "coinmarketcap.com",     # aggregated analyst forecasts, TVL, institutional data
    "beincrypto.com",        # daily coverage of all coins; weaker analytical depth
    "ambcrypto.com",         # often surfaces for altcoins; JS-heavy, harder to parse
    "finance.yahoo.com",     # institutional analyst reports (Standard Chartered, Bernstein)
]

# Tier 3 — NEVER use as a source.
# These sites publish AI-generated price-prediction spam with zero analytical value.
# They contaminate search results but contain no market-moving information.
_NEWS_SOURCES_BLOCKED = [
    "changelly.com",
    "coincodex.com",
    "digitalcoinprice.com",
    "investinghaven.com",
    "nftplazas.com",
    "coindcx.com",           # /blog/price-predictions/* path specifically
    "bitcoinethereumnews.com",
    "spotedcrypto.com",
]


def run(symbol: str, language: str = "Polish") -> str:
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
        symbol: Cryptocurrency ticker (e.g., "BTC", "ETH", "SOL")
        language: Output language for the final report (e.g., "Polish",
                  "English", "Spanish"). Passed per-request so callers —
                  including a future FastAPI frontend — can set it dynamically
                  without restarting the server.

    Returns:
        Formatted market report as a string.

    Raises:
        FinanceAgentError: If any step fails and cannot be recovered.
    """
    symbol = symbol.upper().strip()
    logger.info("Starting analysis for %s (output language: %s)", symbol, language)

    config.validate_env()

    # Step 0: price data from Alpha Vantage + local indicators (no LLM)
    alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY, config.CACHE_TTL_HOURS)
    price_data = get_formatted_price_data(
        alpha_client, symbol, config.PRICE_WINDOW_DAYS, config.PRICE_LAST_N
    )

    # Step 1: news search — always English (intermediate, never shown to user)
    news_analysis = _get_news_analysis(symbol)

    # Step 2: price analysis — always English (intermediate, never shown to user)
    price_analysis = _get_price_analysis(symbol, price_data)

    # Step 3: final report — rendered in the requested language
    return _get_final_report(symbol, news_analysis, price_analysis, language)


# =============================================================================
# Internal helpers
# =============================================================================

def _run_claude(prompt: str, allowed_tools: str = "") -> str:
    """
    Run `claude --print` as a subprocess and return its stdout.

    Web tools (WebSearch, WebFetch) are only granted when explicitly requested
    via allowed_tools — steps that must not access the web pass nothing.

    Args:
        prompt: The prompt text to pass to Claude CLI.
        allowed_tools: Comma-separated tool names to enable (e.g. "WebSearch,WebFetch").
                       Empty string means no extra tools granted.

    Returns:
        Stripped stdout from the Claude CLI process.

    Raises:
        FinanceAgentError: If the process exits with a non-zero code or times out.
    """
    cmd = ["claude", "--print", "--model", config.CLAUDE_MODEL]

    # Only attach web tools for the step that actually needs them (news search).
    # Price analysis and final report explicitly forbid web access — don't grant
    # the permission even if the prompt says not to use it.
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]

    cmd += ["-p", prompt]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise FinanceAgentError(
            f"Claude CLI timed out after {_CLAUDE_TIMEOUT}s. "
            "Try again or increase timeout."
        )
    except FileNotFoundError:
        raise FinanceAgentError(
            "Claude CLI not found. Make sure `claude` is installed and in PATH. "
            "Install with: npm install -g @anthropic-ai/claude-code"
        )

    if result.returncode != 0:
        raise FinanceAgentError(
            f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}"
        )

    return result.stdout.strip()


def _get_news_analysis(symbol: str) -> str:
    """
    Fetch recent news for the symbol via Claude CLI + WebSearch. (Call 1 of 3)

    Always returns English — this output is fed into Claude in Step 3, not
    shown to the user. Keeping it in English maximises reasoning quality.
    Results are cached per symbol + hour to avoid redundant web searches.

    Args:
        symbol: Cryptocurrency ticker.

    Returns:
        Formatted string with market events, sentiment, and news forecast (English).
    """
    cache = CacheManager.with_ttl_minutes(_NEWS_CACHE_DIR, config.CLAUDE_NEWS_CACHE_TTL_MINUTES)
    cache_key = f"claude_news_{symbol}_{datetime.now().strftime('%Y-%m-%d-%H')}"

    cached, is_fresh = cache.get(cache_key)
    if is_fresh and cached:
        logger.info("News cache hit for %s", symbol)
        return cached["analysis"]

    logger.info("Fetching fresh news for %s via Claude CLI web search", symbol)
    today = datetime.now().strftime("%Y-%m-%d")

    tier1_site_query = " OR ".join(f"site:{d}" for d in _NEWS_SOURCES_TIER1)
    tier2_site_query = " OR ".join(f"site:{d}" for d in _NEWS_SOURCES_TIER2)
    blocked_domains = ", ".join(_NEWS_SOURCES_BLOCKED)

    prompt = (
        f"Today is {today}. Search the web for recent news about the {symbol} cryptocurrency "
        f"from the last {config.NEWS_DAYS_BACK} days.\n\n"

        f"=== SEARCH STRATEGY ===\n"
        f"Execute searches in this order:\n"
        f"1. Primary search (Tier 1 sources only):\n"
        f'   Query: "{symbol} cryptocurrency news" ({tier1_site_query})\n'
        f"2. Supplementary search (Tier 2 sources) ONLY if Tier 1 yields fewer than 3 relevant events:\n"
        f'   Query: "{symbol} crypto news" ({tier2_site_query})\n\n'

        f"=== SOURCE RELIABILITY RULES ===\n"
        f"TIER 1 — HIGH TRUST: {', '.join(_NEWS_SOURCES_TIER1)}\n"
        f"  These sites provide analyst-attributed content with verifiable data. Prefer these.\n\n"
        f"TIER 2 — MODERATE TRUST: {', '.join(_NEWS_SOURCES_TIER2)}\n"
        f"  Use only as supplementary. MANDATORY: cross-check any Tier 2 claim against a Tier 1 source.\n"
        f"  If a Tier 2 article cannot be corroborated, do NOT include the claim.\n\n"
        f"BLOCKED — NEVER USE: {blocked_domains}\n"
        f"  These domains publish AI-generated price-prediction content with zero analytical value.\n"
        f"  Discard any result from these domains immediately, regardless of headline.\n\n"

        f"=== CRITICAL VERIFICATION REQUIREMENTS ===\n"
        f"Before including any piece of information you MUST verify:\n"
        f"  1. FRESHNESS: Check the article publication date. Only include events from the last "
        f"{config.NEWS_DAYS_BACK} days (after {today} minus {config.NEWS_DAYS_BACK} days).\n"
        f"     Reject any article without a visible publication date.\n"
        f"  2. SOURCE CREDIBILITY: Confirm the domain matches a Tier 1 or Tier 2 entry above.\n"
        f"     Do not trust a site just because it appears in search results.\n"
        f"  3. SPECIFICITY: The event must name a concrete catalyst (a regulator, institution, "
        f"fund, or protocol). Vague headlines like 'Bitcoin may rise' are not market-moving events.\n"
        f"  4. CORROBORATION: If only one source reports an event, mark it as "
        f"'(unconfirmed — single source)' in your output.\n\n"

        f"=== FOCUS ===\n"
        f"Include ONLY market-moving events: regulatory actions, major partnerships, exchange listings, "
        f"ETF inflows/outflows, protocol upgrades, exchange hacks, macro events (Fed, CPI, tariffs).\n"
        f"Skip: educational articles, price predictions without catalysts, general explanations.\n\n"

        f"=== OUTPUT FORMAT ===\n"
        f"## Market Events\n"
        f"- [event description] (Source: domain.com, Date: YYYY-MM-DD, Tier: 1|2)\n"
        f"(3-5 bullet points only)\n\n"
        f"## Sentiment\n"
        f"Positive / Negative / Mixed — one sentence explanation.\n\n"
        f"## News Forecast\n"
        f"UP / DOWN / NEUTRAL — one sentence rationale.\n\n"
        f"Respond in English."
    )

    # WebSearch and WebFetch only for this step — the only one that needs web access
    analysis = _run_claude(prompt, allowed_tools="WebSearch,WebFetch")
    cache.set(cache_key, {"analysis": analysis})
    return analysis


def _get_price_analysis(symbol: str, price_data: str) -> str:
    """
    Technical analysis of price data via Claude CLI. (Call 2 of 3)

    Always returns English — this output is fed into Claude in Step 3, not
    shown to the user. No web access; Claude works only on the provided data.

    Args:
        symbol: Cryptocurrency ticker.
        price_data: Formatted string with prices and indicators from get_formatted_price_data().

    Returns:
        Technical analysis paragraph ending with a single forecast line (English).
    """
    logger.info("Running price analysis for %s", symbol)
    prompt = (
        f"You are a quantitative cryptocurrency analyst. "
        f"Analyze the following technical indicator data for {symbol}.\n\n"
        f"=== PRICE DATA AND INDICATORS ===\n{price_data}\n\n"
        f"Write a 1-paragraph analysis covering: trend direction, momentum (RSI, MACD), "
        f"volatility regime, and key support/resistance levels from moving averages. "
        f"End with exactly one line:\n"
        f"Forecast: UP / DOWN / NEUTRAL — [one sentence rationale]\n\n"
        f"Do NOT search the web. Use only the provided data. Respond in English."
    )
    return _run_claude(prompt)


def _get_final_report(symbol: str, news_analysis: str, price_analysis: str, language: str) -> str:
    """
    Synthesise news and price analysis into the final market report. (Call 3 of 3)

    This is the only step whose output is shown to the user, so it renders in
    the requested language. No web access — Claude combines the two provided analyses.

    Args:
        symbol: Cryptocurrency ticker.
        news_analysis: Output from _get_news_analysis() (English).
        price_analysis: Output from _get_price_analysis() (English).
        language: Output language for the report (e.g., "Polish", "English", "Spanish").

    Returns:
        Formatted market report string in the requested language.
    """
    logger.info("Generating final report for %s", symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"You are a professional cryptocurrency report writer. "
        f"Combine the two analyses below into a final, concise report for {symbol}.\n\n"
        f"=== NEWS ANALYSIS ===\n{news_analysis}\n\n"
        f"=== TECHNICAL PRICE ANALYSIS ===\n{price_analysis}\n\n"
        f"Output format (translate all section headers and labels to {language}):\n\n"
        f"## Market Report {symbol} — {today}\n\n"
        f"**Summary**\n"
        f"- (point 1: key news catalyst)\n"
        f"- (point 2: key technical signal)\n"
        f"- (point 3: combined outlook — 3 points maximum)\n\n"
        f"**Analysis**\n"
        f"(1 paragraph, 6 sentences maximum. Integrate news sentiment with technical indicators.)\n\n"
        f"**Forecast: UP / DOWN / NEUTRAL**\n"
        f"(1 sentence referencing the 2 strongest signals from both analyses.)\n\n"
        f"*This is not financial advice.*\n\n"
        f"Do NOT search the web. Use only the provided analyses. Respond in {language}."
    )
    return _run_claude(prompt)
