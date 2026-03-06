
import pandas as pd

def generate_signals(factors):
    if len(factors) == 0:
        return pd.DataFrame()
    return factors.sort_values("confidence", ascending=False)
