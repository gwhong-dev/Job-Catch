"""Job-Catch 실행.

  python run.py            수집 → 메일 발송 → 보낸 기록 저장
  python run.py --dry-run  메일 대신 output/mail_<날짜>.html 저장 (기록은 건드리지 않음)

공개 실행 로그에 남으므로 건수만 출력한다 (키워드 · 제목 · 설정 내용은 출력하지 않음).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from jobcatch import history, jobkorea, mail, saramin
from jobcatch.commute import Kakao
from jobcatch.config import ConfigError, load_config
from jobcatch.digest import DetailFetcher, Fetcher, build, collect

ROOT = Path(__file__).parent
KST = timezone(timedelta(hours=9))

FETCHERS: dict[str, Fetcher] = {"saramin": saramin.fetch, "jobkorea": jobkorea.fetch}
DETAILS: dict[str, DetailFetcher] = {"saramin": saramin.fetch_detail, "jobkorea": jobkorea.fetch_detail}


def main(
    argv: list[str],
    env: Mapping[str, str],
    root: Path,
    fetchers: dict[str, Fetcher] | None = None,
    sender: Callable[[str, str, Mapping[str, str]], None] = mail.send,
    today: date | None = None,
    details: dict[str, DetailFetcher] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    dry_run = "--dry-run" in argv
    today = today or datetime.now(KST).date()
    try:
        cfg = load_config(env, root / "config.toml")
    except ConfigError as err:
        print(f"설정 오류: {err}", file=sys.stderr)
        return 2

    collected = collect(cfg, today, fetchers or FETCHERS, sleep)
    seen_path = root / "data" / "seen.json"
    entries = history.load(seen_path)
    history.prune(entries, today)

    key = env.get("KAKAO_REST_KEY", "").strip()
    kakao = Kakao(key) if key else None
    digest, new_jobs = build(
        collected, cfg, entries, today,
        details=details if details is not None else DETAILS, kakao=kakao, sleep=sleep,
    )

    counts = ", ".join(f"{mail.SITE_NAMES.get(s, s)} {n}건" for s, n in collected.counts.items())
    commute_n = sum(1 for j in new_jobs if j.commute_min is not None)
    print(f"{counts} 수집 · 새 공고 {digest.new_total}건 · 마감임박 {len(digest.closing)}건"
          f" · 통근 계산 {commute_n}건")
    for site in digest.failed_sites:
        print(f"경고: {mail.SITE_NAMES.get(site, site)} 수집 실패", file=sys.stderr)
    if digest.commute_failed:
        print("경고: 통근 시간 계산 실패", file=sys.stderr)

    subject = mail.subject(digest)
    html = mail.render_html(digest)
    if dry_run:
        out = root / "output" / f"mail_{today.isoformat()}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"미리보기 저장: {out.relative_to(root)}")
        return 0

    try:
        sender(subject, html, env)
    except Exception as err:
        reason = str(err) if isinstance(err, mail.MailError) else type(err).__name__
        print(f"메일 발송 실패 ({reason})", file=sys.stderr)
        return 1

    history.record(entries, new_jobs, today)
    history.save(seen_path, entries)
    print("메일 발송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ, ROOT))
