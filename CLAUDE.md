@AGENTS.md

## Claude Code 전용

- 스킬: `.claude/skills/` — `ai-endpoint`(엔드포인트 추가 절차), `handoff`(세션 인계),
  `feature-branch`(브랜치 파기 전 Issue 생성·PR `Closes #` 절차 — 새 브랜치 만들기 전 필수 확인)
- 서브에이전트: `.claude/agents/doc-digger.md` — 위키·노션에서 필요한 절만 발췌해 온다.
  팀 문서는 양이 커서 메인 세션에서 직접 읽지 않는다.
- 세션을 시작하면 `docs/STATE.md` 부터 읽는다. 위키를 처음부터 다시 훑지 않는다.
