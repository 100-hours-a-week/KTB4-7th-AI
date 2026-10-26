"""카드별 근거 지표 배정 — app/services/solution_focus.py.

프롬프트로 "각 카드는 서로 다른 지표를 근거로" 라고 지시해도 실측 통과율이 66% 였다.
배정을 코드로 옮긴 이유라, 여기서 가장 중요한 건 "겹치지 않는다" 하나다.
"""

import pytest

from app.services.solution_focus import (
    MAX_CARDS,
    _menu_score,
    _menu_share_delta,
    assign,
    derive,
)

METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "predictedSalesToday": 1250000,
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
        {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
    ],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
}


def test_카드끼리_같은_지표를_받지_않는다():
    focus = assign(METRICS)

    keys = [key for card in focus for key in card]
    assert len(keys) == len(set(keys)), f"지표가 두 카드에 들어갔다: {keys}"


def test_예측과_전체매출은_한_카드로_묶인다():
    """둘 다 "오늘 전체 매출" 이라 따로 두면 netSales 가 두 카드에 나온다."""
    focus = assign(METRICS)

    total = next(card for card in focus if "salesSummary" in card)
    assert "predictedSalesToday" in total


def test_시간대_격차가_크면_첫_카드가_된다():
    """30,000 대 92,000 이면 격차 점수가 커피 쏠림(0.62)보다 높다."""
    focus = assign(METRICS)

    assert "hourlyProfile" in focus[0]


def test_카드는_세_장을_넘지_않는다():
    assert len(assign(METRICS)) <= MAX_CARDS


def test_비어_있는_지표는_배정하지_않는다():
    focus = assign(
        {
            "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
            "hourlyProfile": [],
            "categoryBreakdown": [],
        }
    )

    assert len(focus) == 1
    assert "salesSummary" in focus[0]


def test_비교_기간이_없어도_배정은_된다():
    """첫 업로드 매장은 vsPrevPeriod 가 null 이다 — 점수는 0 이지만 빼지는 않는다."""
    metrics = {**METRICS, "salesSummary": {"netSales": 1183600, "vsPrevPeriod": None}}
    focus = assign(metrics)

    assert len(focus) == 3
    assert any("salesSummary" in card for card in focus)


def test_지표가_하나도_없으면_빈_배정이다():
    assert assign({}) == []


def test_배정된_근거로만_쓰면_채점기의_카드_지표_중복이_구조적으로_불가능하다():
    """배정이 실제로 결함을 막는지 채점기로 되짚는다.

    카드가 자기 근거의 숫자만 인용하면 `카드_지표_중복없음` 이 참이어야 한다 — 참이 아니면
    배정이 결함을 못 막는다는 뜻이고, 그러면 이 변경 자체가 의미가 없다.
    """
    import json

    from devtools.grade import grade_solution

    focus = assign(METRICS)
    # 각 카드가 자기 근거의 숫자 하나만 인용한 응답을 만든다
    quotes = [
        "평일 14시 매출은 30,000원입니다.",
        "커피 매출 비중은 62%입니다.",
        "오늘 예상 매출은 1,250,000원입니다.",
    ]
    raw = json.dumps(
        {
            "solutionCards": [
                {
                    "rankNo": index + 1,
                    "title": f"카드{index + 1}",
                    "summaryText": "요약",
                    "detailText": "실행 1.\n실행 2.\n효과를 늘릴 수 있습니다.",
                    "evidence": quotes[index],
                }
                for index in range(len(focus))
            ]
        },
        ensure_ascii=False,
    )

    # 배정이 겹치지 않으므로 채점기도 중복으로 보지 않아야 한다
    assert grade_solution(raw, METRICS)["카드_지표_중복없음"] is True


def test_영업시간_밖_0원_행은_최저로_뽑지_않는다():
    """24 시간이 통째로 오면 min=0 이라 격차 점수가 늘 1.0 으로 포화되고, "가장 낮은
    시간대" 가 0 시로 뽑힌다. "0 시에 뭘 하세요" 는 점주가 쓸 수 없는 솔루션이다.

    요청에 영업시간이 없어서 "닫은 시간" 과 "열었는데 안 팔린 시간" 을 구분할 방법이
    없다 — 둘 다 쓸 수 없으므로 최저 판단에서 뺀다.
    """
    hours = [
        {"dayType": "WEEKDAY", "hour": h, "amount": 0 if h < 8 or h >= 22 else 50000 + h * 1000}
        for h in range(24)
    ]
    focus = assign({**METRICS, "hourlyProfile": hours})

    rows = next(item["hourlyProfile"] for item in focus if "hourlyProfile" in item)
    assert all(row["amount"] > 0 for row in rows), f"0원 행이 들어갔다: {rows}"
    assert min(row["hour"] for row in rows) >= 8


def test_시간대는_dayType_별로_상하위만_넣는다():
    """48 행이 오면 한 카드가 쓰는 건 두세 행이고 나머지는 틀릴 숫자를 공급한다."""
    hours = [
        {"dayType": day, "hour": h, "amount": 10000 + h * 3137}
        for day in ("WEEKDAY", "WEEKEND")
        for h in range(24)
    ]
    focus = assign({**METRICS, "hourlyProfile": hours})

    rows = next(item["hourlyProfile"] for item in focus if "hourlyProfile" in item)
    assert len(rows) == 8, f"dayType 2 개 × 상·하위 2 행이어야 한다: {len(rows)}행"
    assert {r["dayType"] for r in rows} == {"WEEKDAY", "WEEKEND"}
    # 계열별 최고·최저가 살아 있어야 "가장 높은/낮은" 문장이 맞는다
    weekday = [r for r in rows if r["dayType"] == "WEEKDAY"]
    assert max(r["amount"] for r in weekday) == 10000 + 23 * 3137
    assert min(r["amount"] for r in weekday) == 10000


def test_카테고리는_비중_상위만_넣는다():
    category = [
        {"name": f"카테고리{i}", "share": round(0.5 - i * 0.02, 4), "vsPrevPeriod": 0.01}
        for i in range(20)
    ]
    focus = assign({**METRICS, "categoryBreakdown": category})

    rows = next(item["categoryBreakdown"] for item in focus if "categoryBreakdown" in item)
    assert len(rows) == 5
    assert rows[0]["name"] == "카테고리0", "비중이 가장 큰 쪽이 먼저여야 한다"


_FLAT_METRICS = {
    "salesSummary": {"netSales": 1000000, "vsPrevPeriod": 0.01},
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 10, "amount": 50000},
        {"dayType": "WEEKDAY", "hour": 11, "amount": 52000},
    ],
    "categoryBreakdown": [{"name": "커피", "share": 0.2, "vsPrevPeriod": 0.01}],
}


def test_다른_축이_전부_약하면_날씨가_1순위가_된다():
    """고정점수(0.3)가 "보충" 으로 동작하는지 확인한다 — 다른 세 축이 다 약해야 날씨가 든다."""
    weather = {"basisDateTime": "2026-10-07 11:00", "skyText": "비", "isNotable": True}
    focus = assign({**_FLAT_METRICS, "weatherContext": weather})

    assert "weatherContext" in focus[0]


def test_다른_축이_뚜렷하면_날씨가_밀린다():
    """표준 METRICS(시간대 격차 0.674)는 0.3 보다 훨씬 커서 날씨가 세 장 안에 못 든다."""
    weather = {"basisDateTime": "2026-10-07 11:00", "skyText": "비", "isNotable": True}
    focus = assign({**METRICS, "weatherContext": weather})

    assert not any("weatherContext" in card for card in focus)


def test_날씨가_notable이_아니면_배정되지_않는다():
    weather = {"basisDateTime": "2026-10-07 11:00", "skyText": "맑음", "isNotable": False}
    focus = assign({**METRICS, "weatherContext": weather})

    assert not any("weatherContext" in card for card in focus)
    assert len(focus) == 3


def test_날씨_필드가_없으면_배정되지_않는다():
    focus = assign(METRICS)

    assert not any("weatherContext" in card for card in focus)


def test_선별이_계열별_최고_최저를_보존한다():
    """선별 후에도 "가장 높은/낮은 시간대" 문장이 맞아야 한다.

    상·하위를 고르는 방식이라 성립하는 성질인데, 선별 규칙을 "앞에서 N 행" 같은 걸로
    바꾸면 조용히 깨진다 — 모델은 받은 행 안에서만 최저를 말하므로 틀린 줄도 모른다.
    """
    from app.services.solution_focus import _hourly_rows

    hours = [
        {"dayType": day, "hour": h, "amount": (h * 7919 % 97) * 1000 + 1000}
        for day in ("WEEKDAY", "WEEKEND")
        for h in range(9, 22)
    ]
    rows = _hourly_rows(hours)

    for day in ("WEEKDAY", "WEEKEND"):
        full = [p["amount"] for p in hours if p["dayType"] == day]
        kept = [p["amount"] for p in rows if p["dayType"] == day]
        assert max(kept) == max(full), f"{day} 최고가 빠졌다"
        assert min(kept) == min(full), f"{day} 최저가 빠졌다"


# ── 메뉴 단위 근거 (menuRankings, 2026-10-19) ─────────────────────────

MENUS = [
    {
        "rank": 1,
        "menuName": "아이스 아메리카노",
        "menuSales": 3104200,
        "quantity": 912,
        "ratio": 0.261,
        "vsPrevPeriod": -0.18,
    },
    {
        "rank": 2,
        "menuName": "카페라떼",
        "menuSales": 1420800,
        "quantity": 331,
        "ratio": 0.119,
        "vsPrevPeriod": 0.031,
    },
]


def test_메뉴는_비중이_아니라_변화로_점수를_낸다():
    """메뉴 비중은 카테고리보다 구조적으로 작다 — 커피 카테고리가 62% 여도 그 안의
    아이스 아메리카노는 26% 다. 비중으로 재면 메뉴 축이 거의 항상 진다.

    그리고 "상위 메뉴가 있다" 는 뉴스가 아니다. 늘 아메리카노가 1 위다.
    """
    from app.services.solution_focus import _category_score, _menu_score

    # 비중은 카테고리의 절반 이하인데 변화는 더 크다
    assert max(m["ratio"] for m in MENUS) < 0.62
    assert _menu_score(MENUS) > 0
    # 변화가 없으면 할 말도 없다
    flat = [{**m, "vsPrevPeriod": None} for m in MENUS]
    assert _menu_score(flat) == 0.0
    assert _category_score([{"name": "커피", "share": 0.62}]) == 0.62


def test_메뉴가_크게_움직인_날에만_카드가_된다():
    base = {
        "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ],
        "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
    }
    quiet = assign({**base, "menuRankings": MENUS})
    loud = assign({**base, "menuRankings": [{**MENUS[0], "vsPrevPeriod": -0.42}, MENUS[1]]})

    assert not any("menuRankings" in item for item in quiet)
    assert any("menuRankings" in item for item in loud)


def test_메뉴가_없으면_축에서_빠진다():
    """BE 가 아직 안 보낸다 — 없는 채로도 지금처럼 동작해야 한다."""
    focus = assign(METRICS)

    assert not any("menuRankings" in item for item in focus)
    assert len(focus) == 3


def test_메뉴는_변화폭_상위만_넣는다():
    """점수와 같은 기준으로 골라야 한다. 비중으로 고르면 점수를 만든 메뉴가 빠진다 —
    "유자차가 52% 급락" 이 점수를 1.0 으로 만들어 카드가 올라갔는데, 보여주는 5 종은
    비중 상위라 유자차가 없고 모델은 ±1% 짜리 메뉴만 받는다.
    """
    many = [
        {
            "rank": i + 1,
            "menuName": f"메뉴{i}",
            "menuSales": 500000 - i * 10000,
            "quantity": 100 - i,
            # 비중은 i 가 커질수록 작은데, 움직인 금액은 꼴찌가 가장 크다
            "ratio": 0.25 if i == 19 else 0.02,
            "vsPrevPeriod": -0.6 if i == 19 else 0.01,
        }
        for i in range(20)
    ]
    focus = assign({**METRICS, "menuRankings": many})
    rows = next(item["menuRankings"] for item in focus if "menuRankings" in item)

    assert len(rows) == 5
    assert rows[0]["menuName"] == "메뉴19", "점수를 만든 메뉴가 맨 앞에 와야 한다"


def test_꼬리_메뉴는_점수를_포화시키지_않는다():
    """POS 실측(92 일)에서 이 축이 전부 1.000 이던 원인 — 변화**율** 최댓값으로 재면
    6 개 팔린 메뉴의 +500% 가 `0.5 x 2.0` 으로 상한에 닿는다. 금액 기준은 비중이 작아
    점수를 못 올린다. 근거: docs/experiments/2026-10-26-solution-axis-scores.md
    """
    tail = [
        {
            "rank": 1,
            "menuName": "아메리카노",
            "menuSales": 800000,
            "quantity": 250,
            "ratio": 0.4,
            "vsPrevPeriod": 0.01,
        },
        # 전체 매출의 0.02% 를 차지하는 6 개 팔린 메뉴가 5 배로 뛰었다
        {
            "rank": 2,
            "menuName": "바닐라아이스크림",
            "menuSales": 45000,
            "quantity": 6,
            "ratio": 0.0225,
            "vsPrevPeriod": 5.0,
        },
    ]

    assert _menu_score(tail) < 0.1


def test_비중이_큰_메뉴가_조금_움직이면_꼬리보다_높다():
    """금액 기준으로 바꾼 이유 — 점주가 손쓸 수 있는 건 매출을 움직인 메뉴다."""
    big = {
        "rank": 1,
        "menuName": "아메리카노",
        "menuSales": 800000,
        "quantity": 250,
        "ratio": 0.4,
        "vsPrevPeriod": -0.2,
    }
    tail = {
        "rank": 2,
        "menuName": "유자차",
        "menuSales": 9000,
        "quantity": 2,
        "ratio": 0.0045,
        "vsPrevPeriod": -0.8,
    }

    assert _menu_score([big]) > _menu_score([tail])


def test_변화금액은_전체매출을_안_받고도_정확하다():
    """ratio x vsPrev/(1+vsPrev) 는 근사가 아니라 (현재 - 이전)/전체 와 같은 값이다."""
    total, current, previous = 2_000_000, 800_000, 1_000_000
    point = {
        "ratio": current / total,
        "vsPrevPeriod": (current - previous) / previous,
    }

    assert _menu_share_delta(point) == pytest.approx((current - previous) / total)


def test_전기_매출이_사라진_메뉴는_0이다():
    """vsPrevPeriod 가 -1.0 이면 1 + change 가 0 이라 나눌 수 없다."""
    assert _menu_share_delta({"ratio": 0.1, "vsPrevPeriod": -1.0}) == 0.0


def test_증감이_없는_메뉴는_뒤로_민다():
    """비교할 게 없으면 할 말도 없다 — 시간대 축이 행 2 개 미만이면 빠지는 것과 같다."""
    mixed = [
        {"rank": 1, "menuName": "비교없음", "menuSales": 500000, "quantity": 100, "ratio": 0.3},
        {
            "rank": 2,
            "menuName": "급락",
            "menuSales": 100000,
            "quantity": 20,
            "ratio": 0.3,
            "vsPrevPeriod": -0.5,
        },
    ]
    focus = assign({**METRICS, "menuRankings": mixed})
    rows = next(item["menuRankings"] for item in focus if "menuRankings" in item)

    assert rows[0]["menuName"] == "급락"


# ── 영업시간 (businessHours, 2026-10-20) ──────────────────────────────

HOURS = {"WEEKDAY": {"opensAt": "08:00", "closesAt": "22:00"}}


def test_영업시간_밖_매출은_비교에서_뺀다():
    """0 원 가드만으로는 "닫은 시간" 과 "열었는데 안 팔린 시간" 을 구분하지 못한다.

    마감 뒤에 매출이 찍히는 경우가 실제로 있다(정산·배달 지연 등). 그러면 그 시각이
    최저로 뽑혀 "18시가 23시의 52.5배" 처럼 영업 안 하는 시간과 비교한 문장이 나온다.
    """
    from app.services.solution_focus import _hourly_score, peak_ratios

    rows = [
        {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
        {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        {"dayType": "WEEKDAY", "hour": 23, "amount": 4000},  # 마감 뒤
    ]

    assert peak_ratios(rows)[0]["lowHour"] == 23
    assert peak_ratios(rows, HOURS)[0]["lowHour"] == 8
    assert _hourly_score(rows, HOURS) < _hourly_score(rows)


def test_영업시간이_없으면_지금처럼_동작한다():
    """BE 가 아직 안 보내는 매장도 있다."""
    from app.services.solution_focus import _hourly_rows

    rows = [
        {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
        {"dayType": "WEEKDAY", "hour": 23, "amount": 4000},
    ]

    assert _hourly_rows(rows, None) == _hourly_rows(rows)


def test_영업시간을_모델에게도_넘긴다():
    """ "마감 2시간 전" 같은 실행 시점을 쓰려면 모델이 영업시간을 알아야 한다."""
    metrics = {
        **METRICS,
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 9, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ],
        "businessHours": HOURS,
    }
    hourly = next(item for item in assign(metrics) if "hourlyProfile" in item)

    assert hourly["businessHours"] == HOURS


def test_정의되지_않은_dayType은_거르지_않는다():
    """BE 가 WEEKEND 영업시간을 생략할 수 있다 — 그 계열은 그대로 둔다."""
    from app.services.solution_focus import _hourly_rows

    rows = [
        {"dayType": "WEEKDAY", "hour": 23, "amount": 4000},
        {"dayType": "WEEKEND", "hour": 23, "amount": 9000},
    ]
    kept = _hourly_rows(rows, HOURS)

    assert [r["dayType"] for r in kept] == ["WEEKEND"]


# ── 축 경쟁 (2026-10-21, 이슈 #206) ──────────────────────────────────
# 축이 늘어날 때마다 카드는 3 장 그대로라, 새 축이 들어오면 기존 축 하나가 조용히
# 밀린다. 그걸 아무도 검증하지 않아서 #181(menuRankings) 이 날씨를 밀어낸 걸
# 2026-10-21 에야 알았다. 여기서 경쟁 결과를 숫자로 고정한다.

_FLAT_DAY = {
    "salesSummary": {"netSales": 1102000, "vsPrevPeriod": -0.04},
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 11, "amount": 88000},
        {"dayType": "WEEKDAY", "hour": 14, "amount": 72000},
        {"dayType": "WEEKDAY", "hour": 18, "amount": 96000},
    ],
    "categoryBreakdown": [
        {"name": "커피", "share": 0.38, "vsPrevPeriod": 0.02},
        {"name": "논커피", "share": 0.34, "vsPrevPeriod": -0.03},
    ],
    "weatherContext": {"skyText": "비", "maxPop": 0.8, "isNotable": True},
}


def test_다른_축이_전부_약하면_날씨가_들어온다():
    """ "보충" 설계의 의도된 쪽. 격차도 쏠림도 증감도 약한 날에만 날씨가 자리를 얻는다."""
    focus = assign(_FLAT_DAY)

    assert any("weatherContext" in card for card in focus)


def test_메뉴를_금액으로_재면_날씨_보충_자리가_돌아온다():
    """2026-10-26 까지는 `test_축이_다섯이면_날씨가_밀린다` 였다 — "축이 다섯이 되면서
    날씨 자리가 사실상 사라졌다, 이 테스트가 깨지면 그 결정이 내려진 것" 이라고 적어
    뒀던 tripwire 다.

    깨진 이유는 날씨를 건드려서가 아니라 **메뉴 축의 포화를 없애서** 다. 메뉴를 변화율로
    재던 동안은 꼬리 메뉴 하나가 점수를 1.0 으로 만들어(POS 92 일 실측 전부 1.000) 날씨의
    0.3 을 늘 눌렀다. 금액 기준으로 바꾸니 이 fixture 에서 메뉴가 0.133 으로 내려가
    날씨가 다시 세 번째 자리를 얻는다.
    """
    busy_day = {
        **_FLAT_DAY,
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ],
        "menuRankings": [
            {
                "rank": 1,
                "menuName": "아이스 아메리카노",
                "menuSales": 3980000,
                "quantity": 864,
                "ratio": 0.25,
                "vsPrevPeriod": -0.21,
            },
        ],
    }
    focus = assign(busy_day)

    assert len(focus) == MAX_CARDS
    assert any("weatherContext" in card for card in focus)
    assert not any("menuRankings" in card for card in focus), "메뉴가 날씨에 밀린다"


def test_파생_배율도_영업시간_밖을_뺀다():
    """derive() 가 peak_ratios 에 businessHours 를 안 넘겨 배율만 안 걸러졌다.

    행은 걸러지는데 배율만 안 걸러지면 더 나쁘다 — 모델에게 23 시 행은 안 보이는데
    "52.5 배" 라는 숫자만 주어지고, 그 값은 hourlyPeakRatio 에 실재해 UNGROUNDED_NUMBER
    로도 COMPUTED_RATIO 로도 안 걸린다. 2026-10-21 A40 8 차 실측에서 20 건 중 2 건이
    "평일 18시 매출이 23시에 비해 52.5배" 로 나갔다.

    기존 test_영업시간_밖_매출은_비교에서_뺀다 는 _hourly_score 만 봐서 못 잡았다.
    """
    metrics = {
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
            {"dayType": "WEEKDAY", "hour": 23, "amount": 4000},
        ],
        "businessHours": {"WEEKDAY": {"opensAt": "08:00", "closesAt": "22:00"}},
    }

    ratio = derive(metrics)["hourlyPeakRatio"][0]

    assert ratio["lowHour"] == 8, "마감(22시) 뒤인 23시가 최저로 잡혔다"
    assert ratio["ratio"] == 7.0


# ── 선발 로그 (2026-10-21, 이슈 #215) ────────────────────────────────
# "솔루션에 날씨가 안 나온다" 는 보고가 왔을 때 BE 가 안 보낸 것과 보냈는데 점수에서
# 진 것이 사장님 화면에는 똑같이 보인다. 로그가 그 둘을 가른다.


def test_로그가_탈락과_입력없음을_나눈다(caplog):
    metrics = {
        "salesSummary": {"netSales": 1540000, "vsPrevPeriod": -0.11},
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ],
        "categoryBreakdown": [{"name": "커피", "share": 0.52, "vsPrevPeriod": -0.09}],
        # 날씨는 왔지만 isNotable 이 false — 후보에서 빠진다(입력없음 쪽)
        "weatherContext": {"skyText": "맑음", "maxPop": 0.1, "isNotable": False},
        # 메뉴는 아예 안 왔다 — 역시 입력없음
    }
    with caplog.at_level("INFO", logger="app.services.solution_focus"):
        assign(metrics, store_id=1024)

    line = next(r.getMessage() for r in caplog.records if "솔루션 근거 축" in r.getMessage())
    assert "storeId=1024" in line
    assert "weatherContext" in line.split("입력없음=")[1]
    assert "hourlyProfile" in line.split("선정=")[1].split("탈락=")[0]


def test_로그에_지표_값은_안_남는다(caplog):
    """매출액 같은 영업 정보가 로그로 새면 안 된다."""
    metrics = {
        "salesSummary": {"netSales": 1540000, "vsPrevPeriod": -0.11},
        "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 18, "amount": 210000}],
        "categoryBreakdown": [{"name": "커피", "share": 0.52, "vsPrevPeriod": -0.09}],
    }
    with caplog.at_level("INFO", logger="app.services.solution_focus"):
        assign(metrics, store_id=1024)

    line = next(r.getMessage() for r in caplog.records if "솔루션 근거 축" in r.getMessage())
    assert "1540000" not in line
    assert "210000" not in line
    assert "커피" not in line


# ── 특보급 날씨 (2026-10-21, 이슈 #217) ──────────────────────────────
# 날씨가 isNotable 이면 한파든 흐린 날이든 0.3 으로 같았다. 축이 다섯이 되면서
# 특보급 날씨도 5 위로 밀렸다(A40 8차). 기상청 주의보 기준으로 가른다.

_BUSY_DAY = {
    "salesSummary": {"netSales": 1540000, "vsPrevPeriod": -0.11},
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 8, "amount": 30000},
        {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
    ],
    "categoryBreakdown": [
        {"name": "커피", "share": 0.52, "vsPrevPeriod": -0.09},
        {"name": "디저트", "share": 0.28, "vsPrevPeriod": 0.04},
    ],
    "menuRankings": [
        {
            "rank": 1,
            "menuName": "아이스 아메리카노",
            "menuSales": 3980000,
            "quantity": 864,
            "ratio": 0.25,
            "vsPrevPeriod": -0.14,
        },
    ],
}
_MILD = {"skyText": "흐림", "minTempC": 9, "maxTempC": 19, "maxPop": 0.6, "isNotable": True}


def test_평범한_날씨는_다른_축에_밀린다():
    """축이 다섯인 보통 날에는 날씨가 보충 자리다 — 기존 설계 그대로."""
    focus = assign({**_BUSY_DAY, "weatherContext": _MILD})

    assert not any("weatherContext" in card for card in focus)


def test_한파주의보급이면_1순위가_된다():
    """기상청 한파주의보: 아침 최저기온 -12℃ 이하."""
    cold = {**_MILD, "minTempC": -13, "maxTempC": -4}
    focus = assign({**_BUSY_DAY, "weatherContext": cold})

    assert "weatherContext" in focus[0]


def test_폭염주의보급이면_1순위가_된다():
    """기상청 폭염주의보: 최고기온 33℃ 이상."""
    hot = {**_MILD, "minTempC": 26, "maxTempC": 35}
    focus = assign({**_BUSY_DAY, "weatherContext": hot})

    assert "weatherContext" in focus[0]


def test_기준_바로_아래는_보충_자리에_머문다():
    """-11℃·32℃ 는 주의보가 아니다. 경계에서 한 단계 더 가지 않는지 본다."""
    for edge in ({"minTempC": -11, "maxTempC": -2}, {"minTempC": 25, "maxTempC": 32}):
        focus = assign({**_BUSY_DAY, "weatherContext": {**_MILD, **edge}})
        assert not any("weatherContext" in card for card in focus), edge


def test_isNotable이_아니면_특보_기온이어도_후보에서_빠진다():
    """BE 판정이 우선이다 — 우리가 isNotable 을 덮어쓰지 않는다."""
    cold = {**_MILD, "minTempC": -13, "isNotable": False}
    focus = assign({**_BUSY_DAY, "weatherContext": cold})

    assert not any("weatherContext" in card for card in focus)
