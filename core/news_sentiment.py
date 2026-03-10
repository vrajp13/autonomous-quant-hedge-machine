"""
news_sentiment.py – News & market sentiment analysis.

Key design: fetch_macro_close() downloads VIX + SPY + all sector ETFs ONCE.
Both get_market_sentiment() and get_sector_rotation() consume that pre-fetched
DataFrame, eliminating redundant yf.download calls.
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SECTOR_MAP = {
    "XLK": "Technology",   "XLF": "Financials",   "XLV": "Healthcare",
    "XLE": "Energy",        "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
    "XLI": "Industrials",   "XLU": "Utilities",     "XLRE": "Real Estate",
    "XLB": "Materials",     "XLC": "Comm. Services",
}
SECTOR_ETFS   = list(SECTOR_MAP.keys())
MACRO_TICKERS = ["^VIX", "SPY"] + SECTOR_ETFS


# ── Sentiment lexicon ──────────────────────────────────────────────────────

BULLISH_TERMS = {
    "record earnings": 3, "blowout": 3, "massive beat": 3, "strong buy": 3,
    "upgrade": 2, "raised guidance": 3, "raised target": 2, "beat estimates": 2,
    "earnings beat": 2, "revenue beat": 2, "raised dividend": 2, "buyback": 2,
    "acquisition": 1, "merger": 1, "strategic partnership": 1, "outperform": 2,
    "bullish": 2, "rally": 2, "surge": 2, "jump": 2, "soar": 2,
    "all-time high": 3, "52-week high": 2, "breakout": 2, "growth": 1,
    "expansion": 1, "recovery": 1, "rebound": 1, "profit": 1, "optimistic": 1,
    "rate cut": 2, "stimulus": 2, "fed pivot": 2, "soft landing": 2,
    "gdp beat": 2, "inflation easing": 2,
}

BEARISH_TERMS = {
    "earnings miss": 3, "revenue miss": 3, "lowered guidance": 3, "guidance cut": 3,
    "downgrade": 2, "cut target": 2, "layoffs": 2, "job cuts": 2, "restructuring": 2,
    "bankruptcy": 3, "default": 3, "fraud": 3, "investigation": 2,
    "class action": 2, "sec probe": 3, "recall": 2, "bearish": 2,
    "plunge": 2, "crash": 3, "collapse": 3, "slump": 2, "deficit": 1,
    "disappointing": 2, "warning": 2, "headwinds": 1, "rate hike": 2,
    "recession": 3, "stagflation": 2, "tariff": 1, "trade war": 2,
    "sanctions": 2, "inflation spike": 2, "gdp miss": 2, "bank failure": 3,
}

GEOPOLITICAL_TERMS = {
    "war": -2, "conflict": -1, "tension": -1, "escalation": -2,
    "invasion": -2, "nuclear": -2, "cyber attack": -2,
    "peace talks": 1, "ceasefire": 1, "de-escalation": 1,
}


def _score_headline(headline):
    """Score a single headline. Returns float in [−10, +10]."""
    if not headline:
        return 0.0
    text  = headline.lower()
    score = 0.0
    for term, w in BULLISH_TERMS.items():
        if term in text: score += w
    for term, w in BEARISH_TERMS.items():
        if term in text: score -= w
    for term, w in GEOPOLITICAL_TERMS.items():
        if term in text: score += w
    return max(-10.0, min(10.0, score))


# ── News sentiment scoring ─────────────────────────────────────────────────

def compute_sentiment_scores(news_map, lookback_hours=48):
    """
    Compute sentiment scores from recent news headlines per ticker.

    Parameters
    ----------
    news_map       : dict[ticker -> list[news_dicts]]
    lookback_hours : int  Only consider articles within this window.

    Returns
    -------
    pd.DataFrame  columns: ticker, sentiment_score, news_count,
                            top_headline, sentiment_label
    """
    cutoff_ts = (datetime.utcnow() - timedelta(hours=lookback_hours)).timestamp()
    results   = []

    for ticker, articles in news_map.items():
        scores, titles = [], []
        for article in articles:
            pt = article.get("providerPublishTime", 0)
            if pt and pt < cutoff_ts:
                continue
            title = article.get("title", "")
            scores.append(_score_headline(title))
            titles.append(title)

        avg  = float(np.mean(scores)) if scores else 0.0
        top  = titles[0] if titles else "No recent news"

        if   avg >= 2:    label = "VERY POSITIVE"
        elif avg >= 0.5:  label = "POSITIVE"
        elif avg <= -2:   label = "VERY NEGATIVE"
        elif avg <= -0.5: label = "NEGATIVE"
        else:             label = "NEUTRAL"

        results.append({
            "ticker":          ticker,
            "sentiment_score": round(avg, 2),
            "news_count":      len(scores),
            "top_headline":    top,
            "sentiment_label": label,
        })

    return pd.DataFrame(results)


# ── Single shared macro download ───────────────────────────────────────────

def fetch_macro_close(period="1y"):
    """
    Download VIX + SPY + all sector ETFs in ONE yf.download call.
    Call this once in main.py and pass the result to both
    get_market_sentiment() and get_sector_rotation().

    Returns
    -------
    pd.DataFrame  Close prices indexed by date. Empty DF on failure.
    """
    try:
        logger.info("Downloading macro/sector data (%d tickers)…", len(MACRO_TICKERS))
        data  = yf.download(MACRO_TICKERS, period=period,
                            auto_adjust=True, progress=False, threads=True)
        close = data["Close"] if "Close" in data else pd.DataFrame()
        logger.info("Macro download done. Shape: %s", close.shape)
        return close
    except Exception as exc:
        logger.error("fetch_macro_close error: %s", exc)
        return pd.DataFrame()


# ── Market sentiment (consumes pre-fetched close) ──────────────────────────

def get_market_sentiment(close=None):
    """
    Compute macro sentiment from VIX, SPY trend, and sector breadth.

    Parameters
    ----------
    close : pd.DataFrame | None
        Output of fetch_macro_close(). Fetches fresh only if None.

    Returns
    -------
    dict  keys: vix, vix_label, spy_trend, breadth_pct,
                macro_sentiment, macro_score
    """
    result = {
        "vix": None, "vix_label": "Unknown",
        "spy_trend": "Unknown", "breadth_pct": None,
        "macro_sentiment": "NEUTRAL", "macro_score": 0,
    }

    if close is None or close.empty:
        close = fetch_macro_close()
    if close.empty:
        return result

    try:
        # VIX
        if "^VIX" in close.columns:
            vix = float(close["^VIX"].dropna().iloc[-1])
            result["vix"] = round(vix, 2)
            if   vix < 15: result["vix_label"] = "LOW FEAR (Complacent)"
            elif vix < 20: result["vix_label"] = "CALM"
            elif vix < 30: result["vix_label"] = "MODERATE FEAR"
            elif vix < 40: result["vix_label"] = "HIGH FEAR"
            else:          result["vix_label"] = "EXTREME FEAR (Capitulation Zone)"

        # SPY vs 200-SMA
        if "SPY" in close.columns:
            spy    = close["SPY"].dropna()
            sma200 = float(spy.rolling(200).mean().iloc[-1])
            curr   = float(spy.iloc[-1])
            if   curr > sma200 * 1.02: result["spy_trend"] = "BULL MARKET (above 200-SMA)"
            elif curr > sma200:        result["spy_trend"] = "NEUTRAL (near 200-SMA)"
            else:                      result["spy_trend"] = "BEAR MARKET (below 200-SMA)"

        # Sector breadth
        above_50 = total = 0
        for etf in SECTOR_ETFS:
            if etf in close.columns:
                s = close[etf].dropna()
                if len(s) >= 50:
                    if float(s.iloc[-1]) > float(s.rolling(50).mean().iloc[-1]):
                        above_50 += 1
                    total += 1
        if total:
            result["breadth_pct"] = round(above_50 / total * 100, 1)

        # Composite score
        score = 0
        v = result["vix"]
        if v:
            if   v < 15: score += 2
            elif v < 20: score += 1
            elif v > 35: score -= 3
            elif v > 25: score -= 2
        b = result["breadth_pct"]
        if b is not None:
            if   b >= 70: score += 2
            elif b >= 50: score += 1
            elif b <= 30: score -= 2
            elif b <= 40: score -= 1
        if "BULL" in result["spy_trend"]:  score += 2
        elif "BEAR" in result["spy_trend"]: score -= 2

        result["macro_score"] = score
        if   score >= 3:  result["macro_sentiment"] = "RISK-ON 🟢"
        elif score >= 1:  result["macro_sentiment"] = "MILDLY BULLISH 🟡"
        elif score <= -3: result["macro_sentiment"] = "RISK-OFF 🔴"
        elif score <= -1: result["macro_sentiment"] = "MILDLY BEARISH 🟠"
        else:             result["macro_sentiment"] = "NEUTRAL ⚪"

    except Exception as exc:
        logger.error("get_market_sentiment error: %s", exc)

    return result


# ── Sector rotation (consumes same pre-fetched close) ─────────────────────

def get_sector_rotation(close=None):
    """
    Rank sectors by 1-month & 3-month performance.

    Parameters
    ----------
    close : pd.DataFrame | None
        Output of fetch_macro_close(). Fetches fresh only if None.

    Returns
    -------
    pd.DataFrame  sorted by return_1m_pct descending.
    """
    if close is None or close.empty:
        close = fetch_macro_close()

    results = []
    try:
        for etf, sector in SECTOR_MAP.items():
            if etf not in close.columns:
                continue
            s = close[etf].dropna()
            if len(s) < 21:
                continue
            ret_1m = float(s.iloc[-1]) / float(s.iloc[-21]) - 1
            ret_3m = float(s.iloc[-1]) / float(s.iloc[0])  - 1
            sma50  = s.rolling(50).mean().iloc[-1] if len(s) >= 50 else None
            trend  = ("↑ Above 50-SMA"
                      if sma50 is not None and float(s.iloc[-1]) > float(sma50)
                      else "↓ Below 50-SMA")
            results.append({
                "sector_etf":     etf,
                "sector":         sector,
                "return_1m_pct":  round(ret_1m * 100, 2),
                "return_3m_pct":  round(ret_3m * 100, 2),
                "trend":          trend,
            })
    except Exception as exc:
        logger.error("get_sector_rotation error: %s", exc)

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("return_1m_pct", ascending=False).reset_index(drop=True)
    return df