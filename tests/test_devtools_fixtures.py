"""devtools 픽스처가 현재 스키마와 맞는지 본다.

`devtools/` 는 CI 에서 실행되지 않는다. 계약이 바뀌어도 아무도 모르고, 정작 검증하려고
스크립트를 돌리는 순간에야 422 로 드러난다.

실제로 그렇게 됐다. PR #87 에서 `Metrics` 를 `InsightMetrics` 로 분리할 때
`contract_check.py` 는 고치고 `llm_smoke.py` 를 안 고쳐서, 2026-09-22 부터 6일간
`llm_smoke` 의 인사이트 검증이 422 로 죽어 있었다(#99, 제나 발견).

그 사이 실호출 검증은 전부 curl 로 직접 했기 때문에 도구가 깨진 걸 아무도 몰랐다.
**계약을 바꾸면 여기서 먼저 실패해야 한다.**

실호출은 하지 않는다. 스키마 대조만으로 픽스처가 낡은 것은 전부 잡힌다.
"""

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.schemas.forecast import ForecastRequest
from app.schemas.insight import InsightRequest
from app.schemas.solution import SolutionRequest
from devtools import contract_check, llm_smoke

SCHEMAS = {
    "forecast": ForecastRequest,
    "solutions": SolutionRequest,
    "sales-insights": InsightRequest,
    "chat": ChatRequest,
}


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_contract_check_예시가_현재_스키마와_맞는다(name):
    """`--example` 이 출력하는 요청 모양을 BE 에 그대로 보낸다. 낡으면 BE 를 잘못 안내한다."""
    assert name in contract_check.EXAMPLES, f"{name} 예시가 빠졌다"
    SCHEMAS[name](**contract_check.EXAMPLES[name])


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_contract_check_예시에_조용히_버려지는_필드가_없다(name):
    """`extra="ignore"` 라 오타나 옛 필드명은 422 없이 사라진다.

    예시가 그 상태면 BE 가 보낸 지표가 LLM 에 닿지 않는데도 200 이 나간다.
    """
    dropped = contract_check.ignored_keys(SCHEMAS[name], contract_check.EXAMPLES[name])
    assert not dropped, f"{name} 예시에 스키마에 없는 필드: {dropped}"


def test_llm_smoke_솔루션_픽스처가_현재_스키마와_맞는다():
    SolutionRequest(
        storeId=1024,
        salesAnalysisId=771,
        targetDate="2026-09-21",
        triggerType="UPLOAD",
        metrics=llm_smoke.METRICS,
    )


def test_llm_smoke_인사이트_픽스처가_현재_스키마와_맞는다():
    """#99 회귀. 솔루션용 METRICS 를 인사이트에 재사용해 422 가 났다."""
    InsightRequest(
        storeId=1024,
        salesAnalysisId=771,
        targetMonth="2026-08",
        triggerType="UPLOAD",
        metrics=llm_smoke.INSIGHT_METRICS,
        maxInsightCount=3,
    )


def test_솔루션과_인사이트_픽스처는_서로_다르다():
    """두 지표는 2026-09-22 계약으로 갈라졌다. 한쪽을 다른 쪽에 재사용하면 422 다."""
    assert llm_smoke.METRICS != llm_smoke.INSIGHT_METRICS

    with pytest.raises(ValidationError):
        InsightRequest(
            storeId=1,
            salesAnalysisId=1,
            targetMonth="2026-08",
            triggerType="UPLOAD",
            metrics=llm_smoke.METRICS,  # 솔루션용을 인사이트에 — #99 가 이 상태였다
        )
