import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage import SeenStore
from src.models import Job


def make_job(url="https://example.com/jobs/1"):
    return Job(title="UI Designer", company="Acme", url=url, source="google_cse")


def test_new_store_has_no_jobs():
    with tempfile.TemporaryDirectory() as d:
        store = SeenStore.load(Path(d) / "seen.json")
        assert len(store) == 0
        assert not store.has("anything")


def test_mark_seen_persists_across_load():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "seen.json"
        store = SeenStore.load(path)
        job = make_job()
        job.job_id = "url:abc123"
        store.mark_seen(job, notification_sent=True)
        store.save()

        store2 = SeenStore.load(path)
        assert store2.has("url:abc123")
        entry = store2.get("url:abc123")
        assert entry["notification_sent"] is True
        assert entry["company"] == "Acme"


def test_prune_removes_stale_entries():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "seen.json"
        store = SeenStore.load(path)
        job = make_job()
        job.job_id = "url:old"
        store.mark_seen(job, notification_sent=False)
        # manually backdate
        store._data["url:old"]["last_seen_at"] = "2020-01-01T00:00:00+00:00"
        removed = store.prune(max_age_days=30)
        assert removed == 1
        assert not store.has("url:old")
