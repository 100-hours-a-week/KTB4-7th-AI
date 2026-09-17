# 작업 상태

마지막 갱신: 2026-09-16
브랜치: `feat/21-contract-sync` (Issue #21, `dev` 기준)

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
- **툴 경로**: `hourly-profile`→`hourly-profiles`(복수), `forecast`→`sales/forecasts`,
  `predictedSales`→`predictedSalesAmount`(stub).
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
