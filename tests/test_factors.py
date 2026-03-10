"""
tests/test_factors.py – Unit tests for core.factors.
"""

import numpy as np
import pandas as pd
import pytest

from core.factors import (
    _rsi, _macd, _bollinger,
    compute_technical_factors,
    compute_fundamental_factors,
    compute_earnings_factors,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_price_history(ticker, n=200, seed=42):
    rng    = np.random.default_rng(seed)
    close  = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, n))
    high   = close * 1.01
    low    = close * 0.99
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    idx    = pd.date_range("2024-01-01", periods=n, freq="B")
    data   = {
        ("Close",  ticker): close,
        ("High",   ticker): high,
        ("Low",    ticker): low,
        ("Open",   ticker): close * 0.99,
        ("Volume", ticker): volume,
    }
    df = pd.DataFrame(data, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


# ── RSI ────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rising_series_high_rsi(self):
        s   = pd.Series(np.linspace(100, 200, 60))
        rsi = _rsi(s, 14).dropna()
        assert rsi.iloc[-1] > 70

    def test_falling_series_low_rsi(self):
        s   = pd.Series(np.linspace(200, 100, 60))
        rsi = _rsi(s, 14).dropna()
        assert rsi.iloc[-1] < 30

    def test_range_0_to_100(self):
        s   = pd.Series(np.random.default_rng(0).normal(0, 1, 100).cumsum() + 100)
        rsi = _rsi(s, 14).dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()


# ── MACD ───────────────────────────────────────────────────────────────────

class TestMACD:
    def test_histogram_equals_macd_minus_signal(self):
        s = pd.Series(np.random.default_rng(1).normal(0, 1, 80).cumsum() + 100)
        macd, sig, hist = _macd(s)
        pd.testing.assert_series_equal(hist, macd - sig, check_names=False)

    def test_returns_three_same_length_series(self):
        s = pd.Series(np.linspace(100, 150, 60))
        m, g, h = _macd(s)
        assert len(m) == len(g) == len(h) == 60


# ── Bollinger ──────────────────────────────────────────────────────────────

class TestBollinger:
    def test_finite_values(self):
        s     = pd.Series(np.random.default_rng(7).normal(100, 5, 100))
        pct_b = _bollinger(s, 20).dropna()
        assert pct_b.apply(np.isfinite).all()


# ── Technical factors ──────────────────────────────────────────────────────

class TestComputeTechnicalFactors:
    def test_returns_dataframe(self):
        ph = _make_price_history("AAPL")
        df = compute_technical_factors(ph, ["AAPL"])
        assert isinstance(df, pd.DataFrame)
        assert "AAPL" in df["ticker"].values

    def test_required_columns(self):
        ph = _make_price_history("MSFT")
        df = compute_technical_factors(ph, ["MSFT"])
        for col in ["ticker", "price", "rsi", "momentum_21d_pct",
                    "tech_score", "tech_direction"]:
            assert col in df.columns, f"Missing: {col}"

    def test_score_bounded(self):
        ph = _make_price_history("TSLA", seed=99)
        df = compute_technical_factors(ph, ["TSLA"])
        assert (-10 <= df["tech_score"]).all() and (df["tech_score"] <= 10).all()

    def test_skips_short_series(self):
        ph = _make_price_history("X", n=20)
        df = compute_technical_factors(ph, ["X"])
        assert df.empty

    def test_multiple_tickers(self):
        tickers = ["AAPL", "MSFT", "GOOG"]
        frames  = [_make_price_history(t, seed=i) for i, t in enumerate(tickers)]
        ph = pd.concat(frames, axis=1)
        df = compute_technical_factors(ph, tickers)
        assert len(df) == 3


# ── Fundamental factors ────────────────────────────────────────────────────

class TestComputeFundamentalFactors:
    def _info(self, **kwargs):
        base = {
            "trailingPE": 22.0, "forwardPE": 18.0, "pegRatio": 1.2,
            "returnOnEquity": 0.25, "debtToEquity": 40.0,
            "revenueGrowth": 0.12, "earningsGrowth": 0.18,
            "profitMargins": 0.22, "marketCap": 3e12, "beta": 1.1,
            "recommendationMean": 1.8, "targetMeanPrice": 200.0,
            "regularMarketPrice": 170.0, "shortRatio": 2.0,
        }
        base.update(kwargs)
        return base

    def test_returns_dataframe(self):
        df = compute_fundamental_factors({"AAPL": self._info()})
        assert "AAPL" in df["ticker"].values

    def test_score_bounded(self):
        info = {f"T{i}": self._info() for i in range(5)}
        df   = compute_fundamental_factors(info)
        assert (-10 <= df["fund_score"]).all() and (df["fund_score"] <= 10).all()

    def test_strong_fundamentals_positive_score(self):
        info = {"GREAT": self._info(
            forwardPE=12, pegRatio=0.7, returnOnEquity=0.35,
            revenueGrowth=0.25, earningsGrowth=0.30,
            recommendationMean=1.2, targetMeanPrice=220.0
        )}
        df = compute_fundamental_factors(info)
        assert df.loc[df["ticker"] == "GREAT", "fund_score"].values[0] > 5

    def test_empty_info_skipped(self):
        df = compute_fundamental_factors({"EMPTY": {}, "GOOD": self._info()})
        assert "EMPTY" not in df["ticker"].values
        assert "GOOD"  in  df["ticker"].values


# ── Earnings proximity ─────────────────────────────────────────────────────

class TestComputeEarningsFactors:
    def test_imminent_detection(self):
        from datetime import date, timedelta
        today = date.today()
        em = {
            "NEAR": {"earnings_date": today + timedelta(days=7)},
            "FAR":  {"earnings_date": today + timedelta(days=60)},
            "NONE": {"earnings_date": None},
        }
        df = compute_earnings_factors(em)
        assert df.loc[df["ticker"] == "NEAR", "earnings_imminent"].values[0] == True
        assert df.loc[df["ticker"] == "FAR",  "earnings_imminent"].values[0] == False
        assert df.loc[df["ticker"] == "NONE", "earnings_imminent"].values[0] == False

    def test_all_tickers_present(self):
        em = {"A": {"earnings_date": None}, "B": {"earnings_date": None}}
        df = compute_earnings_factors(em)
        assert set(df["ticker"]) == {"A", "B"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])