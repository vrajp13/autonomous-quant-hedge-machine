"""
main.py – Quant Hedge Engine orchestrator.

Modes
-----
  python main.py            → Auto-detects mode (daily scan or weekly on Fridays)
  python main.py --weekly   → Force a full weekly report
  python main.py --daily    → Force a daily scan report
  python main.py --test     → Dry-run: print report to stdout, no Telegram

GitHub Actions calls this on schedule.
Weekly report is triggered exclusively by the dedicated Friday 20:30 UTC cron.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quant_engine")

# ── Imports ────────────────────────────────────────────────────────────────
from core.universe import (
    get_universe,
    get_stock_tickers,
    get_all_tickers,
    get_dividend_candidate_tickers,
)
from core.data_fetcher import fetch_market_data
from core.factors import (
    compute_technical_factors,
    compute_fundamental_factors,
    compute_earnings_factors,
)
from core.news_sentiment import (
    compute_sentiment_scores,
    fetch_macro_close,
    get_market_sentiment,
    get_sector_rotation,
)
from core.insider_tracker import compute_insider_scores
from core.dividend_screener import get_top_dividend_picks
from signals.signal_model import generate_signals
from reports.daily_report import build_daily_report
from reports.weekly_report import build_weekly_report
from notifier.telegram_alerts import send_chunks, send_telegram_message


# ── Pipeline ───────────────────────────────────────────────────────────────

def run_pipeline():
    """
    Execute the full multi-factor analysis pipeline.

    Returns
    -------
    signals_df      : pd.DataFrame  ranked composite signals
    macro_sentiment : dict          VIX / breadth / trend
    sector_df       : pd.DataFrame  sector rotation ranking
    dividend_df     : pd.DataFrame  top dividend picks
    fundamentals    : dict          raw fundamentals per ticker
    """
    # 1. Universe
    universe_df   = get_universe(instrument_types=["Stock", "ETF"])
    stock_tickers = get_stock_tickers()
    all_tickers   = get_all_tickers(include_indices=False)

    logger.info("Universe: %d stocks | %d total instruments",
                len(stock_tickers), len(all_tickers))

    # 2. Market data (OHLCV + fundamentals + news + earnings + insider)
    price_history, fundamentals, news_map, earnings_map, insider_map = \
        fetch_market_data(all_tickers)

    # 3. Technical factors
    logger.info("Computing technical factors …")
    tech_df = compute_technical_factors(price_history, stock_tickers)

    # 4. Fundamental factors
    logger.info("Computing fundamental factors …")
    fund_df = compute_fundamental_factors(fundamentals)

    # 5. News sentiment
    logger.info("Computing sentiment scores …")
    sentiment_df = compute_sentiment_scores(news_map)

    # 6. Insider signals
    logger.info("Computing insider signals …")
    insider_df = compute_insider_scores(insider_map)

    # 7. Earnings proximity
    logger.info("Computing earnings factors …")
    earnings_df = compute_earnings_factors(earnings_map)

    # 8. Composite signals
    logger.info("Generating composite signals …")
    signals_df = generate_signals(
        tech_df, fund_df, sentiment_df, insider_df, earnings_df, universe_df
    )

    # 9. Macro context — single shared download for VIX + SPY + sector ETFs
    logger.info("Fetching macro/sector data (single download) …")
    macro_close     = fetch_macro_close()
    macro_sentiment = get_market_sentiment(close=macro_close)
    sector_df       = get_sector_rotation(close=macro_close)

    # 10. Dividend picks
    logger.info("Screening dividend stocks …")
    div_fund    = {t: fundamentals[t] for t in get_dividend_candidate_tickers()
                   if t in fundamentals}
    dividend_df = get_top_dividend_picks(div_fund, n=10)

    logger.info(
        "Pipeline complete. Signals: %d | Macro: %s | Dividend picks: %d",
        len(signals_df),
        macro_sentiment.get("macro_sentiment", "?"),
        len(dividend_df),
    )
    return signals_df, macro_sentiment, sector_df, dividend_df, fundamentals


# ── Report dispatch ────────────────────────────────────────────────────────

def send_daily_report(signals_df, macro_sentiment, sector_df, dividend_df):
    logger.info("Building daily report …")
    chunks = build_daily_report(signals_df, macro_sentiment, sector_df, dividend_df)
    send_chunks(chunks)
    logger.info("Daily report sent (%d chunk(s)).", len(chunks))


def send_weekly_report(signals_df, macro_sentiment, sector_df, dividend_df):
    logger.info("Building weekly report …")
    chunks = build_weekly_report(signals_df, macro_sentiment, sector_df, dividend_df)
    send_chunks(chunks)
    logger.info("Weekly report sent (%d chunk(s)).", len(chunks))


# ── Entry point ────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Quant Hedge Engine")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--daily",  action="store_true", help="Force daily scan")
    g.add_argument("--weekly", action="store_true", help="Force weekly report")
    g.add_argument("--test",   action="store_true", help="Dry-run (stdout only)")
    return p.parse_args()


def main():
    args = parse_args()
    now  = datetime.now(timezone.utc)

    if args.weekly:
        mode = "weekly"
    elif args.daily:
        mode = "daily"
    elif args.test:
        mode = "test"
    else:
        # Auto-mode: GitHub Actions sets mode via --daily or --weekly flag
        # based on the cron that fired (see quant_engine.yml)
        mode = "daily"

    logger.info("Mode: %s  |  UTC: %s", mode.upper(), now.strftime("%Y-%m-%d %H:%M"))

    try:
        signals_df, macro_sentiment, sector_df, dividend_df, fundamentals = run_pipeline()
    except Exception as exc:
        logger.critical("Pipeline failed: %s", exc, exc_info=True)
        send_telegram_message(f"🚨 Quant Engine pipeline error: {exc}")
        sys.exit(1)

    if signals_df.empty:
        msg = "⚠️ Quant Engine: No signals generated. Check logs."
        logger.warning(msg)
        send_telegram_message(msg)
        return

    if mode in ("daily", "test"):
        send_daily_report(signals_df, macro_sentiment, sector_df, dividend_df)
    elif mode == "weekly":
        send_weekly_report(signals_df, macro_sentiment, sector_df, dividend_df)


if __name__ == "__main__":
    main()
