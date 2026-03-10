"""
weekly_report.py – Friday deep-analysis Telegram report.

Sections
--------
  1. Header + universe snapshot
  2. Week in Review  – macro summary
  3. SECTOR PLAYBOOK – full 3-layer prediction with analysis per sector
  4. Top 10 BUY Watchlist
  5. Top 5 SELL Watchlist
  6. Sector ETF Scorecard (price-action table)
  7. Dividend Income Report
  8. Upcoming Earnings Calendar
  9. Trade Ideas
 10. Disclaimer
"""

from datetime import datetime, timezone
import pandas as pd


def _pct(val, decimals=1):
    if val is None:
        return "N/A"
    sign = "+" if float(val) > 0 else ""
    return f"{sign}{float(val):.{decimals}f}%"


def _val(val, decimals=2, suffix=""):
    if val is None:
        return "N/A"
    return f"{float(val):.{decimals}f}{suffix}"


# ── Sections ───────────────────────────────────────────────────────────────

def _header(universe_stats):
    now  = datetime.now(timezone.utc)
    week = now.strftime("Week ending %A %d %B %Y")
    n    = universe_stats.get("total_stocks", "?")
    sec  = universe_stats.get("sectors", "?")
    return (
        f"📋 QUANT HEDGE ENGINE — WEEKLY REPORT\n"
        f"📆 {week}\n"
        f"🌐 Live Universe: {n} stocks across {sec} sectors\n"
        f"   (S&P 500 + Nasdaq-100 + ETFs/Bonds/Commodities)"
    )


def _week_review(macro, sector_pred_df):
    top_sec = bot_sec = ""
    if sector_pred_df is not None and not sector_pred_df.empty:
        top_sec = f"{sector_pred_df.iloc[0]['sector']} ({_val(sector_pred_df.iloc[0]['sector_score'],1)})"
        bot_sec = f"{sector_pred_df.iloc[-1]['sector']} ({_val(sector_pred_df.iloc[-1]['sector_score'],1)})"

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📰 WEEK IN REVIEW",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Market Regime : {macro.get('macro_sentiment','N/A')}",
        f"VIX           : {_val(macro.get('vix'),2)} — {macro.get('vix_label','N/A')}",
        f"S&P 500 Trend : {macro.get('spy_trend','N/A')}",
    ]
    b = macro.get("breadth_pct")
    if b: lines.append(f"Sector Breadth : {b:.1f}% above 50-SMA")
    if top_sec: lines.append(f"Best Sector (model) : {top_sec}")
    if bot_sec: lines.append(f"Worst Sector (model): {bot_sec}")
    return "\n".join(lines)


def _sector_playbook(sector_pred_df):
    """Full sector prediction table — the centrepiece of the weekly report."""
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔭 WEEKLY SECTOR PLAYBOOK",
        "   3-Layer Model: Bottom-Up Stocks (40%) + ETF Technicals (35%) + Macro (25%)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if sector_pred_df is None or sector_pred_df.empty:
        lines.append("Sector prediction unavailable.")
        return "\n".join(lines)

    for rank, (_, row) in enumerate(sector_pred_df.iterrows(), 1):
        sector    = row.get("sector", "?")
        score     = row.get("sector_score", 0)
        signal    = row.get("signal", "")
        rotation  = row.get("rotation_call", "")
        picks     = ", ".join(row.get("top_picks") or []) or "—"
        risk      = row.get("risk_factors", "")

        pct_bull  = row.get("pct_bullish")
        pct_bear  = row.get("pct_bearish")
        avg_comp  = row.get("avg_composite")
        mw_score  = row.get("mktcap_weighted_score")
        mom_1m    = row.get("mom_1m_pct")
        mom_3m    = row.get("mom_3m_pct")
        vs_spy    = row.get("vs_spy_1m_pct")
        rsi       = row.get("rsi")
        a50       = row.get("above_50sma")
        a200      = row.get("above_200sma")
        mac_score = row.get("macro_regime_score")
        n_tickers = row.get("ticker_count", "?")
        earn_cat  = row.get("earnings_catalysts", 0)

        sma_str = ""
        if a200 is not None:
            sma_str = "above 50 & 200-SMA" if (a50 and a200) else \
                      "above 50-SMA only"  if a50 else \
                      "below both SMAs"

        lines += [
            f"{'─'*28}",
            f"#{rank}  {sector.upper()}",
            f"    Score: {_val(score,2)} | {signal}",
            f"    Call: {rotation}",
            f"    Top Picks: {picks}",
            f"",
            f"    ▸ Bottom-Up ({n_tickers} stocks analysed)",
            f"      Bullish: {_pct(pct_bull)} | Bearish: {_pct(pct_bear)}",
            f"      Avg Signal: {_val(avg_comp,2)} | Mkt-Cap Wtd: {_val(mw_score,2)}",
            f"      Earnings Catalysts: {earn_cat} stocks reporting ≤14d",
            f"",
            f"    ▸ ETF Technicals",
            f"      Mom 1M: {_pct(mom_1m)} | 3M: {_pct(mom_3m)} | vs SPY: {_pct(vs_spy)}",
            f"      RSI: {_val(rsi,1)} | Trend: {sma_str}",
            f"",
            f"    ▸ Macro Overlay Score: {_val(mac_score,1)}",
            f"    ⚠ Risk: {risk}",
            "",
        ]

    return "\n".join(lines)


def _buy_watchlist(signals_df, n=10):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🚀 WEEKLY TOP BUY WATCHLIST",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if signals_df is None or signals_df.empty:
        lines.append("No signals.")
        return "\n".join(lines)

    subset = signals_df[signals_df["composite_score"] >= 1.0].head(n)
    for rank, (_, row) in enumerate(subset.iterrows(), 1):
        price   = row.get("price")
        target  = row.get("targetMeanPrice") or row.get("analyst_upside_pct")
        upsid   = row.get("analyst_upside_pct")
        earn_im = row.get("earnings_imminent", False)
        insider = row.get("top_insider_action", "")
        ins_str = f"\n     👤 {insider}" if insider and "No" not in insider else ""
        earn_str= f"\n     ⚡ Earnings: {row.get('earnings_date','?')}" if earn_im else ""

        lines += [
            f"{'─'*26}",
            f"#{rank}  {row.get('ticker','?')} | ${_val(price,2)} | {row.get('signal','')}",
            f"    Sector: {row.get('sector','')}  Beta: {_val(row.get('beta'),2)}",
            f"    Confidence: {_val(row.get('confidence_pct'),1)}%  Score: {_val(row.get('composite_score'),2)}",
            f"    Tech → RSI:{_val(row.get('rsi'),1)} Mom-21d:{_pct(row.get('momentum_21d_pct'))} Mom-63d:{_pct(row.get('momentum_63d_pct'))} Vol×:{_val(row.get('volume_ratio'),1)}x",
            f"    Fund → Fwd P/E:{_val(row.get('forward_pe'),1)} ROE:{_val(row.get('roe_pct'),1)}% EPS Gr:{_pct(row.get('earnings_growth_pct'))} Rev Gr:{_pct(row.get('revenue_growth_pct'))}",
            f"    Analyst Upside: {_pct(upsid)}{ins_str}{earn_str}",
            "",
        ]
    return "\n".join(lines)


def _sell_watchlist(signals_df, n=5):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ WEEKLY SELL / SHORT WATCH",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if signals_df is None or signals_df.empty:
        lines.append("No signals.")
        return "\n".join(lines)

    subset = (signals_df[signals_df["composite_score"] <= -1.0]
              .sort_values("composite_score").head(n))
    for rank, (_, row) in enumerate(subset.iterrows(), 1):
        lines += [
            f"#{rank}  {row.get('ticker','?')} | ${_val(row.get('price'),2)} | {row.get('signal','')}",
            f"    Score:{_val(row.get('composite_score'),2)} RSI:{_val(row.get('rsi'),1)} Mom-21d:{_pct(row.get('momentum_21d_pct'))}",
            f"    Sector: {row.get('sector','')}",
            "",
        ]
    return "\n".join(lines)


def _sector_scorecard(sector_rotation_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🗺️ SECTOR ETF SCORECARD",
        f"{'Sector':<22} {'1-Month':>8} {'3-Month':>9}  Trend",
        "─" * 54,
    ]
    if sector_rotation_df is None or sector_rotation_df.empty:
        lines.append("No ETF data.")
        return "\n".join(lines)
    for _, row in sector_rotation_df.iterrows():
        lines.append(
            f"{str(row.get('sector',''))[:21]:<22} "
            f"{_pct(row.get('return_1m_pct')):>8} "
            f"{_pct(row.get('return_3m_pct')):>9}  "
            f"{row.get('trend','')}"
        )
    return "\n".join(lines)


def _dividend_report(dividend_df, n=10):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💰 WEEKLY DIVIDEND INCOME REPORT",
        f"{'#':<3} {'Ticker':<7} {'Yield':>6} {'Rate':>7} {'Payout':>7} {'Grade':<4} Label",
        "─" * 65,
    ]
    if dividend_df is None or dividend_df.empty:
        lines.append("No dividend data.")
        return "\n".join(lines)
    for i, (_, row) in enumerate(dividend_df.head(n).iterrows(), 1):
        lines.append(
            f"{i:<3} {row.get('ticker','?'):<7} "
            f"{_val(row.get('div_yield_pct'),2,'%'):>6} "
            f"${_val(row.get('div_rate_annual'),2):>6} "
            f"{_val(row.get('payout_ratio_pct'),1,'%'):>7} "
            f"{row.get('dividend_grade',''):4} "
            f"{row.get('dividend_label','')}"
        )
    lines += [
        "",
        "💡 Sweet spot: Yield ≥2.5% | Payout ≤65% | Grade A/A+",
    ]
    return "\n".join(lines)


def _earnings_calendar(signals_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📅 UPCOMING EARNINGS — NEXT 14 DAYS",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if signals_df is None or signals_df.empty or "earnings_imminent" not in signals_df.columns:
        lines.append("No data.")
        return "\n".join(lines)

    df = signals_df[signals_df["earnings_imminent"] == True]
    if df.empty:
        lines.append("No imminent earnings in tracked universe.")
        return "\n".join(lines)
    if "days_to_earnings" in df.columns:
        df = df.sort_values("days_to_earnings")

    for _, row in df.iterrows():
        d = row.get("days_to_earnings")
        lines.append(
            f"  ⚡ {row.get('ticker','?'):<6} {row.get('earnings_date','?')} "
            f"(T-{d}d) → {row.get('signal','')} | "
            f"Mom:{_pct(row.get('momentum_21d_pct'))} Upside:{_pct(row.get('analyst_upside_pct'))}"
        )
    lines.append("\n  💡 Strategy: Consider vol plays 1-2 days before report.")
    return "\n".join(lines)


def _trade_ideas(signals_df, sector_pred_df, n=4):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 TRADE IDEAS FOR THE COMING WEEK",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  (Informational only — apply your own risk management)",
    ]

    # Best picks from top predicted sector
    if sector_pred_df is not None and not sector_pred_df.empty and signals_df is not None:
        top_sector = sector_pred_df.iloc[0]["sector"]
        sector_sig = sector_pred_df.iloc[0]["signal"]
        lines.append(f"\n  📌 SECTOR ROTATION PLAY — {top_sector} ({sector_sig})")
        top_in_sector = (signals_df[signals_df["sector"] == top_sector]
                         .sort_values("composite_score", ascending=False).head(3))
        for _, row in top_in_sector.iterrows():
            price  = row.get("price")
            upsid  = row.get("analyst_upside_pct")
            target = round(float(price) * (1 + float(upsid)/100), 2) if price and upsid else None
            lines.append(
                f"     {row.get('ticker','?'):<6} Entry:${_val(price,2)}  "
                f"Target:${_val(target,2)}  Upside:{_pct(upsid)}"
            )

    # Strong buy + imminent earnings = pre-earnings momentum play
    if signals_df is not None and not signals_df.empty:
        earn_plays = signals_df[
            (signals_df["earnings_imminent"] == True) &
            (signals_df["composite_score"] >= 2)
        ].head(2)
        if not earn_plays.empty:
            lines.append("\n  📌 PRE-EARNINGS MOMENTUM PLAYS")
            for _, row in earn_plays.iterrows():
                lines.append(
                    f"     {row.get('ticker','?'):<6} Earnings:{row.get('earnings_date','?')} "
                    f"Mom:{_pct(row.get('momentum_21d_pct'))} Score:{_val(row.get('composite_score'),2)}"
                )

    return "\n".join(lines)


# ── Assembler ──────────────────────────────────────────────────────────────

def build_weekly_report(signals_df, macro_sentiment, sector_rotation_df,
                        sector_pred_df, dividend_df, universe_stats=None):
    """
    Build the full Friday weekly report.  Returns list of ≤4000-char chunks.
    """
    universe_stats = universe_stats or {}
    body = "\n".join([
        _header(universe_stats),
        _week_review(macro_sentiment, sector_pred_df),
        _sector_playbook(sector_pred_df),
        _buy_watchlist(signals_df, n=10),
        _sell_watchlist(signals_df, n=5),
        _sector_scorecard(sector_rotation_df),
        _dividend_report(dividend_df),
        _earnings_calendar(signals_df),
        _trade_ideas(signals_df, sector_pred_df),
        (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️  DISCLAIMER: Automated quant model output.\n"
            "Not financial advice. Always do your own research.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    ])
    return _split(body)


def _split(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > max_len and cur:
            chunks.append(cur.rstrip())
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks