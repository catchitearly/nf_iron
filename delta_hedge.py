"""
Delta-hedges the iron condor with Nifty futures (spot used as the futures
proxy -- see NOTE below) to smooth out the intraday PnL whipsaws that come
from unhedged gamma/delta exposure.

Approach
--------
Each minute:
  1. For every leg, back out the *implied vol* from its current market
     price (BSM, pure python bisection -- no scipy/numpy).
  2. Use that IV to compute the leg's delta (N(d1) for calls, N(d1)-1 for
     puts), signed for BUY/SELL, scaled by qty -> this leg's contribution
     to position delta (in underlying shares/units).
  3. Sum all 4 legs -> option_position_delta.
  4. total_delta = option_position_delta + current_hedge_position
     (futures delta is ~1 per unit, so the hedge just adds directly).
  5. If abs(total_delta) exceeds the configured band, trade futures to
     bring total_delta back to (near) zero. Trade size is rounded to the
     nearest lot, since futures only trade in whole lots.
  6. Mark the *existing* hedge position to market against the minute's
     spot move (standard replication bookkeeping: pnl added this minute
     = hedge_position_before_this_minute * (spot_now - spot_prev)),
     THEN apply any new trade from step 5 for the next minute.

NOTE on the futures proxy: this uses the NIFTY *spot* price series as a
stand-in for the futures price. Futures normally trade at a small
premium/discount (basis) to spot that decays to zero at expiry. Ignoring
basis is a simplification -- fine for illustrating whipsaw reduction,
but if you want basis-accurate hedge PnL, fetch the actual NIFTY futures
1-min candles for the same day/expiry and swap out `spot_price_map` for
that instead; nothing else in this module needs to change.

Time-to-expiry and risk-free rate are read from config (RISK_FREE_RATE,
and EXPIRY_DATE/EXPIRY_CLOSE_TIME for T). Nothing here needs
numpy/pandas.
"""
import math
import datetime as dt

import config


# ----------------------------------------------------------------------
# Pure-python normal distribution helpers (Abramowitz & Stegun 26.2.17,
# same family of approximation used elsewhere in your pure-python code)
# ----------------------------------------------------------------------
def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf(x):
    # Abramowitz & Stegun approximation, accurate to ~7.5e-8
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)


# ----------------------------------------------------------------------
# Black-Scholes (no dividend yield -- fine for index options over a
# single day/week; add a `q` term yourself if you need it)
# ----------------------------------------------------------------------
def bsm_price(S, K, T, r, sigma, opt_type):
    if T <= 0 or sigma <= 0:
        intrinsic = (S - K) if opt_type == "CE" else (K - S)
        return max(intrinsic, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type == "CE":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bsm_delta(S, K, T, r, sigma, opt_type):
    if T <= 0 or sigma <= 0:
        # expired/degenerate: delta collapses to 0 or 1 depending on moneyness
        if opt_type == "CE":
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    if opt_type == "CE":
        return norm_cdf(d1)
    else:
        return norm_cdf(d1) - 1.0


def implied_vol(price, S, K, T, r, opt_type, lo=0.001, hi=5.0, tol=1e-4, max_iter=60):
    """
    Bisection solve for sigma such that bsm_price(...) == price.
    Returns None if T<=0 or price is below intrinsic (degenerate/expired).
    """
    if T <= 0 or price is None or price <= 0:
        return None
    intrinsic = max((S - K) if opt_type == "CE" else (K - S), 0.0)
    if price < intrinsic:
        return None

    p_lo = bsm_price(S, K, T, r, lo, opt_type)
    p_hi = bsm_price(S, K, T, r, hi, opt_type)
    if price <= p_lo:
        return lo
    if price >= p_hi:
        return hi

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        p_mid = bsm_price(S, K, T, r, mid, opt_type)
        if abs(p_mid - price) < tol:
            return mid
        if p_mid > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


# ----------------------------------------------------------------------
# Time to expiry
# ----------------------------------------------------------------------
def time_to_expiry_years(trade_date, hhmm, expiry_date):
    h, m = map(int, hhmm.split(":"))
    current_dt = dt.datetime(trade_date.year, trade_date.month, trade_date.day, h, m)
    expiry_dt = dt.datetime(
        expiry_date.year, expiry_date.month, expiry_date.day,
        *map(int, config.MARKET_CLOSE.split(":"))
    )
    seconds = (expiry_dt - current_dt).total_seconds()
    years = seconds / (365.0 * 24 * 3600)
    # floor at ~1 minute so bisection/BSM never divides by ~0
    return max(years, 1.0 / (365.0 * 24 * 60))


# ----------------------------------------------------------------------
# Position delta at a single minute
# ----------------------------------------------------------------------
LEG_SIGN = {
    "sell_call": -1, "buy_call": +1,
    "sell_put": -1, "buy_put": +1,
}


def position_delta_at(spot, leg_prices, leg_meta, trade_date, hhmm, expiry_date, r):
    """
    leg_prices: {leg_name: current_option_price}
    leg_meta:   {leg_name: {"strike":.., "opt_type": "CE"/"PE"}}
    Returns net option position delta in underlying units (already scaled
    by config.QTY), plus a per-leg breakdown for debugging/inspection.
    """
    T = time_to_expiry_years(trade_date, hhmm, expiry_date)
    per_leg = {}
    net_delta_per_unit = 0.0
    for leg_name, price in leg_prices.items():
        strike = leg_meta[leg_name]["strike"]
        opt_type = leg_meta[leg_name]["opt_type"]
        iv = implied_vol(price, spot, strike, T, r, opt_type)
        if iv is None:
            # degenerate (deep ITM/expired pricing) -- fall back to
            # intrinsic-based delta so we don't crash the hedge loop
            delta = bsm_delta(spot, strike, T, r, 0.0001, opt_type)
        else:
            delta = bsm_delta(spot, strike, T, r, iv, opt_type)
        signed_delta = LEG_SIGN[leg_name] * delta
        per_leg[leg_name] = {"iv": iv, "delta": delta, "signed_delta": signed_delta}
        net_delta_per_unit += signed_delta

    net_delta_units = net_delta_per_unit * config.QTY
    return net_delta_units, per_leg


# ----------------------------------------------------------------------
# Full-day hedge simulation
# ----------------------------------------------------------------------
def run_delta_hedge_for_day(trade_date, minute_grid, spot_lookup, leg_price_lookup,
                             leg_meta, unhedged_pnl_series, expiry_date):
    """
    spot_lookup(hhmm) -> spot price (nearest-fallback already applied upstream)
    leg_price_lookup(leg_name, hhmm) -> option price for that leg/minute

    Returns:
      hedged_pnl_series: [{"time":.., "pnl":.., "hedged_pnl":..}, ...]
      hedge_trades: [{"time":.., "trade_qty":.., "spot":.., "net_delta_before":..}, ...]
      final_hedge_pnl, final_hedged_pnl
    """
    if not config.DELTA_HEDGE_ENABLED or not minute_grid:
        return [], [], 0.0, (unhedged_pnl_series[-1]["pnl"] if unhedged_pnl_series else None)

    if config.DELTA_BAND_LOTS < 1.0:
        print(
            "  [warn] DELTA_BAND_LOTS=%.2f is below 1.0 -- since hedge trades "
            "always round up to a whole lot, this will likely overshoot the "
            "imbalance and flip-flop every minute instead of smoothing PnL."
            % config.DELTA_BAND_LOTS
        )

    band_units = config.DELTA_BAND_LOTS * config.LOT_SIZE
    r = config.RISK_FREE_RATE

    hedge_position = 0.0     # in underlying units (+long / -short futures)
    hedge_pnl_cum = 0.0
    prev_spot = spot_lookup(minute_grid[0])

    hedge_trades = []
    hedged_series = []

    unhedged_by_time = {p["time"]: p["pnl"] for p in unhedged_pnl_series}

    for hhmm in minute_grid:
        spot = spot_lookup(hhmm)
        if spot is None:
            continue

        # 1) mark existing hedge position to market against this minute's move
        hedge_pnl_cum += hedge_position * (spot - prev_spot)
        prev_spot = spot

        # 2) recompute option position delta at this minute
        leg_prices = {leg_name: leg_price_lookup(leg_name, hhmm) for leg_name in leg_meta}
        if any(p is None for p in leg_prices.values()):
            continue
        option_delta, _ = position_delta_at(
            spot, leg_prices, leg_meta, trade_date, hhmm, expiry_date, r
        )

        total_delta = option_delta + hedge_position

        # 3) rehedge only if outside the configured band
        if abs(total_delta) > band_units:
            trade_qty_raw = -total_delta
            # futures only trade in whole lots -- round AWAY from zero
            # (ceiling on magnitude) so a triggered hedge always trades
            # at least 1 lot. Rounding to nearest would let a small
            # breach round down to 0 lots and silently cancel the trade.
            lots_needed = math.ceil(abs(trade_qty_raw) / config.LOT_SIZE)
            sign = 1.0 if trade_qty_raw > 0 else -1.0
            trade_qty = sign * lots_needed * config.LOT_SIZE
            if trade_qty != 0:
                hedge_position += trade_qty
                hedge_trades.append({
                    "time": hhmm,
                    "trade_qty": trade_qty,
                    "spot": round(spot, 2),
                    "net_delta_before": round(total_delta, 1),
                    "hedge_position_after": round(hedge_position, 1),
                })

        unhedged_pnl = unhedged_by_time.get(hhmm)
        hedged_pnl = None
        if unhedged_pnl is not None:
            hedged_pnl = round(unhedged_pnl + hedge_pnl_cum, 2)

        hedged_series.append({
            "time": hhmm,
            "hedge_pnl": round(hedge_pnl_cum, 2),
            "hedged_pnl": hedged_pnl,
        })

    final_hedge_pnl = hedged_series[-1]["hedge_pnl"] if hedged_series else 0.0
    final_hedged_pnl = hedged_series[-1]["hedged_pnl"] if hedged_series else None
    return hedged_series, hedge_trades, final_hedge_pnl, final_hedged_pnl
