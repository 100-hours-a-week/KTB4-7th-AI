# AI 파트 v1 배포 전 QA

실행일: 2026-09-23 · 실행자: 헥터 · 대상 커밋: `f86dae4`
결과: **23건 실행 / 23건 pass / 1건 보류(BE 서버 미배포)**

## 이 시트가 팀 템플릿과 다른 점

팀 QA 템플릿은 화면이 있는 서비스 기준이라(회원가입·페이지 이동·모바일/PC) AI 파트에
그대로 적용되지 않는다. **AI 서버는 화면이 없고 사용자가 BE다.**

| 팀 템플릿 항목 | AI 파트 대응 |
|---|---|
| 회원가입 / 로그인 | 앱 레벨 인증 없음(9/16 결정). 대신 **선택적 내부 토큰** 검증을 E-04~07 로 확인 |
| 주요 기능 CRUD | AI 는 상태를 저장하지 않는다. **생성 4종**(예측·솔루션·인사이트·챗봇)으로 대체 |
| 잘못된 입력·예외 | F-03·F-04·I-03·I-04·S-02·E-03~05·D-01·D-04 |
| 페이지 이동 | 해당 없음 |
| 모바일 / PC 화면 | 해당 없음 |
| 여러 사용자가 사용하는 기능 | `storeId` 단위 격리. 툴 호출 시 `storeId` 를 클로저로 고정해 LLM 에 노출하지 않는다 |
| 배포 환경에서만 발생하는 문제 | **D-01~04** — 환경변수 누락·타임아웃을 실제로 재현 |

재현 입력은 `devtools/` 와 같은 방식으로 스크립트가 생성한다. 아래 모든 케이스는
실제 Claude API 를 호출한 결과다(모킹 없음).

---

## 1. 매출 예측 `POST /internal/v1/ai/forecast/batch`

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| F-01 | 91일(완전한 월 3개) 이력으로 예측 | 200, 35일치 예측 + 예측구간 | **pass** | `horizonDays:35`, `2026-07-01~08-04` |
| F-02 | 이력 1일만 전달 | 200 `INSUFFICIENT_DATA` | **pass** | `missingData:["INSUFFICIENT_HISTORY"]`, `providedTrainingRows:0` |
| F-03 | `forecastStartDate` 가 마지막 날 다음 날이 아님 | 422 + 사유 | **pass** | `INVALID_FORECAST_START_DATE`, 기대 날짜를 메시지에 포함 |
| F-04 | 필수 필드 누락 | 422 | **pass** | `VALIDATION_ERROR` |

## 2. 솔루션 생성 `POST /internal/v1/ai/solutions/generate`

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| S-01 | 정상 지표로 카드 생성 | 200, 카드 3장, `rankNo` 1·2·3 중복 없음, `title` 200자 이내 | **pass** | 3장, 19~23자, 근거 3건 모두 지표 인용 |
| S-02 | `vsPrevPeriod` 가 null (첫 업로드 매장) | 200, 증감 언급 없음 | **pass** | 3장, 근거에 이전 기간 비교 없음 |

## 3. 매출 인사이트 `POST /internal/v1/ai/sales-insights`

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| I-01 | 정상 지표, `maxInsightCount:3` | 200 `COMPLETED`, 문장 3개, 각 100자 이내 | **pass** | 39·50·47자. 비율 4.2/41.7/4.4/28.2/3.1% 전부 정확 |
| I-02 | `maxInsightCount:1` | 문장 1개만 | **pass** | 1개 |
| I-03 | `orderCount:0` | 200 `INSUFFICIENT_DATA`, LLM 미호출 | **pass** | `missingData:["SALES_HISTORY"]` |
| I-04 | `vsPrevPeriod` 3곳 모두 null | 200, 증감 언급 없음 | **pass** | 현재 기간 사실만 3문장 |

## 4. 챗봇 `POST /internal/v1/ai/chat/messages` (SSE)

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| C-01 | `context` 만으로 답할 수 있는 질문 | 토큰 스트리밍, **툴 미호출**, `evidence:null` | **pass** | 전 청크 `evidence:null`, 스텁 BE 호출 0건 |
| C-02 | 지표가 필요한 질문 | 툴 호출 후 답변, `evidence` 채워짐 | **pass** | `GET /internal/v1/sales/summary?period=THIS_MONTH` 1건, `evidence.value:0.125` |
| C-03 | **실제 BE 조회 4종** | 4개 경로 모두 정상 응답 | **보류** | BE 서버 미배포. 스텁으로만 확인 |

## 5. 공통 · 인증

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| E-01 | `GET /health` | 200 | **pass** | `{"status":"ok"}` |
| E-02 | `INTERNAL_AI_TOKEN` 미설정 시 헤더 없이 호출 | 통과(9/16 결정 기본 동작) | **pass** | 200 |
| E-03 | 존재하지 않는 경로 | 404 | **pass** | 404 |
| E-04 | 토큰 설정 + 헤더 없음 | 401 | **pass** | `UNAUTHORIZED`, `retryable:false` |
| E-05 | 토큰 설정 + 틀린 토큰 | 401 | **pass** | 401 |
| E-06 | 토큰 설정 + 맞는 토큰 | 200 | **pass** | 200 |
| E-07 | 토큰 설정 상태의 `/health` | 200 (LB 용이라 인증 제외) | **pass** | 200 |

## 6. 배포 환경에서만 발생하는 문제

| ID | Test Case | Expected | Status | Actual |
|---|---|---|---|---|
| D-01 | `ANTHROPIC_API_KEY` 빈 값으로 기동 후 호출 | 502, 재시도 가능 표시 | **pass** | `PROVIDER_ERROR`, `retryable:true` |
| D-02 | 환경변수 누락 시 기동 로그 | ERROR 로그로 누락 항목 출력 | **pass** | `환경변수가 비어 있다 — …: ANTHROPIC_API_KEY, BACKEND_BASE_URL(로컬 기본값 그대로다)` |
| D-03 | 설정이 틀린 상태의 `/health` | 200 (의도된 동작) | **pass** | 200 — **배포 성공 판단에 `/health` 만 쓰면 안 된다** |
| D-04 | `INSIGHT_LLM_TIMEOUT_SECONDS=0.001` | 504, 재시도 가능 표시 | **pass** | `PROVIDER_TIMEOUT`, `retryable:true` |

---

## 발견 사항

### ① 챗봇 답변에 마크다운이 섞여 나온다 — FE 확인 필요

C-01 응답에 `**평일 오후 …**` 형태의 볼드 마크다운이 포함됐다. 프롬프트에 서식 지시가
없는데 모델이 자연스럽게 쓴다.

FE 가 마크다운을 렌더링하면 문제없지만, **평문으로 표시하면 사용자에게 `**` 가 그대로
보인다.** 화면 확인이 필요하고, 평문이면 프롬프트에 서식 금지 지시를 넣으면 된다.

### ② 챗봇 BE 조회 4종은 여전히 스텁뿐이다 (C-03)

AI 파트에서 **유일하게 실제 BE 를 받아보지 못한 구간**이다. 필드명이 어긋나도
`.get()` 이라 에러 없이 `null` 로 빠져 **챗봇이 조용히 빈 답을 한다.**

BE 주소가 나오면 아래 한 줄로 끝난다.

```
uv run python -m devtools.llm_smoke --with-chat
```

### ③ `/health` 로는 배포 성공을 판단할 수 없다 (D-03)

의도된 설계다(LB 생존 확인용). 대신 **기동 로그의 ERROR 줄**(D-02)과
**F-02 예측 스모크**(LLM 비용 0원)를 배포 검증에 쓴다. `docs/DEPLOY.md` 참고.

### ④ 503 은 어떤 요청도 만들지 않는다

BE 와 "AI 서버 자체의 일시 장애/과부하"로 의미를 맞췄지만 과부하 차단을 두지 않아
발생 경로가 없다. BE 재시도 로직은 만들어둬도 현재는 타지 않는다.

---

## 재현 방법

```bash
# 스텁 BE (챗봇 툴 호출용)
uv run python -m devtools.stub_backend

# AI 서버
BACKEND_BASE_URL=http://localhost:9000 uv run uvicorn app.main:app --port 8000

# 장애 경로는 환경변수로 재현한다 — docs/DEPLOY.md "장애 응답 재현" 표 참고
```

단위 테스트는 `uv run pytest -q` 로 **124 passed**. 다만 이번 QA 에서 확인한 것들은
대부분 **단위 테스트가 통과하는 상태에서 실호출로만 드러나는 종류**라, 배포 전에는
위 표를 실제로 한 번 돌리는 편이 낫다.
