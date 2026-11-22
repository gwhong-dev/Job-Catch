"""이미 보낸 공고 기록 (data/seen.json).

마감 임박 공고를 다시 알리려고 공고 정보(제목 · 회사 · 링크 · 마감일)도 함께 둔다.
개인 정보나 통근 시간은 넣지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

from .models import Job


@dataclass
class Entry:
    title: str
    company: str
    url: str
    source: str
    track: str
    deadline: date | None
    first_sent: date
    excluded: bool = False  # 상세 조회 뒤 제외된 공고: 다시 조회하지 않으려고 잠시 기억


EXCLUDED_KEEP_DAYS = 30


def _to_json(e: Entry) -> dict:
    d = asdict(e)
    d["deadline"] = e.deadline.isoformat() if e.deadline else None
    d["first_sent"] = e.first_sent.isoformat()
    return d


def _from_json(d: dict) -> Entry:
    return Entry(
        title=d["title"], company=d["company"], url=d["url"], source=d["source"],
        track=d.get("track", ""),
        deadline=date.fromisoformat(d["deadline"]) if d.get("deadline") else None,
        first_sent=date.fromisoformat(d["first_sent"]),
        excluded=bool(d.get("excluded", False)),
    )


def load(path: Path) -> dict[str, Entry]:
    """파일이 없거나 깨졌으면 빈 기록 (그날 공고를 한 번 다시 받을 뿐)."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Entry] = {}
    for key, value in raw.items() if isinstance(raw, dict) else []:
        if isinstance(value, dict):  # 예전 형식 {key: "날짜"} 은 건너뜀
            try:
                out[key] = _from_json(value)
            except (KeyError, ValueError, TypeError):
                continue
    return out


def save(path: Path, entries: dict[str, Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: _to_json(e) for k, e in entries.items()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def record(entries: dict[str, Entry], jobs: list[Job], today: date) -> None:
    for j in jobs:
        old = entries.get(j.key)
        if old:
            if j.deadline:
                old.deadline = j.deadline
            continue
        entries[j.key] = Entry(
            title=j.title, company=j.company, url=j.url, source=j.source,
            track=j.track, deadline=j.deadline, first_sent=today,
        )


def record_excluded(entries: dict[str, Entry], jobs: list[Job], today: date) -> None:
    for j in jobs:
        if j.key not in entries:
            entries[j.key] = Entry(
                title=j.title, company=j.company, url=j.url, source=j.source,
                track=j.track, deadline=j.deadline, first_sent=today, excluded=True,
            )


def prune(entries: dict[str, Entry], today: date) -> None:
    for key in list(entries):
        e = entries[key]
        if e.excluded:
            expired = e.first_sent + timedelta(days=EXCLUDED_KEEP_DAYS) < today
        elif e.deadline:
            expired = e.deadline + timedelta(days=30) < today
        else:
            expired = e.first_sent + timedelta(days=60) < today
        if expired:
            del entries[key]
