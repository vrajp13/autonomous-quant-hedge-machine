"""
tests/test_universe.py – Unit tests for core.universe dynamic universe.

All Wikipedia fetches are mocked so tests pass in CI without network.
"""

import io
import pandas as pd
import pytest

import core.universe as univ


# ── Fixtures ───────────────────────────────────────────────────────────────

SP500_HTML = """
<table class="wikitable">
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
<tr><td>AAPL</td><td>Apple Inc.</td><td>Information Technology</td><td>Tech Hardware</td></tr>
<tr><td>MSFT</td><td>Microsoft Corp.</td><td>Information Technology</td><td>Systems Software</td></tr>
<tr><td>JPM</td><td>JPMorgan Chase</td><td>Financials</td><td>Diversified Banks</td></tr>
<tr><td>JNJ</td><td>Johnson &amp; Johnson</td><td>Health Care</td><td>Pharmaceuticals</td></tr>
<tr><td>XOM</td><td>Exxon Mobil</td><td>Energy</td><td>Integrated Oil &amp; Gas</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td><td>Multi-Sector Holdings</td></tr>
</table>
"""

NQ100_HTML = """
<table class="wikitable">
<tr><th>Ticker</th><th>Company</th><th>Sector</th></tr>
<tr><td>NVDA</td><td>NVIDIA</td><td>Information Technology</td></tr>
<tr><td>AAPL</td><td>Apple</td><td>Information Technology</td></tr>
</table>
"""


def _make_sp500_df():
    """Build the S&P 500 DataFrame from mock HTML."""
    return pd.DataFrame([
        {"Symbol": "AAPL", "Security": "Apple Inc.", "GICS Sector": "Information Technology", "GICS Sub-Industry": "Tech Hardware"},
        {"Symbol": "MSFT", "Security": "Microsoft Corp.", "GICS Sector": "Information Technology", "GICS Sub-Industry": "Systems Software"},
        {"Symbol": "JPM", "Security": "JPMorgan Chase", "GICS Sector": "Financials", "GICS Sub-Industry": "Diversified Banks"},
        {"Symbol": "JNJ", "Security": "Johnson & Johnson", "GICS Sector": "Health Care", "GICS Sub-Industry": "Pharmaceuticals"},
        {"Symbol": "XOM", "Security": "Exxon Mobil", "GICS Sector": "Energy", "GICS Sub-Industry": "Integrated Oil & Gas"},
        {"Symbol": "BRK.B", "Security": "Berkshire Hathaway", "GICS Sector": "Financials", "GICS Sub-Industry": "Multi-Sector Holdings"},
    ])


def _make_nq100_df():
    """Build the Nasdaq-100 DataFrame from mock HTML."""
    return pd.DataFrame([
        {"Ticker": "NVDA", "Company": "NVIDIA", "Sector": "Information Technology"},
        {"Ticker": "AAPL", "Company": "Apple", "Sector": "Information Technology"},
    ])


# ── GICS mapping ───────────────────────────────────────────────────────────

class TestGicsMapping:
    def test_it_maps_known_gics(self):
        assert univ.GICS_MAP["Information Technology"] == "Technology"
        assert univ.GICS_MAP["Health Care"]            == "Healthcare"
        assert univ.GICS_MAP["Consumer Discretionary"] == "Consumer Discretionary"

    def test_all_11_gics_sectors_covered(self):
        assert len(univ.GICS_MAP) == 11


# ── _fetch_sp500 ───────────────────────────────────────────────────────────

class TestFetchSP500:
    def test_returns_dataframe(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_sp500_df()])
        df = univ._fetch_sp500()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_contains_required_columns(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_sp500_df()])
        df = univ._fetch_sp500()
        for col in ["ticker", "sector", "instrument_type", "description"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_gics_normalised(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_sp500_df()])
        df = univ._fetch_sp500()
        # 'Information Technology' must become 'Technology'
        tech_row = df[df["ticker"] == "AAPL"]
        assert tech_row["sector"].values[0] == "Technology"

    def test_brk_b_dot_converted(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_sp500_df()])
        df = univ._fetch_sp500()
        tickers = df["ticker"].tolist()
        assert "BRK-B" in tickers
        assert "BRK.B" not in tickers

    def test_all_stocks_type(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_sp500_df()])
        df = univ._fetch_sp500()
        assert (df["instrument_type"] == "Stock").all()

    def test_network_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: (_ for _ in ()).throw(Exception("net err")))
        df = univ._fetch_sp500()
        assert df.empty


# ── _fetch_nasdaq100 ───────────────────────────────────────────────────────

class TestFetchNasdaq100:
    def test_returns_dataframe(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: [_make_nq100_df()])
        df = univ._fetch_nasdaq100()
        assert isinstance(df, pd.DataFrame)

    def test_network_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(univ.pd, "read_html", lambda *a, **k: (_ for _ in ()).throw(Exception("net err")))
        df = univ._fetch_nasdaq100()
        assert df.empty


# ── get_universe ───────────────────────────────────────────────────────────

class TestGetUniverse:
    def _patch(self, monkeypatch):
        monkeypatch.setattr(univ, "_fetch_sp500",    lambda: pd.DataFrame([
            {"ticker": "AAPL", "sector": "Technology",  "instrument_type": "Stock", "description": "Apple"},
            {"ticker": "JPM",  "sector": "Financials",  "instrument_type": "Stock", "description": "JPMorgan"},
            {"ticker": "JNJ",  "sector": "Healthcare",  "instrument_type": "Stock", "description": "J&J"},
        ]))
        monkeypatch.setattr(univ, "_fetch_nasdaq100", lambda: pd.DataFrame([
            {"ticker": "NVDA", "sector": "Technology",  "instrument_type": "Stock", "description": "NVIDIA"},
            {"ticker": "AAPL", "sector": "Technology",  "instrument_type": "Stock", "description": "Apple"},  # dup
        ]))
        univ.invalidate_cache()

    def test_deduplication(self, monkeypatch):
        self._patch(monkeypatch)
        df = univ.get_universe(use_cache=False)
        # AAPL appears in S&P500 AND Nasdaq-100 — must appear only once
        assert df["ticker"].value_counts()["AAPL"] == 1

    def test_supplement_added(self, monkeypatch):
        self._patch(monkeypatch)
        df = univ.get_universe(use_cache=False)
        assert "SPY" in df["ticker"].values
        assert "GLD" in df["ticker"].values
        assert "^VIX" in df["ticker"].values

    def test_sector_filter(self, monkeypatch):
        self._patch(monkeypatch)
        df = univ.get_universe(sectors=["Technology"], use_cache=False)
        assert set(df[df["instrument_type"] == "Stock"]["sector"].unique()) <= {"Technology"}

    def test_instrument_type_filter(self, monkeypatch):
        self._patch(monkeypatch)
        df = univ.get_universe(instrument_types=["Stock"], use_cache=False)
        assert (df["instrument_type"] == "Stock").all()

    def test_fallback_used_on_total_failure(self, monkeypatch):
        monkeypatch.setattr(univ, "_fetch_sp500",    lambda: pd.DataFrame())
        monkeypatch.setattr(univ, "_fetch_nasdaq100", lambda: pd.DataFrame())
        import os, tempfile, pandas as pd2
        fallback_data = pd2.DataFrame([
            {"ticker": "FALLBACK", "sector": "Tech", "instrument_type": "Stock", "description": "x"}
        ])
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            fallback_data.to_csv(f, index=False)
            tmp = f.name
        monkeypatch.setattr(univ, "_CSV_FALLBACK", tmp)
        univ.invalidate_cache()
        df = univ.get_universe(use_cache=False)
        assert "FALLBACK" in df["ticker"].values
        os.unlink(tmp)

    def test_caching(self, monkeypatch):
        call_count = {"n": 0}
        original = univ._fetch_sp500
        def counted():
            call_count["n"] += 1
            return pd.DataFrame([{"ticker":"AAPL","sector":"Technology","instrument_type":"Stock","description":""}])
        monkeypatch.setattr(univ, "_fetch_sp500",    counted)
        monkeypatch.setattr(univ, "_fetch_nasdaq100", lambda: pd.DataFrame())
        univ.invalidate_cache()
        univ.get_universe(use_cache=True)
        univ.get_universe(use_cache=True)
        assert call_count["n"] == 1   # second call used cache


# ── helpers ────────────────────────────────────────────────────────────────

class TestHelpers:
    def _patch(self, monkeypatch):
        monkeypatch.setattr(univ, "_fetch_sp500", lambda: pd.DataFrame([
            {"ticker": "AAPL", "sector": "Technology", "instrument_type": "Stock", "description": ""},
            {"ticker": "JPM",  "sector": "Financials", "instrument_type": "Stock", "description": ""},
            {"ticker": "JNJ",  "sector": "Healthcare",  "instrument_type": "Stock", "description": ""},
            {"ticker": "KO",   "sector": "Consumer Staples", "instrument_type": "Stock", "description": ""},
        ]))
        monkeypatch.setattr(univ, "_fetch_nasdaq100", lambda: pd.DataFrame())
        univ.invalidate_cache()

    def test_get_stock_tickers_no_etfs(self, monkeypatch):
        self._patch(monkeypatch)
        tickers = univ.get_stock_tickers()
        assert "SPY"   not in tickers
        assert "AAPL"  in tickers

    def test_get_dividend_candidates(self, monkeypatch):
        self._patch(monkeypatch)
        tickers = univ.get_dividend_candidate_tickers()
        # Consumer Staples and Healthcare are dividend sectors
        assert "KO"  in tickers
        assert "JNJ" in tickers

    def test_get_universe_stats(self, monkeypatch):
        self._patch(monkeypatch)
        stats = univ.get_universe_stats()
        assert "total_stocks" in stats
        assert "sectors"      in stats
        assert stats["total_stocks"] >= 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])