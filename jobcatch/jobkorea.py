"""잡코리아 검색 결과 페이지에서 채용공고를 읽어 온다.

사람에게 보여 주는 검색 페이지(/Search/)를 읽는다. 서버가 카드 HTML 을 바로 내려준다.
robots.txt 가 일반 접속에 이 경로를 막지 않으며, 하루 1회 · 몇 페이지 · 요청 사이 대기를 지킨다.
목록 카드에는 마감일 · 학력이 없어서, 필요하면 상세 페이지(fetch_detail)에서 보충한다.
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from .models import Detail, Job
from .summary import page_text
from .saramin import USER_AGENT

BASE = "https://www.jobkorea.co.kr"
SEARCH_URL = BASE + "/Search/"

_ID_RE = re.compile(r"GI_Read/(\d+)")
_MD_RE = re.compile(r"(?:(\d{4})\.)?(\d{1,2})[./](\d{1,2})")


def parse_deadline(text: str, today: date) -> date | None:
    """'~01/20(수)', '~ 12.26(토)', '2026.12.28(월)', '오늘마감', '내일마감'. 상시채용 등은 None."""
    if "오늘마감" in text:
        return today
    if "내일마감" in text:
        return today + timedelta(days=1)
    m = _MD_RE.search(text)
    if not m:
        return None
    month, day = int(m.group(2)), int(m.group(3))
    if m.group(1):
        year = int(m.group(1))
    else:
        year = today.year if month >= today.month else today.year + 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def search_params(keyword: str, career: list[str], page: int) -> dict:
    params = {"stext": keyword, "tabType": "recruit", "ord": "RegDtDesc", "Page_No": page}
    if career == ["신입"]:
        params["careerType"] = 1
    return params


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_search_page(html: str, today: date) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()
    for card in soup.select('[data-sentry-component="CardJob"]'):
        title_a = card.select_one('a[data-sentry-component="Title"]')
        m = _ID_RE.search(title_a.get("href", "")) if title_a else None
        if not m or m.group(1) in seen:
            continue
        bottom = [_text(s) for s in card.select("div.items-center.justify-between > div > span")]
        bottom = [b for b in bottom if b and b != "•"]
        if bottom and bottom[0] == "AD":
            continue  # 광고 카드
        job_id = m.group(1)
        seen.add(job_id)

        location, salary, sectors = "", "", []
        for chip in card.select('[data-sentry-component="GrayChip"]'):
            icon = chip.select_one('[class*="emoji--"]')
            icon_cls = " ".join(icon.get("class", [])) if icon else ""
            value = _text(chip)
            if "place" in icon_cls:
                location = value
            elif "briefcase" in icon_cls:
                sectors = [s.strip() for s in value.split(",") if s.strip()]
            elif "원" in value:
                salary = value

        jobs.append(
            Job(
                source="jobkorea",
                job_id=job_id,
                title=_text(title_a),
                company=_text(card.select_one("span.mb-5 a span.truncate")),
                url=f"{BASE}/Recruit/GI_Read/{job_id}",
                deadline_text="",
                deadline=None,
                location=location,
                career=bottom[0] if bottom else "",
                education="",
                employment="",
                salary=salary,
                sectors=sectors,
            )
        )
    return jobs


def fetch(keyword: str, career: list[str], max_pages: int, delay_sec: float, today: date) -> list[Job]:
    """검색어 하나로 최대 max_pages 페이지를 읽는다."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    found: list[Job] = []
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(delay_sec)
        resp = session.get(
            SEARCH_URL, params=search_params(keyword, career, page), timeout=20, allow_redirects=False
        )
        if resp.status_code != 200:
            raise RuntimeError(f"잡코리아 응답 {resp.status_code} (page {page})")
        jobs = parse_search_page(resp.text, today)
        found.extend(jobs)
        if len(jobs) < 20:
            break
    return found


_META_DEADLINE_RE = re.compile(r"마감일\s*:\s*(\d{4}\.\d{1,2}\.\d{1,2})")


def _item_value(soup, component: str, label: str) -> str:
    for item in soup.select(f'[data-sentry-component="{component}"]'):
        head = item.find("span")
        if head and _text(head) == label:
            spans = [s for s in item.find_all("span") if s is not head]
            return _text(spans[0]) if spans else ""
    return ""


def parse_detail(html: str, today: date) -> Detail:
    """상세 페이지의 근무지주소 · 학력 · 마감일."""
    soup = BeautifulSoup(html, "html.parser")
    deadline = None
    meta = soup.select_one('meta[name="description"]')
    m = _META_DEADLINE_RE.search(meta.get("content", "") if meta else "")
    if m:
        deadline = parse_deadline(m.group(1), today)
    return Detail(
        address=_item_value(soup, "RecruitmentItem", "근무지주소"),
        deadline=deadline,
        education=_item_value(soup, "QualificationItem", "학력"),
    )


def fetch_detail(job_id: str, today: date, delay_sec: float = 2.0) -> Detail:
    """공고 페이지(근무지 · 학력 · 마감) + 상세요강 iframe(본문). 본문을 못 읽어도 공고 페이지 값은 쓴다."""
    resp = requests.get(
        f"{BASE}/Recruit/GI_Read/{job_id}", headers={"User-Agent": USER_AGENT}, timeout=20
    )
    if resp.status_code != 200:
        raise RuntimeError(f"잡코리아 상세 응답 {resp.status_code}")
    detail = parse_detail(resp.text, today)
    time.sleep(delay_sec)
    try:
        body = requests.get(
            f"{BASE}/Recruit/GI_Read_Comt_Ifrm", params={"Gno": job_id},
            headers={"User-Agent": USER_AGENT}, timeout=20,
        )
        if body.status_code == 200:
            detail.body = parse_body(body.text)
    except requests.RequestException:
        pass
    return detail


def parse_body(html: str) -> str:
    """상세요강(GI_Read_Comt_Ifrm) 본문 글자."""
    return page_text(html)
