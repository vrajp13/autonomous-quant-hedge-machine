"""
factors.py – Multi-factor computation engine.

Technical factors: RSI, MACD, Bollinger %B, momentum (21d/63d),
                   volume surge, ATR, 52-week position.

Fundamental factors: P/E, forward P/E, PEG, P/B, ROE, revenue growth,
                     earnings growth, analyst target upside, short interest.

Each group returns a DataFrame with a normalised _score column
(−10 to +10) that the signal model combines.
"""

import logging
import numpy as np
import pandas as pd

from core.data_fetcher import get_close_series, get_volume_series

logger = logging.getLogger(__name__)


# ── Technical helpers ──────────────────────────────────────────────────────

def _rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    # Pure-gain rows (loss==0): RSI = 100; flat rows: RSI = 50
    rsi   = rsi.where(loss != 0, other=gain.apply(lambda g: 100.0 if g > 0 else 50.0))
    return rsi


def _macd(series, fast=12, slow=26, signal=9):
    ema_fast  = series.ewm(span=fast,   adjust=False).mean()
    ema_slow  = series.ewm(span=slow,   adjust=False).mean()
    macd_line = ema_fast - ema_slow
    sig_line  = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - sig_line
    return macd_line, sig_line, histogram


def _bollinger(series, period=20, n_std=2):
    sma   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = sma + n_std * std
    lower = sma - n_std * std
    pct_b = (series - lower) / (upper - lower).replace(0, np.nan)
    return pct_b


def _atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Technical factor computation ───────────────────────────────────────────

def compute_technical_factors(price_history, tickers):
    """
    Compute technical factors for each ticker.

    Parameters
    ----------
    price_history : pd.DataFrame  MultiIndex OHLCV from data_fetcher
    tickers       : list[str]

    Returns
    -------
    pd.DataFrame  one row per ticker.
    """
    results = []

    for ticker in tickers:
        try:
            close = get_close_series(price_history, ticker)
            if len(close) < 50:
                continue

            if isinstance(price_history.columns, pd.MultiIndex):
                high   = price_history["High"][ticker].dropna()
                low    = price_history["Low"][ticker].dropna()
                volume = get_volume_series(price_history, ticker)
            else:
                high   = price_history["High"].dropna()
                low    = price_history["Low"].dropna()
                volume = get_volume_series(price_history, ticker)

            curr_price = close.iloc[-1]

            # RSI
            rsi_val = _rsi(close).iloc[-1]

            # MACD
            _, _, hist  = _macd(close)
            macd_bullish = bool(hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2])

            # Bollinger %B
            bb_pct = _bollinger(close).iloc[-1]

            # Momentum
            mom_21 = (close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0.0
            mom_63 = (close.iloc[-1] / close.iloc[-63] - 1) if len(close) >= 63 else 0.0

            # Volume ratio vs 20-day avg
            avg_vol   = volume.rolling(20).mean().iloc[-1]
            vol_ratio = (volume.iloc[-1] / avg_vol) if avg_vol and avg_vol > 0 else 1.0

            # 52-week position
            window    = min(252, len(close))
            high_52w  = close.rolling(window).max().iloc[-1]
            low_52w   = close.rolling(window).min().iloc[-1]
            pct_high  = (curr_price - high_52w) / high_52w
            pct_low   = (curr_price - low_52w)  / low_52w if low_52w else 0.0

            # ATR %
            atr_val = _atr(high, low, close).iloc[-1]
            atr_pct = atr_val / curr_price if curr_price else 0.0

            # ── Score assembly (−10 → +10) ──
            score = 0.0

            # RSI
            if   rsi_val <= 25: score += 3
            elif rsi_val <= 35: score += 2
            elif rsi_val <= 45: score += 1
            elif rsi_val >= 80: score -= 3
            elif rsi_val >= 70: score -= 2
            elif rsi_val >= 60: score -= 1

            # Momentum 21d
            if   mom_21 >  0.07: score += 2
            elif mom_21 >  0.03: score += 1
            elif mom_21 < -0.07: score -= 2
            elif mom_21 < -0.03: score -= 1

            # Momentum 63d
            if   mom_63 >  0.12: score += 2
            elif mom_63 >  0.05: score += 1
            elif mom_63 < -0.12: score -= 2
            elif mom_63 < -0.05: score -= 1

            # MACD
            score += 1 if macd_bullish else -1

            # Volume surge
            if   vol_ratio > 2.0 and mom_21 > 0: score += 1.5
            elif vol_ratio > 1.5 and mom_21 > 0: score += 0.5
            elif vol_ratio > 2.0 and mom_21 < 0: score -= 1.5

            # Near 52-week high
            if   pct_high > -0.03: score += 1
            elif pct_high < -0.30: score -= 1

            score     = max(-10, min(10, score))
            direction = "BULLISH" if score >= 2 else ("BEARISH" if score <= -2 else "NEUTRAL")

            results.append({
                "ticker":           ticker,
                "price":            round(curr_price, 2),
                "rsi":              round(rsi_val, 1),
                "momentum_21d_pct": round(mom_21 * 100, 2),
                "momentum_63d_pct": round(mom_63 * 100, 2),
                "volume_ratio":     round(vol_ratio, 2),
                "bb_pct":           round(bb_pct, 3),
                "pct_from_52w_high":round(pct_high * 100, 2),
                "pct_from_52w_low": round(pct_low  * 100, 2),
                "macd_bullish":     macd_bullish,
                "atr_pct":          round(atr_pct * 100, 2),
                "tech_score":       round(score, 2),
                "tech_direction":   direction,
            })

        except Exception as exc:
            logger.warning("Technical factors failed for %s: %s", ticker, exc)

    return pd.DataFrame(results)


# ── Fundamental factor computation ─────────────────────────────────────────

def compute_fundamental_factors(fundamentals):
    """
    Score each ticker on fundamental quality.

    Parameters
    ----------
    fundamentals : dict[str -> dict]  from data_fetcher.fetch_ticker_info

    Returns
    -------
    pd.DataFrame  one row per ticker.
    """
    results = []

    for ticker, info in fundamentals.items():
        if not info:
            continue
        try:
            fwd_pe      = info.get("forwardPE")
            peg         = info.get("pegRatio")
            pb          = info.get("priceToBook")
            roe         = info.get("returnOnEquity")
            pe          = info.get("trailingPE")
            debt_eq     = info.get("debtToEquity")
            rev_growth  = info.get("revenueGrowth")
            earn_growth = info.get("earningsGrowth")
            profit_mgn  = info.get("profitMargins")
            mkt_cap     = info.get("marketCap", 0)
            beta        = info.get("beta")
            rec_mean    = info.get("recommendationMean")
            target      = info.get("targetMeanPrice")
            curr_price  = info.get("regularMarketPrice")
            short_ratio = info.get("shortRatio")

            analyst_upside = (
                (target - curr_price) / curr_price
                if (target and curr_price and curr_price > 0)
                else None
            )

            score = 0.0

            # Forward P/E
            if fwd_pe and 0 < fwd_pe:
                if   fwd_pe < 12: score += 3
                elif fwd_pe < 18: score += 2
                elif fwd_pe < 25: score += 1
                elif fwd_pe > 50: score -= 2
                elif fwd_pe > 35: score -= 1

            # PEG
            if peg and peg > 0:
                if   peg < 0.8: score += 3
                elif peg < 1.2: score += 2
                elif peg < 1.8: score += 1
                elif peg > 3:   score -= 2
                elif peg > 2:   score -= 1

            # ROE
            if roe:
                if   roe >  0.30: score += 2
                elif roe >  0.15: score += 1
                elif roe <  0:    score -= 2
                elif roe <  0.05: score -= 1

            # Revenue growth
            if rev_growth is not None:
                if   rev_growth >  0.20: score += 2
                elif rev_growth >  0.08: score += 1
                elif rev_growth < -0.10: score -= 2
                elif rev_growth <  0:    score -= 1

            # Earnings growth
            if earn_growth is not None:
                if   earn_growth >  0.25: score += 2
                elif earn_growth >  0.10: score += 1
                elif earn_growth < -0.15: score -= 2
                elif earn_growth <  0:    score -= 1

            # Analyst consensus (1=Strong Buy … 5=Sell)
            if rec_mean:
                if   rec_mean <= 1.5: score += 2
                elif rec_mean <= 2.2: score += 1
                elif rec_mean >= 4:   score -= 2
                elif rec_mean >= 3.5: score -= 1

            # Analyst price-target upside
            if analyst_upside is not None:
                if   analyst_upside >  0.25: score += 2
                elif analyst_upside >  0.10: score += 1
                elif analyst_upside < -0.10: score -= 2
                elif analyst_upside <  0:    score -= 1

            # High short interest
            if short_ratio and short_ratio > 10:
                score -= 1

            score = max(-10, min(10, score))

            results.append({
                "ticker":               ticker,
                "pe_ratio":             round(pe, 1)             if pe          else None,
                "forward_pe":           round(fwd_pe, 1)         if fwd_pe      else None,
                "peg_ratio":            round(peg, 2)            if peg         else None,
                "price_to_book":        round(pb, 2)             if pb          else None,
                "roe_pct":              round(roe * 100, 1)      if roe         else None,
                "debt_equity":          round(debt_eq, 1)        if debt_eq     else None,
                "revenue_growth_pct":   round(rev_growth * 100, 1)  if rev_growth  is not None else None,
                "earnings_growth_pct":  round(earn_growth * 100, 1) if earn_growth is not None else None,
                "profit_margin_pct":    round(profit_mgn * 100, 1)  if profit_mgn  else None,
                "market_cap_B":         round(mkt_cap / 1e9, 1) if mkt_cap     else None,
                "beta":                 round(beta, 2)           if beta        else None,
                "analyst_upside_pct":   round(analyst_upside * 100, 1) if analyst_upside is not None else None,
                "rec_mean":             round(rec_mean, 2)       if rec_mean    else None,
                "short_ratio":          round(short_ratio, 1)    if short_ratio else None,
                "fund_score":           round(score, 2),
            })

        except Exception as exc:
            logger.warning("Fundamental factors failed for %s: %s", ticker, exc)

    return pd.DataFrame(results)


# ── Earnings proximity factor ──────────────────────────────────────────────

def compute_earnings_factors(earnings_map):
    """
    Flag tickers with earnings within the next 14 days.

    Returns
    -------
    pd.DataFrame  columns: ticker, earnings_date, days_to_earnings, earnings_imminent
    """
    from datetime import datetime, timedelta
    today   = datetime.utcnow().date()
    results = []

    for ticker, data in earnings_map.items():
        ed      = data.get("earnings_date")
        days    = None
        imminent = False

        if ed:
            try:
                if hasattr(ed, "date"):
                    ed = ed.date()
                days     = (ed - today).days
                imminent = 0 <= days <= 14
            except Exception:
                pass

        results.append({
            "ticker":           ticker,
            "earnings_date":    str(ed) if ed else None,
            "days_to_earnings": days,
            "earnings_imminent":imminent,
        })

    return pd.DataFrame(results)
