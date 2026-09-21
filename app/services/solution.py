"""위키 [AI] 단계4 §3 파이프라인 B. 카드 3장을 1회 호출로 생성.

파싱 실패 시 1회만 재시도한다 (재호출 비교 검증은 두지 않음 — 단계4 §3.3).
"""

import json
from datetime import date

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import solution as solution_prompt
from app.schemas.solution import SolutionCard, SolutionData, SolutionRequest, SolutionResponse

MAX_RETRY = 1
_WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _day_facts(target_date: str) -> tuple[str, bool]:
    code = _WEEKDAY_CODES[date.fromisoformat(target_date).weekday()]
    return code, code in ("SAT", "SUN")


def _parse(raw: str) -> list[SolutionCard] | None:
    try:
        data = json.loads(llm.strip_fence(raw))
        return [SolutionCard(**card) for card in data["solutionCards"]]
    except Exception:
        return None


async def generate(req: SolutionRequest) -> SolutionResponse:
    day_of_week, is_weekend = _day_facts(req.targetDate)
    metrics = req.metrics.model_dump()
    prompt = solution_prompt.build(metrics, req.targetDate, day_of_week, is_weekend)

    cards = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(solution_prompt.SYSTEM, prompt)
        cards = _parse(raw)
        if cards:
            break

    if cards is None:
        raise ApiError(500, "SOLUTION_GENERATION_FAILED", "솔루션 생성에 실패했습니다.")

    return SolutionResponse(
        data=SolutionData(
            targetDate=req.targetDate,
            solutionCards=cards,
            modelVersion=settings.llm_model,
        )
    )
