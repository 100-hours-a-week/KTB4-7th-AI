"""위키 [AI] 단계1 §7.3. 관찰형 인사이트 — 행동 처방은 하지 않는다.

dataDays 14일 미만은 LLM을 호출하지 않고 코드단에서 즉시 INSUFFICIENT_DATA 를 반환한다.
그 외 재시도 규칙은 solution.py 와 동일 (파싱 실패 1회 재시도).
"""

import json

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import insight_v1
from app.schemas.insight import Insight, InsightRequest, InsightResponse

MIN_DATA_DAYS = 14
MAX_RETRY = 1


def _parse(raw: str) -> list[Insight] | None:
    try:
        data = json.loads(raw)
        return [Insight(**item) for item in data["insights"]]
    except Exception:
        return None


async def generate(req: InsightRequest) -> InsightResponse:
    if req.dataDays < MIN_DATA_DAYS:
        return InsightResponse(
            status="INSUFFICIENT_DATA",
            insights=[],
            modelVersion=settings.llm_model,
            promptVersion=insight_v1.VERSION,
        )

    prompt = insight_v1.build(req.metrics.model_dump())

    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(insight_v1.SYSTEM, prompt)
        insights = _parse(raw)
        if insights is not None:
            break

    if insights is None:
        raise ApiError(500, "INSIGHT_GENERATION_FAILED", "인사이트 생성에 실패했습니다.")

    return InsightResponse(
        status="SUCCESS",
        insights=insights,
        modelVersion=settings.llm_model,
        promptVersion=insight_v1.VERSION,
    )
