# LinkedInQuery

Personal tool that monitors LinkedIn job searches and sends Telegram notifications when new jobs appear. Supports multiple users, each with their own Telegram bot and independent search signals.

## How It Works

1. Each **user** has a Telegram bot
2. Each user has multiple **signals** (search keyword + location + schedule)
3. In daemon mode, each signal runs on its own random timer (1-2hr default)
4. A **request mutex** ensures only one signal scrapes LinkedIn at a time (avoids IP detection)
5. Only runs during active hours (7am-9pm Melbourne time)
6. New jobs are deduplicated against a local SQLite database
7. Only truly new jobs trigger a Telegram notification

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Create a user (with Telegram bot)

First create a bot: message [@BotFather](https://t.me/BotFather) → `/newbot` → get token.
Then get your chat_id: message your bot, visit `https://api.telegram.org/bot<TOKEN>/getUpdates`.

```bash
python3 -m cli.user add trung -t "YOUR_BOT_TOKEN" -c "YOUR_CHAT_ID"
```

### 3. Add search signals

```bash
python3 -m cli.signal add trung swe-intern-au -k "software engineer intern" -l "Australia"
python3 -m cli.signal add trung data-eng-us -k "data engineer" -l "United States" -t r604800
```

### 4. Run

```bash
# Test: run all signals once
python3 -m cli.main --once

# Production: daemon with independent timers per signal
python3 -m cli.main --daemon

# Run only one user's signals
python3 -m cli.main --user trung --once
```

## Managing Users

```bash
# List all users
python3 -m cli.user list

# Add a user with their Telegram bot
python3 -m cli.user add trung -t "7012345678:AAF..." -c "123456789"
python3 -m cli.user add alice -t "6898765432:BBG..." -c "987654321"

# Remove a user (deletes config folder + cleans DB)
python3 -m cli.user remove alice
```

## Managing Signals

```bash
# List all signals across all users
python3 -m cli.signal list

# List signals for a specific user
python3 -m cli.signal list --user trung

# Add a signal — basic (24hr filter, 1-2hr interval)
python3 -m cli.signal add trung swe-intern-au -k "software engineer intern" -l "Australia"

# Add a signal — 7-day filter, custom 1.5-2.5hr interval
python3 -m cli.signal add trung data-eng-us -k "data engineer" -l "United States" -t r604800 -i "90,150"

# Add a signal — 1hr filter for fast-moving roles
python3 -m cli.signal add trung ml-remote -k "machine learning engineer" -l "Remote" -t r3600 -i "30,60"

# Remove a signal (deletes config + cleans DB)
python3 -m cli.signal remove trung data-eng-us
```

### Signal options

| Flag | Default | Description |
|------|---------|-------------|
| `-k`, `--keywords` | required | Search keywords |
| `-l`, `--location` | required | Search location |
| `-t`, `--time-filter` | `r86400` | `r3600`=1hr, `r86400`=24hr, `r604800`=7days |
| `-i`, `--interval` | `60,120` | Run interval in minutes (min,max for random range) |

## Viewing Results

```bash
python3 -m cli.viewer                        # stats + recent jobs
python3 -m cli.viewer --user trung           # filter by user
python3 -m cli.viewer list                   # last 20 jobs
python3 -m cli.viewer list -s swe-intern-au  # filter by signal
python3 -m cli.viewer stats
python3 -m cli.viewer export
python3 -m cli.viewer clear                  # clear all
python3 -m cli.viewer clear -s trung/swe-intern-au  # clear specific signal
```

## Project Structure

```
LinkedInQuery/
├── src/linkedinquery/        # Core library
│   ├── config.py             # Paths, user/signal loading, validation
│   ├── models.py             # Job, SearchQuery dataclasses
│   ├── scraper.py            # LinkedIn guest API scraping
│   ├── database.py           # SQLite operations
│   └── notifier.py           # Telegram Bot API
├── cli/                      # Entry points
│   ├── main.py               # Run signals (--once / --daemon)
│   ├── viewer.py             # View/export/clear jobs
│   ├── user.py               # Manage users
│   └── signal.py             # Manage signals
├── config/
│   ├── config.yaml           # Shared settings (logging)
│   └── users/                # One folder per user
│       └── trung/
│           ├── profile.yaml  # Telegram bot config
│           └── signals/
│               ├── swe-intern-au.yaml
│               └── data-eng-us.yaml
├── data/                     # Runtime (gitignored)
│   ├── jobs.db
│   └── linkedinquery.log
├── .gitignore
└── requirements.txt
```
