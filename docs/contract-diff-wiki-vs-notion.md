# BE ↔ AI 계약 대조표 — 최종 결정본

작성: 2026-09-15 · 최종 갱신: 2026-09-20 · 대상: BE 담당자(승민), AI(제나, 헥터)

기준 문서: 노션 API 정의서(`3d57f3fa-ed48-806b-b27f-d7f04ba53d5a`), ERD(`3d07f3fa-ed48-807a-a1e0-efe32abd2283`). 형식: `항목 | AI위키 | BE노션 | 결정`. 필드명이 갈리면 ERD 컬럼명(snake_case→camelCase)을 기준으로 삼았다.

---

## 1. BE → AI 엔드포인트 경로

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| 기준 | `/internal/ai/...`(버전 없음) | `/internal/v1/ai/...` | ✅ **노션 채택** — 4개 경로 전부 `v1` 사용 |
| 매출 예측 | `POST /internal/ai/forecast/batch` | `POST /internal/ai/forecast/batch`(v1 없음) | ✅ `POST /internal/v1/ai/forecast/batch` — **BE 경로 수정 요청 필요**(현재 노션에 v1 빠짐) |
| 솔루션 생성 | `POST /internal/ai/solutions/generate` | `POST /internal/v1/ai/solutions/generate` | ✅ 노션 채택(양쪽 동일) |
| 매출분석 인사이트 | `POST /internal/ai/insights/generate` | `POST /internal/ai/sales-insights`(v1 없음) | ✅ `POST /internal/v1/ai/sales-insights` — **BE 경로 수정 요청 필요** |
| 챗봇 | `POST /internal/ai/chat/messages` | `POST /internal/v1/ai/chat/messages` | ✅ 노션 채택(양쪽 동일) |

---

## 2. 매출 예측 (`forecast/batch`)

설계 원칙: 위키 [AI] 단계1 §3.3·§7.1, ERD `sales_forecasts` 테이블 기준.

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| 래퍼 | 없음(플랫) | `message`+`data` | ✅ 노션 채택 — *AI 코드 미반영, 구현 시 필요* |
| 예측 시작일 | 없음 | `forecastStartDate`(마지막날+1일, 불일치 시 422) | ✅ 노션 채택 — AI 코드에 이미 구현됨 |
| 예측 기간·건수 | 명시 없음 | 명시 없음 | ✅ **35건 고정**(AI 코드 `HORIZON_DAYS=35`) |
| 이력 데이터 필드명 | 정의 상이 | 정의 없음 | ✅ `dailySales`로 통일 |
| 이력 부족 조건 | (없음) | 직전 두 달 완전월 + 학습데이터 60행 이상 | ✅ **코드로 검증 완료.** AI 코드(`REQUIRED_COMPLETE_MONTHS=2`, `MIN_TRAINING_ROWS=60`)와 이견 없음 — "3개월 이력"과 동일 조건의 다른 표현일 뿐, 헥터 확인 결과 문제없음 |
| 상태 필드(성공 응답) | `status: SUCCESS/INSUFFICIENT_HISTORY` | 없음 | ✅ 노션 채택 — 이력부족은 422로 분리, 200엔 `status` 없음 |
| 예측 배열 필드명 | `date`/`predictedAmount`/`isHoliday` | `targetDate`/`predictedSalesAmount`/`basisDate`/`storeId`/`modelVersion`/`generatedAt` | ✅ 노션(=ERD) 채택, `isHoliday` 드롭(Release 1 범위 아님) — *AI 코드는 아직 `predictedAmount`, 리네임 필요* |
| 이력부족 실패코드 | `status=INSUFFICIENT_HISTORY`+`requiredMonths`/`providedMonths`(200) | `422 + failReason: INSUFFICIENT_HISTORY` | ✅ 노션 채택 — **인사이트의 `DATA_INSUFFICIENT`와 값 다름**(정정 반영). 확장 필드로 `requiredMonths`/`providedMonths` 유지 |
| `forecastStartDate` 불일치 | (없음) | 422 | ✅ 신규 채택 — AI 코드에 이미 구현됨 |
| 월 합계(`monthlyTotal`) | 있음 | 없음 | ✅ **Release 1 제외** — BE가 `sales_daily_summaries`로 별도 계산 |
| 요일 평균(`dowAverage[]`) | 있음 | 없음 | ✅ **Release 1 제외**(사유 동일) |
| 모델 버전 | 최상위 1개 | 항목별 | ✅ 노션 채택 |
| 금액 반올림 | 정수(원) | 정수(원) | ✅ **완료(2026-09-20 확인)** — `docs/api정의서.md:547` "세 금액은 원 단위 정수", ERD `sales_forecasts.predicted_sales_amount`/`lower_bound`/`upper_bound` 전부 `BIGINT UNSIGNED`. 과거 `DECIMAL(14,2)` 우려는 최신 ERD에 없음(구버전 노션 반영 전 상태였던 것으로 보임) |
| 신뢰구간(`lowerBound`/`upperBound`) | 미산출(Ridge 단일값) | 예측 조회 툴 응답에 포함 | ✅ **완료(2026-09-20 확인)** — `docs/api정의서.md:547,794,804`에 80% 예측구간으로 명시, ERD `sales_forecasts`에 `lower_bound`/`upper_bound` 컬럼 존재, `app/schemas/forecast.py`의 `Prediction`과 일치 — 헥터 작업 반영 완료 |

> AI 코드는 아직 위 결정 다수가 미반영 상태(플랫 응답, `predictedAmount`, `verify_internal_key`, 경로에 v1 없음) — 구현 작업으로 일괄 반영 예정(섹션 6).

---

## 3. 솔루션 생성 (`solutions/generate`)

설계 원칙: **"계산은 코드, 해석은 모델"** — AI가 화면 문장을 직접 작성, BE는 가공 없이 저장·전달만.

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| 래퍼 | 없음 | `message`+플랫 | ✅ 노션 채택 |
| 카드 순번 필드명 | `rank` | `rank` | ✅ **ERD 기준 변경**: `rankNo`(컬럼 `rank_no`) |
| 카드 요약 필드명 | 없음 | `summary` | ✅ **ERD 기준 변경**: `summaryText`(컬럼 `summary_text`) |
| 카드 본문 필드명 | `detailContent`(최대 1000자) | `summary`/`action`/`expectedEffect` | ✅ **ERD 기준 변경**: `detailText`(컬럼 `detail_text`), 1000자 유지 |
| `aiInsight`(최상위 요약) | 있음 | 없음 | ✅ **제거** — 매출분석·솔루션은 역할이 분리된 별개 기능 |
| `evidence` 구조 | 구조화 객체 | 문자열(SOL-04 기준) | ✅ **구조화 객체 유지** — 검증·역추적용, 화면엔 비노출 |
| `evidence` DB 저장 여부 | — | — | ⏳ **미정 — BE와 추후 협의**(저장 시 `solutions.evidence_json` 컬럼 신설 필요) |
| `modelVersion`/`promptVersion` | 명시 없음 | 명시 없음 | ✅ **응답에만 포함, DB 비저장** |

---

## 4. 매출분석 인사이트 (`sales-insights`)

diff 작성 시점엔 위키에 없던 엔드포인트 — 노션·ERD(`sales_ai_insights`)가 사실상 유일한 스펙.

| 항목 | AI위키 | BE노션/ERD | 결정 |
|---|---|---|---|
| 요청 필드 | `storeId`/`uploadId`/`dataDays`/`metrics` | `storeId`/`salesAnalysisId`/`targetMonth`/`triggerType`/`metrics` | ✅ BE 채택 |
| 트리거 시점 | 명시 없음 | `triggerType: UPLOAD\|RETRY`(SCHEDULED 제거됨) | ✅ **업로드 이벤트마다 호출** — 월 1회 업로드면 결과적 월 1회, 여러 번 업로드하면 그때마다 갱신. *`triggerType`에 SCHEDULED가 왜 남아있었는지는 확인 완료(사용 안 함)* |
| 데이터 부족 게이트 | `status=INSUFFICIENT_DATA`(14일 미만) | 호출 생략, `422+failReason:DATA_INSUFFICIENT` | ✅ 노션 채택 |
| 응답 구조 | `insights[]` 각 `{text, evidence}` | `insights[]`(문자열 배열, 1~3개, `maxInsightCount`) | ✅ **배열 구조로 통일 완료** — AN-01 3-불릿 디자인 반영, `sales_ai_insights.insights` JSON 배열 저장 (BE 스키마 이미 반영됨) |
| 근거(evidence) 저장 여부 | 항목별 구조화 | evidence 컬럼 없음 | ⏳ **보류 — BE와 추후 협의** |
| 상태 필드 | `SUCCESS`/`INSUFFICIENT_DATA` | `PENDING`/`GENERATING`/`COMPLETED`/`FAILED`(ERD) | ✅ **ERD 채택** |
| 오류 응답 | 위키 공통 포맷 | `422+failReason:DATA_INSUFFICIENT` | ✅ 노션 채택 — forecast와 동일 패턴(단 `failReason` 값은 다름, 섹션 2 참고) |

---

## 5. 챗봇 SSE (`chat/messages`)

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| 청크 구조 | `{"answerChunk":"...","evidence":{...}\|null}`(플랫) | `{"event":"answerChunk","data":{"content":"...","evidence":{...}}}` | ✅ 노션 채택 |
| 종료 시그널 | `data: [DONE]` | 정의 없음(BE에 SSE 사내 통일구조 없음) | ✅ **위키 유지**: `data: [DONE]` — 업계 관행, JSON 아니므로 파싱 전 먼저 체크 |
| 질문 길이 제한 | 최대 300토큰 | 공백 제외 1~300자(BE 이미 422 검증) | ✅ 노션 채택 — AI 내부 엔드포인트는 재검증 안 함 |
| 툴 호출 시점 | 필요 시 호출 후 스트리밍 | 툴 호출 완료 후 스트리밍 시작 | ✅ 동일 설계, 그대로 확정 |
| history 전달 방식 | 명시 없음 | 완료된 전체 누적 대화, 선택값 | ✅ 노션 채택 |
| evidence 구조 | `{metric, dayType, period, value}` | `{metric, period, value}`, 서버 산출값과 일치 필수 | ✅ 노션 채택 |
| 데이터 부족 처리 | 정의 없음 | `403`, `missingData:["INSUFFICIENT_HISTORY"]` | ✅ **완료(2026-09-20 확인)** — 403 아니라 **200 + `status:INSUFFICIENT_DATA`**로 확정됨(`docs/api정의서.md:1127`). 게다가 AI 쪽은 이 상태를 판정할 필요 자체가 없다: FE↔BE 엔드포인트(`POST /v1/chat/messages`) 설명에 "예측 상태가 `INSUFFICIENT_HISTORY`이면 **AI를 호출하지 않고** 200+`INSUFFICIENT_DATA` 반환"이라고 명시(`docs/api정의서.md:1114`) — BE가 사전 차단하므로 `/internal/v1/ai/chat/messages` 자체가 호출되지 않는다. 섹션 8 #5 참고 |

> ⚠️ 운영 메모(결정 아님): `history`를 매번 전체 누적으로 보내는 구조라 대화가 길어질수록 토큰 비용 증가 — 지금 결정 사안은 아니고 운영 단계에서 재검토.

---

## 6. AI → BE 툴 6종 (챗봇용 내부 조회 API)

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| v1 MVP 범위 | 순이익 v2/리뷰 v3로 구분해 둠 | (2026-09-20 갱신) 순이익 `SALES-06 v2`, 리뷰 `SOL-05 v3`로 버전 필드 분리 반영됨 | ✅ **v1 MVP는 4종**(매출요약/카테고리·메뉴/시간대분포/예측조회)만 활성화, 코드(`app/clients/backend.py`)와 일치. 순이익·리뷰는 v1에 없어 호출해도 항상 빈 값이던 문제는 문서상 v2/v3로 버전 분리해 해소. ⚠️ 다만 리뷰 쪽은 **버전 필드만 v3로 바뀌고 경로는 여전히 `/internal/v1/review-summaries`**(`docs/api정의서.md:842`) — 순이익처럼 경로도 `/internal/v3/...`로 맞출지 BE 확인 필요 |
| 시간대 분포 경로 | `hourly-profile`(단수) | `hourly-profiles`(복수) | ✅ 노션(복수형) 채택 |
| 예측 조회 경로 | `GET /internal/v1/forecast` | `GET /internal/v1/sales/forecasts` | ✅ 노션 채택 |
| 예측 조회 필드명 | (해당 없음) | `predictedSales`(Amount 없음, 배치·ERD와 불일치) | ✅ **`predictedSalesAmount`로 통일** — API정의서 자체 내부 불일치 확인됨(위키-노션 차이 아님), ERD/배치 컨벤션에 맞춤 |
| 툴 응답 래퍼 | 명시 없음 | `{"message":...,"data":{...}}` 일관 | ✅ 노션 채택 |
| 신뢰구간(`lowerBound`/`upperBound`) | 미산출 | 예측 조회 툴 응답에 포함 | ✅ **완료(2026-09-20 확인)** — `GET /internal/v1/sales/forecasts` 응답(`docs/api정의서.md:804`)에 포함 확인 |
| 툴 6종 경로 최종 확정 | — | — | ✅ **완료(2026-09-20 확인)** — `docs/api정의서.md:25-27`에 6개 경로 전부 명시(`summary`/`categories`/`hourly-profiles`/`forecasts`/`profit-analyses`/`review-summaries`). `app/clients/backend.py`의 `TOOL_PATHS`(활성 4종)와 경로 일치 확인 |

---

## 7. 공통 규약

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| 성공 응답 래퍼 | 없음(플랫) | 성공 데이터는 전부 `data`에, 최상위엔 `message`/`status`/커서만 | ✅ **엔드포인트별로 노션/ERD 실제 예시를 따른다**(전역 강제 규칙 없음, 위 섹션 2~6에 개별 반영됨) |
| 오류 응답 `traceId` | 전 오류에 포함 | 언급 없음 | ✅ **드롭** — 노션 오류 규약에 `traceId` 개념 자체가 없음 |
| 서버 간 인증(`X-Internal-Api-Key`) | 헤더 검증 구현됨 | 언급 없음 | ✅ **삭제** — 클라우드 SG로 인바운드를 BE로만 제한 가능, 앱 레벨 인증 불필요. *AI 서버 헤더 검증 로직 제거 필요* |
| 비율 표기 | 소수(0.62) | 소수(`changeRate:0.125` 등) — 공통원칙에 "퍼센트 아닌 소수로 표현" 명시 | ✅ **소수 채택(양쪽 동일)**, 변경 불필요 |
| 정의되지 않은 요청 필드 | 422로 거부 | 정의 없음(당시) | ✅ **무시(ignore)로 확정(헥터)** — `extra="ignore"`, BE·AI 독립 배포 대응. AI 서버에 이미 반영됨 |

---

## 8. 아직 열려있는 항목 (2026-09-20 갱신)

| # | 항목 | 담당 | 상태 |
|---|---|---|---|
| 1 | 예측 신뢰구간 산출 방식 | 헥터 | ✅ **완료** — `lowerBound`/`upperBound` 계약·ERD·코드(`app/schemas/forecast.py`) 모두 반영됨 |
| 2 | 예측 금액 반올림(정수 vs `DECIMAL(14,2)`) | BE(승민) | ✅ **완료** — 정수(`BIGINT UNSIGNED`)로 확정, ERD에 `DECIMAL(14,2)` 흔적 없음 |
| 3 | 인사이트 `evidence` 저장 여부·컬럼 | 제나 ↔ 승민 | ⏳ **여전히 미정** — ERD `sales_ai_insights`(2026-09-20 재확인) 컬럼에 evidence류 없음. `insights`는 문자열 배열(JSON)만 저장, 근거 구조는 응답에만 실리고 DB엔 안 남는 구조로 굳어지는 중으로 보임 — BE 확인 필요 |
| 4 | 솔루션 `evidence` DB 저장 여부·컬럼 | 제나 ↔ 승민 | ⏳ **여전히 미정** — ERD `solutions`(2026-09-20 재확인) 컬럼에 evidence류 없음. 3번과 동일 패턴 |
| 5 | ~~챗봇 데이터 부족 처리~~ | 제나 ↔ 승민 | ✅ **완료, 단 애초 문제 설정이 잘못됐었음** — "AI가 INSUFFICIENT_HISTORY를 판정할 트리거가 없다"는 게 원래 우려였는데, 실제로는 **AI가 판정할 필요 자체가 없다.** BE가 `POST /v1/chat/messages` 단계에서 예측 상태를 먼저 확인해 부족하면 `/internal/v1/ai/chat/messages`를 아예 호출하지 않는다(`docs/api정의서.md:1114`). AI 내부 엔드포인트 응답표(line 1155-1163)에 정의된 부족 케이스는 `missingData:["SALES_DATA"]`(context 자체가 비는 경우)뿐, `INSUFFICIENT_HISTORY`는 AI 쪽 계약에 등장하지 않음 — 코드 수정 불필요 |
| 6 | 툴 6종 최종 경로 확정(BE 구현 대상) | 승민 | ✅ **완료** — `docs/api정의서.md:25-27`에 6개 경로 전부 명시, 코드(`app/clients/backend.py`)의 활성 4종과 경로 일치 |
| 7 | 솔루션 생성(`solutions/generate`) `metrics`에 순이익·리뷰 요약 필드 스펙 | 제나 ↔ 승민 | ✅ **범위는 확정, 필드 구조는 여전히 열림.** 순이익=V2·리뷰=V3 확정(사용자 확인) 후 `docs/api정의서.md:574`(v1 `SOL-01` 요청 설명)에서 "순이익은 V2, 리뷰 요약은 V3부터 포함한다"로 정정 완료. `SOL-05 리뷰 감성 요약` 툴도 버전 필드가 v1→v3로 갱신됨(섹션 6 참고). ⏳ **남은 건 필드 자체의 구조**: `app/schemas/common.py`의 `Metrics.reviewSummary: dict \| None`은 구조가 아직 느슨한 `dict`고, 순이익 필드는 코드에 아예 없음 — V2/V3 엔드포인트를 실제 구현할 때 순이익·리뷰 요약 각각의 필드 스펙과, `Metrics`를 v1/v2/v3용으로 분리할지 BE와 확인 필요 |

---

## 9. AI 서버 구현 반영 상태 (2026-09-20 갱신)

`app/schemas/*.py`(필드명·래퍼), `app/api/*.py`(prefix `/internal/v1/ai`, 인증 제거),
`app/core/errors.py`(오류 포맷), `app/clients/backend.py`(툴 경로)까지 solutions/insights/chat은
모두 반영 완료했다(`feat/21-contract-sync`). forecast도 헥터가 별도로 반영했다
(`feat/22-forecast-v1-경로와-인증-정리`, `feat/24-forecast-응답-노션-계약-반영`).

챗봇은 이후 `feat/48-chat-token-streaming-evidence`에서 토큰 단위 SSE 스트리밍과
`{"event":"error","data":{"code","message"}}` 구조화 오류 이벤트(`AI_TIMEOUT`/`AI_GENERATION_ERROR`/
`AI_TOOL_ERROR`)를 추가 반영했다 — Issue #48 코멘트로 BE에 공유함.

2026-09-20 기준 `docs/api정의서.md`·`docs/ERD정의서.md` 최신본(BE 반영, `feat/50-be-docs-sync`)과
대조한 결과 8절의 #1·#2·#5·#6은 해소 확인, #3·#4·#7만 남았다(전부 BE 확인/협의 필요 — AI 쪽
코드 변경 사안 아님).
