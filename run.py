"""Job-Catch 실행: python run.py"""

from __future__ import annotations

import sys
import tomllib
from datetime import date, timedelta
from pathlib import Path

from jobcatch import saramin
from jobcatch.pipeline import dedupe, load_seen, matches, render_markdown, save_seen

ROOT = Path(__file__).parent
SEEN_PATH = ROOT / "data" / "seen.json"
OUT_DIR = ROOT / "output"


def main() -> int:
    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    today = date.today()
    run = cfg.get("run", {})

    fetched = []
    for search in cfg.get("saramin", []):
        jobs = saramin.fetch(search, run.get("max_pages", 2), run.get("delay_sec", 2.0), today)
        print(f"[사람인] '{search['keyword']}' {len(jobs)}건")
        fetched.extend(jobs)

    fetched = dedupe(fetched)
    if not fetched:
        print("경고: 수집 결과가 0건입니다. 사이트 구조가 바뀌었을 수 있습니다.", file=sys.stderr)
        return 1

    passed = [j for j in fetched if matches(j, cfg.get("filter", {}))]
    seen = load_seen(SEEN_PATH)
    new = [j for j in passed if j.key not in seen]
    soon = today + timedelta(days=7)
    closing = [j for j in passed if j.deadline and today <= j.deadline <= soon]

    report = render_markdown(
        new, closing, {"fetched": len(fetched), "passed": len(passed)}, today
    )
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"report_{today.isoformat()}.md"
    out.write_text(report, encoding="utf-8")

    for j in new:
        seen[j.key] = today.isoformat()
    save_seen(SEEN_PATH, seen)

    print(f"조건 통과 {len(passed)}건, 새 공고 {len(new)}건 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
