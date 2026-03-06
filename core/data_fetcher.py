import yfinance as yf
import pandas as pd

def fetch_prices(tickers):

    data = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            price = stock.history(period="1d")["Close"].iloc[-1]

            data.append({
                "ticker": ticker,
                "price": price
            })

        except Exception:
            continue

    return pd.DataFrame(data)
