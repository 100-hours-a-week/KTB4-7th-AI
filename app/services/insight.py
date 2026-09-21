"""위키 [AI] 단계1 §7.3 / docs/api정의서.md SALES-04. 관찰형 인사이트 — 행동 처방은 하지 않는다.

데이터 부족(14일 미만) 판단은 BE 가 호출 전에 한다 — 이 요청엔 dataDays 가 없어 AI 는
스스로 판단할 수 없다. AI 는 항상 생성을 시도하고, 파싱 실패 시 1회만 재시도한다.
"""

import json

from app.clients import llm
from app.core.errors import ApiError
from app.prompts import insight as insight_prompt
from app.schemas.insight import InsightData, InsightRequest, InsightResponse

MAX_RETRY = 1


def _parse(raw: str) -> list[str] | None:
    try:
        data = json.loads(llm.strip_fence(raw))
        insights = data["insights"]
        if not isinstance(insights, list) or not all(isinstance(i, str) for i in insights):
            return None
        return insights
    except Exception:
        return None


async def generate(req: InsightRequest) -> InsightResponse:
    prompt = insight_prompt.build(req.metrics.model_dump(), req.maxInsightCount)

    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(insight_prompt.SYSTEM, prompt)
        insights = _parse(raw)
        if insights is not None:
            break

    if insights is None:
        raise ApiError(500, "INSIGHT_GENERATION_FAILED", "매출 분석 인사이트 생성에 실패했습니다.")

    return InsightResponse(
        message="매출 AI 인사이트를 생성했습니다.",
        status="COMPLETED",
        data=InsightData(targetMonth=req.targetMonth, insights=insights),
    )
