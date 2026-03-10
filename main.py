"""
main.py – Quant Hedge Engine orchestrator.

Modes
-----
  python main.py            → Daily scan (auto mode)
  python main.py --weekly   → Full weekly deep-report
  python main.py --daily    → Force daily scan
  python main.py --test     → Dry-run: stdout only, no Telegram

New in this version:
  • Dynamic universe: S&P 500 + Nasdaq-100 pulled live from Wikipedia
  • Sector prediction: 3-layer model (bottom-up stocks + ETF technicals + macro)
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
    get_universe_stats,
    invalidate_cache,
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
from core.sector_predictor import predict_sectors, get_sector_summary
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
    signals_df       : pd.DataFrame  ticker-level ranked signals
    macro_sentiment  : dict          VIX / SPY / breadth
    sector_rotation  : pd.DataFrame  1m/3m sector ETF performance
    sector_pred_df   : pd.DataFrame  3-layer sector prediction ranking
    dividend_df      : pd.DataFrame  top dividend picks
    fundamentals     : dict          raw fundamentals keyed by ticker
    universe_stats   : dict          summary of dynamic universe
    """
    # ── 1. Dynamic universe (live S&P 500 + Nasdaq-100 + supplements) ──────
    invalidate_cache()          # always fetch fresh on each run
    universe_df   = get_universe(instrument_types=["Stock", "ETF"])
    stock_tickers = get_stock_tickers()
    all_tickers   = get_all_tickers(include_indices=False)
    universe_stats = get_universe_stats()

    logger.info(
        "Universe: %d stocks across %d sectors | %d total instruments",
        universe_stats["total_stocks"],
        universe_stats["sectors"],
        universe_stats["total_instruments"],
    )

    # ── 2. Market data ─────────────────────────────────────────────────────
    price_history, fundamentals, news_map, earnings_map, insider_map = \
        fetch_market_data(all_tickers)

    # ── 3. Technical factors ───────────────────────────────────────────────
    logger.info("Computing technical factors …")
    tech_df = compute_technical_factors(price_history, stock_tickers)

    # ── 4. Fundamental factors ─────────────────────────────────────────────
    logger.info("Computing fundamental factors …")
    fund_df = compute_fundamental_factors(fundamentals)

    # ── 5. News sentiment ──────────────────────────────────────────────────
    logger.info("Computing sentiment scores …")
    sentiment_df = compute_sentiment_scores(news_map)

    # ── 6. Insider signals ─────────────────────────────────────────────────
    logger.info("Computing insider signals …")
    insider_df = compute_insider_scores(insider_map)

    # ── 7. Earnings proximity ──────────────────────────────────────────────
    logger.info("Computing earnings factors …")
    earnings_df = compute_earnings_factors(earnings_map)

    # ── 8. Composite ticker signals ────────────────────────────────────────
    logger.info("Generating composite signals …")
    signals_df = generate_signals(
        tech_df, fund_df, sentiment_df, insider_df, earnings_df, universe_df
    )

    # ── 9. Macro context — single shared download ──────────────────────────
    logger.info("Fetching macro/sector data (single shared download) …")
    macro_close     = fetch_macro_close()
    macro_sentiment = get_market_sentiment(close=macro_close)
    sector_rotation = get_sector_rotation(close=macro_close)

    # ── 10. Sector prediction (3-layer model) ──────────────────────────────
    logger.info("Running sector prediction model …")
    sector_pred_df = predict_sectors(signals_df, macro_close, macro_sentiment)

    # ── 11. Dividend picks ─────────────────────────────────────────────────
    logger.info("Screening dividend stocks …")
    div_tickers = get_dividend_candidate_tickers()
    div_fund    = {t: fundamentals[t] for t in div_tickers if t in fundamentals}
    dividend_df = get_top_dividend_picks(div_fund, n=10)

    logger.info(
        "Pipeline complete | Signals: %d | Top sector: %s | Macro: %s | Div picks: %d",
        len(signals_df),
        sector_pred_df.iloc[0].get("sector", "N/A") if not sector_pred_df.empty else "N/A",
        macro_sentiment.get("macro_sentiment", "?"),
        len(dividend_df),
    )

    return (signals_df, macro_sentiment, sector_rotation,
            sector_pred_df, dividend_df, fundamentals, universe_stats)


# ── Report dispatch ────────────────────────────────────────────────────────

def send_daily_report(signals_df, macro_sentiment, sector_rotation,
                      sector_pred_df, dividend_df, universe_stats):
    logger.info("Building daily report …")
    chunks = build_daily_report(
        signals_df, macro_sentiment, sector_rotation,
        sector_pred_df, dividend_df, universe_stats,
    )
    send_chunks(chunks)
    logger.info("Daily report sent (%d chunk(s)).", len(chunks))


def send_weekly_report(signals_df, macro_sentiment, sector_rotation,
                       sector_pred_df, dividend_df, universe_stats):
    logger.info("Building weekly report …")
    chunks = build_weekly_report(
        signals_df, macro_sentiment, sector_rotation,
        sector_pred_df, dividend_df, universe_stats,
    )
    send_chunks(chunks)
    logger.info("Weekly report sent (%d chunk(s)).", len(chunks))


# ── Entry point ────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Autonomous Quant Hedge Engine")
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
        mode = "daily"

    logger.info("Mode: %s  |  UTC: %s", mode.upper(), now.strftime("%Y-%m-%d %H:%M"))

    try:
        (signals_df, macro_sentiment, sector_rotation,
         sector_pred_df, dividend_df, fundamentals, universe_stats) = run_pipeline()
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
        send_daily_report(signals_df, macro_sentiment, sector_rotation,
                          sector_pred_df, dividend_df, universe_stats)
    elif mode == "weekly":
        send_weekly_report(signals_df, macro_sentiment, sector_rotation,
                           sector_pred_df, dividend_df, universe_stats)


if __name__ == "__main__":
    main()