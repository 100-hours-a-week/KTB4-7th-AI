"""위키 [AI] 단계1 §7.3 / docs/api정의서.md SALES-04. 관찰형 인사이트 — 행동 처방은 하지 않는다.

영업일 14일 미만 판단은 BE 가 호출 전에 한다 — 이 요청엔 dataDays 가 없어 AI 가 직접
셀 수 없다. 다만 그 검사를 통과하고도 **지표가 사실상 비어 있는 경우**는 남아서,
그때는 LLM 을 부르지 않고 INSUFFICIENT_DATA 를 돌려준다(아래 _missing_data).
생성에 들어간 뒤 파싱이 실패하면 1회만 재시도한다.
"""

import json

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import insight as insight_prompt
from app.schemas.insight import InsightData, InsightRequest, InsightResponse

MAX_RETRY = 1

# 풀스택 확정 계약(2026-09-22). 화면에 그대로 뿌리는 문장이라 길이를 AI 가 보증한다.
MAX_CHARS = 100

# 풀스택 확정 계약(2026-09-22)의 어휘다. 노션 API 정의서 SALES-04 는 같은 자리에
# "SALES_DATA" 를 쓴다 — BE 가 자기 문서 기준으로 파싱하므로 이쪽을 따르고, 노션과
# 맞추도록 요청해둔다.
MISSING_SALES_HISTORY = "SALES_HISTORY"


def _missing_data(metrics) -> list[str] | None:
    """관찰할 재료가 없으면 사유를 돌려준다. 없으면 None 이라 생성으로 넘어간다.

    상세 지표 5종은 스키마에서 전부 기본값 []이라 salesSummary 만 있어도 요청이 통과한다.
    그 상태로 LLM 을 부르면 요약 한 줄을 돌려 쓰거나 "총매출은 0원입니다" 같은 문장을
    만들어 **200 으로 화면까지 나간다.** 에러가 아니라 내용이 비는 방식으로 드러나서
    더 늦게 발견된다.
    """
    summary = metrics.salesSummary
    if summary.orderCount == 0 or summary.totalSales == 0:
        return [MISSING_SALES_HISTORY]

    details = (
        metrics.salesTrend,
        metrics.weekdaySales,
        metrics.hourlySales,
        metrics.categorySales,
        metrics.menuRankings,
    )
    if not any(details):
        # 요약 한 줄 말고는 할 말이 없는데 AN-01 은 3불릿 화면이다.
        return [MISSING_SALES_HISTORY]
    return None


def _parse(raw: str, max_count: int) -> list[str] | None:
    """화면에 그대로 뿌릴 수 있는 문장 목록만 돌려준다. 어긋나면 None 이라 재시도한다.

    빈 문자열이 섞이면 AN-01 화면에 빈 불릿이 생기고, 개수가 넘치면 BE 가 요청한
    maxInsightCount 를 어긴다. 길이를 넘기면 카드가 밀린다. 셋 다 에러가 아니라 화면이
    이상해지는 방식으로 드러난다.
    """
    try:
        data = json.loads(llm.strip_fence(raw))
        insights = data["insights"]
    except Exception:
        return None

    if not isinstance(insights, list) or not all(isinstance(i, str) for i in insights):
        return None
    if not 1 <= len(insights) <= max_count:
        return None
    if not all(i.strip() for i in insights):
        return None
    if any(len(i) > MAX_CHARS for i in insights):
        return None
    return insights


async def generate(req: InsightRequest) -> InsightResponse:
    missing = _missing_data(req.metrics)
    if missing:
        # LLM 을 부르지 않는다 — 재료가 없으면 결과도 없고, 토큰만 쓴다.
        return InsightResponse(
            message="AI 인사이트에 필요한 데이터가 부족합니다.",
            status="INSUFFICIENT_DATA",
            data=InsightData(missingData=missing),
        )

    prompt = insight_prompt.build(req.metrics.model_dump(), req.maxInsightCount, MAX_CHARS)

    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(
            insight_prompt.SYSTEM, prompt, timeout=settings.insight_llm_timeout_seconds
        )
        insights = _parse(raw, req.maxInsightCount)
        if insights:
            break

    if not insights:
        raise ApiError(500, "INSIGHT_GENERATION_FAILED", "매출 분석 인사이트 생성에 실패했습니다.")

    return InsightResponse(
        message="매출 AI 인사이트를 생성했습니다.",
        status="COMPLETED",
        data=InsightData(targetMonth=req.targetMonth, insights=insights),
    )
