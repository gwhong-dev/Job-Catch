# 잡코리아 수집 · 통합 기준 · 매일 아침 메일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사람인 · 잡코리아에서 "공통 조건 + 갈래별 검색" 기준으로 공고를 모아, 매일 06:30 KST GitHub Actions 에서 휴대폰용 HTML 메일 한 통을 보낸다.

**Architecture:** 사이트 모듈(`saramin.py`, `jobkorea.py`)은 `fetch(keyword, career, max_pages, delay_sec, today) -> list[Job]` 하나만 노출한다. `filters.py` 가 공고를 통과/확인/제외로 나누고, `digest.py` 가 보낸 기록(`history.py`)과 비교해 메일 내용을 만들고, `mail.py` 가 HTML 을 그리고 보낸다. 설정은 `config.py` 가 환경변수 `JOBCATCH_CONFIG` 또는 로컬 `config.toml` 에서 읽는다.

**Tech Stack:** Python 3.12 (로컬 3.14), requests, beautifulsoup4, tomllib, smtplib, unittest(pytest 로 실행), GitHub Actions(`actions/cache/restore@v4`, `actions/cache/save@v4`, `actions/setup-python@v5`)

**Spec:** `docs/superpowers/specs/2026-11-22-jobkorea-daily-email-design.md`

## Global Constraints

- 저장소는 공개. 실제 검색 기준 · 메일 주소 · 비밀번호를 커밋하지 않는다. `config.toml`, `data/`, `output/` 은 `.gitignore`.
- 공개 로그(stdout/stderr)에는 건수와 사이트 이름만. 키워드 · 회사 · 제목 · 설정 내용 · 메일 주소를 찍지 않는다.
- 사이트 요청: 검색 조건당 최대 `max_pages`(기본 2), 요청 사이 `delay_sec`(기본 2.0초) 이상 대기, 같은 사이트 다음 키워드로 넘어갈 때도 대기.
- 날짜는 KST 기준: `datetime.now(timezone(timedelta(hours=9))).date()` (Windows 에 tzdata 가 없을 수 있어 zoneinfo 쓰지 않음).
- 마감 임박 = 오늘 ≤ 마감일 ≤ 오늘+7일.
- 메일 제목: `[Job-Catch] 11/23(월) 새 공고 12건 · 마감임박 3건`, 새 공고 0건이면 `[Job-Catch] 11/23(월) 새 공고 없음`
- 테스트용 HTML 조각의 회사 · 공고 이름은 `(예시)` 붙은 가짜 이름으로 바꾼다.
- 커밋 메시지는 한국어, 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

- 사이트 구조가 바뀌어 한 사이트가 0건 → 메일 맨 위 "⚠ 잡코리아 수집 실패" 경고가 붙고 다른 사이트 결과는 그대로 보낸다 (Task 6 테스트)
- 메일 발송 실패 → 보낸 기록을 갱신하지 않고 종료 코드 1 (Task 8 테스트)
- `JOBCATCH_CONFIG` 가 없거나 TOML 이 깨짐 → 설정 내용을 찍지 않는 짧은 오류와 종료 코드 2 (Task 1 테스트)
- 12월에 "~ 01/20" 같은 마감일 → 다음 해로 계산 (기존 사람인 테스트 유지 + Task 4 잡코리아 마감 형식 테스트)
- 제목에 `<`, `&` 가 든 공고 → 메일 HTML 에서 이스케이프 (Task 7 테스트)

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `jobcatch/models.py` (새) | `Job` dataclass (`saramin.py` 에서 옮김) |
| `jobcatch/config.py` (새) | 설정 읽기 · 검증 → `Config` |
| `jobcatch/filters.py` (새) | 학력 · 경력 · 지역 해석, `classify()` |
| `jobcatch/saramin.py` | 새 `fetch` 시그니처로 변경 |
| `jobcatch/jobkorea.py` (새) | 잡코리아 검색 페이지 파싱 · 수집 |
| `jobcatch/history.py` (새) | 보낸 기록 `data/seen.json` 읽기 · 쓰기 · 정리 |
| `jobcatch/digest.py` (새) | 수집 → 분류 → 새 공고/마감 임박 묶기 |
| `jobcatch/mail.py` (새) | 메일 제목 · HTML 만들기, Gmail 발송 |
| `jobcatch/pipeline.py` | 삭제 (`matches` 는 filters, `dedupe` 는 digest 로, `render_markdown` 은 mail 로 대체) |
| `run.py` | 조립, `--dry-run` |
| `config.example.toml` | 기존 `config.toml` 을 `git mv` 후 새 형식으로 |
| `.github/workflows/daily.yml` (새) | 예약 실행 |
| `README.md` | 쓰는 법 |

---

### Task 1: Job 모델 이동 + 설정 읽기

**Files:**
- Create: `jobcatch/models.py`, `jobcatch/config.py`, `tests/test_config.py`
- Modify: `jobcatch/saramin.py` (`Job` 정의 삭제, `from .models import Job`), `.gitignore` (`config.toml` 추가)
- Move: `config.toml` → `config.example.toml` (`git mv`, 내용은 스펙 §5 예시 그대로로 교체)

**Interfaces:**
- Produces:
  - `models.Job` — 기존 필드 그대로 + `track: str = ""`, `flags: list[str] = field(default_factory=list)`. `key` 속성 유지.
  - `config.Common(education: str, my_career_months: int, allow_locations: list[str], exclude_words: list[str], exclude_companies: list[str], exclude_employment: list[str])`
  - `config.Track(name: str, sites: list[str], keywords: list[str], career: list[str], include_any: list[str])`
  - `config.Config(max_pages: int, delay_sec: float, max_cards_per_track: int, common: Common, tracks: list[Track])`
  - `config.load_config(env: Mapping[str, str], path: Path) -> Config` — `env["JOBCATCH_CONFIG"]` 가 있으면 그것, 없으면 `path` 파일, 둘 다 없으면 `ConfigError`
  - `class ConfigError(Exception)` — 메시지에 설정 내용을 넣지 않는다
- 검증: `sites` 는 `{"saramin", "jobkorea"}` 부분집합, `career` 는 `{"신입", "경력"}` 부분집합, `track` 1개 이상, `keywords` 비어 있지 않음. 어기면 `ConfigError("track '<name>': ...")`. 기본값 `max_pages=2`, `delay_sec=2.0`, `max_cards_per_track=30`, 목록 항목은 `[]`, `my_career_months=0`, `education="학력무관"`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_config.py`
  - `test_env_wins_over_file`: env 에 track 이름 "A" 인 TOML, 파일에 "B" → `cfg.tracks[0].name == "A"`
  - `test_file_used_without_env`: env `{}` + 임시 파일 → 파일 값
  - `test_missing_raises`: env `{}` + 없는 경로 → `ConfigError`
  - `test_broken_toml_raises_without_echo`: env 에 `"keywords = [비밀키워드"` → `ConfigError`, `"비밀키워드" not in str(err)`
  - `test_unknown_site_rejected`: `sites=["wanted"]` → `ConfigError`
  - `test_example_config_loads`: 저장소의 `config.example.toml` 이 오류 없이 읽힘, `len(cfg.tracks) == 2`
  - `test_defaults`: `[run]` 없는 TOML → `max_pages == 2`, `delay_sec == 2.0`, `max_cards_per_track == 30`
- [ ] **Step 2: 실행해서 실패 확인** — `python -m pytest tests/test_config.py -q` → ImportError
- [ ] **Step 3: `models.py`, `config.py` 구현, `config.toml` → `config.example.toml` 이동 · 교체, `.gitignore` 에 `config.toml`** — `tomllib.TOMLDecodeError` 는 `ConfigError("설정 TOML 형식 오류 (줄 N)")` 로 바꿔 원문을 숨긴다 (`err.lineno` 사용).
- [ ] **Step 4: 전체 테스트 통과 확인** — `python -m pytest -q` → 모두 PASS (기존 `tests/test_saramin.py` 의 `pipeline.matches` import 는 Task 2 에서 바꾸므로, 이 Task 에서는 그 테스트 파일의 import 만 그대로 두고 `pipeline.py` 도 아직 지우지 않는다)
- [ ] **Step 5: 커밋** — `git add -A && git commit -m "설정 읽기와 Job 모델 분리"`

---

### Task 2: 공고 분류 (학력 · 경력 · 지역 · 제외 조건)

**Files:**
- Create: `jobcatch/filters.py`, `tests/test_filters.py`
- Modify: `tests/test_saramin.py` (`matches` 테스트를 `classify` 테스트로 옮김), 삭제: `jobcatch/pipeline.py` 의 `matches`

**Interfaces:**
- Consumes: `models.Job`, `config.Common`, `config.Track`
- Produces:
  - `EDU_ORDER = ["학력무관", "고졸", "초대졸", "대졸", "석사", "박사"]`
  - `required_education(text: str) -> str | None` — 공고의 학력 칸 → `EDU_ORDER` 값, 모르면 None
  - `min_career_months(text: str) -> int | None` — 경력 칸 → 최소 요구 개월, 모르면 None
  - `location_status(location: str, allow: list[str]) -> Literal["pass", "check", "exclude"]`
  - `classify(job: Job, common: Common, track: Track) -> tuple[Literal["pass", "check", "exclude"], list[str]]` — 두 번째 값은 표시용 flags (`"학력 확인"`, `"지역 확인"`, `"경력 확인"`)

해석 규칙 (테스트가 고정함):
- 학력: `"학력무관"`→학력무관, `"고졸"`→고졸, `"초대졸"`·`"대졸(2,3년)"`→초대졸, `"대졸(4년)"`·`"대졸"`(괄호 없음)→대졸, `"석사"`→석사, `"박사"`→박사. 공고 요구 > `common.education` 이면 exclude, None 이면 flag "학력 확인".
- 경력: `"신입"`·`"경력무관"`·`"신입·경력"`(신입 포함)→0, `"경력 3년↑"`·`"경력3년↑"`·`"경력 3~7년"`→36, `"경력"` 만→None. track.career 가 `["신입"]` 만이면 0 일 때만 통과, `"경력"` 포함이면 `≤ common.my_career_months` 통과. None 이면 flag "경력 확인".
- 지역: 공백 정리 후, 빈 값 · `"전국"` · `"재택"` 포함 → check. `" 외 N"` 꼬리가 있으면 나머지 지역을 알 수 없으므로 → check. `","` 로 나눠 여러 곳이면 그중 하나라도 허용 → check, 없으면 exclude. 한 곳이면 허용 항목 중 하나로 시작 → pass; 시·도만 있음(`"서울"`, `"경기"`, `"서울 전체"`) 이고 그 시·도로 시작하는 허용 항목 있음 → check; 그 외 exclude.
- 제외 단어/회사/고용형태, `track.include_any` 는 기존 `matches` 규칙 그대로 (제목+회사+직무 글자, include 는 대소문자 무시).
- 결과: 하나라도 exclude → exclude. 아니면 flags 가 있으면 check, 없으면 pass.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_filters.py`
  - `test_required_education`: `"대졸(2,3년)↑"`→`"초대졸"`, `"대졸(4년)↑"`→`"대졸"`, `"학력무관"`→`"학력무관"`, `"석사↑"`→`"석사"`, `""`→None
  - `test_min_career_months`: `"신입"`→0, `"신입·경력"`→0, `"경력무관"`→0, `"경력 3년↑"`→36, `"경력3년↑"`→36, `"경력 5~10년"`→60, `"경력"`→None
  - `test_location_status`, allow=`["경기 성남시", "서울 금천구"]`: `"경기 성남시 분당구"`→pass, `"서울 금천구"`→pass, `"부산 해운대구"`→exclude, `"서울"`→check, `"서울 종로구 외 14"`→check, `"서울 금천구 외 2"`→check, `"경기 성남시, 부산 중구"`→check, `"부산 중구, 대구 중구"`→exclude, `"전국"`→check, `""`→check
  - `test_classify_excludes_four_year_degree`: common.education `"초대졸"`, job.education `"대졸(4년)↑"` → `("exclude", ...)`
  - `test_classify_career_track`: my_career_months=48, career `["신입","경력"]`: `"경력 3년↑"`→pass, `"경력 7년↑"`→exclude; career `["신입"]`: `"경력 3년↑"`→exclude, `"신입·경력"`→pass
  - `test_classify_unknown_education_flags`: education `""` → `("check", ["학력 확인"])`
  - 기존 `test_saramin.py` 의 `matches` 두 경우(영업 제외, 파견직 제외)를 `classify` 로 옮김
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_filters.py -q` → ImportError
- [ ] **Step 3: `filters.py` 구현, `pipeline.matches` 삭제, `test_saramin.py` import 정리**
- [ ] **Step 4: 통과 확인** — `python -m pytest -q` → PASS
- [ ] **Step 5: 커밋** — `"공고 분류 규칙 추가 (학력·경력·지역)"`

---

### Task 3: 사람인 수집기를 새 시그니처로

**Files:**
- Modify: `jobcatch/saramin.py`, `tests/test_saramin.py`

**Interfaces:**
- Produces: `saramin.fetch(keyword: str, career: list[str], max_pages: int, delay_sec: float, today: date) -> list[Job]`, `saramin.search_params(keyword: str, career: list[str], page: int) -> dict`
- `search_params`: `searchword`, `recruitSort="reg_dt"`, `recruitPageCount=40`, `recruitPage=page`, `exp_cd` = `["신입"]`→`"1"`, `["경력"]`→`"2"`, 둘 다→`"1,2"`. 지역 파라미터는 넣지 않는다 (수집 후 필터).
- `parse_search_page` · `parse_deadline` 은 그대로.

- [ ] **Step 1: 실패하는 테스트** — `test_search_params`: `search_params("기구설계", ["신입","경력"], 2)` 가 `{"searchword": "기구설계", "exp_cd": "1,2", "recruitPage": 2, ...}` 포함, `"loc_mcd" not in`
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_saramin.py -q`
- [ ] **Step 3: 구현** — `fetch` 는 `search_params` 로 요청, 나머지 루프는 기존과 같음
- [ ] **Step 4: 통과 확인** — `python -m pytest -q`
- [ ] **Step 5: 커밋** — `"사람인 수집기 검색 조건을 갈래 설정에 맞춤"`

---

### Task 4: 잡코리아 수집기

**Files:**
- Create: `jobcatch/jobkorea.py`, `tests/test_jobkorea.py`, `tests/fixtures/jobkorea_search.html`

**Interfaces:**
- Produces:
  - `jobkorea.SEARCH_URL = "https://www.jobkorea.co.kr/Search/"`
  - `jobkorea.search_params(keyword: str, career: list[str], page: int) -> dict` — `stext`, `tabType="recruit"`, `ord="RegDtDesc"`, `Page_No=page`, career 가 `["신입"]` 만이면 `careerType=1`, 아니면 넣지 않음
  - `jobkorea.parse_search_page(html: str, today: date) -> list[Job]` — `source="jobkorea"`, `job_id` 는 `GI_Read/(\d+)`, `url=f"https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}"`. 광고(AD) 카드는 뺀다. 한 페이지 안 같은 ID 는 한 번.
  - `jobkorea.parse_deadline(text: str, today: date) -> date | None` — 카드 · 상세에 나오는 형식(`"~12/06(토)"`, `"~ 12.06(토)"`, `"오늘마감"`, `"내일마감"`, `"상시채용"`)
  - `jobkorea.fetch(keyword, career, max_pages, delay_sec, today) -> list[Job]` — 사람인과 같은 User-Agent, `allow_redirects=False`, 200 아니면 `RuntimeError("잡코리아 응답 <code> (page N)")`, 페이지당 결과 < 20 이면 중단
- 마감일 · 학력을 상세 페이지에서 보충하는 것은 이 Task 범위 밖. 카드에 없으면 빈 값 → filters 가 "확인" flag 를 붙인다.

- [ ] **Step 1: 픽스처 만들기** — 검색 페이지를 1회 받아(`stext=백엔드`) 카드 3장(일반 2, AD 1)만 남기고 저장, 회사 · 제목 글자는 `(예시)` 이름으로 교체. 받은 원본 전체는 커밋하지 않는다.
- [ ] **Step 2: 실패하는 테스트**
  - `test_parse_skips_ads`: 픽스처 → 2건, 모두 `source == "jobkorea"`, `job_id` 숫자, `url` 이 `GI_Read/` 포함
  - `test_parse_fields`: 첫 카드의 `title`, `company`, `location`, `career` 가 픽스처에 넣은 값과 같음
  - `test_parse_deadline`: today=2026-12-20 에서 `"~01/20(수)"`→2027-01-20, `"~ 12.26(토)"`→2026-12-26, `"오늘마감"`→today, `"내일마감"`→today+1, `"상시채용"`→None
  - `test_search_params`: `(["신입"])` → `careerType == 1`; `(["신입","경력"])` → `"careerType" not in`
  - `test_empty_page`: `"<html></html>"` → `[]`
- [ ] **Step 3: 실패 확인** — `python -m pytest tests/test_jobkorea.py -q`
- [ ] **Step 4: 구현** — 선택자는 픽스처 구조를 보고 정한다 (`[data-sentry-component=CardJob]` 기준)
- [ ] **Step 5: 통과 확인 + 실제 1회 확인** — `python -m pytest -q`; 그다음 `python -c "from datetime import date; from jobcatch import jobkorea; print(len(jobkorea.fetch('백엔드', ['신입'], 1, 2.0, date.today())))"` → 1 이상
- [ ] **Step 6: 커밋** — `"잡코리아 검색 페이지 수집기 추가"`

---

### Task 5: 보낸 기록

**Files:**
- Create: `jobcatch/history.py`, `tests/test_history.py`

**Interfaces:**
- Produces:
  - `history.Entry(title: str, company: str, url: str, source: str, track: str, deadline: date | None, first_sent: date)`
  - `history.load(path: Path) -> dict[str, Entry]` — 파일 없으면 `{}`; 예전 형식(`{key: "2026-11-22"}`)은 건너뛴다
  - `history.save(path: Path, entries: dict[str, Entry]) -> None` — JSON, 날짜는 ISO 문자열
  - `history.record(entries: dict[str, Entry], jobs: list[Job], today: date) -> None` — 없는 key 만 추가, 있는 key 는 deadline 만 갱신
  - `history.prune(entries: dict[str, Entry], today: date) -> None` — `deadline + 30일 < today` 이거나, deadline 없고 `first_sent + 60일 < today` 인 항목 삭제

- [ ] **Step 1: 실패하는 테스트** — `test_roundtrip`(save→load 같음), `test_record_keeps_first_sent`(두 번 record 해도 first_sent 는 처음 날짜), `test_prune`(마감 31일 지난 것 삭제, 29일 지난 것 유지, 마감 없음+61일 삭제), `test_load_legacy_format_ignored`
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_history.py -q`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `python -m pytest -q`
- [ ] **Step 5: 커밋** — `"보낸 공고 기록 저장 추가"`

---

### Task 5b: 상세 페이지 근무지 · 카카오 통근 시간

**Files:**
- Create: `jobcatch/commute.py`, `tests/test_commute.py`, `tests/fixtures/saramin_detail.html`, `tests/fixtures/jobkorea_detail.html`
- Modify: `jobcatch/saramin.py`, `jobcatch/jobkorea.py`, `jobcatch/config.py` (Common 에 `home_address: str = ""`, `commute_limit_min: int = 60`, `commute_soft_min: int = 75`, `max_detail_lookups: int = 60`), `config.example.toml`

**Interfaces:**
- Produces:
  - `models.Detail(address: str, deadline: date | None, education: str)` (`models.py` 에 추가)
  - `saramin.parse_detail(html: str, today: date) -> Detail` — `.jv_location .address` 글자 (없으면 `""`), deadline/education 은 None/`""`
  - `saramin.fetch_detail(job_id: str, today: date) -> Detail` — `https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=<id>`, 리다이렉트 따라감
  - `jobkorea.parse_detail(html: str, today: date) -> Detail` — "근무지주소" 다음 주소, "마감일 2026.12.06(일)" 형식 마감, "학력" 다음 칸
  - `jobkorea.fetch_detail(job_id: str, today: date) -> Detail`
  - `commute.clean_address(addr: str) -> str` — 괄호 `(` 부터 뒤와 `N층` 제거, 공백 정리
  - `commute.Kakao(key: str, get=requests.get)` 메서드 `geocode(addr: str) -> tuple[float, float] | None`, `transit_minutes(src: tuple[float, float], dst: tuple[float, float]) -> int | None`
  - `class commute.KakaoUnavailable(Exception)` — HTTP 401, 또는 HTTP 400 + `code == -10`(쿼터) 일 때
  - `commute.commute_status(minutes: int | None, limit: int, soft: int) -> Literal["pass", "check", "exclude"] | None` — None 이면 판정 불가
- 카카오 요청: 헤더 `Authorization: KakaoAK <key>`, 주소 `GET https://dapi.kakao.com/v2/local/search/address.json?query=`, 경로 `GET https://dapi.kakao.com/v2/routing/publictraffic?start_x=&start_y=&end_x=&end_y=` (x=경도). 경로는 `status == "OK"` 일 때 `routes[].properties.totalTime`(초) 최솟값 → 반올림 분, 그 외 status 는 None.

- [ ] **Step 1: 픽스처** — 상세 페이지 각 1개를 받아 근무지 · 마감 · 학력 부분만 남기고 회사 이름을 `(예시)` 로 (주소는 공개 건물 주소라 그대로 둠)
- [ ] **Step 2: 실패하는 테스트**
  - `test_saramin_parse_detail`: 픽스처 → `address` 가 `"서울 "` 또는 `"경기 "` 로 시작
  - `test_jobkorea_parse_detail`: 픽스처 → address 비어 있지 않음, deadline 이 date
  - `test_clean_address`: `"서울 종로구 청계천로 41 (서린동, 영풍빌딩) 12층"` → `"서울 종로구 청계천로 41"`
  - `test_geocode`: 가짜 get 이 `{"documents":[{"x":"127.0","y":"37.5"}]}` → `(127.0, 37.5)`; `{"documents":[]}` → None
  - `test_transit_minutes`: 가짜 응답 `status OK`, totalTime `[3300, 3000]` → 50; `status "NO_RESULTS"` → None; 요청 파라미터 `start_x` 가 경도
  - `test_kakao_quota_raises`: HTTP 400 + `{"code": -10}` → `KakaoUnavailable`; HTTP 401 → `KakaoUnavailable`
  - `test_commute_status`: (55,60,75)→pass, (70,60,75)→check, (80,60,75)→exclude, (None,…)→None
- [ ] **Step 3: 실패 확인** — `python -m pytest tests/test_commute.py -q`
- [ ] **Step 4: 구현**
- [ ] **Step 5: 통과 확인 + 실제 상세 1건씩 읽기** — `python -m pytest -q`; 사람인 · 잡코리아 `fetch_detail` 을 실제 ID 하나로 호출해 address 출력 확인 (카카오는 키를 받은 뒤 Task 9 에서 확인)
- [ ] **Step 6: 커밋** — `"상세 페이지 근무지와 카카오 대중교통 시간 조회 추가"`

---

### Task 6: 수집 · 메일 내용 묶기

**Files:**
- Create: `jobcatch/digest.py`, `tests/test_digest.py`
- Delete: `jobcatch/pipeline.py` (`dedupe` 를 digest 로 옮긴 뒤)

**Interfaces:**
- Consumes: `Config`, `classify`, `history.Entry`, 사이트 `fetch`
- Produces:
  - `digest.Fetcher = Callable[[str, list[str], int, float, date], list[Job]]`
  - `digest.Collected(jobs: list[Job], failed_sites: list[str], counts: dict[str, int])` — counts 는 사이트별 수집 건수
  - `digest.collect(cfg: Config, today: date, fetchers: dict[str, Fetcher], sleep: Callable[[float], None] = time.sleep) -> Collected` — 갈래 × 사이트 × 키워드로 호출, 각 Job 에 `track` 채움, 예외는 잡아서 그 사이트를 `failed_sites` 에, 사이트 총 0건도 `failed_sites` 에 (중복 없이). 호출 사이 `sleep(cfg.delay_sec)`. 같은 key 는 처음 나온 갈래로 한 번만.
  - `digest.ClosingItem(title, company, url, source, track, deadline: date, flags: list[str])`
  - `digest.Digest(today: date, new_by_track: dict[str, list[Job]], overflow_by_track: dict[str, int], closing: list[ClosingItem], failed_sites: list[str], new_total: int)`
  - `digest.build(collected: Collected, cfg: Config, entries: dict[str, Entry], today: date, details: dict[str, DetailFetcher] | None = None, kakao: Kakao | None = None, sleep=time.sleep) -> tuple[Digest, list[Job]]` — 두 번째 값은 기록에 남길 새 공고 전부(상한으로 잘린 것 포함). `DetailFetcher = Callable[[str, date], Detail]`
  - `Job` 에 `commute_min: int | None = None` 필드 추가 (Task 1 의 models 에)
  - `Digest` 에 `commute_failed: bool` 추가
- 통근 규칙 (스펙 §6-1):
  - `kakao` 와 `cfg.common.home_address` 가 있으면 통근 모드. 집 좌표는 한 번 geocode, 실패하면 통근 모드 끔 + `commute_failed=True`
  - 통근 모드에서 지역 판정: 카드 지역의 시 · 도가 `allow_locations` 의 시 · 도 집합에 없으면 exclude, 있으면 일단 보류
  - 보류된 새 공고만 최대 `max_detail_lookups` 건 상세 조회(호출 사이 `sleep(delay_sec)`) → 주소 → 좌표 → 분. `commute_status` 가 None 이 아니면 그 값이 지역 판정을 대신하고 `job.commute_min` 기록, None 이거나 상한 밖이면 `location_status` 판정
  - 잡코리아 상세의 deadline · education 이 있으면 Job 을 채운 뒤 classify 를 다시 한다
  - `KakaoUnavailable` → 남은 공고는 지역 목록 판정, `commute_failed=True`. 상세 조회 예외는 그 공고만 지역 목록 판정
- 규칙:
  - classify 결과 exclude 는 버리고, check 는 flags 를 `job.flags` 에 넣어 남긴다
  - 새 공고 = key 가 entries 에 없는 것
  - 마감 임박 = (이번 새 공고 + entries 전체) 중 마감이 오늘~7일 이내, 마감일 오름차순. 새 공고가 마감 임박이면 마감 임박에만 넣고 갈래 목록에서는 뺀다
  - 갈래 목록은 마감일 오름차순(없으면 뒤), `max_cards_per_track` 초과분은 `overflow_by_track` 에 개수만
  - `new_by_track` 키 순서 = 설정의 track 순서, 0건 갈래도 키는 있음

- [ ] **Step 1: 실패하는 테스트** (가짜 fetcher 사용, `sleep=lambda s: None`)
  - `test_collect_marks_failed_site`: jobkorea fetcher 가 `RuntimeError` → `failed_sites == ["jobkorea"]`, 사람인 결과는 남음
  - `test_collect_zero_is_failure`: jobkorea fetcher 가 `[]` → `"jobkorea" in failed_sites`
  - `test_collect_dedupes_across_tracks`: 같은 Job 이 두 갈래에서 나옴 → jobs 에 한 번, track 은 첫 갈래
  - `test_build_new_vs_seen`: entries 에 있는 key 는 new 에 없음
  - `test_build_closing_includes_old_entry`: entries 에 마감 D-3 항목 → closing 에 있음; 마감 D-8 → 없음
  - `test_build_closing_not_duplicated`: 새 공고가 D-2 → closing 에 있고 new_by_track 에는 없음
  - `test_build_cap`: max_cards_per_track=2, 새 공고 5건 → 갈래 목록 2건, overflow 3, 두 번째 반환값 5건
  - `test_commute_overrides_region`: 가짜 kakao 가 50분 → 허용 목록에 없는 "경기 안산시" 공고도 통과, `commute_min == 50`; 90분 → 허용 목록의 "경기 성남시" 공고도 제외
  - `test_commute_province_prefilter`: 통근 모드에서 "부산 중구" → 상세 조회 없이 제외 (가짜 detail fetcher 호출 0회)
  - `test_commute_lookup_cap`: max_detail_lookups=1, 후보 3건 → detail 호출 1회, 나머지는 지역 목록 판정
  - `test_kakao_unavailable_falls_back`: geocode 가 `KakaoUnavailable` → `commute_failed is True`, 지역 목록 판정으로 결과 있음
  - `test_no_kakao_uses_region_list`: kakao=None → detail 호출 0회
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_digest.py -q`
- [ ] **Step 3: 구현, `pipeline.py` 삭제**
- [ ] **Step 4: 통과 확인** — `python -m pytest -q`
- [ ] **Step 5: 커밋** — `"수집 결과를 메일 내용으로 묶는 단계 추가"`

---

### Task 7: 메일 HTML · 발송

**Files:**
- Create: `jobcatch/mail.py`, `tests/test_mail.py`

**Interfaces:**
- Consumes: `digest.Digest`
- Produces:
  - `mail.subject(d: Digest) -> str` — Global Constraints 의 형식. 요일은 `"월화수목금토일"[d.today.weekday()]`
  - `mail.render_html(d: Digest) -> str` — 순서: 수집 실패 경고 → 마감 임박 → 갈래별(`■ 기구설계 (5건)`) → 꼬리말. 카드: 첫 줄 `D-3 · 회사 [사람인]`, 둘째 줄 제목(경력), 셋째 줄 지역 · 고용형태 · 학력, flags 는 작은 배지, `공고 보기 →` 링크. 인라인 style 만(메일 앱은 `<style>` 을 무시할 수 있음), 최대 폭 600px, 표 레이아웃 쓰지 않음. 모든 글자는 `html.escape`.
  - 경고 문구: `⚠ 잡코리아 수집 실패 — 사이트 구조가 바뀌었거나 접속이 막혔을 수 있습니다.` (사이트 이름은 `{"saramin": "사람인", "jobkorea": "잡코리아"}`). `commute_failed` 면 `⚠ 통근 시간 계산 실패 — 오늘은 지역 목록으로 걸렀습니다.`
  - `job.commute_min` 이 있으면 셋째 줄 앞에 `🚇 약 52분`
  - 새 공고 0건: 갈래 대신 `새 공고가 없습니다.` 한 줄 (마감 임박 · 경고는 그대로)
  - overflow: 갈래 끝에 `외 N건은 사이트에서 확인하세요.`
  - 꼬리말: `출처: 사람인 · 잡코리아 검색 결과. 지원 전 원문 공고를 확인하세요.`
  - `mail.send(subject: str, html_body: str, env: Mapping[str, str], smtp_factory=smtplib.SMTP_SSL) -> None` — `smtp_factory("smtp.gmail.com", 465)`, `login(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"])`, `To: env["MAIL_TO"]`, `MIMEText(html, "html", "utf-8")`. 값이 빠졌으면 `MailError("메일 설정 누락: GMAIL_USER")` (값은 찍지 않음)

- [ ] **Step 1: 실패하는 테스트**
  - `test_subject`: today 2026-11-23, new_total 12, closing 3개 → `"[Job-Catch] 11/23(월) 새 공고 12건 · 마감임박 3건"`; new_total 0 → `"[Job-Catch] 11/23(월) 새 공고 없음"`
  - `test_html_escapes`: 제목 `"<b>개발</b> & 설계"` → html 에 `"&lt;b&gt;"` 포함, `"<b>개발"` 미포함
  - `test_html_warning_first`: failed_sites `["jobkorea"]` → `"⚠ 잡코리아 수집 실패"` 가 `"마감 임박"` 보다 앞
  - `test_html_overflow_and_flags`: overflow 3 → `"외 3건"`; job.flags `["학력 확인"]` → `"학력 확인"` 포함
  - `test_send_uses_env`: 가짜 SMTP 객체 → login 인자, To 헤더 확인
  - `test_send_missing_env`: `MAIL_TO` 없음 → `MailError`, 메시지에 다른 env 값 없음
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_mail.py -q`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `python -m pytest -q`
- [ ] **Step 5: 커밋** — `"휴대폰용 메일 HTML과 Gmail 발송 추가"`

---

### Task 8: 실행 파일 조립

**Files:**
- Modify: `run.py`
- Create: `tests/test_run.py`

**Interfaces:**
- Produces: `run.main(argv: list[str], env: Mapping[str, str], root: Path, fetchers: dict[str, Fetcher] | None = None, sender: Callable[[str, str, Mapping[str, str]], None] = mail.send, today: date | None = None) -> int`
- 순서: 설정 읽기(`ConfigError` → stderr 한 줄, 2 반환) → `collect` → history `load(root/"data"/"seen.json")` → `prune` → `build` → `--dry-run` 이면 `root/"output"/f"mail_{today}.html"` 저장하고 기록은 건드리지 않음(0 반환) → 아니면 `sender` 호출, 예외면 stderr `메일 발송 실패` 후 1 반환(기록 저장 안 함) → 성공하면 `record` + `save`, 0 반환
- 로그: `사람인 N건, 잡코리아 N건 수집 · 새 공고 N건 · 마감임박 N건` 한 줄 + 실패 사이트 이름. 키워드 · 제목 출력 금지.
- 수집 결과가 전부 0건이어도 메일은 보낸다 (경고 메일). 종료 코드는 0.

- [ ] **Step 1: 실패하는 테스트** (`tmp_path` 같은 임시 폴더, 가짜 fetcher · sender)
  - `test_dry_run_writes_html_no_history`: `--dry-run` → output 파일 생김, `data/seen.json` 없음
  - `test_send_failure_keeps_history`: sender 가 예외 → 반환 1, seen.json 없음
  - `test_success_records`: 반환 0, seen.json 에 새 공고 key 있음; 두 번째 실행 → 새 공고 0 (sender 가 받은 제목에 `새 공고 없음`)
  - `test_bad_config_exit_2`: env `JOBCATCH_CONFIG="["` → 2
  - `test_logs_no_titles`: capsys 출력에 가짜 공고 제목 · 키워드 없음
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_run.py -q`
- [ ] **Step 3: 구현** — `if __name__ == "__main__": sys.exit(main(sys.argv[1:], os.environ, ROOT, fetchers={"saramin": saramin.fetch, "jobkorea": jobkorea.fetch}))`
- [ ] **Step 4: 통과 확인** — `python -m pytest -q`
- [ ] **Step 5: 실제 dry-run** — 로컬 `config.toml`(커밋 안 됨)에 사용자의 실제 기준을 넣고 `python run.py --dry-run` → 종료 0, `output/mail_<오늘>.html` 생김. 이 HTML 을 사용자에게 보여 주고 휴대폰 폭(375px)에서 확인.
- [ ] **Step 6: 커밋** — `"실행 파일을 새 단계로 조립, --dry-run 추가"`

---

### Task 9: GitHub Actions · README

**Files:**
- Create: `.github/workflows/daily.yml`
- Modify: `README.md`

**Interfaces:**
- 워크플로:
  - `on: schedule: - cron: "30 21 * * *"` 와 `workflow_dispatch`
  - `permissions: contents: read`
  - 단계: checkout → setup-python 3.12 (pip 캐시) → `pip install -r requirements.txt` → `actions/cache/restore@v4` (`path: data/seen.json`, `key: seen-${{ github.run_id }}`, `restore-keys: seen-`) → `python run.py` (env: `JOBCATCH_CONFIG: ${{ vars.JOBCATCH_CONFIG }}`, `GMAIL_USER`/`GMAIL_APP_PASSWORD`/`MAIL_TO`/`KAKAO_REST_KEY` 는 `secrets.*`; run.py 는 `KAKAO_REST_KEY` 가 비어 있지 않을 때만 `Kakao` 를 만든다) → `actions/cache/save@v4` (`if: success()`, 같은 path, `key: seen-${{ github.run_id }}`)
  - `pull_request` 트리거는 두지 않는다
- README: "진행 상황" 체크 갱신, "내 저장소에서 쓰기" 절(스펙 §9 의 4단계, 설정 이름 4개, 앱 비밀번호 만드는 곳 `https://myaccount.google.com/apppasswords`), "로컬에서 시험" 절(`cp config.example.toml config.toml`, `python run.py --dry-run`), 공개 저장소에서 기준을 커밋하지 말 것 안내

- [ ] **Step 1: 워크플로 문법 확인** — `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily.yml', encoding='utf-8'))"` (PyYAML 없으면 `pip install pyyaml` 후) → 오류 없음
- [ ] **Step 2: README 작성**
- [ ] **Step 3: 커밋 · push · PR** — `"매일 아침 실행 워크플로와 사용 안내 추가"`, PR 본문 끝에 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- [ ] **Step 4: 사용자 작업 안내** — Gmail 앱 비밀번호 만들기, Secret 3개 · Variable 1개 등록 (값은 사용자가 직접 입력)
- [ ] **Step 5: 실제 시험** — 등록 후 `gh workflow run daily.yml` → `gh run watch` → 성공, 메일 도착을 사용자에게 확인. 사이트가 막혀 경고 메일이 오면 스펙 §3 대로 작업 스케줄러 방식을 새 작업으로 제안.
