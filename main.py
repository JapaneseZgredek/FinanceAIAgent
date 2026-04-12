import asyncio
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd

from app.charts.chart_generator import generate_price_charts
from app.clients.alpha_vantage_client import AlphaVantageClient
from app.claude_runner import run
from app.exporters.report_exporter import export_report
from app.utils.errors import safe_run, ConfigurationError
from app import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

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
    print(f"  Exported → {path}")


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
        print()
        print("  [e] Export report (HTML / PDF)")
        print("  [m] Main menu")
        print("  [q] Quit")

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
                print("  Unknown option — type e, m, or q.")


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


def _gather_analysis_inputs() -> tuple[str, str, str] | None:
    """Prompt the user for symbol, language, and output format.

    Returns:
        ``(symbol, language, output_format)`` or ``None`` if input was cancelled.
    """
    try:
        symbol = input("Symbol (e.g. BTC): ").strip().upper()
        language = (
            input(f"Language [{config.DEFAULT_LANGUAGE}]: ").strip()
            or config.DEFAULT_LANGUAGE
        )
        fmt_raw = input("Format — markdown / json [markdown]: ").strip().lower()
        output_format = fmt_raw if fmt_raw in ("markdown", "json") else "markdown"
    except EOFError:
        return None

    if not symbol:
        print("  No symbol entered — returning to menu.")
        return None

    return symbol, language, output_format


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

    result = asyncio.run(run(symbol, language=language, output_format=output_format))
    print("\n\n========== FINAL RESULT ==========\n")
    print(result)
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
        print("  No saved reports found in reports/.")
        return None

    print()
    for i, path in enumerate(files, start=1):
        print(f"  [{i}] {path.name}")
    print()

    try:
        raw = input("  Pick a number (or Enter to cancel): ").strip()
    except EOFError:
        return None

    if not raw:
        return None

    if not raw.isdigit() or not (1 <= int(raw) <= len(files)):
        print("  Invalid selection.")
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

    print("=" * 50)
    print("  Finance AI Agent — Crypto Analyzer")
    print("=" * 50)

    while True:
        print()
        print("  [a] Analyze a new symbol")
        print("  [e] Export an existing saved report")
        print("  [q] Quit")

        try:
            action = input("  > ").strip().lower()
        except EOFError:
            break

        match action:
            case "a" | "analyze":
                inputs = _gather_analysis_inputs()
                if inputs is None:
                    continue
                symbol, language, output_format = inputs
                report, chart_paths, analysis_date = safe_run(analyze_symbol, symbol, language, output_format, debug=DEBUG_MODE)
                _post_analysis_menu(symbol, report, output_format, analysis_date, chart_paths)

            case "e" | "export":
                picked = _pick_saved_report()
                if picked is None:
                    continue
                symbol, content, source_format, report_date = picked
                if report_date is None:
                    print("  Nie można wyeksportować — nie udało się odczytać daty z nazwy pliku.")
                    print("  Oczekiwany format: YYYY-MM-DD_SYMBOL.md / .json")
                    continue
                print(f"\n  Report: {symbol}  ({source_format})")
                chart_paths = _generate_charts_for_report(symbol, report_date)
                fmt = _ask_export_format()
                if fmt:
                    _run_export(symbol, content, source_format, fmt, report_date, chart_paths)

            case "q" | "quit" | "exit":
                break

            case _:
                print("  Unknown option — type a, e, or q.")


if __name__ == "__main__":
    main()
