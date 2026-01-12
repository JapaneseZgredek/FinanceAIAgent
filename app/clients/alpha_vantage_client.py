import requests
import pandas as pd


class AlphaVantageClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_daily_prices(self, ticker: str) -> pd.DataFrame:
        url = (
            "https://www.alphavantage.co/query"
            f"?function=DIGITAL_CURRENCY_DAILY&symbol={ticker}"
            f"&market=USD&apikey={self.api_key}"
        )
        data = requests.get(url, timeout=30).json()

        if "Note" in data:
            raise RuntimeError(f"AlphaVantage rate limit: {data['Note']}")
        if "Error Message" in data:
            raise RuntimeError(f"AlphaVantage error: {data['Error Message']}")
        if "Time Series (Digital Currency Daily)" not in data:
            raise RuntimeError(f"Unexpected response keys: {list(data.keys())}")

        ts = data["Time Series (Digital Currency Daily)"]

        def pick_close(prices: dict) -> float:
            for key in ("4a. close (USD)", "4. close", "4b. close (USD)"):
                if key in prices:
                    return float(prices[key])
            for k, v in prices.items():
                if "close" in k.lower():
                    return float(v)
            raise KeyError(f"No close key found. Keys: {list(prices.keys())}")

        close = {d: pick_close(p) for d, p in ts.items()}
        df = pd.DataFrame.from_dict(close, orient="index", columns=["price"])
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()  # rosnąco
        return df
