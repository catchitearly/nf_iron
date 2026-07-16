"""
Builds Fyers-format option symbols for NIFTY.

NOTE: I don't have direct access to your straddle_analyzer.py file in this
session (it wasn't uploaded here), so this uses the standard Fyers v3
convention below. If your straddle_analyzer.py builds symbols differently,
just swap out build_option_symbol() with your existing function -- every
other module only calls this function, so it's a single point of change.

Fyers NIFTY option symbol convention:
  Monthly : NSE:NIFTY{YY}{MMM}{STRIKE}{CE|PE}      e.g. NSE:NIFTY26JUL23500CE
  Weekly  : NSE:NIFTY{YY}{M}{DD}{STRIKE}{CE|PE}     e.g. NSE:NIFTY2670223500CE
            where {M} is a single char month code:
              1-9 for Jan-Sep, O for Oct, N for Nov, D for Dec
            and {DD} is the two-digit expiry day of month.
"""

from datetime import date

_MONTH_CODE_WEEKLY = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
}
_MONTH_CODE_MONTHLY = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def build_option_symbol(expiry_date: date, is_weekly: bool, strike: int,
                         opt_type: str, underlying: str = "NIFTY") -> str:
    """
    opt_type: "CE" or "PE"
    strike: integer strike price (e.g. 23500)
    """
    opt_type = opt_type.upper()
    assert opt_type in ("CE", "PE")
    yy = expiry_date.strftime("%y")

    if is_weekly:
        m_code = _MONTH_CODE_WEEKLY[expiry_date.month]
        dd = "%02d" % expiry_date.day
        return "NSE:%s%s%s%s%d%s" % (underlying, yy, m_code, dd, strike, opt_type)
    else:
        m_code = _MONTH_CODE_MONTHLY[expiry_date.month]
        return "NSE:%s%s%s%d%s" % (underlying, yy, m_code, strike, opt_type)


def build_iron_condor_symbols(frozen_strike: int, short_offset: int,
                               hedge_offset: int, expiry_date: date,
                               is_weekly: bool, underlying: str = "NIFTY"):
    """
    Returns a dict with the 4 leg symbols and their strikes/side info:
      sell_call, buy_call, sell_put, buy_put
    """
    sell_call_strike = frozen_strike + short_offset
    buy_call_strike = frozen_strike + hedge_offset
    sell_put_strike = frozen_strike - short_offset
    buy_put_strike = frozen_strike - hedge_offset

    legs = {
        "sell_call": {
            "symbol": build_option_symbol(expiry_date, is_weekly, sell_call_strike, "CE", underlying),
            "strike": sell_call_strike, "opt_type": "CE", "side": "SELL",
        },
        "buy_call": {
            "symbol": build_option_symbol(expiry_date, is_weekly, buy_call_strike, "CE", underlying),
            "strike": buy_call_strike, "opt_type": "CE", "side": "BUY",
        },
        "sell_put": {
            "symbol": build_option_symbol(expiry_date, is_weekly, sell_put_strike, "PE", underlying),
            "strike": sell_put_strike, "opt_type": "PE", "side": "SELL",
        },
        "buy_put": {
            "symbol": build_option_symbol(expiry_date, is_weekly, buy_put_strike, "PE", underlying),
            "strike": buy_put_strike, "opt_type": "PE", "side": "BUY",
        },
    }
    return legs
