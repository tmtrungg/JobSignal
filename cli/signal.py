#!/usr/bin/env python3
"""Manage LinkedInQuery signals for a user."""

import argparse
import sys

import yaml

from src.linkedinquery.config import USERS_DIR, DB_PATH, load_user_signals
from src.linkedinquery.database import get_db


def list_signals(user_name: str = None):
    USERS_DIR.mkdir(exist_ok=True)

    if user_name:
        user_dirs = [USERS_DIR / user_name]
        if not user_dirs[0].exists():
            print(f"User '{user_name}' not found")
            sys.exit(1)
    else:
        user_dirs = sorted(d for d in USERS_DIR.iterdir() if d.is_dir())

    if not user_dirs:
        print("No users configured. Add one with: python3 -m cli.user add <name>")
        return

    print(f"\n{'='*75}")
    print(f" {'USER':<15} {'SIGNAL':<20} {'KEYWORDS':<22} {'LOCATION':<16}")
    print(f"{'='*75}")

    total = 0
    for user_dir in user_dirs:
        try:
            profile, signals = load_user_signals(user_dir.name)
            if not signals:
                print(f" {profile.name:<15} (no signals)")
                continue
            for sig in signals:
                print(f" {sig.user:<15} {sig.name:<20} {sig.keywords:<22} {sig.location:<16}")
                total += 1
        except Exception as e:
            print(f" {user_dir.name:<15} ERROR: {e}")

    print(f"{'='*75}")
    print(f" {total} signal(s)\n")


def add_signal(user_name: str, signal_name: str, keywords: str, location: str,
               time_filter: str = "r86400", interval: str = "60,120"):
    signals_dir = USERS_DIR / user_name / "signals"
    if not (USERS_DIR / user_name).exists():
        print(f"User '{user_name}' not found. Create with: python3 -m cli.user add {user_name}")
        sys.exit(1)

    signals_dir.mkdir(exist_ok=True)
    path = signals_dir / f"{signal_name}.yaml"

    if path.exists():
        print(f"Signal '{signal_name}' already exists for user '{user_name}'")
        sys.exit(1)

    # Parse interval
    parts = interval.split(",")
    if len(parts) == 2:
        interval_val = [int(parts[0]), int(parts[1])]
    else:
        interval_val = int(parts[0])

    cfg = {
        "search": {
            "keywords": keywords,
            "location": location,
            "time_filter": time_filter,
        },
        "schedule": {
            "interval_minutes": interval_val,
        },
        "scraper": {
            "delay_between_requests": [3, 7],
            "max_pages": 3,
        },
    }

    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    print(f"Created signal '{signal_name}' for user '{user_name}'")
    print(f"  file: {path}")
    print(f"  search: '{keywords}' in '{location}' (past {time_filter})")


def remove_signal(user_name: str, signal_name: str, keep_data: bool = False):
    path = USERS_DIR / user_name / "signals" / f"{signal_name}.yaml"
    if not path.exists():
        print(f"Signal '{signal_name}' not found for user '{user_name}'")
        sys.exit(1)

    path.unlink()
    full_name = f"{user_name}/{signal_name}"
    print(f"Removed signal '{full_name}'")

    if not keep_data and DB_PATH.exists():
        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE search_name = ?", (full_name,)).fetchone()[0]
            if count > 0:
                conn.execute("DELETE FROM seen_jobs WHERE search_name = ?", (full_name,))
                conn.execute("DELETE FROM run_log WHERE search_name = ?", (full_name,))
                conn.commit()
                print(f"Cleared {count} jobs from database")


def main():
    parser = argparse.ArgumentParser(description="Manage LinkedInQuery signals")
    sub = parser.add_subparsers(dest="command")

    # list
    ls = sub.add_parser("list", help="List all signals")
    ls.add_argument("--user", "-u", help="Filter by user")

    # add
    add = sub.add_parser("add", help="Add a signal to a user")
    add.add_argument("user", help="Username")
    add.add_argument("name", help="Signal name (e.g. 'swe-intern-au')")
    add.add_argument("--keywords", "-k", required=True, help="Search keywords")
    add.add_argument("--location", "-l", required=True, help="Search location")
    add.add_argument("--time-filter", "-t", default="r86400", help="Time filter (default: r86400 = 24hr)")
    add.add_argument("--interval", "-i", default="60,120", help="Run interval in minutes (e.g. '60,120' for random 1-2hr)")

    # remove
    rm = sub.add_parser("remove", help="Remove a signal")
    rm.add_argument("user", help="Username")
    rm.add_argument("name", help="Signal name to remove")
    rm.add_argument("--keep-data", action="store_true", help="Keep job records in database")

    args = parser.parse_args()

    if args.command == "add":
        add_signal(args.user, args.name, args.keywords, args.location, args.time_filter, args.interval)
    elif args.command == "remove":
        remove_signal(args.user, args.name, args.keep_data)
    elif args.command == "list":
        list_signals(args.user)
    else:
        list_signals()


if __name__ == "__main__":
    main()
