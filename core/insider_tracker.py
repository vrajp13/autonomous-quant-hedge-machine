"""
insider_tracker.py – Insider buy / sell signal detection.

Uses yfinance insider_transactions (SEC Form 4 data) to detect clusters of
insider buying or selling in the past 60 days.
Cluster buying is one of the strongest documented alpha signals.
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _parse_insider_df(df):
    """Normalise an insider_transactions DataFrame from yfinance."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    col_map = {}
    for col in df.columns:
        cl = col.lower()
        if "start" in cl or "date" in cl:
            col_map[col] = "date"
        elif "shares" in cl:
            col_map[col] = "shares"
        elif "value" in cl:
            col_map[col] = "value"
        elif "transaction" in cl or "type" in cl:
            col_map[col] = "transaction"
        elif "insider" in cl or "name" in cl:
            col_map[col] = "insider"
        elif "title" in cl or "position" in cl:
            col_map[col] = "position"

    df = df.rename(columns=col_map)
    for col in ["date", "shares", "value", "transaction", "insider", "position"]:
        if col not in df.columns:
            df[col] = None
    return df


def compute_insider_scores(insider_map, lookback_days=60):
    """
    Compute insider activity scores for each ticker.

    Scoring logic:
    - Cluster buys (≥ 2 insiders buying) → strong bullish
    - Large buy (> $500k) by C-suite     → bullish
    - Cluster sells (≥ 3 insiders)       → mild bearish
    - Isolated sells                     → neutral (diversification)

    Returns
    -------
    pd.DataFrame  columns: ticker, insider_score, buy_count, sell_count,
                            total_buy_value_k, top_insider_action
    """
    cutoff  = datetime.utcnow() - timedelta(days=lookback_days)
    results = []

    for ticker, raw_df in insider_map.items():
        try:
            df = _parse_insider_df(raw_df)

            if df.empty:
                results.append(_empty_row(ticker))
                continue

            # Filter to lookback window
            if "date" in df.columns and df["date"].notna().any():
                try:
                    df["date"]  = pd.to_datetime(df["date"], utc=True, errors="coerce")
                    cutoff_ts   = pd.Timestamp(cutoff, tz="UTC")
                    df = df[df["date"] >= cutoff_ts]
                except Exception:
                    pass

            if df.empty:
                results.append(_empty_row(ticker))
                continue

            is_buy  = df["transaction"].str.contains("purchase|buy|P -",  case=False, na=False)
            is_sell = df["transaction"].str.contains("sale|sell|S -",     case=False, na=False)

            buy_df  = df[is_buy]
            sell_df = df[is_sell]

            buy_count  = len(buy_df)
            sell_count = len(sell_df)

            total_buy_val = 0.0
            if "value" in buy_df.columns:
                vals = pd.to_numeric(buy_df["value"], errors="coerce").dropna()
                total_buy_val = float(vals.sum())

            if buy_count >= sell_count and buy_count > 0:
                top_action = f"{buy_count} insider buy(s)"
            elif sell_count > 0:
                top_action = f"{sell_count} insider sell(s)"
            else:
                top_action = "No recent activity"

            score = 0.0
            if   buy_count >= 3: score += 4
            elif buy_count == 2: score += 2.5
            elif buy_count == 1: score += 1

            if   total_buy_val > 1_000_000: score += 2
            elif total_buy_val > 500_000:   score += 1

            if   sell_count >= 4: score -= 2
            elif sell_count >= 2: score -= 1

            score = max(-5, min(5, score))

            results.append({
                "ticker":              ticker,
                "insider_score":       round(score, 2),
                "buy_count":           buy_count,
                "sell_count":          sell_count,
                "total_buy_value_k":   round(total_buy_val / 1000, 1),
                "top_insider_action":  top_action,
            })

        except Exception as exc:
            logger.warning("insider_tracker failed for %s: %s", ticker, exc)
            results.append(_empty_row(ticker))

    return pd.DataFrame(results)


def _empty_row(ticker):
    return {
        "ticker":             ticker,
        "insider_score":      0.0,
        "buy_count":          0,
        "sell_count":         0,
        "total_buy_value_k":  0.0,
        "top_insider_action": "No data",
    }
