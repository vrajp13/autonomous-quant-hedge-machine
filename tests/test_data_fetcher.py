"""
tests/test_data_fetcher.py – Unit tests for core.data_fetcher.
"""

import pandas as pd
import pytest
from core import data_fetcher


# ── Fakes ──────────────────────────────────────────────────────────────────

class DummyTicker:
    def __init__(self, ticker):
        self._ticker = ticker

    @property
    def info(self):
        return {"regularMarketPrice": 123.45, "marketCap": 3e12, "forwardPE": 25.0}

    @property
    def news(self):
        return [{"title": "Record earnings beat estimates", "providerPublishTime": 9999999999}]

    @property
    def calendar(self):
        return None

    @property
    def insider_transactions(self):
        return pd.DataFrame()


class DummyTickerNoPrice:
    def __init__(self, ticker):
        pass

    @property
    def info(self):
        return {}

    @property
    def news(self):
        return []

    @property
    def calendar(self):
        return None

    @property
    def insider_transactions(self):
        return pd.DataFrame()


# ── fetch_prices (legacy shim) ─────────────────────────────────────────────

class TestFetchPricesLegacy:
    def test_empty_list(self):
        df = data_fetcher.fetch_prices([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert list(df.columns) == ["ticker", "price"]

    def test_single_string(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        df = data_fetcher.fetch_prices("AAPL")
        assert not df.empty
        assert df.iloc[0]["ticker"] == "AAPL"
        assert df.iloc[0]["price"]  == 123.45

    def test_tuple_iterable(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        df = data_fetcher.fetch_prices(("GOOG", "MSFT"))
        assert list(df["ticker"]) == ["GOOG", "MSFT"]

    def test_all_missing_price(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTickerNoPrice)
        df = data_fetcher.fetch_prices(["X", "Y"])
        assert df.empty

    def test_non_iterable_input(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        df = data_fetcher.fetch_prices(42)
        assert not df.empty
        assert df.iloc[0]["ticker"] == 42

    def test_none_input(self):
        df = data_fetcher.fetch_prices(None)
        assert df.empty


# ── fetch_ticker_info ──────────────────────────────────────────────────────

class TestFetchTickerInfo:
    def test_returns_dict(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        result = data_fetcher.fetch_ticker_info("AAPL")
        assert isinstance(result, dict)

    def test_known_field_present(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        result = data_fetcher.fetch_ticker_info("AAPL")
        assert result["regularMarketPrice"] == 123.45

    def test_error_returns_empty_dict(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: (_ for _ in ()).throw(RuntimeError("err")))
        result = data_fetcher.fetch_ticker_info("BAD")
        assert result == {}


# ── fetch_news ─────────────────────────────────────────────────────────────

class TestFetchNews:
    def test_returns_list(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        news = data_fetcher.fetch_news("AAPL")
        assert isinstance(news, list)

    def test_max_items_respected(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        news = data_fetcher.fetch_news("AAPL", max_items=1)
        assert len(news) <= 1

    def test_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: (_ for _ in ()).throw(RuntimeError("err")))
        assert data_fetcher.fetch_news("BAD") == []


# ── fetch_upcoming_earnings ────────────────────────────────────────────────

class TestFetchUpcomingEarnings:
    def test_returns_dict_with_key(self, monkeypatch):
        monkeypatch.setattr(data_fetcher.yf, "Ticker", DummyTicker)
        result = data_fetcher.fetch_upcoming_earnings("AAPL")
        assert "earnings_date" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])