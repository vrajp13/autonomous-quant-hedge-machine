"""
daily_report.py – Daily / 3-hour scan Telegram report.

Sections
--------
  1. Header          – timestamp + universe size
  2. Market Pulse    – VIX, SPY trend, sector breadth
  3. Sector Forecast – Top 3 OVERWEIGHT / bottom 2 UNDERWEIGHT (from predictor)
  4. Top BUY Signals – Best 7 picks with metrics
  5. Top SELL Alerts – Worst 5 bearish tickers
  6. Earnings Watch  – Tickers reporting in ≤14 days
  7. Sector Rotation – 1-month ETF performance table
  8. Dividend Picks  – Top 5 income ideas
"""

from datetime import datetime, timezone


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
    now      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_stocks = universe_stats.get("total_stocks", "?")
    n_sec    = universe_stats.get("sectors", "?")
    return (
        f"🏦 QUANT HEDGE ENGINE — DAILY SCAN\n"
        f"🕐 {now}\n"
        f"🌐 Universe: {n_stocks} stocks across {n_sec} sectors (live S&P 500 + Nasdaq-100)"
    )


def _market_pulse(macro):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "📊 MARKET PULSE",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"Regime:   {macro.get('macro_sentiment', 'N/A')}",
        f"VIX:      {_val(macro.get('vix'), 2)} — {macro.get('vix_label', 'N/A')}",
        f"Trend:    {macro.get('spy_trend', 'N/A')}",
    ]
    b = macro.get("breadth_pct")
    lines.append(f"Breadth:  {b:.1f}% of sectors above 50-SMA" if b else "Breadth: N/A")
    return "\n".join(lines)


def _sector_forecast(sector_pred_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🔭 SECTOR FORECAST",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    if sector_pred_df is None or sector_pred_df.empty:
        lines.append("Sector prediction unavailable.")
        return "\n".join(lines)

    # Ensure 'sector' column exists
    if "sector" not in sector_pred_df.columns:
        sector_pred_df["sector"] = "Unknown"

    overweight  = sector_pred_df[sector_pred_df["sector_score"] >= 2].head(3)
    underweight = sector_pred_df[sector_pred_df["sector_score"] <= -2].tail(2)

    lines.append("▲ OVERWEIGHT:")
    if overweight.empty:
        lines.append("  No strong overweight calls today")
    for _, row in overweight.iterrows():
        picks = ", ".join(row.get("top_picks", [])) or "—"
        lines.append(
            f"  🟢 {row['sector']:<24} Score: {_val(row['sector_score'],1)} | "
            f"{row['rotation_call']} | Picks: {picks}"
        )

    lines.append("▼ UNDERWEIGHT:")
    if underweight.empty:
        lines.append("  No strong underweight calls today")
    for _, row in underweight.iterrows():
        lines.append(
            f"  🔴 {row['sector']:<24} Score: {_val(row['sector_score'],1)} | "
            f"{row['rotation_call']}"
        )

    return "\n".join(lines)


def _signals_section(signals_df, label, emoji, bullish=True, n=7):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} TOP {label.upper()}",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    if signals_df is None or signals_df.empty:
        lines.append(f"No {label.lower()} signals.")
        return "\n".join(lines)

    subset = (
        signals_df[signals_df["composite_score"] >= 1.0].head(n) if bullish
        else signals_df[signals_df["composite_score"] <= -1.0]
                       .sort_values("composite_score").head(n)
    )

    for _, row in subset.iterrows():
        earn_str = ""
        if row.get("earnings_imminent"):
            earn_str = f"\n   ⚡ Earnings: {row.get('earnings_date','?')}"
        insider = row.get("top_insider_action", "")
        ins_str = f"\n   👤 Insider: {insider}" if insider and "No" not in insider else ""

        lines += [
            f"🔹 {row.get('ticker','?')} | ${_val(row.get('price'),2)} | {row.get('signal','')}",
            f"   Sector: {row.get('sector','')}  Conf: {_val(row.get('confidence_pct'),1)}%",
            f"   RSI:{_val(row.get('rsi'),1)} Mom-21d:{_pct(row.get('momentum_21d_pct'))} "
            f"Vol×:{_val(row.get('volume_ratio'),1)}x Upside:{_pct(row.get('analyst_upside_pct'))}",
            f"{earn_str}{ins_str}",
            "",
        ]
    return "\n".join(lines)


def _earnings_watch(signals_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "📅 EARNINGS WATCH (≤14 days)",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    if signals_df is None or signals_df.empty or "earnings_imminent" not in signals_df.columns:
        lines.append("No imminent earnings detected.")
        return "\n".join(lines)

    df = signals_df[signals_df["earnings_imminent"] == True]
    if df.empty:
        lines.append("No imminent earnings in current universe.")
        return "\n".join(lines)

    if "days_to_earnings" in df.columns:
        df = df.sort_values("days_to_earnings")

    for _, row in df.iterrows():
        d = row.get("days_to_earnings")
        lines.append(
            f"  ⚡ {row.get('ticker','?'):<6} "
            f"{row.get('earnings_date','?')} (T-{d}d) | "
            f"{row.get('signal','')} | Mom: {_pct(row.get('momentum_21d_pct'))}"
        )
    return "\n".join(lines)


def _sector_rotation(sector_rotation_df):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "🔄 SECTOR ROTATION (1-Month)",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    if sector_rotation_df is None or sector_rotation_df.empty:
        lines.append("Sector ETF data unavailable.")
        return "\n".join(lines)

    for i, (_, row) in enumerate(sector_rotation_df.iterrows()):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        lines.append(
            f"{medal} {row.get('sector',''):<22} "
            f"{_pct(row.get('return_1m_pct'))} | {row.get('trend','')}"
        )
    return "\n".join(lines)


def _dividend_section(dividend_df, n=5):
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━",
        "💰 TOP DIVIDEND PICKS",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    if dividend_df is None or dividend_df.empty:
        lines.append("No dividend data.")
        return "\n".join(lines)

    for _, row in dividend_df.head(n).iterrows():
        lines.append(
            f"  {row.get('dividend_label','')} {row.get('ticker','?')} — "
            f"Yield:{_val(row.get('div_yield_pct'),2)}% "
            f"Payout:{_val(row.get('payout_ratio_pct'),1)}% "
            f"Grade:{row.get('dividend_grade','')}"
        )
    return "\n".join(lines)


# ── Assembler ──────────────────────────────────────────────────────────────

def build_daily_report(signals_df, macro_sentiment, sector_rotation_df,
                       sector_pred_df, dividend_df, universe_stats=None):
    """
    Build the daily scan report.  Returns list of ≤4000-char chunks.
    """
    universe_stats = universe_stats or {}
    body = "\n".join([
        _header(universe_stats),
        _market_pulse(macro_sentiment),
        _sector_forecast(sector_pred_df),
        _signals_section(signals_df, "BUY SIGNALS", "🚀", bullish=True,  n=7),
        _signals_section(signals_df, "SELL ALERTS", "⚠️", bullish=False, n=5),
        _earnings_watch(signals_df),
        _sector_rotation(sector_rotation_df),
        _dividend_section(dividend_df),
        "\n━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ Informational only. Not financial advice.",
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