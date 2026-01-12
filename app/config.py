import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
EXA_API_KEY = os.getenv("EXA_API_KEY")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# Aktualny, działający model (zmieniasz w .env bez dotykania kodu)
GROQ_MODEL = os.getenv("GROQ_MODEL", "groq/llama-3.1-8b-instant")

NEWS_DAYS_BACK = int(os.getenv("NEWS_DAYS_BACK", "7"))
NEWS_LIMIT = int(os.getenv("NEWS_LIMIT", "3"))
NEWS_MAX_SUMMARY_CHARS = int(os.getenv("NEWS_MAX_SUMMARY_CHARS", "280"))

PRICE_WINDOW_DAYS = int(os.getenv("PRICE_WINDOW_DAYS", "120"))
PRICE_LAST_N = int(os.getenv("PRICE_LAST_N", "10"))

USE_INCLUDE_DOMAINS = os.getenv("USE_INCLUDE_DOMAINS", "false").lower() in ("1", "true", "yes")

BAD_DOMAINS = [
    "wikipedia.org",
    "bitcoin.org",
    "coinmarketcap.com",
    "coingecko.com",
    "investopedia.com",
    "britannica.com",
    "dictionary.com",
    "medium.com",
]

GOOD_NEWS_DOMAINS = [
    "reuters.com",
    "coindesk.com",
    "cointelegraph.com",
    "theblock.co",
    "decrypt.co",
]


def validate_env() -> None:
    missing = [k for k, v in {
        "GROQ_API_KEY": GROQ_API_KEY,
        "EXA_API_KEY": EXA_API_KEY,
        "ALPHAVANTAGE_API_KEY": ALPHAVANTAGE_API_KEY,
    }.items() if not v]
    if missing:
        raise SystemExit(f"Missing env vars in .env: {', '.join(missing)}")
