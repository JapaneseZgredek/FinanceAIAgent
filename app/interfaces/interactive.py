"""Interactive Rich-enhanced CLI for Finance AI Agent."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from app import config
from app.comparators import compare_reports
from app.core.pipeline import (
    analyze_symbol,
    generate_charts_for_report,
    run_export,
)
from app.core.reports_index import list_saved_reports, parse_report_filename
from app.utils.errors import FinanceAgentError, safe_run
from app.utils.logging import setup_logging

console = Console()
logger = logging.getLogger(__name__)

DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


@dataclass
class AnalysisInputs:
    symbol: str
    language: str
    output_format: str


@dataclass
class ComparisonInputs:
    symbol: str
    base_date: date
    compare_date: date
    output_format: str
    language: str


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _ask_output_format() -> str | None:
    choice = Prompt.ask(
        "  Format", choices=["markdown", "json", "m", "j"], default="markdown"
    )
    match choice:
        case "m" | "markdown":
            return "markdown"
        case "j" | "json":
            return "json"
        case _:
            return None


def _ask_export_format() -> str | None:
    choice = Prompt.ask(
        "  Export format", choices=["html", "pdf", "h", "p", "skip"], default="skip"
    )
    match choice:
        case "h" | "html":
            return "html"
        case "p" | "pdf":
            return "pdf"
        case _:
            return None


def _gather_analysis_inputs() -> AnalysisInputs | None:
    symbol = Prompt.ask("  Symbol (e.g. BTC)").strip().upper()
    if not symbol:
        console.print("  [dim]No symbol entered — returning to menu.[/dim]")
        return None

    language = Prompt.ask("  Language", default=config.DEFAULT_LANGUAGE)
    output_format = _ask_output_format()
    if output_format is None:
        return None

    return AnalysisInputs(symbol=symbol, language=language, output_format=output_format)


def _gather_comparison_inputs() -> ComparisonInputs | None:
    today = date.today()
    yesterday = today - timedelta(days=1)

    symbol = Prompt.ask("  Symbol (e.g. BTC)").strip().upper()
    if not symbol:
        console.print("  [dim]No symbol entered — returning to menu.[/dim]")
        return None

    raw_base = Prompt.ask("  Base date", default=str(yesterday))
    raw_compare = Prompt.ask("  Compare date", default=str(today))
    language = Prompt.ask("  Language", default=config.DEFAULT_LANGUAGE)

    try:
        base_date = date.fromisoformat(raw_base)
    except ValueError:
        console.print(f"  [red]Invalid base date '{raw_base}' — expected YYYY-MM-DD.[/red]")
        return None

    try:
        compare_date = date.fromisoformat(raw_compare)
    except ValueError:
        console.print(f"  [red]Invalid compare date '{raw_compare}' — expected YYYY-MM-DD.[/red]")
        return None

    output_format = _ask_output_format()
    if output_format is None:
        return None

    return ComparisonInputs(
        symbol=symbol,
        base_date=base_date,
        compare_date=compare_date,
        output_format=output_format,
        language=language,
    )


# ---------------------------------------------------------------------------
# Post-analysis menu
# ---------------------------------------------------------------------------


def _post_analysis_menu(
    symbol: str,
    report: str,
    source_format: str,
    report_date: date,
    chart_paths: list[Path] | None = None,
) -> None:
    while True:
        console.print()
        console.print("  [bold green]e[/] Export report (HTML / PDF)")
        console.print("  [bold cyan]m[/] Main menu")
        console.print("  [dim]q[/] Quit")

        action = Prompt.ask("  >", choices=["e", "m", "q"], default="m")

        match action:
            case "e":
                fmt = _ask_export_format()
                if fmt:
                    run_export(symbol, report, source_format, fmt, report_date, chart_paths)
            case "m":
                return
            case "q":
                raise SystemExit(0)


# ---------------------------------------------------------------------------
# Saved reports picker
# ---------------------------------------------------------------------------


def _pick_saved_report() -> tuple[str, str, str, date | None] | None:
    files = list_saved_reports()
    if not files:
        console.print("  [dim]No saved reports found in reports/.[/dim]")
        return None

    table = Table(title="Saved Reports", show_lines=False)
    table.add_column("#", style="bold", width=4)
    table.add_column("Date", style="cyan")
    table.add_column("Symbol", style="green")
    table.add_column("Format")

    for i, path in enumerate(files, start=1):
        parsed = parse_report_filename(path.stem)
        if parsed:
            symbol, report_date = parsed
            table.add_row(str(i), str(report_date), symbol, path.suffix[1:])
        else:
            table.add_row(str(i), "—", path.stem, path.suffix[1:])

    console.print()
    console.print(table)
    console.print()

    raw = Prompt.ask("  Pick a number (or Enter to cancel)", default="")
    if not raw:
        return None

    if not raw.isdigit() or not (1 <= int(raw) <= len(files)):
        console.print("  [red]Invalid selection.[/red]")
        return None

    path = files[int(raw) - 1]
    content = path.read_text(encoding="utf-8")
    source_format = "json" if path.suffix == ".json" else "markdown"

    parsed = parse_report_filename(path.stem)
    if parsed is None:
        console.print(
            f"  [yellow]Unexpected filename format '{path.name}' — charts won't be generated.[/yellow]"
        )
        return path.stem, content, source_format, None

    symbol, report_date = parsed
    return symbol, content, source_format, report_date


# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------


def run_interactive() -> None:
    """Entry point for the interactive menu mode."""
    setup_logging(DEBUG_MODE)
    safe_run(config.validate_env, debug=DEBUG_MODE)

    console.print(
        Panel.fit(
            f"[bold]Finance AI Agent[/bold] — Crypto Analyzer\n\n"
            f"[dim]model=[/]{config.CLAUDE_MODEL}  "
            f"[dim]cache=[/]{config.CACHE_TTL_HOURS:.0f}h  "
            f"[dim]price_window=[/]{config.PRICE_WINDOW_DAYS}d  "
            f"[dim]news=[/]{config.NEWS_DAYS_BACK}d  "
            f"[dim]debug=[/]{DEBUG_MODE}",
            border_style="blue",
        )
    )

    while True:
        console.print()
        console.print("  [bold cyan]a[/] Analyze a new symbol")
        console.print("  [bold yellow]c[/] Compare two saved reports")
        console.print("  [bold green]e[/] Export an existing saved report")
        console.print("  [dim]q[/] Quit")

        try:
            action = Prompt.ask("  >", choices=["a", "c", "e", "q"], default="a")
        except (EOFError, KeyboardInterrupt):
            break

        match action:
            case "a":
                inputs = _gather_analysis_inputs()
                if inputs is None:
                    continue

                with console.status(f"[bold cyan]Analyzing {inputs.symbol}…"):
                    result = safe_run(
                        analyze_symbol,
                        inputs.symbol,
                        inputs.language,
                        inputs.output_format,
                        debug=DEBUG_MODE,
                    )

                report, chart_paths, analysis_date = result
                console.print()
                console.rule(f"[bold green]{inputs.symbol} — Analysis Result")
                console.print(report)
                console.rule()
                _post_analysis_menu(
                    inputs.symbol, report, inputs.output_format, analysis_date, chart_paths
                )

            case "c":
                inputs = _gather_comparison_inputs()
                if inputs is None:
                    continue
                try:
                    with console.status(f"[bold cyan]Comparing {inputs.symbol}…"):
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
                    console.print(result)
                except FinanceAgentError as e:
                    console.print(f"[red]{e.display()}[/red]")

            case "e":
                picked = _pick_saved_report()
                if picked is None:
                    continue
                symbol, content, source_format, report_date = picked
                if report_date is None:
                    console.print("[red]Cannot export — failed to parse date from filename.[/red]")
                    continue
                chart_paths = generate_charts_for_report(symbol, report_date)
                fmt = _ask_export_format()
                if fmt:
                    run_export(symbol, content, source_format, fmt, report_date, chart_paths)

            case "q":
                break


if __name__ == "__main__":
    run_interactive()
