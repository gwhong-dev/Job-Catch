"""수집 → 조건 필터 → 중복 제거 → 리포트."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .saramin import Job


def matches(job: Job, f: dict) -> bool:
    text = f"{job.title} {job.company} {' '.join(job.sectors)}"
    for word in f.get("exclude_words", []):
        if word and word in text:
            return False
    for comp in f.get("exclude_companies", []):
        if comp and comp in job.company:
            return False
    for emp in f.get("exclude_employment", []):
        if emp and emp in job.employment:
            return False
    include = [w for w in f.get("include_any", []) if w]
    if include and not any(w.lower() in text.lower() for w in include):
        return False
    return True


def dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    out = []
    for j in jobs:
        if j.key not in seen:
            seen.add(j.key)
            out.append(j)
    return out


def load_seen(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_seen(path: Path, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def d_day(job: Job, today: date) -> str:
    if job.deadline is None:
        return job.deadline_text or "-"
    n = (job.deadline - today).days
    return "D-day" if n == 0 else (f"D-{n}" if n > 0 else "마감")


def _sort_key(job: Job, today: date):
    return (job.deadline or date.max, job.title)


def render_markdown(new: list[Job], closing: list[Job], stats: dict, today: date) -> str:
    lines = [
        f"# Job-Catch 리포트 {today.isoformat()}",
        "",
        f"검색 {stats['fetched']}건 → 조건 통과 {stats['passed']}건 → **새 공고 {len(new)}건**"
        f" · 마감 7일 이내 {len(closing)}건",
        "",
    ]

    def table(jobs: list[Job]) -> list[str]:
        rows = [
            "| 마감 | 회사 | 공고 | 지역 | 경력 | 고용형태 |",
            "|---|---|---|---|---|---|",
        ]
        for j in sorted(jobs, key=lambda x: _sort_key(x, today)):
            title = j.title.replace("|", "/")
            rows.append(
                f"| {d_day(j, today)} | {j.company} | [{title}]({j.url}) | "
                f"{j.location} | {j.career} | {j.employment} |"
            )
        return rows

    if closing:
        lines += ["## 마감 임박 (7일 이내)", ""] + table(closing) + [""]
    lines += ["## 새 공고", ""]
    lines += table(new) if new else ["새 공고가 없습니다."]
    lines += ["", "---", "Powered by 취업 사람인 · 공고 원문은 링크에서 확인하세요."]
    return "\n".join(lines) + "\n"
