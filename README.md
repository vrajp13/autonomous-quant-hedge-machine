# 🏦 Autonomous Quant Hedge Engine

> **Goldman-style multi-factor stock & sector scanner.**
> Dynamically fetches the live S&P 500 + Nasdaq-100 on every run,
> analyses every ticker across 7 factor layers, and predicts which
> sectors to overweight/underweight using a 3-layer model.
> Delivers results directly to Telegram — daily and weekly.

---

## 🆕 What's New

| Feature | Detail |
|---|---|
| **Live Universe** | Fetches S&P 500 (~503 tickers) + Nasdaq-100 from Wikipedia on every run — no stale CSV |
| **Auto sector tagging** | GICS sector names mapped automatically; BRK.B → BRK-B fixed |
| **Fallback** | If network fails, gracefully falls back to `data/tickers.csv` |
| **Sector Predictor** | 3-layer model: bottom-up stocks + ETF technicals + macro regime |
| **Sector Playbook** | Weekly report includes full per-sector breakdown with rotate-in/out calls |

---

## 🧠 Analysis Layers

### Per-Ticker Signals (7 layers → composite score −10 to +10)

| Layer | What It Computes |
|---|---|
| **Technical** | RSI(14), MACD, Bollinger %B, 21d/63d momentum, volume surge, ATR, 52-week position |
| **Fundamental** | Forward P/E, PEG, ROE, rev & EPS growth, analyst target upside, short interest |
| **News Sentiment** | 80+ bullish/bearish/geopolitical keywords scored across headlines |
| **Insider Activity** | SEC Form 4 cluster buy/sell detection |
| **Earnings Calendar** | Flags tickers reporting within 14 days as catalyst events |
| **Macro** | VIX fear gauge, SPY vs 200-SMA, % sectors above 50-SMA |
| **Dividends** | Yield, payout safety, earnings cover, consistency, balance sheet |

### Sector Prediction (3-layer model → sector score −10 to +10)

```
LAYER 1 — Bottom-Up (40%)
  Aggregates all ticker signals within each sector
  ├─ Market-cap-weighted composite score
  ├─ % bullish vs % bearish tickers
  ├─ Avg RSI, sentiment, insider activity
  └─ Earnings catalyst density

LAYER 2 — ETF Technicals (35%)
  Analyses the sector ETF (XLK, XLF, …) price data
  ├─ Momentum: 1-month, 3-month, 6-month
  ├─ Relative strength vs SPY (alpha)
  ├─ RSI (sector-level overbought/oversold)
  └─ Position vs 50-SMA & 200-SMA

LAYER 3 — Macro Regime Overlay (25%)
  Adjusts sector scores based on current market regime
  ├─ RISK-ON  → favours Tech, Discretionary, Financials
  ├─ RISK-OFF → favours Utilities, Staples, Healthcare
  └─ Neutral  → no adjustment
```

**Sector Signals:** `🟢 STRONG OVERWEIGHT → 🟢 OVERWEIGHT → ⚪ NEUTRAL → 🔴 UNDERWEIGHT → 🔴 STRONG UNDERWEIGHT`

**Rotation Calls:** `🚀 ROTATE IN | ⏸️ HOLD | ⚠️ ROTATE OUT`

---

## 📁 Project Structure

```
├── main.py                             # Orchestrator
├── conftest.py                         # pytest path config
├── requirements.txt
├── data/
│   └── tickers.csv                     # Static fallback (used if network fails)
├── core/
│   ├── universe.py                     # 🆕 Dynamic S&P500+NDX100 universe fetcher
│   ├── data_fetcher.py                 # OHLCV + fundamentals + news + earnings
│   ├── factors.py                      # Technical & fundamental scoring
│   ├── news_sentiment.py               # Headline sentiment + macro context
│   ├── insider_tracker.py              # SEC Form 4 insider signals
│   ├── dividend_screener.py            # Dividend quality scoring
│   └── sector_predictor.py             # 🆕 3-layer sector prediction engine
├── signals/
│   └── signal_model.py                 # Weighted composite signal synthesis
├── reports/
│   ├── daily_report.py                 # 🆕 Includes sector forecast section
│   └── weekly_report.py                # 🆕 Includes full sector playbook
├── notifier/
│   └── telegram_alerts.py              # Chunking + retry + rate-limit handling
├── tests/
│   ├── test_data_fetcher.py
│   ├── test_factors.py
│   ├── test_universe.py                # 🆕 Dynamic universe tests (mocked network)
│   └── test_sector_predictor.py        # 🆕 3-layer predictor tests
└── .github/workflows/
    └── quant_engine.yml
```

---

## 📲 Telegram Output

### Daily Scan (every 3 hours Mon–Fri)
```
🏦 QUANT HEDGE ENGINE — DAILY SCAN
🕐 2025-05-28 15:00 UTC
🌐 Universe: 503 stocks across 11 sectors (live S&P 500 + Nasdaq-100)

📊 MARKET PULSE
━━━━━━━━━━━━━━━━━━━━━
Regime:   RISK-ON 🟢
VIX:      16.40 — CALM
Trend:    BULL MARKET (above 200-SMA)
Breadth:  72.7% of sectors above 50-SMA

🔭 SECTOR FORECAST
━━━━━━━━━━━━━━━━━━━━━
▲ OVERWEIGHT:
  🟢 Technology               Score: 7.2 | 🚀 ROTATE IN | Picks: NVDA, MSFT, AAPL
  🟢 Financials               Score: 3.1 | 🚀 ROTATE IN | Picks: JPM, GS, V
▼ UNDERWEIGHT:
  🔴 Utilities                Score: -5.8 | ⚠️ ROTATE OUT

🚀 TOP BUY SIGNALS
...
```

### Weekly Report (Fridays ~8:30 PM UTC)
Full deep-analysis including the complete **Sector Playbook** — every sector broken down with:
- Bottom-up stock signal aggregation
- ETF momentum and relative strength vs SPY
- Macro regime overlay score
- Top 3 picks per sector
- Key risk factors

---

## ⚙️ How the Dynamic Universe Works

```python
# Every run fetches fresh data — no manual ticker list updates needed
run_pipeline()
  │
  ├─► Wikipedia S&P 500 table  → ~503 tickers with GICS sector tags
  ├─► Wikipedia Nasdaq-100     → ~100 tickers (adds NDX-only names like MSTR)
  ├─► Supplement list          → sector ETFs, bonds, commodities, ^VIX
  ├─► De-duplicate             → S&P 500 sector tag takes priority
  └─► Fallback                 → data/tickers.csv if network fails
```

---

## 🚀 Setup

### 1. Telegram Bot
1. Open Telegram → search **@BotFather** → `/newbot` → save **BOT TOKEN**
2. Search **@userinfobot** → `/start` → save your **CHAT ID**

### 2. GitHub Secrets
**Settings → Secrets → Actions → New secret**

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID from @userinfobot |

### 3. Deploy
```bash
git add .
git commit -m "feat: dynamic universe + sector predictor"
git push origin main
```
Go to **Actions** tab → enable workflows if prompted.

### 4. Local Testing
```bash
pip install -r requirements.txt
python main.py --test     # stdout only, no Telegram
python main.py --daily    # force daily scan + Telegram
python main.py --weekly   # force full weekly report + Telegram
pytest tests/ -v          # run all tests (no network required)
```

---

## ⏰ Schedule

| Cron | Time (UTC) | Action |
|---|---|---|
| `0 9,12,15,18,21 * * 1-5` | Every 3 hrs, Mon–Fri | Daily scan |
| `30 20 * * 5` | Friday 8:30 PM | Full weekly report |

---

## ⚠️ Disclaimer

For **educational and informational purposes only.**
This is not financial advice. Always perform your own due diligence.