"""
Handles fetching and caching historical price data.

Uses Twelve Data (https://twelvedata.com) as the primary source -- a real,
documented API with a free tier, rather than scraping Yahoo Finance or
Stooq, both of which turned out to rate-limit / block automated requests
unpredictably. Falls back to Yahoo Finance if Twelve Data is unavailable.
"""
import os
import time
import random
import requests
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")

_PERIOD_DAYS = {"1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 8000}


def _fetch_from_twelvedata(ticker: str, period: str) -> pd.DataFrame:
    if not TWELVE_DATA_API_KEY:
        raise ValueError("TWELVE_DATA_API_KEY is not set in .env -- sign up free at twelvedata.com and add it.")

    outputsize = min(_PERIOD_DAYS.get(period, 730), 5000)  # free tier caps at 5000 bars/request
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": ticker,
        "interval": "1day",
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if data.get("status") == "error" or "values" not in data:
        raise ValueError(f"Twelve Data error for {ticker}: {data.get('message', data)}")

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col])

    if df.empty:
        raise ValueError(f"Twelve Data returned no data for {ticker}.")
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _fetch_from_yahoo(ticker: str, period: str, interval: str, max_retries: int) -> pd.DataFrame:
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                return df
            last_error = ValueError(f"No data returned for {ticker}.")
        except Exception as e:
            last_error = e

        if attempt < max_retries:
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"  {ticker}: Yahoo Finance fetch failed (attempt {attempt}/{max_retries}), retrying in {wait:.1f}s...")
            time.sleep(wait)

    raise last_error


def get_price_history(ticker: str, period: str = "2y", interval: str = "1d", use_cache: bool = True,
                       max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch adjusted daily price history for a ticker.
    Caches to disk so repeated backtests don't re-hit the API.
    Tries Twelve Data first (reliable, needs a free API key in .env).
    Falls back to Yahoo Finance if no Twelve Data key is set or it fails.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{ticker}_{period}_{interval}.csv")

    if use_cache and os.path.exists(cache_path):
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        if not df.empty:
            return df

    errors = []

    if TWELVE_DATA_API_KEY:
        try:
            df = _fetch_from_twelvedata(ticker, period)
            df.to_csv(cache_path)
            return df
        except Exception as e:
            errors.append(f"Twelve Data: {e}")
            print(f"  {ticker}: Twelve Data failed ({e}), trying Yahoo Finance...")

    try:
        df = _fetch_from_yahoo(ticker, period, interval, max_retries)
        df.to_csv(cache_path)
        return df
    except Exception as e:
        errors.append(f"Yahoo Finance: {e}")

    raise ValueError(f"Could not fetch data for {ticker}. Errors: {' | '.join(errors)}")


def get_latest_price(ticker: str) -> float:
    """Fetch the most recent closing price for a ticker."""
    df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"Could not fetch latest price for {ticker}")
    return float(df["Close"].iloc[-1])


if __name__ == "__main__":
    # Quick manual test
    df = get_price_history("AAPL", period="1y")
    print(df.tail())
