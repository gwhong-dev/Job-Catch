import unittest
from datetime import date, timedelta

from jobcatch.ai import AiStats
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


STOP_WARN = "⚠ AI 요약 중단 — 일부 카드는 규칙 요약입니다."
FAIL_WARN = "⚠ AI 요약 실패 — 오늘 카드는 모두 규칙 요약입니다."


def with_job(j: Job, **kw) -> Digest:
    return digest(new_by_track={"설계": [j]}, new_total=1, **kw)


class FitTest(unittest.TestCase):
    def test_fit_line_between_place_and_summary(self):
        html = render_html(with_job(job("1", fit="상", fit_reason="직접 설계", summary="요약")))
        self.assertIn("🎯", html)
        self.assertIn("직접 설계", html)
        self.assertLess(html.index("📍"), html.index("🎯"))
        self.assertLess(html.index("🎯"), html.index("📝"))

    def test_fit_without_reason(self):
        html = render_html(with_job(job("1", fit="중")))
        self.assertIn("🎯", html)
        self.assertRegex(html, r"🎯 <b[^>]*>중</b></div>")

    def test_low_fit_still_shown(self):
        html = render_html(with_job(job("1", fit="하", fit_reason="가공 일")))
        self.assertIn("공고1(예시)", html)
        self.assertIn("가공 일", html)

    def test_no_fit_no_line(self):
        self.assertNotIn("🎯", render_html(with_job(job("1", fit=""))))

    def test_fit_line_escaped(self):
        html = render_html(with_job(job("1", fit="하", fit_reason="<script>x</script>")))
        self.assertNotIn("<script>x", html)
        self.assertIn("&lt;script&gt;x", html)

    def test_closing_card_fit(self):
        c = ClosingItem("공고(예시)", "회사", "u", "saramin", "설계", TODAY + timedelta(days=2),
                        fit="상", fit_reason="옛 이유")
        html = render_html(digest(closing=[c]))
        self.assertIn("옛 이유", html)

    def test_ai_stopped_warning(self):
        self.assertIn(STOP_WARN, render_html(digest(ai=AiStats(stopped=429))))

    def test_no_warning_when_ai_off_or_ok(self):
        self.assertNotIn(STOP_WARN, render_html(digest()))
        self.assertNotIn(STOP_WARN, render_html(digest(ai=AiStats(targets=3, done=2, failed=1))))
        self.assertNotIn(FAIL_WARN, render_html(digest(ai=AiStats(targets=3, done=2, failed=1))))
        self.assertNotIn(FAIL_WARN, render_html(digest(ai=AiStats())))

    def test_all_failed_warning(self):
        # 모델이 내려가거나 서버 오류가 계속되면 조용히 규칙 요약만 실리지 않게 경고
        self.assertIn(FAIL_WARN, render_html(digest(ai=AiStats(targets=3, failed=3))))
        h = render_html(digest(ai=AiStats(targets=3, skipped=3, stopped=429)))
        self.assertIn(STOP_WARN, h)
        self.assertNotIn(FAIL_WARN, h)  # 중단 경고 하나로 충분


class HtmlTest(unittest.TestCase):
    def test_required_line(self):
        html = render_html(digest(new_by_track={"설계": [job("1", required="Creo <3년> & 영어")]}, new_total=1))
        self.assertIn("✅ 필수: Creo &lt;3년&gt; &amp; 영어", html)

    def test_no_required_line_when_empty(self):
        html = render_html(digest(new_by_track={"설계": [job("1")]}, new_total=1))
        self.assertNotIn("✅", html)

    def test_escapes(self):
        h = render_html(digest(new_by_track={"설계": [job("1", title="<b>개발</b> & 설계")]}, new_total=1))
        self.assertIn("&lt;b&gt;개발&lt;/b&gt; &amp; 설계", h)
        self.assertNotIn("<b>개발", h)

    def test_warning_first(self):
        h = render_html(digest(failed_sites=["jobkorea"], closing=closing(1)))
        self.assertIn("⚠ 잡코리아 수집 실패", h)
        self.assertLess(h.index("⚠ 잡코리아 수집 실패"), h.index("마감 임박"))

    def test_old_reminder_card_renders_blank(self):
        c = ClosingItem("공고(예시)", "회사", "u", "saramin", "설계", TODAY + timedelta(days=2))
        html = render_html(digest(closing=[c]))
        self.assertNotIn("✅", html)
        self.assertNotIn("📍", html)

    def test_detail_failed_warning(self):
        html = render_html(digest(detail_failed_sites=["jobkorea"]))
        self.assertIn("⚠ 잡코리아 상세 페이지 읽기 실패", html)

    def test_commute_warning(self):
        self.assertIn("⚠ 통근 시간 계산 실패", render_html(digest(commute_failed=True)))

    def test_commute_no_home_warning(self):
        html = render_html(digest(commute_no_home=True))
        self.assertIn("⚠ 통근 계산 꺼짐 — 설정에 집 주소(home_address)가 없습니다.", html)
        self.assertNotIn("통근 계산 꺼짐", render_html(digest()))

    def test_overflow_and_flags(self):
        d = digest(new_by_track={"설계": [job("1", flags=["학력 확인"], commute_min=52)], "개발": []},
                   overflow_by_track={"설계": 3}, new_total=4)
        h = render_html(d)
        self.assertIn("외 3건", h)
        self.assertIn("학력 확인", h)
        self.assertIn("🚇 약 52분", h)
        self.assertIn("■ 설계 (4건)", h)
        self.assertIn('href="https://example.com/1"', h)

    def test_card_shows_address_summary_tags(self):
        j = job("1", address="서울 중구 세종대로 110", summary="컨베이어 설계 / BOM 작성", tags=["Creo", "반도체"])
        h = render_html(digest(new_by_track={"설계": [j], "개발": []}, new_total=1))
        self.assertIn("📍 서울 중구 세종대로 110", h)
        self.assertIn("📝 컨베이어 설계 / BOM 작성", h)
        self.assertIn("Creo", h)
        self.assertNotIn("정규직", h)  # 고용형태 · 학력 줄은 뺐다

    def test_card_falls_back_to_card_location(self):
        h = render_html(digest(new_by_track={"설계": [job("1")], "개발": []}, new_total=1))
        self.assertIn("📍 경기 성남시", h)
        self.assertNotIn("📝", h)

    def test_groups_subheadings_and_toc(self):
        jobs = [job("1", group="기구설계"), job("2", group="기구설계"), job("3", group="기타")]
        h = render_html(digest(new_by_track={"설계": jobs, "개발": [job("4", track="개발")]}, new_total=4))
        self.assertIn("▸ 기구설계 (2)", h)
        self.assertIn("▸ 기타 (1)", h)
        self.assertLess(h.index("▸ 기구설계 (2)"), h.index("공고1(예시)"))
        self.assertLess(h.index("▸ 기타 (1)"), h.index("공고3(예시)"))
        self.assertLess(h.index("공고1(예시)"), h.index("▸ 기타 (1)"))
        toc = h[: h.index("■ 설계")]
        self.assertIn("설계 3건 (기구설계 2 · 기타 1)", toc)
        self.assertIn("개발 1건", toc)

    def test_closing_card_shows_summary(self):
        c = ClosingItem("마감 공고", "다라(예시)", "u", "saramin", "설계", TODAY + timedelta(days=2),
                        location="경기 성남시", address="경기 성남시 분당구 판교역로 1", summary="지그 설계",
                        tags=["지그"])
        h = render_html(digest(closing=[c]))
        self.assertIn("📍 경기 성남시 분당구 판교역로 1", h)
        self.assertIn("📝 지그 설계", h)

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
