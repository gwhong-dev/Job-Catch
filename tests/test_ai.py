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


def img(size: int, mime: str = "image/jpeg") -> Resp:
    return Resp(200, text="", content=b"\xff" * size, headers={"Content-Type": mime})


class DownloadTest(unittest.TestCase):
    def test_download_limits(self):
        urls = [f"https://pds.saramin.co.kr/{i}.jpg" for i in range(8)]
        responses = {u: img(10) for u in urls}
        responses[urls[1]] = img(4_000_001)
        responses[urls[2]] = img(10, "image/gif")
        responses[urls[3]] = img(3_900_000)
        responses[urls[4]] = img(3_900_000, "image/png")
        responses[urls[5]] = img(3_900_000, "image/webp; charset=binary")
        # 0(10) + 3 + 4 + 5 = 11,700,010. 6, 7 번째는 6장 상한 밖
        sleeps: list[float] = []
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=sleeps.append)
        self.assertEqual([m for m, _ in got], ["image/jpeg", "image/jpeg", "image/png", "image/webp"])
        self.assertEqual(dropped, 4)
        self.assertEqual(sleeps, [1] * 5)

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
            urls[1]: Resp(404, text="", content=b"", headers={"Content-Type": "image/jpeg"}),
            urls[2]: requests.ConnectionError("x"),
            urls[3]: img(5, "image/jpg"),
        }
        got, dropped = download_images(urls, get=FakeGet(responses), sleep=lambda s: None)
        self.assertEqual(got, [("image/jpeg", b"\xff" * 5)])
        self.assertEqual(dropped, 3)

    def test_empty(self):
        self.assertEqual(download_images([], get=FakeGet({}), sleep=lambda s: None), ([], 0))


if __name__ == "__main__":
    unittest.main()
