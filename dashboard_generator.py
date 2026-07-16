"""
Builds a single self-contained HTML dashboard from results.json.
One tab per trading day, each tab shows:
  - trade summary (frozen strike, 4 legs, entry credit, final pnl)
  - a Plotly PnL curve from 09:45 -> 15:00

Pure python -- only string templating, no pandas/numpy. Plotly is loaded
from CDN in the browser, so no plotly python package is required to
*generate* the file (json.dumps is enough).
"""
import json

import config


LEG_ORDER = ["sell_call", "buy_call", "sell_put", "buy_put"]
LEG_LABEL = {
    "sell_call": "SELL CE",
    "buy_call": "BUY CE (hedge)",
    "sell_put": "SELL PE",
    "buy_put": "BUY PE (hedge)",
}


def build_html(results):
    tab_buttons = []
    tab_panels = []
    chart_scripts = []

    for i, day in enumerate(results):
        date_str = day["date"]
        active_class = " active" if i == 0 else ""
        display_style = "block" if i == 0 else "none"

        tab_buttons.append(
            '<button class="tab-btn%s" onclick="showTab(%d)" id="tab-btn-%d">%s</button>'
            % (active_class, i, i, date_str)
        )

        legs_rows = ""
        for leg_key in LEG_ORDER:
            leg = day["legs"][leg_key]
            legs_rows += (
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%.2f</td></tr>"
                % (LEG_LABEL[leg_key], leg["side"], leg["symbol"], leg["entry_price"])
            )

        final_pnl = day["final_pnl"]
        pnl_class = "pnl-pos" if (final_pnl or 0) >= 0 else "pnl-neg"
        final_pnl_str = ("%.2f" % final_pnl) if final_pnl is not None else "N/A"

        panel_html = """
<div class="tab-panel" id="tab-panel-{i}" style="display:{display_style};">
  <div class="summary-grid">
    <div class="summary-card">
      <div class="summary-label">Spot @ 09:30</div>
      <div class="summary-value">{spot_at_freeze}</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Frozen Strike</div>
      <div class="summary-value">{frozen_strike}</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Entry Credit / unit</div>
      <div class="summary-value">{entry_credit_per_unit}</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Qty ({lot_size} x {num_lots})</div>
      <div class="summary-value">{qty}</div>
    </div>
    <div class="summary-card">
      <div class="summary-label">Final PnL</div>
      <div class="summary-value {pnl_class}">{final_pnl_str}</div>
    </div>
  </div>

  <table class="legs-table">
    <thead><tr><th>Leg</th><th>Side</th><th>Symbol</th><th>Entry Price</th></tr></thead>
    <tbody>{legs_rows}</tbody>
  </table>

  <div class="chart" id="chart-{i}"></div>
</div>
""".format(
            i=i,
            display_style=display_style,
            spot_at_freeze=day["spot_at_freeze"],
            frozen_strike=day["frozen_strike"],
            entry_credit_per_unit=day["entry_credit_per_unit"],
            lot_size=config.LOT_SIZE,
            num_lots=config.NUM_LOTS,
            qty=day["qty"],
            pnl_class=pnl_class,
            final_pnl_str=final_pnl_str,
            legs_rows=legs_rows,
        )
        tab_panels.append(panel_html)

        times = [p["time"] for p in day["pnl_series"]]
        pnls = [p["pnl"] for p in day["pnl_series"]]

        chart_scripts.append("""
Plotly.newPlot('chart-{i}', [{{
  x: {times},
  y: {pnls},
  type: 'scatter',
  mode: 'lines',
  line: {{color: '#3b82f6', width: 2}},
  fill: 'tozeroy',
  fillcolor: 'rgba(59,130,246,0.1)',
  name: 'PnL'
}}], {{
  margin: {{t: 20, r: 20, b: 40, l: 60}},
  xaxis: {{title: 'Time', tickangle: -45}},
  yaxis: {{title: 'PnL (INR)', zeroline: true, zerolinecolor: '#94a3b8', zerolinewidth: 1}},
  shapes: [{{type: 'line', x0: 0, x1: 1, xref: 'paper', y0: 0, y1: 0, line: {{color: '#94a3b8', width: 1, dash: 'dot'}}}}],
  height: 420
}}, {{responsive: true}});
""".format(i=i, times=json.dumps(times), pnls=json.dumps(pnls)))

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Nifty Iron Condor Backtest Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    margin: 0;
    padding: 24px;
  }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 20px; font-size: 13px; }}
  .tab-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 16px;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 12px;
  }}
  .tab-btn {{
    background: #1e293b;
    color: #cbd5e1;
    border: none;
    padding: 8px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }}
  .tab-btn:hover {{ background: #334155; }}
  .tab-btn.active {{ background: #3b82f6; color: white; }}
  .tab-panel {{
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 20px;
  }}
  .summary-grid {{
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 18px;
  }}
  .summary-card {{
    background: #1e293b;
    border-radius: 8px;
    padding: 10px 16px;
    min-width: 140px;
  }}
  .summary-label {{ font-size: 11px; color: #94a3b8; margin-bottom: 4px; }}
  .summary-value {{ font-size: 18px; font-weight: 600; }}
  .pnl-pos {{ color: #34d399; }}
  .pnl-neg {{ color: #f87171; }}
  .legs-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 18px;
    font-size: 13px;
  }}
  .legs-table th, .legs-table td {{
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid #1e293b;
  }}
  .legs-table th {{ color: #94a3b8; font-weight: 500; }}
  .chart {{ width: 100%; }}
</style>
</head>
<body>
  <h1>Nifty Iron Condor Backtest -- Sell 300pt / Hedge 400pt</h1>
  <div class="subtitle">
    {num_days} trading days &middot; Lot size {lot_size} &times; {num_lots} lots &middot;
    Entry 09:45 &middot; Exit 15:00 &middot; Expiry {expiry}
  </div>

  <div class="tab-bar">
    {tab_buttons}
  </div>

  {tab_panels}

  <script>
    function showTab(i) {{
      var panels = document.querySelectorAll('.tab-panel');
      var btns = document.querySelectorAll('.tab-btn');
      panels.forEach(function(p, idx) {{
        p.style.display = (idx === i) ? 'block' : 'none';
      }});
      btns.forEach(function(b, idx) {{
        b.classList.toggle('active', idx === i);
      }});
      var evt = window.dispatchEvent(new Event('resize'));
    }}
    {chart_scripts}
  </script>
</body>
</html>
""".format(
        num_days=len(results),
        lot_size=config.LOT_SIZE,
        num_lots=config.NUM_LOTS,
        expiry=config.EXPIRY_DATE.strftime("%Y-%m-%d"),
        tab_buttons="\n    ".join(tab_buttons),
        tab_panels="\n".join(tab_panels),
        chart_scripts="\n".join(chart_scripts),
    )
    return html


def main():
    with open(config.RESULTS_JSON) as f:
        results = json.load(f)

    if not results:
        print("No results to build a dashboard from.")
        return

    html = build_html(results)

    import os
    os.makedirs(os.path.dirname(config.DASHBOARD_HTML), exist_ok=True)
    with open(config.DASHBOARD_HTML, "w") as f:
        f.write(html)

    print("Dashboard written to %s" % config.DASHBOARD_HTML)


if __name__ == "__main__":
    main()
