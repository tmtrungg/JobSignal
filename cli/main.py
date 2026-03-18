#!/usr/bin/env python3
"""LinkedInQuery — Monitor LinkedIn job searches and get Telegram notifications."""

import argparse
import fcntl
import logging
import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.linkedinquery.config import DATA_DIR, LOCK_FILE, Signal, load_all, load_logging_config, load_user_signals
from src.linkedinquery.database import cleanup_old_jobs, get_db, insert_new_jobs, log_run, mark_notified
from src.linkedinquery.models import SearchQuery
from src.linkedinquery.notifier import send_telegram_digest
from src.linkedinquery.scraper import scrape_jobs

# Only one signal can hit LinkedIn at a time (avoids IP detection)
scrape_lock = threading.Lock()

MELB_TZ = ZoneInfo("Australia/Melbourne")
ACTIVE_HOURS = (7, 21)


def setup_logging():
    log_cfg = load_logging_config()
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    handlers = [logging.StreamHandler()]
    log_file = log_cfg.get("file")
    if log_file:
        handlers.append(logging.FileHandler(DATA_DIR / log_file))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def run_signal(signal: Signal):
    """Run one signal: scrape → dedup → notify."""
    logger = logging.getLogger(f"signal.{signal.full_name}")
    query = SearchQuery.from_signal(signal)

    logger.info(f"Searching: {signal.keywords} in {signal.location}")

    with scrape_lock:
        try:
            jobs = scrape_jobs(query, delay_range=signal.delay_range)
        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            with get_db() as conn:
                log_run(conn, signal.full_name, 0, 0, status="error", error_message=str(e))
            return

    with get_db() as conn:
        new_jobs = insert_new_jobs(conn, jobs, signal.full_name)
        log_run(conn, signal.full_name, len(jobs), len(new_jobs))
        logger.info(f"Found {len(jobs)} total, {len(new_jobs)} new")

        if new_jobs and signal.bot_token and signal.bot_token != "YOUR_BOT_TOKEN" and signal.chat_id:
            if send_telegram_digest(signal.bot_token, signal.chat_id, new_jobs, signal.full_name):
                mark_notified(conn, [j.job_id for j in new_jobs])
                logger.info(f"Telegram sent ({len(new_jobs)} jobs)")
            else:
                logger.error("Telegram notification failed")
        elif new_jobs:
            logger.warning("Telegram not configured — skipping notification")

        cleanup_old_jobs(conn, days=30)


# --- Daemon ---

def _seconds_until_active() -> int:
    now = datetime.now(MELB_TZ)
    hour = now.hour
    if ACTIVE_HOURS[0] <= hour < ACTIVE_HOURS[1]:
        return 0
    if hour >= ACTIVE_HOURS[1]:
        next_start = now.replace(hour=ACTIVE_HOURS[0], minute=0, second=0, microsecond=0)
        next_start += timedelta(days=1)
    else:
        next_start = now.replace(hour=ACTIVE_HOURS[0], minute=0, second=0, microsecond=0)
    return int((next_start - now).total_seconds())


def _signal_loop(signal: Signal):
    """Independent loop for one signal in its own thread."""
    logger = logging.getLogger(f"signal.{signal.full_name}")

    # Stagger: random initial delay so signals don't all fire at once
    stagger = random.uniform(0, 120)
    logger.info(f"Starting in {stagger:.0f}s (stagger)")
    time.sleep(stagger)

    while True:
        wait_secs = _seconds_until_active()
        if wait_secs > 0:
            logger.info(f"Outside active hours. Sleeping {wait_secs // 3600}h {(wait_secs % 3600) // 60}m")
            time.sleep(wait_secs)

        run_signal(signal)

        wait = random.uniform(signal.interval_min, signal.interval_max)
        logger.info(f"Next run in {wait:.0f} minutes")
        time.sleep(wait * 60)


def run_daemon(signals: list[Signal]):
    logger = logging.getLogger("main")
    logger.info(f"Daemon starting with {len(signals)} signal(s), active {ACTIVE_HOURS[0]}am-{ACTIVE_HOURS[1] - 12}pm Melbourne")

    for signal in signals:
        t = threading.Thread(target=_signal_loop, args=(signal,), name=signal.full_name, daemon=True)
        t.start()
        logger.info(f"  [{signal.full_name}] {signal.keywords} in {signal.location} | every {signal.interval_min}-{signal.interval_max}min")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down.")


# --- Entrypoint ---

def acquire_lock() -> int:
    fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        print("Another instance is already running. Exiting.", file=sys.stderr)
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="LinkedInQuery — LinkedIn job monitor")
    parser.add_argument("--once", action="store_true", help="Run all signals once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run continuously with independent timers")
    parser.add_argument("--user", type=str, help="Run only signals for a specific user")
    args = parser.parse_args()

    setup_logging()

    if args.user:
        _, signals = load_user_signals(args.user)
        if not signals:
            print(f"No signals for user '{args.user}'. Add with: python3 -m cli.signal add {args.user} <name> -k '...' -l '...'")
            sys.exit(1)
    else:
        signals = load_all()
        if not signals:
            print("No signals configured. Set up with:")
            print("  python3 -m cli.user add <name> -t <bot_token> -c <chat_id>")
            print("  python3 -m cli.signal add <user> <signal> -k 'keywords' -l 'location'")
            sys.exit(1)

    lock_fd = acquire_lock()
    try:
        if args.daemon:
            run_daemon(signals)
        else:
            for signal in signals:
                run_signal(signal)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


if __name__ == "__main__":
    main()
