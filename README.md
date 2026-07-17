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

## Delta hedging (smooths the whipsaw)

`delta_hedge.py` adds a Nifty-futures delta hedge overlay to reduce the intraday PnL whipsaws that come from unhedged directional exposure:

- Every minute, it backs out each leg's **implied vol** from its live price (pure-python bisection), then computes each leg's **delta** and sums them into a net position delta.
- If `abs(net delta)` exceeds `config.DELTA_BAND_LOTS` (in lots), it trades Nifty futures (proxied by spot price — see note in the module docstring) to flatten it, rounding **up** to at least 1 whole lot.
- The hedge PnL is tracked separately and added to the option PnL to produce a `hedged_pnl` series alongside the original `pnl` series — both are plotted on the dashboard, plus diamond markers wherever a hedge trade fired.

**Important finding from testing:** don't set `DELTA_BAND_LOTS` below `1.0`. Since a hedge trade must round up to a full lot, a band narrower than 1 lot causes the hedge to *overshoot* the imbalance it's correcting and immediately breach the band in the other direction — this produced constant flip-flopping in testing that made PnL choppier, not smoother (confirmed: stdev of minute-to-minute PnL went from 33 to 90 in one test run).

Also worth knowing: with the default 300pt/400pt vertical spread structure at 15 lots, net position delta naturally stays well under 1 lot even on a 300-500pt trend day — each vertical spread's delta is self-limiting. That means at the default settings, the hedge may rarely or never trigger, which is actually the correct/honest answer for this specific structure — its delta risk is small. If you want to see the hedge more active, either widen the verticals (e.g. `SHORT_OFFSET=400`, `HEDGE_OFFSET=600`) or scale up `NUM_LOTS` so a lot's worth of delta becomes a smaller fraction of your total exposure. I validated the hedge mechanism itself works correctly at larger scale (100 lots): it cut the max intraday PnL swing roughly in half in a strong-trend synthetic test.

If the whipsaw you're seeing in your live 300/400 dashboard isn't explained by delta, it's more likely coming from gamma/vega/IV effects — a static delta hedge won't smooth those out; that would need a gamma-scalping or vega-hedge approach instead.


```bash
pip install -r requirements.txt
export FYERS_CLIENT_ID="your_id"
export FYERS_ACCESS_TOKEN="your_token"
python iron_condor_backtest.py
python dashboard_generator.py
open docs/index.html   # or just double-click it
```
