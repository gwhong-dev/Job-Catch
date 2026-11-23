import base64
import json
import unittest

import requests

from jobcatch.ai import (
    AiError, AiResult, AiStopped, Gemini, clip, download_images,
)

KEY = "AIzaFAKEKEY123"


class Resp:
    def __init__(self, status=200, payload=None, text=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {}, ensure_ascii=False)
        self.content = content
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def ok(obj) -> Resp:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def rate_limited(delay: str | None = None) -> Resp:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}] if delay else []
    return Resp(429, {"error": {"code": 429, "message": "quota 본문비밀", "details": details}})


class FakePost:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    def __init__(self, *values):
        self.values = list(values)
        self.last = values[-1] if values else 0

    def __call__(self):
        if self.values:
            self.last = self.values.pop(0)
        return self.last


def gemini(post, sleeps=None, clock=None) -> Gemini:
    sleeps = sleeps if sleeps is not None else []
    return Gemini(KEY, post=post, sleep=sleeps.append, clock=clock or Clock(0))


GOOD = {"duty": "설계 / 도면", "required": "CAD", "fit": "상", "reason": "직접 설계"}


class AnalyzeTest(unittest.TestCase):
    def test_parses_schema_response(self):
        g = gemini(FakePost(ok(GOOD)))
        self.assertEqual(g.analyze("본문", [], "설계 기준"), AiResult("설계 / 도면", "CAD", "상", "직접 설계"))

    def test_key_in_header_not_url(self):
        post = FakePost(ok(GOOD))
        gemini(post).analyze("본문", [], "기준")
        call = post.calls[0]
        self.assertNotIn(KEY, call["url"])
        self.assertEqual(call["headers"]["x-goog-api-key"], KEY)
        self.assertIn("gemini-3.5-flash-lite:generateContent", call["url"])

    def test_body_truncated_to_12000(self):
        post = FakePost(ok(GOOD))
        gemini(post).analyze("뷁" * 20000, [], "기준")
        text = post.calls[0]["json"]["contents"][0]["parts"][0]["text"]
        self.assertEqual(text.count("뷁"), 12000)

    def test_images_sent_inline(self):
        post = FakePost(ok(GOOD))
        gemini(post).analyze("본문", [("image/png", b"x")], "기준")
        parts = post.calls[0]["json"]["contents"][0]["parts"]
        self.assertIn({"inline_data": {"mime_type": "image/png", "data": "eA=="}}, parts)

    def test_fit_rule_in_prompt_and_schema(self):
        post = FakePost(ok(GOOD))
        gemini(post).analyze("본문", [], "직접 설계하는 일")
        body = post.calls[0]["json"]
        self.assertIn("직접 설계하는 일", body["contents"][0]["parts"][0]["text"])
        schema = body["generationConfig"]["response_schema"]
        self.assertEqual(schema["properties"]["fit"]["enum"], ["상", "중", "하"])
        self.assertIn("fit", schema["required"])
        self.assertEqual(body["generationConfig"]["response_mime_type"], "application/json")

    def test_no_fit_rule_omits_fit(self):
        post = FakePost(ok(GOOD))
        r = gemini(post).analyze("본문", [], "")
        schema = post.calls[0]["json"]["generationConfig"]["response_schema"]
        self.assertNotIn("fit", schema["properties"])
        self.assertNotIn("적합도", post.calls[0]["json"]["contents"][0]["parts"][0]["text"])
        self.assertEqual((r.fit, r.reason), ("", ""))
        self.assertEqual(r.duty, "설계 / 도면")

    def test_invalid_fit_value_dropped(self):
        r = gemini(FakePost(ok(dict(GOOD, fit="매우 좋음")))).analyze("본문", [], "기준")
        self.assertEqual((r.fit, r.reason), ("", ""))

    def test_long_values_clipped(self):
        r = gemini(FakePost(ok(dict(GOOD, duty="가" * 200, required="나" * 200, reason="다" * 100)))).analyze(
            "본문", [], "기준")
        self.assertLessEqual(len(r.duty), 80)
        self.assertLessEqual(len(r.required), 80)
        self.assertLessEqual(len(r.reason), 40)

    def test_non_string_values_become_empty(self):
        r = gemini(FakePost(ok({"duty": ["x"], "required": None, "fit": "중", "reason": 3}))).analyze(
            "본문", [], "기준")
        self.assertEqual(r, AiResult("", "", "중", ""))


class ClipTest(unittest.TestCase):
    def test_clip_long_single_item(self):
        self.assertLessEqual(len(clip("가" * 200, 80)), 80)
        self.assertTrue(clip("가" * 200, 80).endswith("…"))

    def test_clip_reason_40(self):
        self.assertLessEqual(len(clip("나" * 100, 40)), 40)

    def test_clip_cuts_at_item_boundary(self):
        text = " / ".join(["설비 기구 설계 업무"] * 10)
        out = clip(text, 80)
        self.assertLessEqual(len(out), 80)
        self.assertTrue(out.startswith("설비 기구 설계 업무 / "))

    def test_short_kept_and_spaces_folded(self):
        self.assertEqual(clip("설계직", 40), "설계직")
        self.assertEqual(clip(" 도면\n작성 ", 80), "도면 작성")
        self.assertEqual(clip("", 80), "")


class PacingTest(unittest.TestCase):
    def test_paces_4_seconds(self):
        sleeps: list[float] = []
        g = gemini(FakePost(ok(GOOD), ok(GOOD)), sleeps, Clock(0, 1))
        g.analyze("a", [], "")
        g.analyze("b", [], "")
        self.assertEqual(sleeps, [3])

    def test_no_wait_when_enough_time_passed(self):
        sleeps: list[float] = []
        g = gemini(FakePost(ok(GOOD), ok(GOOD)), sleeps, Clock(0, 10))
        g.analyze("a", [], "")
        g.analyze("b", [], "")
        self.assertEqual(sleeps, [])


class ErrorTest(unittest.TestCase):
    def test_retry_once_on_429(self):
        sleeps: list[float] = []
        post = FakePost(rate_limited("7s"), ok(GOOD))
        r = gemini(post, sleeps, Clock(0, 100)).analyze("본문", [], "기준")
        self.assertIn(7, sleeps)
        self.assertEqual(r.fit, "상")
        self.assertEqual(len(post.calls), 2)

    def test_429_without_delay_waits_30(self):
        sleeps: list[float] = []
        gemini(FakePost(rate_limited(), ok(GOOD)), sleeps, Clock(0, 100)).analyze("본문", [], "기준")
        self.assertIn(30, sleeps)

    def test_429_with_long_delay_stops_without_waiting(self):
        sleeps: list[float] = []
        post = FakePost(rate_limited("3600s"))
        with self.assertRaises(AiStopped) as cm:
            gemini(post, sleeps).analyze("본문", [], "기준")
        self.assertEqual(cm.exception.status, 429)
        self.assertEqual(sleeps, [])
        self.assertEqual(len(post.calls), 1)

    def test_second_429_raises_stopped(self):
        with self.assertRaises(AiStopped) as cm:
            gemini(FakePost(rate_limited("1s"), rate_limited("1s"))).analyze("본문", [], "기준")
        self.assertEqual(cm.exception.status, 429)

    def test_404_model_gone_raises_stopped(self):
        with self.assertRaises(AiStopped) as cm:
            gemini(FakePost(Resp(404, {"error": {"status": "NOT_FOUND"}}))).analyze("본문", [], "")
        self.assertEqual(cm.exception.status, 404)

    def test_timeout_capped_by_time_left(self):
        post = FakePost(ok(GOOD))
        gemini(post, clock=Clock(0, 0, 0)).analyze("본문", [], "", time_left=30)
        self.assertLessEqual(post.calls[0]["timeout"], 30)
        post = FakePost(ok(GOOD))
        gemini(post).analyze("본문", [], "")
        self.assertEqual(post.calls[0]["timeout"], 120)

    def test_no_time_left_no_call(self):
        post = FakePost(ok(GOOD))
        with self.assertRaises(AiError):
            gemini(post).analyze("본문", [], "", time_left=2)
        self.assertEqual(post.calls, [])

    def test_retry_skipped_when_wait_exceeds_time_left(self):
        sleeps: list[float] = []
        post = FakePost(rate_limited("30s"), ok(GOOD))
        with self.assertRaises(AiError):
            gemini(post, sleeps).analyze("본문", [], "", time_left=20)
        self.assertEqual(len(post.calls), 1)
        self.assertNotIn(30, sleeps)

    def test_401_403_raise_stopped(self):
        for status in (401, 403):
            with self.subTest(status=status):
                with self.assertRaises(AiStopped) as cm:
                    gemini(FakePost(Resp(status, {"error": {"message": "x"}}))).analyze("본문", [], "")
                self.assertEqual(cm.exception.status, status)

    def test_invalid_key_400_raises_stopped(self):
        bad = Resp(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                   "details": [{"reason": "API_KEY_INVALID"}]}})
        with self.assertRaises(AiStopped) as cm:
            gemini(FakePost(bad)).analyze("본문", [], "")
        self.assertEqual(cm.exception.status, 400)

    def test_500_and_bad_json_raise_ai_error(self):
        cases = [
            Resp(500, {"error": {}}),
            Resp(400, {"error": {"status": "INVALID_ARGUMENT"}}),
            ok("이건 JSON 이 아님"),
            ok(["목록"]),
            Resp(200, {"candidates": []}),
            Resp(200, None, text="<html>"),
            requests.Timeout("read timed out"),
        ]
        for resp in cases:
            with self.subTest(resp=resp):
                with self.assertRaises(AiError):
                    gemini(FakePost(resp)).analyze("본문", [], "")

    def test_error_message_has_no_body_or_key(self):
        cases = [Resp(500, {"error": {"message": "본문비밀"}}), ok("본문비밀 not json"),
                 requests.ConnectionError(f"key={KEY} 본문비밀")]
        for resp in cases:
            with self.assertRaises(AiError) as cm:
                gemini(FakePost(resp)).analyze("본문비밀", [], "기준비밀")
            for secret in ("본문비밀", "기준비밀", KEY):
                self.assertNotIn(secret, str(cm.exception))
        with self.assertRaises(AiStopped) as cm:
            gemini(FakePost(rate_limited("1s"), rate_limited("1s"))).analyze("본문비밀", [], "기준비밀")
        for secret in ("본문비밀", "기준비밀", KEY):
            self.assertNotIn(secret, str(cm.exception))


class FakeGet:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.urls: list[str] = []

    def __call__(self, url, headers=None, timeout=None):
        self.urls.append(url)
        r = self.responses[url]
        if isinstance(r, Exception):
            raise r
        return r


MAGIC = {"jpeg": b"\xff\xd8\xff\xe0", "png": b"\x89PNG\r\n\x1a\n", "webp": b"RIFF\x00\x00\x00\x00WEBPVP8 ",
         "gif": b"GIF89a"}


def img(size: int, kind: str = "jpeg", content_type: str = "image/jpeg") -> Resp:
    head = MAGIC[kind]
    return Resp(200, text="", content=head + b"\x00" * (size - len(head)), headers={"Content-Type": content_type})


class DownloadTest(unittest.TestCase):
    def test_download_limits(self):
        urls = [f"https://pds.saramin.co.kr/{i}.jpg" for i in range(8)]
        responses = {u: img(10) for u in urls}
        responses[urls[1]] = img(7_000_001)
        responses[urls[2]] = img(10, "gif", "image/gif")
        responses[urls[3]] = img(3_900_000)
        responses[urls[4]] = img(3_900_000, "png", "image/png")
        responses[urls[5]] = img(3_900_000, "webp", "image/webp; charset=binary")
        # 0(10) + 3 + 4 + 5 = 11,700,010. 6, 7 번째는 6장 상한 밖
        sleeps: list[float] = []
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=sleeps.append)
        self.assertEqual([m for m, _ in got], ["image/jpeg", "image/jpeg", "image/png", "image/webp"])
        self.assertEqual(dropped, 4)
        self.assertEqual(sleeps, [1] * 5)

    def test_big_poster_image_kept(self):
        # 세로로 긴 공고 이미지는 5MB 를 넘기도 한다 (실제 5.6MB PNG 확인)
        got, dropped = download_images(["https://x/a.png"], get=FakeGet({"https://x/a.png": img(5_634_178, "png")}),
                                       sleep=lambda s: None)
        self.assertEqual((len(got), dropped), (1, 0))

    def test_type_from_bytes_not_header(self):
        # file2.jobkorea.co.kr 는 JPEG 를 application/octet-stream 으로 준다
        urls = ["https://x/a", "https://x/b"]
        responses = {urls[0]: img(100, "jpeg", "application/octet-stream"),
                     urls[1]: Resp(200, text="<html>", content=b"<html><body>error</body></html>",
                                   headers={"Content-Type": "image/jpeg"})}
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=lambda s: None)
        self.assertEqual([m for m, _ in got], ["image/jpeg"])
        self.assertEqual(dropped, 1)

    def test_total_over_14mb_dropped(self):
        urls = [f"https://pds.saramin.co.kr/{i}.jpg" for i in range(4)]
        responses = {u: img(3_900_000) for u in urls}
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=lambda s: None)
        self.assertEqual(len(got), 3)
        self.assertEqual(dropped, 1)

    def test_download_skips_non_image(self):
        urls = ["https://pds.saramin.co.kr/a.jpg", "https://pds.saramin.co.kr/b.jpg",
                "https://pds.saramin.co.kr/c.jpg", "https://pds.saramin.co.kr/d.jpg"]
        responses = {
            urls[0]: Resp(200, text="<html>", content=b"<html>", headers={"Content-Type": "text/html"}),
            urls[1]: Resp(404, text="", content=MAGIC["jpeg"], headers={"Content-Type": "image/jpeg"}),
            urls[2]: requests.ConnectionError("x"),
            urls[3]: img(5, "jpeg", "image/jpg"),
        }
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=lambda s: None)
        self.assertEqual(got, [("image/jpeg", MAGIC["jpeg"] + b"\x00")])
        self.assertEqual(dropped, 3)

    def test_empty(self):
        self.assertEqual(download_images([], get=FakeGet({}), sleep=lambda s: None), ([], 0))



# ---- enrich_jobs (카드 선택 뒤 AI 단계) ----
from jobcatch.ai import AiStats, enrich_jobs  # noqa: E402
from jobcatch.models import Job  # noqa: E402


def make_job(job_id: str, body: str = "본문", images=None, track: str = "설계", **kw) -> Job:
    j = Job(source="saramin", job_id=job_id, title=f"공고{job_id}(예시)", company="가나(예시)", url="u",
            deadline_text="", deadline=None, location="경기", career="신입", education="", employment="",
            salary="", track=track, **kw)
    j.body = body
    j.images = list(images or [])
    return j


class FakeGemini:
    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, list, str]] = []
        self.time_left: list[float | None] = []

    def analyze(self, body, images, fit_rule, time_left=None):
        self.calls.append((body, images, fit_rule))
        self.time_left.append(time_left)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def no_download(urls):
    return [("image/jpeg", b"x") for _ in urls], 0


R = AiResult("AI 요약", "AI 필수", "상", "이유")


class EnrichTest(unittest.TestCase):
    def test_image_only_job_is_target(self):
        ai = FakeGemini(R)
        stats = enrich_jobs([make_job("1", body="", images=["https://pds.saramin.co.kr/a.jpg"])],
                            {"설계": "기준"}, ai, download=no_download)
        self.assertEqual((stats.targets, stats.done), (1, 1))
        self.assertEqual(len(ai.calls[0][1]), 1)

    def test_title_sent_with_body(self):
        ai = FakeGemini(R)
        enrich_jobs([make_job("1", body="본문")], {}, ai, download=no_download)
        self.assertIn("공고1(예시)", ai.calls[0][0])
        self.assertIn("본문", ai.calls[0][0])

    def test_no_body_no_images_not_target(self):
        ai = FakeGemini()
        stats = enrich_jobs([make_job("1", body="  ")], {}, ai, download=no_download)
        self.assertEqual((stats.targets, stats.done), (0, 0))
        self.assertEqual(ai.calls, [])

    def test_fit_rule_by_track(self):
        ai = FakeGemini(R, R)
        enrich_jobs([make_job("1"), make_job("2", track="개발")], {"설계": "설계 기준"}, ai, download=no_download)
        self.assertEqual([c[2] for c in ai.calls], ["설계 기준", ""])

    def test_ai_result_overrides_rule_only_when_nonempty(self):
        j = make_job("1", summary="규칙 요약", required="규칙 필수")
        enrich_jobs([j], {}, FakeGemini(AiResult("AI 요약", "", "", "")), download=no_download)
        self.assertEqual((j.summary, j.required), ("AI 요약", "규칙 필수"))

    def test_sets_fit_and_counts(self):
        a, b = make_job("1"), make_job("2")
        stats = enrich_jobs([a, b], {"설계": "기준"},
                            FakeGemini(R, AiResult("x 업무", "", "하", "가공 일")), download=no_download)
        self.assertEqual((a.fit, a.fit_reason, b.fit, b.fit_reason), ("상", "이유", "하", "가공 일"))
        self.assertEqual(stats.fit, {"상": 1, "중": 0, "하": 1})

    def test_ai_error_keeps_rule_and_continues(self):
        a, b = make_job("1", summary="규칙"), make_job("2")
        stats = enrich_jobs([a, b], {}, FakeGemini(AiError("x"), R), download=no_download)
        self.assertEqual((stats.failed, stats.done), (1, 1))
        self.assertEqual((a.summary, a.fit), ("규칙", ""))
        self.assertEqual(b.summary, "AI 요약")

    def test_stop_marks_rest_skipped(self):
        ai = FakeGemini(R, AiStopped(429))
        stats = enrich_jobs([make_job("1"), make_job("2"), make_job("3")], {}, ai, download=no_download)
        self.assertEqual(stats.stopped, 429)
        self.assertEqual(len(ai.calls), 2)
        self.assertEqual((stats.done, stats.skipped, stats.targets), (1, 2, 3))

    def test_time_limit_skips_rest(self):
        ai = FakeGemini(R, R, R)
        stats = enrich_jobs([make_job("1"), make_job("2"), make_job("3")], {}, ai,
                            download=no_download, clock=Clock(0, 1, 481))
        self.assertEqual((stats.done, stats.skipped), (1, 2))
        self.assertIsNone(stats.stopped)

    def test_time_left_passed_to_analyze(self):
        ai = FakeGemini(R)
        enrich_jobs([make_job("1")], {}, ai, download=no_download, clock=Clock(0, 30))
        self.assertEqual(ai.time_left, [450])

    def test_time_checked_after_download(self):
        # 이미지 내려받기에 시간을 다 쓰면 AI 를 부르지 않고 남은 공고와 함께 건너뜀
        ai = FakeGemini(R, R)
        stats = enrich_jobs([make_job("1", images=["a"]), make_job("2")], {}, ai,
                            download=no_download, clock=Clock(0, 481))
        self.assertEqual(ai.calls, [])
        self.assertEqual((stats.done, stats.skipped), (0, 2))

    def test_unexpected_exception_counts_failed(self):
        def broken_download(urls):
            raise ValueError("이상한 응답")

        a, b, c = make_job("1", summary="규칙"), make_job("2", images=["x"]), make_job("3")
        ai = FakeGemini(KeyError("x"), R, UnicodeEncodeError("latin-1", "키", 0, 1, "bad"))
        stats = enrich_jobs([a, b, c], {}, ai, download=broken_download)
        self.assertEqual((stats.failed, stats.done), (2, 1))
        self.assertEqual(a.summary, "규칙")
        self.assertEqual(stats.dropped_images, 1)  # 내려받기가 깨지면 그 공고 이미지 전부 뺀 것으로
        self.assertEqual(ai.calls[1][1], [])  # 이미지 없이 본문만이라도 보냄

    def test_dropped_images_summed(self):
        def download(urls):
            return [], len(urls)

        stats = enrich_jobs([make_job("1", images=["a", "b"]), make_job("2", images=["c"])], {},
                            FakeGemini(R, R), download=download)
        self.assertEqual(stats.dropped_images, 3)

    def test_empty_stats(self):
        self.assertEqual(AiStats().fit, {"상": 0, "중": 0, "하": 0})


if __name__ == "__main__":
    unittest.main()
