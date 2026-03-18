"""Shared configuration, paths, and data models."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
USERS_DIR = CONFIG_DIR / "users"
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "jobs.db"
LOCK_FILE = Path("/tmp/linkedinquery.lock")


@dataclass
class UserProfile:
    name: str
    bot_token: str
    chat_id: str


@dataclass
class Signal:
    """One search signal bound to a user."""
    name: str                    # signal filename stem
    user: str                    # user folder name
    keywords: str
    location: str
    time_filter: str = "r86400"
    geo_id: int | None = None
    work_type: int | None = None
    interval_min: int = 60
    interval_max: int = 120
    delay_range: tuple[int, int] = (3, 7)
    max_pages: int = 3
    bot_token: str = ""
    chat_id: str = ""

    @property
    def full_name(self) -> str:
        """Unique identifier: user/signal."""
        return f"{self.user}/{self.name}"


def _parse_interval(raw) -> tuple[int, int]:
    if isinstance(raw, list):
        return int(raw[0]), int(raw[1])
    return int(raw), int(raw)


def _parse_delay(raw) -> tuple[int, int]:
    if isinstance(raw, list):
        return int(raw[0]), int(raw[1])
    return int(raw), int(raw)


def load_user_profile(user_dir: Path) -> UserProfile:
    profile_path = user_dir / "profile.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"No profile.yaml in {user_dir}")
    with open(profile_path) as f:
        cfg = yaml.safe_load(f) or {}
    tg = cfg.get("telegram", {})
    return UserProfile(
        name=user_dir.name,
        bot_token=tg.get("bot_token", ""),
        chat_id=str(tg.get("chat_id", "")),
    )


def load_signal(path: Path, user: UserProfile) -> Signal:
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}

    search = cfg.get("search", {})
    schedule = cfg.get("schedule", {})
    scraper = cfg.get("scraper", {})

    interval_min, interval_max = _parse_interval(schedule.get("interval_minutes", [60, 120]))
    delay_range = _parse_delay(scraper.get("delay_between_requests", [3, 7]))

    signal = Signal(
        name=path.stem,
        user=user.name,
        keywords=search.get("keywords", ""),
        location=search.get("location", ""),
        time_filter=search.get("time_filter", "r86400"),
        geo_id=search.get("geo_id"),
        work_type=search.get("work_type"),
        interval_min=interval_min,
        interval_max=interval_max,
        delay_range=delay_range,
        max_pages=scraper.get("max_pages", 3),
        bot_token=user.bot_token,
        chat_id=user.chat_id,
    )

    if not signal.keywords:
        raise ValueError(f"{path}: 'search.keywords' is required")
    if not signal.location:
        raise ValueError(f"{path}: 'search.location' is required")

    return signal


def load_user_signals(user_name: str) -> tuple[UserProfile, list[Signal]]:
    """Load a specific user's profile and all their signals."""
    user_dir = USERS_DIR / user_name
    if not user_dir.exists():
        raise FileNotFoundError(f"User '{user_name}' not found in {USERS_DIR}")

    profile = load_user_profile(user_dir)
    signals_dir = user_dir / "signals"
    signals = []
    if signals_dir.exists():
        for path in sorted(signals_dir.glob("*.yaml")):
            signals.append(load_signal(path, profile))
    return profile, signals


def load_all() -> list[Signal]:
    """Load all users and all their signals."""
    USERS_DIR.mkdir(exist_ok=True)
    all_signals = []
    for user_dir in sorted(USERS_DIR.iterdir()):
        if not user_dir.is_dir():
            continue
        try:
            profile = load_user_profile(user_dir)
            signals_dir = user_dir / "signals"
            if signals_dir.exists():
                for path in sorted(signals_dir.glob("*.yaml")):
                    all_signals.append(load_signal(path, profile))
        except Exception:
            continue
    return all_signals


def load_logging_config() -> dict:
    main_cfg = CONFIG_DIR / "config.yaml"
    if main_cfg.exists():
        with open(main_cfg) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("logging", {})
    return {}
