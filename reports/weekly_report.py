"""
weekly_report.py – Friday end-of-week comprehensive report formatter.

Sections:
  1. Week in Review          – Market summary
  2. Top BUY Watchlist       – Top 10 picks with full detail
  3. Top SELL Watchlist      – Top 5 bearish picks
  4. Sector Scorecard        – 1-week & 1-month performance table
  5. Dividend Income Report  – Top 10 dividend stocks
  6. Upcoming Earnings       – Next-week earnings calendar
  7. Trade Ideas             – Actionable setups
"""

from datetime import datetime, timezone
import pandas as pd


def _pct(val, decimals=1):
    if val is None:
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{decimals}f}%"


def _val(val, decimals=2, suffix=""):
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}{suffix}"


# ── Section builders ───────────────────────────────────────────────────────

def _week_summary_section(macro, sector_df):
    best_s = worst_s = ""
    if sector_df is not None and not sector_df.empty and "return_1m_pct" in sector_df.columns:
        b = sector_df.iloc[0];  best_s  = f"{b['sector']} ({_pct(b.get('return_1m_pct'))})"
        w = sector_df.iloc[-1]; worst_s = f"{w['sector']} ({_pct(w.get('return_1m_pct'))})"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📰 WEEK IN REVIEW",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Market Regime: {macro.get('macro_sentiment', 'N/A')}",
        f"VIX: {_val(macro.get('vix'), 2)} — {macro.get('vix_label', 'N/A')}",
        f"Market Trend: {macro.get('spy_trend', 'N/A')}",
    ]
    b = macro.get("breadth_pct")
    if b: lines.append(f"Sector Breadth: {b:.1f}% above 50-SMA")
    if best_s:  lines.append(f"Best Sector  : {best_s}")
    if worst_s: lines.append(f"Worst Sector : {worst_s}")
    return "\n".join(lines)


def _signals_section(signals_df, label, emoji, n=10):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} WEEKLY {label.upper()} WATCHLIST",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if signals_df is None or signals_df.empty:
        lines.append(f"No {label.lower()} signals.")
        return "\n".join(lines)

    for rank, (_, row) in enumerate(signals_df.head(n).iterrows(), 1):
        ticker   = row.get("ticker", "?")
        sector   = row.get("sector", "")
        price    = row.get("price")
        signal   = row.get("signal", "")
        conf     = row.get("confidence_pct")
        mom21    = row.get("momentum_21d_pct")
        mom63    = row.get("momentum_63d_pct")
        rsi      = row.get("rsi")
        vol_r    = row.get("volume_ratio")
        upsid    = row.get("analyst_upside_pct")
        fwd_pe   = row.get("forward_pe")
        roe      = row.get("roe_pct")
        earn_gr  = row.get("earnings_growth_pct")
        rev_gr   = row.get("revenue_growth_pct")
        insider  = row.get("top_insider_action", "")
        headline = row.get("top_headline", "")
        earn_d   = row.get("earnings_date")
        earn_im  = row.get("earnings_imminent", False)
        beta     = row.get("beta")
        score    = row.get("composite_score")

        block = [
            f"{'─'*25}",
            f"#{rank}  {ticker}  |  ${_val(price, 2)}  |  {signal}",
            f"     Sector: {sector}   Beta: {_val(beta, 2)}",
            f"     Confidence: {_val(conf, 1)}%   Score: {_val(score, 2)}",
            f"     Technicals → RSI: {_val(rsi, 1)} | Mom-21d: {_pct(mom21)} | Mom-63d: {_pct(mom63)} | Vol×: {_val(vol_r, 1)}x",
        ]

        fund_parts = []
        if fwd_pe:   fund_parts.append(f"Fwd P/E: {_val(fwd_pe, 1)}")
        if roe:      fund_parts.append(f"ROE: {_val(roe, 1)}%")
        if earn_gr:  fund_parts.append(f"EPS Growth: {_pct(earn_gr)}")
        if rev_gr:   fund_parts.append(f"Rev Growth: {_pct(rev_gr)}")
        if fund_parts:
            block.append(f"     Fundamentals → {' | '.join(fund_parts)}")

        if upsid is not None:
            block.append(f"     Analyst Target Upside: {_pct(upsid)}")
        if insider and "No" not in insider and "data" not in insider.lower():
            block.append(f"     Insider Activity: {insider}")
        if earn_im and earn_d:
            block.append(f"     ⚡ Earnings: {earn_d}  ← CATALYST WATCH")
        elif earn_d:
            block.append(f"     Earnings: {earn_d}")
        if headline and len(headline) > 10:
            short_hl = headline[:100] + ("…" if len(headline) > 100 else "")
            block.append(f'     Latest News: "{short_hl}"')

        lines.extend(block)
        lines.append("")

    return "\n".join(lines)


def _sector_scorecard(sector_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🗺️ SECTOR SCORECARD",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'Sector':<22} {'1-Month':>8} {'3-Month':>9}  Trend",
        "─" * 54,
    ]

    if sector_df is None or sector_df.empty:
        lines.append("Sector data unavailable.")
        return "\n".join(lines)

    for _, row in sector_df.iterrows():
        sector = (row.get("sector", ""))[:21]
        r1m    = _pct(row.get("return_1m_pct"))
        r3m    = _pct(row.get("return_3m_pct"))
        trend  = row.get("trend", "")
        lines.append(f"{sector:<22} {r1m:>8} {r3m:>9}  {trend}")

    return "\n".join(lines)


def _dividend_report(dividend_df, n=10):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💰 WEEKLY DIVIDEND INCOME REPORT",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'#':<3} {'Ticker':<7} {'Yield':>6} {'Rate':>7} {'Payout':>8} {'Grade':<5} Label",
        "─" * 70,
    ]

    if dividend_df is None or dividend_df.empty:
        lines.append("No dividend data available.")
        return "\n".join(lines)

    for rank, (_, row) in enumerate(dividend_df.head(n).iterrows(), 1):
        ticker = row.get("ticker", "?")
        yld    = _val(row.get("div_yield_pct"), 2, "%")
        rate   = f"${_val(row.get('div_rate_annual'), 2)}"
        payout = _val(row.get("payout_ratio_pct"), 1, "%")
        grade  = row.get("dividend_grade", "")
        label  = row.get("dividend_label", "")
        lines.append(f"{rank:<3} {ticker:<7} {yld:>6} {rate:>7} {payout:>8} {grade:<5} {label}")

    lines += [
        "",
        "💡 Dividend Strategy Notes:",
        "  • Grade A+/A = Safe growing payers — ideal for income portfolios",
        "  • Grade B    = Good yield, monitor payout ratio trend closely",
        "  • Grade C/D  = Higher risk — verify earnings cover before buying",
        "  • REITs (O, SPG, AMT, CCI) distribute ≥90% of taxable income by law",
        "  • Sweet spot: Yield ≥2.5% | Payout ≤65% | ROE ≥10%",
    ]
    return "\n".join(lines)


def _upcoming_earnings_section(signals_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📅 UPCOMING EARNINGS — NEXT 7 DAYS",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if signals_df is None or signals_df.empty or "earnings_imminent" not in signals_df.columns:
        lines.append("No imminent earnings data.")
        return "\n".join(lines)

    earn_df = signals_df[signals_df["earnings_imminent"] == True]
    if earn_df.empty:
        lines.append("No earnings in next 7 days for tracked universe.")
        return "\n".join(lines)

    if "days_to_earnings" in earn_df.columns:
        earn_df = earn_df.sort_values("days_to_earnings")

    for _, row in earn_df.iterrows():
        ticker = row.get("ticker", "?")
        date   = row.get("earnings_date", "?")
        days   = row.get("days_to_earnings")
        signal = row.get("signal", "")
        mom21  = row.get("momentum_21d_pct")
        upsid  = row.get("analyst_upside_pct")
        dstr   = f"T-{days}d" if days is not None else ""
        lines.append(
            f"  ⚡ {ticker:<6} {date} ({dstr}) → {signal} | "
            f"Mom: {_pct(mom21)} | Analyst Upside: {_pct(upsid)}"
        )

    lines.append("\n  Strategy: Consider vol plays (straddles) 1–2 days before report.")
    return "\n".join(lines)


def _trade_ideas_section(signals_df, n=5):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 TRADE IDEAS FOR THE COMING WEEK",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  (Informational only — always apply your own risk management)",
    ]

    if signals_df is None or signals_df.empty:
        lines.append("No data available.")
        return "\n".join(lines)

    strong = signals_df[signals_df["signal"].str.contains("STRONG BUY", na=False)].head(n)
    if strong.empty:
        strong = signals_df[signals_df["composite_score"] >= 3].head(n)

    for _, row in strong.iterrows():
        ticker  = row.get("ticker", "?")
        price   = row.get("price")
        upsid   = row.get("analyst_upside_pct")
        rsi     = row.get("rsi")
        mom21   = row.get("momentum_21d_pct")
        earn_im = row.get("earnings_imminent", False)
        target  = None
        if price and upsid:
            target = round(float(price) * (1 + float(upsid) / 100), 2)

        lines += [
            f"  📌 {ticker}  (${_val(price, 2)})",
            f"     Entry Zone: ${_val(price, 2)}  Target: ${_val(target, 2) if target else 'See analyst consensus'}",
            f"     RSI: {_val(rsi, 1)} | Momentum: {_pct(mom21)}",
        ]
        if earn_im:
            lines.append("     ⚡ Pre-earnings setup — manage position size accordingly")
        lines.append("")

    return "\n".join(lines)


# ── Main assembler ─────────────────────────────────────────────────────────

def build_weekly_report(signals_df, macro_sentiment, sector_df, dividend_df):
    """
    Build the full weekly report.
    Returns list of message chunks ≤ 4000 chars each.
    """
    now  = datetime.now(timezone.utc)
    week = now.strftime("Week ending %A %d %B %Y")

    header = (
        f"📋 QUANT HEDGE ENGINE — WEEKLY REPORT\n"
        f"📆 {week}\n"
        f"🏦 Goldman-Style Multi-Factor Analysis\n"
    )

    bullish = (signals_df[signals_df["composite_score"] >= 1.0]
               if signals_df is not None and not signals_df.empty else None)
    bearish = (signals_df[signals_df["composite_score"] <= -1.0].sort_values("composite_score")
               if signals_df is not None and not signals_df.empty else None)

    sections = [
        header,
        _week_summary_section(macro_sentiment, sector_df),
        _signals_section(bullish, "BUY", "🚀", n=10),
        _signals_section(bearish, "SELL / SHORT", "⚠️", n=5),
        _sector_scorecard(sector_df),
        _dividend_report(dividend_df, n=10),
        _upcoming_earnings_section(signals_df),
        _trade_ideas_section(signals_df),
        (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️  DISCLAIMER: Generated by an automated quant model.\n"
            "Not financial advice. Always do your own research and\n"
            "consult a licensed financial advisor before trading.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
    ]

    return _split_message("\n".join(sections))


def _split_message(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks
