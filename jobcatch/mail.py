"""휴대폰에서 읽기 좋은 메일 HTML 을 만들고 Gmail 로 보낸다.

메일 앱은 <style> 을 무시하기도 해서 인라인 style 만 쓴다. 모든 글자는 이스케이프한다.
"""

from __future__ import annotations

import smtplib
from datetime import date
from email.mime.text import MIMEText
from html import escape
from typing import Mapping

from .digest import ClosingItem, Digest
from .models import Job

SITE_NAMES = {"saramin": "사람인", "jobkorea": "잡코리아"}
WEEKDAYS = "월화수목금토일"

C_TEXT = "#1f2328"
C_SUB = "#59636e"
C_LINE = "#d1d9e0"
C_ACCENT = "#0b57d0"
C_WARN_BG = "#fff4e5"
C_WARN = "#8a4b00"
C_URGENT = "#c5221f"


class MailError(Exception):
    pass


def _day(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def subject(d: Digest) -> str:
    head = f"[Job-Catch] {_day(d.today)}"
    if d.new_total == 0:
        return f"{head} 새 공고 없음"
    return f"{head} 새 공고 {d.new_total}건 · 마감임박 {len(d.closing)}건"


def _dday(deadline: date | None, today: date, fallback: str) -> str:
    if deadline is None:
        return fallback or "마감일 확인"
    n = (deadline - today).days
    return "D-day" if n == 0 else (f"D-{n}" if n > 0 else "마감")


C_TAG_BG = "#eef1f4"


def _badges(items: list[str], bg: str, color: str) -> str:
    return "".join(
        f'<span style="display:inline-block;margin:6px 4px 0 0;padding:2px 8px;border-radius:10px;'
        f'background:{bg};color:{color};font-size:12px">{escape(x)}</span>'
        for x in items
    )


def _card(*, dday: str, urgent: bool, company: str, source: str, title: str, place: str,
          commute_min: int | None, summary: str, tags: list[str], flags: list[str], url: str) -> str:
    color = C_URGENT if urgent else C_ACCENT
    where = [f"📍 {escape(place)}"] if place else []
    if commute_min is not None:
        where.append(f"🚇 약 {commute_min}분")
    summary_html = (
        f'<div style="font-size:13px;color:{C_TEXT};line-height:1.5;margin-top:4px">📝 {escape(summary)}</div>'
        if summary else ""
    )
    return (
        f'<div style="border:1px solid {C_LINE};border-radius:12px;padding:12px 14px;margin:0 0 10px">'
        f'<div style="font-size:13px;color:{C_SUB}">'
        f'<b style="color:{color}">{escape(dday)}</b> · {escape(company)} '
        f'<span style="color:{C_SUB}">[{escape(SITE_NAMES.get(source, source))}]</span></div>'
        f'<div style="font-size:15px;font-weight:600;color:{C_TEXT};margin:4px 0 2px;line-height:1.4">'
        f'<a href="{escape(url, quote=True)}" style="color:{C_TEXT};text-decoration:none">{escape(title)}</a></div>'
        f'<div style="font-size:13px;color:{C_SUB};line-height:1.5">{" · ".join(where)}</div>'
        f"{summary_html}"
        f"{_badges(tags, C_TAG_BG, C_SUB)}{_badges(flags, C_WARN_BG, C_WARN)}"
        f'<div style="margin-top:8px"><a href="{escape(url, quote=True)}" '
        f'style="color:{C_ACCENT};font-size:14px;font-weight:600;text-decoration:none">공고 보기 →</a></div>'
        f"</div>"
    )


def _job_card(j: Job, today: date) -> str:
    title = f"{j.title} ({j.career})" if j.career else j.title
    return _card(
        dday=_dday(j.deadline, today, j.deadline_text), urgent=False, company=j.company,
        source=j.source, title=title, place=j.address or j.location, commute_min=j.commute_min,
        summary=j.summary, tags=j.tags, flags=j.flags, url=j.url,
    )


def _closing_card(c: ClosingItem, today: date) -> str:
    return _card(
        dday=_dday(c.deadline, today, ""), urgent=True, company=c.company, source=c.source,
        title=f"{c.title} · {c.track}", place=c.address or c.location, commute_min=c.commute_min,
        summary=c.summary, tags=c.tags, flags=c.flags, url=c.url,
    )


def _subheading(text: str) -> str:
    return (f'<div style="font-size:14px;font-weight:600;color:{C_SUB};margin:14px 0 8px">'
            f"{escape(text)}</div>")


def _group_counts(jobs: list[Job]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j.group] = counts.get(j.group, 0) + 1
    return list(counts.items())


def _toc(d: Digest) -> str:
    lines = []
    if d.closing:
        lines.append(f"마감 임박 {len(d.closing)}건")
    for name, jobs in d.new_by_track.items():
        total = len(jobs) + d.overflow_by_track.get(name, 0)
        if not total:
            continue
        groups = [(g, n) for g, n in _group_counts(jobs) if g]
        detail = f" ({' · '.join(f'{g} {n}' for g, n in groups)})" if groups else ""
        lines.append(f"{name} {total}건{detail}")
    if not lines:
        return ""
    items = "".join(f"<div>• {escape(line)}</div>" for line in lines)
    return (f'<div style="background:{C_TAG_BG};border-radius:10px;padding:10px 14px;margin:10px 0 0;'
            f'font-size:13px;color:{C_TEXT};line-height:1.7">{items}</div>')


def _heading(text: str) -> str:
    return (f'<h2 style="font-size:17px;color:{C_TEXT};margin:22px 0 10px;padding-bottom:6px;'
            f'border-bottom:2px solid {C_TEXT}">{escape(text)}</h2>')


def _warning(text: str) -> str:
    return (f'<div style="background:{C_WARN_BG};color:{C_WARN};border-radius:10px;padding:12px 14px;'
            f'margin:0 0 12px;font-size:14px;line-height:1.5">{escape(text)}</div>')


def render_html(d: Digest) -> str:
    parts: list[str] = []
    for site in d.failed_sites:
        name = SITE_NAMES.get(site, site)
        parts.append(_warning(f"⚠ {name} 수집 실패 — 사이트 구조가 바뀌었거나 접속이 막혔을 수 있습니다."))
    if d.commute_failed:
        parts.append(_warning("⚠ 통근 시간 계산 실패 — 오늘은 지역 목록으로 걸렀습니다."))

    parts.append(_toc(d))

    if d.closing:
        parts.append(_heading(f"마감 임박 ({len(d.closing)}건)"))
        parts += [_closing_card(c, d.today) for c in d.closing]

    if d.new_total == 0:
        parts.append(f'<p style="font-size:15px;color:{C_SUB};margin:22px 0">새 공고가 없습니다.</p>')
    else:
        for name, jobs in d.new_by_track.items():
            extra = d.overflow_by_track.get(name, 0)
            if not jobs and not extra:
                continue
            parts.append(_heading(f"■ {name} ({len(jobs) + extra}건)"))
            counts = dict(_group_counts(jobs))
            current = None
            for j in jobs:
                if j.group and j.group != current:
                    parts.append(_subheading(f"▸ {j.group} ({counts[j.group]})"))
                current = j.group
                parts.append(_job_card(j, d.today))
            if extra:
                parts.append(f'<p style="font-size:13px;color:{C_SUB}">외 {extra}건은 사이트에서 확인하세요.</p>')

    parts.append(
        f'<p style="font-size:12px;color:{C_SUB};margin-top:28px;line-height:1.5">'
        "출처: 사람인 · 잡코리아 검색 결과. 지원 전 원문 공고를 확인하세요.</p>"
    )
    body = "".join(parts)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:#ffffff">'
        f'<div style="max-width:600px;margin:0 auto;padding:16px;font-family:-apple-system,'
        f"'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:{C_TEXT}\">"
        f'<div style="font-size:13px;color:{C_SUB}">Job-Catch · {escape(_day(d.today))}</div>'
        f"{body}</div></body></html>"
    )


def send(subject_text: str, html_body: str, env: Mapping[str, str], smtp_factory=smtplib.SMTP_SSL) -> None:
    for name in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "MAIL_TO"):
        if not env.get(name):
            raise MailError(f"메일 설정 누락: {name}")
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject_text
    msg["From"] = env["GMAIL_USER"]
    msg["To"] = env["MAIL_TO"]
    with smtp_factory("smtp.gmail.com", 465) as smtp:
        smtp.login(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"])
        smtp.send_message(msg)
