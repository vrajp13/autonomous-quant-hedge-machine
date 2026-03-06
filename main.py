
import os
from core.universe import get_universe
from core.data_fetcher import fetch_prices
from core.factors import compute_factors
from signals.signal_model import generate_signals
from telegram.telegram_alerts import send_telegram_message

def run_engine():
    tickers = get_universe()
    prices = fetch_prices(tickers)
    factors = compute_factors(prices)
    signals = generate_signals(factors)

    if len(signals) == 0:
        send_telegram_message("No signals generated today.")
        return

    high_conf = signals[signals['confidence'] > 0.8]

    if len(high_conf) == 0:
        send_telegram_message("No high confidence signals today.")
        return

    msg = "🚨 High Confidence Signals 🚨\n"
    for _, r in high_conf.iterrows():
        msg += f"{r['ticker']} | score={r['confidence']:.2f}\n"

    send_telegram_message(msg)

if __name__ == "__main__":
    run_engine()
