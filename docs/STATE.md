# 작업 상태

마지막 갱신: 2026-09-16
브랜치: `feat/5-insights-api` (Issue #5)

## 지금 어디

세 브랜치가 동시에 떠 있다. 전부 `dev`(a69898b)에서 갈라졌고 서로 독립적이다.

- `feat/1-초기개발환경설정` (Issue #1) — BE 초기환경 정렬 커밋까지 완료, **PR(#3)은 사용자가
  일부러 닫음**. 계약(위키 vs 노션) 문제를 BE(승민)와 먼저 정리하고 싶다고 해서 보류 중.
- `feat/4-solutions-api` (Issue #4) — 솔루션 생성 API 구현·커밋 완료, **아직 push 안 함**.
- `feat/5-insights-api` (Issue #5, 현재 브랜치) — 인사이트 생성 API 구현 완료, **커밋 전** (다음 한 걸음 참고).

계약 미확정 상태라 두 기능 API 모두 **위키 기준으로 우선 진행**하기로 사용자와 합의함.

## 마지막으로 통과한 것

- `doc-digger`로 위키 `[AI] 단계1 §7.3`(인사이트 요청/응답 표) 원문 확인 — 기존
  `app/schemas/insight.py`·`app/prompts/insight_v1.py`와 필드 단위로 전부 일치함을 검증.
  단계4(파이프라인 문서)엔 인사이트 전용 절이 없다 — "인사이트"는 그 문서에서 전부
  `solutions/generate`의 `aiInsight` 필드를 가리키는 다른 개념이었음.
- `INTERNAL_API_KEY=test-key uv run pytest -q` — 16 passed
  (`tests/test_insights.py` 5건: 정상/401/422/INSUFFICIENT_DATA/파싱실패+재시도1회)
- `uv run ruff check --fix . && uv run ruff format .` — 통과, 변경 없음
- 서버 실기동 후 curl: 401·422·`dataDays=13→INSUFFICIENT_DATA(LLM 미호출, 200)`·
  `/openapi.json` 라우트 노출 전부 확인
- **미검증**: 정상 SUCCESS 경로의 실제 Claude 호출 (`ANTHROPIC_API_KEY` 미설정 — monkeypatch로만 검증)

## 다음 한 걸음

- `feat/5-insights-api` 커밋하기 (사용자 승인 대기 중 — 커밋 메시지 제안: `feat: 매출분석 인사이트
  생성 API 구현`, `Closes #5`)
- `feat/4-solutions-api`, `feat/5-insights-api` 둘 다 아직 push·PR 안 함 — 사용자가 각각 언제
  올릴지 정할 것
- 챗봇(`POST /internal/ai/chat/messages`)이 마지막 남은 담당 엔드포인트. `app/prompts/chat_v1.py`만
  있고 서비스·라우터 없음. SSE 스트리밍이라 절차가 다를 수 있어 구현 전에 위키 단계1 §7.4를
  doc-digger로 확인할 것

## 미해결 결정

- Issue #2의 13건(위키 vs 노션 계약 통일) — 기한 9/16(오늘)이었으나 팀 확정 소식 아직 없음.
  사용자가 승민(BE)과 별도 협의 중. **확정되기 전엔 다른 엔드포인트도 위키 기준으로 계속 쌓되,
  확정 즉시 `app/schemas/*` · 라우터 prefix · `app/core/errors.py` · `app/clients/backend.py`
  일괄 수정이 필요함을 잊지 말 것.**

## 함정

- `app/core/errors.py`의 예외 핸들러 3곳이 `JSONResponse(status, body)`로 인자 순서가 뒤집혀
  있던 버그가 있었다(최초 커밋 `2441a31`부터). `feat/4-solutions-api`와 `feat/5-insights-api`
  양쪽 브랜치에서 각자 고쳤다 — **둘 다 dev에서 독립적으로 갈라져서 한쪽만 고치면 안 됐다.**
  나중에 둘 다 머지되면 diff가 겹치지만 내용이 같아 충돌 없이 합쳐질 것이다.
- `llm.py`에 `anthropic.APITimeoutError → 504` 분기도 같은 이유로 두 브랜치에 각각 추가했다.
- 로컬 8000 포트에 이전 세션의 stale uvicorn 프로세스가 남아있던 적이 있다. curl 검증 전
  `lsof -i :8000`으로 먼저 확인할 것.
