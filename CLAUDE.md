@AGENTS.md

## Claude Code 전용

- 스킬: `.claude/skills/` — `ai-endpoint`(엔드포인트 추가 절차), `handoff`(세션 인계),
  `feature-branch`(브랜치·PR 절차 — **생성/삭제/머지는 항상 사용자 확인 후에만 실행**)
- 서브에이전트: `.claude/agents/doc-digger.md` — 위키·노션에서 필요한 절만 발췌해 온다.
  팀 문서는 양이 커서 메인 세션에서 직접 읽지 않는다.
- 세션을 시작하면 `docs/STATE.md` 부터 읽는다. 위키를 처음부터 다시 훑지 않는다.
- 커밋 메시지·PR 본문·이슈 본문 어디에도 `Co-Authored-By: Claude ...` 트레일러나
  "Generated with Claude Code" 류의 생성 배너를 넣지 않는다 (2026-10-12 결정,
  2026-10-13 PR 본문까지 범위 확대 — 세션 시작 때 한 번 읽고 끝내지 말고 커밋·PR
  작성 직전에 다시 확인한다. 과거 실제로 이 규칙이 있는 채로 어겨진 적이 있다).
