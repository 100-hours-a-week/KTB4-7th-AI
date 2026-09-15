# BE ↔ AI 계약 대조표 — 위키 vs 노션

작성: 2026-09-15 · 대상: BE 담당자(승민)와 AI 담당자(제나, 헥터)

## 왜 이 문서인가

두 파트가 **서로 다른 문서를 기준으로 구현하고 있다.**

- BE `AGENTS.md`: "기능 범위·비즈니스 로직은 요구사항 분석, **API 구현은 API 정의서**(노션), DB·Entity·JPA는 ERD 정의서"
- AI: GitHub AI Wiki `[AI] 단계 1: 모델 API 설계` 기준으로 `app/schemas/` 작성 완료

경로·응답 포맷·인증이 전부 다르다. **9/23 서버연결 시점에 안 붙는다.** 이 문서는 차이만 나열하고 판정하지 않는다 — 어느 쪽으로 통일할지는 함께 정한다.

> 참고: BE `AGENTS.md`(머지 전)가 가리키던 노션 API 정의서 ID는 `3d57f3fa-ed48-806b-b27f-d7f04ba53d5a` 이고,
> AI가 읽은 노션 페이지는 `3dcbdeb9-2c66-804c-8ff9-f4c2dc9e48ee` 다. **같은 문서인지 먼저 확인이 필요하다.**
> 아래 "노션" 열은 후자 기준으로 작성했다.

---

## 1. 요약

| 구분 | 충돌 건수 |
|---|---|
| BE → AI 엔드포인트 경로 | 4건 중 **4건 전부 다름** |
| AI → BE 툴 경로 | 6건 중 **3건 다름**, 버전 표기 2건 다름 |
| 성공 응답 포맷 | 전부 다름 |
| 오류 응답 포맷 | 전부 다름 |
| 서버 간 인증 | **노션에 규약 자체가 없음** |

---

## 2. BE → AI 엔드포인트 (AI가 구현, BE가 호출)

| 기능 | 위키 | 노션 |
|---|---|---|
| 매출 예측 | `POST /internal/ai/forecast/batch` | `POST /internal/v1/ai/forecasts/batch` |
| 솔루션 생성 | `POST /internal/ai/solutions/generate` | `POST /internal/v1/ai/solutions/generate` |
| 매출분석 인사이트 | `POST /internal/ai/insights/generate` | `POST /internal/v1/ai/sales-insights` |
| 챗봇 | `POST /internal/ai/chat/messages` | `POST /internal/v1/ai/chat/messages` |

**차이 요약**: 노션은 전부 `/internal/v1/ai/...` 로 버전이 경로에 들어간다. 인사이트는 이름 자체가 다르다(`insights/generate` vs `sales-insights`).

### 2-1. 매출 예측 응답

| 항목 | 위키 | 노션 |
|---|---|---|
| 래퍼 | 없음 (플랫) | `message` + 플랫 |
| 상태 필드 | `status`: `SUCCESS` / `INSUFFICIENT_HISTORY` | 없음 |
| 예측 배열 | `predictions[].date` / `.predictedAmount` / `.isHoliday` | `predictions[].targetDate` / `.predictedSalesAmount` / `.basisDate` / `.storeId` / `.modelVersion` / `.generatedAt` |
| 월 합계 | `monthlyTotal.predictedAmount` / `.vsPrevMonth` | 없음 |
| 요일 평균 | `dowAverage[]` 7건 | 없음 |
| 이력 부족 | `status=INSUFFICIENT_HISTORY` + `requiredMonths` / `providedMonths` | 정의 없음 |
| 모델 버전 | 최상위 `modelVersion: "ridge_v1"` | 항목별 `modelVersion: "forecast-v1.0"` |

**영향**: 위키는 월 합계·요일 평균을 AI가 계산해서 주고, 노션은 일별 예측만 준다. FE 화면에 월 합계가 필요하면 누가 계산할지가 갈린다. → **헥터 확인 필요**

### 2-2. 솔루션 생성 응답

| 항목 | 위키 | 노션 |
|---|---|---|
| 래퍼 | 없음 | `message` + 플랫 |
| 카드 필드 | `rank` / `title` / `evidence`(객체) / `detailContent`(최대 1000자) | `rank` / `title` (예시에 둘만 등장) |
| evidence | 구조화 객체 `{metric, dayType, period, value}` | BE 저장 후 FE 응답(SOL-04)에선 **문자열** |
| 카드 본문 | `detailContent` | `summary` / `action` / `expectedEffect` (SOL-04 기준) |

**영향**: `evidence`가 객체냐 문자열이냐가 핵심. 위키는 AI가 구조화해서 주고 BE가 문장으로 가공하는 설계다. 노션 SOL-04 응답은 이미 문장이다. → **구조화 유지 여부 결정 필요**

### 2-3. 매출분석 인사이트 응답

| 항목 | 위키 | 노션 |
|---|---|---|
| 경로 | `/internal/ai/insights/generate` | `/internal/v1/ai/sales-insights` |
| 요청 | `storeId`, `uploadId`, `dataDays`, `metrics` | `storeId`, `period`, `metrics` |
| 래퍼 | 없음 | `data` 래퍼 |
| 결과 | `insights[]` — 각 `{text, evidence}` | `data.summary`(문자열) + `data.highlights[]`(문자열 배열) |
| 데이터 부족 | `status=INSUFFICIENT_DATA` (14일 미만) | 정의 없음 |
| 상태 | `SUCCESS` / `INSUFFICIENT_DATA` | `COMPLETED` |

**영향**: 구조가 가장 많이 다르다. 위키는 근거 포함 배열, 노션은 요약 문자열 + 문장 배열. `dataDays` 14일 게이트가 노션엔 없다.

### 2-4. 챗봇 SSE 청크

| 항목 | 위키 | 노션 |
|---|---|---|
| 청크 | `data: {"answerChunk":"...","evidence":{...}\|null}` | `{"event":"answerChunk","data":{"content":"..."}}` |
| 종료 | `data: [DONE]` | 정의 없음 |
| 질문 상한 | 최대 300**토큰** | 공백 제외 1~300**자** (FE→BE 기준) |
| 툴 호출 시점 | 필요 시 호출 후 스트리밍 | "툴 호출이 **먼저 끝난 뒤** 스트리밍 시작" 명시 |

**영향**: SSE 필드명(`answerChunk` vs `event`/`data.content`)이 달라 BE 중계 코드가 안 맞는다. 종료 시그널도 노션엔 없다.

---

## 3. AI → BE 툴 6종 (BE가 구현, AI가 호출)

**이쪽이 더 위험하다** — BE가 구현하므로 BE 기준으로 만들어지면 AI 쪽 툴 호출이 전부 404다.

| 툴 | 위키 | 노션 | 일치 |
|---|---|---|---|
| 매출 요약 | `GET /internal/v1/sales/summary` | `GET /internal/v1/sales/summary` | ✅ |
| 카테고리·메뉴 | `GET /internal/v1/sales/categories` | `GET /internal/v1/sales/categories` | ✅ |
| 시간대 분포 | `GET /internal/v1/sales/hourly-profile` | `GET /internal/v1/sales/hourly-profile**s**` | ❌ 복수형 |
| 예측 조회 | `GET /internal/v1/forecast` | `GET /internal/v1/sales/forecasts` | ❌ 경로 다름 |
| 순이익 | `GET /internal/v1/profit` (**v2**) | `GET /internal/v1/sales/profit-analyses` (**v1**) | ❌ 경로·버전 |
| 리뷰 요약 | `GET /internal/v1/reviews/summary` (**v3**) | `GET /internal/v1/review-summaries` (**v1**) | ❌ 경로·버전 |

**버전 차이가 범위 문제다.** 위키는 순이익을 v2, 리뷰를 v3로 미뤘는데 노션은 둘 다 v1이다. MVP에 순이익·리뷰 툴이 들어가는지 정해야 한다.

### 툴 응답 포맷
- 노션: 전부 `{"message":"조회에 성공했습니다.","data":{...}}` — `data` 래퍼 일관
- 위키: 반환 내용만 서술, 래퍼 명시 없음

### 예측 조회 툴의 신뢰구간
노션은 `{"targetDate","predictedSales","lowerBound","upperBound"}` 를 요구한다.
위키의 Ridge 설계(α=12, 피처 7종)는 **단일 예측값만 산출**한다. 신뢰구간을 낼 방법이 정의돼 있지 않다.
→ **헥터 확인 필요**

---

## 4. 공통 규약

### 4-1. 성공 응답 래퍼

| | 위키 | 노션 |
|---|---|---|
| BE→AI 생성 API | 플랫 | **일관되지 않음**: 예측·솔루션은 플랫, 인사이트는 `data` 래퍼 |
| AI→BE 툴 | 명시 없음 | `data` 래퍼 |
| `message` 필드 | 없음 | 전부 있음 (한글 사용자 안내 문구) |

노션 내부에서도 래퍼가 통일돼 있지 않다. 이것부터 정리가 필요하다.

### 4-2. 오류 응답

**위키**
```json
{"success": false,
 "error": {"code": "VALIDATION_ERROR",
           "message": "요청 필드가 스키마와 일치하지 않습니다.",
           "traceId": "b213ceca-c231-4f10-bff5-cc67b4737213"}}
```

**노션**
```json
{"message": "필수 데이터가 누락되었거나 형식이 올바르지 않습니다."}
```
필요 시 `retryAfterSeconds`, `status`, `failReason` 추가.

**영향**: `traceId`가 노션엔 없다. 위키는 "왜 이 솔루션이 나왔는지 역추적"을 설계 목표로 잡고 `traceId`를 전 오류에 넣었다. 장애 추적을 포기할지 결정해야 한다.

### 4-3. 서버 간 인증 ⚠️

| | |
|---|---|
| 위키 | `X-Internal-Api-Key: <service_token>`. AI는 사용자 로그인 토큰을 받지도 해석하지도 않음. mTLS 전환 검토 중 |
| 노션 | **언급 없음.** `X-Internal-Api-Key` 문자열이 문서에 0건. "인증 방식: 세션 쿠키"는 FE→BE 규약 |

**노션만 보고 구현하면 내부 인증이 없는 상태가 된다.** AI 서버는 Backend SG에서만 인바운드를 허용하지만(클라우드 설계), 애플리케이션 레벨 인증은 별도다.
AI 서버는 현재 `X-Internal-Api-Key` 검증을 구현해 둔 상태다 — BE가 이 헤더를 안 보내면 **전부 401**이다.

### 4-4. 필드 표기
- 위키: `camelCase`, 금액은 정수(원), 비율은 소수(0.62), 날짜 `YYYY-MM-DD`, 정의되지 않은 요청 필드는 422
- 노션: `camelCase` 동일. 비율은 **퍼센트 표기**(`changeRate: 12.5`, `ratio: 56.3`) — 위키의 소수 표기(0.125)와 **다름**

**비율 표기가 다르다.** `0.62` vs `62.0`. 이건 값이 100배 틀어지는 문제다.

---

## 5. 결정이 필요한 항목

| # | 항목 | 누가 결정 | 기한 |
|---|---|---|---|
| 1 | 두 노션 페이지(`3d57f3fa…` / `3dcbdeb9…`)가 같은 문서인가 | 제나 ↔ 승민 | 즉시 |
| 2 | 기준 문서를 위키/노션 중 무엇으로 통일할 것인가 | 팀 | 9/16 |
| 3 | 엔드포인트 경로에 `/v1` 을 넣을 것인가 | 팀 | 9/16 |
| 4 | 성공 응답에 `data` 래퍼를 쓸 것인가 (노션 내부 불일치부터 정리) | 팀 | 9/16 |
| 5 | 오류 응답에 `traceId` 를 유지할 것인가 | 팀 | 9/16 |
| 6 | **비율을 소수(0.62)로 쓸 것인가 퍼센트(62.0)로 쓸 것인가** | 팀 | 9/16 |
| 7 | `X-Internal-Api-Key` 를 쓸 것인가 (노션에 규약 추가 필요) | 제나 ↔ 승민 ↔ 클라우드 | 9/18 |
| 8 | 툴 6종 최종 경로 (BE 구현 대상) | 승민 | 9/18 |
| 9 | 순이익·리뷰 툴이 MVP(v1) 범위인가 | 팀 | 9/16 |
| 10 | `evidence` 를 구조화 객체로 둘 것인가 문자열로 둘 것인가 | 제나 ↔ 승민 | 9/16 |
| 11 | 예측 신뢰구간(`lowerBound`/`upperBound`)을 낼 것인가 | 헥터 | 9/18 |
| 12 | 월 합계·요일 평균을 AI가 줄 것인가 BE가 계산할 것인가 | 헥터 ↔ 승민 | 9/18 |
| 13 | 인사이트 14일 게이트, 예측 3개월 게이트를 유지할 것인가 | 팀 | 9/16 |

---

## 6. AI 쪽 현재 상태

`app/schemas/` 는 **위키 기준으로 작성돼 있다.** 아직 원격에 푸시하지 않았다(로컬 커밋만).

기준이 노션으로 정해지면 수정 범위는 다음과 같다.
- `app/schemas/*.py` — 필드명·래퍼 변경
- `app/api/*.py` — 라우터 `prefix` 를 `/internal/v1/ai` 로
- `app/core/errors.py` — 오류 포맷
- `app/clients/backend.py` — 툴 6종 경로 상수 (아직 미작성)

스키마를 한곳에 모아둬서 **뒤집혀도 반나절이면 된다.** 다만 기준이 정해지기 전에 엔드포인트를 더 쌓으면 그만큼 늘어난다.
