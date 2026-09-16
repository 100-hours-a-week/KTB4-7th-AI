# 작업 상태

마지막 갱신: 2026-09-16
브랜치: `feat/6-chat-api` (Issue #6)

## 지금 어디

담당 엔드포인트 4개(예측 제외) 중 마지막인 챗봇까지 구현 완료. 네 브랜치가 전부 `dev`(a69898b)에서
독립적으로 갈라져 있다.

- `feat/1-초기개발환경설정` (#1) — BE 초기환경 정렬 완료, **PR(#3)은 사용자가 계약 협의 위해 보류**.
- `feat/4-solutions-api` (#4) — 구현·커밋 완료, **push 안 함**.
- `feat/5-insights-api` (#5) — 구현·커밋 완료, **push 안 함**.
- `feat/6-chat-api` (#6, 현재 브랜치) — 구현 완료, **커밋 전**.

계약 미확정 상태라 세 기능 API 전부 **위키 기준으로 우선 진행**하기로 사용자와 합의됨(반복 기록).

## 마지막으로 통과한 것

- `doc-digger`로 위키 3개 절 원문 확인: 단계1 §7.4(요청/SSE 응답/에러 표), 단계3 §2.1(agent↔tools
  사이클, **툴 실패 2회 후 실패문구** — 이 규칙은 단계4가 아니라 단계3에 있었음), 단계4 §4(툴 6종
  설계 제약, LangGraph 상태관리). 기존 `app/schemas/chat.py`·`app/prompts/chat_v1.py`와 필드 일치 확인.
- `INTERNAL_API_KEY=test-key uv run pytest -q` — 16 passed
  (`tests/test_chat.py` 5건: 컨텍스트만으로 응답/툴호출후응답/툴2회실패→실패문구/401/422)
- `uv run ruff check --fix . && uv run ruff format .` — 통과
- 서버 실기동 후 curl: 401·422·`/openapi.json` 라우트 노출 확인
- **미검증**: 실제 Claude 호출 경로 전체(`ANTHROPIC_API_KEY` 미설정). LangGraph 에이전트 루프는
  `FakeModel`(고정 응답 큐)로만 검증했다 — 실제 Anthropic 툴콜 포맷과 100% 같다는 보장은 없다.

## 이번 구현에서 의도적으로 단순화한 것 (다음 사람이 알아야 함)

- **토큰 단위 스트리밍이 아니다.** 위키는 "토큰 단위로 스트리밍"을 요구하지만, 지금은
  `app/services/chat/graph.py`의 LangGraph 루프를 `ainvoke`로 끝까지 돌려 완성된 답변을 얻은 뒤
  `app/api/chat.py`에서 40자 단위로 잘라 SSE로 보낸다. TTFB 이득이 없다. 실제 모델 스트리밍
  (`astream` + 콘텐츠 블록 타입으로 tool_use/text 구분)으로 바꾸는 게 다음 개선 과제.
  대신 이 방식 덕에 그래프 실행 중 502/504/500 이 스트림이 열리기 **전에** 일반 HTTP 에러로
  깨끗하게 나간다 — 진짜 토큰 스트리밍으로 바꾸면 이 에러 처리도 다시 설계해야 한다.
- **위키의 `400`(질문 형식 오류)을 따로 구현하지 않았다.** 솔루션·인사이트와 동일하게 Pydantic
  검증 실패는 전부 `422`로 나간다. 위키 챗봇 절만 유일하게 400을 표로 갖고 있는데, 트리거 조건이
  명시돼 있지 않아 임의로 구분하지 않았다.
- **`422`(매출 데이터 없어 컨텍스트 구성 불가)도 구현 안 함.** `context`는 BE가 이미 채워서 보내는
  값이라 AI 쪽에서 이 실패를 판정할 지점이 불명확하다. BE에 트리거 조건 확인 필요.
- evidence는 항상 `null`로 나간다. 어느 청크에 근거를 붙일지의 기준이 위키에 없다.

## 다음 한 걸음

- `feat/6-chat-api` 커밋 (사용자 승인 대기 — 제안: `feat: 챗봇 메시지 API 구현`, `Closes #6`)
- `feat/4`, `feat/5`, `feat/6` 세 브랜치 전부 push·PR 안 됨 — 사용자가 순서·시점 정할 것
- 담당 범위 엔드포인트 4개(solutions/insights/chat 전부, forecast는 헥터 담당) 구현 완료.
  다음은 위 "단순화한 것" 항목 중 토큰 스트리밍 전환이 가장 체감 효과 큼

## 미해결 결정

- Issue #2의 13건(위키 vs 노션 계약 통일) — 기한 9/16(오늘) 지났으나 팀 확정 소식 없음. 사용자가
  승민(BE)과 별도 협의 중. 확정 즉시 `app/schemas/*` · 라우터 prefix · `app/core/errors.py` ·
  `app/clients/backend.py` · `app/services/chat/tools.py`(툴 이름·params) 일괄 수정 필요.
- 챗봇 400/422 트리거 조건 — 위 "단순화" 항목 참고.

## 함정

- `app/core/errors.py`의 `JSONResponse(status, body)` 인자 순서 버그는 `feat/4`·`feat/5`·`feat/6`
  **세 브랜치 모두에서 각자 고쳤다** — 전부 `dev`에서 독립적으로 갈라져서 그렇다. 머지 순서 상관없이
  같은 diff라 충돌 없이 합쳐질 것이다.
- LangGraph `MessagesState`를 상속해 커스텀 필드(`failures: int`)를 추가할 때 리듀서를 따로
  안 걸면 "마지막 쓴 값으로 덮어쓰기"로 동작한다(메시지 리스트만 `add_messages`로 누적). 의도한
  동작이라 문제는 없었지만 다음에 상태 필드를 늘릴 때 리듀서 기본 동작을 헷갈리지 말 것.
- 로컬 8000 포트에 이전 세션의 stale uvicorn 프로세스가 남아있던 적이 있다. curl 검증 전
  `lsof -i :8000`으로 먼저 확인할 것.
