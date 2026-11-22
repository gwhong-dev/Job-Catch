"""상세 본문에서 공고 요약을 규칙으로 뽑는다 (무료, API 없음).

- 업무 요약: "주요업무 / 담당업무 / 업무내용" 다음부터 다음 제목 전까지, 글머리표를 " / " 로 이어 80자까지
- 태그: 정해 둔 단어(설계 툴 · 분야 · 개발 기술) + 설정의 extra_tags 중 본문에 나오는 것
- 세부 묶음: 갈래 설정의 groups 순서대로 제목 · 직무 태그에 단어가 있으면 그 묶음
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

DUTY_HEADINGS = [
    "주요업무", "주요 업무", "담당업무", "담당 업무", "업무내용", "업무 내용", "수행업무", "직무내용",
    "이런 일을 해요", "이런 업무를 해요", "하는 일",
]
STOP_HEADINGS = [
    "자격요건", "자격 요건", "지원자격", "지원 자격", "필수", "우대", "근무조건", "근무 조건",
    "근무환경", "복리", "복지", "전형", "접수", "채용절차", "기타사항", "급여", "이런 분",
]
_BULLETS = "▣•ㆍ·-*■□◆◇○●▶►✔✓※▪◎"
MAX_DUTY = 80
MAX_TAGS = 6

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


def _find_heading(text: str, words: list[str], start: int = 0) -> tuple[int, int] | None:
    """가장 먼저 나오는 제목의 (시작, 끝) 위치."""
    best = None
    for w in words:
        i = text.find(w, start)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, i + len(w))
    return best


def extract_duty(body: str) -> str:
    head = _find_heading(body, DUTY_HEADINGS)
    if not head:
        return ""
    stop = _find_heading(body, STOP_HEADINGS, head[1])
    segment = body[head[1]: stop[0] if stop else len(body)]
    items = []
    for line in re.split(r"\n|(?<=\S)\s*[ㆍ▣•■▶►]\s*", segment):
        # "[담당업무] …" 처럼 제목을 감싼 괄호 조각도 떼어 낸다
        line = line.strip().lstrip(_BULLETS + " :]】)>").rstrip(" [【(<").strip()
        if re.search(r"[0-9A-Za-z가-힣]", line):
            items.append(" ".join(line.split()))
    duty = " / ".join(items)
    if len(duty) > MAX_DUTY:
        duty = duty[: MAX_DUTY - 1].rstrip(" /") + "…"
    return duty


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
