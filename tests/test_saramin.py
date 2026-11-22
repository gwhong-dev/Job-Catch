import unittest
from datetime import date

from jobcatch.saramin import parse_deadline, parse_search_page, search_params

# 실제 페이지 구조를 줄여 만든 가짜 HTML (회사·공고는 예시)
HTML = """
<div class="item_recruit" value="111">
  <div class="area_job">
    <h2 class="job_tit"><a href="/x" title="백엔드 개발자 신입 채용"><span>백엔드</span></a></h2>
    <div class="job_date"><span class="date">~ 12/06(토)</span></div>
    <div class="job_condition">
      <span><a>서울</a> <a>강남구</a></span><span>신입</span><span>대졸↑</span><span>정규직</span>
    </div>
    <div class="job_sector"><a>백엔드/서버개발</a>, <a>Python</a> <span class="job_day">등록일 26/11/22</span></div>
  </div>
  <div class="area_corp"><strong class="corp_name"><a>가나소프트(예시)</a></strong></div>
</div>
<div class="item_recruit" value="222">
  <div class="area_job">
    <h2 class="job_tit"><a title="IT 영업 담당"><span>영업</span></a></h2>
    <div class="job_date"><span class="date">상시채용</span></div>
    <div class="job_condition"><span><a>경기</a></span><span>경력무관</span><span>학력무관</span><span>파견직</span></div>
  </div>
  <div class="area_corp"><strong class="corp_name"><a>다라상사(예시)</a></strong></div>
</div>
"""

TODAY = date(2026, 11, 22)


class ParseTest(unittest.TestCase):
    def test_parse_fields(self):
        jobs = parse_search_page(HTML, TODAY)
        self.assertEqual([j.job_id for j in jobs], ["111", "222"])
        j = jobs[0]
        self.assertEqual(j.title, "백엔드 개발자 신입 채용")
        self.assertEqual(j.company, "가나소프트(예시)")
        self.assertEqual(j.location, "서울 강남구")
        self.assertEqual(j.career, "신입")
        self.assertEqual(j.employment, "정규직")
        self.assertEqual(j.deadline, date(2026, 12, 6))
        self.assertIn("rec_idx=111", j.url)
        self.assertIsNone(jobs[1].deadline)

    def test_deadline_rolls_to_next_year(self):
        self.assertEqual(parse_deadline("~ 01/20(수)", TODAY), date(2027, 1, 20))
        self.assertIsNone(parse_deadline("채용시", TODAY))


class ParamsTest(unittest.TestCase):
    def test_search_params(self):
        p = search_params("기구설계", ["신입", "경력"], 2)
        self.assertEqual(p["searchword"], "기구설계")
        self.assertEqual(p["exp_cd"], "1,2")
        self.assertEqual(p["recruitPage"], 2)
        self.assertEqual(p["recruitSort"], "reg_dt")
        self.assertNotIn("loc_mcd", p)
        self.assertEqual(search_params("x", ["신입"], 1)["exp_cd"], "1")
        self.assertEqual(search_params("x", ["경력"], 1)["exp_cd"], "2")


if __name__ == "__main__":
    unittest.main()
