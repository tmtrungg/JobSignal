# JobSignal

**Monitor LinkedIn job searches and get instant Telegram notifications when new jobs appear.**

No login required. No browser automation. Just lightweight HTTP requests to LinkedIn's public API, deduplication via SQLite, and push notifications straight to your phone.

---

## Features

- **Real-time alerts** — Get Telegram notifications the moment new jobs match your search
- **Multi-user support** — Each user gets their own Telegram bot with independent search signals
- **Multiple signals per user** — Track different roles, locations, and time ranges simultaneously
- **Smart deduplication** — SQLite-backed tracking ensures you never see the same job twice
- **Anti-detection built in** — Randomized intervals (1-2hr), User-Agent rotation, request mutex, active hours only
- **Zero dependencies on browsers** — No Selenium, no Playwright, no Chrome — just `requests`
- **Simple CLI** — Add/remove users and signals in one command
- **Fully local** — All data stays on your machine, no external services beyond LinkedIn and Telegram

## How It Works

```
  LinkedIn Public API
         |
    [Scrape jobs]
         |
    [Deduplicate against SQLite]
         |
    [New jobs found?]
         |
    [Send Telegram notification]
```

Each **signal** (keyword + location + schedule) runs on its own randomized timer. A request mutex ensures only one signal hits LinkedIn at a time. Jobs older than 30 days are automatically cleaned up.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/tmtrungg/JobSignal.git
cd JobSignal
pip install -r requirements.txt
```

### 2. Set up Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy your **bot token**
2. Send any message to your new bot
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` → copy your **chat_id**

### 3. Create a user

```bash
python3 -m cli.user add myname -t "YOUR_BOT_TOKEN" -c "YOUR_CHAT_ID"
```

### 4. Add a search signal

```bash
python3 -m cli.signal add myname my-search -k "software engineer" -l "Australia"
```

### 5. Run

```bash
python3 -m cli.main --once     # Run once and exit
python3 -m cli.main --daemon   # Run continuously (recommended)
```

That's it. You'll get a Telegram message whenever new jobs appear.

---

## Usage

### Managing Users

Each user is linked to one Telegram bot.

```bash
# List all users
python3 -m cli.user list

# Add a user
python3 -m cli.user add alice -t "BOT_TOKEN" -c "CHAT_ID"

# Remove a user (deletes config + cleans database)
python3 -m cli.user remove alice
```

### Managing Signals

Each signal is an independent search with its own schedule.

```bash
# List all signals
python3 -m cli.signal list
python3 -m cli.signal list --user alice

# Add signals with different configurations
python3 -m cli.signal add alice frontend-uk -k "frontend developer" -l "United Kingdom"
python3 -m cli.signal add alice backend-remote -k "backend engineer" -l "Remote" -t r604800 -i "90,150"

# Remove a signal
python3 -m cli.signal remove alice frontend-uk
```

#### Signal Options

| Flag | Default | Description |
|------|---------|-------------|
| `-k`, `--keywords` | *required* | Search keywords |
| `-l`, `--location` | *required* | Search location |
| `-t`, `--time-filter` | `r86400` | Time range: `r3600` (1hr), `r86400` (24hr), `r604800` (7 days) |
| `-i`, `--interval` | `60,120` | Minutes between runs (min,max for random range) |

### Running

```bash
# Run all signals once
python3 -m cli.main --once

# Daemon mode: each signal on its own random timer
python3 -m cli.main --daemon

# Run only one user's signals
python3 -m cli.main --user alice --once
```

### Viewing & Managing Data

```bash
python3 -m cli.viewer                    # Overview: stats + recent jobs
python3 -m cli.viewer list               # Last 20 jobs
python3 -m cli.viewer list -s my-search  # Filter by signal name
python3 -m cli.viewer stats              # Database statistics
python3 -m cli.viewer export             # Export to CSV
python3 -m cli.viewer clear              # Clear all data
python3 -m cli.viewer clear -s alice/frontend-uk  # Clear one signal
```

---

## Project Structure

```
JobSignal/
├── src/linkedinquery/        # Core library
│   ├── config.py             # Paths, user/signal loading, validation
│   ├── models.py             # Job, SearchQuery dataclasses
│   ├── scraper.py            # LinkedIn public API scraping
│   ├── database.py           # SQLite deduplication + run logging
│   └── notifier.py           # Telegram Bot API integration
├── cli/                      # CLI entry points
│   ├── main.py               # Run engine (--once / --daemon)
│   ├── viewer.py             # View, export, clear jobs
│   ├── user.py               # Manage users
│   └── signal.py             # Manage signals
├── config/
│   ├── config.yaml           # Shared settings (logging)
│   └── users/                # Per-user config (gitignored)
│       └── <username>/
│           ├── profile.yaml  # Telegram bot credentials
│           └── signals/      # One YAML per search signal
├── data/                     # SQLite DB + logs (gitignored)
├── requirements.txt
└── CLAUDE.md                 # Full technical documentation
```

## Anti-Detection

This tool is designed for personal use with conservative request patterns:

- **Randomized intervals**: 1-2 hours between runs (configurable)
- **Request mutex**: Only one signal scrapes at a time, even with multiple signals
- **User-Agent rotation**: Cycles through 5 real browser user agents
- **Page delays**: 3-7 second random waits between paginated requests
- **Active hours only**: Runs 7am-9pm (Melbourne time) — no overnight requests
- **429 backoff**: Respects rate limits with 30s retry, then stops
- **Process lock**: Prevents duplicate daemon instances

## Requirements

- Python 3.10+
- `requests`
- `PyYAML`
- A Telegram bot (free, takes 2 minutes to set up)

## Disclaimer

This tool accesses LinkedIn's publicly available job listing pages for personal use. It does not require authentication or access any private data. Please use responsibly and in accordance with LinkedIn's Terms of Service. The author is not responsible for any misuse.

---

## License

MIT
