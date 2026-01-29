import logging

from app.crew_runner import run

# Configure logging to show INFO level for our app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy loggers from dependencies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)


def main():
    symbol = input("Which cryptocurrency symbol do you want to analyze (e.g. BTC)? ").strip().upper()
    if not symbol:
        raise SystemExit("Empty symbol.")
    result = run(symbol)
    print("\n\n========== FINAL RESULT ==========\n")
    print(result)


if __name__ == "__main__":
    main()
