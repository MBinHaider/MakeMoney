import json, os, sqlite3, time
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

DB_5M = os.path.expanduser("~/MakeMoney/data/polybot5m.db")
DB_BN = os.path.expanduser("~/MakeMoney/data/binancebot.db")
STATE_FILE = os.path.expanduser("~/MakeMoney/data/polybot5m_state.json")

HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PolyBot Dashboard</title>
<meta http-equiv="refresh" content="10">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Courier New',monospace;padding:12px}
h1{text-align:center;color:#00ff88;font-size:1.5em;margin-bottom:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;max-width:900px;margin:0 auto}
@media(max-width:600px){.grid{grid-template-columns:1fr}}
.card{background:#12121a;border:1px solid #1a1a2e;border-radius:8px;padding:14px}
.card h2{color:#00aaff;font-size:1em;margin-bottom:8px;border-bottom:1px solid #1a1a2e;padding-bottom:4px}
.card.full{grid-column:1/-1}
.stat{display:flex;justify-content:space-between;padding:3px 0}
.label{color:#888}.value{color:#fff;font-weight:bold}
.green{color:#00ff88}.red{color:#ff4444}.yellow{color:#ffaa00}
table{width:100%;border-collapse:collapse;font-size:0.85em}
th{text-align:left;color:#00aaff;border-bottom:1px solid #1a1a2e;padding:4px}
td{padding:4px;border-bottom:1px solid #0a0a12}
.win{color:#00ff88}.loss{color:#ff4444}
.tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:0.8em}
.tag-live{background:#003300;color:#00ff88;border:1px solid #00ff88}
.tag-paper{background:#332200;color:#ffaa00;border:1px solid #ffaa00}
.footer{text-align:center;color:#444;font-size:0.75em;margin-top:12px}
</style></head><body>
<h1>⚡ POLYBOT DASHBOARD ⚡</h1>
<div class="grid">
<div class="card">
<h2>📊 PolyBot 5M <span class="tag tag-live">LIVE</span></h2>
{% if fm %}
<div class="stat"><span class="label">Balance</span><span class="value">${{'%.2f'|format(fm.balance)}}</span></div>
<div class="stat"><span class="label">P&L</span><span class="value {{ 'green' if fm.total_pnl >= 0 else 'red' }}">${{'%.2f'|format(fm.total_pnl)}}</span></div>
<div class="stat"><span class="label">Trades</span><span class="value">{{fm.total_trades}} ({{fm.total_wins}}W/{{fm.total_trades - fm.total_wins}}L)</span></div>
<div class="stat"><span class="label">Win Rate</span><span class="value">{{'%.0f'|format(fm.win_rate)}}%</span></div>
{% else %}<p>No data</p>{% endif %}
</div>
<div class="card">
<h2>📈 BinanceBot <span class="tag tag-paper">PAPER</span></h2>
{% if bn %}
<div class="stat"><span class="label">Balance</span><span class="value">${{'%.2f'|format(bn.balance)}}</span></div>
<div class="stat"><span class="label">P&L</span><span class="value {{ 'green' if bn.total_pnl >= 0 else 'red' }}">${{'%.2f'|format(bn.total_pnl)}}</span></div>
<div class="stat"><span class="label">Trades</span><span class="value">{{bn.total_trades}}</span></div>
{% else %}<p>No data</p>{% endif %}
</div>
<div class="card">
<h2>📡 Live Signals</h2>
{% if signals %}
{% for s in signals %}
<div class="stat">
<span class="label">{{s.asset}}</span>
<span class="value">M:{{s.momentum}} O:{{s.orderbook}} V:{{s.volume}}
{% if s.signal %}<span class="{{ 'green' if s.confidence > 0.7 else 'yellow' }}">{{s.signal}} {{'%.0f'|format(s.confidence*100)}}%</span>{% else %}-{% endif %}</span>
</div>
{% endfor %}
{% else %}<p>Waiting for data...</p>{% endif %}
</div>
<div class="card">
<h2>🕐 Status</h2>
<div class="stat"><span class="label">Server</span><span class="value green">Online</span></div>
<div class="stat"><span class="label">Updated</span><span class="value">{{now}}</span></div>
</div>
<div class="card full">
<h2>📋 Recent 5M Trades</h2>
<table>
<tr><th>#</th><th>Asset</th><th>Dir</th><th>Entry</th><th>Cost</th><th>P&L</th><th>Result</th><th>Time</th></tr>
{% for t in trades %}
<tr>
<td>{{t.id}}</td><td>{{t.asset}}</td><td>{{t.direction}}</td>
<td>${{'%.2f'|format(t.entry_price)}}</td><td>${{'%.2f'|format(t.cost)}}</td>
<td class="{{ 'win' if t.pnl > 0 else 'loss' if t.pnl < 0 else '' }}">${{'%.2f'|format(t.pnl)}}</td>
<td class="{{ t.result }}">{{t.result|upper}}</td>
<td>{{t.timestamp[11:19] if t.timestamp else ''}}</td>
</tr>
{% endfor %}
{% if not trades %}<tr><td colspan="8">No trades yet</td></tr>{% endif %}
</table>
</div>
</div>
<div class="footer">Auto-refreshes every 10s | PolyBot Trading System</div>
</body></html>"""


def get_db(path):
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def dashboard():
    fm = bn = None
    signals = []
    trades = []

    conn = get_db(DB_5M)
    if conn:
        row = conn.execute("SELECT * FROM fm_portfolio WHERE id=1").fetchone()
        if row:
            d = dict(row)
            wr = (d["total_wins"] / d["total_trades"] * 100) if d["total_trades"] > 0 else 0
            fm = type("O", (object,), {**d, "win_rate": wr})()
        rows = conn.execute("SELECT * FROM fm_trades ORDER BY id DESC LIMIT 20").fetchall()
        trades = [type("O", (object,), dict(r))() for r in rows]
        conn.close()

    conn = get_db(DB_BN)
    if conn:
        row = conn.execute("SELECT * FROM bn_portfolio WHERE id=1").fetchone()
        if row:
            bn = type("O", (object,), dict(row))()
        conn.close()

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
                signals = [type("O", (object,), s)() for s in state.get("signals", [])]
        except Exception:
            pass

    return render_template_string(
        HTML,
        fm=fm,
        bn=bn,
        signals=signals,
        trades=trades,
        now=datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    )


@app.route("/api/status")
def api_status():
    data = {"server": "online", "time": time.time()}
    conn = get_db(DB_5M)
    if conn:
        row = conn.execute("SELECT * FROM fm_portfolio WHERE id=1").fetchone()
        if row:
            data["polybot5m"] = dict(row)
        conn.close()
    conn = get_db(DB_BN)
    if conn:
        row = conn.execute("SELECT * FROM bn_portfolio WHERE id=1").fetchone()
        if row:
            data["binancebot"] = dict(row)
        conn.close()
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
