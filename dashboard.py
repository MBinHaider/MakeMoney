import asyncio
import argparse
import sys

from config import Config
from dashboard.app import DashboardApp


def main():
    parser = argparse.ArgumentParser(description="MBH Trading Bots Command Center")
    parser.add_argument("--dashboard-only", action="store_true", help="Dashboard only, don't start bots")
    parser.add_argument("--bots-only", action="store_true", help="Start bots only, no dashboard")
    parser.add_argument("--stop", action="store_true", help="Stop all bots")
    args = parser.parse_args()

    config = Config()

    if args.stop:
        print("Stopping bots...")
        import subprocess
        subprocess.run(["pkill", "-f", "polybot5m.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "binancebot.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "polybot.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "caffeinate"], capture_output=True)
        print("All bots stopped.")
        return

    if args.bots_only:
        import subprocess
        print("Starting bots in background...")
        subprocess.Popen([sys.executable, "polybot5m.py", "--mode", "paper"],
                        stdout=open("polybot5m.log", "a"), stderr=subprocess.STDOUT)
        print("PolyBot 5M started (polybot5m.log)")
        print("Use --stop to stop all bots")
        return

    if not args.dashboard_only:
        import subprocess
        import os
        # Start bots if not already running
        try:
            import psutil
            running = [p.name() for p in psutil.process_iter(["name"])]
        except Exception:
            running = []

        if "polybot5m.py" not in str(running):
            subprocess.Popen([sys.executable, "polybot5m.py", "--mode", "paper"],
                            stdout=open("polybot5m.log", "a"), stderr=subprocess.STDOUT)
            print("Started PolyBot 5M")

    app = DashboardApp(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nDashboard stopped. Bots continue running in background.")
        print("Use 'python dashboard.py --stop' to stop everything.")


if __name__ == "__main__":
    main()
