"""사이트와 상관없이 쓰는 공고 모양."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Job:
    source: str
    job_id: str
    title: str
    company: str
    url: str
    deadline_text: str
    deadline: date | None
    location: str
    career: str
    education: str
    employment: str
    salary: str
    sectors: list[str] = field(default_factory=list)
    posted_text: str = ""
    track: str = ""
    flags: list[str] = field(default_factory=list)
    commute_min: int | None = None
    # 상세 페이지에서 채우는 값 (모르면 빈 값)
    address: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    group: str = ""  # 갈래 안 세부 묶음

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"


@dataclass
class Detail:
    """공고 상세 페이지에서 읽은 값. 모르면 빈 값."""

    address: str = ""
    deadline: date | None = None
    education: str = ""
    coords: tuple[float, float] | None = None  # (경도 x, 위도 y). 페이지에 있으면 주소 변환을 건너뛴다
    body: str = ""  # 상세요강 본문 글자 (요약용)
