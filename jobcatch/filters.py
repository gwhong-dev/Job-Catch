"""공고를 통과(pass) / 확인 필요(check) / 제외(exclude) 로 나눈다."""

from __future__ import annotations

import re
from typing import Literal

from .config import Common, Track
from .models import Job

Status = Literal["pass", "check", "exclude"]

EDU_ORDER = ["학력무관", "고졸", "초대졸", "대졸", "석사", "박사"]


def required_education(text: str) -> str | None:
    """공고의 학력 칸 → EDU_ORDER 값. 모르면 None."""
    t = text.replace(" ", "")
    if not t:
        return None
    if "박사" in t:
        return "박사"
    if "석사" in t:
        return "석사"
    if "초대졸" in t or "2,3년" in t or "2~3년" in t:
        return "초대졸"
    if "대졸" in t:
        return "대졸"
    if "고졸" in t:
        return "고졸"
    if "무관" in t:
        return "학력무관"
    return None


_CAREER_RE = re.compile(r"경력\s*(\d+)\s*(?:년|~)")


def min_career_months(text: str) -> int | None:
    """경력 칸 → 최소 요구 개월. 모르면 None."""
    if "신입" in text or "경력무관" in text:
        return 0
    m = _CAREER_RE.search(text)
    return int(m.group(1)) * 12 if m else None


_MORE_RE = re.compile(r"\s외\s*\d+")


def _one_location(part: str, allow: list[str]) -> Status:
    if any(part.startswith(a) for a in allow):
        return "pass"
    tokens = part.split()
    province_only = len(tokens) == 1 or (len(tokens) == 2 and tokens[1] == "전체")
    if tokens and province_only and any(a.startswith(tokens[0]) for a in allow):
        return "check"
    return "exclude"


def location_status(location: str, allow: list[str]) -> Status:
    loc = " ".join(location.split())
    if not loc or "전국" in loc or "재택" in loc:
        return "check"
    if _MORE_RE.search(loc):
        return "check"  # "서울 종로구 외 14": 나머지 근무지를 알 수 없다
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if len(parts) == 1:
        return _one_location(parts[0], allow)
    return "check" if any(_one_location(p, allow) != "exclude" for p in parts) else "exclude"


def _text_rules_pass(job: Job, common: Common, track: Track) -> bool:
    text = f"{job.title} {job.company} {' '.join(job.sectors)}"
    if any(w and w in text for w in common.exclude_words):
        return False
    if any(c and c in job.company for c in common.exclude_companies):
        return False
    if any(e and e in job.employment for e in common.exclude_employment):
        return False
    include = [w for w in track.include_any if w]
    if include and not any(w.lower() in text.lower() for w in include):
        return False
    return True


def education_ok(job: Job, common: Common) -> bool | None:
    need = required_education(job.education)
    if need is None:
        return None
    mine = common.education if common.education in EDU_ORDER else "박사"
    return EDU_ORDER.index(need) <= EDU_ORDER.index(mine)


def career_ok(job: Job, common: Common, track: Track) -> bool | None:
    need = min_career_months(job.career)
    if need is None:
        return None
    if "경력" in track.career:
        return need <= common.my_career_months
    return need == 0


def classify(
    job: Job, common: Common, track: Track, location: Status | None = None
) -> tuple[Status, list[str]]:
    """location 을 주면 지역 목록 대신 그 판정(통근 시간 등)을 쓴다."""
    if not _text_rules_pass(job, common, track):
        return "exclude", []
    flags: list[str] = []
    for ok, flag in (
        (education_ok(job, common), "학력 확인"),
        (career_ok(job, common, track), "경력 확인"),
    ):
        if ok is False:
            return "exclude", []
        if ok is None:
            flags.append(flag)
    loc = location or location_status(job.location, common.allow_locations)
    if loc == "exclude":
        return "exclude", []
    if loc == "check":
        flags.append("지역 확인")
    return ("check" if flags else "pass"), flags
