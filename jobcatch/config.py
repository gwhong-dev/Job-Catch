"""검색 기준 설정 읽기.

순서: 환경변수 JOBCATCH_CONFIG (TOML 전문) → 로컬 config.toml.
오류 메시지에는 설정 내용을 넣지 않는다 (공개 실행 로그에 남지 않도록).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

SITES = {"saramin", "jobkorea"}
CAREERS = {"신입", "경력"}


class ConfigError(Exception):
    pass


@dataclass
class Common:
    education: str = "학력무관"
    my_career_months: int = 0
    allow_locations: list[str] = field(default_factory=list)
    exclude_words: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    exclude_employment: list[str] = field(default_factory=list)
    home_address: str = ""
    commute_limit_min: int = 60
    commute_soft_min: int = 75
    max_detail_lookups: int = 60


@dataclass
class Track:
    name: str
    sites: list[str]
    keywords: list[str]
    career: list[str]
    include_any: list[str] = field(default_factory=list)


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


def load_config(env: Mapping[str, str], path: Path) -> Config:
    try:
        data = tomllib.loads(_read_text(env, path))
    except tomllib.TOMLDecodeError as err:
        line = getattr(err, "lineno", "?")
        raise ConfigError(f"설정 TOML 형식 오류 (줄 {line})") from None

    run = data.get("run", {})
    c = data.get("common", {})
    try:
        common = Common(
            education=str(c.get("education", "학력무관")),
            my_career_months=int(c.get("my_career_months", 0)),
            allow_locations=_str_list(c.get("allow_locations", []), "common.allow_locations"),
            exclude_words=_str_list(c.get("exclude_words", []), "common.exclude_words"),
            exclude_companies=_str_list(c.get("exclude_companies", []), "common.exclude_companies"),
            exclude_employment=_str_list(c.get("exclude_employment", []), "common.exclude_employment"),
            home_address=str(c.get("home_address", "")),
            commute_limit_min=int(c.get("commute_limit_min", 60)),
            commute_soft_min=int(c.get("commute_soft_min", 75)),
            max_detail_lookups=int(c.get("max_detail_lookups", 60)),
        )
    except (TypeError, ValueError):
        raise ConfigError("common: 숫자 칸에 숫자가 아닌 값이 있습니다") from None

    tracks: list[Track] = []
    for i, t in enumerate(data.get("track", [])):
        name = str(t.get("name", f"갈래{i + 1}"))
        where = f"track '{name}'"
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
