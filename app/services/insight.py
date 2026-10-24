"""위키 [AI] 단계1 §7.3 / docs/api정의서.md SALES-04. 관찰형 인사이트 — 행동 처방은 하지 않는다.

영업일 14일 미만 판단은 BE 가 호출 전에 한다 — 이 요청엔 dataDays 가 없어 AI 가 직접
셀 수 없다. 다만 그 검사를 통과하고도 **지표가 사실상 비어 있는 경우**는 남아서,
그때는 LLM 을 부르지 않고 INSUFFICIENT_DATA 를 돌려준다(아래 _missing_data).
생성에 들어간 뒤 파싱이 실패하면 1회만 재시도한다.

2026-10-24: 파싱은 됐지만 위반 문장이 버려져 요청한 개수(wanted)보다 적게
나오는 경우도 그 1회 재시도를 쓴다(`_complete_best_effort`) — 예전엔 뭐라도
받으면 멈춰서, 3개 중 1개가 걸러지면 재시도 없이 2개만 그대로 나갔다(점주 신고).
재시도해도 더 못 채우면 먼저 받은 걸 그대로 쓴다 — 없는 근거로 억지로 3개를
채우진 않는다.
"""

import json

from app.clients import llm
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import insight as insight_prompt
from app.schemas.insight import InsightData, InsightRequest, InsightResponse
from app.services.insight_focus import assign as assign_focus
from app.services.solution import _ROUNDED_AMOUNT, _ungrounded

MAX_RETRY = 1

# 풀스택 확정 계약(2026-09-22). 화면에 그대로 뿌리는 문장이라 길이를 AI 가 보증한다.
MAX_CHARS = 100

# 전역 기본값 2000 은 인사이트에 5 배 과다다. _parse 가 100자 넘는 문장을 거부하므로
# 합법적으로 가장 긴 응답이 `100자 × 3 + JSON` = 326자(약 400 토큰)다. 상한이 크면
# 모델이 공백 반복 루프에 빠질 때 그만큼 더 길게 돈다 — 전에 솔루션에서 상한을 올렸다가
# 최악이 136초에서 276초가 됐다. 잘려서 파싱이 실패하면 재시도가 도는데, 그건 100자
# 규칙을 이미 어긴 응답이라 어차피 거부됐을 응답이다.
#
# 솔루션은 못 내린다. 스키마 상한까지 쓴 응답이 4,912자, 실제로 나오던 분량이 1,222자라
# 2000 토큰도 빠듯하다.
MAX_TOKENS = 700

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


# 솔루션 쪽 검사기를 그대로 쓴다. 세 번째 복사본을 만들면 드리프트가 는다 — 채점기와
# 서비스가 어긋나서 측정이 틀린 사고가 이 레포에서 이미 여러 번 났다. 공통 모듈로 빼는
# 게 맞지만 그건 별도 작업으로 두고, 지금은 로컬 모델에서 드러난 결함부터 막는다.
_INSIGHT_BLOCKING = ("ROUNDED_AMOUNT", "UNGROUNDED_NUMBER")


def _violations(sentence: str, metrics: dict) -> list[str]:
    """재시도로 보낼 이유. 비어 있으면 통과다.

    둘 다 프롬프트에 규칙이 있는데 지켜지지 않는다. A40 실측(n=40, Qwen3-32B)에서
    금액_어림_없음 77.5%, 수치_정확 65.0% 였고 **그대로 점주에게 나갔다** — 인사이트에는
    솔루션과 달리 차단 게이트가 아예 없었다. Claude 로 잴 때는 둘 다 100% 라 안 보였다.
    """
    reasons = []
    if _ROUNDED_AMOUNT.search(sentence):
        reasons.append("ROUNDED_AMOUNT")
    if _ungrounded(sentence, metrics):
        reasons.append("UNGROUNDED_NUMBER")
    return reasons


def _parse(raw: str, max_count: int, metrics: dict | None) -> list[str] | None:
    """화면에 그대로 뿌릴 수 있는 문장 목록만 돌려준다. 어긋나면 None 이라 재시도한다.

    빈 문자열이 섞이면 AN-01 화면에 빈 불릿이 생기고, 개수가 넘치면 BE 가 요청한
    maxInsightCount 를 어긴다. 길이를 넘기면 카드가 밀린다. 셋 다 에러가 아니라 화면이
    이상해지는 방식으로 드러난다.

    metrics 를 주면 금액 어림·지표에 없는 수치까지 검사해 위반 문장을 버린다. None 이면
    그 검사를 건너뛴다 — 순이익 인사이트(app/services/profit_insight.py)가 그렇다.
    거기는 지표 모양이 달라 접지 기준을 아직 못 정했고, 로컬 모델로 측정한 적도 없다.
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

    # 위반 문장만 버리고 남은 걸 돌려준다. 한 문장도 안 남으면 None 이라 재시도한다 —
    # 솔루션의 "최소 1장·최대 3장" 과 같은 판단이다(2026-10-17). 세 문장 중 하나가
    # 틀렸다고 셋을 다 버리면 그날 인사이트가 통째로 없어진다.
    if metrics is None:
        return insights
    kept = [sentence for sentence in insights if not _violations(sentence, metrics)]
    return kept or None


async def _complete_best_effort(
    system: str, user: str, wanted: int, metrics: dict | None
) -> list[str] | None:
    """wanted 개를 받을 때까지 MAX_RETRY 번 안에서 재시도하고, 그래도 모자라면
    그때까지 받은 것 중 가장 많이 건진 걸 돌려준다 — 0 보다는 낫다(2026-10-24,
    점주 신고 — 3개 요청했는데 2개만 보임).

    `_parse` 가 위반 문장만 버려서(ROUNDED_AMOUNT 등) 모델이 wanted 개를 만들어도
    결과가 그보다 적게 나갈 수 있다. 예전엔 "뭔가 받으면 바로 멈춘다"(모자라도
    재시도 안 함)라 그 위반이 재시도 없이 그대로 화면에 나갔다. wanted 는
    assign_focus 가 실제로 찾은 축 수라 — 모자란 건 재료 부족이 아니라 그날 생성
    품질 문제다. 재시도로 더 받으면 쓰고, 더 못 받으면 먼저 받은 걸 그대로 쓴다.
    """
    best: list[str] | None = None
    for _ in range(MAX_RETRY + 1):
        raw = await llm.complete(
            system, user, max_tokens=MAX_TOKENS, timeout=settings.insight_llm_timeout_seconds
        )
        parsed = _parse(raw, wanted, metrics)
        if parsed and (best is None or len(parsed) > len(best)):
            best = parsed
        if best and len(best) >= wanted:
            break
    return best


async def generate(req: InsightRequest) -> InsightResponse:
    missing = _missing_data(req.metrics)
    if missing:
        # LLM 을 부르지 않는다 — 재료가 없으면 결과도 없고, 토큰만 쓴다.
        return InsightResponse(
            message="AI 인사이트에 필요한 데이터가 부족합니다.",
            status="INSUFFICIENT_DATA",
            data=InsightData(missingData=missing),
        )

    # exclude_none: 값이 없는 지표는 프롬프트에서 아예 뺀다. "null 이면 언급하지 마세요"로
    # 부탁하는 것보다 안 보여주는 쪽이 확실하다 — 코드펜스 때 배운 것과 같은 이유다.
    metrics = req.metrics.model_dump(exclude_none=True)
    # 문장마다 쓸 근거 지표를 코드가 배정한다 — 6 종을 통째로 주면 모델이 엉뚱한 값을
    # 집는다(`수치_정확` 68%, n=48). app/services/insight_focus.py 참고.
    focus = assign_focus(metrics, req.maxInsightCount)
    prompt = insight_prompt.build(focus, MAX_CHARS)

    # 배정한 수만큼만 받는다. _missing_data 를 통과했으면 축이 둘 이상 남으므로 0 은 아니다.
    wanted = len(focus) or req.maxInsightCount

    insights = await _complete_best_effort(insight_prompt.SYSTEM, prompt, wanted, metrics)

    if not insights:
        raise ApiError(500, "INSIGHT_GENERATION_FAILED", "매출 분석 인사이트 생성에 실패했습니다.")

    return InsightResponse(
        message="매출 AI 인사이트를 생성했습니다.",
        status="COMPLETED",
        data=InsightData(targetMonth=req.targetMonth, insights=insights),
    )
