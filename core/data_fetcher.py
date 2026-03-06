import yfinance as yf
import pandas as pd
import time


def fetch_prices(tickers):
    """Retrieve the latest price for each ticker in *tickers*.

    Parameters
    ----------
    tickers : iterable or str
        A list (or any iterable) of ticker symbols. A single string is also
        accepted and will be treated as a one‑element list. Passing ``None``
        or an empty sequence will return an empty :class:`pandas.DataFrame`.

    Returns
    -------
    pandas.DataFrame
        A data frame with columns ``['ticker', 'price']``.  If no prices could
        be fetched the result will be empty.
    """

    # normalize input to a list so that callers can pass a string or other
    # iterable without accidentally iterating over the characters.  This also
    # prevents pandas from interpreting a dict-of-scalars later on, which was
    # the root cause of the CI failure.
    if tickers is None:
        tickers = []
    elif isinstance(tickers, str):
        tickers = [tickers]
    else:
        # cast to list to allow single-use generators, etc.
        try:
            tickers = list(tickers)
        except TypeError:
            # fallback if the object is not iterable at all
            tickers = [tickers]

    rows = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            price = stock.info.get("regularMarketPrice")

            if price is not None:
                rows.append({"ticker": ticker, "price": price})

        except Exception as e:
            # network errors, rate limits, etc. should not stop the loop
            print(f"Error fetching {ticker}: {e}")

        time.sleep(0.1)  # polite pause to avoid Yahoo throttling

    if len(rows) == 0:
        print("WARNING: No price data returned")
        return pd.DataFrame(columns=["ticker", "price"])

    # constructing from a list of dicts guarantees pandas will infer rows
    df = pd.DataFrame(rows)
    return df
