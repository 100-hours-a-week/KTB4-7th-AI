"""metrics.conditionPatterns 수신 (2026-10-19 BE 확정, BE PR #492 · 이슈 #194).

이 파일은 **BE 가 실제로 보내는 그 값**이 끝까지 가는지만 본다 — `BE_SAMPLE` 은 BE PR
#492 의 `ConditionPatternsServiceTest` 가 단언하는 값 그대로다. 점수식·게이트 규칙
자체는 `tests/test_solution_focus.py` 의 "강수 패턴" 절에서 전용 픽스처로 잰다.

2026-10-31: 프롬프트·점수식 연결이 #247·#254 로 끝났다. 그전까지 여기 있던
`test_프롬프트에_아직_연결되지_않았다` 는 "연결되면 깨지라고" 둔 감시였는데 **안 깨진
채로 연결이 지나갔다.** 그 테스트의 지표에 `weatherContext` 가 없었고, 강수 패턴은
날씨 축에 묶여 실리기 때문에 날씨 축이 후보에 못 올라가 늘 통과했다. 같은 자리를
"BE 샘플이 날씨 카드에 실린다" 를 단정하는 쪽으로 바꿨다.
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


# 비 예보가 있고 기온이 구성을 갈라놓는 날. 날씨 축이 뽑히는 조건이고, 강수 패턴은
# 그 축에 묶여 실린다(app/services/solution_focus.py::_condition_score 주석).
_RAINY_FORECAST = {
    "basisDateTime": "2026-10-31 08:00",
    "skyText": "흐리고 비",
    "minTempC": 12,
    "maxTempC": 34,
    "maxPop": 0.8,
    "rainHours": [12, 13, 14],
    "isNotable": True,
}
# `_condition_score` 가 하루 매출로 나누므로 집계 기간이 없으면 점수가 안 난다.
_SUMMARY_WITH_PERIOD = {**BASE["salesSummary"], "period": "2026-10-01~2026-10-28"}


def test_BE_샘플이_날씨_카드에_그대로_실린다():
    """BE 가 보내는 값이 `Metrics` → `assign` → focus 까지 가는지 본다.

    축 선정 규칙은 여기서 재지 않는다 — `tests/test_solution_focus.py` 가 전용 픽스처로
    잰다. 이 테스트가 잡는 건 **BE 계약이 흘러가다 끊기는 것**이다.
    """
    from app.services.solution_focus import assign

    focus = assign(
        {
            **BASE,
            "salesSummary": _SUMMARY_WITH_PERIOD,
            "weatherContext": _RAINY_FORECAST,
            "conditionPatterns": [BE_SAMPLE],
        }
    )

    weather_cards = [item for item in focus if "weatherContext" in item]
    assert len(weather_cards) == 1, "날씨 축이 뽑히지 않으면 이 테스트가 재려는 게 사라진다"
    assert "conditionPatterns" in weather_cards[0], "강수 패턴이 날씨 카드에 실리지 않았다"
    assert weather_cards[0]["conditionPatterns"] == [BE_SAMPLE]


def test_오늘_비_예보가_없으면_BE_샘플도_실리지_않는다():
    """ "비 올 때는 이렇습니다" 는 비 오는 날에만 할 말이다 — 맑은 날엔 빠진다."""
    from app.services.solution_focus import assign

    clear = {**_RAINY_FORECAST, "skyText": "맑음", "maxPop": 0.1, "rainHours": []}
    focus = assign(
        {
            **BASE,
            "salesSummary": _SUMMARY_WITH_PERIOD,
            "weatherContext": clear,
            "conditionPatterns": [BE_SAMPLE],
        }
    )

    assert all("conditionPatterns" not in item for item in focus)
