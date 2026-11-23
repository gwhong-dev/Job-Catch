# Job-Catch 작업 규칙

## 토큰 규칙 (근거: docs/decisions/2026-11-23-token-diet.md)
- 대화 길이 상한 20만 토큰: `.claude/settings.json` 의 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 로 자동 요약. 결정 · 다음 할 일은 요약 전에 저장소 파일(`docs/superpowers/` 의 계획 · 설계, `docs/decisions/`)에 적는다
- 주제가 바뀌면 새 세션 (예: 새 수집처 추가 · 메일 모양 · 로그 분석은 각자). 메인은 15만 토큰(`get_usage`)을 넘으면 하던 PR 이 끝난 시점에 새 세션으로 넘긴다
- 검증 에이전트: 보통 변경(수집 · 분류 · 메일 내용)은 바뀐 줄만 + `sonnet`. 큰 위험(규칙 · 설정 파일, `.github/workflows`, 보낸 공고 기록 · 메일 발송, 데이터 삭제)은 전체 검증 + `opus`. 분기 세션 모델은 `start_session` 의 `model` 에 직접 적는다 (비우면 메인 모델을 따라감)
- 이 프로젝트에서 안 쓰는 플러그인은 `.claude/settings.json` 의 `enabledPlugins` 에서 꺼 둔다
