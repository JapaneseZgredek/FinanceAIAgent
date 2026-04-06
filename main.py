import asyncio
import logging
import os
from datetime import date
from pathlib import Path

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


def _run_export(symbol: str, report: str, source_format: str, export_fmt: str) -> None:
    """Convert a report string to HTML or PDF and print the result path."""
    path = export_report(
        content=report,
        symbol=symbol,
        export_date=date.today(),
        source_format=source_format,
        export_format=export_fmt,
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


def _post_analysis_menu(symbol: str, report: str, source_format: str) -> None:
    """Interactive loop shown after a report is ready (new or loaded).

    Options:
        e — export (asks html/pdf)
        n — analyze another symbol directly (prompts for symbol, stays in loop)
        m — back to main menu
        q — quit the program entirely
    """
    while True:
        print()
        print("  [e] Export report (HTML / PDF)")
        print("  [n] Analyze another symbol")
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
                    _run_export(symbol, report, source_format, fmt)
            case "n" | "next":
                inputs = _gather_analysis_inputs()
                if inputs is None:
                    continue
                symbol_new, language_new, output_format_new = inputs
                result = safe_run(
                    analyze_symbol, symbol_new, language_new, output_format_new,
                    debug=DEBUG_MODE,
                )
                if result is not None:
                    symbol = symbol_new
                    report = result
                    source_format = output_format_new
            case "m" | "menu":
                return
            case "q" | "quit" | "exit":
                raise SystemExit(0)
            case _:
                print("  Unknown option — type e, n, m, or q.")


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


def analyze_symbol(symbol: str, language: str, output_format: str = "markdown") -> str:
    """Run the full analysis pipeline for one symbol.

    Args:
        symbol: Cryptocurrency ticker, e.g. ``"BTC"``.
        language: Report language, e.g. ``"Polish"``.
        output_format: ``"markdown"`` or ``"json"``.

    Returns:
        Final report string.

    Raises:
        ConfigurationError: If symbol is empty.
    """
    if not symbol:
        raise ConfigurationError(
            message="No symbol provided",
            hint="Enter a cryptocurrency symbol like BTC, ETH, or SOL.",
        )

    result = asyncio.run(run(symbol, language=language, output_format=output_format))
    print("\n\n========== FINAL RESULT ==========\n")
    print(result)
    _save_report(symbol, result, output_format)
    return result


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


def _pick_saved_report() -> tuple[str, str, str] | None:
    """Let the user pick a saved report from the reports/ directory.

    Returns:
        ``(symbol, content, source_format)`` or ``None`` if cancelled.
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
    # Extract symbol from filename: YYYY-MM-DD_SYMBOL.ext
    symbol = path.stem.split("_", 1)[-1] if "_" in path.stem else path.stem
    return symbol, content, source_format


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
                result = safe_run(analyze_symbol, symbol, language, output_format, debug=DEBUG_MODE)
                if result is not None:
                    _post_analysis_menu(symbol, result, output_format)

            case "e" | "export":
                picked = _pick_saved_report()
                if picked is None:
                    continue
                symbol, content, source_format = picked
                print(f"\n  Report: {symbol}  ({source_format})")
                fmt = _ask_export_format()
                if fmt:
                    _run_export(symbol, content, source_format, fmt)

            case "q" | "quit" | "exit":
                break

            case _:
                print("  Unknown option — type a, e, or q.")


if __name__ == "__main__":
    main()
