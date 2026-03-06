import os
import sys

# ensure the repository root is on the import path so that the
# `core` package can be imported when pytest runs from the tests/ directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import pytest

from core import data_fetcher


class DummyTicker:
    def __init__(self, ticker):
        self._ticker = ticker

    @property
    def info(self):
        # always return a constant price so that we can assert on it
        return {"regularMarketPrice": 123.45}


class DummyTickerNoPrice:
    def __init__(self, ticker):
        self._ticker = ticker

    @property
    def info(self):
        # simulate missing data
        return {}


def test_fetch_prices_empty(monkeypatch):
    # empty list should give empty DataFrame with correct columns
    df = data_fetcher.fetch_prices([])
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == ["ticker", "price"]


def test_fetch_prices_single_string(monkeypatch):
    # passing a string should be treated as a list of one ticker
    monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
    df = data_fetcher.fetch_prices("AAPL")
    assert not df.empty
    assert df.iloc[0].ticker == "AAPL"
    assert df.iloc[0].price == 123.45


def test_fetch_prices_iterable(monkeypatch):
    monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
    tickers = ("GOOG", "MSFT")  # tuple to ensure casting works
    df = data_fetcher.fetch_prices(tickers)
    assert list(df.ticker) == ["GOOG", "MSFT"]


def test_fetch_prices_all_none(monkeypatch):
    monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTickerNoPrice)
    df = data_fetcher.fetch_prices(["X", "Y"])
    assert df.empty, "should return empty DataFrame when no prices are available"


def test_fetch_prices_invalid_type(monkeypatch):
    # passing a non-iterable object should not crash
    monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
    df = data_fetcher.fetch_prices(42)
    assert not df.empty
    assert df.iloc[0].ticker == 42


if __name__ == "__main__":
    pytest.main([__file__])
