"""검색 기준 설정 읽기.

순서: 환경변수 JOBCATCH_CONFIG (TOML 전문) → 로컬 config.toml.
오류 메시지에는 설정 내용을 넣지 않는다 (공개 실행 로그에 남지 않도록).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

SITES = {"saramin", "jobkorea"}
CAREERS = {"신입", "경력"}
EDU_ORDER = ["학력무관", "고졸", "초대졸", "대졸", "석사", "박사"]


class ConfigError(Exception):
    pass


@dataclass
class Common:
    education: str = ""  # 비우면 학력으로 거르지 않음
    my_career_months: int = 0
    allow_locations: list[str] = field(default_factory=list)
    exclude_words: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    exclude_employment: list[str] = field(default_factory=list)
    home_address: str = ""
    commute_limit_min: int = 60
    commute_soft_min: int = 75
    max_detail_lookups: int = 60
    extra_tags: list[str] = field(default_factory=list)  # 요약 태그로 더 찾을 단어


@dataclass
class Track:
    name: str
    sites: list[str]
    keywords: list[str]
    career: list[str]
    include_any: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)  # 세부 묶음: 이름 → 제목에서 찾을 단어


@dataclass
class Config:
    common: Common
    tracks: list[Track]
    max_pages: int = 2
    delay_sec: float = 2.0
    max_cards_per_track: int = 30


def _read_text(env: Mapping[str, str], path: Path) -> str:
    text = env.get("JOBCATCH_CONFIG", "")
    if text.strip():
        return text
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise ConfigError(
        "검색 기준 설정이 없습니다. config.example.toml 을 config.toml 로 복사하거나 "
        "JOBCATCH_CONFIG 를 설정하세요."
    )


def _str_list(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: 글자 목록이어야 합니다")
    return value


def _groups(value, where: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ConfigError(f'{where}: {{ "묶음 이름" = ["단어", ...] }} 모양이어야 합니다')
    return {str(k): _str_list(v, where) for k, v in value.items()}


def _table(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] 은 표(table)여야 합니다")
    return value


def load_config(env: Mapping[str, str], path: Path) -> Config:
    try:
        data = tomllib.loads(_read_text(env, path))
    except tomllib.TOMLDecodeError as err:
        m = re.search(r"line (\d+)", str(err))
        raise ConfigError(f"설정 TOML 형식 오류 (줄 {m.group(1) if m else '?'})") from None

    run = _table(data, "run")
    c = _table(data, "common")
    education = c.get("education", "")
    if education and education not in EDU_ORDER:
        raise ConfigError(f"common.education 은 {' / '.join(EDU_ORDER)} 중에서 고르거나 비웁니다")
    try:
        common = Common(
            education=str(education),
            my_career_months=int(c.get("my_career_months", 0)),
            allow_locations=_str_list(c.get("allow_locations", []), "common.allow_locations"),
            exclude_words=_str_list(c.get("exclude_words", []), "common.exclude_words"),
            exclude_companies=_str_list(c.get("exclude_companies", []), "common.exclude_companies"),
            exclude_employment=_str_list(c.get("exclude_employment", []), "common.exclude_employment"),
            home_address=str(c.get("home_address", "")),
            commute_limit_min=int(c.get("commute_limit_min", 60)),
            commute_soft_min=int(c.get("commute_soft_min", 75)),
            max_detail_lookups=int(c.get("max_detail_lookups", 60)),
            extra_tags=_str_list(c.get("extra_tags", []), "common.extra_tags"),
        )
    except (TypeError, ValueError):
        raise ConfigError("common: 숫자 칸에 숫자가 아닌 값이 있습니다") from None

    raw_tracks = data.get("track", [])
    if not isinstance(raw_tracks, list) or not all(isinstance(t, dict) for t in raw_tracks):
        raise ConfigError("갈래는 [[track]] 블록으로 적습니다")
    tracks: list[Track] = []
    for i, t in enumerate(raw_tracks):
        name = str(t.get("name", f"갈래{i + 1}"))
        where = f"track #{i + 1}"  # 갈래 이름은 원하는 직무라서 공개 로그에 남기지 않는다
        sites = _str_list(t.get("sites", []), f"{where} sites")
        keywords = _str_list(t.get("keywords", []), f"{where} keywords")
        career = _str_list(t.get("career", ["신입"]), f"{where} career")
        if not sites or not set(sites) <= SITES:
            raise ConfigError(f"{where}: sites 는 {sorted(SITES)} 중에서 고릅니다")
        if not keywords:
            raise ConfigError(f"{where}: keywords 가 비어 있습니다")
        if not career or not set(career) <= CAREERS:
            raise ConfigError(f"{where}: career 는 신입 / 경력 중에서 고릅니다")
        tracks.append(
            Track(
                name=name,
                sites=sites,
                keywords=keywords,
                career=career,
                include_any=_str_list(t.get("include_any", []), f"{where} include_any"),
                groups=_groups(t.get("groups", {}), f"{where} groups"),
            )
        )
    if not tracks:
        raise ConfigError("[[track]] 이 하나 이상 있어야 합니다")

    try:
        return Config(
            common=common,
            tracks=tracks,
            max_pages=int(run.get("max_pages", 2)),
            delay_sec=float(run.get("delay_sec", 2.0)),
            max_cards_per_track=int(run.get("max_cards_per_track", 30)),
        )
    except (TypeError, ValueError):
        raise ConfigError("run: 숫자 칸에 숫자가 아닌 값이 있습니다") from None
