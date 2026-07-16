"""
Nifty Iron Condor backtest, day by day, over config.START_DATE..END_DATE.

Per day:
  1. Fetch NIFTY spot 1-min candles.
  2. Freeze reference strike = round(spot close @ 09:30, to nearest 100).
  3. Build 4-leg iron condor around the frozen strike (hardcoded expiry).
  4. Fetch 1-min candles for all 4 option legs.
  5. Entry price of each leg = close @ 09:45 (nearest available candle).
  6. Mark-to-market every minute from 09:45 -> 15:00, pnl in rupees.
  7. Store per-day pnl series -> results.json (input for dashboard_generator.py)
"""
import json
import datetime as dt

import config
from fyers_client import (
    get_fyers_model, fetch_1min_candles, find_candle_at_or_nearest,
    build_minute_price_map,
)
from symbol_builder import build_iron_condor_symbols


def round_to_nearest(value, step):
    return int(round(value / float(step)) * step)


def daterange(start_date, end_date):
    d = start_date
    one_day = dt.timedelta(days=1)
    while d <= end_date:
        yield d
        d += one_day


def generate_minute_grid(start_hhmm, end_hhmm):
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    start_total = sh * 60 + sm
    end_total = eh * 60 + em
    out = []
    t = start_total
    while t <= end_total:
        out.append("%02d:%02d" % (t // 60, t % 60))
        t += 1
    return out


def price_at_minute(price_map, sorted_times, hhmm):
    """
    Exact match if the minute exists in price_map, else nearest available
    minute (by absolute distance) from sorted_times. price_map/sorted_times
    come from build_minute_price_map() + sorted(price_map.keys()).
    """
    if hhmm in price_map:
        return price_map[hhmm]
    if not sorted_times:
        return None

    h, m = map(int, hhmm.split(":"))
    target = h * 60 + m

    def minute_of(t):
        th, tm = map(int, t.split(":"))
        return th * 60 + tm

    nearest = min(sorted_times, key=lambda t: abs(minute_of(t) - target))
    return price_map[nearest]


def run_day(fyers, trade_date):
    print("Processing %s ..." % trade_date)

    spot_candles = fetch_1min_candles(fyers, config.SPOT_SYMBOL, trade_date)
    if not spot_candles:
        print("  no spot data (holiday / no trading) -- skipping day")
        return None

    freeze_candle = find_candle_at_or_nearest(spot_candles, config.FREEZE_TIME)
    if freeze_candle is None:
        print("  could not find freeze-time candle -- skipping day")
        return None

    frozen_strike = round_to_nearest(freeze_candle["close"], config.STRIKE_ROUND_STEP)

    legs = build_iron_condor_symbols(
        frozen_strike=frozen_strike,
        short_offset=config.SHORT_OFFSET,
        hedge_offset=config.HEDGE_OFFSET,
        expiry_date=config.EXPIRY_DATE,
        is_weekly=config.IS_WEEKLY,
        underlying=config.UNDERLYING_NAME,
    )

    leg_data = {}
    for leg_name, leg_info in legs.items():
        candles = fetch_1min_candles(fyers, leg_info["symbol"], trade_date)
        if not candles:
            print("  no data for leg %s (%s) -- skipping day" % (leg_name, leg_info["symbol"]))
            return None
        price_map = build_minute_price_map(candles)
        leg_data[leg_name] = {
            "symbol": leg_info["symbol"],
            "strike": leg_info["strike"],
            "side": leg_info["side"],
            "price_map": price_map,
            "sorted_times": sorted(price_map.keys()),
        }

    # Entry prices (09:45, nearest fallback)
    entry_prices = {}
    for leg_name, ld in leg_data.items():
        entry_prices[leg_name] = price_at_minute(ld["price_map"], ld["sorted_times"], config.ENTRY_TIME)

    entry_credit = (
        entry_prices["sell_call"] + entry_prices["sell_put"]
        - entry_prices["buy_call"] - entry_prices["buy_put"]
    )

    # Minute-by-minute PnL walk from entry to exit
    minute_grid = [t for t in generate_minute_grid(config.ENTRY_TIME, config.EXIT_TIME)]

    pnl_series = []
    for hhmm in minute_grid:
        cur = {}
        ok = True
        for leg_name, ld in leg_data.items():
            p = price_at_minute(ld["price_map"], ld["sorted_times"], hhmm)
            if p is None:
                ok = False
                break
            cur[leg_name] = p
        if not ok:
            continue

        current_value = (
            cur["sell_call"] + cur["sell_put"]
            - cur["buy_call"] - cur["buy_put"]
        )
        pnl_per_unit = entry_credit - current_value
        pnl_rupees = pnl_per_unit * config.QTY
        pnl_series.append({"time": hhmm, "pnl": round(pnl_rupees, 2)})

    day_result = {
        "date": trade_date.strftime("%Y-%m-%d"),
        "frozen_strike": frozen_strike,
        "spot_at_freeze": freeze_candle["close"],
        "legs": {
            leg_name: {
                "symbol": ld["symbol"],
                "strike": ld["strike"],
                "side": ld["side"],
                "entry_price": entry_prices[leg_name],
            }
            for leg_name, ld in leg_data.items()
        },
        "entry_credit_per_unit": round(entry_credit, 2),
        "qty": config.QTY,
        "entry_credit_total": round(entry_credit * config.QTY, 2),
        "final_pnl": pnl_series[-1]["pnl"] if pnl_series else None,
        "pnl_series": pnl_series,
    }
    print("  frozen_strike=%s entry_credit/unit=%.2f final_pnl=%s" % (
        frozen_strike, entry_credit, day_result["final_pnl"]))
    return day_result


def main():
    fyers = get_fyers_model()
    results = []
    for trade_date in daterange(config.START_DATE, config.END_DATE):
        if trade_date.weekday() >= 5:  # Sat/Sun
            continue
        try:
            day_result = run_day(fyers, trade_date)
        except Exception as e:
            print("  [error] %s -- skipping day: %s" % (trade_date, e))
            day_result = None
        if day_result:
            results.append(day_result)

    with open(config.RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2)

    print("\nDone. %d days processed, results written to %s" % (len(results), config.RESULTS_JSON))


if __name__ == "__main__":
    main()
