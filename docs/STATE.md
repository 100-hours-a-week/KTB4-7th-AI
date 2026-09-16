# 작업 상태

마지막 갱신: 2026-09-16
브랜치: `feat/4-solutions-api` (Issue #4)

## 지금 어디

초기환경 브랜치(`feat/1-초기개발환경설정`, Issue #1)는 BE 초기환경과 정렬하는 커밋까지 마쳤지만,
계약 미확정 문제를 먼저 정리하고 싶다고 해서 PR(#3)은 일부러 닫아뒀다. 사용자가 BE(승민)와
API 계약 협의 중이며, 정리되는 대로 그 브랜치에 커밋을 더 쌓고 재오픈할 예정.

그 사이 솔루션 생성 API(`POST /internal/ai/solutions/generate`)를 `dev`에서 새로 판
`feat/4-solutions-api`에서 구현 완료. 계약 미확정 상태라 **위키 기준으로 우선 진행**하기로
사용자와 합의함 (기준이 바뀌면 별도 후속 작업).

## 마지막으로 통과한 것

- `doc-digger`로 위키 `[AI] 단계1 §7.2`(요청/응답 표) · `단계4 §3`(파이프라인·프롬프트) 원문 확인 —
  기존 `app/schemas/solution.py`·`app/prompts/solution_v1.py`와 필드 단위로 전부 일치함을 검증
- `INTERNAL_API_KEY=test-key uv run pytest -q` — 15 passed (신규 `tests/test_solutions.py` 4건 포함)
- `uv run ruff check --fix . && uv run ruff format .` — 통과, 변경 없음
- 서버 실기동 후 curl:
  - 인증 헤더 없음 → 401 `{"success":false,"error":{"code":"UNAUTHORIZED",...}}`
  - 필수 필드 누락 → 422 `{"success":false,"error":{"code":"VALIDATION_ERROR",...}}`
  - `/openapi.json`에 `/internal/ai/solutions/generate` 노출 확인
- **미검증**: 정상 200 경로의 실제 Claude 호출 (`ANTHROPIC_API_KEY` 미설정 — pytest에서는 `llm.complete` monkeypatch로만 검증)

## 다음 한 걸음

- `feat/4-solutions-api` → `dev` PR 올리기 (Issue #4, `Closes #4`) — 아직 안 올림, 사용자 승인 필요
- 인사이트 생성 API(`POST /internal/ai/insights/generate`)를 같은 절차(`ai-endpoint` 스킬)로 진행.
  `app/schemas/insight.py`·`app/prompts/insight_v1.py`는 이미 있음
- 챗봇은 `app/prompts/chat_v1.py`만 있고 서비스·라우터 없음. SSE 스트리밍이라 절차가 다를 수 있어
  구현 전에 위키 단계1 §7.4·단계4 챗봇 절을 doc-digger로 다시 확인할 것

## 미해결 결정

- Issue #2의 13건(위키 vs 노션 계약 통일) — 기한 9/16(오늘)이었으나 팀 확정 소식 아직 없음.
  사용자가 승민(BE)과 별도 협의 중. **확정되기 전엔 다른 엔드포인트도 위키 기준으로 계속 쌓되,
  확정 즉시 `app/schemas/*` · 라우터 prefix · `app/core/errors.py` · `app/clients/backend.py`
  일괄 수정이 필요함을 잊지 말 것.**

## 함정

- `app/core/errors.py`의 세 예외 핸들러가 `JSONResponse(status, body)` 순서로 인자가 뒤집혀 있던
  버그를 이번에 발견해 고쳤다(최초 커밋 `2441a31`부터 있었음 — 이 경로를 실제로 타는 테스트가
  지금까지 없어서 안 걸렸다). 팀에 알릴 것.
- `llm.py`에 `anthropic.APITimeoutError → 504` 분기를 추가했다(위키 §7.2 오류표에 504가 명시됨).
  502/504 둘 다 monkeypatch로만 검증했고 실제 타임아웃 재현은 안 해봤다.
- 로컬 8000 포트에 **이전 세션이 띄워둔 stale uvicorn 프로세스**가 두 개 떠 있었다(구 코드로 계속
  응답 중이었음). curl로 새 라우트 검증할 땐 반드시 `lsof -i :8000`으로 먼저 확인할 것.
