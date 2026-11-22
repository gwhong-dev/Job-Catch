"""카카오 API 로 집 → 근무지 대중교통 시간을 구한다.

- 주소 → 좌표: 카카오 로컬 주소 검색 (무료 하루 100,000건)
- 대중교통 경로: 카카오맵 대중교통 경로 조회 (무료 하루 1,000건)
소요 시간은 저장해 두지 않고 그때그때 조회한다.
"""

from __future__ import annotations

import re
from typing import Callable, Literal

import requests

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
TRANSIT_URL = "https://dapi.kakao.com/v2/routing/publictraffic"

Coords = tuple[float, float]  # (경도 x, 위도 y)


class KakaoUnavailable(Exception):
    """키 오류 · 쿼터 초과: 이번 실행에서는 통근 계산을 멈춘다."""


def clean_address(addr: str) -> str:
    """우편번호 · 괄호 안 건물명 · 층수를 떼어 주소 검색에 맞춘다."""
    a = re.sub(r"^\(\d{5}\)\s*", "", addr.strip())
    a = a.split("(")[0]
    a = re.sub(r"\s\d+층.*$", "", a)
    return " ".join(a.split())


class Kakao:
    def __init__(self, key: str, get: Callable = requests.get):
        self._headers = {"Authorization": f"KakaoAK {key}"}
        self._get = get

    def _call(self, url: str, params: dict) -> dict:
        try:
            resp = self._get(url, params=params, headers=self._headers, timeout=15)
        except requests.RequestException as err:
            raise KakaoUnavailable(f"카카오 접속 실패 ({type(err).__name__})") from None
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code == 401 or resp.status_code == 403:
            raise KakaoUnavailable(f"카카오 키 오류 (HTTP {resp.status_code})")
        if resp.status_code == 400 and isinstance(body, dict) and body.get("code") == -10:
            raise KakaoUnavailable("카카오 쿼터 초과")
        if resp.status_code != 200:
            return {}
        return body if isinstance(body, dict) else {}

    def geocode(self, addr: str) -> Coords | None:
        query = clean_address(addr)
        if not query:
            return None
        docs = self._call(ADDRESS_URL, {"query": query}).get("documents") or []
        if not docs:
            return None
        try:
            return float(docs[0]["x"]), float(docs[0]["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def transit_minutes(self, src: Coords, dst: Coords) -> int | None:
        body = self._call(
            TRANSIT_URL,
            {"start_x": str(src[0]), "start_y": str(src[1]), "end_x": str(dst[0]), "end_y": str(dst[1])},
        )
        if body.get("status") != "OK":
            return None
        times = [
            r.get("properties", {}).get("totalTime")
            for r in body.get("routes") or []
        ]
        times = [t for t in times if isinstance(t, (int, float))]
        return round(min(times) / 60) if times else None


def commute_status(minutes: int | None, limit: int, soft: int) -> Literal["pass", "check", "exclude"] | None:
    if minutes is None:
        return None
    if minutes <= limit:
        return "pass"
    if minutes <= soft:
        return "check"
    return "exclude"
