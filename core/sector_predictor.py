"""
sector_predictor.py – Three-layer sector prediction engine.

Produces a ranked sector scorecard combining:

  LAYER 1 – Bottom-up (40%):
    Aggregates individual stock signals within each sector.
    Market-cap-weighted composite score, % bullish/bearish tickers,
    avg RSI, sentiment, insider activity, earnings catalyst density.

  LAYER 2 – Top-down ETF technicals (35%):
    Sector ETF momentum (1m, 3m, 6m), RSI, relative strength vs SPY
    (alpha), position vs 50/200-SMA, volume surge (institutional flow).

  LAYER 3 – Macro regime overlay (25%):
    Adjusts sector scores based on VIX level, SPY trend, and the
    classic late/mid/early cycle sector rotation playbook.

Final output per sector:
    sector_score  : −10 → +10
    signal        : STRONG OVERWEIGHT / OVERWEIGHT / NEUTRAL /
                    UNDERWEIGHT / STRONG UNDERWEIGHT
    rotation_call : ROTATE IN / HOLD / ROTATE OUT
    top_picks     : best 3 stock tickers in that sector
    risk_factors  : concise risk summary string
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Weights ────────────────────────────────────────────────────────────────
W_BOTTOM_UP  = 0.40
W_ETF_TECH   = 0.35
W_MACRO      = 0.25

# ── Sector ETF map ─────────────────────────────────────────────────────────
SECTOR_ETF = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Healthcare":             "XLV",
    "Energy":                 "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Materials":              "XLB",
    "Communication Services": "XLC",
}

# ── Macro regime cycle preferences ────────────────────────────────────────
# Score adjustment per sector per regime (−3 → +3)
REGIME_BIAS = {
    "RISK-ON": {
        "Technology": 2, "Consumer Discretionary": 2, "Financials": 1,
        "Industrials": 1, "Materials": 1, "Communication Services": 1,
        "Consumer Staples": -1, "Utilities": -2, "Real Estate": -1,
        "Healthcare": 0, "Energy": 0,
    },
    "MILDLY BULLISH": {
        "Technology": 1, "Consumer Discretionary": 1, "Financials": 1,
        "Industrials": 1, "Materials": 0, "Communication Services": 0,
        "Consumer Staples": 0, "Utilities": -1, "Real Estate": 0,
        "Healthcare": 0, "Energy": 0,
    },
    "NEUTRAL": {
        s: 0 for s in SECTOR_ETF
    },
    "MILDLY BEARISH": {
        "Technology": -1, "Consumer Discretionary": -1, "Financials": -1,
        "Industrials": -1, "Materials": -1, "Communication Services": 0,
        "Consumer Staples": 1, "Utilities": 2, "Real Estate": 0,
        "Healthcare": 1, "Energy": 0,
    },
    "RISK-OFF": {
        "Technology": -2, "Consumer Discretionary": -2, "Financials": -1,
        "Industrials": -2, "Materials": -2, "Communication Services": -1,
        "Consumer Staples": 3, "Utilities": 3, "Real Estate": 1,
        "Healthcare": 2, "Energy": -1,
    },
}

# ── Risk factor descriptions ───────────────────────────────────────────────
SECTOR_RISKS = {
    "Technology":             "Valuation multiple compression in rate-rise environments; AI capex cycle risk",
    "Financials":             "Credit cycle risk; NIM compression if rates fall faster than expected",
    "Healthcare":             "Drug pricing regulatory risk; patent cliff exposure for large pharma",
    "Energy":                 "Oil price volatility; OPEC+ policy shifts; energy transition headwinds",
    "Consumer Discretionary": "Consumer spending slowdown; credit card delinquency rising; high beta",
    "Consumer Staples":       "Input cost inflation; private-label competition; slow growth ceiling",
    "Industrials":            "Supply chain normalization; government contract timing risk; FX exposure",
    "Utilities":              "Rate sensitivity (bond proxy); high debt loads; permitting delays for renewables",
    "Real Estate":            "Rate sensitivity; office vacancy crisis; cap-rate expansion risk",
    "Materials":              "China demand sensitivity; commodity price cycles; USD strength headwinds",
    "Communication Services": "Ad spend cyclicality; streaming saturation; regulatory antitrust risk",
}


# ── RSI helper ─────────────────────────────────────────────────────────────

def _rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    rsi   = rsi.where(loss != 0, other=gain.apply(lambda g: 100.0 if g > 0 else 50.0))
    return rsi


# ── Layer 1: Bottom-up stock signal aggregation ────────────────────────────

def _compute_bottom_up_scores(signals_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate ticker-level signals into sector-level scores.

    Returns DataFrame with one row per sector:
        sector, ticker_count, avg_composite, pct_bullish, pct_bearish,
        avg_tech_score, avg_fund_score, avg_sentiment, avg_insider,
        earnings_catalysts, mktcap_weighted_score, bottom_up_score
    """
    if signals_df is None or signals_df.empty or "sector" not in signals_df.columns:
        return pd.DataFrame()

    # Only stock-level signals (exclude ETF rows that slipped in)
    df = signals_df[signals_df.get("instrument_type", "Stock") != "ETF"].copy()
    df = df[df["sector"].notna() & (df["sector"] != "")]

    results = []
    for sector, grp in df.groupby("sector"):
        n = len(grp)
        if n == 0:
            continue

        avg_comp  = grp["composite_score"].mean()
        pct_bull  = (grp["composite_score"] > 1).mean() * 100
        pct_bear  = (grp["composite_score"] < -1).mean() * 100

        avg_tech  = grp["tech_score"].mean() if "tech_score" in grp else 0
        avg_fund  = grp["fund_score"].mean() if "fund_score" in grp else 0
        avg_sent  = grp["sentiment_score"].mean() if "sentiment_score" in grp else 0
        avg_ins   = grp["insider_score"].mean() if "insider_score" in grp else 0
        earn_cat  = int(grp["earnings_imminent"].sum()) if "earnings_imminent" in grp else 0

        # Market-cap-weighted composite (large caps dominate sector moves)
        if "market_cap_B" in grp.columns and grp["market_cap_B"].notna().any():
            caps     = grp["market_cap_B"].fillna(1.0).clip(lower=0.1)
            mw_score = float(np.average(grp["composite_score"], weights=caps))
        else:
            mw_score = avg_comp

        # Bottom-up sector score (−10 → +10)
        bu_score = 0.0
        # Signal breadth (% bullish vs % bearish)
        breadth = (pct_bull - pct_bear) / 100    # −1 → +1
        bu_score += breadth * 4

        # Market-cap weighted composite (larger weight)
        bu_score += mw_score * 0.5

        # Insider activity
        bu_score += avg_ins * 0.3

        # Earnings catalyst density (many imminent earnings → vol + opportunity)
        if n > 0:
            catalyst_density = earn_cat / n
            bu_score += catalyst_density * 1.5

        bu_score = max(-10, min(10, bu_score))

        results.append({
            "sector":               sector,
            "ticker_count":         n,
            "avg_composite":        round(avg_comp, 3),
            "pct_bullish":          round(pct_bull, 1),
            "pct_bearish":          round(pct_bear, 1),
            "avg_tech_score":       round(avg_tech, 2),
            "avg_fund_score":       round(avg_fund, 2),
            "avg_sentiment":        round(avg_sent, 2),
            "avg_insider_score":    round(avg_ins, 2),
            "earnings_catalysts":   earn_cat,
            "mktcap_weighted_score":round(mw_score, 3),
            "bottom_up_score":      round(bu_score, 3),
        })

    return pd.DataFrame(results)


# ── Layer 2: Sector ETF technical scoring ──────────────────────────────────

def _compute_etf_technical_scores(macro_close: pd.DataFrame) -> pd.DataFrame:
    """
    Score each sector using its ETF's price data.

    Returns DataFrame with one row per sector:
        sector, etf, mom_1m, mom_3m, mom_6m, rsi, vs_spy_1m,
        above_50sma, above_200sma, etf_tech_score
    """
    if macro_close is None or macro_close.empty:
        return pd.DataFrame()

    spy_series = macro_close["SPY"].dropna() if "SPY" in macro_close.columns else None
    results    = []

    for sector, etf in SECTOR_ETF.items():
        if etf not in macro_close.columns:
            continue
        s = macro_close[etf].dropna()
        if len(s) < 21:
            continue

        curr    = float(s.iloc[-1])
        mom_1m  = (curr / float(s.iloc[-21]) - 1) if len(s) >= 21 else 0.0
        mom_3m  = (curr / float(s.iloc[-63]) - 1) if len(s) >= 63 else mom_1m
        mom_6m  = (curr / float(s.iloc[-126])- 1) if len(s) >= 126 else mom_3m

        rsi_val = float(_rsi(s, 14).iloc[-1]) if len(s) >= 28 else 50.0

        sma50_val  = float(s.rolling(50).mean().iloc[-1])  if len(s) >= 50  else None
        sma200_val = float(s.rolling(200).mean().iloc[-1]) if len(s) >= 200 else None
        above_50   = curr > sma50_val  if sma50_val  else False
        above_200  = curr > sma200_val if sma200_val else False

        # Relative strength vs SPY
        vs_spy_1m = 0.0
        if spy_series is not None and len(spy_series) >= 21:
            spy_ret   = float(spy_series.iloc[-1]) / float(spy_series.iloc[-21]) - 1
            vs_spy_1m = mom_1m - spy_ret   # positive = outperforming market

        # Score assembly
        score = 0.0

        # Momentum
        if   mom_1m >  0.05: score += 2
        elif mom_1m >  0.02: score += 1
        elif mom_1m < -0.05: score -= 2
        elif mom_1m < -0.02: score -= 1

        if   mom_3m >  0.10: score += 2
        elif mom_3m >  0.04: score += 1
        elif mom_3m < -0.10: score -= 2
        elif mom_3m < -0.04: score -= 1

        if   mom_6m >  0.15: score += 1.5
        elif mom_6m >  0.06: score += 0.5
        elif mom_6m < -0.15: score -= 1.5
        elif mom_6m < -0.06: score -= 0.5

        # Relative strength (alpha vs SPY)
        if   vs_spy_1m >  0.03: score += 2
        elif vs_spy_1m >  0.01: score += 1
        elif vs_spy_1m < -0.03: score -= 2
        elif vs_spy_1m < -0.01: score -= 1

        # RSI (sector-level overbought/oversold)
        if   rsi_val <= 30: score += 2     # oversold = opportunity
        elif rsi_val <= 40: score += 1
        elif rsi_val >= 75: score -= 2
        elif rsi_val >= 65: score -= 1

        # SMA trend
        if above_200: score += 1
        if above_50:  score += 0.5

        score = max(-10, min(10, score))

        results.append({
            "sector":        sector,
            "etf":           etf,
            "mom_1m_pct":    round(mom_1m * 100, 2),
            "mom_3m_pct":    round(mom_3m * 100, 2),
            "mom_6m_pct":    round(mom_6m * 100, 2),
            "rsi":           round(rsi_val, 1),
            "vs_spy_1m_pct": round(vs_spy_1m * 100, 2),
            "above_50sma":   above_50,
            "above_200sma":  above_200,
            "etf_tech_score":round(score, 3),
        })

    return pd.DataFrame(results)


# ── Layer 3: Macro regime overlay ──────────────────────────────────────────

def _compute_macro_overlay(macro_sentiment: dict, sector_names: list) -> pd.DataFrame:
    """
    Apply the macro regime bias to each sector.

    Returns DataFrame: sector, macro_regime_score
    """
    raw_sentiment = macro_sentiment.get("macro_sentiment", "NEUTRAL")

    # Strip emoji to get clean key
    regime_key = "NEUTRAL"
    for key in REGIME_BIAS:
        if key in raw_sentiment:
            regime_key = key
            break

    bias_table = REGIME_BIAS.get(regime_key, REGIME_BIAS["NEUTRAL"])

    results = []
    for sector in sector_names:
        raw_bias    = bias_table.get(sector, 0)
        macro_score = raw_bias * (10 / 3)   # scale −3→+3 to −10→+10
        macro_score = max(-10, min(10, macro_score))
        results.append({"sector": sector, "macro_regime_score": round(macro_score, 2)})

    return pd.DataFrame(results)


# ── Top picks extraction ───────────────────────────────────────────────────

def _get_top_picks(signals_df: pd.DataFrame, sector: str, n: int = 3) -> list:
    """Return the n best ticker symbols within a sector."""
    if signals_df is None or signals_df.empty or "sector" not in signals_df.columns:
        return []
    grp = signals_df[signals_df["sector"] == sector]
    grp = grp[grp["composite_score"] > 0]
    grp = grp.sort_values("composite_score", ascending=False)
    return grp["ticker"].head(n).tolist()


# ── Main public function ────────────────────────────────────────────────────

def predict_sectors(
    signals_df: pd.DataFrame,
    macro_close: pd.DataFrame,
    macro_sentiment: dict,
) -> pd.DataFrame:
    """
    Run the three-layer sector prediction engine.

    Parameters
    ----------
    signals_df      : output of generate_signals() — ticker-level signals
    macro_close     : output of fetch_macro_close() — sector ETF prices
    macro_sentiment : output of get_market_sentiment() — VIX/SPY/breadth

    Returns
    -------
    pd.DataFrame  sorted by sector_score descending, columns:
        sector, sector_score, signal, rotation_call,
        ticker_count, pct_bullish, pct_bearish,
        avg_composite, mktcap_weighted_score,
        etf, mom_1m_pct, mom_3m_pct, mom_6m_pct,
        rsi, vs_spy_1m_pct, above_50sma, above_200sma,
        macro_regime_score, top_picks, risk_factors
    """
    logger.info("Running sector prediction (3-layer model)…")

    # Layer 1
    bu_df = _compute_bottom_up_scores(signals_df)

    # Layer 2
    etf_df = _compute_etf_technical_scores(macro_close)

    # All sectors we have coverage for
    all_sectors = set()
    if not bu_df.empty and "sector" in bu_df.columns:
        all_sectors.update(bu_df["sector"].tolist())
    if not etf_df.empty and "sector" in etf_df.columns:
        all_sectors.update(etf_df["sector"].tolist())
    all_sectors = list(all_sectors)

    # Layer 3
    macro_df = _compute_macro_overlay(macro_sentiment, all_sectors)

    # ── Merge layers ──────────────────────────────────────────────────────
    df = macro_df.copy()
    if not bu_df.empty and "sector" in bu_df.columns:
        df = df.merge(bu_df,  on="sector", how="left")
    if not etf_df.empty and "sector" in etf_df.columns:
        df = df.merge(etf_df, on="sector", how="left")

    # Fill missing scores with 0
    for col in ["bottom_up_score", "etf_tech_score", "macro_regime_score"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)
        else:
            df[col] = 0

    # ── Weighted composite ────────────────────────────────────────────────
    df["sector_score"] = (
        df["bottom_up_score"]    * W_BOTTOM_UP
        + df["etf_tech_score"]   * W_ETF_TECH
        + df["macro_regime_score"]* W_MACRO
    ).round(3)

    # ── Signal labels ─────────────────────────────────────────────────────
    def _signal(score):
        if   score >=  5:  return "🟢 STRONG OVERWEIGHT"
        elif score >=  2:  return "🟢 OVERWEIGHT"
        elif score >= -2:  return "⚪ NEUTRAL"
        elif score >= -5:  return "🔴 UNDERWEIGHT"
        else:              return "🔴 STRONG UNDERWEIGHT"

    def _rotation(score):
        if   score >=  3:  return "🚀 ROTATE IN"
        elif score >= -3:  return "⏸️  HOLD"
        else:              return "⚠️  ROTATE OUT"

    df["signal"]       = df["sector_score"].apply(_signal)
    df["rotation_call"]= df["sector_score"].apply(_rotation)

    # ── Top picks & risk factors ──────────────────────────────────────────
    if "sector" not in df.columns:
        df["sector"] = "Unknown"
    df["top_picks"]    = df["sector"].apply(
        lambda s: _get_top_picks(signals_df, s, n=3)
    )
    df["risk_factors"] = df["sector"].map(SECTOR_RISKS).fillna("General market risk")

    # ── Sort & clean ──────────────────────────────────────────────────────
    df = df.sort_values("sector_score", ascending=False).reset_index(drop=True)

    # Round numeric columns
    for col in df.select_dtypes(include="number").columns:
        df[col] = df[col].round(2)

    logger.info("Sector prediction complete. Top sector: %s",
                df.iloc[0].get("sector", "N/A") if not df.empty else "N/A")

    return df


# ── Convenience summary ────────────────────────────────────────────────────

def get_sector_summary(sector_df: pd.DataFrame) -> dict:
    """
    Return a quick summary dict for use in report headers.
    """
    if sector_df is None or sector_df.empty:
        return {}

    top    = sector_df.iloc[0]
    bottom = sector_df.iloc[-1]
    rotate_in  = sector_df[sector_df["rotation_call"].str.contains("ROTATE IN",  na=False)]
    rotate_out = sector_df[sector_df["rotation_call"].str.contains("ROTATE OUT", na=False)]

    return {
        "top_sector":         top["sector"],
        "top_signal":         top["signal"],
        "top_score":          top["sector_score"],
        "bottom_sector":      bottom["sector"],
        "bottom_signal":      bottom["signal"],
        "rotate_in_count":    len(rotate_in),
        "rotate_out_count":   len(rotate_out),
        "rotate_in_sectors":  rotate_in["sector"].tolist(),
        "rotate_out_sectors": rotate_out["sector"].tolist(),
    }