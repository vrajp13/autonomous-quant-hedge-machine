import yfinance as yf
import pandas as pd
import time


def fetch_prices(tickers):
    rows = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            price = stock.info.get("regularMarketPrice")

            if price is not None:
                rows.append({
                    "ticker": ticker,
                    "price": price
                })

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")

        time.sleep(0.1)  # prevent Yahoo throttling

    if len(rows) == 0:
        print("WARNING: No price data returned")
        return pd.DataFrame(columns=["ticker", "price"])

    df = pd.DataFrame(rows)
    return df
