# POST /internal/v2/ai/profit-insights 설계

- 날짜: 2026-10-12
- 이슈: #148
- 근거 계약: `docs/api정의서.md` SALES-06 · `POST /internal/v2/ai/profit-insights` (2026-10-12 신규 반영)
- 참고 구현: 기존 `/internal/v1/ai/sales-insights` (`app/api/insights.py`, `app/schemas/insight.py`,
  `app/services/insight.py`, `app/prompts/insight.py`)

## 배경

매출분석(V1) 화면의 "AI가 발견했어요" 3불릿과 동일한 패턴으로, 순이익(V2) 탭에서도 순이익
기반 관찰형 인사이트 1~3개를 생성해야 한다. BE가 `GET /v2/sales/profit-analyses`에서 계산한
확정 지표만 받아 해석하고, 금액·비율은 재계산하지 않는다.

기존 v1 인사이트와 버전(`/internal/v1/ai/*` vs `/internal/v2/ai/*`)·지표 구조가 전혀 달라
완전히 새 파일로 분리한다(기존 insights.py 계열을 건드리지 않음).

## 파일 구조

```
app/schemas/profit_insight.py   — 요청/응답 모델
app/prompts/profit_insight.py   — SYSTEM/USER 템플릿, VERSION="2026-10-12"
app/services/profit_insight.py  — 안전망·파싱·재시도·생성
app/api/profit_insights.py      — 라우터 (prefix="/internal/v2/ai")
tests/test_profit_insights.py
```

`app/main.py`에 라우터 import·`include_router` 2줄 추가.

## 스키마

```python
class ProfitPeriod(Contract):
    startDate: str
    endDate: str


class ProfitSummary(Contract):
    totalNetAmount: int
    ingredientCost: int
    fixedCost: int
    netProfit: int
    netProfitRate: float
    previousNetProfit: int | None = None
    netProfitChangeRate: float | None = None


class DailyProfitPoint(Contract):
    date: str
    netProfit: int


class ProfitInsightRequest(Contract):
    storeId: int
    period: ProfitPeriod
    summary: ProfitSummary
    dailyProfits: list[DailyProfitPoint]  # 계약상 필수
    maxInsightCount: int  # 계약상 필수 (BE는 항상 3을 보냄)


class ProfitInsightData(Contract):
    insights: list[str] = []  # INSUFFICIENT_DATA 때도 빈 배열(계약 예시와 일치)


class ProfitInsightResponse(Contract):
    status: Literal["COMPLETED", "INSUFFICIENT_DATA"]
    data: ProfitInsightData
```

`message` 필드는 넣지 않는다 — 계약 문서가 성공 응답(`COMPLETED`/`INSUFFICIENT_DATA`) 예시에
`message`를 포함하지 않음을 명시했다(`docs/api정의서.md` 1825~1826번 줄). 401/422/500은
`ApiError`를 던지면 기존 전역 핸들러(`app/core/errors.py`)가 `{"message":...,"data":null}`
형태로 처리하므로 이 스키마와 무관하다.

음수 금액(`netProfit`, `previousNetProfit`)은 계약상 허용이라 `int`에 별도 제약을 걸지 않는다.

## 서비스 로직 (`app/services/profit_insight.py`)

```python
MAX_RETRY = 1
MAX_CHARS = 100
# v1 insight.py와 동일 근거: 합법적으로 가장 긴 응답이 100자×3+JSON ≈ 326자(≈400 토큰).
MAX_TOKENS = 700


def _insufficient(summary: ProfitSummary, daily: list[DailyProfitPoint]) -> bool:
    """BE가 COST_INPUT_REQUIRED/EMPTY를 걸러주지만, 그 게이트를 통과했는데도
    관찰할 재료가 없는 경우(전부 0원)를 AI 쪾에서 한 번 더 막는다 — v1 insight.py의
    _missing_data와 같은 이유(과거 "총매출 0원" 200 노출 사고)."""
    return (
        summary.totalNetAmount == 0
        and summary.netProfit == 0
        and all(d.netProfit == 0 for d in daily)
    )


def _parse(raw: str, max_count: int) -> list[str] | None:
    """v1 insight.py._parse와 동일한 검증: JSON 파싱, 1~max_count개, 공백 아님, 100자 이하."""


async def generate(req: ProfitInsightRequest) -> ProfitInsightResponse:
    if _insufficient(req.summary, req.dailyProfits):
        return ProfitInsightResponse(status="INSUFFICIENT_DATA", data=ProfitInsightData())

    prompt = profit_insight_prompt.build(req, MAX_CHARS)
    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(
            profit_insight_prompt.SYSTEM,
            prompt,
            max_tokens=MAX_TOKENS,
            timeout=settings.insight_llm_timeout_seconds,  # BE 읽기 제한(30s)과 동일한 예산 — v1과 공유
        )
        insights = _parse(raw, req.maxInsightCount)
        if insights:
            break

    if not insights:
        raise ApiError(
            500, "PROFIT_INSIGHT_GENERATION_FAILED", "순이익 인사이트 생성에 실패했습니다."
        )

    return ProfitInsightResponse(status="COMPLETED", data=ProfitInsightData(insights=insights))
```

에러 메시지는 계약 문서 500 예시(`docs/api정의서.md` 1829번 줄) 문구를 그대로 쓴다.

지표 종류가 v1(6종)보다 적어 `insight_focus.py` 같은 배정 로직 없이 지표 전체를 한 번에
프롬프트에 넣는 단순한 버전으로 시작한다. 실측에서 수치 정확도가 떨어지면 그때 focus 배정
도입을 검토한다(지금은 과설계).

## 프롬프트 (`app/prompts/profit_insight.py`)

v1 인사이트의 고정 규칙을 그대로 가져온다: 직접 계산 금지, 금액은 지표 값 그대로 천 단위로
표기, 비율은 소수→문장에서 백분율로 변환하되 반올림 금지, 처방 금지(관찰만).

순이익 전용 추가 규칙:

- `netProfitRate`/`netProfitChangeRate`가 0.6/0.2면 "60%"/"20%"로 쓴다.
- `previousNetProfit`/`netProfitChangeRate`가 `null`이면 이전 기간과 비교하지 않는다.
- **연속성 표현**: `dailyProfits`에서 실제로 방향이 바뀌지 않고 이어지는 구간에서만
  "N일 연속 증가/감소"를 허용한다. N은 실제로 센 연속 일수와 정확히 일치해야 하고,
  중간에 방향이 바뀌면 그 구간까지만 말한다. 추측이나 과장은 금지한다.

VERSION = "2026-10-12".

## 라우터 (`app/api/profit_insights.py`)

```python
router = APIRouter(prefix="/internal/v2/ai", dependencies=[Depends(verify_internal_token)])


@router.post("/profit-insights", response_model=ProfitInsightResponse)
async def generate_profit_insight(req: ProfitInsightRequest) -> ProfitInsightResponse:
    return await profit_insight_service.generate(req)
```

인증(`verify_internal_token`)은 기존 공유 의존성을 그대로 재사용한다. 401/422 문구가 계약
문서 예시와 실제 공유 핸들러 문구가 다르지만, 이는 기존 v1 엔드포인트들도 이미 같은 차이를
가진 기존 동작이라 이번 작업 범위에서 건드리지 않는다.

## 테스트 계획 (`.claude/skills/ai-endpoint` 순서: schema → 실패 테스트 → service → router → curl)

1. 스키마: 계약 예시 요청이 그대로 파싱되는지, `previousNetProfit`/`netProfitChangeRate`
   `null` 허용 확인.
2. **실패 테스트 먼저(TDD)**:
   - 빈 배열/개수초과/100자초과 응답 → 재시도 후 500
   - `_insufficient` 조건 충족 → `INSUFFICIENT_DATA`, `llm.complete` 호출 안 됐는지
     (`assert_not_called`)
   - 인증 없음 → 401 (`tests/test_auth.py` 패턴 재사용)
3. 서비스 유닛 테스트: `_parse`, `_insufficient` 개별 테스트
4. 라우터 통합 테스트: `TestClient` + `llm.complete` monkeypatch
5. **연속성 표현 실측** (요금 발생, 실행 전 승인 필요): `devtools/llm_smoke` 류로 더미
   `dailyProfits` 두 종류(① 실제 연속 증가/감소 구간, ② 증가·감소가 뒤섞인 구간)를 n회(예 10회)
   실호출. "N일 연속" 문장의 N이 실제 연속 일수와 일치하는지, 혼재 구간에서 거짓 연속성을
   주장하지 않는지 채점. 기준(예: 90% 이상 정확) 미달 시 SYSTEM에서 연속성 언급을 v1처럼
   전면 금지하는 쪽으로 되돌린다.
6. curl 검증: `devtools/stub_backend` 기동 후 계약 예시 요청으로 실제 서버 호출 확인.

## 범위 밖

- `docs/api정의서.md`/ERD 수정 — BE 담당 문서라 AI가 직접 고치지 않는다(이미 BE가 반영함).
- `GET /v2/sales/profit-analyses`, `POST /internal/v2/profit-analysis-jobs` — 헥터/BE 영역.
- focus 배정 로직 도입 — 실측 전까지는 불필요.
