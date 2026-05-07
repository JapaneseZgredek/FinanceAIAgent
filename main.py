import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from app.charts.chart_generator import generate_price_charts
from app.clients.alpha_vantage_client import AlphaVantageClient
from app.claude_runner import run
from app.comparators import compare_reports
from app.exporters.report_exporter import export_report
from app.utils.errors import safe_run, ConfigurationError, FinanceAgentError
from app import config

DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Input bundles
# ---------------------------------------------------------------------------


@dataclass
class AnalysisInputs:
    symbol: str
    language: str
    output_format: str  # "markdown" | "json"


@dataclass
class ComparisonInputs:
    symbol: str
    base_date: date
    compare_date: date
    output_format: str  # "markdown" | "json"
    language: str

logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------


def _save_report(symbol: str, report: str, output_format: str = "markdown") -> Path:
    """Save the final report to reports/YYYY-MM-DD_<SYMBOL>.<ext>.

    Returns:
        Path to the saved file.
    """
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ext = "json" if output_format == "json" else "md"
    path = reports_dir / f"{date.today().isoformat()}_{symbol}.{ext}"
    path.write_text(report, encoding="utf-8")
    logger.info("Report saved → %s", path)
    return path


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _run_export(
    symbol: str,
    report: str,
    source_format: str,
    export_fmt: str,
    export_date: date,
    chart_paths: list[Path] | None = None,
) -> None:
    """Convert a report string to HTML or PDF and print the result path."""
    path = export_report(
        content=report,
        symbol=symbol,
        export_date=export_date,
        source_format=source_format,
        export_format=export_fmt,
        chart_paths=chart_paths,
    )
    logger.info("Exported → %s", path)


def _ask_output_format() -> str | None:
    """Ask the user to pick a report output format.

    Returns:
        ``"markdown"``, ``"json"``, or ``None`` if the input is invalid.
    """
    choice = input("  Format: [m]arkdown / [j]son [markdown]: ").strip().lower()
    match choice:
        case "" | "m" | "markdown":
            return "markdown"
        case "j" | "json":
            return "json"
        case _:
            return None


def _ask_export_format() -> str | None:
    """Ask the user to pick an export format.

    Returns:
        ``"html"``, ``"pdf"``, or ``None`` if the user skips.
    """
    choice = input("  Format: [h]tml / [p]df / [skip]: ").strip().lower()
    match choice:
        case "h" | "html":
            return "html"
        case "p" | "pdf":
            return "pdf"
        case _:
            return None


# ---------------------------------------------------------------------------
# Post-analysis action loop
# ---------------------------------------------------------------------------


def _post_analysis_menu(
    symbol: str,
    report: str,
    source_format: str,
    report_date: date,
    chart_paths: list[Path] | None = None,
) -> None:
    """Interactive loop shown after a report is ready (new or loaded).

    Options:
        e — export (asks html/pdf)
        m — back to main menu
        q — quit the program entirely
    """
    while True:
        logger.info("")
        logger.info("  [e] Export report (HTML / PDF)")
        logger.info("  [m] Main menu")
        logger.info("  [q] Quit")

        try:
            action = input("  > ").strip().lower()
        except EOFError:
            return

        match action:
            case "e" | "export":
                fmt = _ask_export_format()
                if fmt:
                    _run_export(symbol, report, source_format, fmt, report_date, chart_paths)
            case "m" | "menu":
                return
            case "q" | "quit" | "exit":
                raise SystemExit(0)
            case _:
                logger.info("  Unknown option — type e, m, or q.")


# ---------------------------------------------------------------------------
# Chart generation helpers
# ---------------------------------------------------------------------------


def _generate_charts_for_report(symbol: str, report_date: date) -> list[Path]:
    """Generuj wykresy dla istniejącego raportu z danego dnia.

    Pobiera pełną historię cen (z cache), filtruje df do danych
    niepóźniejszych niż ``report_date`` (żadne "przyszłe" dane nie wyciekają),
    a następnie generuje wykresy PNG do katalogu ``reports/``.

    Args:
        symbol: Symbol kryptowaluty, np. ``"BTC"``.
        report_date: Data raportu — górna granica filtrowania historii.

    Returns:
        Lista ścieżek do wygenerowanych plików PNG.
    """
    alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY)
    df = alpha_client.get_daily_prices(symbol)
    df_as_of = df[df.index <= pd.Timestamp(report_date)]
    return generate_price_charts(df_as_of, symbol, Path("reports"), export_date=report_date)


# ---------------------------------------------------------------------------
# New analysis flow
# ---------------------------------------------------------------------------


def _gather_analysis_inputs() -> AnalysisInputs | None:
    """Prompt the user for symbol, language, and output format.

    Returns:
        ``AnalysisInputs`` or ``None`` if input was cancelled.
    """
    try:
        symbol = input("Symbol (e.g. BTC): ").strip().upper()
        if not symbol:
            logger.info("  No symbol entered — returning to menu.")
            return None
        language = (
            input(f"Language [{config.DEFAULT_LANGUAGE}]: ").strip()
            or config.DEFAULT_LANGUAGE
        )
    except EOFError:
        return None

    output_format = _ask_output_format()
    if output_format is None:
        logger.info("  Invalid format — returning to menu.")
        return None

    return AnalysisInputs(symbol=symbol, language=language, output_format=output_format)


def _gather_comparison_inputs() -> ComparisonInputs | None:
    """Prompt the user for comparison parameters.

    Returns:
        ``ComparisonInputs`` or ``None`` if input was cancelled or invalid.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    try:
        symbol = input("Symbol (e.g. BTC): ").strip().upper()
        if not symbol:
            logger.info("  No symbol entered — returning to menu.")
            return None

        raw_base = input(f"Base date [{yesterday}]: ").strip() or str(yesterday)
        raw_compare = input(f"Compare date [{today}]: ").strip() or str(today)
        language = (
            input(f"Language [{config.DEFAULT_LANGUAGE}]: ").strip()
            or config.DEFAULT_LANGUAGE
        )
    except EOFError:
        return None

    try:
        base_date = date.fromisoformat(raw_base)
    except ValueError:
        logger.info("  Invalid base date '%s' — expected YYYY-MM-DD.", raw_base)
        return None

    try:
        compare_date = date.fromisoformat(raw_compare)
    except ValueError:
        logger.info("  Invalid compare date '%s' — expected YYYY-MM-DD.", raw_compare)
        return None

    output_format = _ask_output_format()
    if output_format is None:
        logger.info("  Invalid format — returning to menu.")
        return None

    return ComparisonInputs(
        symbol=symbol,
        base_date=base_date,
        compare_date=compare_date,
        output_format=output_format,
        language=language,
    )


def _compare_reports_flow(inputs: ComparisonInputs) -> None:
    """Run the comparison pipeline and log the result."""
    logger.info(
        "Comparing %s: %s → %s (%s)", inputs.symbol, inputs.base_date, inputs.compare_date, inputs.output_format,
    )
    t0 = time.perf_counter()
    result = asyncio.run(
        compare_reports(
            inputs.symbol,
            inputs.base_date,
            inputs.compare_date,
            output_format=inputs.output_format,
            language=inputs.language,
        )
    )
    logger.info("Comparison completed in %.1fs", time.perf_counter() - t0)
    logger.info("========== COMPARISON ==========")
    logger.info("%s", result)


def analyze_symbol(
    symbol: str,
    language: str,
    output_format: str = "markdown",
) -> tuple[str, list[Path], date]:
    """Run the full analysis pipeline for one symbol and generate price charts.

    Args:
        symbol: Cryptocurrency ticker, e.g. ``"BTC"``.
        language: Report language, e.g. ``"Polish"``.
        output_format: ``"markdown"`` or ``"json"``.

    Returns:
        Tuple of ``(report, chart_paths, analysis_date)`` — the final report
        string, list of generated PNG chart paths, and the date captured at
        the start of the analysis (used consistently for filenames and exports).

    Raises:
        ConfigurationError: If symbol is empty.
    """
    if not symbol:
        raise ConfigurationError(
            message="No symbol provided",
            hint="Enter a cryptocurrency symbol like BTC, ETH, or SOL.",
        )

    # Data przechwycona raz — używana spójnie do zapisu raportu, wykresów i eksportu
    analysis_date = date.today()

    t0 = time.perf_counter()
    result = asyncio.run(run(symbol, language=language, output_format=output_format))
    logger.info("Full pipeline for %s completed in %.1fs", symbol, time.perf_counter() - t0)

    logger.info("========== FINAL RESULT ==========")
    logger.info("%s", result)

    _save_report(symbol, result, output_format)

    # Generuj wykresy — dane pobrane z cache (szybkie, bez dodatkowego wywołania API)
    alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY)
    df = alpha_client.get_daily_prices(symbol)
    chart_paths = generate_price_charts(df, symbol, Path("reports"), export_date=analysis_date)

    return result, chart_paths, analysis_date


# ---------------------------------------------------------------------------
# Load existing report flow
# ---------------------------------------------------------------------------


def _list_saved_reports() -> list[Path]:
    """Return saved report files sorted newest-first."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    files = [
        p for p in reports_dir.iterdir()
        if p.suffix in (".md", ".json") and not p.name.startswith(".")
    ]
    return sorted(files, reverse=True)


def _parse_report_filename(stem: str) -> tuple[str, date] | None:
    """Parse a report filename stem into (symbol, report_date).

    Expected format: ``YYYY-MM-DD_SYMBOL`` (e.g. ``2026-04-12_BTC``).
    Returns ``None`` if the stem doesn't match this pattern.

    Args:
        stem: Filename without extension, e.g. ``"2026-04-12_BTC"``.

    Returns:
        ``(symbol, report_date)`` or ``None`` if parsing fails.
    """
    parts = stem.split("_", 1)
    if len(parts) != 2:
        return None
    date_str, symbol = parts
    try:
        return symbol, date.fromisoformat(date_str)
    except ValueError:
        return None


def _pick_saved_report() -> tuple[str, str, str, date | None] | None:
    """Let the user pick a saved report from the reports/ directory.

    Returns:
        ``(symbol, content, source_format, report_date)`` or ``None`` if cancelled.
        ``report_date`` is ``None`` when the filename doesn't match the expected
        ``YYYY-MM-DD_SYMBOL.ext`` pattern — the caller should skip chart generation.
    """
    files = _list_saved_reports()
    if not files:
        logger.info("  No saved reports found in reports/.")
        return None

    logger.info("")
    for i, path in enumerate(files, start=1):
        logger.info("  [%d] %s", i, path.name)
    logger.info("")

    try:
        raw = input("  Pick a number (or Enter to cancel): ").strip()
    except EOFError:
        return None

    if not raw:
        return None

    if not raw.isdigit() or not (1 <= int(raw) <= len(files)):
        logger.info("  Invalid selection.")
        return None

    path = files[int(raw) - 1]
    content = path.read_text(encoding="utf-8")
    source_format = "json" if path.suffix == ".json" else "markdown"

    parsed = _parse_report_filename(path.stem)
    if parsed is None:
        logger.warning(
            "Nieoczekiwany format nazwy pliku '%s' — oczekiwano YYYY-MM-DD_SYMBOL. "
            "Wykresy nie zostaną wygenerowane.",
            path.name,
        )
        # Użyj całego stem jako symbolu (best-effort dla nagłówka HTML)
        return path.stem, content, source_format, None

    symbol, report_date = parsed
    return symbol, content, source_format, report_date


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    safe_run(config.validate_env, debug=DEBUG_MODE)

    logger.info("=" * 50)
    logger.info("  Finance AI Agent — Crypto Analyzer")
    logger.info("=" * 50)
    logger.info(
        "Config: model=%s | cache_ttl=%.1fh | price_window=%dd | news_days=%d | debug=%s",
        config.CLAUDE_MODEL, config.CACHE_TTL_HOURS,
        config.PRICE_WINDOW_DAYS, config.NEWS_DAYS_BACK, DEBUG_MODE,
    )

    while True:
        logger.info("")
        logger.info("  [a] Analyze a new symbol")
        logger.info("  [c] Compare two saved reports")
        logger.info("  [e] Export an existing saved report")
        logger.info("  [q] Quit")

        try:
            action = input("  > ").strip().lower()
        except EOFError:
            break

        match action:
            case "a" | "analyze":
                inputs = _gather_analysis_inputs()
                if inputs is None:
                    continue
                report, chart_paths, analysis_date = safe_run(
                    analyze_symbol, inputs.symbol, inputs.language, inputs.output_format, debug=DEBUG_MODE,
                )
                _post_analysis_menu(inputs.symbol, report, inputs.output_format, analysis_date, chart_paths)

            case "c" | "compare":
                inputs = _gather_comparison_inputs()
                if inputs is None:
                    continue
                try:
                    _compare_reports_flow(inputs)
                except FinanceAgentError as e:
                    logger.error(e.display())

            case "e" | "export":
                picked = _pick_saved_report()
                if picked is None:
                    continue
                symbol, content, source_format, report_date = picked
                if report_date is None:
                    logger.warning("Nie można wyeksportować — nie udało się odczytać daty z nazwy pliku.")
                    logger.warning("Oczekiwany format: YYYY-MM-DD_SYMBOL.md / .json")
                    continue
                logger.info("Report: %s  (%s)", symbol, source_format)
                chart_paths = _generate_charts_for_report(symbol, report_date)
                fmt = _ask_export_format()
                if fmt:
                    _run_export(symbol, content, source_format, fmt, report_date, chart_paths)

            case "q" | "quit" | "exit":
                break

            case _:
                logger.info("  Unknown option — type a, c, e, or q.")


if __name__ == "__main__":
    main()
