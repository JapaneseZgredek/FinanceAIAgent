import logging
import os

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


def analyze_symbol(symbol: str, language: str):
    """Run analysis for a cryptocurrency symbol in the given output language."""
    if not symbol:
        raise ConfigurationError(
            message="No symbol provided",
            hint="Enter a cryptocurrency symbol like BTC, ETH, or SOL.",
        )

    result = run(symbol, language=language)
    print("\n\n========== FINAL RESULT ==========\n")
    print(result)
    return result


def main():
    print("=" * 50)
    print("  🪙 Finance AI Agent - Crypto Analyzer")
    print("=" * 50)
    print()

    try:
        symbol = input("Which cryptocurrency symbol do you want to analyze (e.g. BTC)? ").strip().upper()
        language = input(f"Report language (e.g. Polish, English, Spanish) [{config.DEFAULT_LANGUAGE}]: ").strip() or config.DEFAULT_LANGUAGE
    except EOFError:
        print("\n⚠️  No input provided.")
        return

    safe_run(analyze_symbol, symbol, language, debug=DEBUG_MODE)


if __name__ == "__main__":
    main()
