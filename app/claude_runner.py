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


def run(symbol: str) -> str:
    """
    Run the full analysis pipeline for a cryptocurrency symbol.

    Steps:
      0. Fetch price data + calculate technical indicators locally (no LLM)
      1. News search via Claude CLI + WebSearch
      2. Technical price analysis via Claude CLI (no web access)
      3. Final report via Claude CLI (no web access)

    Args:
        symbol: Cryptocurrency ticker (e.g., "BTC", "ETH", "SOL")

    Returns:
        Formatted market report as a string.

    Raises:
        FinanceAgentError: If any step fails and cannot be recovered.
    """
    symbol = symbol.upper().strip()
    logger.info("Starting analysis for %s", symbol)

    config.validate_env()

    # Step 0: price data from Alpha Vantage + local indicators (no LLM)
    alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY, config.CACHE_TTL_HOURS)
    price_data = get_formatted_price_data(
        alpha_client, symbol, config.PRICE_WINDOW_DAYS, config.PRICE_LAST_N
    )

    # Step 1: news search via Claude CLI + built-in WebSearch (cached)
    news_analysis = _get_news_analysis(symbol)

    # Step 2: technical price analysis via Claude CLI (pure reasoning, no web)
    price_analysis = _get_price_analysis(symbol, price_data)

    # Step 3: final report via Claude CLI (synthesises news + price analysis)
    return _get_final_report(symbol, news_analysis, price_analysis)


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
    Pobiera aktualne newsy dla symbolu przez Claude CLI z WebSearch. (Wywołanie 1 z 3)

    Wyniki są cachowane per symbol + godzina, żeby uniknąć zbędnych wyszukiwań.

    Args:
        symbol: Symbol kryptowaluty.

    Returns:
        Sformatowany string z analizą newsów po polsku.
    """
    cache = CacheManager.with_ttl_minutes(_NEWS_CACHE_DIR, config.CLAUDE_NEWS_CACHE_TTL_MINUTES)
    cache_key = f"claude_news_{symbol}_{datetime.now().strftime('%Y-%m-%d-%H')}"

    cached, is_fresh = cache.get(cache_key)
    if is_fresh and cached:
        logger.info("News cache hit for %s", symbol)
        return cached["analysis"]

    logger.info("Fetching fresh news for %s via Claude CLI web search", symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"Przeszukaj internet w poszukiwaniu wiadomości o kryptowalucie {symbol} z ostatnich {config.NEWS_DAYS_BACK} dni. "
        f"Skup się WYŁĄCZNIE na wydarzeniach wpływających na rynek: działania regulacyjne, duże partnerstwa, listingi na giełdach, "
        f"napływy/odpływy ETF, włamania na giełdy, zdarzenia makro (Fed, CPI) wpływające na ceny kryptowalut. "
        f"Pomiń: artykuły edukacyjne, prognozy cenowe bez katalizatorów, ogólne wyjaśnienia.\n\n"
        f"Zwróć dokładnie w tym formacie:\n"
        f"## Wydarzenia Rynkowe\n"
        f"- [opis wydarzenia] (Źródło: domena.com, Data: {today})\n"
        f"(tylko 3-5 punktów)\n\n"
        f"## Sentyment\n"
        f"Pozytywny / Negatywny / Mieszany — jedno zdanie wyjaśnienia.\n\n"
        f"## Prognoza Newsów\n"
        f"WZROST / SPADEK / NEUTRALNIE — jedno zdanie uzasadnienia.\n\n"
        f"Odpowiedz w języku polskim."
    )

    # WebSearch i WebFetch tylko dla tego kroku — tylko on potrzebuje dostępu do internetu
    analysis = _run_claude(prompt, allowed_tools="WebSearch,WebFetch")
    cache.set(cache_key, {"analysis": analysis})
    return analysis


def _get_price_analysis(symbol: str, price_data: str) -> str:
    """
    Analiza techniczna danych cenowych przez Claude CLI. (Wywołanie 2 z 3)

    Brak dostępu do internetu — Claude operuje wyłącznie na dostarczonych danych wskaźników.

    Args:
        symbol: Symbol kryptowaluty.
        price_data: Sformatowany string z cenami i wskaźnikami z get_formatted_price_data().

    Returns:
        Akapit analizy technicznej kończący się linią
        "Prognoza: WZROST / SPADEK / NEUTRALNIE — [uzasadnienie]".
    """
    logger.info("Running price analysis for %s", symbol)
    prompt = (
        f"Jesteś ilościowym analitykiem kryptowalut. "
        f"Przeanalizuj poniższe dane wskaźników technicznych dla {symbol}.\n\n"
        f"=== DANE CENOWE I WSKAŹNIKI ===\n{price_data}\n\n"
        f"Napisz analizę w 1 akapicie obejmującą: kierunek trendu, momentum (RSI, MACD), "
        f"reżim zmienności oraz kluczowe poziomy wsparcia/oporu ze średnich kroczących. "
        f"Zakończ dokładnie jedną linią:\n"
        f"Prognoza: WZROST / SPADEK / NEUTRALNIE — [jedno zdanie uzasadnienia]\n\n"
        f"NIE przeszukuj internetu. Używaj wyłącznie dostarczonych danych. Odpowiedz w języku polskim."
    )
    return _run_claude(prompt)


def _get_final_report(symbol: str, news_analysis: str, price_analysis: str) -> str:
    """
    Syntezuje analizę newsów i cenową w finalny raport rynkowy. (Wywołanie 3 z 3)

    Brak dostępu do internetu — Claude łączy dwie dostarczone analizy.

    Args:
        symbol: Symbol kryptowaluty.
        news_analysis: Wyjście z _get_news_analysis().
        price_analysis: Wyjście z _get_price_analysis().

    Returns:
        Sformatowany raport rynkowy po polsku.
    """
    logger.info("Generating final report for %s", symbol)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        f"Jesteś profesjonalnym autorem raportów kryptowalutowych. "
        f"Połącz poniższe dwie analizy w finalny, zwięzły raport dla {symbol}.\n\n"
        f"=== ANALIZA NEWSÓW ===\n{news_analysis}\n\n"
        f"=== TECHNICZNA ANALIZA CENOWA ===\n{price_analysis}\n\n"
        f"Format wyjściowy (zachuj dokładnie):\n\n"
        f"## Raport Rynkowy {symbol} — {today}\n\n"
        f"**Podsumowanie**\n"
        f"- (punkt 1: kluczowy katalizator newsowy)\n"
        f"- (punkt 2: kluczowy sygnał techniczny)\n"
        f"- (punkt 3: łączna perspektywa — maksymalnie 3 punkty)\n\n"
        f"**Analiza**\n"
        f"(1 akapit, maksymalnie 6 zdań. Zintegruj sentyment newsów ze wskaźnikami technicznymi.)\n\n"
        f"**Prognoza: WZROST / SPADEK / NEUTRALNIE**\n"
        f"(1 zdanie powołujące się na 2 najsilniejsze sygnały z obu analiz.)\n\n"
        f"*To nie jest porada finansowa.*\n\n"
        f"NIE przeszukuj internetu. Używaj wyłącznie dostarczonych analiz. Odpowiedz w języku polskim."
    )
    return _run_claude(prompt)
