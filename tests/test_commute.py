import unittest
from datetime import date
from pathlib import Path

from jobcatch import jobkorea, saramin
from jobcatch.commute import Kakao, KakaoUnavailable, clean_address, commute_status

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 22)


class FakeResp:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeGet:
    def __init__(self, *responses: FakeResp):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params or {}, headers or {}))
        return self.responses.pop(0)


class DetailTest(unittest.TestCase):
    def test_saramin_parse_detail(self):
        d = saramin.parse_detail((FIX / "saramin_detail.html").read_text(encoding="utf-8"), TODAY)
        self.assertEqual(d.address, "서울 중구 세종대로 110")
        self.assertEqual(d.coords, (126.9779451, 37.5662952))

    def test_jobkorea_parse_detail(self):
        d = jobkorea.parse_detail((FIX / "jobkorea_detail.html").read_text(encoding="utf-8"), TODAY)
        self.assertTrue(d.address.startswith("서울 중구 세종대로 110"))
        self.assertEqual(d.deadline, date(2026, 12, 6))
        self.assertEqual(d.education, "초대졸이상")
        self.assertIsNone(d.coords)

    def test_empty_detail(self):
        self.assertEqual(saramin.parse_detail("<html></html>", TODAY).address, "")
        self.assertEqual(jobkorea.parse_detail("<html></html>", TODAY).address, "")


class KakaoTest(unittest.TestCase):
    def test_clean_address(self):
        self.assertEqual(clean_address("서울 종로구 청계천로 41 (서린동, 영풍빌딩) 12층"), "서울 종로구 청계천로 41")
        self.assertEqual(clean_address("(07590) 서울 강서구 화곡로61길 59"), "서울 강서구 화곡로61길 59")
        self.assertEqual(clean_address("경기 성남시 분당구 판교역로 1 3층"), "경기 성남시 분당구 판교역로 1")

    def test_geocode(self):
        get = FakeGet(FakeResp(200, {"documents": [{"x": "127.0", "y": "37.5"}]}),
                      FakeResp(200, {"documents": []}))
        k = Kakao("KEY", get=get)
        self.assertEqual(k.geocode("서울 중구 세종대로 110 (시청) 3층"), (127.0, 37.5))
        self.assertIsNone(k.geocode("없는 주소"))
        url, params, headers = get.calls[0]
        self.assertEqual(url, "https://dapi.kakao.com/v2/local/search/address.json")
        self.assertEqual(params["query"], "서울 중구 세종대로 110")
        self.assertEqual(headers["Authorization"], "KakaoAK KEY")

    def test_transit_minutes(self):
        ok = {"status": "OK", "routes": [{"properties": {"totalTime": 3300}},
                                          {"properties": {"totalTime": 3000}}]}
        get = FakeGet(FakeResp(200, ok), FakeResp(200, {"status": "NO_RESULTS"}))
        k = Kakao("KEY", get=get)
        self.assertEqual(k.transit_minutes((127.11, 37.39), (126.97, 37.56)), 50)
        self.assertIsNone(k.transit_minutes((127.11, 37.39), (126.97, 37.56)))
        url, params, _ = get.calls[0]
        self.assertEqual(url, "https://dapi.kakao.com/v2/routing/publictraffic")
        self.assertEqual((params["start_x"], params["start_y"]), ("127.11", "37.39"))
        self.assertEqual((params["end_x"], params["end_y"]), ("126.97", "37.56"))

    def test_kakao_quota_raises(self):
        k = Kakao("KEY", get=FakeGet(FakeResp(400, {"code": -10, "msg": "API limit has been exceeded."})))
        with self.assertRaises(KakaoUnavailable):
            k.geocode("서울 중구 세종대로 110")

    def test_kakao_bad_key_raises(self):
        k = Kakao("KEY", get=FakeGet(FakeResp(401, {"code": -401})))
        with self.assertRaises(KakaoUnavailable):
            k.transit_minutes((1.0, 2.0), (3.0, 4.0))

    def test_commute_status(self):
        self.assertEqual(commute_status(55, 60, 75), "pass")
        self.assertEqual(commute_status(60, 60, 75), "pass")
        self.assertEqual(commute_status(70, 60, 75), "check")
        self.assertEqual(commute_status(80, 60, 75), "exclude")
        self.assertIsNone(commute_status(None, 60, 75))


if __name__ == "__main__":
    unittest.main()
