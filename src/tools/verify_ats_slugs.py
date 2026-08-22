"""
Run this locally (with internet access) to check which `ats`/`ats_slug`
entries in config/companies.json actually resolve to a real job board.
The slugs pre-filled in companies.json are best-effort guesses (see the
"_ats_warning" note in that file) and were NOT verified against live APIs.

Usage:
    python -m src.tools.verify_ats_slugs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


def main() -> int:
    companies_path = ROOT_DIR / "config" / "companies.json"
    data = json.loads(companies_path.read_text(encoding="utf-8"))

    ok, bad, skipped = [], [], []

    for company in data.get("companies", []):
        name = company.get("name")
        ats = company.get("ats")
        slug = company.get("ats_slug")
        if not ats or not slug:
            skipped.append(name)
            continue
        url_template = ENDPOINTS.get(ats)
        if not url_template:
            skipped.append(name)
            continue
        url = url_template.format(slug=slug)
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.content:
                ok.append((name, ats, slug))
            else:
                bad.append((name, ats, slug, resp.status_code))
        except requests.RequestException as e:
            bad.append((name, ats, slug, str(e)))

    print(f"\nVALID ({len(ok)}):")
    for name, ats, slug in ok:
        print(f"  ✅ {name}: {ats}:{slug}")

    print(f"\nINVALID / needs fixing or removing ({len(bad)}):")
    for name, ats, slug, err in bad:
        print(f"  ❌ {name}: {ats}:{slug} -> {err}")
        print(f"     Fix: set \"ats\": null, \"ats_slug\": null for {name} in config/companies.json"
              f" (Google Search fallback will still cover it), or find the correct slug from the"
              f" company's actual job board URL.")

    print(f"\nSkipped (no ATS configured, using Google Search fallback only): {len(skipped)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
