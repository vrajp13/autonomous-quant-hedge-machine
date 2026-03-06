
import pandas as pd

def get_universe():
    df = pd.read_csv("data/tickers.csv")
    return df['ticker'].tolist()
