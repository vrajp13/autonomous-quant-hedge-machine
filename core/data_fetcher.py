"""
data_fetcher.py – Market data acquisition layer.

Fetches OHLCV history, per-ticker fundamentals, news headlines,
earnings calendar, and insider transactions via yfinance.

All public functions are resilient: network errors are caught and
logged so a single bad ticker never aborts the pipeline.
"""

import time
import logging
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)


# ── Bulk OHLCV download ────────────────────────────────────────────────────

def fetch_price_history(tickers, period="1y", interval="1d"):
    """
    Download OHLCV history for *tickers* in one batched request.

    Returns a MultiIndex DataFrame (columns: Price-type × Ticker).
    Single-ticker results are re-wrapped to a consistent MultiIndex.
    """
    if not tickers:
        return pd.DataFrame()
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = list(tickers)

    try:
        data = yf.download(
            tickers,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="column",
        )
        # Ensure MultiIndex even for a single ticker
        if len(tickers) == 1 and not isinstance(data.columns, pd.MultiIndex):
            data.columns = pd.MultiIndex.from_product([data.columns, tickers])
        return data
    except Exception as exc:
        logger.error("fetch_price_history error: %s", exc)
        return pd.DataFrame()


def get_close_series(price_history, ticker):
    """Extract the Close price series for *ticker*."""
    try:
        if isinstance(price_history.columns, pd.MultiIndex):
            return price_history["Close"][ticker].dropna()
        return price_history["Close"].dropna()
    except KeyError:
        return pd.Series(dtype=float)


def get_volume_series(price_history, ticker):
    """Extract the Volume series for *ticker*."""
    try:
        if isinstance(price_history.columns, pd.MultiIndex):
            return price_history["Volume"][ticker].dropna()
        return price_history["Volume"].dropna()
    except KeyError:
        return pd.Series(dtype=float)


# ── Per-ticker fundamental info ────────────────────────────────────────────

_INFO_FIELDS = [
    "regularMarketPrice", "previousClose", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "marketCap", "trailingPE", "forwardPE", "pegRatio", "priceToBook",
    "enterpriseToEbitda", "returnOnEquity", "returnOnAssets",
    "profitMargins", "operatingMargins", "revenueGrowth", "earningsGrowth",
    "earningsQuarterlyGrowth", "debtToEquity", "currentRatio", "quickRatio",
    "totalCash", "totalDebt", "dividendYield", "dividendRate", "payoutRatio",
    "exDividendDate", "fiveYearAvgDividendYield", "trailingAnnualDividendYield",
    "earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd",
    "shortRatio", "shortPercentOfFloat", "recommendationMean",
    "numberOfAnalystOpinions", "targetMeanPrice", "targetHighPrice",
    "targetLowPrice", "beta", "longName", "sector", "industry",
    "averageVolume", "averageVolume10days",
]


def fetch_ticker_info(ticker, retries=2):
    """Fetch the info dict for a single ticker. Returns dict (may be empty)."""
    for attempt in range(retries + 1):
        try:
            t    = yf.Ticker(ticker)
            info = t.info or {}
            return {k: info.get(k) for k in _INFO_FIELDS}
        except Exception as exc:
            if attempt < retries:
                time.sleep(1)
            else:
                logger.warning("fetch_ticker_info(%s) failed: %s", ticker, exc)
    return {}


def fetch_news(ticker, max_items=8):
    """Return a list of news dicts for *ticker*."""
    try:
        t    = yf.Ticker(ticker)
        news = t.news or []
        return news[:max_items]
    except Exception as exc:
        logger.warning("fetch_news(%s) failed: %s", ticker, exc)
        return []


def fetch_upcoming_earnings(ticker):
    """Returns dict with 'earnings_date' key (datetime or None)."""
    try:
        t   = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty:
            if isinstance(cal, pd.DataFrame):
                dates = cal.loc["Earnings Date"] if "Earnings Date" in cal.index else None
                if dates is not None:
                    return {"earnings_date": dates.iloc[0]}
            elif isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    return {"earnings_date": ed[0] if isinstance(ed, list) else ed}
    except Exception as exc:
        logger.debug("fetch_upcoming_earnings(%s): %s", ticker, exc)
    return {"earnings_date": None}


def fetch_insider_transactions(ticker):
    """Return insider buy/sell DataFrame (or empty DataFrame)."""
    try:
        t  = yf.Ticker(ticker)
        df = t.insider_transactions
        if df is not None and not df.empty:
            return df.head(20)
    except Exception as exc:
        logger.debug("fetch_insider_transactions(%s): %s", ticker, exc)
    return pd.DataFrame()


# ── Main aggregated fetch ──────────────────────────────────────────────────

def fetch_market_data(tickers, price_period="1y"):
    """
    Orchestrate all data fetching for the given ticker list.

    Returns
    -------
    price_history : pd.DataFrame  MultiIndex OHLCV
    fundamentals  : dict[ticker -> info_dict]
    news_map      : dict[ticker -> list[news_dicts]]
    earnings_map  : dict[ticker -> dict]
    insider_map   : dict[ticker -> pd.DataFrame]
    """
    logger.info("Fetching price history for %d tickers …", len(tickers))
    price_history = fetch_price_history(tickers, period=price_period)

    fundamentals = {}
    news_map     = {}
    earnings_map = {}
    insider_map  = {}

    logger.info("Fetching per-ticker fundamentals/news/earnings/insider …")
    for idx, ticker in enumerate(tickers):
        fundamentals[ticker] = fetch_ticker_info(ticker)
        news_map[ticker]     = fetch_news(ticker)
        earnings_map[ticker] = fetch_upcoming_earnings(ticker)
        insider_map[ticker]  = fetch_insider_transactions(ticker)

        if (idx + 1) % 20 == 0:
            logger.info("  %d / %d tickers done", idx + 1, len(tickers))

        time.sleep(0.25)   # polite pause to avoid Yahoo throttling

    logger.info("Data fetch complete.")
    return price_history, fundamentals, news_map, earnings_map, insider_map


# ── Legacy shim (used by existing unit tests) ──────────────────────────────

def fetch_prices(tickers):
    """Legacy single-price fetch. Returns DataFrame(ticker, price)."""
    if tickers is None:
        tickers = []
    elif isinstance(tickers, str):
        tickers = [tickers]
    else:
        try:
            tickers = list(tickers)
        except TypeError:
            tickers = [tickers]

    rows = []
    for ticker in tickers:
        try:
            info  = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice")
            if price is not None:
                rows.append({"ticker": ticker, "price": price})
        except Exception as exc:
            logger.warning("fetch_prices(%s): %s", ticker, exc)
        time.sleep(0.1)

    if not rows:
        logger.warning("WARNING: No price data returned")
        return pd.DataFrame(columns=["ticker", "price"])

    return pd.DataFrame(rows)