import asyncio
import logging
import os
from datetime import date
from pathlib import Path

from app.claude_runner import run
from app.utils.errors import safe_run, ConfigurationError
from app import config

# Configure logging to show INFO level for our app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy loggers from dependencies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Enable debug mode via environment variable
DEBUG_MODE = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

logger = logging.getLogger(__name__)


def _save_report(symbol: str, report: str, output_format: str = "markdown") -> None:
    """Save the final report to reports/YYYY-MM-DD_<SYMBOL>.<ext>."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ext = "json" if output_format == "json" else "md"
    filename = reports_dir / f"{date.today().isoformat()}_{symbol}.{ext}"
    filename.write_text(report, encoding="utf-8")
    logger.info("Report saved → %s", filename)


def analyze_symbol(symbol: str, language: str, output_format: str = "markdown"):
    """Run analysis for a cryptocurrency symbol in the given output language and format."""
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


def main():
    safe_run(config.validate_env, debug=DEBUG_MODE)

    print("=" * 50)
    print("  🪙 Finance AI Agent - Crypto Analyzer")
    print("=" * 50)
    print()

    try:
        symbol = input("Which cryptocurrency symbol do you want to analyze (e.g. BTC)? ").strip().upper()
        language = input(f"Report language (e.g. Polish, English, Spanish) [{config.DEFAULT_LANGUAGE}]: ").strip() or config.DEFAULT_LANGUAGE
        fmt_input = input("Output format (markdown, json) [markdown]: ").strip().lower()
        output_format = fmt_input if fmt_input in ("markdown", "json") else "markdown"
    except EOFError:
        print("\n⚠️  No input provided.")
        return

    safe_run(analyze_symbol, symbol, language, output_format, debug=DEBUG_MODE)


if __name__ == "__main__":
    main()
