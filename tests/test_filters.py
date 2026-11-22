import unittest

from jobcatch.config import Common, Track
from jobcatch.filters import classify, location_status, min_career_months, required_education
from jobcatch.models import Job


def job(**kw) -> Job:
    base = dict(
        source="saramin", job_id="1", title="기구설계 엔지니어", company="가나정밀(예시)",
        url="u", deadline_text="", deadline=None, location="경기 성남시 분당구",
        career="신입", education="학력무관", employment="정규직", salary="",
    )
    base.update(kw)
    return Job(**base)


ALLOW = ["경기 성남시", "서울 금천구"]
COMMON = Common(education="초대졸", my_career_months=48, allow_locations=ALLOW,
                exclude_words=["영업"], exclude_employment=["파견직"])
BOTH = Track(name="설계", sites=["saramin"], keywords=["기구설계"], career=["신입", "경력"])
NEW = Track(name="개발", sites=["jobkorea"], keywords=["백엔드"], career=["신입"])


class EducationTest(unittest.TestCase):
    def test_required_education(self):
        self.assertEqual(required_education("대졸(2,3년)↑"), "초대졸")
        self.assertEqual(required_education("초대졸↑"), "초대졸")
        self.assertEqual(required_education("대졸(4년)↑"), "대졸")
        self.assertEqual(required_education("대졸이상"), "대졸")
        self.assertEqual(required_education("학력무관"), "학력무관")
        self.assertEqual(required_education("고졸↑"), "고졸")
        self.assertEqual(required_education("석사↑"), "석사")
        self.assertIsNone(required_education(""))


class CareerTest(unittest.TestCase):
    def test_min_career_months(self):
        self.assertEqual(min_career_months("신입"), 0)
        self.assertEqual(min_career_months("신입·경력"), 0)
        self.assertEqual(min_career_months("경력무관"), 0)
        self.assertEqual(min_career_months("경력 3년↑"), 36)
        self.assertEqual(min_career_months("경력3년↑"), 36)
        self.assertEqual(min_career_months("경력 5~10년"), 60)
        self.assertIsNone(min_career_months("경력"))


class LocationTest(unittest.TestCase):
    def test_location_status(self):
        cases = {
            "경기 성남시 분당구": "pass",
            "서울 금천구": "pass",
            "부산 해운대구": "exclude",
            "서울": "check",
            "서울 전체": "check",
            "서울 종로구 외 14": "check",
            "서울 금천구 외 2": "check",
            "경기 성남시, 부산 중구": "check",
            "부산 중구, 대구 중구": "exclude",
            "전국": "check",
            "재택근무": "check",
            "": "check",
        }
        for loc, want in cases.items():
            with self.subTest(loc=loc):
                self.assertEqual(location_status(loc, ALLOW), want)


class ClassifyTest(unittest.TestCase):
    def test_excludes_four_year_degree(self):
        self.assertEqual(classify(job(education="대졸(4년)↑"), COMMON, BOTH)[0], "exclude")

    def test_allows_junior_college(self):
        self.assertEqual(classify(job(education="대졸(2,3년)↑"), COMMON, BOTH), ("pass", []))

    def test_career_track(self):
        self.assertEqual(classify(job(career="경력 3년↑"), COMMON, BOTH)[0], "pass")
        self.assertEqual(classify(job(career="경력 7년↑"), COMMON, BOTH)[0], "exclude")
        self.assertEqual(classify(job(career="경력 3년↑"), COMMON, NEW)[0], "exclude")
        self.assertEqual(classify(job(career="신입·경력"), COMMON, NEW)[0], "pass")

    def test_unknown_education_flags(self):
        self.assertEqual(classify(job(education=""), COMMON, BOTH), ("check", ["학력 확인"]))

    def test_unknown_career_flags(self):
        self.assertEqual(classify(job(career="경력"), COMMON, BOTH), ("check", ["경력 확인"]))

    def test_unsure_location_flags(self):
        self.assertEqual(classify(job(location="서울"), COMMON, BOTH), ("check", ["지역 확인"]))

    def test_exclude_words_and_employment(self):
        self.assertEqual(classify(job(title="기구 영업 담당"), COMMON, BOTH)[0], "exclude")
        self.assertEqual(classify(job(employment="파견직"), COMMON, BOTH)[0], "exclude")

    def test_include_any(self):
        t = Track(name="개발", sites=["jobkorea"], keywords=["개발"], career=["신입"],
                  include_any=["python"])
        self.assertEqual(classify(job(title="Python 백엔드"), COMMON, t)[0], "pass")
        self.assertEqual(classify(job(title="Java 백엔드"), COMMON, t)[0], "exclude")


if __name__ == "__main__":
    unittest.main()
