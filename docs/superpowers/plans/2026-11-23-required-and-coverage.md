# 필수조건 · 카드 채우기 · 통근순 정렬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메일 카드마다 주소 · 통근 · 요약 · 필수조건이 붙도록 상세 조회를 고치고, 묶음 안을 통근순으로 세우고, 마감 임박 다시 알림 카드도 채운다.

**Architecture:** 본문 분석은 `summary.analyze()` 한 곳으로 모은다 (나중에 무료 AI 로 갈아 끼울 자리). 상세 조회 순서 · 상한 · 시간 안전장치 · 미룸은 `digest._Commute` 와 `build()` 에서 처리한다. 보낸 기록 `Entry` 에 카드 내용을 더 저장해 다시 알림 카드에 쓴다 (통근 시간은 저장하지 않고 다시 계산).

**Tech Stack:** Python 3.12, BeautifulSoup, requests, unittest(pytest 로 실행)

**Spec:** `docs/superpowers/specs/2026-11-23-required-and-coverage-design.md`

## Global Constraints

- 공개 실행 로그에는 건수만. 공고 제목 · 본문 · 설정 내용 출력 금지.
- 요청 사이 `delay_sec` 대기 유지.
- 필수조건은 보여 주기만 한다. 필수조건으로 공고를 빼거나 순서를 바꾸지 않는다.
- 보낸 기록(`seen.json`)에 통근 시간을 저장하지 않는다.
- `max_detail_lookups` 기본값 150. 상세 조회 시간 안전장치 15분. 워크플로 `timeout-minutes: 30` 유지.
- 마감 임박 기준 `CLOSING_DAYS = 7` (기존 값).
- 테스트 본문 조각은 실제 회사 · 공고를 알아볼 수 없게 쓴다 ("(예시)" 붙이기 등 기존 관례).
- 전체 테스트: `python -m pytest -q` → 모두 PASS 여야 커밋.

## Review Focus

- 필수 구역이 업무 구역보다 먼저 나오는 본문 → 두 값 모두 제자리에서 뽑혀야 한다 (Task 1 테스트).
- 우대 구역만 있고 자격요건이 없는 본문 → 필수조건은 빈 값 (Task 1 테스트).
- 목록에서 마감일을 모르는 공고(잡코리아)가 상한에 걸림 → 마감 임박 예외가 아니라 내일로 미뤄진다 (Task 3 테스트).
- 필수조건에 `<`, `&` 같은 글자 → 메일에서 이스케이프된다 (Task 2 테스트).
- 예전 형식 기록의 다시 알림 카드 → `✅` 줄 · 📍 없이 오류 없이 그려진다 (Task 5 테스트).

---

### Task 1: 본문 구역 나누기 · 필수조건 · 엉터리 거르기 (`analyze`)

**Files:**
- Modify: `jobcatch/summary.py`
- Test: `tests/test_summary.py`

**Interfaces:**
- Produces:
  - `@dataclass class Analysis: duty: str = ""; required: str = ""; tags: list[str] = field(default_factory=list)`
  - `analyze(body: str, extra_tags: list[str]) -> Analysis`
  - `extract_duty(body: str) -> str` (기존 이름 유지), `extract_required(body: str) -> str` (새로)
  - `find_tags`, `group_of`, `page_text` 는 시그니처 그대로

규칙 (테스트가 못 정하는 부분):
- **시작 제목**(업무 · 필수)은 줄 맨 앞(글머리표 · 괄호 · 번호 · 이모지 다음) 이거나 `[ ]` `【 】` `< >` 괄호 안일 때만 인정한다. **끝 제목**은 지금처럼 어디서든 인정한다 (일찍 멈추는 쪽이 안전).
- 끝 제목 목록에 회사 소개(`채용 기업`, `채용기업 소개`, `회사 소개`, `회사소개`, `기업 소개`, `기업소개`)를 더한다.
- 필수 시작 제목: `자격요건`, `자격 요건`, `지원자격`, `지원 자격`, `필수요건`, `필수 요건`, `자격조건`, `자격 조건`, `필수사항`, `필수 사항`, `이런 분을 찾아요`. 필수 구역의 끝: 우대 · 근무조건 · 복리 · 전형 · 접수 · 회사 소개 계열, 또는 업무 시작 제목. 필수 구역 안에서 `우대` 가 들어간 항목은 뺀다. 필수 시작 제목은 업무 구역의 끝 제목이기도 하다 (`STOP_HEADINGS` 에 남긴다).
- 거르기 (업무 · 필수 공통, 항목 단위): 시작 · 끝 제목 말만 있는 항목, `상세내용을 입력하세요` · `내용을 입력하세요` 가 들어간 항목, 한글 · 영문 · 숫자가 2자 미만이거나 `및` `등` `외` 뿐인 항목을 뺀다. 남은 항목을 이은 글의 한글 · 영문 · 숫자가 6자 미만이면 빈 값.
- 자르기: 80자(`MAX_DUTY`, 필수도 같은 값) 안에서 **항목 경계**로 자르고, 하나라도 잘렸으면 끝에 `…`. 첫 항목 하나가 80자를 넘으면 지금처럼 글자 단위로 자르고 `…`.
- 태그: 업무 · 필수 구역 중 하나라도 찾았으면 그 두 구역 글에서만 `find_tags`, 둘 다 없으면 본문 전체.

- [ ] **Step 1: 실패하는 테스트 쓰기** (`tests/test_summary.py` 에 `class AnalyzeTest`)

```python
def test_conjunction_only_is_empty(self):
    self.assertEqual(extract_duty("주요업무 및 자격요건\n- 경력 3년 이상"), "")

def test_company_intro_not_in_duty(self):
    body = "담당업무\n[채용 기업]\n채용기업은 글로벌 상장사(예시)입니다\n자격요건\n- 경력 3년"
    self.assertEqual(extract_duty(body), "")

def test_template_residue_removed(self):
    body = "주요업무\n상세내용을 입력하세요\n- 서버 운영(예시)\n상세내용을 입력하세요\n자격요건\n- 신입"
    self.assertEqual(extract_duty(body), "서버 운영(예시)")

def test_heading_only_items_removed(self):
    body = "주요업무\n담당업무\n- AWS 인프라 구축(예시)\n지원자격\n- 무관"
    self.assertEqual(extract_duty(body), "AWS 인프라 구축(예시)")

def test_mid_sentence_heading_ignored(self):
    body = "회사는 고객이 하는 일까지 함께할 엔지니어를 찾습니다(예시)\n복리후생\n- 식대"
    self.assertEqual(extract_duty(body), "")

def test_required_without_preferred(self):
    body = "주요업무\n- 지그 설계(예시)\n자격요건\n- Creo 3년 이상\n- 우대: 영어 가능\n우대사항\n- 반도체 경험"
    self.assertEqual(extract_required(body), "Creo 3년 이상")

def test_required_before_duty(self):
    body = "[지원자격]\n- 초대졸 이상\n[담당업무]\n- 컨베이어 설계(예시)\n[근무조건]\n- 주5일"
    a = analyze(body, [])
    self.assertEqual(a.required, "초대졸 이상")
    self.assertEqual(a.duty, "컨베이어 설계(예시)")

def test_preferred_only_gives_empty_required(self):
    self.assertEqual(extract_required("주요업무\n- 판금 설계(예시)\n우대사항\n- SolidWorks"), "")

def test_cut_at_item_boundary(self):
    body = "주요업무\n" + "\n".join(f"- 업무{i} " + "가" * 20 for i in range(6)) + "\n자격요건\n- x"
    duty = extract_duty(body)
    self.assertLessEqual(len(duty), 80)
    self.assertTrue(duty.endswith("…"))
    self.assertNotIn("업무5", duty)
    self.assertTrue(duty.split(" / ")[0].startswith("업무0"))

def test_tags_only_from_sections(self):
    body = "회사 소개\nJava Spring React 를 쓰는 여러 팀(예시)\n주요업무\n- 기구 설계\n자격요건\n- Creo 사용"
    self.assertEqual(analyze(body, []).tags, ["Creo"])

def test_tags_whole_body_without_sections(self):
    self.assertEqual(analyze("이미지 위주 공고 Creo(예시)", []).tags, ["Creo"])

def test_empty_body(self):
    self.assertEqual(analyze("", []), Analysis())
```

기존 `DutyTest` · `TagTest` · `GroupTest` 는 그대로 통과해야 한다 (`test_extract_duty_cut` 포함).

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest -q tests/test_summary.py`
Expected: `AnalyzeTest` 가 ImportError 또는 FAIL

- [ ] **Step 3: `summary.py` 구현** — 위 규칙대로 본문을 구역으로 나누는 내부 함수 하나를 두고 `extract_duty` · `extract_required` · `analyze` 가 그것을 쓴다.

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest -q`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add jobcatch/summary.py tests/test_summary.py
git commit -m "본문 구역 나누기: 필수조건 추출 · 엉터리 요약 거르기"
```

---

### Task 2: 카드에 필수조건 줄 · 묶음 안 통근순 정렬

**Files:**
- Modify: `jobcatch/models.py` (Job), `jobcatch/digest.py` (judge 의 요약 부분, ClosingItem, 정렬), `jobcatch/mail.py` (`_card`, `_job_card`, `_closing_card`), `README.md` (세부 묶음과 요약 항목에 필수조건 · 통근순 한 줄)
- Test: `tests/test_digest.py`, `tests/test_mail.py`

**Interfaces:**
- Consumes: `analyze(body, extra_tags) -> Analysis` (Task 1)
- Produces:
  - `Job.required: str = ""`
  - `ClosingItem.required: str = ""` (기존 필드 뒤, 기본값 있음)
  - `_card(..., required: str, ...)` — 📝 줄 다음에 `✅ 필수: {required}`, 비면 줄 없음. 스타일은 📝 줄과 같다.

- [ ] **Step 1: 실패하는 테스트 쓰기**

`tests/test_digest.py`:
```python
def test_detail_fills_required(self):   # SummaryGroupTest
    def details(job_id, today):
        return Detail(address="a", body="주요업무\n- 컨베이어 설계\n자격요건\n- Creo 3년 이상\n우대사항\n- 영어")
    _, new = build(collected(job("1")), config(), {}, TODAY, details={"saramin": details}, sleep=NO_SLEEP)
    self.assertEqual(new[0].required, "Creo 3년 이상")

def test_group_sorted_by_commute(self):   # CommuteTest
    cfg = config(home_address="서울 중구 세종대로 110")
    kakao = FakeKakao({(1.0, 1.0): 50, (1.0, 2.0): 30})
    jobs = [job("1"), job("2"), job("3", location="서울 금천구")]
    details = {"saramin": lambda i, t: Detail(address=f"주소{i}", coords=(1.0, float(i)))}
    d, _ = build(collected(*jobs), cfg, {}, TODAY, details=details, kakao=kakao, sleep=NO_SLEEP)
    self.assertEqual([j.job_id for j in d.new_by_track["설계"]], ["2", "1", "3"])  # 30분, 50분, 모름
```

`tests/test_mail.py` (`HtmlTest`):
```python
def test_required_line(self):
    html = render_html(digest(new_by_track={"설계": [job("1", required="Creo <3년> & 영어")]}, new_total=1))
    self.assertIn("✅ 필수: Creo &lt;3년&gt; &amp; 영어", html)

def test_no_required_line_when_empty(self):
    html = render_html(digest(new_by_track={"설계": [job("1")]}, new_total=1))
    self.assertNotIn("✅", html)
```
(`digest(...)` · `job(...)` 은 `tests/test_mail.py` 의 기존 도우미. 인자 모양이 다르면 도우미에 맞춘다.)

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest -q tests/test_digest.py tests/test_mail.py` → 새 테스트 FAIL

- [ ] **Step 3: 구현**
  - `_Commute.judge`: `extract_duty` / `find_tags` 호출을 `analyze(detail.body, common.extra_tags)` 하나로 바꾸고 `job.summary`, `job.required`, `job.tags` 를 채운다.
  - `build`: 오늘 공고로 만드는 `ClosingItem` 에 `required` 전달. 묶음 안 정렬 키 `(묶음 순서, commute_min 없으면 무한대, deadline or date.max, title)`.
  - `mail._card` 에 `required` 인자, 두 카드 함수에서 전달.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest -q` → 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add jobcatch/models.py jobcatch/digest.py jobcatch/mail.py README.md tests/test_digest.py tests/test_mail.py
git commit -m "카드에 필수조건 줄, 묶음 안 통근 짧은 순 정렬"
```

---

### Task 3: 상세 조회 순서 · 상한 150 · 시간 안전장치 · 내일로 미루기

**Files:**
- Modify: `jobcatch/digest.py` (`_Commute`, `build`, `Digest`), `jobcatch/config.py` (기본값 150 두 곳), `config.example.toml` (`max_detail_lookups = 150`, 주석에 "넘친 공고는 다음 날 다시"), `run.py` (미룸 안내 줄), `README.md` (범위의 "하루 최대 60건" → 150, 넘치면 다음 날)
- Test: `tests/test_digest.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `build(..., clock: Callable[[], float] = time.monotonic)` — 새 키워드 인자 (기존 인자 뒤)
  - `DETAIL_TIME_LIMIT_SEC = 15 * 60` (digest.py 상수)
  - `Digest.deferred: int = 0` — 기존 `unchecked_by_cap` 을 **대체**한다 (이름 바꿈). `run.py` 안내: `참고: 상세 조회 상한으로 {n}건은 내일 다시`
  - `_lookup_order(jobs: list[Job], today: date) -> list[Job]` — 목록 마감일이 오늘~`CLOSING_DAYS` 안인 공고를 원래 순서대로 먼저, 나머지는 갈래별 원래 순서를 유지하며 갈래를 번갈아 한 건씩.

동작:
- `build` 는 `collected.jobs` 를 `_lookup_order` 순서로 처리한다 (출력 순서는 뒤에서 다시 정렬하므로 영향 없음).
- 상한(`lookups >= max_detail_lookups`) 또는 시간(첫 조회부터 `clock()` 경과 ≥ `DETAIL_TIME_LIMIT_SEC`)에 걸린 공고: 마감일을 알고 오늘~7일 안이면 지금처럼 지역 목록 판정. 그 밖(마감일 모름 포함)이면 **미룸** — `kept` 에도, 두 번째 반환값(보낸 기록용)에도, `excluded_after_lookup` 에도 넣지 않고 `deferred` 만 센다. 통근 켜짐 · 꺼짐 두 경로 모두 같다.

- [ ] **Step 1: 실패하는 테스트 쓰기** (`tests/test_digest.py` `CommuteTest`). 기존 `test_lookup_cap` · `test_lookup_cap_counted` 는 아래로 **바꾼다**.

```python
def test_lookup_cap_defers(self):
    details = CountingDetails()
    d, new = build(collected(job("1"), job("2"), job("3")), self.cfg(max_detail_lookups=1), {}, TODAY,
                   details={"saramin": details}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP)
    self.assertEqual(details.calls, ["1"])
    self.assertEqual([j.job_id for j in new], ["1"])
    self.assertEqual(d.deferred, 2)

def test_capped_closing_still_sent(self):
    a = job("1", deadline=TODAY + timedelta(days=3))
    b = job("2", deadline=TODAY + timedelta(days=4))
    d, new = build(collected(a, b), self.cfg(max_detail_lookups=1), {}, TODAY,
                   details={"saramin": CountingDetails()}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP)
    self.assertEqual([(j.job_id, j.commute_min) for j in new], [("1", 30), ("2", None)])  # 2 는 지역 판정
    self.assertEqual(d.deferred, 0)

def test_closing_first_then_defer(self):
    soon = job("2", deadline=TODAY + timedelta(days=3))
    d, new = build(collected(job("1"), soon), self.cfg(max_detail_lookups=1), {}, TODAY,
                   details={"saramin": CountingDetails()}, kakao=FakeKakao({(1.0, 2.0): 30}), sleep=NO_SLEEP)
    self.assertEqual([j.job_id for j in new], ["2"])
    self.assertEqual(d.deferred, 1)

def test_closing_looked_up_first(self):
    details = CountingDetails()
    soon = job("9", deadline=TODAY + timedelta(days=2))
    build(collected(job("1"), job("2"), soon), self.cfg(max_detail_lookups=1), {}, TODAY,
          details={"saramin": details}, kakao=FakeKakao({}), sleep=NO_SLEEP)
    self.assertEqual(details.calls, ["9"])

def test_unknown_deadline_capped_is_deferred(self):
    a = job("1", source="jobkorea", track="개발")
    b = job("2", source="jobkorea", track="개발")
    d, new = build(collected(a, b), self.cfg(max_detail_lookups=1), {}, TODAY,
                   details={"jobkorea": CountingDetails()}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP)
    self.assertEqual([j.job_id for j in new], ["1"])
    self.assertEqual(d.deferred, 1)

def test_tracks_take_turns(self):
    details = CountingDetails()
    jobs = [job("1"), job("2"), job("3"), job("4", track="개발"), job("5", track="개발")]
    build(collected(*jobs), self.cfg(max_detail_lookups=2), {}, TODAY,
          details={"saramin": details}, kakao=FakeKakao({}), sleep=NO_SLEEP)
    self.assertEqual(details.calls, ["1", "4"])

def test_time_guard_defers(self):
    details = CountingDetails()
    d, new = build(collected(job("1"), job("2")), self.cfg(), {}, TODAY,
                   details={"saramin": details}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP,
                   clock=lambda: 901 if details.calls else 0)
    self.assertEqual(details.calls, ["1"])
    self.assertEqual(d.deferred, 1)

def test_no_kakao_cap_defers(self):
    d, new = build(collected(job("1"), job("2")), config(max_detail_lookups=1), {}, TODAY,
                   details={"saramin": CountingDetails()}, kakao=None, sleep=NO_SLEEP)
    self.assertEqual([j.job_id for j in new], ["1"])
    self.assertEqual(d.deferred, 1)
```
(`test_tracks_take_turns` 는 두 갈래 공고 모두 `saramin` 상세로 조회되게 `job("4", track="개발")` 의 source 를 기본값 saramin 으로 둔다.)

`tests/test_config.py`: 설정에 `max_detail_lookups` 가 없을 때 150 인지 확인하는 테스트 하나.

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest -q tests/test_digest.py tests/test_config.py` → 새 테스트 FAIL

- [ ] **Step 3: 구현** — `_Commute.judge` 의 상한 분기를 위 동작으로 바꾸고 `"defer"` 를 돌려준다. `build` 가 `"defer"` 를 받으면 건너뛰고 센다. `clock` 을 `_Commute` 에 넘긴다. `run.py` 의 `unchecked_by_cap` 안내를 `deferred` 로 바꾼다. 설정 · 예시 · README 의 값을 고친다.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest -q` → 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add jobcatch/digest.py jobcatch/config.py config.example.toml run.py README.md tests/test_digest.py tests/test_config.py
git commit -m "상세 조회: 마감 임박 먼저 · 갈래 번갈아 · 상한 150 · 15분 안전장치 · 넘치면 내일 다시"
```

---

### Task 4: 상세 조회 실패 경고 · 실행 로그 건수

**Files:**
- Modify: `jobcatch/digest.py` (`_Commute` 집계, `Digest`), `jobcatch/mail.py` (`render_html` 경고), `run.py` (건수 줄)
- Test: `tests/test_digest.py`, `tests/test_mail.py`, `tests/test_run.py`

**Interfaces:**
- Consumes: Task 3 의 `Digest.deferred`
- Produces:
  - `Digest.detail_read: int = 0` (상세를 받아 온 건수, 실패 제외), `Digest.detail_failed: int = 0`, `Digest.detail_failed_sites: list[str] = []`
  - 실패 = `fetch` 가 예외를 냈거나, 받은 `Detail` 의 `address` · `body` · `coords` 가 모두 비었을 때. 실패한 공고는 지금처럼 지역 목록 판정으로 싣는다 (미루지 않음).
  - 사이트별 시도 ≥ 3 이고 실패 × 2 ≥ 시도이면 `detail_failed_sites` 에 사이트 이름(`saramin` 등).
  - 메일 경고 문구: `⚠ {사이트 이름} 상세 페이지 읽기 실패 — 주소 · 요약 없이 지역 목록으로 걸렀습니다.` (수집 실패 경고 바로 다음)
  - `run.py` 건수 줄 (Task 3 의 `참고: … 내일 다시` 줄을 대체): `상세 읽음 {detail_read} · 상세 실패 {detail_failed} · 요약 {요약 있는 새 공고 수} · 필수조건 {필수조건 있는 새 공고 수} · 내일 다시 {deferred}` (새 공고 = `build` 의 두 번째 반환값)

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
# tests/test_digest.py CommuteTest
def test_detail_failures_warned(self):
    def boom(job_id, today):
        raise RuntimeError("403")
    d, new = build(collected(job("1"), job("2"), job("3")), self.cfg(), {}, TODAY,
                   details={"saramin": boom}, kakao=FakeKakao({}), sleep=NO_SLEEP)
    self.assertEqual(len(new), 3)          # 실패해도 지역 목록으로 실림
    self.assertEqual(d.detail_failed, 3)
    self.assertEqual(d.detail_failed_sites, ["saramin"])

def test_few_failures_not_warned(self):
    calls = []
    def flaky(job_id, today):
        calls.append(job_id)
        if job_id == "1":
            raise RuntimeError("timeout")
        return Detail(address="a", coords=(1.0, 1.0))
    d, _ = build(collected(job("1"), job("2"), job("3")), self.cfg(), {}, TODAY,
                 details={"saramin": flaky}, kakao=FakeKakao({(1.0, 1.0): 30}), sleep=NO_SLEEP)
    self.assertEqual((d.detail_read, d.detail_failed, d.detail_failed_sites), (2, 1, []))
```
```python
# tests/test_mail.py HtmlTest
def test_detail_failed_warning(self):
    html = render_html(digest(detail_failed_sites=["jobkorea"]))
    self.assertIn("잡코리아 상세 페이지 읽기 실패", html)
```
`tests/test_run.py`: dry-run 출력(capture stdout)에 `상세 읽음 ` 과 `내일 다시 ` 가 들어가고, 가짜 공고 제목 글자는 들어가지 않는지 확인하는 테스트 하나 (기존 `RunTest` 의 dry-run 테스트 방식을 따른다).

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest -q tests/test_digest.py tests/test_mail.py tests/test_run.py` → 새 테스트 FAIL

- [ ] **Step 3: 구현** — `_Commute` 에 사이트별 시도 · 실패 수를 세고 `build` 가 `Digest` 에 넣는다. 메일 경고와 `run.py` 건수 줄을 더한다.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest -q` → 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add jobcatch/digest.py jobcatch/mail.py run.py tests/test_digest.py tests/test_mail.py tests/test_run.py
git commit -m "상세 조회 실패 경고와 실행 로그 건수"
```

---

### Task 5: 마감 임박 다시 알림 카드 채우기

**Files:**
- Modify: `jobcatch/history.py` (`Entry`, `_from_json`, `record`, 맨 위 설명), `jobcatch/digest.py` (기록으로 만드는 `ClosingItem`, `_Commute` 에 통근 다시 계산)
- Test: `tests/test_history.py`, `tests/test_digest.py`, `tests/test_mail.py`

**Interfaces:**
- Consumes: `Job.required` (Task 2), `ClosingItem.required` (Task 2)
- Produces:
  - `Entry` 에 기본값 있는 필드 추가 (기존 `excluded` 뒤): `location: str = ""`, `address: str = ""`, `summary: str = ""`, `required: str = ""`, `tags: list[str] = field(default_factory=list)`, `flags: list[str] = field(default_factory=list)`
  - `record()` 가 새 기록을 만들 때 `Job` 의 같은 이름 값을 채운다 (`flags` 는 `j.flags`). `record_excluded()` 는 채우지 않는다.
  - `_from_json` 은 새 키가 없으면 기본값 (예전 형식 호환).
  - `_Commute.minutes_to(address: str) -> int | None`: 통근 켜짐 · 주소 있음일 때만 카카오로 계산, `KakaoUnavailable` 이면 `None` (그때 `failed` 처리는 기존 `judge` 와 같게).
  - 기록으로 만드는 `ClosingItem`: `location`, `address`, `summary`, `required`, `tags`, `flags` 를 `Entry` 에서, `commute_min` 은 `minutes_to(e.address)`.

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
# tests/test_history.py
def test_roundtrip_card_fields_without_commute(self):
    j = job("1", TODAY + timedelta(days=3))
    j.address, j.location, j.summary, j.required = "서울 중구 세종대로 110", "서울 중구", "지그 설계", "Creo 3년"
    j.tags, j.flags, j.commute_min = ["Creo"], ["학력 확인"], 42
    entries = {}
    history.record(entries, [j], TODAY)
    history.save(self.path, entries)
    loaded = history.load(self.path)["saramin:1"]
    self.assertEqual((loaded.address, loaded.summary, loaded.required, loaded.tags, loaded.flags),
                     ("서울 중구 세종대로 110", "지그 설계", "Creo 3년", ["Creo"], ["학력 확인"]))
    self.assertNotIn("42", self.path.read_text(encoding="utf-8"))
    self.assertNotIn("commute", self.path.read_text(encoding="utf-8"))

def test_old_format_loads(self):
    self.path.parent.mkdir(parents=True)
    self.path.write_text(json.dumps({"saramin:1": {
        "title": "t", "company": "c", "url": "u", "source": "saramin", "track": "설계",
        "deadline": None, "first_sent": TODAY.isoformat()}}), encoding="utf-8")
    e = history.load(self.path)["saramin:1"]
    self.assertEqual((e.address, e.summary, e.tags), ("", "", []))
```
```python
# tests/test_digest.py CommuteTest
def test_reminder_card_filled_and_commute_recomputed(self):
    e = Entry("t", "c", "u", "saramin", "설계", TODAY + timedelta(days=3), TODAY - timedelta(days=5),
              address="서울 중구 세종대로 110", location="서울 중구", summary="지그 설계",
              required="Creo 3년", tags=["Creo"], flags=["학력 확인"])
    kakao = FakeKakao({(127.0, 37.0): 45})
    d, _ = build(collected(), self.cfg(), {"saramin:1": e}, TODAY, details={}, kakao=kakao, sleep=NO_SLEEP)
    c = d.closing[0]
    self.assertEqual((c.address, c.summary, c.required, c.tags, c.flags, c.commute_min),
                     ("서울 중구 세종대로 110", "지그 설계", "Creo 3년", ["Creo"], ["학력 확인"], 45))
```
(`FakeKakao.geocode` 는 주소가 있으면 `(127.0, 37.0)` 를 돌려준다.)

```python
# tests/test_mail.py HtmlTest
def test_old_reminder_card_renders_blank(self):
    c = ClosingItem("공고(예시)", "회사", "u", "saramin", "설계", date(2026, 11, 25))
    html = render_html(digest(closing=[c]))
    self.assertNotIn("✅", html)
    self.assertNotIn("📍", html)
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest -q tests/test_history.py tests/test_digest.py tests/test_mail.py` → 새 테스트 FAIL

- [ ] **Step 3: 구현** — 위 Interfaces 대로. `history.py` 맨 위 설명을 "공고 정보와 카드 내용(주소 · 요약 · 필수조건 · 태그 · 확인 표시)을 둔다. 통근 시간은 넣지 않는다" 로 고친다.

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest -q` → 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add jobcatch/history.py jobcatch/digest.py tests/test_history.py tests/test_digest.py tests/test_mail.py
git commit -m "마감 임박 다시 알림 카드에 주소 · 요약 · 필수조건 · 태그 (통근은 다시 계산)"
```

---

### Task 6: 실제 데이터로 확인 (dry-run)

**Files:** 없음 (확인만)

- [ ] **Step 1:** 메인 체크아웃의 `config.toml` 을 이 작업 폴더로 복사해 `python run.py --dry-run` (커밋 금지 · `.gitignore` 확인). 카카오 키가 있으면 환경변수로.
- [ ] **Step 2:** 로그의 건수 줄(상세 읽음 · 요약 · 필수조건 · 내일 다시)과 `output/mail_<날짜>.html` 을 11/23 결과(카드 65장 중 요약 27)와 견주어 사용자에게 보고한다. 공고 제목은 대화에만, 저장소에는 남기지 않는다.
- [ ] **Step 3:** 복사한 `config.toml` 을 지운다.
