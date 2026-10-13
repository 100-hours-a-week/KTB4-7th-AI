@AGENTS.md

## Claude Code 전용

- 스킬: `.claude/skills/` — `ai-endpoint`(엔드포인트 추가 절차), `handoff`(세션 인계),
  `feature-branch`(브랜치·PR 절차 — **생성/삭제/머지는 항상 사용자 확인 후에만 실행**),
  `notion-contract`(API·ERD 정의서를 노션에서 직접 조회 — 로컬 사본 없음, 2026-10-13부)
- 서브에이전트: `.claude/agents/doc-digger.md` — 위키·노션에서 필요한 절만 발췌해 온다.
  팀 문서는 양이 커서 메인 세션에서 직접 읽지 않는다.
- 세션을 시작하면 `docs/STATE.md` 부터 읽는다. 위키를 처음부터 다시 훑지 않는다.
- 커밋 메시지에 `Co-Authored-By: Claude ...` 트레일러를 넣지 않는다 (2026-10-12 결정).
