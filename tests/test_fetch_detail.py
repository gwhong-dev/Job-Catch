import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from jobcatch import jobkorea, saramin

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 23)


def page(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


class Resp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status


class Router:
    """URL 에 들어 있는 글자로 가짜 응답을 고른다."""

    def __init__(self, routes: dict[str, str]):
        self.routes = routes
        self.urls: list[str] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.urls.append(url)
        for key, text in self.routes.items():
            if key in url:
                return Resp(text)
        return Resp("", 404)


class SaraminFetchDetailTest(unittest.TestCase):
    def test_body_with_workplace_needs_one_request(self):
        router = Router({"view-detail": page("saramin_body.html")})
        with mock.patch.object(saramin.requests, "get", router):
            d = saramin.fetch_detail("1", TODAY, delay_sec=0)
        self.assertEqual(len(router.urls), 1)
        self.assertEqual(d.address, "서울 중구 세종대로 110")
        self.assertIn("주요업무", d.body)
        self.assertIsNone(d.coords)

    def test_body_without_workplace_falls_back_to_view_page(self):
        router = Router({"view-detail": "<p>주요업무 설계</p>", "jobs/view": page("saramin_detail.html")})
        with mock.patch.object(saramin.requests, "get", router):
            d = saramin.fetch_detail("1", TODAY, delay_sec=0)
        self.assertEqual(len(router.urls), 2)
        self.assertEqual(d.address, "서울 중구 세종대로 110")
        self.assertEqual(d.coords, (126.9779451, 37.5662952))
        self.assertIn("주요업무", d.body)


class JobkoreaFetchDetailTest(unittest.TestCase):
    def test_reads_page_and_body(self):
        router = Router({"GI_Read_Comt_Ifrm": page("jobkorea_body.html"), "GI_Read/": page("jobkorea_detail.html")})
        with mock.patch.object(jobkorea.requests, "get", router):
            d = jobkorea.fetch_detail("1", TODAY, delay_sec=0)
        self.assertEqual(len(router.urls), 2)
        self.assertEqual(d.education, "초대졸이상")
        self.assertIn("담당업무", d.body)

    def test_body_failure_keeps_page_values(self):
        router = Router({"GI_Read/": page("jobkorea_detail.html")})
        with mock.patch.object(jobkorea.requests, "get", router):
            d = jobkorea.fetch_detail("1", TODAY, delay_sec=0)
        self.assertEqual(d.education, "초대졸이상")
        self.assertEqual(d.body, "")


if __name__ == "__main__":
    unittest.main()
