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

# 풀스택 확정 계약(2026-09-22). 화면에 그대로 뿌리는 문장이라 길이를 AI 가 보증한다.
MAX_CHARS = 100

# BE 응답 제한이 30초다. 재시도 1회를 포함해도 그 안에 끝나야 한다 — 넘기면 BE 는 이미
# 끊은 뒤이고 이쪽만 토큰을 계속 태운다. 실측 3.9~4.6초(2026-09-22, sonnet-4-5)라
# 12초면 약 3배 여유고 최악 24초로 들어온다. 전역 LLM_TIMEOUT_SECONDS(60)는 솔루션이
# 15~20초를 쓰고 있어 함께 낮출 수 없다.
TIMEOUT_SECONDS = 12.0


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
    prompt = insight_prompt.build(req.metrics.model_dump(), req.maxInsightCount, MAX_CHARS)

    insights = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(insight_prompt.SYSTEM, prompt, timeout=TIMEOUT_SECONDS)
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
