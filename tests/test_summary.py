import unittest
from datetime import date
from pathlib import Path

from jobcatch import jobkorea, saramin
from jobcatch.summary import extract_duty, find_tags, group_of

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 23)


class BodyTest(unittest.TestCase):
    def test_saramin_parse_body(self):
        body, address = saramin.parse_body((FIX / "saramin_body.html").read_text(encoding="utf-8"))
        self.assertIn("주요업무", body)
        self.assertEqual(address, "서울 중구 세종대로 110")

    def test_jobkorea_parse_body(self):
        body = jobkorea.parse_body((FIX / "jobkorea_body.html").read_text(encoding="utf-8"))
        self.assertIn("담당업무", body)
        self.assertIn("Spring", body)

    def test_empty_body(self):
        self.assertEqual(saramin.parse_body("<html></html>"), ("", ""))
        self.assertEqual(jobkorea.parse_body("<html></html>"), "")


class DutyTest(unittest.TestCase):
    def test_extract_duty_saramin(self):
        body, _ = saramin.parse_body((FIX / "saramin_body.html").read_text(encoding="utf-8"))
        self.assertEqual(extract_duty(body),
                         "반도체 장비 기구설계, 설계 검증 / 시스템 기구 도면 및 BOM 작성 / 컨베이어 모듈 개선")

    def test_extract_duty_jobkorea(self):
        body = jobkorea.parse_body((FIX / "jobkorea_body.html").read_text(encoding="utf-8"))
        duty = extract_duty(body)
        self.assertTrue(duty.startswith("선배 개발자의 멘토링 아래"))
        self.assertNotIn("Java", duty)

    def test_extract_duty_cut(self):
        long = "주요업무 " + "가" * 200 + " 자격요건 x"
        duty = extract_duty(long)
        self.assertLessEqual(len(duty), 80)
        self.assertTrue(duty.endswith("…"))

    def test_bracket_heading(self):
        self.assertEqual(extract_duty("[담당업무] 가스보일러 연구 [자격요건] 경력 3년"), "가스보일러 연구")

    def test_other_duty_headings(self):
        self.assertEqual(extract_duty("수행업무\n- 지그 설계\n우대사항\n- Creo"), "지그 설계")
        self.assertEqual(extract_duty("이런 일을 해요\n• 컨베이어 설계\n이런 분을 찾아요\n• 경력 3년"), "컨베이어 설계")

    def test_no_heading(self):
        self.assertEqual(extract_duty("그냥 이미지 공고"), "")


class TagTest(unittest.TestCase):
    def test_find_tags(self):
        body, _ = saramin.parse_body((FIX / "saramin_body.html").read_text(encoding="utf-8"))
        self.assertEqual(find_tags(body, []), ["AutoCAD", "SolidWorks", "ANSYS", "반도체", "컨베이어"])

    def test_find_tags_dev_and_extra(self):
        body = jobkorea.parse_body((FIX / "jobkorea_body.html").read_text(encoding="utf-8"))
        self.assertEqual(find_tags(body, ["멘토링"]), ["Java", "Spring", "MySQL", "AWS", "Docker", "멘토링"])

    def test_short_words_need_boundary(self):
        self.assertEqual(find_tags("Google NXT 프로젝트", []), [])
        self.assertEqual(find_tags("NX, Creo 사용", []), ["Creo", "NX"])

    def test_max_six(self):
        text = "AutoCAD SolidWorks CATIA Creo Inventor ANSYS 반도체 2차전지"
        self.assertEqual(len(find_tags(text, [])), 6)


class GroupTest(unittest.TestCase):
    GROUPS = {"기구설계": ["기구"], "장비설계": ["장비"], "자동화/제어": ["자동화", "PLC"]}

    def test_group_of(self):
        self.assertEqual(group_of("반도체 장비 기구설계", [], self.GROUPS), "기구설계")
        self.assertEqual(group_of("장비 설계 엔지니어", [], self.GROUPS), "장비설계")
        self.assertEqual(group_of("제어 엔지니어", ["PLC"], self.GROUPS), "자동화/제어")
        self.assertEqual(group_of("GEO 컨설턴트", [], self.GROUPS), "기타")
        self.assertEqual(group_of("아무거나", [], {}), "")

    def test_title_wins_over_sectors(self):
        # 사람인 직무 태그에는 검색어("기구설계")가 흔히 붙어 있어, 제목을 먼저 본다
        self.assertEqual(group_of("장비 설계 엔지니어", ["기구설계"], self.GROUPS), "장비설계")
        self.assertEqual(group_of("설계 엔지니어", ["기구설계"], self.GROUPS), "기구설계")

    def test_ug_means_nx(self):
        self.assertEqual(find_tags("사출금형설계(UG사용자)", []), ["NX", "금형"])


if __name__ == "__main__":
    unittest.main()
