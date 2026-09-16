"""위키 [AI] 단계4 §3 파이프라인 B. 카드 3장+인사이트를 1회 호출로 동시 생성.

파싱 실패 시 1회만 재시도한다 (재호출 비교 검증은 두지 않음 — 단계4 §3.3).
"""

import json

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import solution_v1
from app.schemas.solution import SolutionCard, SolutionRequest, SolutionResponse

MAX_RETRY = 1


def _parse(raw: str) -> tuple[list[SolutionCard], str] | None:
    try:
        data = json.loads(raw)
        cards = [SolutionCard(**card) for card in data["solutionCards"]]
        return cards, data["aiInsight"]
    except Exception:
        return None


async def generate(req: SolutionRequest) -> SolutionResponse:
    prompt = solution_v1.build(req.metrics.model_dump(), req.context.model_dump())

    result = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(solution_v1.SYSTEM, prompt)
        result = _parse(raw)
        if result:
            break

    if result is None:
        raise ApiError(500, "SOLUTION_GENERATION_FAILED", "솔루션 생성에 실패했습니다.")

    cards, ai_insight = result
    return SolutionResponse(
        targetDate=req.targetDate,
        solutionCards=cards,
        aiInsight=ai_insight,
        modelVersion=settings.llm_model,
        promptVersion=solution_v1.VERSION,
    )
