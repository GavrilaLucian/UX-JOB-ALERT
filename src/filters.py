"""
Cheap, deterministic keyword prefilter. Runs on every candidate job with
zero API cost, and produces a 0-100 prefilter_score plus reasons. Only jobs
that clear `ai_filter.only_score_if_prefilter_score_at_least` get sent to
the (paid) AI filter, which minimizes AI API costs.
"""
from __future__ import annotations

import re

from .models import Job


def _contains_any(haystack: str, needles: list[str]) -> str | None:
    hs = haystack.lower()
    for n in needles:
        if n.lower() in hs:
            return n
    return None


def prefilter(job: Job, settings: dict) -> Job:
    reasons: list[str] = []
    score = 0
    text_blob = f"{job.title} {job.description_snippet} {job.location_text}"

    title_l = job.title.lower()

    # 1. Excluded seniority / role titles -> hard exclude.
    # Check both explicit phrases (e.g. "Design Lead") and standalone
    # seniority words as whole tokens anywhere in the title (e.g. "Lead
    # Product Designer", "Product Design Director") so word order doesn't
    # let an excluded role slip through.
    excluded_titles = settings.get("excluded_title_keywords", [])
    hit = _contains_any(title_l, excluded_titles)
    seniority_exclude_terms = settings.get("seniority_exclude_terms", [])
    word_hit = None
    for term in seniority_exclude_terms:
        if re.search(rf"\b{re.escape(term.lower())}\b", title_l):
            word_hit = term
            break
    if hit or word_hit:
        job.prefilter_score = 0
        job.prefilter_reasons = [f"excluded title match: {hit or word_hit}"]
        return job

    # 2. Excluded field (branding/marketing/etc) -> hard exclude unless it's
    #    a "Visual Designer" doing digital product work (keep-list override).
    excluded_fields = settings.get("excluded_field_keywords", [])
    field_hit = _contains_any(text_blob, excluded_fields)
    if field_hit:
        keep_keywords = settings.get("visual_designer_keep_keywords", [])
        keep_hit = _contains_any(text_blob, keep_keywords)
        if not ("visual designer" in title_l and keep_hit):
            job.prefilter_score = 0
            job.prefilter_reasons = [f"excluded field match: {field_hit}"]
            return job
        reasons.append(f"visual designer kept due to digital-product signal: {keep_hit}")

    # 3. Role relevance: must match one of the included job title patterns
    include_titles = settings.get("job_titles_include", [])
    role_hit = _contains_any(title_l, include_titles)
    if role_hit:
        score += 40
        reasons.append(f"title matches target role: {role_hit}")
    else:
        # allow generic "designer" + ui/ux/product keyword combos
        if re.search(r"\bdesigner\b", title_l) and re.search(r"\b(ui|ux|product|digital)\b", title_l):
            score += 25
            reasons.append("generic designer title with UI/UX/product signal")
        else:
            job.prefilter_score = 0
            job.prefilter_reasons = ["no target role match in title"]
            return job

    # 4. Seniority: don't over-penalize Senior; only lightly flag it
    if "senior" in title_l:
        score += 5
        reasons.append("senior title - not auto-excluded, needs level review")
    elif re.search(r"\bjunior\b", title_l):
        score += 10
        reasons.append("junior title")
    elif re.search(r"\bmid\b|\bmiddle\b", title_l):
        score += 10
        reasons.append("mid-level title")
    else:
        score += 8
        reasons.append("no explicit seniority in title (neutral)")

    # 5. Location fit
    loc_keywords = settings.get("location_keywords_priority", [])
    remote_signals = settings.get("romania_remote_signals", [])
    loc_hit = _contains_any(text_blob, loc_keywords)
    remote_hit = _contains_any(text_blob, remote_signals)
    is_remote_word = "remote" in text_blob.lower()

    if loc_hit:
        score += 30
        reasons.append(f"location match: {loc_hit}")
    elif is_remote_word and remote_hit:
        score += 25
        reasons.append(f"remote explicitly open to Romania/region: {remote_hit}")
    elif is_remote_word and not remote_hit:
        score += 8
        reasons.append("remote but Romania eligibility unclear - needs review")
    else:
        score += 0
        reasons.append("no Romania/remote location signal found")

    # 6. Watchlist bonus (small, since watchlist companies are pre-vetted)
    if job.is_watchlist_company:
        score += 5
        reasons.append("from tracked watchlist company")

    job.prefilter_score = min(score, 100)
    job.prefilter_reasons = reasons
    return job


def apply_prefilter(jobs: list[Job], settings: dict) -> list[Job]:
    return [prefilter(j, settings) for j in jobs]
