# Job-Catch 작업 규칙

## 토큰 규칙 (근거: docs/decisions/2026-11-23-token-diet.md)
- 대화 길이 상한 20만 토큰: `.claude/settings.json` 의 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 로 자동 요약. 결정 · 다음 할 일은 요약 전에 저장소 파일(`docs/superpowers/` 의 계획 · 설계, `docs/decisions/`)에 적는다
- 주제가 바뀌면 새 세션 (예: 새 수집처 추가 · 메일 모양 · 로그 분석은 각자). 메인은 15만 토큰(`get_usage`)을 넘으면 하던 PR 이 끝난 시점에 새 세션으로 넘긴다
- 검증 에이전트: 보통 변경(수집 · 분류 · 메일 내용)은 바뀐 줄만 + `sonnet`. 큰 위험(규칙 · 설정 파일, `.github/workflows`, 보낸 공고 기록 · 메일 발송, 데이터 삭제)은 전체 검증 + `opus`. 분기 세션 모델은 `start_session` 의 `model` 에 직접 적는다 (비우면 메인 모델을 따라감)
- 이 프로젝트에서 안 쓰는 플러그인은 `.claude/settings.json` 의 `enabledPlugins` 에서 꺼 둔다

## 통합문서 트리 등록
- 통합문서: https://claude.ai/artifact/DDgZ1hcfoKXYLdQW461Mcf (탭: 해야할일 · 작업기록 > 날짜 · 자료 > 개발 문서 · 화면 시안)
- 아티팩트(Docs · Design · HTML)를 만들면 작업 끝에 project-artifact-tree 스킬을 쓴다.
- 할 일 상태 옮기기(요청 없이 자동): 개발 시작 때 해야할일 행 → '진행 중', 머지 + 실행 확인 때 '진행 중' 행 → '작업기록 > MM/DD (요일)'.
- 저장소 쪽 진행 문서는 `docs/progress.md`(진행 중 · 해야 할 일 · 검토할 일 · 완료)다. 통합문서와 같은 내용으로 맞춘다.
- 작업이 끝날 때마다 PROGRESS-LOG.md 에 한 줄(날짜 | 작업 | 문제 | 해결 | 결과 | 비고)을 남기고, 통합문서도 갱신한다. 통합문서를 못 열면 비고에 "트리 반영 필요"를 적는다 (다음 채팅이 시작할 때 옮김).
- Claude Docs 를 열 수 없으면 PROGRESS-LOG.md 비고에 "트리 등록 필요: 제목 · 링크 · 탭"을 남기고 사용자에게 알린다.
- 스킬 원본은 계정 스킬 project-artifact-tree. 이 저장소 파일은 사본이다.
