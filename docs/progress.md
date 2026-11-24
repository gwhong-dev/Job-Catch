# Job-Catch 진행 문서

새 세션은 이 문서 상단(진행 중 · 해야 할 일)만 읽고 이어서 한다.

## 진행 중

- 운영 안전장치 PR (브랜치 `claude/ops-guards-4e1bf8`)
  - (4) 조용한 실패 경고: 카카오 키는 있는데 집 주소가 비면 로그 경고 + 메일 맨 위 경고 상자
  - (5) AI 실패 원인 로그: 실패를 원인별 건수로 (HTTP 상태 코드 · 시간 초과 · 연결 실패 · 응답 형식 오류 · 기타)
  - (1) 하루 한 번만 발송: 그날(KST) 발송 성공 기록이 있으면 수집도 하지 않고 건너뜀, 손 실행은 `force` 로 다시 보냄

## 해야 할 일

- B 외부 예약 (사용자 보류, 비용 없음 확인됨): cron-job.org 가 06:30 KST(시간대 Asia/Seoul)에 `workflow_dispatch` 호출.
  이 저장소 Actions 쓰기 권한만 가진 fine-grained 토큰, 토큰 만료 알림 장치 필요
- A 예약 시각을 정각이 아닌 분으로 당기기 (B 와 함께)

## 검토할 일

- 로컬 `config.toml` ↔ Secret `JOBCATCH_CONFIG` 동기화. 고치면:
  `Get-Content C:\dev\Job-Catch\config.toml -Raw | gh secret set JOBCATCH_CONFIG --repo gwhong-dev/Job-Catch`
- 사람인 수집 실패 경고 (GitHub 서버에서 240→160건): 며칠 지켜보기
- 적합도 '하' 공고 거르기 · 아래로 내리기: 며칠 메일 보고 결정
- `max_detail_lookups` 60 vs 예시 150
- PR #6 검증의 남은 작은 문제: temperature 0, 이미지 stream 없이 받기, data-src 지연 로딩 이미지, 기록 fit null→"None"

## 완료

- PR #6: Gemini AI 요약 · 필수조건 · 🎯 적합도
