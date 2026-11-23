"""상세 본문에서 공고 요약을 규칙으로 뽑는다 (무료, API 없음).

- 구역: 줄 맨 앞(또는 괄호 안)의 제목으로 업무 / 필수(자격요건) 구역을 찾는다. 끝 제목은 어디서든 본다
- 업무 요약 · 필수조건: 구역의 항목을 " / " 로 이어 80자까지 (항목 경계에서 자름). 제목 말 · 사이트 양식 잔재 ·
  "및" 같은 조각은 빼고, 남은 게 너무 짧으면 비운다. 필수조건에는 "우대" 항목을 넣지 않는다
- 태그: 정해 둔 단어(설계 툴 · 분야 · 개발 기술) + 설정의 extra_tags 중 업무 · 필수 구역(없으면 본문 전체)에 나오는 것
- 세부 묶음: 갈래 설정의 groups 순서대로 제목 · 직무 태그에 단어가 있으면 그 묶음
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

DUTY_HEADINGS = [
    "주요업무", "주요 업무", "담당업무", "담당 업무", "업무내용", "업무 내용", "수행업무", "직무내용",
    "이런 일을 해요", "이런 업무를 해요", "하는 일",
]
REQUIRED_HEADINGS = [
    "자격요건", "자격 요건", "지원자격", "지원 자격", "필수요건", "필수 요건", "자격조건", "자격 조건",
    "필수사항", "필수 사항", "이런 분을 찾아요",
]
STOP_HEADINGS = [
    "자격요건", "자격 요건", "지원자격", "지원 자격", "필수", "우대", "근무조건", "근무 조건",
    "근무환경", "복리", "복지", "전형", "접수", "채용절차", "기타사항", "급여", "이런 분",
]
# 회사 소개는 업무 · 필수 구역의 끝. 흔한 말이라 줄 맨 앞 · 괄호 안일 때만 제목으로 본다
INTRO_HEADINGS = ["채용 기업", "채용기업 소개", "회사 소개", "회사소개", "기업 소개", "기업소개"]
# 필수 구역의 끝: 업무 구역 끝 말에서 필수 제목 자체와 "필수" · "이런 분" · "우대" 를 빼고 따로 본다
REQUIRED_STOPS = [w for w in STOP_HEADINGS if w not in REQUIRED_HEADINGS + ["필수", "이런 분", "우대"]] + [
    "이런 분이면",
]
TEMPLATE_RESIDUE = ["상세내용을 입력하세요", "내용을 입력하세요"]
FILLER_WORDS = {"및", "등", "외"}
_BULLETS = "▣•ㆍ·-*■□◆◇○●▶►✔✓※▪◎"
_OPEN_BRACKETS = "[【<(〔「『"
_MEANING = re.compile(r"[0-9A-Za-z가-힣]")
_LETTER = re.compile(r"[A-Za-z가-힣]")
MAX_DUTY = 80
MIN_MEANING = 4  # 요약 전체의 한글 · 영문 · 숫자가 이보다 적으면 비운다 ("및" 같은 조각)
MAX_TAGS = 6


def _norm(text: str) -> str:
    return "".join(_MEANING.findall(text))


_HEADING_WORDS = {_norm(w) for w in DUTY_HEADINGS + REQUIRED_HEADINGS + STOP_HEADINGS + INTRO_HEADINGS}


# (표시 이름, 본문에서 찾을 말들). 순서대로 붙는다.
TAGS: list[tuple[str, list[str]]] = [
    # 설계 툴
    ("AutoCAD", ["AutoCAD", "Auto CAD", "오토캐드"]),
    ("SolidWorks", ["SolidWorks", "Solid Works", "솔리드웍스"]),
    ("CATIA", ["CATIA", "카티아"]),
    ("Creo", ["Creo", "크레오", "Pro-E", "ProE"]),
    ("NX", ["NX", "UG-NX", "UG", "Unigraphics"]),
    ("Inventor", ["Inventor", "인벤터"]),
    ("ANSYS", ["ANSYS", "앤시스"]),
    # 분야
    ("반도체", ["반도체"]),
    ("2차전지", ["2차전지", "이차전지", "배터리"]),
    ("디스플레이", ["디스플레이", "OLED", "LCD"]),
    ("자동차", ["자동차", "차량"]),
    ("컨베이어", ["컨베이어", "Conveyor"]),
    ("로봇", ["로봇"]),
    ("금형", ["금형"]),
    ("판금", ["판금"]),
    ("지그", ["지그", "JIG"]),
    ("유공압", ["유공압", "공압", "유압"]),
    ("PLC", ["PLC"]),
    # 개발 기술
    ("Java", ["Java"]),
    ("Spring", ["Spring"]),
    ("Kotlin", ["Kotlin"]),
    ("Python", ["Python", "파이썬"]),
    ("Django", ["Django"]),
    ("Node.js", ["Node.js", "NodeJS"]),
    ("React", ["React"]),
    ("TypeScript", ["TypeScript"]),
    ("MySQL", ["MySQL"]),
    ("PostgreSQL", ["PostgreSQL"]),
    ("AWS", ["AWS"]),
    ("Docker", ["Docker"]),
    ("Kubernetes", ["Kubernetes", "k8s"]),
]


def page_text(html: str) -> str:
    """HTML 의 보이는 글자를 줄 단위로 (스크립트 · 스타일 제외)."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = (" ".join(line.split()) for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def _starts_line(text: str, i: int) -> bool:
    """제목으로 볼 자리인가: 줄 맨 앞(글머리표 · 번호 · 기호 다음)이거나 여는 괄호 바로 뒤."""
    if i > 0 and text[i - 1] in _OPEN_BRACKETS:
        return True
    line_start = text.rfind("\n", 0, i) + 1
    return _LETTER.search(text, line_start, i) is None


def _find_heading(text: str, words: list[str], start: int = 0, line_start: bool = False) -> tuple[int, int] | None:
    """가장 먼저 나오는 제목의 (시작, 끝) 위치. line_start 면 줄 맨 앞 · 괄호 안인 것만."""
    best = None
    for w in words:
        i = text.find(w, start)
        while i >= 0 and line_start and not _starts_line(text, i):
            i = text.find(w, i + 1)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, i + len(w))
    return best


def _first(*hits: tuple[int, int] | None) -> tuple[int, int] | None:
    found = [h for h in hits if h]
    return min(found) if found else None


def _duty_segment(body: str) -> str | None:
    head = _find_heading(body, DUTY_HEADINGS, line_start=True)
    if not head:
        return None
    stop = _first(_find_heading(body, STOP_HEADINGS, head[1]),
                  _find_heading(body, INTRO_HEADINGS, head[1], line_start=True))
    return body[head[1]: stop[0] if stop else len(body)]


def _required_segment(body: str) -> str | None:
    head = _find_heading(body, REQUIRED_HEADINGS, line_start=True)
    if not head:
        return None
    stop = _first(_find_heading(body, REQUIRED_STOPS, head[1]),
                  _find_heading(body, ["우대"] + INTRO_HEADINGS + DUTY_HEADINGS, head[1], line_start=True))
    return body[head[1]: stop[0] if stop else len(body)]


def _items(segment: str) -> list[str]:
    items = []
    for line in re.split(r"\n|(?<=\S)\s*[ㆍ▣•■▶►]\s*", segment):
        # "[담당업무] …" 처럼 제목을 감싼 괄호 조각도 떼어 낸다
        line = " ".join(line.strip().lstrip(_BULLETS + " :]】)>").rstrip(" [【(<").split())
        key = _norm(line)
        if len(key) < 2 and line not in FILLER_WORDS:
            continue
        if line in FILLER_WORDS or key in _HEADING_WORDS or any(t in line for t in TEMPLATE_RESIDUE):
            continue
        items.append(line)
    return items


def _join(items: list[str]) -> str:
    """항목 경계에서 MAX_DUTY 안으로 자른다. 하나라도 잘리면 끝에 …"""
    if not items or len(_norm(" ".join(items))) < MIN_MEANING:
        return ""
    joined = " / ".join(items)
    if len(joined) <= MAX_DUTY:
        return joined
    if len(items[0]) > MAX_DUTY - 2:
        return items[0][: MAX_DUTY - 1].rstrip(" /") + "…"
    out = items[0]
    for item in items[1:]:
        if len(out) + 3 + len(item) > MAX_DUTY - 2:
            break
        out += " / " + item
    return out + " …"


def extract_duty(body: str) -> str:
    segment = _duty_segment(body)
    return _join(_items(segment)) if segment is not None else ""


def extract_required(body: str) -> str:
    segment = _required_segment(body)
    if segment is None:
        return ""
    return _join([i for i in _items(segment) if "우대" not in i])


@dataclass
class Analysis:
    duty: str = ""
    required: str = ""
    tags: list[str] = field(default_factory=list)


def analyze(body: str, extra_tags: list[str]) -> Analysis:
    """본문 글자 → 업무 요약 · 필수조건 · 태그. 추출 방법을 바꿀 때는 이 함수 안쪽만 바꾼다."""
    if not body:
        return Analysis()
    duty_seg, req_seg = _duty_segment(body), _required_segment(body)
    sections = [s for s in (duty_seg, req_seg) if s is not None]
    tag_text = "\n".join(sections) if sections else body
    return Analysis(duty=extract_duty(body), required=extract_required(body),
                    tags=find_tags(tag_text, extra_tags))


def _contains(text: str, word: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9.\- ]+", word):
        # 영문 짧은 말(NX, Go 등)은 다른 단어의 일부로 걸리지 않게 경계를 본다
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, re.I) is not None
    return word in text


def find_tags(body: str, extra_tags: list[str]) -> list[str]:
    found = [name for name, words in TAGS if any(_contains(body, w) for w in words)]
    found += [w for w in extra_tags if w and w not in found and _contains(body, w)]
    return found[:MAX_TAGS]


def group_of(title: str, sectors: list[str], groups: dict[str, list[str]]) -> str:
    if not groups:
        return ""
    # 제목을 먼저 본다. 사람인 직무 태그에는 검색어가 흔히 붙어 있어 태그는 제목에 단서가 없을 때만 쓴다
    for text in (title, " ".join(sectors)):
        for name, words in groups.items():
            if any(w and _contains(text, w) for w in words):
                return name
    return "기타"
