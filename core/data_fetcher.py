import yfinance as yf
import pandas as pd


def fetch_prices(tickers):

    rows = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")

            if hist.empty:
                continue

            price = hist["Close"].iloc[-1]

            rows.append({
                "ticker": ticker,
                "price": float(price)
            })

        except Exception:
            continue

    return pd.DataFrame(rows)
