#!/usr/bin/env python3
"""Manage LinkedInQuery users."""

import argparse
import shutil
import sys

import yaml

from src.linkedinquery.config import USERS_DIR, DB_PATH, load_user_profile
from src.linkedinquery.database import get_db


def list_users():
    USERS_DIR.mkdir(exist_ok=True)
    user_dirs = sorted(d for d in USERS_DIR.iterdir() if d.is_dir())

    if not user_dirs:
        print("No users configured. Add one with: python3 -m cli.user add <name>")
        return

    print(f"\n{'='*60}")
    print(f" USERS")
    print(f"{'='*60}")

    for user_dir in user_dirs:
        try:
            profile = load_user_profile(user_dir)
            signals_dir = user_dir / "signals"
            signal_count = len(list(signals_dir.glob("*.yaml"))) if signals_dir.exists() else 0
            tg_status = "configured" if profile.bot_token and profile.bot_token != "YOUR_BOT_TOKEN" else "not set"
            print(f" {profile.name:<20} telegram: {tg_status:<14} signals: {signal_count}")
        except Exception as e:
            print(f" {user_dir.name:<20} ERROR: {e}")

    print(f"{'='*60}\n")


def add_user(name: str, bot_token: str = None, chat_id: str = None):
    user_dir = USERS_DIR / name
    if user_dir.exists():
        print(f"User '{name}' already exists at {user_dir}")
        sys.exit(1)

    user_dir.mkdir(parents=True)
    (user_dir / "signals").mkdir()

    profile = {
        "telegram": {
            "bot_token": bot_token or "YOUR_BOT_TOKEN",
            "chat_id": chat_id or "YOUR_CHAT_ID",
        }
    }

    with open(user_dir / "profile.yaml", "w") as f:
        yaml.dump(profile, f, default_flow_style=False, sort_keys=False)

    print(f"Created user '{name}' at {user_dir}/")
    print(f"  profile: {user_dir}/profile.yaml")
    print(f"  signals: {user_dir}/signals/")

    if not bot_token:
        print(f"\n  Next: edit profile.yaml with your Telegram bot_token and chat_id")
    print(f"  Then:  python3 -m cli.signal add {name} <signal-name> -k 'keywords' -l 'location'")


def remove_user(name: str, keep_data: bool = False):
    user_dir = USERS_DIR / name
    if not user_dir.exists():
        print(f"User '{name}' not found")
        sys.exit(1)

    # List signals being removed
    signals_dir = user_dir / "signals"
    signal_names = []
    if signals_dir.exists():
        signal_names = [p.stem for p in signals_dir.glob("*.yaml")]

    shutil.rmtree(user_dir)
    print(f"Removed user '{name}' and {len(signal_names)} signal(s)")

    if not keep_data and DB_PATH.exists() and signal_names:
        with get_db() as conn:
            for sig_name in signal_names:
                full_name = f"{name}/{sig_name}"
                conn.execute("DELETE FROM seen_jobs WHERE search_name = ?", (full_name,))
                conn.execute("DELETE FROM run_log WHERE search_name = ?", (full_name,))
            conn.commit()
            print(f"Cleared database records for all signals")


def main():
    parser = argparse.ArgumentParser(description="Manage LinkedInQuery users")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all users")

    add = sub.add_parser("add", help="Add a new user")
    add.add_argument("name", help="Username (used as folder name)")
    add.add_argument("--bot-token", "-t", help="Telegram bot token")
    add.add_argument("--chat-id", "-c", help="Telegram chat ID")

    rm = sub.add_parser("remove", help="Remove a user and all their signals")
    rm.add_argument("name", help="Username to remove")
    rm.add_argument("--keep-data", action="store_true", help="Keep job records in database")

    args = parser.parse_args()

    if args.command == "add":
        add_user(args.name, args.bot_token, args.chat_id)
    elif args.command == "remove":
        remove_user(args.name, args.keep_data)
    else:
        list_users()


if __name__ == "__main__":
    main()
