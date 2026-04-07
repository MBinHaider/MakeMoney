"""Analyze PolyBot 5M performance on the server."""
import sqlite3
import os
from datetime import datetime, timezone

DB = os.path.expanduser("~/MakeMoney/data/polybot5m.db")

def main():
    if not os.path.exists(DB):
        print(f"DB not found: {DB}")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print("="*60)
    print("POLYBOT 5M PERFORMANCE ANALYSIS")
    print("="*60)

    # Portfolio
    p = conn.execute("SELECT * FROM fm_portfolio WHERE id=1").fetchone()
    if p:
        p = dict(p)
        print(f"\n[PORTFOLIO]")
        print(f"  Balance:         ${p['balance']:.2f}")
        print(f"  Starting:        ${p['starting_balance']:.2f}")
        print(f"  Peak:            ${p.get('peak_balance', 0):.2f}")
        print(f"  Total PnL:       ${p['total_pnl']:.2f}")
        print(f"  Daily PnL:       ${p.get('daily_pnl', 0):.2f}")
        print(f"  Total Trades:    {p['total_trades']}")
        print(f"  Wins:            {p['total_wins']}")
        losses = p['total_trades'] - p['total_wins']
        wr = (p['total_wins'] / p['total_trades'] * 100) if p['total_trades'] > 0 else 0
        print(f"  Losses:          {losses}")
        print(f"  Win Rate:        {wr:.1f}%")
        print(f"  Consec Losses:   {p.get('consecutive_losses', 0)}")
        print(f"  Paused:          {bool(p.get('is_paused', 0))}")

    # Trades by result
    print(f"\n[TRADES BY RESULT]")
    rows = conn.execute(
        "SELECT result, COUNT(*) as c, COALESCE(SUM(pnl),0) as p FROM fm_trades GROUP BY result"
    ).fetchall()
    for r in rows:
        print(f"  {r['result']:10s} {r['c']:4d} trades  PnL: ${r['p']:.2f}")

    # By asset
    print(f"\n[BY ASSET]")
    rows = conn.execute(
        """SELECT asset, COUNT(*) as c,
           SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
           COALESCE(SUM(pnl),0) as p
           FROM fm_trades GROUP BY asset"""
    ).fetchall()
    for r in rows:
        wr = (r['w']/r['c']*100) if r['c']>0 else 0
        print(f"  {r['asset']:5s} {r['c']:4d} trades  {r['w']:3d}W ({wr:5.1f}%)  PnL: ${r['p']:+.2f}")

    # By signal phase
    print(f"\n[BY SIGNAL PHASE]")
    rows = conn.execute(
        """SELECT signal_phase, COUNT(*) as c,
           SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
           COALESCE(SUM(pnl),0) as p
           FROM fm_trades GROUP BY signal_phase"""
    ).fetchall()
    for r in rows:
        wr = (r['w']/r['c']*100) if r['c']>0 else 0
        print(f"  {r['signal_phase']:10s} {r['c']:4d} trades  {r['w']:3d}W ({wr:5.1f}%)  PnL: ${r['p']:+.2f}")

    # Confidence buckets
    print(f"\n[BY CONFIDENCE]")
    buckets = [(0.0, 0.6, "low"), (0.6, 0.75, "med"), (0.75, 1.01, "high")]
    for lo, hi, lbl in buckets:
        row = conn.execute(
            """SELECT COUNT(*) as c,
               SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
               COALESCE(SUM(pnl),0) as p
               FROM fm_trades WHERE signal_confidence >= ? AND signal_confidence < ?""",
            (lo, hi)
        ).fetchone()
        c = row['c']; w = row['w']; pl = row['p']
        wr = (w/c*100) if c > 0 else 0
        print(f"  {lbl} ({lo:.2f}-{hi:.2f})  {c:4d} trades  {w:3d}W ({wr:5.1f}%)  PnL: ${pl:+.2f}")

    # Recent 10
    print(f"\n[LAST 10 TRADES]")
    rows = conn.execute(
        """SELECT asset, direction, entry_price, cost, result, pnl,
                  signal_confidence, signal_phase, timestamp
           FROM fm_trades ORDER BY id DESC LIMIT 10"""
    ).fetchall()
    for r in rows:
        t = r['timestamp'][:19] if r['timestamp'] else ''
        print(f"  {t} {r['asset']} {r['direction']:4s} @ ${r['entry_price']:.3f} "
              f"cost=${r['cost']:.2f} {r['result']:7s} "
              f"PnL=${(r['pnl'] or 0):+.2f} conf={r['signal_confidence']:.0%} {r['signal_phase']}")

    # Signal stats today
    print(f"\n[SIGNALS TODAY]")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        gen = conn.execute(
            "SELECT COUNT(*) as c FROM fm_signals WHERE date(timestamp) = ?", (today,)
        ).fetchone()['c']
        traded = conn.execute(
            "SELECT COUNT(*) as c FROM fm_signals WHERE action_taken='traded' AND date(timestamp) = ?",
            (today,)
        ).fetchone()['c']
        print(f"  Generated: {gen}")
        print(f"  Traded:    {traded}")
        print(f"  Skipped:   {gen - traded}")
    except Exception as e:
        print(f"  No signal data: {e}")

    conn.close()
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
