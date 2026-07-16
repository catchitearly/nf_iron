# Nifty Iron Condor Backtest

Backtests a Nifty iron condor (sell 300pts OTM, hedge 400pts OTM) over a
hardcoded date range using Fyers 1-min historical data, entered at 09:45
around a strike frozen from the 09:30 spot price, marked to market every
minute until 15:00. Outputs a tabbed HTML dashboard (one tab per day).

## ⚠️ Please check before running

**Option symbol format** — I didn't have your `straddle_analyzer.py` file
in this session, so `symbol_builder.py` uses the standard Fyers v3
convention:
- Weekly: `NSE:NIFTY{YY}{MonthCode}{DD}{STRIKE}{CE/PE}` e.g. `NSE:NIFTY2670223500CE`
- Monthly: `NSE:NIFTY{YY}{MMM}{STRIKE}{CE/PE}` e.g. `NSE:NIFTY26JULE23500CE`

If your existing symbol-builder logic differs, just edit
`build_option_symbol()` in `symbol_builder.py` — every other file only
calls this one function, so it's a single-point fix. Easiest way to
confirm: run `python -c "from symbol_builder import build_option_symbol; from datetime import date; print(build_option_symbol(date(2026,7,2), True, 23500, 'CE'))"`
and check it matches a real symbol on Fyers.

## Files

| File | Purpose |
|---|---|
| `config.py` | **Edit this.** Date range, expiry, strikes, lot size, timings |
| `symbol_builder.py` | Builds the 4 option symbols from the frozen strike + expiry |
| `fyers_client.py` | Fyers historical API wrapper (retries, nearest-candle fallback) |
| `iron_condor_backtest.py` | Main backtest loop → writes `results.json` |
| `dashboard_generator.py` | Turns `results.json` into `docs/index.html` |
| `.github/workflows/run_backtest.yml` | Runs everything on GitHub Actions |

## Setup

1. Create a new GitHub repo, push this folder to it.
2. In repo **Settings → Secrets and variables → Actions**, add:
   - `FYERS_CLIENT_ID`
   - `FYERS_ACCESS_TOKEN`
3. Edit `config.py`:
   - `START_DATE` / `END_DATE`
   - `EXPIRY_DATE` + `IS_WEEKLY`
4. In repo **Settings → Pages**, set source to `main` branch, `/docs` folder — this publishes `docs/index.html` as your live dashboard URL.
5. Run manually: **Actions tab → Iron Condor Backtest → Run workflow** (or it runs automatically on every push to `main`).

## How each day is computed

1. Fetch NIFTY spot 1-min candles for the day.
2. Take the close of the 09:30 candle (nearest available if missing) → round to nearest 100 → **frozen strike**.
3. Build 4 legs around the frozen strike:
   - Sell Call @ frozen + 300, Buy Call @ frozen + 400
   - Sell Put @ frozen − 300, Buy Put @ frozen − 400
4. Entry price of each leg = close of its 09:45 candle (nearest available if missing).
5. Every minute from 09:45 to 15:00: mark-to-market all 4 legs (nearest-candle fallback per leg), pnl = entry credit − current cost to close, × (lot size × lots).
6. Days with no data at all (holidays, symbol errors) are skipped and logged.

## Local test (without GitHub Actions)

```bash
pip install -r requirements.txt
export FYERS_CLIENT_ID="your_id"
export FYERS_ACCESS_TOKEN="your_token"
python iron_condor_backtest.py
python dashboard_generator.py
open docs/index.html   # or just double-click it
```
