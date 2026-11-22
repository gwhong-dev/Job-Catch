import unittest
from datetime import date, timedelta

from jobcatch.commute import KakaoUnavailable
from jobcatch.config import Common, Config, Track
from jobcatch.digest import build, collect
from jobcatch.history import Entry
from jobcatch.models import Detail, Job

TODAY = date(2026, 11, 22)
NO_SLEEP = lambda s: None  # noqa: E731


def job(job_id: str, source: str = "saramin", **kw) -> Job:
    base = dict(
        source=source, job_id=job_id, title=f"설계 공고{job_id}(예시)", company="가나(예시)",
        url=f"u{job_id}", deadline_text="", deadline=None, location="경기 성남시 분당구",
        career="신입", education="학력무관", employment="정규직", salary="",
    )
    base.update(kw)
    return Job(**base)


def config(**common) -> Config:
    c = dict(education="초대졸", allow_locations=["경기 성남시", "서울 금천구"])
    c.update(common)
    return Config(
        common=Common(**c),
        tracks=[
            Track(name="설계", sites=["saramin"], keywords=["기구설계"], career=["신입", "경력"]),
            Track(name="개발", sites=["jobkorea"], keywords=["백엔드"], career=["신입"]),
        ],
        max_cards_per_track=30,
    )


def collected(*jobs: Job, failed=None):
    from jobcatch.digest import Collected

    for j in jobs:
        j.track = j.track or "설계"
    return Collected(jobs=list(jobs), failed_sites=failed or [], counts={})


class FakeKakao:
    def __init__(self, minutes: dict[str, int | None] | None = None, fail_geocode=False):
        self.minutes = minutes or {}
        self.fail_geocode = fail_geocode

    def geocode(self, addr):
        if self.fail_geocode:
            raise KakaoUnavailable("쿼터")
        return (127.0, 37.0) if addr else None

    def transit_minutes(self, src, dst):
        return self.minutes.get(dst)


class CountingDetails:
    def __init__(self, coords: dict[str, tuple[float, float]] | None = None):
        self.calls: list[str] = []
        self.coords = coords or {}

    def __call__(self, job_id, today):
        self.calls.append(job_id)
        return Detail(address=f"주소{job_id}", coords=self.coords.get(job_id, (1.0, float(job_id))))


class CollectTest(unittest.TestCase):
    def test_marks_failed_site(self):
        def boom(*a):
            raise RuntimeError("잡코리아 응답 403")

        c = collect(config(), TODAY, {"saramin": lambda *a: [job("1")], "jobkorea": boom}, NO_SLEEP)
        self.assertEqual(c.failed_sites, ["jobkorea"])
        self.assertEqual([j.key for j in c.jobs], ["saramin:1"])
        self.assertEqual(c.jobs[0].track, "설계")

    def test_zero_is_failure(self):
        c = collect(config(), TODAY, {"saramin": lambda *a: [job("1")], "jobkorea": lambda *a: []}, NO_SLEEP)
        self.assertIn("jobkorea", c.failed_sites)
        self.assertNotIn("saramin", c.failed_sites)

    def test_dedupes_across_tracks(self):
        cfg = config()
        cfg.tracks[1].sites = ["saramin"]
        c = collect(cfg, TODAY, {"saramin": lambda *a: [job("1")]}, NO_SLEEP)
        self.assertEqual(len(c.jobs), 1)
        self.assertEqual(c.jobs[0].track, "설계")

    def test_sleeps_between_calls(self):
        slept = []
        cfg = config()
        cfg.tracks[0].keywords = ["a", "b"]
        collect(cfg, TODAY, {"saramin": lambda *a: [], "jobkorea": lambda *a: []}, slept.append)
        self.assertEqual(slept, [2.0, 2.0])  # 호출 3번 → 사이 2번


class BuildTest(unittest.TestCase):
    def test_new_vs_seen(self):
        entries = {"saramin:1": Entry("t", "c", "u", "saramin", "설계", None, TODAY)}
        d, new = build(collected(job("1"), job("2")), config(), entries, TODAY)
        self.assertEqual([j.key for j in new], ["saramin:2"])
        self.assertEqual([j.job_id for j in d.new_by_track["설계"]], ["2"])
        self.assertEqual(list(d.new_by_track), ["설계", "개발"])

    def test_closing_includes_old_entry(self):
        entries = {
            "saramin:9": Entry("옛 공고", "c", "u", "saramin", "설계", TODAY + timedelta(days=3), TODAY),
            "saramin:8": Entry("먼 공고", "c", "u", "saramin", "설계", TODAY + timedelta(days=8), TODAY),
        }
        d, _ = build(collected(), config(), entries, TODAY)
        self.assertEqual([c.title for c in d.closing], ["옛 공고"])

    def test_closing_not_duplicated(self):
        d, new = build(collected(job("1", deadline=TODAY + timedelta(days=2))), config(), {}, TODAY)
        self.assertEqual([c.url for c in d.closing], ["u1"])
        self.assertEqual(d.new_by_track["설계"], [])
        self.assertEqual(d.new_total, 1)
        self.assertEqual(len(new), 1)

    def test_cap(self):
        cfg = config()
        cfg.max_cards_per_track = 2
        d, new = build(collected(*[job(str(i)) for i in range(5)]), cfg, {}, TODAY)
        self.assertEqual(len(d.new_by_track["설계"]), 2)
        self.assertEqual(d.overflow_by_track["설계"], 3)
        self.assertEqual(len(new), 5)

    def test_excluded_and_flagged(self):
        d, new = build(collected(job("1", location="부산 중구"), job("2", location="서울")), config(), {}, TODAY)
        self.assertEqual([j.job_id for j in new], ["2"])
        self.assertEqual(new[0].flags, ["지역 확인"])

    def test_failed_sites_passed_through(self):
        d, _ = build(collected(failed=["jobkorea"]), config(), {}, TODAY)
        self.assertEqual(d.failed_sites, ["jobkorea"])


class CommuteTest(unittest.TestCase):
    def cfg(self, **kw):
        return config(home_address="서울 중구 세종대로 110", **kw)

    def test_commute_overrides_region(self):
        near = job("1", location="경기 안산시 단원구")   # 지역 목록 밖
        far = job("2", location="경기 성남시 수정구")     # 지역 목록 안
        kakao = FakeKakao({(1.0, 1.0): 50, (1.0, 2.0): 90})
        d, new = build(collected(near, far), self.cfg(), {}, TODAY,
                       details={"saramin": CountingDetails()}, kakao=kakao, sleep=NO_SLEEP)
        self.assertEqual([j.job_id for j in new], ["1"])
        self.assertEqual(new[0].commute_min, 50)
        self.assertFalse(d.commute_failed)

    def test_commute_soft_limit_flags(self):
        kakao = FakeKakao({(1.0, 1.0): 70})
        _, new = build(collected(job("1")), self.cfg(), {}, TODAY,
                       details={"saramin": CountingDetails()}, kakao=kakao, sleep=NO_SLEEP)
        self.assertEqual(new[0].flags, ["통근 확인"])

    def test_province_prefilter(self):
        details = CountingDetails()
        _, new = build(collected(job("1", location="부산 중구")), self.cfg(), {}, TODAY,
                       details={"saramin": details}, kakao=FakeKakao(), sleep=NO_SLEEP)
        self.assertEqual(new, [])
        self.assertEqual(details.calls, [])

    def test_lookup_cap(self):
        details = CountingDetails()
        kakao = FakeKakao({(1.0, 1.0): 30})
        _, new = build(collected(job("1"), job("2"), job("3")), self.cfg(max_detail_lookups=1), {}, TODAY,
                       details={"saramin": details}, kakao=kakao, sleep=NO_SLEEP)
        self.assertEqual(details.calls, ["1"])
        self.assertEqual([j.commute_min for j in new], [30, None, None])  # 나머지는 지역 목록 판정

    def test_no_route_falls_back_to_region(self):
        _, new = build(collected(job("1", location="경기 안산시")), self.cfg(), {}, TODAY,
                       details={"saramin": CountingDetails()}, kakao=FakeKakao({}), sleep=NO_SLEEP)
        self.assertEqual(new, [])  # 경로 없음 → 지역 목록 → 안산은 목록 밖

    def test_kakao_unavailable_falls_back(self):
        d, new = build(collected(job("1")), self.cfg(), {}, TODAY,
                       details={"saramin": CountingDetails()}, kakao=FakeKakao(fail_geocode=True),
                       sleep=NO_SLEEP)
        self.assertTrue(d.commute_failed)
        self.assertEqual([j.job_id for j in new], ["1"])

    def test_detail_fills_jobkorea_fields(self):
        def details(job_id, today):
            return Detail(address="a", deadline=TODAY + timedelta(days=20), education="대졸이상",
                          coords=(1.0, 1.0))

        j = job("1", source="jobkorea", education="", track="개발")
        _, new = build(collected(j), self.cfg(), {}, TODAY, details={"jobkorea": details},
                       kakao=FakeKakao({(1.0, 1.0): 40}), sleep=NO_SLEEP)
        self.assertEqual(new, [])  # 상세에서 '대졸이상' → 초대졸은 제외

    def test_detail_without_kakao_fills_education(self):
        calls = []

        def details(job_id, today):
            calls.append(job_id)
            return Detail(address="a", education="대졸이상" if job_id == "1" else "초대졸이상")

        a = job("1", source="jobkorea", education="", track="개발")
        b = job("2", source="jobkorea", education="", track="개발")
        far = job("3", source="jobkorea", education="", track="개발", location="부산 중구")
        _, new = build(collected(a, b, far), config(), {}, TODAY, details={"jobkorea": details},
                       kakao=None, sleep=NO_SLEEP)
        self.assertEqual([j.job_id for j in new], ["2"])
        self.assertEqual(new[0].flags, [])
        self.assertEqual(calls, ["1", "2"])  # 지역 목록으로 빠지는 공고는 조회 안 함

    def test_excluded_after_lookup_reported(self):
        kakao = FakeKakao({(1.0, 1.0): 30, (1.0, 2.0): 90})
        d, new = build(collected(job("1"), job("2")), self.cfg(), {}, TODAY,
                       details={"saramin": CountingDetails()}, kakao=kakao, sleep=NO_SLEEP)
        self.assertEqual([j.job_id for j in new], ["1"])
        self.assertEqual([j.job_id for j in d.excluded_after_lookup], ["2"])

    def test_excluded_entry_skipped_and_not_closing(self):
        entries = {"saramin:2": Entry("제외", "c", "u", "saramin", "설계", TODAY + timedelta(days=2), TODAY,
                                      excluded=True)}
        details = CountingDetails()
        d, new = build(collected(job("2")), self.cfg(), entries, TODAY, details={"saramin": details},
                       kakao=FakeKakao({}), sleep=NO_SLEEP)
        self.assertEqual(details.calls, [])
        self.assertEqual(new, [])
        self.assertEqual(d.closing, [])

    def test_routes_never_found_is_failure(self):
        d, _ = build(collected(job("1"), job("2"), job("3")), self.cfg(), {}, TODAY,
                     details={"saramin": CountingDetails()}, kakao=FakeKakao({}), sleep=NO_SLEEP)
        self.assertTrue(d.commute_failed)

    def test_lookup_cap_counted(self):
        d, _ = build(collected(job("1"), job("2"), job("3")), self.cfg(max_detail_lookups=1), {}, TODAY,
                     details={"saramin": CountingDetails()}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP)
        self.assertEqual(d.unchecked_by_cap, 2)

    def test_no_kakao_still_reads_detail_for_summary(self):
        details = CountingDetails()
        _, new = build(collected(job("1")), self.cfg(), {}, TODAY, details={"saramin": details},
                       kakao=None, sleep=NO_SLEEP)
        self.assertEqual(details.calls, ["1"])
        self.assertEqual(len(new), 1)
        self.assertIsNone(new[0].commute_min)


class SummaryGroupTest(unittest.TestCase):
    def test_detail_fills_address_summary_tags(self):
        def details(job_id, today):
            return Detail(address="서울 중구 세종대로 110",
                          body="📋 주요업무\n▣ 컨베이어 설계\n📋 자격요건\n• Creo 사용")

        cfg = config(extra_tags=["설계검증"])
        _, new = build(collected(job("1")), cfg, {}, TODAY, details={"saramin": details}, sleep=NO_SLEEP)
        self.assertEqual(new[0].address, "서울 중구 세종대로 110")
        self.assertEqual(new[0].summary, "컨베이어 설계")
        self.assertEqual(new[0].tags, ["Creo", "컨베이어"])

    def test_groups_order_and_other(self):
        cfg = config()
        cfg.tracks[0].groups = {"기구설계": ["기구"], "장비설계": ["장비"]}
        jobs = [job("1", title="GEO 컨설턴트(예시)"), job("2", title="장비 설계(예시)"),
                job("3", title="반도체 장비 기구설계(예시)")]
        d, _ = build(collected(*jobs), cfg, {}, TODAY)
        got = [(j.job_id, j.group) for j in d.new_by_track["설계"]]
        self.assertEqual(got, [("3", "기구설계"), ("2", "장비설계"), ("1", "기타")])

    def test_no_groups_means_empty_group(self):
        d, _ = build(collected(job("1")), config(), {}, TODAY)
        self.assertEqual(d.new_by_track["설계"][0].group, "")


if __name__ == "__main__":
    unittest.main()
