# 작업 상태

마지막 갱신: 2026-09-23
브랜치: `dev` (아래 PR 전부 머지 완료)

## 지금 어디

**MVP 범위의 엔드포인트 4종이 모두 구현·머지됐고, 계약은 노션 기준으로 확정됐다.**
SALES 인사이트는 2026-09-22 에 풀스택 확정 계약까지 반영을 마쳤다.
**남은 건 코드가 아니라 연동 검증과 배포다** — 아래 "다음 한 걸음" 참고.

검증 현황: 예측은 BE 실제 데이터로 62/62일 일치, 솔루션·인사이트·챗봇은 승민 실제 요청
샘플로 실호출 200 확인. **다만 챗봇이 부르는 BE 조회 API 4종만 아직 스텁뿐이다.**

아래 "이번에 반영한 것"은 2026-09-16~17 계약 동기화 세션의 기록이다. 그 이후 작업은
날짜별 절("2026-09-17~21", "2026-09-21 오후", "2026-09-22", "2026-09-22 오후")에 적었다.

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
  `app/core/auth.py` 자체는 `forecast.py`가 아직 쓰고 있어서 남겨둠.
  → **완료(2026-09-17, PR #8).** `forecast.py`에서도 제거했다. 인바운드를 BE로만 제한하는
  보안 그룹이 경계다. AI → BE 툴 호출에도 `X-Internal-Api-Key` 를 쓰지 않는다 —
  `app/clients/backend.py` 의 `call_tool` 은 인증 헤더를 보내지 않는다(2026-09-21 확인).
- **라우터 prefix**: `/internal/ai` → `/internal/v1/ai` (solutions/insights/chat).
  `app/api/forecast.py`도 `/internal/v1/ai/forecast/batch`로 맞췄다 → **완료(2026-09-17, PR #8).**
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
    → **2026-09-21 뒤집힘.** AI가 생성하는 것으로 확정. 아래 "2026-09-21 결정" 참고.
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

## 2026-09-17~21 (헥터, 예측 파트)

- **80% 예측구간 추가** (PR #36): `app/services/forecast/intervals.py` 신설. 매장별 백테스트
  잔차 분위수로 `lowerBound`/`upperBound`를 만든다. **신뢰구간이 아니라 예측구간이다** —
  "다음에 실제로 찍힐 값이 이 범위에 들어올 확률 80%"라는 뜻.
  - 누수 없는 백테스트(분위수를 평가 시점보다 **엄격히 이전** 원점에서만 뽑음)로 검증:
    목표 80% → **실측 80.0%**, 목표 90% → 90.3%.
  - 잔차 왜도가 +1.18이라 **구간이 비대칭이다**(−17% / +25%). 의도한 것이다.
  - ⚠️ **일별 구간을 더해서 기간 구간을 만들면 안 된다** — 약 1.5배 과대평가된다.
    기간 단위가 필요하면 별도로 산출해야 한다.
  - 표본이 매장 한 곳(267일)이라 `DEFAULT_QUANTILES`는 잠정치다. 데이터가 늘면 재측정한다.
  - `_incomplete_months`를 `features.py`의 공개 `incomplete_months()`로 옮겼다
    (`service.py`·`intervals.py` 양쪽에서 쓰는데 순환 import가 나서).
- **`modelVersion`을 날짜형으로 변경** (PR #29): `ridge_v2` → `ridge-2026-09-16`.
  팀의 릴리스 버전(v1 MVP / v2 순이익 / v3 리뷰)과 헷갈리지 않고, 문자열 정렬만으로
  최신 버전이 나와 BE가 최신 예측을 고르기 쉽다. 프롬프트 `VERSION` 상수와 같은 규칙이다.
- **ERD 사본 금액 타입 갱신** (PR #33): `predicted_sales_amount`를 `BIGINT UNSIGNED`로.
  이후 BE가 `lower_bound`/`upper_bound`와 `UNIQUE (store_id, target_date)`,
  `CHECK (lower_bound <= predicted_sales_amount <= upper_bound)`를 반영했다.
- **AGENTS.md 계약 기준을 노션으로 갱신** (PR #31): 금액·개수는 정수 / 비율·증감률은 소수
  규칙을 명문화했다. 이 표기가 두 번 뒤집혔던 적이 있어서 규칙으로 못 박았다.
- **ARCHITECTURE.md에 예측 파이프라인 추가** (PR #38): §4.6 "예측은 LLM을 쓰지 않는다".
- **`devtools/interval_backtest.py` 신설**: 예측구간 커버리지 재측정용.
- **`devtools/forecast_check.py` 수정**: 새 경로·api-key 제거 반영, `lowerBound`/`upperBound`
  검사와 `failReason` 검증 추가. 결측 시나리오가 92일짜리 파일에서 아무것도 안 지우고
  통과하던 버그도 고쳤다(인덱스를 `len(rows)//2`로 변경).

## 2026-09-21 결정 (evidence 3종)

`evidence`는 세 군데에 나오는데 형태도 목적도 다르다. 혼동이 반복돼서 여기 고정한다.

| | 형태 | 화면 노출 | 용도 | 상태 |
|---|---|---|---|---|
| 챗봇 | 구조화 객체 `{metric, period, value}` | ❌ | 답변 수치가 서버 산출값과 같은지 검증 | ✅ 구현 완료, `chat_messages.evidence_json` |
| 솔루션 | 한 문장 문자열 | ✅ | 이 카드를 왜 추천했는지 설명 | 🔜 AI 생성으로 확정, BE 컬럼 요청함 |
| 인사이트 | — | — | — | ❌ **V1 범위 아님** |

- **솔루션**: `solutions.evidence_text TEXT NULL` 컬럼을 승민에게 요청했다. AI 응답에
  `evidence` 필드를 추가한다(제나 영역 — `prompts/solution.py`, `schemas/solution.py`,
  `tests/test_solutions.py`). `NULL` 허용으로 여는 이유는 LLM이 근거를 못 뽑았을 때
  재시도 후 500이 나는 걸 막기 위해서다.
  - v2에서 요약 모델로 교체하더라도 **생성 주체만 바뀌고 계약은 그대로**라, 지금 필드를
    확정해두면 마이그레이션을 한 번 덜 돈다.
- **인사이트**: 제외한다. 인사이트는 처방이 아니라 **관찰**이라(`app/prompts/insight.py`의
  "제안은 하지 말고 관찰되는 사실만") **문장 자체가 이미 근거다.** 붙이면 동어반복이 된다.
  AN-01 화면도 불릿 3개라 근거를 넣을 자리가 없다. 저장하려면 컬럼 추가가 아니라
  `sales_ai_insights.insights`의 JSON 구조를 `["문장"]` → `[{text, evidence}]`로 바꿔야 해서
  이미 구현된 BE 엔티티까지 건드려야 한다 — 얻는 것 대비 범위가 크다.
  - 인사이트에도 수치는 들어간다("3주 연속"). 환각 위험은 있지만 그건 **DB 컬럼 문제가 아니라
    생성 시점 검증 문제**다. 필요해지면 AI 쪽 서버 검증으로 푼다.

**규칙: 처방에는 근거가 붙고, 관찰에는 안 붙는다.** 관찰은 그 자체가 근거다.

## 2026-09-21 오후 (제나 휴가 중 — 헥터가 에이전트 파트까지 진행)

실제 Claude API 키를 처음 받아 실호출을 돌렸고, **CI 가 못 잡는 P0 를 두 건** 찾았다.
둘 다 원인이 같다 — **목(mock)이 실제 모델과 달라서 단위 테스트가 계속 통과했다.**

- **코드펜스** (PR #60, 이슈 #59): 모델이 JSON 을 ```json 펜스로 감싸 내려줘 솔루션·인사이트가
  실호출에서 100% 500 이 났다. Anthropic 응답은 200 OK 고 파싱만 깨진다. 프롬프트에
  "설명 없이 JSON만 출력하세요" 가 있지만 지켜지지 않는다 — 프롬프트 대신 코드에서 벗긴다
  (`llm.strip_fence`). 재시도도 매번 같은 결과라 요청 1건당 API 를 2번 쓰고 500 이 났다.
  못 잡은 이유: 테스트가 `llm.complete` 를 monkeypatch 하고 **순수 JSON 만** 흘려줬다.
- **챗봇 도구 내부 노출** (PR #63, 이슈 #62): SSE 가 도구 호출 턴의 content 를 그대로
  내보내 `toolu_...` ID·도구 이름·인자가 사용자에게 샜다. 계약상 `content` 는 문자열인데
  리스트가 나갔다. Anthropic 은 도구 호출 턴 content 를 **빈 문자열이 아니라 블록 리스트**로
  스트리밍한다 — `if chunk.content:` 로는 안 걸러진다(`_text_of` 추가).
  못 잡은 이유: `FakeModel` 이 도구 호출 턴을 `AIMessageChunk(content="")` 로 흉내냈다.
  PR #49 에서 들어왔고, 6be11b8(#55·#61 머지 전)에서도 재현돼 오늘 머지와 무관함을 확인했다.

**교훈**: LLM 경로를 건드리는 PR 은 머지 전에 `uv run python -m devtools.llm_smoke --with-chat`
를 한 번 돌린다. CI 는 실호출을 하지 않으므로 이 종류의 버그를 구조적으로 못 잡는다.

머지한 제나 PR:

- **#55 솔루션 evidence** — `SolutionCard.evidence: str | None = None`. NULL 허용이라 LLM 이
  근거를 못 뽑아도 재시도 후 500 이 나지 않는다. BE 에 `solutions.evidence_text TEXT NULL`
  컬럼을 요청해둔 상태다.
- **#61 LLM provider 추상화** — Claude/OpenAI/Google/Upstage 스위칭. 머지 전에 워크트리에서
  시뮬레이션해 `strip_fence`(#60)가 살아남는지 확인하고 넣었다. `LLM_PROVIDER` 기본값은
  `anthropic` 이다.
  ⚠️ **anthropic 외 3개 경로는 실호출로 검증된 적이 없다.** `tests/test_llm_providers.py` 는
  클라이언트 생성만 보는 mock 테스트다. 실제로 쓰기 전에 키를 넣고 `llm_smoke` 를 돌려야 한다.
- **#65** 낡은 `X-Internal-Api-Key` 문구 삭제, `AGENTS.md` 스텁 실행 명령 정정
  (`uv run python devtools/stub_backend.py` 는 ModuleNotFoundError 로 죽는다).

기타:

- **BE 일별 집계 대조 완료** — 승민이 취소 처리를 고친 뒤 재대조해 **62/62일 금액·주문 수
  완전 일치**. BE 요청 바디를 그대로 예측 API 에 쏴 200 + 35건을 받았고, 예측 일평균
  1,255,790 원이 6월 실적 일평균 1,262,408 원과 0.5% 차이였다.
- **인사이트 프롬프트에 수치 인용 규칙 추가** — 실호출 3회 중 1회에서 18시 매출 210,000 원을
  "30만원"으로 어림했다. 비율(7배)은 맞고 절대값만 틀렸다.

## 2026-09-22 (제나 휴가 중 — 헥터가 에이전트 파트까지 진행)

승민에게 받은 **BE 실제 요청 샘플**과 SDK 기본값 점검에서 5건이 나왔다. 어제와 마찬가지로
**전부 단위 테스트가 통과하는 상태**에서 발견됐다.

- **챗봇 `chatDate` 누락** (PR #71): BE 가 보내는데 스키마에 없어 버려지고 있었다. 툴 `period`
  에 "지난달"이 없어 절대 날짜를 계산해 `CUSTOM` 으로 불러야 하는데, 날짜를 모르니 불가능했다.
  실제로 `THIS_MONTH` 를 부른 뒤 증감률로 **금액을 역산해 만들어냈다**("역산하면 약 285만원").
  날짜를 주니 `CUSTOM&startDate=2026-05-01&endDate=2026-05-31` 로 정확히 조회한다.
- **솔루션 카드 ERD 제약 미검증** (PR #73): `rankNo` 중복·`title` 200자 초과·카드 개수가 전부
  그대로 200 으로 나갔다. `rankNo` 중복은 `UNIQUE (solution_bundle_id, rank_no)` 위반이라
  묶음 하나가 통째로 저장되지 않는다. **AI 는 200, BE 가 INSERT 에서 터지는** 형태다.
- **인사이트도 같은 부류** (PR #79): 빈 배열이 `insights is not None` 조건 때문에 재시도조차
  없이 200 으로 나갔다. `maxInsightCount` 도 강제하지 않아 3개 요청에 5개가 나갔다.
- **표기 규칙** (PR #75): 솔루션 근거가 `1,340,580` 을 "134만 580원"으로, `-0.0885` 를
  "**-8.85% 감소**"로 써서 증가로 읽혔다. 인사이트에만 있던 규칙을 솔루션에도 넣었다.
- **LLM 타임아웃 미설정** (PR #77): SDK 기본이 읽기 600초 + 재시도 2회라, 서비스 재시도까지
  겹치면 요청 하나가 최악 **1시간**을 붙잡는다. 60초 + SDK 재시도 0회로 바꿨다(재시도는 서비스
  레이어 담당). 504 핸들러도 600초 뒤에나 발동해 사실상 쓰이지 않던 코드였다.

**BE 요청 계약 대조 완료** — 솔루션·인사이트·챗봇 3종 모두 승민 실제 샘플로 422 없음을
확인했고, 실호출로 200 까지 받았다. `devtools/contract_check.py` 로 재현 가능하다.

**배포 설정 정리** — `docs/DEPLOY.md` 신설. `ANTHROPIC_API_KEY` 와 `BACKEND_BASE_URL` 은
기본값이 있어 **앱이 정상 기동하고 `/health` 도 200 을 돌려준다.** 배포는 성공한 것처럼 보이고
첫 요청에서 터진다. 기동 시 ERROR 로그로 잡도록 했다.

**문서 전수 검수** — 위키 단계1·2·3·4 와 `docs/ARCHITECTURE.md` 에서 구현과 어긋난 서술을
바로잡았다. 가장 컸던 것은 단계1 의 "`evidence` 는 AI 가 내리지 않고 Backend 가 직접 만든다"
(실제로는 만드는 쪽이 없었고, 2026-09-21 에 AI 생성으로 확정)와 단계2 의 "프롬프트 캐싱을
적용한다"(실측 결과 v1 미적용 결정)다.

## 2026-09-22 오후 — SALES 인사이트 계약 확정 (풀스택 연동)

풀스택이 확정 계약을 전달해 인사이트 경로를 통째로 맞췄다. 세 PR 로 나눠 들어갔다.

- **`metrics` 전면 교체** (PR #87): `salesSummary.netSales` → `totalSales`+`menuSales`+
  `orderCount`+`averageOrderValue`, `hourlyProfile`→`hourlySales`, `categoryBreakdown`→
  `categorySales`, 그리고 `salesTrend`·`weekdaySales`·`menuRankings` 신규.
  **공유 `Metrics` 를 고치지 않고 `InsightMetrics` 를 따로 뒀다** — 솔루션이 같은 모델을
  쓰고 있어서 그대로 바꾸면 승민 실제 샘플로 검증이 끝난 경로가 함께 깨진다.
  `analysisRunId` 는 스키마에 없어 `extra="ignore"` 가 조용히 버리고 있었다.
- **`INSUFFICIENT_DATA` 실제 응답** (PR #89): 스키마에 `status`·`missingData` 가 선언돼
  있었는데 **서비스가 한 번도 내보내지 않았다.** 영업일 14일 미만은 BE 가 거르지만, 그
  검사를 통과하고도 지표가 비는 경우가 남는다 — 상세 지표 5종이 전부 기본값 `[]` 이라
  `salesSummary` 만으로 요청이 통과하고, 그대로 생성하면 "총매출은 0원입니다" 같은 문장이
  **200 으로 화면까지 나간다.** 이제 LLM 을 부르지 않고 `INSUFFICIENT_DATA` 를 돌려준다.
- **오류 바디 `error.code`·`retryable`** (PR #91): `ApiError.code` 는 이미 모든 호출부에
  있었는데 로그에만 쓰이고 응답에 나가지 않았다. `retryable` 은 **HTTP 상태 코드에서
  파생**시킨다 — 손으로 관리하는 표를 두면 BE 재시도 정책과 조용히 어긋난다.
  `LLM_ERROR`→`PROVIDER_ERROR`, `LLM_TIMEOUT`→`PROVIDER_TIMEOUT` (BE 계약 예시에 맞춤,
  provider 4종 지원이라 실제와도 맞다). 환경변수 `LLM_TIMEOUT_SECONDS` 는 이름 그대로다.

**실호출로만 잡힌 것 3건** — 어제·그제와 같은 패턴이고 전부 단위 테스트는 통과하고 있었다.

| 증상 | 정답 | 빈도 |
|---|---|---|
| `0.042` → "4% 증가" | 4.2% | 3회 중 1회 |
| `ratio` 0.417 → "**전체의** 41.7%" | 메뉴 매출의 41.7% (총매출 기준이면 39.4%) | 5회 중 1회 |
| `vsPrevPeriod` → "**메뉴 매출**이 4.2% 증가" | 총매출 기준 | 5회 중 1회 |

기존 지시가 **금액 어림만 막고 비율은 안 막았다.** `4.2 → 4` 는 화면에서 티가 안 나
조용히 틀린다. 세 번째는 계약 자체의 구멍이라 BE 에 물어 `totalSales` 기준으로 확정받았다.
프롬프트를 세 번 고치며 매번 5~6회 실호출로 좁혀 **6/6 정확**까지 갔다.

**타임아웃 정렬** — BE 응답 제한이 30초인데 AI 최악이 `60초 × 재시도 2회 = 120초`였다.
BE 가 끊은 뒤에도 토큰만 태운다. 인사이트만 12초로 묶어 최악 24초로 넣었고(`llm.complete()`
에 호출별 `timeout` 인자 추가), **호출별 하드코딩이 전역 환경변수를 조용히 덮어써서
504 재현이 불가능해진 걸 BE 질문으로 발견해** `INSIGHT_LLM_TIMEOUT_SECONDS` 설정으로 뺐다.

**선택적 내부 인증** (`app/core/auth.py` 부활) — `INTERNAL_AI_TOKEN` 이 **비어 있으면
검증하지 않는다.** 2026-09-16 "앱 레벨 인증 없음" 결정의 기본 동작 그대로다. 필수로 두면
배포 때 BE·AI 시크릿이 어긋나는 순간 전부 401 이라 연동 테스트 당일을 막는다. 되살린 이유는
**보안 그룹 요구사항이 그날까지 코드 주석에만 있었고 인프라 반영 여부를 아무도 확인하지
않았기** 때문이다. 보안 그룹이 1차, 이건 2차다.

**BE 와 확정한 상태 코드 구분** (2026-09-22):

```
200 COMPLETED / 200 INSUFFICIENT_DATA        error 필드 없음
401 UNAUTHORIZED           retryable false
422 VALIDATION_ERROR       retryable false
500 *_GENERATION_FAILED    retryable false   AI 가 이미 1회 재시도한 뒤다
502 PROVIDER_ERROR         retryable true    BE 가 재시도 대상에 넣었다(429/529 가 여기 묶인다)
504 PROVIDER_TIMEOUT       retryable true
503                        — 현재 어떤 요청도 만들지 않는다(과부하 차단 없음)
```

**기간 정책 확정** — V1 은 `targetMonth` 기준 월간 고정. 필터 변경으로 재생성하지 않는다.
스키마·ERD 변경 없음.

## 마지막으로 통과한 것

- `uv run pytest -q` — **120 passed** (2026-09-23)
- `uv run python -m devtools.llm_smoke --with-chat` — 솔루션·인사이트·챗봇 3종 실호출 통과
- `uv run python -m devtools.forecast_check --pos <엑셀> --be-daily <BE 샘플>` — 62/62일 일치
- `uv run ruff check --fix . && uv run ruff format .` — 통과
- 서버 실기동 후 curl: 3개 라우트(`solutions/generate`, `sales-insights`, `chat/messages`) 전부
  새 경로로 노출, 422 응답이 새 플랫 포맷(`{"message":...}`)인지 확인
- 인사이트 전 상태 실기동 확인: `200 COMPLETED` / `200 INSUFFICIENT_DATA` / `401` /
  `422` / `502` / `504` — 풀스택 원본 페이로드 그대로, 6/6 정확, 3.2~4.0초
- **미검증 ①**: anthropic 외 provider(openai/google/upstage) 실호출 — mock 테스트만 있다.
- **미검증 ②**: 챗봇이 부르는 **BE 조회 API 4종** — 스텁으로만 확인했다. AI 파트에서
  유일하게 실제 BE 를 한 번도 못 받아본 구간이다. 필드명이 어긋나도 `.get()` 이라 에러 없이
  `null` 로 빠져 **챗봇이 조용히 빈 답을 한다.** BE 주소만 나오면
  `devtools/llm_smoke.py --with-chat` 로 바로 확인 가능하다.

## 다음 한 걸음

**AI 코드는 완료다.** 남은 건 전부 다른 팀에 걸려 있거나, 서버 주소가 나와야 할 수 있는 일이다.

1. 🔴 **챗봇 BE 조회 4종 실호출 검증** — AI 파트에서 **유일하게 검증 안 된 구간**이다.
   BE 주소만 나오면 `uv run python -m devtools.llm_smoke --with-chat` 로 끝난다.
   나머지 3개 엔드포인트는 실제 데이터·실제 LLM 으로 다 돌려봤는데 이것만 스텁뿐이다.

2. 🔴 **클라우드팀** — 배포는 사실상 되고 있고, CI 만 빨간불이다.

   **ECR** — 붙었다(#85, OIDC). 이미지가 실제로 올라간다.
   ```
   memme/ai:bd964cfa5847…  sha256:0aeb0057970254c006cbc4fb2d719549b8bc5c308e1904cf40d1e77b3235f349
   memme/ai:34e606445097…  sha256:bd255705c18eb9f6530343a89753844b07eab86329adbe6f84e018443c8512f8
   ```
   **푸시 직후** `ecr:DescribeImages` 권한이 없어 다이제스트 조회에서 잡이 죽는다
   (`GitHubActionsAIECRPushRole`). ECR 잡이 실행된 2회 모두 같은 지점이다.
   지금은 새 커밋마다 푸시가 되니 안 드러나지만, **같은 커밋으로 재실행하면 진짜로 실패한다** —
   "이미 있으면 건너뛴다" 가드도 `describe-images` 로 판단해서 항상 "없음"으로 떨어지고,
   태그가 immutable 이라 재푸시가 거부된다. IAM 에 `ecr:DescribeImages` 한 줄이면 둘 다 풀린다.

   `ci.yml` 요약 출력에 **별개 버그**가 하나 더 있다. 큰따옴표 안 백틱이라 셸이 SHA 를
   명령으로 실행한다 — 권한을 고쳐도 요약에는 빈 값이 찍힌다.

   ```
   $ GITHUB_SHA=bd964cf bash -c 'echo "- Source commit: `$GITHUB_SHA`"'
   bash: bd964cf: command not found
   - Source commit:
   ```

   클라우드팀 파일이라 AI 가 직접 고치지 않았다.

   **보안 그룹** — 요구사항이 2026-09-22 까지 코드 주석에만 있었다. 그날 처음 명시적으로
   요청했고 아직 반영 여부 미확인이다. 8000 포트 인바운드를 BE 보안 그룹으로만 제한해야 한다.

   **운영 `ANTHROPIC_API_KEY`** — 현재 키는 개발용 개인 키이고 대화방에 노출된 이력이 있다.
   운영 전용 키 발급 + 폐기 필요.

3. 🟡 **풀스택 회신 대기** — `PROVIDER_ERROR` 이름이 맞는지, `missingData` 어휘를
   `SALES_HISTORY`(풀스택 계약) 로 갈지 `SALES_DATA`(노션 SALES-04) 로 갈지. 둘 다 한 줄 변경이다.

4. 🟡 **승민 — `solutions.evidence_text TEXT NULL` 컬럼.** 2026-09-21 에 요청했고 아직이다.
   없으면 SOL-04 응답의 `evidence` 를 BE 가 내려줄 수 없고, 챗봇 `context[].evidence` 도
   항상 `null` 로 들어와 근거를 못 본다.

5. **제나 복귀 후 리뷰** — 휴가 중 담당 영역을 **12번** 건드렸다:
   #60 #63 #67 #71 #73 #75 #77 #79 #80 #87 #89 #91. 전부 PR 본문 맨 위에 경계 침범을
   명시하고 revert 가능함을 적어뒀다. 방향이 다르면 되돌린다.

6. **`docs/api정의서.md` 솔루션 응답 예시에 `evidence` 가 빠져 있다** — #55 로 AI 가 내보내기
   시작했는데 예시 2개 모두 `rankNo/title/summaryText/detailText` 만 있다. FE 가 이 예시를
   보고 만들면 근거 칸이 빈다. BE 담당 문서라 AI 가 직접 고치지 않는다 — 노션 원본 갱신 요청.

7. **노션 SALES-04 200 예시가 자기 규칙을 위반한다** — 예시 문장이
   `"최근 화요일 매출이 3주 연속 감소하고 있어요."` 인데, 2026-09-22 확정 규칙은
   "여러 주 데이터가 필요한 표현 금지"다. AI 쪽은 프롬프트로 막아뒀고 노션 예시 교체가 필요하다.

8. **`llm_model` 기본값이 `claude-sonnet-4-5`** (최신은 `claude-sonnet-5`). 버그가 아니라
   개선이고, 바꾸면 품질·비용이 달라지므로 연동 후에 `llm_smoke` 와 함께 판단한다.

## 미해결 결정

- **챗봇 데이터 부족 처리**: 사용자가 "예측·인사이트·챗봇 모두 200+`status:INSUFFICIENT_DATA`+
  `data.missingData`로 통일"이라고 확정했다. 챗봇은 이 상태를 코드에서 판단할 명확한 트리거가
  없어서 아직 구현하지 않았다 — 지금은 LLM이 시스템 프롬프트 지시("데이터가 부족하면 부족하다고
  말하세요")로 자연어로만 표현한다. 언제 이 상태를 코드로 판정할지 BE와 조건 정의 필요.
- **솔루션 metrics의 순이익(V2)/리뷰 요약(V3)**: 설계 설명엔 포함된다고 돼 있는데 `Metrics`
  스키마에 필드가 없다. BE가 보내도 `extra="ignore"` 때문에 조용히 버려진다.
  → **V2 착수 시점에 확정하기로 미뤘다(2026-09-21).** 지금 스펙이 없어도 안 깨지고,
  지금 정해봐야 실제 기능을 만들 때 다시 바뀐다.
- **인사이트 metrics의 정확한 MENU 전용 필드명**: "menu_net_amount와 MENU 전용 일별·요일별·
  시간대별·카테고리별 지표"라는 서술만 있고 리터럴 JSON 예시가 없다. BE 확인 필요.
- **`modelVersion` 을 저장할 것인가** (2026-09-21 신규): #61 이 형식을 `{provider}:{model}` 로
  바꾼 이유가 "provider 비교 평가" 인데, 정작 저장되는 곳이 없다 — `solutions`·
  `solution_bundles` 에 컬럼이 없고(`sales_forecasts` 에만 `model_version VARCHAR(50)` 존재),
  인사이트·챗봇 응답에는 `modelVersion` 필드 자체가 없다. 지금 구조로는 응답을 볼 때만 보이고
  쌓이지 않아 비교가 불가능하다. 실제로 비교할 생각이면 `solution_bundles` 컬럼 + 인사이트·
  챗봇 응답 필드가 필요하다. **V1 에서는 그대로 두고 V2 에서 정하는 쪽을 권한다.**

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
