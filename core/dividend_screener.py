"""
dividend_screener.py – Dividend stock quality screener.

Scores each ticker across five dimensions:
  1. Yield attractiveness  (2.5–6% is optimal)
  2. Payout ratio safety   (< 50% ideal)
  3. Earnings growth cover (growing earnings sustain dividends)
  4. Yield consistency     (current vs 5-year average)
  5. Balance-sheet quality (low debt, strong current ratio)

Final dividend_score is normalised to 0–100.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_WEIGHTS = {
    "yield_score":        0.30,
    "safety_score":       0.25,
    "growth_cover_score": 0.20,
    "consistency_score":  0.15,
    "balance_sheet_score":0.10,
}


def _score_yield(div_yield):
    if div_yield is None or div_yield <= 0:
        return 0.0
    y = div_yield * 100
    if   y < 1:   return 0.5
    elif y < 2:   return 1.5
    elif y < 2.5: return 2.5
    elif y < 4:   return 5.0   # sweet spot
    elif y < 6:   return 4.0
    elif y < 8:   return 2.5   # high yield → distress risk
    else:         return 1.0   # yield trap


def _score_safety(payout_ratio):
    if payout_ratio is None or payout_ratio <= 0:
        return 2.5
    p = payout_ratio * 100
    if   p < 30:  return 5.0
    elif p < 50:  return 4.0
    elif p < 65:  return 3.0
    elif p < 80:  return 2.0
    elif p < 100: return 1.0
    else:         return 0.0


def _score_growth_cover(earnings_growth):
    if earnings_growth is None: return 2.0
    g = earnings_growth
    if   g >  0.20: return 5.0
    elif g >  0.10: return 4.0
    elif g >  0.03: return 3.0
    elif g >= 0:    return 2.0
    elif g > -0.10: return 1.0
    else:           return 0.0


def _score_consistency(five_yr_avg_yield, current_yield):
    if five_yr_avg_yield is None or current_yield is None: return 2.5
    if five_yr_avg_yield <= 0 or current_yield <= 0:       return 2.5
    ratio = current_yield / five_yr_avg_yield
    if   0.8 <= ratio <= 1.2: return 5.0   # stable
    elif 0.6 <= ratio < 0.8:  return 4.0   # yield compressed (price up)
    elif 1.2 < ratio <= 1.5:  return 3.5   # yield elevated
    elif ratio > 1.5:         return 1.5   # price stressed
    else:                     return 2.0


def _score_balance_sheet(debt_equity, current_ratio):
    score = 2.5
    if debt_equity is not None:
        if   debt_equity < 30:  score += 1.5
        elif debt_equity < 60:  score += 0.75
        elif debt_equity > 150: score -= 1.5
        elif debt_equity > 100: score -= 0.75
    if current_ratio is not None:
        if   current_ratio > 2:   score += 1.0
        elif current_ratio > 1.5: score += 0.5
        elif current_ratio < 1:   score -= 1.0
    return max(0.0, min(5.0, score))


def compute_dividend_scores(fundamentals):
    """
    Score each ticker on dividend quality.

    Parameters
    ----------
    fundamentals : dict[ticker -> info_dict]

    Returns
    -------
    pd.DataFrame  sorted by dividend_score descending.
    """
    results = []

    for ticker, info in fundamentals.items():
        if not info:
            continue

        div_yield  = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
        div_rate   = info.get("dividendRate")
        payout     = info.get("payoutRatio")
        five_yr    = info.get("fiveYearAvgDividendYield")
        earn_growth= info.get("earningsGrowth")
        debt_eq    = info.get("debtToEquity")
        curr_ratio = info.get("currentRatio")

        if not div_yield or div_yield <= 0:
            continue

        # Convert 5-yr avg from % to decimal if necessary
        if five_yr and five_yr > 1:
            five_yr = five_yr / 100

        ys = _score_yield(div_yield)
        ss = _score_safety(payout)
        gs = _score_growth_cover(earn_growth)
        cs = _score_consistency(five_yr, div_yield)
        bs = _score_balance_sheet(debt_eq, curr_ratio)

        raw   = (ys * _WEIGHTS["yield_score"]
                 + ss * _WEIGHTS["safety_score"]
                 + gs * _WEIGHTS["growth_cover_score"]
                 + cs * _WEIGHTS["consistency_score"]
                 + bs * _WEIGHTS["balance_sheet_score"])
        score = raw / 5.0 * 100

        if   score >= 80: grade, label = "A+", "⭐ Exceptional Dividend"
        elif score >= 70: grade, label = "A",  "🟢 Strong Dividend"
        elif score >= 60: grade, label = "B",  "🟡 Good Dividend"
        elif score >= 45: grade, label = "C",  "🟠 Average Dividend"
        else:             grade, label = "D",  "🔴 Risky Dividend"

        results.append({
            "ticker":              ticker,
            "div_yield_pct":       round(div_yield * 100, 2),
            "div_rate_annual":     round(div_rate, 2)       if div_rate else None,
            "payout_ratio_pct":    round(payout * 100, 1)   if payout   else None,
            "five_yr_avg_yield_pct":round(five_yr * 100, 2) if five_yr  else None,
            "dividend_score":      round(score, 1),
            "dividend_grade":      grade,
            "dividend_label":      label,
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("dividend_score", ascending=False).reset_index(drop=True)
    return df


def get_top_dividend_picks(fundamentals, n=10):
    """Return top-N dividend stocks by composite score."""
    df = compute_dividend_scores(fundamentals)
    return df.head(n) if not df.empty else df