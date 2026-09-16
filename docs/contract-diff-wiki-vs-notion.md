# BE ↔ AI 계약 대조표 — 최종 결정본

작성: 2026-09-15 · 최종 갱신: 2026-09-16 · 대상: BE 담당자(승민), AI(제나, 헥터)

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
| 금액 반올림 | 정수(원) | 정의 없음 | ⏳ **미정 — BE 확인 필요**(ERD는 `DECIMAL(14,2)`) |
| 신뢰구간(`lowerBound`/`upperBound`) | 미산출(Ridge 단일값) | 예측 조회 툴 응답에 포함 | ⏳ **헥터가 추후 직접 작성 예정** |

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
| 데이터 부족 처리 | 정의 없음 | `403`, `missingData:["INSUFFICIENT_HISTORY"]` | 📌 **체크만 해둠 — BE 판단 영역.** forecast/insights는 422인데 챗봇만 403 — 변경 요청 안 함 |

> ⚠️ 운영 메모(결정 아님): `history`를 매번 전체 누적으로 보내는 구조라 대화가 길어질수록 토큰 비용 증가 — 지금 결정 사안은 아니고 운영 단계에서 재검토.

---

## 6. AI → BE 툴 6종 (챗봇용 내부 조회 API)

| 항목 | AI위키 | BE노션 | 결정 |
|---|---|---|---|
| v1 MVP 범위 | 순이익 v2/리뷰 v3로 구분해 둠 | 순이익·리뷰 경로는 v1 표기지만 실제 계산 잡은 v2/v3 | ✅ **v1 MVP는 4종**(매출요약/카테고리·메뉴/시간대분포/예측조회)만. 순이익→v2, 리뷰→v3 이관 — 두 툴은 "v1" 표기인데 원본 데이터를 만드는 백엔드 잡이 v1에 없어 호출해도 항상 빈 값 |
| 시간대 분포 경로 | `hourly-profile`(단수) | `hourly-profiles`(복수) | ✅ 노션(복수형) 채택 |
| 예측 조회 경로 | `GET /internal/v1/forecast` | `GET /internal/v1/sales/forecasts` | ✅ 노션 채택 |
| 예측 조회 필드명 | (해당 없음) | `predictedSales`(Amount 없음, 배치·ERD와 불일치) | ✅ **`predictedSalesAmount`로 통일** — API정의서 자체 내부 불일치 확인됨(위키-노션 차이 아님), ERD/배치 컨벤션에 맞춤 |
| 툴 응답 래퍼 | 명시 없음 | `{"message":...,"data":{...}}` 일관 | ✅ 노션 채택 |
| 신뢰구간(`lowerBound`/`upperBound`) | 미산출 | 예측 조회 툴 응답에 포함 | ⏳ **헥터가 추후 직접 작성 예정** |

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

## 8. 아직 열려있는 항목

| # | 항목 | 담당 | 상태 |
|---|---|---|---|
| 1 | 예측 신뢰구간 산출 방식 | 헥터 | ⏳ 헥터가 추후 직접 작성 예정 |
| 2 | 예측 금액 반올림(정수 vs `DECIMAL(14,2)`) | BE(승민) | ⏳ 확인 필요 |
| 3 | 인사이트 `evidence` 저장 여부·컬럼 | 제나 ↔ 승민 | ⏳ 협의 필요 |
| 4 | 솔루션 `evidence` DB 저장 여부·컬럼 | 제나 ↔ 승민 | ⏳ 협의 필요 |
| 5 | 챗봇 403 vs 422 (데이터 부족 처리) | 승민 | 📌 체크만 해둠, BE 판단 영역 |
| 6 | 툴 6종 최종 경로 확정(BE 구현 대상) | 승민 | ⏳ 확인 필요 |

---

## 9. AI 서버 구현 반영 필요 (결정 완료, 코드 미반영)

`app/schemas/`는 현재 위키 기준으로 작성돼 있고 원격 미푸시 상태(로컬 커밋만). 이번 라운드 결정사항 반영 시 변경 범위:

- `app/schemas/*.py` — 필드명·래퍼 변경(`predictedAmount`→`predictedSalesAmount`, `rank`→`rankNo` 등)
- `app/api/*.py` — 라우터 prefix `/internal/v1/ai`로, `verify_internal_key` 의존성 제거(섹션 7 인증 삭제 결정)
- `app/core/errors.py` — 오류 포맷(`failReason` 값들: forecast는 `INSUFFICIENT_HISTORY`, insights는 `DATA_INSUFFICIENT`)
- `app/clients/backend.py` — 툴 6종 경로 상수(아직 미작성)

스키마가 한곳에 모여 있어 반나절 내 반영 가능. 기준이 흔들리기 전에는 엔드포인트를 더 쌓지 않는다.
