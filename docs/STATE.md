# 작업 상태

마지막 갱신: 2026-09-20
브랜치: `feat/48-chat-token-streaming-evidence` (Issue #48, `dev` 기준)

## 2026-09-20 후속 — 실패를 error 이벤트로 구조화 (BE 확인 완료)

09-19에 만든 in-stream 실패 문구가 그냥 평문 텍스트라 BE/FE가 성공 답변과 구분하려면 문자열
파싱을 해야 하는 문제가 있었다. 사용자 지적으로 구조화된 `error` 이벤트로 바꿨다:

- `{"event":"error","data":{"code":"AI_TIMEOUT"|"AI_GENERATION_ERROR"|"AI_TOOL_ERROR",
  "message":"..."}}` — 기존 `{"event":"answerChunk",...}`과 같은 `data: ...\n\n` SSE 라인
  안에 JSON으로 실어 보낸다(진짜 SSE `event:` 필드로 바꾼 게 아님 — 계약의 기존 전송 방식을
  그대로 유지하면서 최소 변경으로 판단, **BE 확인 완료(2026-09-20)**).
  - `AI_TIMEOUT`(504였던 것) / `AI_GENERATION_ERROR`(원래 502였는데 `docs/api정의서.md:1163`엔
    500만 문서화돼 있어서 500으로 맞춤) — `app/services/chat/graph.py`의 `_stream_model`.
  - `AI_TOOL_ERROR` — 도구 조회 2회 연속 실패. 기존엔 `FAILURE_PHRASE`를 정상 답변인 것처럼
    `answerChunk`로 보냈는데, ERD `chat_messages.status`에 이미 `FAILED` 값이 있어서 error
    이벤트로 보내는 게 더 맞다고 판단해 바꿨다.
- **BE 확인 완료(2026-09-20, Issue #48 코멘트로 전달 후 BE 회신 받음)**:
  1. 기존 `answerChunk` 형식은 그대로 유지, `error` 이벤트만 추가되는 구조로 BE가 그대로 수용함.
  2. `event:"error"` 수신 시 `chat_messages.status=FAILED`로 처리하기로 합의됨 — BE가 직접 이
     매핑을 구현한다.
  3. 실제 SSE `event:` 필드 변경은 없음(계속 `data:` 줄 안에 JSON으로 실어 보내는 기존 방식
     유지) — BE도 이 전제로 확인함.
  4. 문서(`docs/api정의서.md`)의 504/500 기술은 아직 BE 쪽 노션 반영 전이라 남아있을 수 있음 —
     반영 여부는 다음에 문서 동기화할 때 확인.

## 2026-09-19 세션 — 챗봇 토큰 스트리밍 + evidence 구현

코드 감사 중 발견한 두 가지를 고쳤다 (Issue #48):

- **진짜 토큰 단위 SSE 스트리밍**: 기존엔 `app/api/chat.py`가 LangGraph를 `ainvoke`로 끝까지
  돌려 완성된 답변을 40자씩 잘라 흉내만 냈다(`docs/api정의서.md:1149` "토큰 단위로 스트리밍
  반환한다" 위반). `app/services/chat/graph.py`의 `agent_node`가 `model.astream(messages,
  config=config)`로 실제 토큰을 받고, `app/api/chat.py`는 `compiled.astream_events(...,
  version="v2")`로 `langgraph_node=="agent"`인 `on_chat_model_stream` 이벤트만 걸러 실시간
  중계한다. 도구 호출 결정 턴은 보통 빈 content만 스트리밍하므로 `if chunk.content`로
  자연히 걸러진다.
  - **트레이드오프**: `StreamingResponse`는 반환되는 순간 200 헤더를 먼저 보내므로(Starlette
    `stream_response` 확인 완료), 스트리밍이 시작된 뒤엔 502/504로 격상할 수 없다. 모델 호출
    실패(`APITimeoutError`/`AnthropicError`)는 이제 in-stream 실패 문구로만 내려간다
    (`app/api/chat.py`의 `_stream` 안 `except ApiError`). 기존엔 `ainvoke`를 먼저 끝까지
    기다려서 실패를 깨끗한 HTTP 상태로 반환했었는데, 진짜 스트리밍과는 근본적으로 양립할 수
    없는 속성이라 포기했다 — 모든 실시간 스트리밍 챗 API가 겪는 제약이다.
- **evidence 근거값 채우기**: `app/api/chat.py`가 모든 청크에 `evidence: null`을 하드코딩하고
  있었다(`docs/api정의서.md:1175` "서버 산출값과 반드시 일치해야 함" — 환각 검증 장치인데
  미구현). `app/services/chat/graph.py`의 `tools_node`가 도구 조회 성공마다
  `_build_evidence(tool_name, args, result)`로 `last_evidence`를 갱신하고, API 레이어가 다음
  답변 청크마다 함께 실어 보낸다. `get_sales_summary`→`changeRate`, `get_forecast`→가장 가까운
  `predictedSalesAmount`만 단일 값(`value`)으로 채우고, `get_category_breakdown`/
  `get_hourly_profile`처럼 리스트형 응답은 `metric`/`period`만 채우고 `value`는 null이다
  (여러 항목 중 어떤 수치를 답변이 인용했는지 지금은 모델이 알려주지 않아서 특정할 수 없음
  — **알려진 한계**, 업그레이드하려면 모델이 구조화된 출력으로 어떤 값을 인용했는지 직접
  표시하게 해야 함).
- `tests/test_chat.py`의 `FakeModel`을 `.ainvoke`만 흉내내던 가짜 객체에서 `BaseChatModel`을
  상속한 진짜 스트리밍 가짜 모델로 바꿨다(`_astream`으로 텍스트는 공백 단위 여러 청크, 툴
  호출은 빈 content 한 청크). 새 테스트 2개 추가: 토큰이 여러 청크로 오는지, evidence가
  도구 사용 여부에 따라 채워지는지.
- `uv run pytest -q`: 40 passed. `uv run ruff check . / ruff format .`: 통과.
- **미검증**: 실제 Anthropic API 스트리밍(로컬엔 `ANTHROPIC_API_KEY` 없음) — `GenericFakeChatModel`로
  LangGraph `astream_events`가 `on_chat_model_stream`을 정상 발생시키는 것만 별도 스크립트로
  확인했다. 실서비스 키로 curl 스모크 테스트 필요.

## 지금 어디

BE와 최종 합의한 계약(`docs/api정의서.md`, `docs/ERD정의서.md` — 사용자가 직접 붙여넣음)을
solutions/insights/chat 코드에 반영했다. `docs/contract-diff-wiki-vs-notion.md`(이전 세션이 작성한
요약본)는 일부 항목이 실제 API 정의서와 달라서(§3 rank/aiInsight, §4 요청·응답 구조) **참고용으로만
쓰고 원본 파일을 기준으로 다시 확인하며 작업했다.**

Notion 직접 조회는 이 세션의 연동 계정(`woheee@gmail.com` 개인 워크스페이스)이 BE가 보는 팀
워크스페이스 페이지(`3d57f3fa…`, `3d07f3fa…`)에 접근할 수 없어서 실패했다 — 사용자가 `docs/`에
`api정의서.md`·`ERD정의서.md`를 직접 복사해 넣어줘서 그걸로 대조했다.

## 이번에 반영한 것

- **공통 에러 포맷**: `{"success":false,"error":{code,message,traceId}}` → `{"message":"...","data":null}`
  (+ 특정 상황에만 `failReason`). `app/core/errors.py`의 `ApiError`에 `fail_reason` 옵션 추가
  (기존 호출부는 안 건드림 — 위치 인자라 하위호환). `data:null`은 2026-09-17에 추가 — API 정의서
  67번 줄 전역 규칙("실패 응답은 기본적으로 `{"message":...,"data":null}`")과 문서 전체 40여 개
  실제 예시로 확인, `_body()`에 빠져 있던 걸 헥터가 지적해서 반영했다.
- **서버 간 인증 삭제**: solutions/insights/chat 라우터에서 `Depends(verify_internal_key)` 제거.
  `app/core/auth.py` 자체는 `forecast.py`가 아직 쓰고 있어서 남겨둠 — **헥터도 지워야 완전히 끝남.**
- **라우터 prefix**: `/internal/ai` → `/internal/v1/ai` (solutions/insights/chat).
  ⚠️ **`app/api/forecast.py`는 아직 `/internal/ai/forecast/batch`로 v1이 안 붙어있다** —
  헥터에게 알릴 것 (방금 사용자가 `/internal/v1/ai/forecast/batch`로 확정한다고 확인해줌).
- **비율 표기**: 한때 소수(0.62)→정수 퍼센트(62)로 바꿨었는데, 2026-09-17 API 정의서 재확인 +
  BE 확인 결과 **소수가 맞는 것으로 원복**했다(`app/schemas/common.py`의
  `SalesSummary.vsPrevPeriod`, `CategoryPoint.share/vsPrevPeriod`, `devtools/stub_backend.py`,
  테스트 픽스처 3곳). 금액(`netSales`/`amount`)·시간(`hour`)은 그대로 `int`.
- **솔루션 생성** (`POST /internal/v1/ai/solutions/generate`):
  - `context`(dayOfWeek/isWeekend/dataBasisPeriod) 요청 필드 삭제 — 서비스가 `targetDate`로
    요일·주말 여부를 코드로 계산한다(달력 계산이라 환각 위험 없음).
  - 카드 필드 `rank`→`rankNo`, `detailContent`→`detailText`, `summaryText` 신규 추가.
  - 최상위 `aiInsight` 삭제 — 매출 AI 인사이트는 별도 엔드포인트 담당.
  - `evidence` 필드 삭제 — ERD `solutions` 테이블에 evidence 컬럼이 없음(확인 완료).
  - 응답이 `{"message":...,"data":{...}}` 래퍼로 변경.
  - `salesAnalysisId`는 `SCHEDULED` 트리거일 땐 안 온다 — Optional로 변경.
  - 프롬프트 `solution_v2.py` 신규(파일명=`promptVersion` 규칙, v1은 이력으로 남김).
- **매출분석 인사이트**: 경로가 `/internal/ai/insights/generate` → `/internal/v1/ai/sales-insights`로
  완전히 바뀜. 요청도 `uploadId`/`dataDays` → `salesAnalysisId`/`targetMonth`/`triggerType`/
  `maxInsightCount`로 전면 교체. 응답도 `insights[]`(객체+evidence) → `data.insights`(문자열 배열)로
  단순화. 14일 게이트는 BE가 호출 전에 판단하므로(`dataDays` 자체가 요청에 없음) AI 쪽 게이트 로직은
  전부 제거했다 — `INSUFFICIENT_DATA` 상태값은 스키마엔 있지만 서비스는 항상 `COMPLETED`만 반환한다.
  프롬프트 `insight_v2.py` 신규.
- **챗봇**: SSE 청크를 `{"answerChunk":...,"evidence":...}` 플랫 → `{"event":"answerChunk","data":
  {"content":...,"evidence":...}}` 중첩으로 변경. `question` 길이 검증(`max_length=300`) 제거 — BE가
  이미 검증하므로 AI는 재검증하지 않는다.
- **챗봇 `history[].role` 대문자로 변경** (2026-09-17): `Literal["user","assistant"]` →
  `Literal["USER","ASSISTANT"]`. API 정의서 1088번 줄 GET 메시지 목록 응답 예시가 DB 값 그대로
  `"role":"USER"`를 보여줌 — `history`도 같은 DB 컬럼에서 나오므로 동일 표기로 판단했다.
  `app/api/chat.py`의 `role_map`도 같이 대문자로 맞췄다.
- **챗봇 `context` 필드 전면 재정의** (2026-09-17): `{type: Literal["SOLUTION_SUMMARY"|...],
  content: str}` 스키마는 실제 계약 어디에도 근거가 없었다(`SOLUTION_SUMMARY` 등 문자열이
  api정의서·ERD정의서·contract-diff 문서 전부에 0건). API 정의서 1135번 줄 "context(필수 —
  SOL-02 전체 내용: 카드별 rank/title/detail)" 기준으로 SOL-02 실제 응답 모양(964번 줄
  `items:[{rankNo,title,summaryText,detailText,evidence}]`)을 그대로 재사용해
  `context: list[ChatContextCard]`로 교체했다(사용자 확인 완료 — evidence 포함).
  `app/prompts/chat.py`의 `build_system`도 `(context_type, context_content)` 두 문자열 인자 대신
  카드 리스트 하나를 받아 `json.dumps`로 넘기도록 변경(솔루션 프롬프트와 동일한 패턴).
- **툴 경로**: `hourly-profile`→`hourly-profiles`(복수), `forecast`→`sales/forecasts`,
  `predictedSales`→`predictedSalesAmount`(stub).
- **챗봇 툴 파라미터 보강** (2026-09-17): API 정의서 25~27번 줄 기준으로 4종 툴에 빠진 파라미터를
  추가했다.
  - `get_sales_summary`/`get_category_breakdown`: `startDate`/`endDate`(선택, `period=CUSTOM`일 때
    BE가 필수로 검증) 추가.
  - `get_hourly_profile`: 위 두 개 + `dayOfWeek`(선택) 추가.
  - `get_forecast`: 원래 파라미터가 아예 없었는데, 명세상 `period`가 아니라 `targetDate`(선택,
    YYYY-MM-DD)를 받는다 — 시그니처를 통째로 교체했다.
  - `app/clients/backend.py`의 `call_tool`이 `None` 값 파라미터를 쿼리에서 제거하도록 수정
    (httpx가 `None`을 빈 문자열로 직렬화해서 `?targetDate=`가 나가는 걸 막음).
- **스텁 필드명 정정** (2026-09-17): `devtools/stub_backend.py`가 세 개 툴 응답에서 실제 명세와
  다른 필드명을 쓰고 있었다 — API 정의서 706/738/769번 줄 리터럴 예시로 확인.
  - `get_sales_summary`: `netSales` → `totalSales`
  - `get_category_breakdown`: `categories[].netSales`/`menuRankings[].netSales` → `menuSales`
  - `get_hourly_profile`: `hourlyProfiles[].netSales` → `menuSales`
  - `get_profit`(`netSales` 그대로)·`get_forecast`는 명세와 이미 일치해서 안 건드림.
  - `tests/test_backend_client.py`·`tests/test_chat.py`의 관련 픽스처도 같이 맞췄다.
  - (참고) 이 필드들은 챗봇 전용 조회 툴 응답이라 예측 모델과 무관하다 — 예측 모델
    (`app/services/forecast/`, 헥터 담당)은 `dailySales[].amount`(일별 합계) 하나만 쓰고
    메뉴·카테고리·시간대 세부 데이터는 아예 요구하지 않는다(코드로 확인 완료).
- **프롬프트 버전 표기를 날짜식으로 전환, `promptVersion` 응답 필드 삭제** (2026-09-17):
  `VERSION="v1"/"v2"`가 API 배포 버전(`/internal/v1/ai/...`)과 헷갈린다는 지적으로
  `VERSION="2026-09-17"` 형태로 세 프롬프트 파일(`solution.py`/`insight.py`/`chat.py`) 전부
  변경. 동시에 솔루션 응답의 `promptVersion` 필드 자체를 삭제했다(`app/schemas/solution.py`,
  `app/services/solution.py`) — `VERSION` 상수는 이제 응답에 노출되지 않는 순수 내부 값이다.
  `docs/api정의서.md` 580/610번 줄은 아직 `promptVersion`을 필수 응답 필드로 보여주지만,
  BE와 확인 결과 **필드 삭제로 최종 합의**했다(2026-09-17, Issue #39) — 문서는 BE가 갱신 예정.
- 기존 테스트(`test_solutions.py`/`test_insights.py`/`test_chat.py`) 전부 새 계약으로 재작성.
  401 테스트는 "인증 없어도 통과" 테스트로 대체.

## 마지막으로 통과한 것

- `uv run pytest -q` — 34 passed
- `uv run ruff check --fix . && uv run ruff format .` — 통과
- 서버 실기동 후 curl: 3개 라우트(`solutions/generate`, `sales-insights`, `chat/messages`) 전부
  새 경로로 노출, 422 응답이 새 플랫 포맷(`{"message":...}`)인지 확인
- **미검증**: 실제 Claude 호출 (여전히 `ANTHROPIC_API_KEY` 없음, monkeypatch로만 검증)

## 다음 한 걸음

- 커밋 승인 대기 (`feat/21-contract-sync`, Issue #21)
- **헥터에게 알릴 것**: (1) `forecast.py` 라우터 prefix에 `/v1` 누락, (2) `verify_internal_key`
  삭제 결정이 `forecast.py`에도 적용되는지, (3) `Metrics`에 순이익 필드가 없어 BE가 solutions
  요청에 순이익 지표를 넣어 보내도 `extra="ignore"`때문에 조용히 버려짐(설계 원칙 문서엔 "순이익·리뷰
  요약"도 metrics에 포함된다고 돼 있음 — 실제로 필요한 시점에 필드 추가 필요)

## 미해결 결정

- **챗봇 데이터 부족 처리**: 사용자가 "예측·인사이트·챗봇 모두 200+`status:INSUFFICIENT_DATA`+
  `data.missingData`로 통일"이라고 확정했다. 챗봇은 이 상태를 코드에서 판단할 명확한 트리거가
  없어서 아직 구현하지 않았다 — 지금은 LLM이 시스템 프롬프트 지시("데이터가 부족하면 부족하다고
  말하세요")로 자연어로만 표현한다. 언제 이 상태를 코드로 판정할지 BE와 조건 정의 필요.
- **솔루션 metrics의 순이익/리뷰 요약**: 설계 설명엔 포함된다고 돼 있는데 스키마에 필드가 없다(위 참고).
- **인사이트 metrics의 정확한 MENU 전용 필드명**: "menu_net_amount와 MENU 전용 일별·요일별·
  시간대별·카테고리별 지표"라는 서술만 있고 리터럴 JSON 예시가 없다. BE 확인 필요.

## 설계상 확정된 사실 (미해결 아님 — 혼동 방지용)

- **인사이트는 항상 `status: COMPLETED`만 반환한다.** 스키마엔 `COMPLETED | INSUFFICIENT_DATA`
  둘 다 있지만, 데이터 부족(14일 미만) 판단은 **BE가 호출 전에** 한다 — 요청에 `dataDays` 자체가
  없어서 AI는 판단할 신호가 없다. `INSUFFICIENT_DATA`는 계약상 값 존재만 보장하는 자리이고,
  `app/services/insight.py`가 이 상태를 만들 일은 설계상 없다. 나중에 "왜 여기 게이트가 없지?"
  하고 다시 파고들지 않도록 기록해 둔다.

## 함정

- Notion 연동 워크스페이스가 개인 계정이라 팀 공유 페이지에 접근이 안 된다 — 이번처럼 사용자가
  `docs/`에 파일로 복사해 넣어주는 방식이 제일 빠르다.
- `app/core/errors.py`의 `JSONResponse` 인자 순서 버그는 이번에 포맷을 아예 새로 짜면서 같이
  정리됐다(과거 세 브랜치가 각자 고쳤던 그 버그).
- 로컬 8000 포트에 stale uvicorn이 남는 경우가 잦다 — curl 검증 전 `lsof -i :8000` 확인 습관화.
