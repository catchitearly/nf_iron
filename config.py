"""
Config for Nifty Iron Condor backtest.
Edit the values below and commit -- everything the backtester needs is here.
Pure python, no numpy/pandas dependency.
"""
import os
from datetime import date

# ----------------------------------------------------------------------
# CREDENTIALS (read from GitHub Actions secrets / environment variables)
# ----------------------------------------------------------------------
FYERS_CLIENT_ID = os.environ.get("FYERS_CLIENT_ID", "")
FYERS_ACCESS_TOKEN = os.environ.get("FYERS_ACCESS_TOKEN", "")

# ----------------------------------------------------------------------
# DATE RANGE  (hardcode the backtest window here)
# ----------------------------------------------------------------------
START_DATE = date(2026, 7, 14)
END_DATE = date(2026, 7, 16)

# ----------------------------------------------------------------------
# EXPIRY  (hardcoded -- same expiry used to build all 4 option symbols
# for every day in the range above)
# ----------------------------------------------------------------------
EXPIRY_DATE = date(2026, 7, 21)   # <-- set the option expiry date here
IS_WEEKLY = True                 # True = weekly contract, False = monthly

# ----------------------------------------------------------------------
# SYMBOLS
# ----------------------------------------------------------------------
SPOT_SYMBOL = "NSE:NIFTY50-INDEX"
UNDERLYING_NAME = "NIFTY"

# ----------------------------------------------------------------------
# STRATEGY PARAMETERS
# ----------------------------------------------------------------------
STRIKE_ROUND_STEP = 100     # freeze the 9:30 spot to nearest 100
SHORT_OFFSET = 300          # sell leg distance from frozen strike
HEDGE_OFFSET = 400          # buy (hedge) leg distance from frozen strike
                            # (100 pts beyond the short leg)

LOT_SIZE = 65
NUM_LOTS = 15
QTY = LOT_SIZE * NUM_LOTS   # total quantity per leg

# ----------------------------------------------------------------------
# TIMING (all IST, 24h "HH:MM")
# ----------------------------------------------------------------------
FREEZE_TIME = "09:30"    # spot candle used to freeze the reference strike
ENTRY_TIME = "09:45"     # candle used for entry price of all 4 legs
EXIT_TIME = "15:00"      # last candle used for mark-to-market / exit

MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"

# ----------------------------------------------------------------------
# FYERS HISTORICAL API
# ----------------------------------------------------------------------
RESOLUTION = "1"          # 1-minute candles
API_MAX_RETRIES = 3
API_RETRY_SLEEP_SEC = 2

# ----------------------------------------------------------------------
# OUTPUT
# ----------------------------------------------------------------------
RESULTS_JSON = "results.json"
DASHBOARD_HTML = "docs/index.html"
