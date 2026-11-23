import unittest
from datetime import date
from pathlib import Path

from jobcatch import jobkorea, saramin
from jobcatch.summary import Analysis, analyze, extract_duty, extract_required, find_tags, group_of

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


class AnalyzeTest(unittest.TestCase):
    def test_conjunction_only_is_empty(self):
        self.assertEqual(extract_duty("주요업무 및 자격요건\n- 경력 3년 이상"), "")

    def test_company_intro_not_in_duty(self):
        body = "담당업무\n[채용 기업]\n채용기업은 글로벌 상장사(예시)입니다\n자격요건\n- 경력 3년"
        self.assertEqual(extract_duty(body), "")

    def test_template_residue_removed(self):
        body = "주요업무\n상세내용을 입력하세요\n- 서버 운영(예시)\n상세내용을 입력하세요\n자격요건\n- 신입"
        self.assertEqual(extract_duty(body), "서버 운영(예시)")

    def test_heading_only_items_removed(self):
        body = "주요업무\n담당업무\n- AWS 인프라 구축(예시)\n지원자격\n- 무관"
        self.assertEqual(extract_duty(body), "AWS 인프라 구축(예시)")

    def test_mid_sentence_heading_ignored(self):
        body = "회사는 고객이 하는 일까지 함께할 엔지니어를 찾습니다(예시)\n복리후생\n- 식대"
        self.assertEqual(extract_duty(body), "")

    def test_required_without_preferred(self):
        body = "주요업무\n- 지그 설계(예시)\n자격요건\n- Creo 3년 이상\n- 우대: 영어 가능\n우대사항\n- 반도체 경험"
        self.assertEqual(extract_required(body), "Creo 3년 이상")

    def test_required_before_duty(self):
        body = "[지원자격]\n- 초대졸 이상\n[담당업무]\n- 컨베이어 설계(예시)\n[근무조건]\n- 주5일"
        a = analyze(body, [])
        self.assertEqual(a.required, "초대졸 이상")
        self.assertEqual(a.duty, "컨베이어 설계(예시)")

    def test_preferred_only_gives_empty_required(self):
        self.assertEqual(extract_required("주요업무\n- 판금 설계(예시)\n우대사항\n- SolidWorks"), "")

    def test_cut_at_item_boundary(self):
        body = "주요업무\n" + "\n".join(f"- 업무{i} " + "가" * 20 for i in range(6)) + "\n자격요건\n- x"
        duty = extract_duty(body)
        self.assertLessEqual(len(duty), 80)
        self.assertTrue(duty.endswith("…"))
        self.assertNotIn("업무5", duty)
        self.assertTrue(duty.split(" / ")[0].startswith("업무0"))

    def test_tags_only_from_sections(self):
        body = "회사 소개\nJava Spring React 를 쓰는 여러 팀(예시)\n주요업무\n- 기구 설계\n자격요건\n- Creo 사용"
        self.assertEqual(analyze(body, []).tags, ["Creo"])

    def test_tags_whole_body_without_sections(self):
        self.assertEqual(analyze("이미지 위주 공고 Creo(예시)", []).tags, ["Creo"])

    def test_empty_body(self):
        self.assertEqual(analyze("", []), Analysis())


if __name__ == "__main__":
    unittest.main()
