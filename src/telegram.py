from __future__ import annotations

import logging
from datetime import datetime

import requests

from .models import Job

log = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TELEGRAM_MESSAGE_LEN = 4000  # stay under Telegram's 4096 char hard limit


def _emoji_for_score(score: int) -> str:
    if score >= 90:
        return "🔥"
    if score >= 75:
        return "🟢"
    return "🟡"


def _level_line(job: Job) -> str:
    if job.level_guess and job.level_guess != "Unclear":
        return f"📊 Level: {job.level_guess}"
    if "senior" in job.title.lower():
        return "📊 Level: Senior"
    if "junior" in job.title.lower():
        return "📊 Level: Junior"
    return "📊 Level: Mid (estimated)"


def format_job_block(job: Job, index: int) -> str:
    emoji = _emoji_for_score(job.final_score())
    location = job.location_text or "Location not specified"
    reason = job.ai_reasons or (job.prefilter_reasons[0] if job.prefilter_reasons else "")
    lines = [
        f"{emoji} {index}. {job.company} — {job.title}",
        f"📍 {location}",
        f"🎯 Match: {job.final_score()}/100",
        _level_line(job),
        "",
        "De ce merită:",
        reason or "Se potrivește criteriilor de căutare.",
        "",
        f"🔗 Apply: {job.best_url()}",
    ]
    return "\n".join(lines)


def build_messages(watchlist_jobs: list[Job], new_company_jobs: list[Job], max_per_message: int) -> list[str]:
    if not watchlist_jobs and not new_company_jobs:
        return []

    date_str = datetime.now().strftime("%d %b %Y").upper()
    header = f"🔔 NEW DESIGN JOBS — {date_str}"

    blocks: list[str] = []
    idx = 1
    for job in watchlist_jobs:
        blocks.append(format_job_block(job, idx))
        idx += 1

    new_company_blocks: list[str] = []
    if new_company_jobs:
        new_company_blocks.append("🆕 NEW COMPANY")
        for job in new_company_jobs:
            new_company_blocks.append(format_job_block(job, idx))
            idx += 1

    all_blocks = blocks + new_company_blocks
    messages: list[str] = []
    current = header
    count_in_message = 0

    for block in all_blocks:
        candidate = current + "\n\n---\n\n" + block if current else block
        too_long = len(candidate) > MAX_TELEGRAM_MESSAGE_LEN
        too_many = count_in_message >= max_per_message
        if (too_long or too_many) and current:
            messages.append(current)
            current = block
            count_in_message = 1
        else:
            current = candidate
            count_in_message += 1

    if current:
        messages.append(current)

    return messages


def send_message(bot_token: str, chat_id: str, text: str, timeout: int = 15) -> bool:
    try:
        resp = requests.post(
            API_URL.format(token=bot_token),
            data={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error("Telegram send failed: %s", e)
        return False


def notify(
    bot_token: str | None,
    chat_id: str | None,
    watchlist_jobs: list[Job],
    new_company_jobs: list[Job],
    max_per_message: int,
) -> int:
    """Returns number of Telegram messages successfully sent."""
    if not bot_token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - cannot send notifications.")
        return 0

    messages = build_messages(watchlist_jobs, new_company_jobs, max_per_message)
    sent = 0
    for msg in messages:
        if send_message(bot_token, chat_id, msg):
            sent += 1
    return sent
