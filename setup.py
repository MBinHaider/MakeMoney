#!/usr/bin/env python3
# setup.py - One-command installer for PolyBot
import subprocess
import sys
import os
import shutil


def main():
    print("=" * 50)
    print("  PolyBot Setup")
    print("=" * 50)

    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required (you have {sys.version})")
        sys.exit(1)
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} OK")

    print("\nInstalling dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    print("Dependencies installed OK")

    os.makedirs("data", exist_ok=True)
    print("Data directory OK")

    if not os.path.exists(".env"):
        shutil.copy(".env.example", ".env")
        print("\nCreated .env from template")
        print("IMPORTANT: Edit .env with your keys before running!")
    else:
        print(".env already exists")

    from utils.db import init_db
    from config import Config
    cfg = Config()
    init_db(cfg.DB_PATH)
    print("Database initialized OK")

    print("\nRunning tests...")
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"])
    if result.returncode == 0:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed. Check output above.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("  Setup Complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Edit .env with your private key and Telegram bot token")
    print("2. Run: python polybot.py --mode paper --capital 100")
    print("3. When ready for live: python polybot.py --mode live --capital 25")


if __name__ == "__main__":
    main()
