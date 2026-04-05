import asyncio
import argparse
import subprocess
import sys
import os

from config import Config
from dashboard.app import DashboardApp


def _is_bot_running(name: str) -> bool:
    """Check if a bot process is running."""
    try:
        import psutil
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or [])
                if name in cmd and "dashboard" not in cmd:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return False


def start_bots():
    """Start all bots in background if not already running."""
    started = []

    if not _is_bot_running("polybot5m.py"):
        subprocess.Popen(
            [sys.executable, "polybot5m.py", "--mode", "paper"],
            stdout=open("polybot5m.log", "a"), stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started.append("PolyBot 5M")

    if not _is_bot_running("binancebot.py"):
        subprocess.Popen(
            [sys.executable, "binancebot.py", "--mode", "paper", "--capital", "45"],
            stdout=open("binancebot.log", "a"), stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started.append("BinanceBot")

    if not _is_bot_running("polybot.py"):
        subprocess.Popen(
            [sys.executable, "polybot.py"],
            stdout=open("polybot.log", "a"), stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        started.append("PolyBot")

    return started


def stop_bots():
    """Stop all bots."""
    subprocess.run(["pkill", "-f", "polybot5m.py"], capture_output=True)
    subprocess.run(["pkill", "-f", "binancebot.py"], capture_output=True)
    subprocess.run(["pkill", "-f", "polybot.py --mode"], capture_output=True)
    subprocess.run(["pkill", "-f", "caffeinate"], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description="MBH Trading Bots Command Center")
    parser.add_argument("--start", action="store_true", help="Start all bots in background (no dashboard)")
    parser.add_argument("--stop", action="store_true", help="Stop all bots")
    parser.add_argument("--status", action="store_true", help="Check which bots are running")
    parser.add_argument("--no-start", action="store_true", help="Don't auto-start bots, just show dashboard")
    args = parser.parse_args()

    config = Config()

    if args.stop:
        print("Stopping all bots...")
        stop_bots()
        print("All bots stopped.")
        return

    if args.status:
        bots = {"PolyBot 5M": "polybot5m.py", "BinanceBot": "binancebot.py", "PolyBot": "polybot.py"}
        for name, proc in bots.items():
            running = _is_bot_running(proc)
            status = "● RUNNING" if running else "○ STOPPED"
            color = "\033[92m" if running else "\033[91m"
            print(f"  {color}{status}\033[0m  {name}")
        return

    if args.start:
        started = start_bots()
        if started:
            print(f"Started: {', '.join(started)}")
        else:
            print("All bots already running.")
        print("Logs: polybot5m.log, binancebot.log, polybot.log")
        return

    # Default: ensure bots are running, then show dashboard
    if not args.no_start:
        started = start_bots()
        if started:
            print(f"Started: {', '.join(started)}")
            import time
            time.sleep(2)  # Give bots time to init

    # Dashboard is just a viewer — closing it does NOT stop bots
    app = DashboardApp(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass

    print("\nDashboard closed. Bots continue running in background.")
    print("  python dashboard.py          → reopen dashboard")
    print("  python dashboard.py --status → check bot status")
    print("  python dashboard.py --stop   → stop everything")


if __name__ == "__main__":
    main()
