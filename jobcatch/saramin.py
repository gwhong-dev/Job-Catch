"""사람인 검색 결과 페이지에서 채용공고를 읽어 온다.

공식 API가 아니라 사람에게 보여 주는 검색 페이지(/zf_user/search/recruit)를 읽는다.
robots.txt 가 이 경로를 막지 않으며, 하루 1회 · 몇 페이지 · 요청 사이 대기를 지킨다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE = "https://www.saramin.co.kr"
SEARCH_URL = BASE + "/zf_user/search/recruit"

# 사람인은 기본 프로그램 User-Agent 요청을 오류 페이지로 돌려보낸다.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


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

    @property
    def key(self) -> str:
        return f"{self.source}:{self.job_id}"


_DEADLINE_RE = re.compile(r"~\s*(\d{1,2})/(\d{1,2})")


def parse_deadline(text: str, today: date) -> date | None:
    """'~ 12/06(금)' 같은 글자에서 마감일을 만든다. 상시채용 등은 None."""
    m = _DEADLINE_RE.search(text)
    if not m:
        if "오늘마감" in text:
            return today
        return None
    month, day = int(m.group(1)), int(m.group(2))
    year = today.year if month >= today.month else today.year + 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_search_page(html: str, today: date) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for item in soup.select("div.item_recruit"):
        job_id = item.get("value") or ""
        link = item.select_one("h2.job_tit a")
        if not job_id or not link:
            continue
        cond = [_text(s) for s in item.select("div.job_condition > span")]
        cond += [""] * (5 - len(cond))
        deadline_text = _text(item.select_one("div.job_date span.date"))
        jobs.append(
            Job(
                source="saramin",
                job_id=job_id,
                title=(link.get("title") or _text(link)).strip(),
                company=_text(item.select_one("strong.corp_name a")),
                url=f"{BASE}/zf_user/jobs/relay/view?rec_idx={job_id}",
                deadline_text=deadline_text,
                deadline=parse_deadline(deadline_text, today),
                location=cond[0],
                career=cond[1],
                education=cond[2],
                employment=cond[3],
                salary=cond[4],
                sectors=[_text(a) for a in item.select("div.job_sector a")],
                posted_text=_text(item.select_one("span.job_day")),
            )
        )
    return jobs


def fetch(search: dict, max_pages: int, delay_sec: float, today: date) -> list[Job]:
    """검색 조건 하나로 최대 max_pages 페이지를 읽는다."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    params = {
        "searchword": search["keyword"],
        "recruitSort": "reg_dt",  # 최신 등록순
        "recruitPageCount": 40,
    }
    if search.get("exp_cd"):
        params["exp_cd"] = search["exp_cd"]
    if search.get("loc_mcd"):
        params["loc_mcd"] = search["loc_mcd"]
    params.update(search.get("extra_params", {}))

    found: list[Job] = []
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(delay_sec)
        params["recruitPage"] = page
        resp = session.get(SEARCH_URL, params=params, timeout=20, allow_redirects=False)
        if resp.status_code != 200:
            raise RuntimeError(f"사람인 응답 {resp.status_code} (page {page})")
        jobs = parse_search_page(resp.text, today)
        found.extend(jobs)
        if len(jobs) < 40:
            break
    return found
