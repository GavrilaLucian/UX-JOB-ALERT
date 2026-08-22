"""
AI relevance scoring, used ONLY for candidates that already passed the free
keyword prefilter (see filters.py) — this is what keeps API costs low.

Provider: Anthropic Claude API (a Claude Haiku model by default), because
it's inexpensive and this is a small classification task. You need an
ANTHROPIC_API_KEY (https://console.anthropic.com/), which is a paid API key
(there is no free tier), billed per token. Cost estimate for this workload:
each candidate job is scored with a short prompt (~250-400 input tokens,
~120 output tokens). Even on a busy day with e.g. 40 candidates scored,
that's roughly 16,000 input + 4,800 output tokens/day. At current Haiku
pricing (see https://www.anthropic.com/pricing for up-to-date numbers) that
is a fraction of a cent to a few cents per day - well under $1/month for
this workload. If you'd rather not pay anything, set
`ai_filter.enabled: false` in config/settings.json and the system will rank
jobs using only the free keyword prefilter score.
"""
from __future__ import annotations

import json
import logging

from .models import Job

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a strict, consistent job-relevance classifier for a UI/UX/Product \
Designer based in Bucharest, Romania who has ~4 years of experience (junior-to-mid, \
sometimes senior-accessible). You will be given ONE job posting's title, company, \
location text, and a short description snippet. Score it from 0-100 on how well it fits:

Rules:
- UI-only, UX-only, or full Product Design roles are all acceptable - do not require \
"full UX+UI".
- Junior, Mid, and reasonably-accessible Senior roles are acceptable. Do NOT auto-exclude \
"Senior" in the title if requirements look like a normal senior IC role.
- Lead / Staff / Principal / Head of Design / Design Manager / Director / VP roles must \
score below 20, always.
- Roles that are primarily graphic design, branding, logo design, marketing/social media \
design, motion graphics, video editing, or print design must score below 20 - UNLESS the \
posting is clearly about digital product UI (then treat it as a normal UI role).
- Location: Bucharest or other Romania cities score highest. Remote roles must EXPLICITLY \
allow Romania (or EU/Europe-wide remote) to score well; remote roles that seem US-only, \
or where Romania eligibility is unclear, should be scored lower (max ~50) with that noted \
in your reason.
- Respond with STRICT JSON ONLY, no markdown fences, no preamble, matching this schema:
{"score": <integer 0-100>, "level_guess": "<Junior|Mid|Senior|Lead+|Unclear>", \
"reason": "<one short sentence in Romanian, max ~20 words, explaining the score>"}
"""

USER_TEMPLATE = """Title: {title}
Company: {company}
Location text: {location}
Snippet: {snippet}
"""


def _build_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def score_job(client, model: str, job: Job) -> tuple[int, str, str]:
    """Returns (score, level_guess, reason). Falls back to prefilter score on any error."""
    user_msg = USER_TEMPLATE.format(
        title=job.title,
        company=job.company,
        location=job.location_text or "unknown",
        snippet=(job.description_snippet or "")[:600],
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        data = json.loads(text)
        score = int(data.get("score", job.prefilter_score))
        score = max(0, min(100, score))
        level = str(data.get("level_guess", "Unclear"))
        reason = str(data.get("reason", ""))
        return score, level, reason
    except Exception as e:  # noqa: BLE001 - never let one bad job kill the run
        log.warning("AI scoring failed for '%s' at %s: %s", job.title, job.company, e)
        return job.prefilter_score, "Unclear", "AI scoring failed - fell back to keyword prefilter score"


def apply_ai_filter(
    jobs: list[Job],
    api_key: str | None,
    model: str,
    min_prefilter_score: int,
    max_candidates: int,
) -> list[Job]:
    if not api_key:
        log.info("ANTHROPIC_API_KEY not set - skipping AI filter, using prefilter scores only.")
        return jobs

    candidates = [j for j in jobs if j.prefilter_score >= min_prefilter_score]
    candidates.sort(key=lambda j: j.prefilter_score, reverse=True)
    candidates = candidates[:max_candidates]
    scored_keys = {id(j) for j in candidates}

    if not candidates:
        return jobs

    try:
        client = _build_client(api_key)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not initialize Anthropic client: %s", e)
        return jobs

    for job in candidates:
        score, level, reason = score_job(client, model, job)
        job.ai_score = score
        job.level_guess = level
        job.ai_reasons = reason

    # Jobs that didn't reach the AI step keep only their prefilter score
    # (final_score() on Job already falls back correctly).
    return jobs
