"""
Thin wrapper around Fyers v3 Historical Data API.
Pure python (no pandas/numpy) -- returns plain lists of dicts.
"""
import time
import datetime as dt

import config

IST_OFFSET = dt.timedelta(hours=5, minutes=30)


def _epoch_to_ist(epoch: int) -> dt.datetime:
    """
    Fyers epoch values are standard UTC unix timestamps. Converting with
    dt.datetime.fromtimestamp() uses the machine's local timezone, which
    happens to work on a box already set to IST but is WRONG on GitHub
    Actions runners (UTC by default) -- it silently shifts every candle's
    label by 5:30 and breaks every 09:30 / 09:45 / etc lookup, which then
    falls back to "nearest candle" for almost every minute and produces
    a flat PnL line. Always convert via UTC explicitly, then add the
    fixed IST offset, so behaviour is identical on any runner regardless
    of its local timezone.
    """
    return dt.datetime.utcfromtimestamp(epoch) + IST_OFFSET

try:
    from fyers_apiv3 import fyersModel
except ImportError:
    fyersModel = None


def get_fyers_model():
    if fyersModel is None:
        raise RuntimeError(
            "fyers-apiv3 not installed. Add 'fyers-apiv3' to requirements.txt"
        )
    if not config.FYERS_CLIENT_ID or not config.FYERS_ACCESS_TOKEN:
        raise RuntimeError(
            "FYERS_CLIENT_ID / FYERS_ACCESS_TOKEN not set in environment."
        )
    return fyersModel.FyersModel(
        client_id=config.FYERS_CLIENT_ID,
        token=config.FYERS_ACCESS_TOKEN,
        is_async=False,
        log_path="",
    )


def fetch_1min_candles(fyers, symbol: str, trade_date: dt.date):
    """
    Returns a list of candles for the given calendar day:
      [{"epoch": int, "time": "HH:MM", "open":..,"high":..,"low":..,"close":..,"volume":..}, ...]
    Empty list if no data (holiday / no trades / symbol not found).
    """
    data = {
        "symbol": symbol,
        "resolution": config.RESOLUTION,
        "date_format": "1",
        "range_from": trade_date.strftime("%Y-%m-%d"),
        "range_to": trade_date.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }

    last_err = None
    for attempt in range(config.API_MAX_RETRIES):
        try:
            resp = fyers.history(data=data)
            if resp and resp.get("s") == "ok" and resp.get("candles"):
                candles = []
                for c in resp["candles"]:
                    epoch, o, h, l, cl, v = c
                    t = _epoch_to_ist(epoch)
                    candles.append({
                        "epoch": epoch,
                        "time": t.strftime("%H:%M"),
                        "open": o, "high": h, "low": l, "close": cl,
                        "volume": v,
                    })
                return candles
            else:
                # 's' == 'no_data' or similar -- not an error, just nothing to retry
                if resp and resp.get("s") == "no_data":
                    return []
                last_err = resp
        except Exception as e:
            last_err = e
        time.sleep(config.API_RETRY_SLEEP_SEC)

    print("  [warn] failed to fetch %s on %s: %s" % (symbol, trade_date, last_err))
    return []


def find_candle_at_or_nearest(candles, target_hhmm: str):
    """
    Exact match on HH:MM if present, else the candle with the closest
    timestamp (falls back forward or backward, whichever is nearer).
    Returns None if candles is empty.
    """
    if not candles:
        return None
    for c in candles:
        if c["time"] == target_hhmm:
            return c

    h, m = map(int, target_hhmm.split(":"))
    target_minutes = h * 60 + m

    def minute_of(c):
        ch, cm = map(int, c["time"].split(":"))
        return ch * 60 + cm

    return min(candles, key=lambda c: abs(minute_of(c) - target_minutes))


def build_minute_price_map(candles):
    """
    HH:MM -> close price, for easy nearest-lookup during the pnl walk.
    """
    return {c["time"]: c["close"] for c in candles}
