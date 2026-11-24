"""수집 → 분류(지역 · 통근 포함) → 새 공고 / 마감 임박으로 묶기."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from .ai import AiStats, enrich_jobs
from .commute import Kakao, KakaoUnavailable, commute_status
from .config import Config, Track
from .filters import classify
from .history import Entry
from .models import Detail, Job
from .summary import analyze, group_of

Fetcher = Callable[[str, list[str], int, float, date], list[Job]]
DetailFetcher = Callable[[str, date], Detail]

CLOSING_DAYS = 7
DETAIL_TIME_LIMIT_SEC = 15 * 60  # 상세 조회 단계가 이보다 길면 남은 공고는 내일로 (워크플로 제한 30분)


def _closing_soon(job: Job, today: date) -> bool:
    return job.deadline is not None and today <= job.deadline <= today + timedelta(days=CLOSING_DAYS)


def _lookup_order(jobs: list[Job], today: date) -> list[Job]:
    """상세 조회 순서: 마감 임박(목록 마감일 기준) 먼저, 나머지는 갈래를 번갈아 한 건씩."""
    first = [j for j in jobs if _closing_soon(j, today)]
    by_track: dict[str, list[Job]] = {}
    for j in jobs:
        if not _closing_soon(j, today):
            by_track.setdefault(j.track, []).append(j)
    queues = list(by_track.values())
    rest = [q[i] for i in range(max(map(len, queues), default=0)) for q in queues if i < len(q)]
    return first + rest


@dataclass
class Collected:
    jobs: list[Job]
    failed_sites: list[str]
    counts: dict[str, int] = field(default_factory=dict)


def collect(
    cfg: Config, today: date, fetchers: dict[str, Fetcher], sleep: Callable[[float], None] = time.sleep
) -> Collected:
    """갈래 × 사이트 × 키워드로 검색. 사이트 오류 · 0건은 failed_sites 에 (조용한 실패 방지)."""
    jobs: list[Job] = []
    keys: set[str] = set()
    failed: list[str] = []
    counts: dict[str, int] = {}
    first = True
    for track in cfg.tracks:
        for site in track.sites:
            counts.setdefault(site, 0)
            for keyword in track.keywords:
                if not first:
                    sleep(cfg.delay_sec)
                first = False
                try:
                    found = fetchers[site](keyword, track.career, cfg.max_pages, cfg.delay_sec, today)
                except Exception:
                    if site not in failed:
                        failed.append(site)
                    continue
                counts[site] += len(found)
                for j in found:
                    if j.key in keys:
                        continue
                    keys.add(j.key)
                    j.track = track.name
                    jobs.append(j)
    for site, n in counts.items():
        if n == 0 and site not in failed:
            failed.append(site)
    return Collected(jobs=jobs, failed_sites=failed, counts=counts)


@dataclass
class ClosingItem:
    title: str
    company: str
    url: str
    source: str
    track: str
    deadline: date
    flags: list[str] = field(default_factory=list)
    commute_min: int | None = None
    location: str = ""
    address: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    required: str = ""
    fit: str = ""
    fit_reason: str = ""


@dataclass
class Digest:
    today: date
    new_by_track: dict[str, list[Job]]
    overflow_by_track: dict[str, int]
    closing: list[ClosingItem]
    failed_sites: list[str]
    new_total: int
    commute_failed: bool = False
    commute_no_home: bool = False  # 카카오 키는 있는데 집 주소가 비어 통근 계산이 꺼짐
    excluded_after_lookup: list[Job] = field(default_factory=list)  # 다음 날 다시 조회하지 않게 기록
    deferred: int = 0  # 상세 조회 상한 · 시간에 걸려 내일 다시 볼 공고 수 (보낸 기록에 남기지 않음)
    detail_read: int = 0
    detail_failed: int = 0
    detail_failed_sites: list[str] = field(default_factory=list)  # 시도 3건 이상 중 절반 이상 실패한 사이트
    # 분석 적중률: 상세 본문이 있던 공고 중 요약 · 필수조건이 나온 건수 (제외된 공고 포함)
    with_body: int = 0
    with_summary: int = 0
    with_required: int = 0
    ai: AiStats | None = None  # AI 단계 건수 (키가 없으면 None)


def _province(location: str) -> str:
    parts = location.split()
    return parts[0] if parts else ""


class _Commute:
    """통근 모드 상태: 집 좌표, 조회 횟수, 실패 여부."""

    def __init__(self, cfg: Config, today: date, kakao: Kakao | None,
                 details: dict[str, DetailFetcher] | None, sleep: Callable[[float], None],
                 clock: Callable[[], float] = time.monotonic):
        self.cfg = cfg
        self.today = today
        self.kakao = kakao
        self.details = details or {}
        self.sleep = sleep
        self.clock = clock
        self.started: float | None = None  # 첫 상세 조회 시각
        self.failed = False
        self.lookups = 0
        self.deferred = 0
        self.read = 0  # 상세를 받아 온 건수
        self.with_body = 0  # 그중 본문 글자가 있는 건수 (적중률의 분모)
        self.with_summary = 0
        self.with_required = 0
        self.tries: dict[str, int] = {}  # 사이트별 상세 조회 시도
        self.fails: dict[str, int] = {}  # 사이트별 실패 (예외 · 빈 응답)
        self.looked_up = False  # 마지막 judge 가 상세 페이지를 읽었는지
        self.route_tries = 0
        self.route_found = 0
        self.home = None
        home_address = cfg.common.home_address.strip()
        self.no_home = kakao is not None and not home_address
        if kakao and home_address:
            try:
                self.home = kakao.geocode(home_address)
            except KakaoUnavailable:
                self.home = None
            if self.home is None:
                self.failed = True
        self.provinces = {_province(a) for a in cfg.common.allow_locations if _province(a)}

    @property
    def on(self) -> bool:
        return self.home is not None

    def outside_provinces(self, job: Job) -> bool:
        prov = _province(job.location)
        if not self.provinces or not prov or "전국" in job.location or "재택" in job.location:
            return False
        return prov not in self.provinces

    def minutes_to(self, address: str) -> int | None:
        """다시 알림 카드용 통근 시간 (기록에 저장하지 않으므로 그때 다시 계산)."""
        if not self.on or not address:
            return None
        try:
            dst = self.kakao.geocode(address)
            return self.kakao.transit_minutes(self.home, dst) if dst else None
        except KakaoUnavailable:
            self.home = None
            self.failed = True
            return None

    def _out_of_budget(self) -> bool:
        if self.lookups >= self.cfg.common.max_detail_lookups:
            return True
        if self.started is None:
            self.started = self.clock()
            return False
        return self.clock() - self.started >= DETAIL_TIME_LIMIT_SEC

    def judge(self, job: Job, track: Track) -> tuple[str, list[str]]:
        """상세 페이지 → 근무지 → 대중교통 시간으로 판정. 못 구하면 지역 목록 판정.

        상한 · 시간에 걸리면 마감 임박 공고만 지역 목록으로 판정하고, 나머지는 "defer" (내일 다시).
        """
        common = self.cfg.common
        fetch = self.details.get(job.source)
        self.looked_up = False
        if not fetch:
            return classify(job, common, track)
        if self._out_of_budget():
            if _closing_soon(job, self.today):
                return classify(job, common, track)
            self.deferred += 1
            return "defer", []
        self.looked_up = True
        if self.lookups:
            self.sleep(self.cfg.delay_sec)
        self.lookups += 1
        self.tries[job.source] = self.tries.get(job.source, 0) + 1
        try:
            detail = fetch(job.job_id, self.today)
        except Exception:
            self.fails[job.source] = self.fails.get(job.source, 0) + 1
            return classify(job, common, track)
        if detail.address or detail.body or detail.coords or detail.images:
            self.read += 1
        else:  # 빈 응답: 사이트 구조가 바뀌었을 수 있다
            self.fails[job.source] = self.fails.get(job.source, 0) + 1
        if detail.deadline and not job.deadline:
            job.deadline = detail.deadline
        if detail.education and not job.education:
            job.education = detail.education
        job.address = detail.address
        job.body, job.images = detail.body, list(detail.images)
        if detail.body:
            a = analyze(detail.body, common.extra_tags)
            job.summary, job.required, job.tags = a.duty, a.required, a.tags
            self.with_body += 1
            self.with_summary += bool(a.duty)
            self.with_required += bool(a.required)
        minutes = None
        if self.on:
            try:
                dst = detail.coords or (self.kakao.geocode(detail.address) if detail.address else None)
                if dst:
                    self.route_tries += 1
                    minutes = self.kakao.transit_minutes(self.home, dst)
                    self.route_found += minutes is not None
            except KakaoUnavailable:
                self.home = None
                self.failed = True
        status = commute_status(minutes, common.commute_limit_min, common.commute_soft_min)
        if status is None:
            return classify(job, common, track)
        job.commute_min = minutes
        result, flags = classify(job, common, track, location=status)
        return result, ["통근 확인" if f == "지역 확인" else f for f in flags]


def build(
    collected: Collected,
    cfg: Config,
    entries: dict[str, Entry],
    today: date,
    details: dict[str, DetailFetcher] | None = None,
    kakao: Kakao | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    ai=None,
) -> tuple[Digest, list[Job]]:
    """두 번째 값은 기록에 남길 새 공고 전부 (카드 상한으로 잘린 것 포함, 내일로 미룬 것 제외)."""
    tracks = {t.name: t for t in cfg.tracks}
    commute = _Commute(cfg, today, kakao, details, sleep, clock)

    kept: list[Job] = []
    excluded_after_lookup: list[Job] = []
    # 상세 조회 전에 빠질 공고를 먼저 거른다. 그래야 갈래 번갈아 순서가 실제 후보 기준이 된다
    candidates: list[Job] = []
    for job in collected.jobs:
        if job.key in entries or job.track not in tracks:
            continue
        track = tracks[job.track]
        if commute.on:
            if commute.outside_provinces(job):
                continue
            if classify(job, cfg.common, track, location="pass")[0] == "exclude":
                continue  # 지역과 상관없이 빠지는 공고는 상세 조회하지 않는다
        elif classify(job, cfg.common, track)[0] == "exclude":
            continue
        candidates.append(job)

    for job in _lookup_order(candidates, today):
        commute.looked_up = False
        track = tracks[job.track]
        # 통근 계산이 꺼져 있어도 상세 페이지를 읽는다: 근무지 주소 · 요약, 잡코리아 학력 보충
        status, flags = commute.judge(job, track)
        if status == "defer":
            continue
        if status == "exclude":
            if commute.looked_up:
                excluded_after_lookup.append(job)
            continue
        job.flags = flags
        job.group = group_of(job.title, job.sectors, track.groups)
        kept.append(job)

    soon = today + timedelta(days=CLOSING_DAYS)
    closing_jobs = sorted((j for j in kept if j.deadline and today <= j.deadline <= soon),
                          key=lambda j: (j.deadline, j.title))
    closing_keys = {j.key for j in closing_jobs}

    new_by_track: dict[str, list[Job]] = {t.name: [] for t in cfg.tracks}
    for j in kept:
        if j.key not in closing_keys:
            new_by_track[j.track].append(j)
    overflow: dict[str, int] = {}
    for name, jobs in new_by_track.items():
        # 묶음 순서(설정 순서, "기타" 는 맨 뒤) → 통근 짧은 순(모름은 뒤) → 마감일 → 제목.
        # 상한에 걸리면 뒤쪽 묶음부터, 묶음 안에서는 먼 공고부터 잘린다
        order = {g: i for i, g in enumerate(tracks[name].groups)}
        jobs.sort(key=lambda j: (order.get(j.group, len(order)),
                                 j.commute_min if j.commute_min is not None else float("inf"),
                                 j.deadline or date.max, j.title))
        extra = len(jobs) - cfg.max_cards_per_track
        if extra > 0:
            overflow[name] = extra
            del jobs[cfg.max_cards_per_track:]

    # AI 는 메일에 실리는 카드만: 마감 임박 먼저, 그다음 갈래 순서 · 카드 순서 (한도에 걸리면 뒤쪽이 규칙 요약)
    ai_stats = None
    if ai is not None:
        cards = closing_jobs + [j for t in cfg.tracks for j in new_by_track[t.name]]
        ai_stats = enrich_jobs(cards, {t.name: t.fit for t in cfg.tracks}, ai)

    closing: list[ClosingItem] = []
    for j in closing_jobs:
        closing.append(ClosingItem(j.title, j.company, j.url, j.source, j.track, j.deadline,
                                   list(j.flags), j.commute_min, j.location,
                                   j.address, j.summary, list(j.tags), j.required, j.fit, j.fit_reason))
    for key, e in entries.items():
        if not e.excluded and e.deadline and today <= e.deadline <= soon:
            # 다시 알림 카드는 AI 를 부르지 않고 보낸 기록의 값을 쓴다
            closing.append(ClosingItem(e.title, e.company, e.url, e.source, e.track, e.deadline,
                                       list(e.flags), commute.minutes_to(e.address), e.location,
                                       e.address, e.summary, list(e.tags), e.required, e.fit, e.fit_reason))
    closing.sort(key=lambda c: (c.deadline, c.title))

    digest = Digest(
        today=today,
        new_by_track=new_by_track,
        overflow_by_track=overflow,
        closing=closing,
        failed_sites=list(collected.failed_sites),
        new_total=len(kept),
        commute_failed=commute.failed or (commute.route_tries >= 3 and commute.route_found == 0),
        commute_no_home=commute.no_home,
        excluded_after_lookup=excluded_after_lookup,
        deferred=commute.deferred,
        detail_read=commute.read,
        with_body=commute.with_body,
        with_summary=commute.with_summary,
        with_required=commute.with_required,
        detail_failed=sum(commute.fails.values()),
        detail_failed_sites=[s for s, n in commute.tries.items()
                             if n >= 3 and commute.fails.get(s, 0) * 2 >= n],
        ai=ai_stats,
    )
    return digest, kept
