# CLAUDE.md — LinkedInQuery

## Important

When making ANY changes to the codebase — new features, refactors, bug fixes, config changes — you MUST update:
1. This file (CLAUDE.md) if the workflow, architecture, or data flow changes
2. README.md if usage instructions, commands, or config format changes

Do not let documentation drift from the code.

---

## What This App Does

Monitors LinkedIn job searches and sends Telegram notifications when new jobs appear. Supports multiple users, each with their own Telegram bot and independent search signals. Each signal runs on its own randomized timer in daemon mode.

## Project Structure

```
LinkedInQuery/
├── src/linkedinquery/           # Core library
│   ├── __init__.py
│   ├── config.py                # Paths, user/signal loading, dataclasses
│   ├── models.py                # Job and SearchQuery dataclasses
│   ├── scraper.py               # LinkedIn HTTP scraping + HTML parsing
│   ├── database.py              # SQLite operations (dedup, logging, cleanup)
│   └── notifier.py              # Telegram Bot API integration
├── cli/                         # Entry points (run from project root)
│   ├── __init__.py
│   ├── main.py                  # python3 -m cli.main (--once / --daemon)
│   ├── viewer.py                # python3 -m cli.viewer (list/stats/export/clear)
│   ├── user.py                  # python3 -m cli.user (add/remove/list)
│   └── signal.py                # python3 -m cli.signal (add/remove/list)
├── config/
│   ├── config.yaml              # Shared settings (logging only)
│   └── users/                   # One folder per user (gitignored — contains secrets)
│       └── <username>/
│           ├── profile.yaml     # Telegram bot config (bot_token, chat_id)
│           └── signals/
│               └── <signal>.yaml  # Search config (keywords, location, schedule)
├── data/                        # Auto-created at runtime (gitignored)
│   ├── jobs.db                  # SQLite database
│   └── linkedinquery.log        # Log file
├── .gitignore
├── requirements.txt             # requests, PyYAML
├── README.md                    # User-facing setup and usage guide
└── CLAUDE.md                    # This file — full technical reference
```

## Dependencies

- `requests` — HTTP client for LinkedIn API and Telegram API
- `PyYAML` — config file parsing
- Everything else is Python stdlib: `sqlite3`, `html.parser`, `logging`, `zoneinfo`, `fcntl`, `threading`

## Data Model: Users and Signals

### Relationships

```
1 User  →  1 Telegram Bot (profile.yaml)
1 User  →  N Signals     (signals/*.yaml)
```

Each signal inherits its parent user's `bot_token` and `chat_id`.

### Dataclasses (`src/linkedinquery/config.py`)

```python
UserProfile:  name, bot_token, chat_id
Signal:       name, user, keywords, location, time_filter, geo_id, work_type,
              interval_min, interval_max, delay_range, max_pages, bot_token, chat_id
              → full_name property: "{user}/{name}" (used as DB key)
```

### Dataclasses (`src/linkedinquery/models.py`)

```python
Job:          job_id, title, company, location, url, date_posted
SearchQuery:  name, keywords, location, time_filter, geo_id, work_type, results_per_page, max_pages
              → from_signal(signal) classmethod builds SearchQuery from a Signal
```

## Config Format

### User profile (`config/users/<name>/profile.yaml`)

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"   # From @BotFather
  chat_id: "YOUR_CHAT_ID"       # From getUpdates API
```

### Signal (`config/users/<name>/signals/<signal>.yaml`)

```yaml
search:
  keywords: "software engineer intern"
  location: "Australia"
  time_filter: "r86400"          # r3600=1hr, r86400=24hr, r604800=7days
  # geo_id: 101452733           # Optional: LinkedIn geoId
  # work_type: 3                # Optional: 1=onsite, 2=hybrid, 3=remote

schedule:
  interval_minutes: [60, 120]    # Random 1-2hr between runs

scraper:
  delay_between_requests: [3, 7] # Random seconds between HTTP requests
  max_pages: 3                   # Pages per search (25 results each)
```

### Shared settings (`config/config.yaml`)

```yaml
logging:
  level: "INFO"
  file: "linkedinquery.log"
```

## Complete Execution Flow

### 1. Startup (`cli/main.py → main()`)

```
main()
  ├─ parse CLI args (--once, --daemon, --user)
  ├─ setup_logging()                        # loads level/file from config/config.yaml
  ├─ if --user:
  │    load_user_signals(name)              # → (UserProfile, list[Signal])
  │  else:
  │    load_all()                           # iterates config/users/*/ → list[Signal]
  ├─ acquire_lock()                         # fcntl.flock on /tmp/linkedinquery.lock
  │    └─ exits if another instance running
  └─ --daemon → run_daemon(signals)
     --once  → for signal in signals: run_signal(signal)
```

### 2. Config Loading (`src/linkedinquery/config.py`)

```
load_all()
  ├─ iterate config/users/*/
  │   ├─ load_user_profile(user_dir)       # profile.yaml → UserProfile
  │   └─ for each signals/*.yaml:
  │       load_signal(path, profile)        # → Signal (inherits bot_token, chat_id)
  └─ return flat list of all Signal objects

load_user_signals(user_name)
  ├─ load_user_profile(USERS_DIR / user_name)
  └─ load all signals/*.yaml → list[Signal]
  └─ return (UserProfile, list[Signal])
```

### 3. Single Signal Run (`run_signal(signal)`)

```
run_signal(signal)
  ├─ build SearchQuery.from_signal(signal)
  ├─ acquire scrape_lock (threading.Lock)   # only one signal scrapes at a time
  │   └─ scrape_jobs(query, delay_range)    # → list[Job]
  │       ├─ create requests.Session with random User-Agent
  │       ├─ FOR EACH page (0 to max_pages):
  │       │   ├─ GET linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
  │       │   │   params: keywords, location, f_TPR, sortBy=DD, start=page*25
  │       │   ├─ handle 429 → sleep 30s, retry once
  │       │   ├─ parse_jobs(html) → list[Job]
  │       │   │   └─ JobCardParser (HTMLParser subclass)
  │       │   │       extracts: job_id (from data-entity-urn), title (h3),
  │       │   │       company (h4), location (span), url (a href), date (time)
  │       │   └─ sleep random delay_range before next page
  │       └─ deduplicate by job_id across pages
  │
  ├─ insert_new_jobs(conn, jobs, signal.full_name)  # → list[Job] (only new ones)
  │   └─ INSERT each job; IntegrityError = already seen → skip
  │       dedup key: job_id (LinkedIn's numeric posting ID)
  │       search_name stored as "user/signal" (e.g. "trung/swe-intern-au")
  │
  ├─ log_run(conn, signal.full_name, ...)
  │
  ├─ if new_jobs and Telegram configured:
  │   ├─ send_telegram_digest(bot_token, chat_id, new_jobs, signal.full_name)
  │   └─ mark_notified(conn, job_ids)
  │
  └─ cleanup_old_jobs(conn, days=30)
```

### 4. Daemon Mode (`run_daemon(signals)`)

```
run_daemon(signals)
  ├─ FOR EACH signal: spawn daemon thread → _signal_loop(signal)
  │   each thread has:
  │   ├─ random stagger: sleep 0-120s (so signals don't all fire at once)
  │   └─ LOOP FOREVER:
  │       ├─ _seconds_until_active()
  │       │   └─ if outside 7am-9pm Melbourne → sleep until 7am
  │       ├─ run_signal(signal)
  │       ├─ pick random wait between signal.interval_min and interval_max
  │       └─ sleep(wait * 60)
  └─ main thread: sleep loop, KeyboardInterrupt → shutdown
```

### Concurrency Model

- **Thread per signal**: Each signal runs independently in its own daemon thread
- **`scrape_lock` (threading.Lock)**: Mutex ensures only one signal hits LinkedIn at a time — prevents concurrent HTTP requests that could trigger IP detection
- **Stagger**: Each thread sleeps a random 0-120s before its first run
- **Process lock**: `fcntl.flock()` on `/tmp/linkedinquery.lock` prevents multiple daemon instances

## SQLite Tables (data/jobs.db)

**seen_jobs** — every job ever scraped. The dedup table.
```
job_id        TEXT PRIMARY KEY    ← LinkedIn posting ID (from data-entity-urn), e.g. "4384098627"
title         TEXT NOT NULL       ← "Software Engineer Intern"
company       TEXT                ← "Google"
location      TEXT                ← "Sydney, New South Wales, Australia"
url           TEXT NOT NULL       ← "https://au.linkedin.com/jobs/view/..."
date_posted   TEXT                ← "2 hours ago" (LinkedIn's relative text)
search_name   TEXT                ← "user/signal" format, e.g. "trung/swe-intern-au"
first_seen_at TEXT NOT NULL       ← ISO 8601 UTC timestamp of first scrape
notified      INTEGER DEFAULT 0  ← 1 after Telegram notification sent
```

**run_log** — audit trail of every scrape cycle.
```
id            INTEGER PRIMARY KEY
run_at        TEXT NOT NULL       ← ISO 8601 UTC timestamp
search_name   TEXT NOT NULL       ← "user/signal" format
jobs_found    INTEGER             ← total results in this run
new_jobs      INTEGER             ← jobs not previously in seen_jobs
status        TEXT                ← "ok" or "error"
error_message TEXT                ← null unless status="error"
```

### Deduplication Logic

The `job_id` is extracted from LinkedIn's `data-entity-urn="urn:li:jobPosting:XXXXXXXXXX"` attribute in the HTML. This is a stable, unique numeric ID for each posting.

`insert_new_jobs()` does `INSERT INTO seen_jobs ...` for each job. If `job_id` already exists → `IntegrityError` → silently skip. The function returns only the jobs that were actually inserted (= new).

## LinkedIn Scraping Details

### Endpoint

```
GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
```

This is LinkedIn's public guest API — no authentication needed. Returns HTML fragments (not JSON).

### Query Parameters

| Param | Example | Notes |
|-------|---------|-------|
| `keywords` | `software engineer intern` | URL-encoded job search terms |
| `location` | `Australia` | Free text location |
| `f_TPR` | `r86400` | Time posted range: r3600=1hr, r86400=24hr, r604800=7days |
| `f_WT` | `3` | Work type: 1=onsite, 2=hybrid, 3=remote |
| `geoId` | `101452733` | LinkedIn's numeric geo ID (optional, more precise) |
| `sortBy` | `DD` | Sort by date descending |
| `start` | `0`, `25`, `50` | Pagination offset (25 per page) |

### HTML Parsing

The response is an HTML fragment containing `<li>` elements with job cards. Each card has:
- `<div class="base-card job-search-card" data-entity-urn="urn:li:jobPosting:XXXXXXXXXX">` → job_id
- `<h3 class="base-search-card__title">` → title
- `<h4 class="base-search-card__subtitle">` → company
- `<span class="job-search-card__location">` → location
- `<a class="base-card__full-link" href="...">` → url
- `<time class="job-search-card__listdate">` → date_posted

Parsed with Python stdlib `html.parser.HTMLParser` — no BeautifulSoup dependency.

### Anti-Scraping Measures

- Random User-Agent rotation (5 real browser UAs)
- 3-7 second random delays between page fetches
- 1-2 hour random intervals between runs (daemon mode)
- Only runs 7am-9pm Melbourne time
- `scrape_lock` mutex: sequential requests only across all signals
- 429 handling: sleep 30s, retry once, then stop
- File lock prevents overlapping daemon processes

### Known Limitations

- Guest API returns a subset of what logged-in users see
- LinkedIn may soft-throttle (return HTTP 200 with empty body) after many rapid requests
- Results differ from logged-in search due to personalization, promoted listings, and "similar" suggestions
- LinkedIn's Terms of Use prohibit scraping — this tool is for personal use only

## Telegram Integration

### Setup
1. Create bot via @BotFather → get `bot_token`
2. Send message to bot, then GET `https://api.telegram.org/bot<TOKEN>/getUpdates` → get `chat_id`
3. Add to user profile: `python3 -m cli.user add <name> -t <token> -c <chat_id>`

### Message Format
- HTML parse mode (not MarkdownV2 — less escaping issues)
- One digest message per signal per run (not one per job)
- Messages split at 4000 chars if needed (Telegram limit is 4096)
- Link preview disabled

### API Call
```
POST https://api.telegram.org/bot{token}/sendMessage
Body: { chat_id, text, parse_mode: "HTML", disable_web_page_preview: true }
```

## CLI Commands

All run from project root:

```bash
# Users
python3 -m cli.user list                               # list all users
python3 -m cli.user add <name> -t <token> -c <chat_id> # create user + Telegram bot
python3 -m cli.user remove <name>                       # remove user + clean DB

# Signals
python3 -m cli.signal list                              # list all signals
python3 -m cli.signal list --user <name>                # list user's signals
python3 -m cli.signal add <user> <signal> -k "keywords" -l "location"
python3 -m cli.signal add <user> <signal> -k "keywords" -l "location" -t r604800 -i "90,150"
python3 -m cli.signal remove <user> <signal>            # remove signal + clean DB

# Run
python3 -m cli.main --once                              # run all signals once
python3 -m cli.main --daemon                            # daemon with per-signal timers
python3 -m cli.main --user <name> --once                # run one user's signals

# View
python3 -m cli.viewer                                   # stats + last 10 jobs
python3 -m cli.viewer --user <name>                     # filter by user
python3 -m cli.viewer list                              # last 20 jobs
python3 -m cli.viewer list -s <signal>                  # filter by signal name
python3 -m cli.viewer stats                             # DB stats + recent runs
python3 -m cli.viewer export                            # export to data/jobs_export.csv
python3 -m cli.viewer clear                             # delete all jobs + history
python3 -m cli.viewer clear -s <user/signal>            # delete specific signal data
```

## Path Resolution

All paths are resolved relative to `PROJECT_ROOT` (the repo root), computed in `src/linkedinquery/config.py`:

```
PROJECT_ROOT = Path(__file__).parent.parent.parent   # LinkedInQuery/
CONFIG_DIR   = PROJECT_ROOT / "config"               # LinkedInQuery/config/
USERS_DIR    = CONFIG_DIR / "users"                  # LinkedInQuery/config/users/
DATA_DIR     = PROJECT_ROOT / "data"                 # LinkedInQuery/data/  (auto-created)
DB_PATH      = DATA_DIR / "jobs.db"
LOCK_FILE    = /tmp/linkedinquery.lock
```
