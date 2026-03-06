
import yfinance as yf
import pandas as pd

def fetch_prices(tickers):
    data = {}
    for t in tickers[:200]:
        try:
            df = yf.download(t, period="6mo", progress=False)
            if not df.empty:
                data[t] = df['Close']
        except:
            pass
    return pd.DataFrame(data)
