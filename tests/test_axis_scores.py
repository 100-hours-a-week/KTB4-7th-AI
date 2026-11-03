"""축 점수 측정 스크립트 — devtools/axis_scores.py.

여기서 중요한 건 "조용히 틀리지 않는다" 하나다. 같은 측정을 네 번 새로 짜는 동안 한 번
크게 틀렸고(`drop_duplicates()` 가 같은 시각 같은 메뉴를 산 다른 손님을 지워 행의 21.7%
소실), 그 숫자로 실험 기록을 썼다. 측정이 틀려도 결과가 그럴듯해 보이는 게 문제다.
근거: docs/experiments/2026-10-26-solution-axis-scores.md §7 정정
"""

import pandas as pd

from devtools.axis_scores import _ratio, build_metrics, business_hours

HOURS = {k: {"opensAt": "09:00", "closesAt": "24:00"} for k in ("WEEKDAY", "WEEKEND")}


def _rows(spec: list[tuple[str, int, str, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(day),
                "hour": hour,
                "menu": menu,
                "category": category,
                "amount": amount,
            }
            for day, hour, menu, category, amount in spec
        ]
    )


def _spread(days: list[str], hours: list[int]) -> pd.DataFrame:
    return _rows([(day, hour, "아메리카노", "coffee", 5000) for day in days for hour in hours])


WEEKDAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]


def test_자정을_넘긴_영업시간을_한_구간으로_잡는다():
    """POS 두 매장이 실제로 이렇다 — 0 시 매출이 9 시의 2.5 배다."""
    pos = _spread(WEEKDAYS, [*range(10, 24), 0, 1])
    assert business_hours(pos)["WEEKDAY"] == {"opensAt": "10:00", "closesAt": "02:00"}


def test_영업일의_절반이_안_되는_시각은_영업시간에서_뺀다():
    """주말 9 시가 영업일의 21~31% 다. 넣으면 유휴 비중이 부풀려진다."""
    pos = pd.concat(
        [
            _spread(WEEKDAYS, [10, 11, 12]),
            _spread(WEEKDAYS[:1], [9]),  # 닷새 중 하루만
        ]
    )
    assert business_hours(pos)["WEEKDAY"] == {"opensAt": "10:00", "closesAt": "13:00"}


def test_평일과_주말의_영업시간을_따로_잡는다():
    pos = pd.concat([_spread(WEEKDAYS, [9, 10]), _spread(["2026-03-07"], [12, 13])])
    hours = business_hours(pos)
    assert hours["WEEKDAY"] == {"opensAt": "09:00", "closesAt": "11:00"}
    assert hours["WEEKEND"] == {"opensAt": "12:00", "closesAt": "14:00"}


def test_하루_내내_팔리면_24시간_영업으로_잡는다():
    pos = _spread(WEEKDAYS, list(range(24)))
    assert business_hours(pos)["WEEKDAY"] == {"opensAt": "00:00", "closesAt": "24:00"}


def test_중간에_쉬는_매장은_한_구간으로_뭉개진다():
    """알고 있는 한계다 — 영업시간이 하루에 두 구간인 매장은 공백까지 영업으로 센다.

    POS 두 매장은 한 구간이라 이 경로를 타지 않는다. 타는 매장이 들어오면 유휴 비중이
    공백 시간만큼 부풀려진다.
    """
    pos = _spread(WEEKDAYS, [10, 11, 12, 17, 18, 19])
    assert business_hours(pos)["WEEKDAY"] == {"opensAt": "10:00", "closesAt": "20:00"}


def test_이전_기간이_0이면_증감률은_None이다():
    """BE 의 `changeRate` 와 같은 규칙 — 0 으로 나누지 않고 null 을 보낸다."""
    assert _ratio(100.0, 0.0) is None
    assert _ratio(150.0, 100.0) == 0.5


def test_이전_기간에만_있던_카테고리는_목록에_없다():
    """BE 의 categoryBreakdown 은 현재 기간만 훑는다 — 그 구멍까지 재현해야 한다."""
    cur = _rows([("2026-03-02", 12, "아메리카노", "coffee", 5000)])
    prev = _rows(
        [
            ("2026-02-23", 12, "아메리카노", "coffee", 4000),
            ("2026-02-23", 13, "케이크", "cake", 6000),
        ]
    )
    names = [c["name"] for c in build_metrics(cur, prev, HOURS, None)["categoryBreakdown"]]
    assert names == ["coffee"]


def test_메뉴_랭킹에_매출_상위와_변화_상위가_같이_든다():
    """변화 상위를 빼면 점수와 표시 행의 기준이 어긋난다 — `_menu_rows` 와 같은 이유다."""
    cur = _rows(
        [
            ("2026-03-02", 12, "아메리카노", "coffee", 100000),
            ("2026-03-02", 12, "유자차", "teabag", 1000),
        ]
    )
    prev = _rows(
        [
            ("2026-02-23", 12, "아메리카노", "coffee", 99000),
            ("2026-02-23", 12, "유자차", "teabag", 20000),
        ]
    )
    menus = build_metrics(cur, prev, HOURS, None)["menuRankings"]
    assert {m["menuName"] for m in menus} == {"아메리카노", "유자차"}
