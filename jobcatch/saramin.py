"""사람인 검색 결과 페이지에서 채용공고를 읽어 온다.

공식 API가 아니라 사람에게 보여 주는 검색 페이지(/zf_user/search/recruit)를 읽는다.
robots.txt 가 이 경로를 막지 않으며, 하루 1회 · 몇 페이지 · 요청 사이 대기를 지킨다.
"""

from __future__ import annotations

import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from .models import Detail, Job
from .summary import image_urls, page_text

BASE = "https://www.saramin.co.kr"
SEARCH_URL = BASE + "/zf_user/search/recruit"

# 사람인은 기본 프로그램 User-Agent 요청을 오류 페이지로 돌려보낸다.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)




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


_EXP_CD = {"신입": "1", "경력": "2"}


def search_params(keyword: str, career: list[str], page: int) -> dict:
    """지역은 넣지 않는다: 수집 후 지역 · 통근 기준으로 거른다."""
    codes = [_EXP_CD[c] for c in ("신입", "경력") if c in career]
    params = {
        "searchword": keyword,
        "recruitSort": "reg_dt",  # 최신 등록순
        "recruitPageCount": 40,
        "recruitPage": page,
    }
    if codes:
        params["exp_cd"] = ",".join(codes)
    return params


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
            raise RuntimeError(f"사람인 응답 {resp.status_code} (page {page})")
        jobs = parse_search_page(resp.text, today)
        found.extend(jobs)
        if len(jobs) < 40:
            break
    return found


DETAIL_URL = BASE + "/zf_user/jobs/view"


def parse_detail(html: str, today: date) -> Detail:
    """상세 페이지의 근무지위치(.jv_location): 주소와 좌표."""
    soup = BeautifulSoup(html, "html.parser")
    loc = soup.select_one(".jv_location")
    if not loc:
        return Detail()
    address = loc.get("data-address") or _text(loc.select_one(".txt_adr"))
    address = re.sub(r"^\(\d{5}\)\s*", "", address.strip())
    coords = None
    try:
        lon, lat = float(loc.get("data-longitude", "")), float(loc.get("data-latitude", ""))
        if lon and lat:
            coords = (lon, lat)
    except ValueError:
        pass
    return Detail(address=" ".join(address.split()), coords=coords)


def _get(url: str, job_id: str) -> str:
    resp = requests.get(url, params={"rec_idx": job_id}, headers={"User-Agent": USER_AGENT}, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"사람인 상세 응답 {resp.status_code}")
    return resp.text


# 실제 공고 이미지는 pds 에 있다. static.saraminimage.co.kr(빈 그림 · 양식 머리) · 회사 로고 등 꾸밈 이미지는 뺀다
IMAGE_HOSTS = {"pds.saramin.co.kr"}


def parse_images(html: str) -> list[str]:
    """상세요강 본문의 공고 이미지 주소."""
    return image_urls(html, IMAGE_HOSTS)


def fetch_detail(job_id: str, today: date, delay_sec: float = 2.0) -> Detail:
    """상세요강 본문(작은 페이지)을 먼저 읽고, 본문에 근무지가 없을 때만 공고 페이지에서 주소 · 좌표."""
    html = _get(BODY_URL, job_id)
    body, address = parse_body(html)
    images = parse_images(html)
    if address:
        return Detail(address=address, body=body, images=images)
    time.sleep(delay_sec)
    detail = parse_detail(_get(DETAIL_URL, job_id), today)
    detail.body = body
    detail.images = images
    return detail


BODY_URL = BASE + "/zf_user/jobs/relay/view-detail"
_WORKPLACE_RE = re.compile(r"근무지\s*[:：]\s*([^\n]+)")
_ROAD_RE = re.compile(r"^(.+?(?:로|길)\s*\d+(?:-\d+)?)")


def parse_body(html: str) -> tuple[str, str]:
    """상세요강 본문과, 본문의 "근무지 : ..." 줄에서 뽑은 도로명 주소."""
    text = page_text(html)
    address = ""
    m = _WORKPLACE_RE.search(text)
    if m:
        line = re.sub(r"^\(\d{5}\)\s*", "", m.group(1).strip())
        road = _ROAD_RE.match(line)
        address = road.group(1) if road else line.split("(")[0].strip()
    return text, address
