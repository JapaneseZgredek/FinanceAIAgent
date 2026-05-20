"""Typer CLI for Finance AI Agent — scriptable subcommands."""

import asyncio
import os
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from app import config
from app.comparators import compare_reports
from app.core.pipeline import (
    analyze_symbol,
    generate_charts_for_report,
    run_export,
)
from app.core.reports_index import parse_report_filename
from app.utils.errors import ConfigurationError, safe_run
from app.utils.logging import setup_logging

cli_app = typer.Typer(
    name="finance-ai",
    help="Crypto market analysis powered by Claude.",
    no_args_is_help=True,
)

DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")


class OutputFormat(StrEnum):
    md = "md"
    json = "json"


class ExportFormat(StrEnum):
    html = "html"
    pdf = "pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(target, *args, **kwargs):
    """Wrap sync or async callables with safe_run."""
    if asyncio.iscoroutinefunction(target):
        return safe_run(lambda: asyncio.run(target(*args, **kwargs)), debug=DEBUG_MODE)
    return safe_run(target, *args, debug=DEBUG_MODE, **kwargs)


def _resolve_export_target(
    report: str | None,
    symbol: str | None,
    report_date: str | None,
) -> tuple[str, date]:
    """Resolve (symbol, date) from flexible CLI input.

    Raises:
        ConfigurationError: On missing or conflicting arguments.
    """
    parsed_symbol: str | None = None
    parsed_date: date | None = None

    if report:
        result = parse_report_filename(report)
        if result is None:
            raise ConfigurationError(
                message=f"Cannot parse --report '{report}'",
                hint="Expected format: YYYY-MM-DD_SYMBOL (e.g. 2026-04-06_BTC)",
            )
        parsed_symbol, parsed_date = result

    if symbol and parsed_symbol and symbol.upper() != parsed_symbol:
        raise ConfigurationError(
            message=f"Conflicting symbols: --report implies '{parsed_symbol}', --symbol is '{symbol}'",
            hint="Remove one of the conflicting flags.",
        )

    if report_date:
        try:
            date_val = date.fromisoformat(report_date)
        except ValueError:
            raise ConfigurationError(
                message=f"Invalid --date '{report_date}'",
                hint="Expected format: YYYY-MM-DD",
            )
        if parsed_date and date_val != parsed_date:
            raise ConfigurationError(
                message=f"Conflicting dates: --report implies '{parsed_date}', --date is '{date_val}'",
                hint="Remove one of the conflicting flags.",
            )
        parsed_date = date_val

    if symbol:
        parsed_symbol = symbol.upper()

    if not parsed_symbol:
        raise ConfigurationError(
            message="Cannot determine symbol",
            hint="Provide --symbol or --report.",
        )
    if not parsed_date:
        raise ConfigurationError(
            message="Cannot determine date",
            hint="Provide --date or --report.",
        )

    return parsed_symbol, parsed_date


# ---------------------------------------------------------------------------
# Callback (runs before any subcommand)
# ---------------------------------------------------------------------------


@cli_app.callback()
def _callback(
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
) -> None:
    global DEBUG_MODE
    if debug:
        DEBUG_MODE = True
    setup_logging(DEBUG_MODE)
    safe_run(config.validate_env, debug=DEBUG_MODE)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@cli_app.command()
def analyze(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Crypto ticker (e.g. BTC)")],
    language: Annotated[str, typer.Option("--language", "-l", help="Report language.")] = config.DEFAULT_LANGUAGE,
    fmt: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format.")] = OutputFormat.md,
    out: Annotated[Path, typer.Option("--out", "-o", help="Reports directory.")] = Path("reports"),
    export: Annotated[ExportFormat | None, typer.Option("--export", help="Auto-export after analysis.")] = None,
    no_charts: Annotated[bool, typer.Option("--no-charts", help="Skip chart generation.")] = False,
    news_days: Annotated[int | None, typer.Option("--news-days", help="Override NEWS_DAYS_BACK.")] = None,
    price_days: Annotated[int | None, typer.Option("--price-days", help="Override PRICE_WINDOW_DAYS.")] = None,
) -> None:
    """Run a full analysis for a cryptocurrency symbol."""
    if news_days is not None:
        config.NEWS_DAYS_BACK = news_days
    if price_days is not None:
        config.PRICE_WINDOW_DAYS = price_days

    output_format = "json" if fmt == OutputFormat.json else "markdown"

    report, chart_paths, analysis_date = _run(
        analyze_symbol,
        symbol.upper(),
        language,
        output_format,
        reports_dir=out,
        generate_charts=not no_charts,
    )

    typer.echo(report)

    if export:
        _run(
            run_export,
            symbol.upper(),
            report,
            output_format,
            export.value,
            analysis_date,
            chart_paths,
            out,
        )


@cli_app.command()
def compare(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Crypto ticker.")],
    base: Annotated[str | None, typer.Option("--base", help="Base date (YYYY-MM-DD).")] = None,
    compare_date: Annotated[str | None, typer.Option("--compare", help="Compare date (YYYY-MM-DD).")] = None,
    fmt: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format.")] = OutputFormat.md,
    language: Annotated[str, typer.Option("--language", "-l", help="Report language.")] = config.DEFAULT_LANGUAGE,
    no_narrative: Annotated[bool, typer.Option("--no-narrative", help="Skip LLM narrative.")] = False,
    no_auto_generate: Annotated[
        bool, typer.Option("--no-auto-generate", help="Don't auto-generate missing report.")
    ] = False,
    out: Annotated[Path, typer.Option("--out", "-o", help="Reports directory.")] = Path("reports"),
) -> None:
    """Compare two saved reports for the same symbol."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    base_date = date.fromisoformat(base) if base else yesterday
    cmp_date = date.fromisoformat(compare_date) if compare_date else today

    output_format = "json" if fmt == OutputFormat.json else "markdown"

    result = _run(
        compare_reports,
        symbol.upper(),
        base_date,
        cmp_date,
        output_format=output_format,
        language=language,
        include_narrative=not no_narrative,
        auto_generate_today=not no_auto_generate,
        reports_dir=out,
    )

    typer.echo(result)


@cli_app.command()
def export(
    report: Annotated[str | None, typer.Option("--report", help="Report stem (e.g. 2026-04-06_BTC).")] = None,
    symbol: Annotated[str | None, typer.Option("--symbol", "-s", help="Crypto ticker.")] = None,
    report_date: Annotated[str | None, typer.Option("--date", help="Report date (YYYY-MM-DD).")] = None,
    source: Annotated[
        OutputFormat | None, typer.Option("--source", help="Source format to export from (md or json).")
    ] = None,
    fmt: Annotated[ExportFormat, typer.Option("--format", "-f", help="Export format.")] = ExportFormat.html,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("reports"),
    regenerate_charts: Annotated[bool, typer.Option("--regenerate-charts", help="Force chart regeneration.")] = False,
    no_charts: Annotated[bool, typer.Option("--no-charts", help="Skip charts entirely.")] = False,
) -> None:
    """Export a saved report to HTML or PDF."""
    resolved_symbol, resolved_date = _run(_resolve_export_target, report, symbol, report_date)

    stem = f"{resolved_date.isoformat()}_{resolved_symbol}"
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"

    if source == OutputFormat.json:
        source_path = json_path
        source_format = "json"
    elif source == OutputFormat.md:
        source_path = md_path
        source_format = "markdown"
    elif json_path.exists():
        source_path = json_path
        source_format = "json"
    elif md_path.exists():
        source_path = md_path
        source_format = "markdown"
    else:
        typer.echo(f"Error: No report found at {out}/{stem}.{{md,json}}", err=True)
        raise typer.Exit(1)

    if not source_path.exists():
        typer.echo(f"Error: {source_path} does not exist.", err=True)
        raise typer.Exit(1)

    content = source_path.read_text(encoding="utf-8")

    chart_paths: list[Path] = []
    if not no_charts:
        existing_charts = list(out.glob(f"{stem}_*.png"))
        if regenerate_charts or not existing_charts:
            chart_paths = _run(generate_charts_for_report, resolved_symbol, resolved_date, output_dir=out)
        else:
            chart_paths = existing_charts

    path = _run(
        run_export,
        resolved_symbol,
        content,
        source_format,
        fmt.value,
        resolved_date,
        chart_paths,
        out,
    )
    typer.echo(f"Exported → {path}")


@cli_app.command()
def charts(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Crypto ticker.")],
    report_date: Annotated[str, typer.Option("--date", help="Report date (YYYY-MM-DD).")],
    window_days: Annotated[int | None, typer.Option("--window-days", help="Chart display window.")] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")] = Path("reports"),
) -> None:
    """Generate price charts for a given symbol and date."""
    dt = date.fromisoformat(report_date)

    kwargs: dict = {"output_dir": out}
    if window_days is not None:
        kwargs["window_days"] = window_days

    paths = _run(generate_charts_for_report, symbol.upper(), dt, **kwargs)

    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    cli_app()
