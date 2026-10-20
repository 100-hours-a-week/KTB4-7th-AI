"""metrics.conditionPatterns 수신 (2026-10-19 BE 확정, BE PR #492 · 이슈 #194).

받아서 버리지 않는 것까지만 확인한다. 프롬프트·점수식에는 아직 연결하지 않았다 —
#187 인사이트 게이트의 A40 효과를 먼저 재야 입력 축을 늘린 영향과 섞이지 않는다.
"""

from app.schemas.common import Metrics
from app.services.solution import _metric_numbers

# BE PR #492 의 ConditionPatternsServiceTest 가 단언하는 실제 값.
BE_SAMPLE = {
    "condition": "RAIN",
    "basisWeeks": 12,
    "thresholdMm": 1.0,
    "sampleDays": 5,
    "baselineDays": 5,
    "sampleWeekdayRatio": 0.6,
    "baselineWeekdayRatio": 0.8,
    "menus": [
        {
            "menuName": "아이스 아메리카노",
            "avgQuantity": 4,
            "baselineAvgQuantity": 8,
            "vsBaseline": -0.5,
            "avgSales": 1000,
            "baselineAvgSales": 2000,
        }
    ],
}

BASE = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
}


def test_BE_가_보내는_모양을_그대로_받는다():
    metrics = Metrics(**BASE, conditionPatterns=[BE_SAMPLE])

    pattern = metrics.conditionPatterns[0]
    assert pattern.condition == "RAIN"
    assert pattern.basisWeeks == 12
    assert pattern.sampleWeekdayRatio == 0.6
    assert pattern.baselineWeekdayRatio == 0.8

    menu = pattern.menus[0]
    assert menu.menuName == "아이스 아메리카노"
    assert menu.vsBaseline == -0.5
    assert menu.avgSales == 1000


def test_금액_수량은_정수_비율은_소수다():
    """AGENTS.md 공통 원칙. BE 도 같은 규약으로 보낸다(PR #492 적용 정책)."""
    menu = Metrics(**BASE, conditionPatterns=[BE_SAMPLE]).conditionPatterns[0].menus[0]

    assert isinstance(menu.avgQuantity, int)
    assert isinstance(menu.avgSales, int)
    assert isinstance(menu.vsBaseline, float)


def test_생략되면_빈_리스트다():
    """BE 는 표본 미달·관측 지점 미연결이면 배열 일부나 null 이 아니라 전체를 생략한다.

    생략 시 지금까지와 똑같이 동작해야 한다 — 이 필드를 안 보내는 BE 버전도 있다.
    """
    assert Metrics(**BASE).conditionPatterns == []


def test_menus_가_비어도_받는다():
    pattern = Metrics(**BASE, conditionPatterns=[{**BE_SAMPLE, "menus": []}])
    assert pattern.conditionPatterns[0].menus == []


def test_접지_허용_집합에_금액이_들어간다():
    """프롬프트에 연결하지 않아도 solution.py 가 metrics 를 통째로 넘기므로 넓어진다.

    3자리 이상은 avgSales·baselineAvgSales 와 thresholdMm 의 백분율 표기뿐이다.
    2자리 이하는 _ungrounded 가 이미 "실행 지시" 로 통과시켜 변화가 없다.
    """
    dumped = Metrics(**BASE, conditionPatterns=[BE_SAMPLE]).model_dump(exclude_none=True)
    added = _metric_numbers({"conditionPatterns": dumped["conditionPatterns"]})

    three_or_more = {n for n in added if len(n.lstrip("-").split(".")[0]) >= 3}
    assert three_or_more == {"100", "1000", "2000"}


def test_프롬프트에_아직_연결되지_않았다():
    """3단계에서 연결한다(이슈 #194). 평일 비중 교란과 인과 게이트 조정을 같이 봐야 한다.

    이 테스트가 깨지면 연결이 된 것이다 — 그때 이 테스트를 지우고
    devtools/grade.py 의 "conditionPatterns 미도입" 주석도 같이 고친다.
    """
    from app.services.solution_focus import assign

    metrics = {**BASE, "conditionPatterns": [BE_SAMPLE]}
    focus = assign(metrics)

    assert all("conditionPatterns" not in item for item in focus)
