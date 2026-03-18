import logging
from html import escape

import requests

from .models import Job

logger = logging.getLogger(__name__)


def send_telegram_digest(bot_token: str, chat_id: str, jobs: list[Job], search_name: str) -> bool:
    """Send a single digest message with all new jobs to Telegram."""
    if not jobs:
        return True

    lines = [f"<b>{len(jobs)} new job(s)</b> — <i>{escape(search_name)}</i>\n"]
    for i, job in enumerate(jobs, 1):
        title = escape(job.title)
        company = escape(job.company)
        location = escape(job.location)
        date = escape(job.date_posted) if job.date_posted else "Recent"
        url = job.url

        lines.append(f"<b>{i}. {title}</b>")
        lines.append(f"   {company}")
        lines.append(f"   {location}")
        lines.append(f"   {date}")
        if url:
            lines.append(f'   <a href="{url}">View on LinkedIn</a>')
        lines.append("")

    message = "\n".join(lines)
    return _send_message(bot_token, chat_id, message)


def _send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    chunks = _split_message(text, 4000)

    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Telegram API error: {resp.status_code} — {resp.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    return True


def _split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
