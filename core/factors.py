
import pandas as pd
import numpy as np

def compute_factors(prices):
    results = []

    for t in prices.columns:
        s = prices[t].dropna()

        if len(s) < 50:
            continue

        momentum = s.iloc[-1] / s.iloc[-50] - 1
        vol = s.pct_change().std()
        ret = s.pct_change().mean()

        score = (momentum * 0.5) + (ret * 0.3) - (vol * 0.2)

        conf = 1 / (1 + np.exp(-score*5))

        results.append({
            "ticker": t,
            "momentum": momentum,
            "volatility": vol,
            "return": ret,
            "confidence": conf
        })

    return pd.DataFrame(results)
