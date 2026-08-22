import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dedup import normalize_url, job_key, fuzzy_key, extract_ats_job_id


def test_normalize_url_strips_tracking_params():
    a = "https://www.example.com/jobs/123?utm_source=linkedin&utm_medium=social"
    b = "https://example.com/jobs/123"
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://example.com/jobs/123/") == normalize_url("https://example.com/jobs/123")


def test_extract_greenhouse_job_id():
    url = "https://boards.greenhouse.io/acme/jobs/6789012"
    assert extract_ats_job_id(url, "greenhouse") == "greenhouse:6789012"


def test_job_key_same_for_tracking_variants():
    a = "https://example.com/careers/product-designer?ref=linkedin"
    b = "https://example.com/careers/product-designer?utm_source=indeed"
    assert job_key(a) == job_key(b)


def test_job_key_different_for_different_jobs():
    a = "https://example.com/careers/ui-designer"
    b = "https://example.com/careers/ux-designer"
    assert job_key(a) != job_key(b)


def test_fuzzy_key_ignores_case_and_punctuation():
    k1 = fuzzy_key("Acme Corp.", "UI/UX Designer")
    k2 = fuzzy_key("acme corp", "ui ux designer")
    assert k1 == k2
