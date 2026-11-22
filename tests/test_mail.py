import unittest
from datetime import date, timedelta

from jobcatch.digest import ClosingItem, Digest
from jobcatch.mail import MailError, render_html, send, subject
from jobcatch.models import Job

TODAY = date(2026, 11, 23)  # 월요일


def job(job_id: str, **kw) -> Job:
    base = dict(
        source="saramin", job_id=job_id, title=f"공고{job_id}(예시)", company="가나(예시)",
        url=f"https://example.com/{job_id}", deadline_text="", deadline=None,
        location="경기 성남시", career="신입", education="대졸(2,3년)↑", employment="정규직",
        salary="", track="설계",
    )
    base.update(kw)
    return Job(**base)


def digest(**kw) -> Digest:
    base = dict(today=TODAY, new_by_track={"설계": [], "개발": []}, overflow_by_track={},
                closing=[], failed_sites=[], new_total=0)
    base.update(kw)
    return Digest(**base)


def closing(n: int) -> list[ClosingItem]:
    return [ClosingItem(f"c{i}", "회사", "u", "saramin", "설계", TODAY + timedelta(days=i)) for i in range(n)]


class SubjectTest(unittest.TestCase):
    def test_subject(self):
        self.assertEqual(subject(digest(new_total=12, closing=closing(3))),
                         "[Job-Catch] 11/23(월) 새 공고 12건 · 마감임박 3건")
        self.assertEqual(subject(digest()), "[Job-Catch] 11/23(월) 새 공고 없음")


class HtmlTest(unittest.TestCase):
    def test_escapes(self):
        h = render_html(digest(new_by_track={"설계": [job("1", title="<b>개발</b> & 설계")]}, new_total=1))
        self.assertIn("&lt;b&gt;개발&lt;/b&gt; &amp; 설계", h)
        self.assertNotIn("<b>개발", h)

    def test_warning_first(self):
        h = render_html(digest(failed_sites=["jobkorea"], closing=closing(1)))
        self.assertIn("⚠ 잡코리아 수집 실패", h)
        self.assertLess(h.index("⚠ 잡코리아 수집 실패"), h.index("마감 임박"))

    def test_commute_warning(self):
        self.assertIn("⚠ 통근 시간 계산 실패", render_html(digest(commute_failed=True)))

    def test_overflow_and_flags(self):
        d = digest(new_by_track={"설계": [job("1", flags=["학력 확인"], commute_min=52)], "개발": []},
                   overflow_by_track={"설계": 3}, new_total=4)
        h = render_html(d)
        self.assertIn("외 3건", h)
        self.assertIn("학력 확인", h)
        self.assertIn("🚇 약 52분", h)
        self.assertIn("■ 설계 (4건)", h)
        self.assertIn('href="https://example.com/1"', h)

    def test_no_new(self):
        h = render_html(digest())
        self.assertIn("새 공고가 없습니다.", h)
        self.assertIn("출처: 사람인 · 잡코리아", h)

    def test_card_shows_dday_and_site(self):
        d = digest(closing=[ClosingItem("마감 공고", "다라(예시)", "u", "jobkorea", "개발", TODAY + timedelta(days=3),
                                        location="서울 금천구")])
        h = render_html(d)
        self.assertIn("서울 금천구", h)
        self.assertIn("D-3", h)
        self.assertIn("[잡코리아]", h)


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.logged = None
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        self.logged = (user, password)

    def send_message(self, msg):
        self.sent = msg


ENV = {"GMAIL_USER": "me@example.com", "GMAIL_APP_PASSWORD": "pw", "MAIL_TO": "to@example.com"}


class SendTest(unittest.TestCase):
    def test_send_uses_env(self):
        FakeSMTP.instances.clear()
        send("제목", "<p>본문</p>", ENV, smtp_factory=FakeSMTP)
        s = FakeSMTP.instances[0]
        self.assertEqual((s.host, s.port), ("smtp.gmail.com", 465))
        self.assertEqual(s.logged, ("me@example.com", "pw"))
        self.assertEqual(s.sent["To"], "to@example.com")
        self.assertEqual(s.sent["Subject"], "제목")

    def test_send_missing_env(self):
        env = dict(ENV)
        del env["MAIL_TO"]
        with self.assertRaises(MailError) as ctx:
            send("제목", "본문", env, smtp_factory=FakeSMTP)
        self.assertIn("MAIL_TO", str(ctx.exception))
        self.assertNotIn("pw", str(ctx.exception))
        self.assertNotIn("me@example.com", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
