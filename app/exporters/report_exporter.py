"""HTML and PDF export for Finance AI Agent reports.

Converts a markdown or JSON report string to a styled HTML document
(using templates/report.html + templates/report.css) and optionally
to PDF via WeasyPrint.

Designed as a standalone callable — has no dependency on the pipeline
or main.py. Accepts only the final report string plus metadata.

Standalone usage::

    from pathlib import Path
    from datetime import date
    from app.exporters.report_exporter import export_report

    path = export_report(
        content=Path("reports/2026-04-06_BTC.md").read_text(),
        symbol="BTC",
        export_date=date.today(),
        source_format="markdown",
        export_format="pdf",
    )
    print(path)  # reports/2026-04-06_BTC.pdf

FastAPI usage::

    path = export_report(content, symbol, today, export_format=fmt)
    return FileResponse(path)
    # or offload to thread: await asyncio.to_thread(export_report, ...)

WeasyPrint system requirements (PDF only):
    macOS:  brew install weasyprint
    Ubuntu: apt install python3-weasyprint  or  pip install weasyprint
            (also needs: libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0)
"""

import base64
import json
import logging
from datetime import date
from pathlib import Path
from typing import Literal

import markdown as md_lib

logger = logging.getLogger(__name__)

# Directory containing report.html and report.css, resolved relative to this file.
_TEMPLATES_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def _load_template(name: str) -> str:
    """Read a template file from the templates/ directory.

    Args:
        name: Filename, e.g. ``"report.html"`` or ``"report.css"``.

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal conversion helpers
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Escape HTML special characters for safe embedding inside an element.

    Only escapes the four characters that would break HTML structure:
    ``&``, ``<``, ``>``, ``"``. Does not encode quotes inside attributes
    since the output is always placed inside a tag's text content.

    Args:
        text: Plain-text string to escape.

    Returns:
        HTML-safe string.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _to_html_body(content: str, source_format: Literal["markdown", "json"]) -> str:
    """Convert report content to an HTML fragment.

    For markdown input, delegates to the ``markdown`` library with the
    ``tables``, ``fenced_code``, and ``nl2br`` extensions enabled.

    For JSON input, pretty-prints the JSON and wraps it in a ``<div>``
    with class ``json-report`` (styled in report.css as a monospace block).

    Args:
        content: Raw report string — markdown text or a JSON string.
        source_format: ``"markdown"`` or ``"json"``.

    Returns:
        HTML fragment string ready to embed inside ``<main>``.
    """
    if source_format == "json":
        try:
            parsed = json.loads(content)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed — embedding raw content as-is.")
            pretty = content
        return f'<div class="json-report">{_escape_html(pretty)}</div>'

    return md_lib.markdown(
        content,
        extensions=["tables", "fenced_code", "nl2br"],
    )


def _charts_to_html(chart_paths: list[Path]) -> str:
    """Convert a list of PNG chart files to a self-contained HTML section.

    Each PNG is read from disk, base64-encoded, and embedded as a
    ``data:image/png;base64,…`` URI so the HTML file stays self-contained
    (no external file references needed). WeasyPrint handles data URIs
    natively, so PDF export works without extra steps.

    An empty list produces an empty string — the ``{charts}`` placeholder
    in the template is simply replaced with nothing.

    Args:
        chart_paths: Paths to PNG files produced by
            :func:`app.charts.chart_generator.generate_price_charts`.

    Returns:
        HTML ``<section class="charts">`` fragment, or ``""`` if the list
        is empty or all files are missing.
    """
    if not chart_paths:
        return ""

    figures: list[str] = []
    for path in chart_paths:
        if not path.exists():
            logger.warning("Plik wykresu nie istnieje, pomijam: %s", path)
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        figures.append(
            f'<figure>'
            f'<img src="data:image/png;base64,{b64}" alt="{path.stem}"/>'
            f'<figcaption>{path.stem}</figcaption>'
            f'</figure>'
        )

    if not figures:
        return ""

    return '<section class="charts">' + "\n".join(figures) + "</section>"


def _render_html(
    html_body: str,
    symbol: str,
    export_date: date,
    charts_html: str = "",
) -> str:
    """Wrap an HTML fragment in the full page template.

    Loads ``templates/report.html`` and ``templates/report.css`` from disk,
    then substitutes ``{symbol}``, ``{report_date}``, ``{css}``,
    ``{charts}``, and ``{body}`` placeholders.

    Args:
        html_body: HTML fragment produced by :func:`_to_html_body`.
        symbol: Cryptocurrency symbol shown in the page header (e.g. ``"BTC"``).
        export_date: Report date shown in the page header and ``<title>``.
        charts_html: Optional HTML fragment with embedded chart images,
            produced by :func:`_charts_to_html`. Empty string if no charts.

    Returns:
        Complete, self-contained HTML document string.
    """
    html_template = _load_template("report.html")
    css = _load_template("report.css")
    # str.format() would choke on CSS curly braces — use plain replace instead.
    return (
        html_template
        .replace("{symbol}", symbol)
        .replace("{report_date}", export_date.isoformat())
        .replace("{css}", css)
        .replace("{charts}", charts_html)
        .replace("{body}", html_body)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_report(
    content: str,
    symbol: str,
    export_date: date,
    source_format: Literal["markdown", "json"] = "markdown",
    export_format: Literal["html", "pdf"] = "html",
    output_dir: Path = Path("reports"),
    chart_paths: list[Path] | None = None,
) -> Path:
    """Render a report string to an HTML or PDF file.

    Always writes an intermediate ``.html`` file first (it is kept on disk
    alongside any ``.pdf``). If ``export_format="pdf"``, WeasyPrint converts
    the HTML to PDF and the PDF path is returned.

    Args:
        content: Report string — either markdown text or a JSON string.
        symbol: Cryptocurrency symbol used in the filename and page header
            (e.g. ``"BTC"``).
        export_date: Date used in the output filename and page header.
        source_format: Format of ``content`` — ``"markdown"`` or ``"json"``.
        export_format: Desired output format — ``"html"`` or ``"pdf"``.
        output_dir: Directory where files are written. Created if absent.
            Defaults to ``reports/`` relative to the current working directory.
        chart_paths: Optional list of PNG chart files to embed in the HTML
            output as base64 data URIs. Displayed above the report body.
            ``None`` or empty list → no charts embedded.

    Returns:
        :class:`pathlib.Path` to the generated file.
        Points to the ``.pdf`` when ``export_format="pdf"``,
        otherwise to the ``.html`` file.

    Raises:
        ImportError: If the ``weasyprint`` package is not installed when
            ``export_format="pdf"`` is requested.

    Example::

        from datetime import date
        from pathlib import Path
        from app.exporters.report_exporter import export_report

        path = export_report(
            content=Path("reports/2026-04-06_BTC.md").read_text(),
            symbol="BTC",
            export_date=date(2026, 4, 6),
            source_format="markdown",
            export_format="pdf",
        )
        # path == Path("reports/2026-04-06_BTC.pdf")
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{export_date.isoformat()}_{symbol}"

    # Step 1 — convert source content to an HTML fragment
    html_body = _to_html_body(content, source_format)

    # Step 2 — embed fragment into the full page template with CSS
    charts_html = _charts_to_html(chart_paths or [])
    html_doc = _render_html(html_body, symbol, export_date, charts_html)

    # Step 3 — always save the HTML file (self-contained, opens in any browser)
    html_path = output_dir / f"{stem}.html"
    html_path.write_text(html_doc, encoding="utf-8")
    logger.info("HTML report saved → %s", html_path)

    if export_format == "html":
        return html_path

    # Step 4 — PDF conversion via WeasyPrint.
    # WeasyPrint is imported here (not at module level) because it is an
    # OPTIONAL dependency that requires system-level libraries (Pango, Cairo,
    # GDK-PixBuf). Many users only want HTML export and should not need to
    # install those system libraries just to import this module. Deferring the
    # import means: if WeasyPrint is not installed, the error is raised only
    # when PDF is actually requested, not at every import of report_exporter.
    try:
        import weasyprint
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for PDF export.\n"
            "Install with: pip install weasyprint\n"
            "On macOS also run: brew install weasyprint"
        ) from exc

    pdf_path = output_dir / f"{stem}.pdf"
    logger.info("Rendering PDF → %s (this may take a few seconds)", pdf_path)
    weasyprint.HTML(string=html_doc, base_url=str(output_dir)).write_pdf(str(pdf_path))
    logger.info("PDF report saved → %s", pdf_path)
    return pdf_path
