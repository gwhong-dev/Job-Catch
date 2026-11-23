import unittest
from datetime import date, timedelta
from pathlib import Path

from jobcatch import jobkorea
from jobcatch.jobkorea import parse_deadline, parse_search_page, search_params

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 22)


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.jobs = parse_search_page((FIX / "jobkorea_search.html").read_text(encoding="utf-8"), TODAY)

    def test_parse_skips_ads(self):
        self.assertEqual([j.job_id for j in self.jobs], ["11111111", "33333333"])
        for j in self.jobs:
            self.assertEqual(j.source, "jobkorea")
            self.assertEqual(j.url, f"https://www.jobkorea.co.kr/Recruit/GI_Read/{j.job_id}")

    def test_parse_fields(self):
        j = self.jobs[0]
        self.assertEqual(j.title, "백엔드 개발자 신입 채용(예시)")
        self.assertEqual(j.company, "가나소프트(예시)")
        self.assertEqual(j.location, "경기 성남시")
        self.assertEqual(j.career, "신입")
        self.assertIn("백엔드개발자", j.sectors)
        self.assertEqual(self.jobs[1].location, "서울 영등포구 외 5")
        self.assertEqual(self.jobs[1].career, "신입·경력")
        self.assertEqual(self.jobs[1].salary, "월급 ~250만원")

    def test_empty_page(self):
        self.assertEqual(parse_search_page("<html></html>", TODAY), [])


class DeadlineTest(unittest.TestCase):
    def test_parse_deadline(self):
        dec = date(2026, 12, 20)
        self.assertEqual(parse_deadline("~01/20(수)", dec), date(2027, 1, 20))
        self.assertEqual(parse_deadline("~ 12.26(토)", dec), date(2026, 12, 26))
        self.assertEqual(parse_deadline("2026.12.28(월)", dec), date(2026, 12, 28))
        self.assertEqual(parse_deadline("오늘마감", dec), dec)
        self.assertEqual(parse_deadline("내일마감", dec), dec + timedelta(days=1))
        self.assertIsNone(parse_deadline("상시채용", dec))


class ParamsTest(unittest.TestCase):
    def test_search_params(self):
        p = search_params("백엔드", ["신입"], 2)
        self.assertEqual(p["stext"], "백엔드")
        self.assertEqual(p["tabType"], "recruit")
        self.assertEqual(p["ord"], "RegDtDesc")
        self.assertEqual(p["Page_No"], 2)
        self.assertEqual(p["careerType"], 1)
        self.assertNotIn("careerType", search_params("백엔드", ["신입", "경력"], 1))


class ImagesTest(unittest.TestCase):
    def test_parse_images_from_fixture(self):
        html = (FIX / "jobkorea_body_images.html").read_text(encoding="utf-8")
        self.assertEqual(jobkorea.parse_images(html), [
            "https://imgraph.jobkorea.co.kr/images/jobkorea/aaaa1111.png",
            "https://imgraph.jobkorea.co.kr/images/jobkorea/bbbb2222.png",
            "https://file2.jobkorea.co.kr/Net/Mng/DownImage/CorpEditor?file_No=1234",
        ])


if __name__ == "__main__":
    unittest.main()
