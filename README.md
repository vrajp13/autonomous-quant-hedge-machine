# 🏦 Autonomous Quant Hedge Engine

> **Goldman-style multi-factor stock scanner** — analyses all S&P 500 sectors
> using technical, fundamental, sentiment, insider, and macro factors.
> Delivers daily 3-hour scans and a Friday weekly deep-analysis report
> directly to your Telegram bot.

---

## 🧠 What It Analyses

| Layer | What It Computes |
|---|---|
| **Technical** | RSI(14), MACD histogram, Bollinger %B, 21d & 63d momentum, volume surge ratio, ATR, 52-week position |
| **Fundamental** | Forward P/E, PEG ratio, ROE, revenue & earnings growth, analyst price target upside, short interest |
| **News Sentiment** | 80+ bullish/bearish/geopolitical keywords scored across yfinance headlines |
| **Insider Activity** | SEC Form 4 cluster buy/sell detection via yfinance insider_transactions |
| **Earnings Calendar** | Flags tickers reporting within 14 days as catalyst events |
| **Macro / VIX** | VIX fear gauge, SPY vs 200-SMA trend, % of sector ETFs above 50-SMA |
| **Sector Rotation** | 1-month & 3-month performance ranking across all 11 S&P sectors |
| **Dividend Screen** | Yield attractiveness, payout safety, earnings cover, consistency, balance sheet |

All layers are combined into a **composite score (−10 to +10)**:

```
🟢 STRONG BUY  |  🟢 BUY  |  🟡 MILD BUY  |  ⚪ NEUTRAL
🔴 MILD SELL   |  🔴 SELL |  🔴 STRONG SELL
```

---

## 📁 Repository Structure

```
├── main.py                             # Orchestrator (daily / weekly modes)
├── conftest.py                         # pytest root path configuration
├── requirements.txt
├── data/
│   └── tickers.csv                     # ~150 tickers across all sectors + ETFs
├── core/
│   ├── universe.py                     # Ticker universe management
│   ├── data_fetcher.py                 # OHLCV + fundamentals + news + earnings + insider
│   ├── factors.py                      # Technical & fundamental factor scoring
│   ├── news_sentiment.py               # Headline sentiment + macro VIX/breadth analysis
│   ├── insider_tracker.py              # SEC Form 4 insider signal detection
│   └── dividend_screener.py            # Multi-dimension dividend quality scoring
├── signals/
│   └── signal_model.py                 # Weighted composite signal synthesis
├── reports/
│   ├── daily_report.py                 # 3-hour scan Telegram formatter
│   └── weekly_report.py                # Friday deep-report formatter
├── notifier/
│   └── telegram_alerts.py              # Telegram Bot (chunking + retry + rate-limit)
├── tests/
│   ├── test_data_fetcher.py
│   └── test_factors.py
└── .github/workflows/
    └── quant_engine.yml                # GitHub Actions schedule
```

---

## 📲 Telegram Output

### Daily Scan (every 3 hours, Mon–Fri)
```
🏦 QUANT HEDGE ENGINE — DAILY SCAN
🕐 2025-05-28 15:00 UTC

━━━━━━━━━━━━━━━━━━━━━
📊 MARKET PULSE
━━━━━━━━━━━━━━━━━━━━━
Overall: RISK-ON 🟢
VIX: 16.40 — CALM
S&P 500: BULL MARKET (above 200-SMA)
Sector Breadth: 72.7% above 50-SMA

🚀 TOP BUY SIGNALS
━━━━━━━━━━━━━━━━━━━━━
🔹 NVDA | $875.40
   Signal: 🟢 STRONG BUY  Conf: 82.0%
   Sector: Technology
   RSI: 48.2 | Mom-21d: +6.8% | Vol×: 1.8x
   Analyst Upside: +18.4%
   Insider: 3 insider buy(s)
   ⚡ Earnings Due: 2025-05-28

💰 TOP DIVIDEND PICKS
━━━━━━━━━━━━━━━━━━━━━
  ⭐ Exceptional Dividend JNJ — Yield: 3.12% | Rate: $4.96/yr | Grade: A+
  🟢 Strong Dividend KO  — Yield: 2.81% | Rate: $1.94/yr | Grade: A
```

### Weekly Report (Fridays ~8:30 PM UTC)
Full deep-analysis: top 10 BUY/SELL picks with complete breakdowns,
sector scorecard table, dividend income report with strategy notes,
upcoming earnings calendar, and actionable trade ideas.

---

## ⚙️ Ticker Universe (~150 instruments)

| Category | Key Tickers |
|---|---|
| Technology | AAPL, MSFT, NVDA, GOOGL, META, AMD, AVGO, ORCL, CRM |
| Financials | JPM, GS, MS, BAC, V, MA, BLK, AXP |
| Healthcare | UNH, LLY, JNJ, PFE, ABBV, MRK, TMO, AMGN |
| Energy | XOM, CVX, COP, SLB, EOG, OXY, MPC |
| Consumer Disc. | AMZN, TSLA, HD, MCD, NKE, SBUX, BKNG |
| Consumer Staples | PG, KO, PEP, PM, COST, WMT |
| Industrials | CAT, HON, LMT, RTX, GE, UPS, BA, DE |
| Utilities | NEE, DUK, SO, D, AEP |
| Real Estate | AMT, PLD, CCI, EQIX, SPG, O |
| Materials | LIN, FCX, NEM, ALB |
| Comm. Services | NFLX, DIS, T, VZ, CMCSA |
| Sector ETFs | XLK, XLF, XLV, XLE, XLY, XLP, XLI, XLU, XLRE, XLB, XLC |
| Commodities | GLD, SLV, USO, UNG, PDBC |
| Bonds | TLT, IEF, HYG, LQD |

---

## 🚀 Setup

### 1. Telegram Bot
1. Open Telegram → search **@BotFather** → `/newbot` → save **BOT TOKEN**
2. Search **@userinfobot** → `/start` → save your **CHAT ID**

### 2. GitHub Secrets
**Settings → Secrets and variables → Actions → New secret**

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your chat ID |

### 3. Push & Enable
```bash
git add .
git commit -m "feat: quant hedge engine"
git push origin main
```
Go to **Actions** tab → enable workflows if prompted.

### 4. Manual Test
```bash
pip install -r requirements.txt
python main.py --test     # stdout only, no Telegram
python main.py --daily    # force daily scan
python main.py --weekly   # force weekly report
```

---

## ⏰ Schedule

| Cron | UTC Time | Report |
|---|---|---|
| `0 9,12,15,18,21 * * 1-5` | Every 3 hrs, Mon–Fri | Daily scan |
| `30 20 * * 5` | Friday 8:30 PM | Full weekly report |

---

## ⚠️ Disclaimer

For **educational and informational purposes only**.
Not financial advice. Always perform your own due diligence.
