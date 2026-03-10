"""
universe.py – Dynamic ticker universe management.

Fetches the live S&P 500 constituent list from Wikipedia on every run,
augmented with Nasdaq-100 extras and a curated supplement of ETFs,
commodity trackers, bond ETFs and volatility indices.

Falls back to the static data/tickers.csv if any network fetch fails,
ensuring the pipeline always has a valid universe.

GICS sector names from Wikipedia are normalised to our internal names
(e.g. 'Information Technology' → 'Technology').
"""

import logging
import os
import time

import pandas as pd

logger = logging.getLogger(__name__)

_CSV_FALLBACK = os.path.join(os.path.dirname(__file__), "..", "data", "tickers.csv")

# ── GICS → internal sector name mapping ──────────────────────────────────
GICS_MAP = {
    "Information Technology":  "Technology",
    "Health Care":             "Healthcare",
    "Financials":              "Financials",
    "Consumer Discretionary":  "Consumer Discretionary",
    "Communication Services":  "Communication Services",
    "Industrials":             "Industrials",
    "Consumer Staples":        "Consumer Staples",
    "Energy":                  "Energy",
    "Utilities":               "Utilities",
    "Real Estate":             "Real Estate",
    "Materials":               "Materials",
}

# ── Sector ETF map ────────────────────────────────────────────────────────
SECTOR_ETF_MAP = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Healthcare":             "XLV",
    "Energy":                 "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Industrials":            "XLI",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Materials":              "XLB",
    "Communication Services": "XLC",
}

# ── Supplemental instruments always included (not in S&P 500) ─────────────
SUPPLEMENT = [
    # Broad market ETFs
    {"ticker": "SPY",  "sector": "ETF",        "instrument_type": "ETF",       "description": "S&P 500 ETF"},
    {"ticker": "QQQ",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Nasdaq-100 ETF"},
    {"ticker": "IWM",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Russell 2000 ETF"},
    {"ticker": "DIA",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Dow Jones ETF"},
    # Sector ETFs
    {"ticker": "XLK",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Technology Sector ETF"},
    {"ticker": "XLF",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Financials Sector ETF"},
    {"ticker": "XLV",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Healthcare Sector ETF"},
    {"ticker": "XLE",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Energy Sector ETF"},
    {"ticker": "XLY",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Consumer Discretionary ETF"},
    {"ticker": "XLP",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Consumer Staples ETF"},
    {"ticker": "XLI",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Industrials Sector ETF"},
    {"ticker": "XLU",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Utilities Sector ETF"},
    {"ticker": "XLRE", "sector": "ETF",        "instrument_type": "ETF",       "description": "Real Estate Sector ETF"},
    {"ticker": "XLB",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Materials Sector ETF"},
    {"ticker": "XLC",  "sector": "ETF",        "instrument_type": "ETF",       "description": "Communication Services ETF"},
    # Commodities
    {"ticker": "GLD",  "sector": "Commodities","instrument_type": "ETF",       "description": "Gold ETF"},
    {"ticker": "SLV",  "sector": "Commodities","instrument_type": "ETF",       "description": "Silver ETF"},
    {"ticker": "USO",  "sector": "Commodities","instrument_type": "ETF",       "description": "Oil ETF"},
    {"ticker": "UNG",  "sector": "Commodities","instrument_type": "ETF",       "description": "Natural Gas ETF"},
    {"ticker": "PDBC", "sector": "Commodities","instrument_type": "ETF",       "description": "Commodities ETF"},
    # Bonds
    {"ticker": "TLT",  "sector": "Bonds",      "instrument_type": "ETF",       "description": "20+ Yr Treasury ETF"},
    {"ticker": "IEF",  "sector": "Bonds",      "instrument_type": "ETF",       "description": "7-10 Yr Treasury ETF"},
    {"ticker": "HYG",  "sector": "Bonds",      "instrument_type": "ETF",       "description": "High Yield Bond ETF"},
    {"ticker": "LQD",  "sector": "Bonds",      "instrument_type": "ETF",       "description": "Investment Grade Bond ETF"},
    # Volatility
    {"ticker": "^VIX", "sector": "Volatility", "instrument_type": "Index",     "description": "CBOE Volatility Index"},
]


# ── Wikipedia fetch helpers ────────────────────────────────────────────────

def _fetch_sp500() -> pd.DataFrame:
    """
    Scrape the live S&P 500 constituent table from Wikipedia.
    Returns DataFrame with columns: ticker, sector, instrument_type, description.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        tables = pd.read_html(url, header=0)
        df     = tables[0]   # first table is the constituent list

        # Normalise column names (Wikipedia occasionally renames them)
        col_map = {}
        for col in df.columns:
            cl = col.lower().replace(" ", "").replace("-", "").replace("_", "")
            if cl in ("symbol", "ticker"):
                col_map[col] = "ticker"
            elif "sector" in cl:
                col_map[col] = "gics_sector"
            elif "security" in cl or "company" in cl or "name" in cl:
                col_map[col] = "description"
            elif "subindustry" in cl or "industry" in cl:
                col_map[col] = "sub_industry"
        df = df.rename(columns=col_map)

        # Keep only the columns we need
        for col in ["ticker", "gics_sector", "description"]:
            if col not in df.columns:
                df[col] = ""

        df = df[["ticker", "gics_sector", "description"]].copy()

        # Fix BRK.B → BRK-B (Yahoo Finance format)
        df["ticker"] = (df["ticker"]
                        .str.replace(r"\.", "-", regex=True)
                        .str.strip())

        # Map GICS → internal sector name
        df["sector"]          = df["gics_sector"].map(GICS_MAP).fillna(df["gics_sector"])
        df["instrument_type"] = "Stock"
        df = df.drop(columns=["gics_sector"])
        df = df[df["ticker"].str.len() > 0].reset_index(drop=True)

        logger.info("S&P 500: fetched %d tickers from Wikipedia", len(df))
        return df

    except Exception as exc:
        logger.warning("Wikipedia S&P 500 fetch failed: %s", exc)
        return pd.DataFrame()


def _fetch_nasdaq100() -> pd.DataFrame:
    """
    Scrape the Nasdaq-100 constituent list from Wikipedia.
    Returns same schema as _fetch_sp500(). Used to add high-growth names
    not in the S&P 500 (e.g. MSTR, DXCM).
    """
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    try:
        tables = pd.read_html(url, header=0)
        # Find the table that has a Ticker/Symbol column
        df = None
        for t in tables:
            cols_lower = [c.lower() for c in t.columns]
            if any(k in cols_lower for k in ("ticker", "symbol")):
                df = t
                break

        if df is None:
            return pd.DataFrame()

        col_map = {}
        for col in df.columns:
            cl = col.lower()
            if cl in ("ticker", "symbol"):
                col_map[col] = "ticker"
            elif "company" in cl or "security" in cl or "name" in cl:
                col_map[col] = "description"
            elif "sector" in cl or "industry" in cl:
                col_map[col] = "gics_sector"
        df = df.rename(columns=col_map)

        for col in ["ticker", "description", "gics_sector"]:
            if col not in df.columns:
                df[col] = ""

        df["ticker"]          = df["ticker"].str.replace(r"\.", "-", regex=True).str.strip()
        df["sector"]          = df["gics_sector"].map(GICS_MAP).fillna("Technology")
        df["instrument_type"] = "Stock"
        df = df[["ticker", "sector", "instrument_type", "description"]]
        df = df[df["ticker"].str.len() > 0].reset_index(drop=True)

        logger.info("Nasdaq-100: fetched %d tickers from Wikipedia", len(df))
        return df

    except Exception as exc:
        logger.warning("Wikipedia Nasdaq-100 fetch failed: %s", exc)
        return pd.DataFrame()


def _load_fallback() -> pd.DataFrame:
    """Load the static fallback CSV."""
    try:
        df = pd.read_csv(_CSV_FALLBACK)
        logger.info("Fallback CSV: loaded %d tickers", len(df))
        return df
    except Exception as exc:
        logger.error("Fallback CSV also failed: %s", exc)
        return pd.DataFrame(columns=["ticker", "sector", "instrument_type", "description"])


# ── Public API ─────────────────────────────────────────────────────────────

_CACHE: pd.DataFrame | None = None   # module-level cache (one fetch per process)


def get_universe(
    sectors=None,
    instrument_types=None,
    exclude_types=None,
    use_cache=True,
    include_sp500=True,
    include_nasdaq100=True,
) -> pd.DataFrame:
    """
    Build and return the full dynamic ticker universe.

    Fetch order:
      1. S&P 500 from Wikipedia (live)
      2. Nasdaq-100 from Wikipedia (live) — adds missing growth names
      3. Supplement list (ETFs, bonds, commodities, VIX)
      4. De-duplicate; if everything fails, fall back to static CSV.

    Parameters
    ----------
    sectors          : list[str] | None  Filter to these sectors after building.
    instrument_types : list[str] | None  Keep only these types.
    exclude_types    : list[str] | None  Drop these types.
    use_cache        : bool              Re-use result from previous call in same run.
    include_sp500    : bool
    include_nasdaq100: bool

    Returns
    -------
    pd.DataFrame  columns: ticker, sector, instrument_type, description
    """
    global _CACHE

    if use_cache and _CACHE is not None:
        df = _CACHE
    else:
        frames = []
        live_sources_succeeded = False

        if include_sp500:
            sp500 = _fetch_sp500()
            if not sp500.empty:
                frames.append(sp500)
                live_sources_succeeded = True

        if include_nasdaq100:
            nq100 = _fetch_nasdaq100()
            if not nq100.empty:
                frames.append(nq100)
                live_sources_succeeded = True

        # Only add supplement if at least one live source succeeded
        if live_sources_succeeded:
            frames.append(pd.DataFrame(SUPPLEMENT))

        if frames:
            df = pd.concat(frames, ignore_index=True)
            # De-duplicate: keep first occurrence (S&P 500 takes priority for sector)
            df = df.drop_duplicates(subset="ticker", keep="first")
            df = df.reset_index(drop=True)
        else:
            logger.warning("All live sources failed — loading static CSV fallback")
            df = _load_fallback()

        if df.empty:
            df = _load_fallback()

        # Ensure all required columns exist
        for col in ["ticker", "sector", "instrument_type", "description"]:
            if col not in df.columns:
                df[col] = ""

        logger.info("Universe built: %d total instruments", len(df))
        _CACHE = df

    # ── Apply filters ──────────────────────────────────────────────────────
    if sectors:
        df = df[df["sector"].isin(sectors)]
    if instrument_types:
        df = df[df["instrument_type"].isin(instrument_types)]
    if exclude_types:
        df = df[~df["instrument_type"].isin(exclude_types)]

    return df.reset_index(drop=True)


def invalidate_cache():
    """Force a fresh universe fetch on the next call."""
    global _CACHE
    _CACHE = None


def get_stock_tickers() -> list:
    """Return only equity tickers (no ETFs, no indices)."""
    return get_universe(instrument_types=["Stock"])["ticker"].tolist()


def get_all_tickers(include_indices=False) -> list:
    df = get_universe()
    if not include_indices:
        df = df[df["instrument_type"] != "Index"]
    return df["ticker"].tolist()


def get_sector_etf_tickers() -> list:
    return list(SECTOR_ETF_MAP.values())


def get_tickers_by_sector() -> dict:
    df = get_universe(instrument_types=["Stock"])
    return df.groupby("sector")["ticker"].apply(list).to_dict()


def get_ticker_metadata(ticker: str) -> dict:
    df = get_universe()
    row = df[df["ticker"] == ticker]
    return row.iloc[0].to_dict() if not row.empty else {}


def get_dividend_candidate_tickers() -> list:
    div_sectors = [
        "Consumer Staples", "Utilities", "Financials",
        "Energy", "Healthcare", "Industrials", "Real Estate",
    ]
    return get_universe(sectors=div_sectors, instrument_types=["Stock"])["ticker"].tolist()


def get_universe_stats() -> dict:
    """Return summary statistics about the current universe."""
    df = get_universe()
    stocks = df[df["instrument_type"] == "Stock"]
    return {
        "total_instruments": len(df),
        "total_stocks":      len(stocks),
        "total_etfs":        len(df[df["instrument_type"] == "ETF"]),
        "sectors":           stocks["sector"].nunique(),
        "sector_counts":     stocks.groupby("sector").size().to_dict(),
    }