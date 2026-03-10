"""
tests/test_sector_predictor.py – Unit tests for core.sector_predictor.
"""

import numpy as np
import pandas as pd
import pytest

from core.sector_predictor import (
    _compute_bottom_up_scores,
    _compute_etf_technical_scores,
    _compute_macro_overlay,
    predict_sectors,
    get_sector_summary,
    SECTOR_ETF,
    REGIME_BIAS,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

def _make_signals(n_per_sector=5, seed=42):
    """Create a synthetic signals DataFrame covering all sectors."""
    rng = np.random.default_rng(seed)
    rows = []
    sectors = list(SECTOR_ETF.keys())
    for sector in sectors:
        for i in range(n_per_sector):
            ticker = f"{sector[:3].upper()}{i}"
            rows.append({
                "ticker":            ticker,
                "sector":            sector,
                "instrument_type":   "Stock",
                "composite_score":   float(rng.uniform(-5, 5)),
                "tech_score":        float(rng.uniform(-5, 5)),
                "fund_score":        float(rng.uniform(-5, 5)),
                "sentiment_score":   float(rng.uniform(-3, 3)),
                "insider_score":     float(rng.uniform(-2, 2)),
                "market_cap_B":      float(rng.uniform(10, 500)),
                "earnings_imminent": bool(rng.integers(0, 2)),
                "rsi":               float(rng.uniform(30, 70)),
            })
    return pd.DataFrame(rows)


def _make_macro_close(n=252, seed=7):
    """Synthetic Close price DataFrame for macro tickers."""
    rng    = np.random.default_rng(seed)
    tickers = ["^VIX", "SPY"] + list(SECTOR_ETF.values())
    idx    = pd.date_range("2024-01-01", periods=n, freq="B")
    data   = {}
    for t in tickers:
        start = 100 if t != "^VIX" else 18
        data[t] = start * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
    return pd.DataFrame(data, index=idx)


def _make_macro_sentiment(regime="RISK-ON"):
    return {
        "macro_sentiment": f"{regime} 🟢",
        "vix": 17.0,
        "vix_label": "CALM",
        "spy_trend": "BULL MARKET (above 200-SMA)",
        "breadth_pct": 72.0,
        "macro_score": 4,
    }


# ── Bottom-up layer ────────────────────────────────────────────────────────

class TestBottomUpScores:
    def test_returns_dataframe(self):
        df = _compute_bottom_up_scores(_make_signals())
        assert isinstance(df, pd.DataFrame)

    def test_one_row_per_sector(self):
        signals = _make_signals(n_per_sector=4)
        df = _compute_bottom_up_scores(signals)
        assert len(df) == df["sector"].nunique()
        assert df["sector"].nunique() == len(SECTOR_ETF)

    def test_score_bounded(self):
        df = _compute_bottom_up_scores(_make_signals())
        assert (df["bottom_up_score"] >= -10).all()
        assert (df["bottom_up_score"] <=  10).all()

    def test_required_columns(self):
        df = _compute_bottom_up_scores(_make_signals())
        for col in ["sector", "ticker_count", "avg_composite",
                    "pct_bullish", "pct_bearish", "bottom_up_score"]:
            assert col in df.columns

    def test_high_bullish_sector_positive_score(self):
        rows = [{"ticker": f"T{i}", "sector": "Technology", "instrument_type": "Stock",
                 "composite_score": 4.0, "tech_score": 3.0, "fund_score": 3.0,
                 "sentiment_score": 2.0, "insider_score": 1.0, "market_cap_B": 100.0,
                 "earnings_imminent": False}
                for i in range(10)]
        df = _compute_bottom_up_scores(pd.DataFrame(rows))
        tech = df[df["sector"] == "Technology"]["bottom_up_score"].values[0]
        assert tech > 0

    def test_high_bearish_sector_negative_score(self):
        rows = [{"ticker": f"T{i}", "sector": "Energy", "instrument_type": "Stock",
                 "composite_score": -4.0, "tech_score": -3.0, "fund_score": -3.0,
                 "sentiment_score": -2.0, "insider_score": -1.0, "market_cap_B": 50.0,
                 "earnings_imminent": False}
                for i in range(10)]
        df = _compute_bottom_up_scores(pd.DataFrame(rows))
        energy = df[df["sector"] == "Energy"]["bottom_up_score"].values[0]
        assert energy < 0

    def test_empty_signals_returns_empty(self):
        df = _compute_bottom_up_scores(pd.DataFrame())
        assert df.empty


# ── ETF technical layer ────────────────────────────────────────────────────

class TestEtfTechnicalScores:
    def test_returns_dataframe(self):
        df = _compute_etf_technical_scores(_make_macro_close())
        assert isinstance(df, pd.DataFrame)

    def test_covers_all_sectors(self):
        df = _compute_etf_technical_scores(_make_macro_close())
        assert set(df["sector"]) == set(SECTOR_ETF.keys())

    def test_score_bounded(self):
        df = _compute_etf_technical_scores(_make_macro_close())
        assert (df["etf_tech_score"] >= -10).all()
        assert (df["etf_tech_score"] <=  10).all()

    def test_required_columns(self):
        df = _compute_etf_technical_scores(_make_macro_close())
        for col in ["sector", "etf", "mom_1m_pct", "mom_3m_pct",
                    "vs_spy_1m_pct", "rsi", "etf_tech_score"]:
            assert col in df.columns

    def test_empty_close_returns_empty(self):
        df = _compute_etf_technical_scores(pd.DataFrame())
        assert df.empty


# ── Macro overlay layer ────────────────────────────────────────────────────

class TestMacroOverlay:
    def test_risk_on_favours_technology(self):
        df = _compute_macro_overlay(_make_macro_sentiment("RISK-ON"), list(SECTOR_ETF.keys()))
        tech  = df[df["sector"] == "Technology"]["macro_regime_score"].values[0]
        utils = df[df["sector"] == "Utilities"]["macro_regime_score"].values[0]
        assert tech > 0
        assert utils < 0

    def test_risk_off_favours_defensives(self):
        df = _compute_macro_overlay(_make_macro_sentiment("RISK-OFF"), list(SECTOR_ETF.keys()))
        staples = df[df["sector"] == "Consumer Staples"]["macro_regime_score"].values[0]
        utils   = df[df["sector"] == "Utilities"]["macro_regime_score"].values[0]
        tech    = df[df["sector"] == "Technology"]["macro_regime_score"].values[0]
        assert staples > 0
        assert utils   > 0
        assert tech    < 0

    def test_score_bounded(self):
        df = _compute_macro_overlay(_make_macro_sentiment(), list(SECTOR_ETF.keys()))
        assert (df["macro_regime_score"] >= -10).all()
        assert (df["macro_regime_score"] <=  10).all()

    def test_neutral_all_zeros(self):
        df = _compute_macro_overlay({"macro_sentiment": "NEUTRAL"}, list(SECTOR_ETF.keys()))
        assert (df["macro_regime_score"] == 0).all()


# ── Full predict_sectors ───────────────────────────────────────────────────

class TestPredictSectors:
    def test_returns_dataframe(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_sorted_descending(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        scores = df["sector_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_required_columns(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        for col in ["sector", "sector_score", "signal", "rotation_call",
                    "top_picks", "risk_factors"]:
            assert col in df.columns

    def test_signal_labels_valid(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        valid = {"🟢 STRONG OVERWEIGHT", "🟢 OVERWEIGHT", "⚪ NEUTRAL",
                 "🔴 UNDERWEIGHT", "🔴 STRONG UNDERWEIGHT"}
        for sig in df["signal"]:
            assert sig in valid

    def test_rotation_calls_valid(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        valid = {"🚀 ROTATE IN", "⏸️  HOLD", "⚠️  ROTATE OUT"}
        for rc in df["rotation_call"]:
            assert rc in valid

    def test_top_picks_are_lists(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        for picks in df["top_picks"]:
            assert isinstance(picks, list)

    def test_risk_on_makes_tech_top_3(self):
        # In RISK-ON regime + strongly bullish tech signals, tech should rank high
        rng  = np.random.default_rng(0)
        rows = [{"ticker": f"T{i}", "sector": "Technology", "instrument_type": "Stock",
                 "composite_score": 5.0, "tech_score": 5.0, "fund_score": 5.0,
                 "sentiment_score": 3.0, "insider_score": 2.0, "market_cap_B": 500.0,
                 "earnings_imminent": True}
                for i in range(10)]
        # add weak signals for all other sectors
        for sec in SECTOR_ETF:
            if sec == "Technology":
                continue
            for i in range(5):
                rows.append({"ticker": f"{sec[:2]}{i}", "sector": sec,
                             "instrument_type": "Stock", "composite_score": -3.0,
                             "tech_score": -3.0, "fund_score": -3.0,
                             "sentiment_score": -2.0, "insider_score": -1.0,
                             "market_cap_B": 20.0, "earnings_imminent": False})
        df = predict_sectors(pd.DataFrame(rows), _make_macro_close(), _make_macro_sentiment("RISK-ON"))
        top3 = df.head(3)["sector"].tolist()
        assert "Technology" in top3

    def test_empty_signals_still_returns_etf_based_rankings(self):
        df = predict_sectors(pd.DataFrame(), _make_macro_close(), _make_macro_sentiment())
        assert not df.empty  # ETF layer + macro layer should still produce output


# ── get_sector_summary ─────────────────────────────────────────────────────

class TestGetSectorSummary:
    def test_returns_dict(self):
        df  = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        s   = get_sector_summary(df)
        assert isinstance(s, dict)

    def test_has_required_keys(self):
        df = predict_sectors(_make_signals(), _make_macro_close(), _make_macro_sentiment())
        s  = get_sector_summary(df)
        for key in ["top_sector", "top_signal", "top_score",
                    "bottom_sector", "rotate_in_sectors", "rotate_out_sectors"]:
            assert key in s

    def test_empty_returns_empty_dict(self):
        assert get_sector_summary(pd.DataFrame()) == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])