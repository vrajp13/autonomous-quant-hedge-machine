"""
universe.py – Ticker universe management.

Loads tickers from data/tickers.csv and exposes helpers to filter by sector
or instrument type.
"""

import os
import pandas as pd

_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tickers.csv")

SECTOR_ETFS = {
    "Technology":            "XLK",
    "Financials":            "XLF",
    "Healthcare":            "XLV",
    "Energy":                "XLE",
    "Consumer Discretionary":"XLY",
    "Consumer Staples":      "XLP",
    "Industrials":           "XLI",
    "Utilities":             "XLU",
    "Real Estate":           "XLRE",
    "Materials":             "XLB",
    "Communication Services":"XLC",
}


def get_universe(sectors=None, instrument_types=None, exclude_types=None):
    """
    Return the full ticker universe as a DataFrame.

    Parameters
    ----------
    sectors          : list[str] | None  Filter to only these sectors.
    instrument_types : list[str] | None  Keep only these types.
    exclude_types    : list[str] | None  Exclude these types.

    Returns
    -------
    pd.DataFrame  columns: ticker, sector, instrument_type, description
    """
    df = pd.read_csv(_CSV_PATH)
    if sectors:
        df = df[df["sector"].isin(sectors)]
    if instrument_types:
        df = df[df["instrument_type"].isin(instrument_types)]
    if exclude_types:
        df = df[~df["instrument_type"].isin(exclude_types)]
    return df.reset_index(drop=True)


def get_stock_tickers():
    """Return only equity tickers (no ETFs, no indices)."""
    return get_universe(instrument_types=["Stock"])["ticker"].tolist()


def get_all_tickers(include_indices=False):
    """Return all tickers including ETFs."""
    df = get_universe()
    if not include_indices:
        df = df[df["instrument_type"] != "Index"]
    return df["ticker"].tolist()


def get_sector_etf_tickers():
    """Return the list of sector ETF tickers."""
    return list(SECTOR_ETFS.values())


def get_tickers_by_sector():
    """Return a dict mapping sector -> list of stock tickers."""
    df = get_universe(instrument_types=["Stock"])
    return df.groupby("sector")["ticker"].apply(list).to_dict()


def get_ticker_metadata(ticker):
    """Return a dict with sector / type / description for a single ticker."""
    df = pd.read_csv(_CSV_PATH)
    row = df[df["ticker"] == ticker]
    if row.empty:
        return {}
    return row.iloc[0].to_dict()


def get_dividend_candidate_tickers():
    """
    Return tickers from classic dividend-paying sectors:
    Consumer Staples, Utilities, Financials, Energy,
    Healthcare, Industrials, Real Estate.
    """
    div_sectors = [
        "Consumer Staples", "Utilities", "Financials",
        "Energy", "Healthcare", "Industrials", "Real Estate",
    ]
    return get_universe(sectors=div_sectors, instrument_types=["Stock"])["ticker"].tolist()
