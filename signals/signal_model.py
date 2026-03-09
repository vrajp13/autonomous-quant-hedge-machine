"""
signal_model.py – Multi-factor signal synthesis.

Combines technical, fundamental, sentiment, earnings, and insider scores
into a single composite signal for each ticker.

Weight allocation:
    Technical   : 35%
    Fundamental : 30%
    Sentiment   : 15%
    Insider     : 15%
    Earnings    :  5%  (binary proximity boost)
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

WEIGHTS = {
    "tech":      0.35,
    "fund":      0.30,
    "sentiment": 0.15,
    "insider":   0.15,
    "earnings":  0.05,
}

# (min_score_inclusive, label, confidence_label)
SIGNAL_MAP = [
    ( 6.0, "🟢 STRONG BUY",  "Very High"),
    ( 3.5, "🟢 BUY",         "High"),
    ( 1.0, "🟡 MILD BUY",    "Moderate"),
    (-1.0, "⚪ NEUTRAL",      "Low"),
    (-3.5, "🔴 MILD SELL",   "Moderate"),
    (-6.0, "🔴 SELL",        "High"),
    (-99,  "🔴 STRONG SELL", "Very High"),
]


def _to_score(df, col):
    if col in df.columns:
        return df[col].fillna(0).astype(float)
    return pd.Series(0.0, index=df.index)


def _normalise(series, raw_max):
    return (series / raw_max * 10).clip(-10, 10)


def _assign_signal(score):
    for threshold, label, conf in SIGNAL_MAP:
        if score >= threshold:
            return label, conf
    return "🔴 STRONG SELL", "Very High"


def _confidence_pct(score):
    return round(min(100, abs(score) / 10 * 100), 1)


def generate_signals(tech_df, fund_df, sentiment_df, insider_df,
                     earnings_df, universe_df):
    """
    Merge all factor DataFrames and produce a ranked signals DataFrame.

    Parameters
    ----------
    tech_df      : from compute_technical_factors
    fund_df      : from compute_fundamental_factors
    sentiment_df : from compute_sentiment_scores
    insider_df   : from compute_insider_scores
    earnings_df  : from compute_earnings_factors
    universe_df  : from get_universe() — provides sector / type metadata

    Returns
    -------
    pd.DataFrame  sorted by composite_score descending.
    """
    base = tech_df.copy() if not tech_df.empty else pd.DataFrame(columns=["ticker"])

    for df, suffix in [
        (fund_df,      "_fund"),
        (sentiment_df, "_sent"),
        (insider_df,   "_ins"),
        (earnings_df,  "_earn"),
    ]:
        if df is not None and not df.empty:
            rename = {
                c: c + suffix
                for c in df.columns
                if c != "ticker" and c in base.columns
            }
            base = base.merge(df.rename(columns=rename), on="ticker", how="left")

    # Metadata
    if universe_df is not None and not universe_df.empty:
        meta = universe_df[["ticker", "sector", "instrument_type"]].drop_duplicates("ticker")
        base = base.merge(meta, on="ticker", how="left")

    if base.empty:
        return pd.DataFrame()

    # Normalise each raw score → [−10, +10]
    base["_tech_n"] = _normalise(_to_score(base, "tech_score"),      raw_max=10)
    base["_fund_n"] = _normalise(_to_score(base, "fund_score"),      raw_max=10)
    base["_sent_n"] = _normalise(_to_score(base, "sentiment_score"), raw_max=10)
    base["_ins_n"]  = _normalise(_to_score(base, "insider_score"),   raw_max=5)
    # Earnings proximity: imminent → small positive boost
    base["_earn_n"] = (
        base.get("earnings_imminent", pd.Series(False, index=base.index))
            .fillna(False).astype(float) * 2
    )

    # Weighted composite
    base["composite_score"] = (
        base["_tech_n"] * WEIGHTS["tech"]
        + base["_fund_n"] * WEIGHTS["fund"]
        + base["_sent_n"] * WEIGHTS["sentiment"]
        + base["_ins_n"]  * WEIGHTS["insider"]
        + base["_earn_n"] * WEIGHTS["earnings"]
    ).round(3)

    # Signal labels
    base[["signal", "confidence"]] = base["composite_score"].apply(
        lambda s: pd.Series(_assign_signal(s))
    )
    base["confidence_pct"] = base["composite_score"].apply(_confidence_pct)

    # Drop internal columns
    base = base.drop(columns=[c for c in base.columns if c.startswith("_")], errors="ignore")

    return base.sort_values("composite_score", ascending=False).reset_index(drop=True)


def get_top_signals(signals_df, n=10, direction="bullish"):
    """
    Return top-N signals.
    direction : 'bullish' | 'bearish' | 'all'
    """
    if signals_df is None or signals_df.empty:
        return pd.DataFrame()
    if direction == "bullish":
        return signals_df[signals_df["composite_score"] > 0].head(n)
    elif direction == "bearish":
        return signals_df[signals_df["composite_score"] < 0].tail(n).iloc[::-1]
    return signals_df.head(n)
