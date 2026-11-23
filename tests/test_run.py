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

    def test_logs_analysis_counts_only(self):
        from jobcatch.models import Detail

        body = "주요업무\n- 지그 설계(예시)\n자격요건\n- Creo 3년 이상"
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            run.main(["--dry-run"], self.env, self.root, fetchers={"saramin": fake_saramin}, sender=Sender(),
                     today=TODAY, sleep=lambda s: None,
                     details={"saramin": lambda job_id, today: Detail(address="a", body=body)})
        log = out.getvalue() + err.getvalue()
        self.assertIn("상세 읽음 1 · 상세 실패 0 · 본문 1건 중 요약 1 · 필수조건 1 · 내일 다시 0", log)
        self.assertNotIn("지그 설계", log)
        self.assertNotIn("비밀제목", log)

    def run_ai(self, ai_factory, env, body="주요업무\n- 지그 설계(예시)"):
        from jobcatch.models import Detail

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run.main(["--dry-run"], env, self.root, fetchers={"saramin": fake_saramin},
                            sender=Sender(), today=TODAY, sleep=lambda s: None,
                            details={"saramin": lambda job_id, today: Detail(address="a", body=body)},
                            ai_factory=ai_factory)
        return code, out.getvalue(), err.getvalue()

    def test_ai_off_without_key(self):
        calls = []
        code, out, _ = self.run_ai(lambda key, model: calls.append(key), self.env)
        self.assertEqual(code, 0)
        self.assertIn("AI 요약 꺼짐", out)
        self.assertEqual(calls, [])

    def test_ai_counts_logged_without_text(self):
        from jobcatch.ai import AiResult

        made = []

        class FakeAi:
            def analyze(self, body, images, fit_rule, time_left=None):
                return AiResult("업무비밀문구", "필수비밀문구", "상", "이유비밀문구")

        def factory(key, model):
            made.append((key, model))
            return FakeAi()

        env = {"JOBCATCH_CONFIG": CONFIG + 'fit = "기준비밀문구"\n', "GEMINI_API_KEY": "키비밀문구"}
        code, out, err = self.run_ai(factory, env)
        log = out + err
        self.assertEqual(code, 0)
        self.assertEqual(made, [("키비밀문구", "gemini-3.5-flash-lite")])
        self.assertIn("AI 요약 1건 / 대상 1건 · 실패 0 · 건너뜀 0 · 빠진 이미지 0 · 적합도 상 1 중 0 하 0", log)
        for secret in ("업무비밀문구", "필수비밀문구", "이유비밀문구", "키비밀문구", "기준비밀문구", "지그 설계"):
            self.assertNotIn(secret, log)
        html = (self.root / "output" / "mail_2026-11-23.html").read_text(encoding="utf-8")
        self.assertIn("업무비밀문구", html)
        self.assertIn("🎯", html)

    def test_ai_stop_logs_status(self):
        from jobcatch.ai import AiStopped

        class StoppedAi:
            def analyze(self, body, images, fit_rule, time_left=None):
                raise AiStopped(429)

        env = dict(self.env, GEMINI_API_KEY="k")
        _, _, err = self.run_ai(lambda key, model: StoppedAi(), env)
        self.assertIn("경고: AI 요약 중단 (HTTP 429)", err)

    def test_ai_all_failed_logged(self):
        from jobcatch.ai import AiError

        class FailingAi:
            def analyze(self, body, images, fit_rule, time_left=None):
                raise AiError("Gemini HTTP 500")

        env = dict(self.env, GEMINI_API_KEY="k")
        code, _, err = self.run_ai(lambda key, model: FailingAi(), env)
        self.assertEqual(code, 0)
        self.assertIn("경고: AI 요약 전부 실패", err)

    def test_unexpected_ai_error_still_mails(self):
        class BrokenAi:
            def analyze(self, body, images, fit_rule, time_left=None):
                raise UnicodeEncodeError("latin-1", "키비밀", 0, 1, "bad")

        sender = Sender()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run.main([], dict(self.env, GEMINI_API_KEY="k"), self.root,
                            fetchers={"saramin": fake_saramin}, sender=sender, today=TODAY,
                            sleep=lambda s: None, ai_factory=lambda key, model: BrokenAi(),
                            details={"saramin": lambda job_id, today: __import__("jobcatch.models").models.Detail(
                                address="a", body="본문")})
        self.assertEqual(code, 0)
        self.assertEqual(len(sender.subjects), 1)
        self.assertNotIn("키비밀", out.getvalue() + err.getvalue())

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
