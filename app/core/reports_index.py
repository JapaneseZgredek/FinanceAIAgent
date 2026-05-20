"""Filesystem helpers for saved report files."""

from datetime import date
from pathlib import Path


def list_saved_reports(reports_dir: Path = Path("reports")) -> list[Path]:
    """Return saved report files sorted newest-first.

    Args:
        reports_dir: Directory to scan for report files.

    Returns:
        Sorted list of .md and .json report paths (newest first).
    """
    if not reports_dir.exists():
        return []
    files = [p for p in reports_dir.iterdir() if p.suffix in (".md", ".json") and not p.name.startswith(".")]
    return sorted(files, reverse=True)


def parse_report_filename(stem: str) -> tuple[str, date] | None:
    """Parse a report filename stem into (symbol, report_date).

    Expected format: ``YYYY-MM-DD_SYMBOL`` (e.g. ``2026-04-12_BTC``).

    Args:
        stem: Filename without extension.

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
