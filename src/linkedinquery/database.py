import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .config import DB_PATH
from .models import Job


def init_db(db_path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id        TEXT PRIMARY KEY,
            title         TEXT NOT NULL,
            company       TEXT,
            location      TEXT,
            url           TEXT NOT NULL,
            date_posted   TEXT,
            search_name   TEXT,
            first_seen_at TEXT NOT NULL,
            notified      INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_log (
            id            INTEGER PRIMARY KEY,
            run_at        TEXT NOT NULL,
            search_name   TEXT NOT NULL,
            jobs_found    INTEGER,
            new_jobs      INTEGER,
            status        TEXT,
            error_message TEXT
        )
    """)
    conn.commit()
    return conn


@contextmanager
def get_db(db_path: str = None):
    """Context manager that ensures the connection is always closed."""
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_new_jobs(conn: sqlite3.Connection, jobs: list[Job], search_name: str) -> list[Job]:
    """Insert jobs, return only the ones that were actually new."""
    new_jobs = []
    now = _now()
    for job in jobs:
        try:
            conn.execute(
                """INSERT INTO seen_jobs (job_id, title, company, location, url, date_posted, search_name, first_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.job_id, job.title, job.company, job.location, job.url, job.date_posted, search_name, now),
            )
            new_jobs.append(job)
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return new_jobs


def mark_notified(conn: sqlite3.Connection, job_ids: list[str]):
    if not job_ids:
        return
    placeholders = ",".join("?" for _ in job_ids)
    conn.execute(f"UPDATE seen_jobs SET notified = 1 WHERE job_id IN ({placeholders})", job_ids)
    conn.commit()


def log_run(conn: sqlite3.Connection, search_name: str, jobs_found: int, new_jobs: int, status: str = "ok", error_message: str | None = None):
    conn.execute(
        "INSERT INTO run_log (run_at, search_name, jobs_found, new_jobs, status, error_message) VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), search_name, jobs_found, new_jobs, status, error_message),
    )
    conn.commit()


def cleanup_old_jobs(conn: sqlite3.Connection, days: int = 30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM seen_jobs WHERE first_seen_at < ?", (cutoff,))
    conn.commit()
