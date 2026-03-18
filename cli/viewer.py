#!/usr/bin/env python3
"""CLI viewer for the LinkedInQuery jobs database."""

import argparse
import csv

from src.linkedinquery.config import DATA_DIR, DB_PATH
from src.linkedinquery.database import get_db


def _require_db():
    if not DB_PATH.exists():
        print("No database found. Run 'python3 -m cli.main --once' first.")
        raise SystemExit(1)


def _truncate(text: str, length: int) -> str:
    return (text[:length - 2] + "..") if len(text) > length else text


def list_jobs(user: str = None, signal: str = None, limit: int = 20, show_all: bool = False):
    _require_db()
    query = "SELECT title, company, location, date_posted, search_name, url FROM seen_jobs"
    params = []
    conditions = []

    if user:
        conditions.append("search_name LIKE ?")
        params.append(f"{user}/%")
    if signal:
        conditions.append("search_name LIKE ?")
        params.append(f"%{signal}%")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY first_seen_at DESC"
    if not show_all:
        query += " LIMIT ?"
        params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No jobs found.")
        return

    print(f"\n{'='*100}")
    print(f" {'SIGNAL':<20} {'TITLE':<30} {'COMPANY':<18} {'LOCATION':<18} {'POSTED':<12}")
    print(f"{'='*100}")
    for title, company, location, date_posted, search_name, url in rows:
        print(f" {_truncate(search_name, 20):<20} {_truncate(title, 30):<30} {_truncate(company, 18):<18} {_truncate(location, 18):<18} {_truncate(date_posted or 'N/A', 12):<12}")
        print(f"   {url}")
    print(f"{'='*100}")
    print(f" Showing {len(rows)} job(s)\n")


def show_stats(user: str = None):
    _require_db()
    with get_db() as conn:
        if user:
            total = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE search_name LIKE ?", (f"{user}/%",)).fetchone()[0]
            notified = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE notified = 1 AND search_name LIKE ?", (f"{user}/%",)).fetchone()[0]
            searches = conn.execute("SELECT search_name, COUNT(*) FROM seen_jobs WHERE search_name LIKE ? GROUP BY search_name ORDER BY COUNT(*) DESC", (f"{user}/%",)).fetchall()
            recent_runs = conn.execute(
                "SELECT run_at, search_name, jobs_found, new_jobs, status FROM run_log WHERE search_name LIKE ? ORDER BY run_at DESC LIMIT 10", (f"{user}/%",)
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
            notified = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE notified = 1").fetchone()[0]
            searches = conn.execute("SELECT search_name, COUNT(*) FROM seen_jobs GROUP BY search_name ORDER BY COUNT(*) DESC").fetchall()
            recent_runs = conn.execute(
                "SELECT run_at, search_name, jobs_found, new_jobs, status FROM run_log ORDER BY run_at DESC LIMIT 10"
            ).fetchall()

    print(f"\n{'='*60}")
    print(f" DATABASE STATS{f' — {user}' if user else ''}")
    print(f"{'='*60}")
    print(f" Total jobs tracked:   {total}")
    print(f" Notifications sent:   {notified}")
    print(f"\n Jobs by signal:")
    for name, count in searches:
        print(f"   {name}: {count}")

    if recent_runs:
        print(f"\n{'='*70}")
        print(f" RECENT RUNS")
        print(f"{'='*70}")
        print(f" {'TIMESTAMP':<22} {'SIGNAL':<25} {'FOUND':>6} {'NEW':>5} {'STATUS':<8}")
        print(f" {'-'*22} {'-'*25} {'-'*6} {'-'*5} {'-'*8}")
        for run_at, sname, found, new, status in recent_runs:
            ts = run_at[:19].replace("T", " ")
            print(f" {ts:<22} {_truncate(sname, 25):<25} {found:>6} {new:>5} {status:<8}")

    print(f"{'='*70 if recent_runs else '='*60}\n")


def export_csv(output: str = None, user: str = None):
    _require_db()
    if output is None:
        output = str(DATA_DIR / "jobs_export.csv")

    with get_db() as conn:
        if user:
            rows = conn.execute(
                "SELECT job_id, title, company, location, date_posted, search_name, first_seen_at, url FROM seen_jobs WHERE search_name LIKE ? ORDER BY first_seen_at DESC",
                (f"{user}/%",)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT job_id, title, company, location, date_posted, search_name, first_seen_at, url FROM seen_jobs ORDER BY first_seen_at DESC"
            ).fetchall()

    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Job ID", "Title", "Company", "Location", "Date Posted", "Signal", "First Seen", "URL"])
        writer.writerows(rows)
    print(f"Exported {len(rows)} jobs to {output}")


def clear_db(user: str = None, signal: str = None):
    _require_db()
    with get_db() as conn:
        if signal:
            search_name = f"{user}/{signal}" if user else signal
            count = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE search_name = ?", (search_name,)).fetchone()[0]
            conn.execute("DELETE FROM seen_jobs WHERE search_name = ?", (search_name,))
            conn.execute("DELETE FROM run_log WHERE search_name = ?", (search_name,))
            conn.commit()
            print(f"Cleared {count} jobs for signal '{search_name}'")
        elif user:
            count = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE search_name LIKE ?", (f"{user}/%",)).fetchone()[0]
            conn.execute("DELETE FROM seen_jobs WHERE search_name LIKE ?", (f"{user}/%",))
            conn.execute("DELETE FROM run_log WHERE search_name LIKE ?", (f"{user}/%",))
            conn.commit()
            print(f"Cleared {count} jobs for user '{user}'")
        else:
            count = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
            conn.execute("DELETE FROM seen_jobs")
            conn.execute("DELETE FROM run_log")
            conn.commit()
            print(f"Cleared all {count} jobs and run history")


def main():
    parser = argparse.ArgumentParser(description="View LinkedInQuery job database")
    parser.add_argument("--user", "-u", help="Filter by user")
    sub = parser.add_subparsers(dest="command")

    ls = sub.add_parser("list", help="List tracked jobs")
    ls.add_argument("-s", "--signal", help="Filter by signal name")
    ls.add_argument("-n", "--limit", type=int, default=20, help="Number of jobs to show")
    ls.add_argument("--all", action="store_true", help="Show all jobs")

    sub.add_parser("stats", help="Show database statistics")

    ex = sub.add_parser("export", help="Export all jobs to CSV")
    ex.add_argument("-o", "--output", default=None, help="Output file path")

    cl = sub.add_parser("clear", help="Clear jobs from database")
    cl.add_argument("-s", "--signal", help="Clear only a specific signal")

    args = parser.parse_args()

    commands = {
        "list": lambda: list_jobs(user=args.user, signal=args.signal, limit=args.limit, show_all=args.all),
        "stats": lambda: show_stats(user=args.user),
        "export": lambda: export_csv(args.output, user=args.user),
        "clear": lambda: clear_db(user=args.user, signal=args.signal),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        show_stats(user=args.user)
        list_jobs(user=args.user, limit=10)


if __name__ == "__main__":
    main()
