import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from jobcatch import history
from jobcatch.models import Job

TODAY = date(2026, 11, 22)


def job(job_id: str, deadline: date | None = None) -> Job:
    return Job(
        source="saramin", job_id=job_id, title=f"공고{job_id}(예시)", company="가나(예시)",
        url=f"u{job_id}", deadline_text="", deadline=deadline, location="", career="",
        education="", employment="", salary="", track="설계",
    )


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data" / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        entries = {}
        history.record(entries, [job("1", TODAY + timedelta(days=3)), job("2")], TODAY)
        history.save(self.path, entries)
        self.assertEqual(history.load(self.path), entries)
        self.assertEqual(entries["saramin:1"].track, "설계")

    def test_roundtrip_card_fields_without_commute(self):
        j = job("1", TODAY + timedelta(days=3))
        j.address, j.location, j.summary, j.required = "서울 중구 세종대로 110", "서울 중구", "지그 설계", "Creo 3년"
        j.tags, j.flags, j.commute_min = ["Creo"], ["학력 확인"], 42
        entries = {}
        history.record(entries, [j], TODAY)
        history.save(self.path, entries)
        loaded = history.load(self.path)["saramin:1"]
        self.assertEqual((loaded.address, loaded.location, loaded.summary, loaded.required, loaded.tags,
                          loaded.flags),
                         ("서울 중구 세종대로 110", "서울 중구", "지그 설계", "Creo 3년", ["Creo"], ["학력 확인"]))
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("42", text)
        self.assertNotIn("commute", text)

    def test_old_format_loads(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"saramin:1": {
            "title": "t", "company": "c", "url": "u", "source": "saramin", "track": "설계",
            "deadline": None, "first_sent": TODAY.isoformat()}}), encoding="utf-8")
        e = history.load(self.path)["saramin:1"]
        self.assertEqual((e.address, e.summary, e.tags), ("", "", []))

    def test_load_missing_is_empty(self):
        self.assertEqual(history.load(self.path), {})

    def test_record_keeps_first_sent(self):
        entries = {}
        history.record(entries, [job("1")], TODAY)
        later = TODAY + timedelta(days=2)
        history.record(entries, [job("1", later + timedelta(days=5))], later)
        self.assertEqual(entries["saramin:1"].first_sent, TODAY)
        self.assertEqual(entries["saramin:1"].deadline, later + timedelta(days=5))

    def test_prune(self):
        entries = {}
        history.record(entries, [job("old", TODAY - timedelta(days=31)),
                                 job("recent", TODAY - timedelta(days=29))], TODAY)
        history.record(entries, [job("nodl")], TODAY - timedelta(days=61))
        history.record(entries, [job("nodl2")], TODAY - timedelta(days=59))
        history.prune(entries, TODAY)
        self.assertEqual(sorted(entries), ["saramin:nodl2", "saramin:recent"])

    def test_record_excluded_and_prune(self):
        entries = {}
        history.record_excluded(entries, [job("x", TODAY + timedelta(days=90))], TODAY - timedelta(days=31))
        history.record_excluded(entries, [job("y")], TODAY - timedelta(days=29))
        self.assertTrue(entries["saramin:x"].excluded)
        history.save(self.path, entries)
        entries = history.load(self.path)
        self.assertTrue(entries["saramin:y"].excluded)
        history.prune(entries, TODAY)
        self.assertEqual(sorted(entries), ["saramin:y"])  # 제외 기록은 30일 뒤 다시 판정

    def test_load_legacy_format_ignored(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"saramin:1": "2026-11-20"}), encoding="utf-8")
        self.assertEqual(history.load(self.path), {})

    def test_load_broken_file_is_empty(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(history.load(self.path), {})


if __name__ == "__main__":
    unittest.main()
