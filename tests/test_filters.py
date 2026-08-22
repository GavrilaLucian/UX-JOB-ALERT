import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.filters import prefilter
from src.models import Job

SETTINGS = json.loads((Path(__file__).resolve().parent.parent / "config" / "settings.json").read_text())


def make_job(title, location="", snippet="", watchlist=False):
    return Job(title=title, company="TestCo", url="https://example.com/j", source="google_cse",
               location_text=location, description_snippet=snippet, is_watchlist_company=watchlist)


def test_lead_designer_excluded():
    job = make_job("Lead Product Designer", location="Bucharest")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score == 0


def test_senior_not_auto_excluded():
    job = make_job("Senior Product Designer", location="Bucharest")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score > 0


def test_branding_designer_excluded():
    job = make_job("Brand Designer", location="Bucharest", snippet="logo design and branding")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score == 0


def test_visual_designer_kept_if_digital_product():
    job = make_job("Visual Designer", location="Bucharest",
                    snippet="working on our SaaS platform UI and design system in Figma")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score > 0


def test_ui_only_role_accepted():
    job = make_job("UI Designer", location="Bucharest, Romania")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score > 0


def test_remote_without_romania_signal_scored_lower_than_bucharest():
    remote_job = make_job("Product Designer", location="Remote")
    bucharest_job = make_job("Product Designer", location="Bucharest")
    r1 = prefilter(remote_job, SETTINGS)
    r2 = prefilter(bucharest_job, SETTINGS)
    assert r2.prefilter_score > r1.prefilter_score


def test_irrelevant_role_excluded():
    job = make_job("Backend Engineer", location="Bucharest")
    result = prefilter(job, SETTINGS)
    assert result.prefilter_score == 0
