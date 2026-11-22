import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import run
from jobcatch.models import Job

TODAY = date(2026, 11, 23)
CONFIG = """
[common]
education = "초대졸"
allow_locations = ["경기 성남시"]

[[track]]
name = "설계"
sites = ["saramin"]
keywords = ["비밀키워드"]
career = ["신입"]
"""


def fake_saramin(keyword, career, max_pages, delay, today):
    return [Job(source="saramin", job_id="1", title="비밀제목(예시)", company="가나(예시)", url="u",
                deadline_text="", deadline=None, location="경기 성남시 분당구", career="신입",
                education="학력무관", employment="정규직", salary="")]


class Sender:
    def __init__(self, fail=False):
        self.fail = fail
        self.subjects: list[str] = []

    def __call__(self, subject, html, env):
        if self.fail:
            raise OSError("smtp down")
        self.subjects.append(subject)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = {"JOBCATCH_CONFIG": CONFIG}
        self.seen = self.root / "data" / "seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, argv, sender=None, env=None):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run.main(argv, env or self.env, self.root, fetchers={"saramin": fake_saramin},
                            sender=sender or Sender(), today=TODAY, sleep=lambda s: None)
        return code, out.getvalue() + err.getvalue()

    def test_dry_run_writes_html_no_history(self):
        code, _ = self.main(["--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "output" / "mail_2026-11-23.html").exists())
        self.assertFalse(self.seen.exists())

    def test_send_failure_keeps_history(self):
        code, log = self.main([], sender=Sender(fail=True))
        self.assertEqual(code, 1)
        self.assertFalse(self.seen.exists())
        self.assertIn("메일 발송 실패", log)

    def test_success_records(self):
        s = Sender()
        self.assertEqual(self.main([], sender=s)[0], 0)
        self.assertTrue(self.seen.exists())
        self.assertEqual(self.main([], sender=s)[0], 0)
        self.assertIn("새 공고 1건", s.subjects[0])
        self.assertIn("새 공고 없음", s.subjects[1])

    def test_excluded_after_lookup_recorded(self):
        from jobcatch import history
        from jobcatch.models import Detail

        def no_edu(*a):
            j = fake_saramin(*a)[0]
            j.education = ""
            return [j]

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run.main([], self.env, self.root, fetchers={"saramin": no_edu}, sender=Sender(),
                            today=TODAY, sleep=lambda s: None,
                            details={"saramin": lambda job_id, today: Detail(education="대졸(4년)↑")})
        self.assertEqual(code, 0)
        self.assertTrue(history.load(self.seen)["saramin:1"].excluded)

    def test_bad_config_exit_2(self):
        code, log = self.main([], env={"JOBCATCH_CONFIG": "["})
        self.assertEqual(code, 2)
        self.assertIn("설정", log)

    def test_logs_no_titles(self):
        _, log = self.main([])
        self.assertNotIn("비밀제목", log)
        self.assertNotIn("비밀키워드", log)
        self.assertIn("사람인 1건", log)


if __name__ == "__main__":
    unittest.main()
