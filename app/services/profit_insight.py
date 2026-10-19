"""docs/api정의서.md SALES-06 순이익 인사이트. 계산은 BE, 여기서는 해석할 재료만 고른다.

BE 가 COST_INPUT_REQUIRED·EMPTY 를 걸러서 호출하지만, 통과하고도 매출이 전부 0원인 경우가
남아 그때는 LLM 을 부르지 않고 INSUFFICIENT_DATA 를 돌려준다. 파싱이 실패하면 1회만 재시도한다.
"""

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import profit_insight as prompt
from app.schemas.profit_insight import (
    DailyProfit,
    ProfitInsightData,
    ProfitInsightRequest,
    ProfitInsightResponse,
)
from app.services.insight import MAX_CHARS, MAX_RETRY, MAX_TOKENS, _parse

_WEEKDAYS = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")


def _day(item: DailyProfit) -> dict:
    return {
        "date": item.date.isoformat(),
        "dayOfWeek": _WEEKDAYS[item.date.weekday()],
        "netProfit": item.netProfit,
    }


def _highlights(days: list[DailyProfit]) -> dict:
    # dailyProfits 는 날짜 오름차순이라 max/min 이 동률에서 첫 원소, 즉 가장 이른 날짜를 돌려준다.
    # 2일 미만이면 최고·최저를 말할 수 없다.
    result = {"lossDays": sum(d.netProfit < 0 for d in days)}
    if len(days) >= 2:
        result["bestDay"] = _day(max(days, key=lambda d: d.netProfit))
        result["worstDay"] = _day(min(days, key=lambda d: d.netProfit))
    return result


async def generate(req: ProfitInsightRequest) -> ProfitInsightResponse:
    if req.summary.totalNetAmount == 0:
        return ProfitInsightResponse(
            message="순이익 인사이트에 필요한 데이터가 부족합니다.",
            status="INSUFFICIENT_DATA",
            data=ProfitInsightData(insights=[]),
        )

    summary = req.summary.model_dump(exclude_none=True)
    previous = req.summary.previousNetProfit
    if previous is not None:
        summary["netProfitDifference"] = req.summary.netProfit - previous
        if previous < 0:
            # BE 정책(docs/v2-profit-calculation-policy.md): 전기가 적자면 비율로 개선 여부를
            # 설명하지 않고 두 기간의 순이익과 차액을 함께 제시한다.
            summary.pop("netProfitChangeRate", None)

    user = prompt.build(
        summary,
        _highlights(req.dailyProfits),
        req.maxInsightCount,
        MAX_CHARS,
    )

    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(
            prompt.SYSTEM,
            user,
            max_tokens=MAX_TOKENS,
            timeout=settings.insight_llm_timeout_seconds,
        )
        # metrics=None → 금액 어림·수치 접지 검사를 건너뛴다. 매출 인사이트에는 2026-10-20
        # 에 넣었는데(A40 실측에서 금액_어림 77.5%·수치_정확 65.0% 가 그대로 나갔다),
        # 순이익 쪽은 지표 모양이 달라 접지 기준을 못 정했고 측정도 없다.
        insights = _parse(raw, req.maxInsightCount, None)
        if insights:
            break

    if not insights:
        raise ApiError(
            500, "PROFIT_INSIGHT_GENERATION_FAILED", "순이익 인사이트 생성에 실패했습니다."
        )

    return ProfitInsightResponse(
        message="순이익 인사이트를 생성했습니다.",
        status="COMPLETED",
        data=ProfitInsightData(insights=insights),
    )
