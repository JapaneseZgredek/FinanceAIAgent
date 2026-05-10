"""
Service layer for Finance AI Agent.

Importable by CLI, interactive mode, and FastAPI.
Functions here never call sys.exit — they raise FinanceAgentError on failure.
"""

import asyncio
import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd

from app import config
from app.charts.chart_generator import generate_price_charts
from app.clients.alpha_vantage_client import AlphaVantageClient
from app.core.claude_runner import run
from app.exporters.report_exporter import export_report
from app.utils.errors import ConfigurationError

logger = logging.getLogger(__name__)


def save_report(
    symbol: str,
    content: str,
    output_format: str = "markdown",
    *,
    report_date: date | None = None,
    reports_dir: Path = Path("reports"),
) -> Path:
    """Save a report string to reports/<date>_<SYMBOL>.<ext>.

    Args:
        symbol: Cryptocurrency ticker.
        content: Report string (markdown or JSON).
        output_format: ``"markdown"`` or ``"json"``.
        report_date: Date for the filename. Defaults to today at call time.
        reports_dir: Target directory (created if needed).

    Returns:
        Path to the saved file.
    """
    if report_date is None:
        report_date = date.today()
    reports_dir.mkdir(exist_ok=True)
    ext = "json" if output_format == "json" else "md"
    path = reports_dir / f"{report_date.isoformat()}_{symbol}.{ext}"
    path.write_text(content, encoding="utf-8")
    logger.info("Report saved → %s", path)
    return path


def run_export(
    symbol: str,
    content: str,
    source_format: str,
    export_fmt: str,
    export_date: date,
    chart_paths: list[Path] | None = None,
    output_dir: Path = Path("reports"),
) -> Path:
    """Export a report to HTML or PDF.

    Args:
        symbol: Cryptocurrency ticker.
        content: Report string.
        source_format: ``"markdown"`` or ``"json"``.
        export_fmt: ``"html"`` or ``"pdf"``.
        export_date: Date used in the output filename.
        chart_paths: Optional chart PNGs to embed.
        output_dir: Target directory.

    Returns:
        Path to the exported file.
    """
    path = export_report(
        content=content,
        symbol=symbol,
        export_date=export_date,
        source_format=source_format,
        export_format=export_fmt,
        output_dir=output_dir,
        chart_paths=chart_paths,
    )
    logger.info("Exported → %s", path)
    return path


def generate_charts_for_report(
    symbol: str,
    report_date: date,
    *,
    alpha_client: AlphaVantageClient | None = None,
    window_days: int | None = None,
    output_dir: Path = Path("reports"),
) -> list[Path]:
    """Fetch price history and generate chart PNGs for a saved report.

    Filters data to ``report_date`` (no future data leakage).

    Args:
        symbol: Cryptocurrency ticker.
        report_date: Upper bound for price data.
        alpha_client: Optional pre-built client (DI).
        window_days: Chart display window. Defaults to config.PRICE_WINDOW_DAYS.
        output_dir: Target directory for PNGs.

    Returns:
        List of generated PNG paths.
    """
    if alpha_client is None:
        alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY)
    df = alpha_client.get_daily_prices(symbol)
    df_as_of = df[df.index <= pd.Timestamp(report_date)]
    kwargs: dict = {"export_date": report_date}
    if window_days is not None:
        kwargs["window_days"] = window_days
    return generate_price_charts(df_as_of, symbol, output_dir, **kwargs)


def analyze_symbol(
    symbol: str,
    language: str,
    output_format: str = "markdown",
    *,
    analysis_date: date | None = None,
    reports_dir: Path = Path("reports"),
    generate_charts: bool = True,
    alpha_client: AlphaVantageClient | None = None,
) -> tuple[str, list[Path], date]:
    """Run the full analysis pipeline for one symbol.

    Args:
        symbol: Cryptocurrency ticker, e.g. ``"BTC"``.
        language: Report output language.
        output_format: ``"markdown"`` or ``"json"``.
        analysis_date: Captured date for filenames. Defaults to today.
        reports_dir: Directory for report and chart files.
        generate_charts: Whether to generate PNG charts after analysis.
        alpha_client: Optional pre-built client (DI).

    Returns:
        Tuple of ``(report, chart_paths, analysis_date)``.

    Raises:
        ConfigurationError: If ``symbol`` is empty.
    """
    if not symbol:
        raise ConfigurationError(
            message="No symbol provided",
            hint="Enter a cryptocurrency symbol like BTC, ETH, or SOL.",
        )

    if analysis_date is None:
        analysis_date = date.today()

    t0 = time.perf_counter()
    result = asyncio.run(run(symbol, language=language, output_format=output_format))
    logger.info("Full pipeline for %s completed in %.1fs", symbol, time.perf_counter() - t0)

    save_report(symbol, result, output_format, report_date=analysis_date, reports_dir=reports_dir)

    chart_paths: list[Path] = []
    if generate_charts:
        if alpha_client is None:
            alpha_client = AlphaVantageClient(config.ALPHAVANTAGE_API_KEY)
        df = alpha_client.get_daily_prices(symbol)
        chart_paths = generate_price_charts(df, symbol, reports_dir, export_date=analysis_date)

    return result, chart_paths, analysis_date
