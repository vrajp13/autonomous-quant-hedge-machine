"""
daily_report.py – Daily / 3-hour scan report formatter.

Builds a Telegram-ready report covering:
  1. Market Pulse     – VIX, SPY trend, sector breadth
  2. Top BUY Signals  – Best candidates with key metrics
  3. Top SELL Signals – Bearish candidates
  4. Earnings Watch   – Tickers reporting in next 14 days
  5. Sector Heat Map  – 1-month sector performance ranking
  6. Top Dividend Picks
"""

from datetime import datetime, timezone


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

def _market_pulse_section(macro):
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━",
        "📊 MARKET PULSE",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"Overall: {macro.get('macro_sentiment', 'N/A')}",
        f"VIX: {_val(macro.get('vix'), 2)} — {macro.get('vix_label', 'N/A')}",
        f"S&P 500: {macro.get('spy_trend', 'N/A')}",
    ]
    b = macro.get("breadth_pct")
    lines.append(f"Sector Breadth: {b:.1f}% above 50-SMA" if b else "Sector Breadth: N/A")
    return "\n".join(lines)


def _signals_section(signals_df, label, emoji, n=7):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} TOP {label.upper()} SIGNALS",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if signals_df is None or signals_df.empty:
        lines.append(f"No {label.lower()} signals this scan.")
        return "\n".join(lines)

    for _, row in signals_df.head(n).iterrows():
        ticker  = row.get("ticker", "?")
        sector  = row.get("sector", "")
        price   = row.get("price")
        signal  = row.get("signal", "")
        conf    = row.get("confidence_pct")
        mom21   = row.get("momentum_21d_pct")
        rsi     = row.get("rsi")
        vol_r   = row.get("volume_ratio")
        upsid   = row.get("analyst_upside_pct")
        insider = row.get("top_insider_action", "")
        earn_im = row.get("earnings_imminent", False)
        earn_d  = row.get("earnings_date")

        lines += [
            f"🔹 {ticker} | ${_val(price, 2)}",
            f"   Signal: {signal}  Conf: {_val(conf, 1)}%",
            f"   Sector: {sector}",
            f"   RSI: {_val(rsi, 1)} | Mom-21d: {_pct(mom21)} | Vol×: {_val(vol_r, 1)}x",
        ]
        if upsid is not None:
            lines.append(f"   Analyst Upside: {_pct(upsid)}")
        if insider and "No" not in insider and "data" not in insider.lower():
            lines.append(f"   Insider: {insider}")
        if earn_im and earn_d:
            lines.append(f"   ⚡ Earnings Due: {earn_d}")
        lines.append("")

    return "\n".join(lines)


def _earnings_watch_section(signals_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "📅 EARNINGS WATCH (Next 14 Days)",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if signals_df is None or signals_df.empty or "earnings_imminent" not in signals_df.columns:
        lines.append("No upcoming earnings detected.")
        return "\n".join(lines)

    earn_df = signals_df[signals_df["earnings_imminent"] == True]
    if earn_df.empty:
        lines.append("No imminent earnings this scan.")
        return "\n".join(lines)

    for _, row in earn_df.iterrows():
        ticker = row.get("ticker", "?")
        days   = row.get("days_to_earnings")
        date   = row.get("earnings_date", "?")
        signal = row.get("signal", "")
        dstr   = f"in {days}d" if days is not None else ""
        lines.append(f"  • {ticker} — {date} ({dstr}) | {signal}")

    return "\n".join(lines)


def _sector_rotation_section(sector_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🔄 SECTOR ROTATION (1-Month)",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if sector_df is None or sector_df.empty:
        lines.append("Sector data unavailable.")
        return "\n".join(lines)

    for i, (_, row) in enumerate(sector_df.iterrows()):
        medal  = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        sector = row.get("sector", "")
        r1m    = row.get("return_1m_pct")
        trend  = row.get("trend", "")
        lines.append(f"{medal} {sector}: {_pct(r1m)} | {trend}")

    return "\n".join(lines)


def _dividend_section(dividend_df, n=5):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "💰 TOP DIVIDEND PICKS",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if dividend_df is None or dividend_df.empty:
        lines.append("No dividend data available.")
        return "\n".join(lines)

    for _, row in dividend_df.head(n).iterrows():
        ticker = row.get("ticker", "?")
        yld    = row.get("div_yield_pct")
        rate   = row.get("div_rate_annual")
        payout = row.get("payout_ratio_pct")
        grade  = row.get("dividend_grade", "")
        label  = row.get("dividend_label", "")
        lines.append(
            f"  {label} {ticker} — Yield: {_val(yld, 2)}% | "
            f"Rate: ${_val(rate, 2)}/yr | Payout: {_val(payout, 1)}% | Grade: {grade}"
        )

    return "\n".join(lines)


# ── Main assembler ─────────────────────────────────────────────────────────

def build_daily_report(signals_df, macro_sentiment, sector_rotation_df, dividend_df):
    """
    Build the complete daily scan report.
    Returns a list of message chunks ≤ 4000 chars (Telegram limit).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    header = f"🏦 QUANT HEDGE ENGINE — DAILY SCAN\n🕐 {now}\n"

    bullish = (signals_df[signals_df["composite_score"] >= 1.0]
               if signals_df is not None and not signals_df.empty else None)
    bearish = (signals_df[signals_df["composite_score"] <= -1.0].sort_values("composite_score")
               if signals_df is not None and not signals_df.empty else None)

    sections = [
        header,
        _market_pulse_section(macro_sentiment),
        _signals_section(bullish, "BUY", "🚀"),
        _signals_section(bearish, "SELL / SHORT", "⚠️"),
        _earnings_watch_section(signals_df),
        _sector_rotation_section(sector_rotation_df),
        _dividend_section(dividend_df),
        "\n━━━━━━━━━━━━━━━━━━━━━\n⚠️ For informational purposes only. Not financial advice.",
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
