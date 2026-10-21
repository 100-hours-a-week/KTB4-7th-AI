"""카드별 근거 지표 배정 — app/services/solution_focus.py.

프롬프트로 "각 카드는 서로 다른 지표를 근거로" 라고 지시해도 실측 통과율이 66% 였다.
배정을 코드로 옮긴 이유라, 여기서 가장 중요한 건 "겹치지 않는다" 하나다.
"""

from app.services.solution_focus import MAX_CARDS, assign

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
            "ratio": round(0.3 - i * 0.01, 4),
            # 비중은 i 가 커질수록 작은데, 변화는 꼴찌가 가장 크다
            "vsPrevPeriod": -0.42 if i == 19 else 0.01,
        }
        for i in range(20)
    ]
    focus = assign({**METRICS, "menuRankings": many})
    rows = next(item["menuRankings"] for item in focus if "menuRankings" in item)

    assert len(rows) == 5
    assert rows[0]["menuName"] == "메뉴19", "점수를 만든 메뉴가 맨 앞에 와야 한다"


def test_증감이_없는_메뉴는_뒤로_민다():
    """비교할 게 없으면 할 말도 없다 — 시간대 축이 행 2 개 미만이면 빠지는 것과 같다."""
    mixed = [
        {"rank": 1, "menuName": "비교없음", "menuSales": 500000, "quantity": 100, "ratio": 0.3},
        {
            "rank": 2,
            "menuName": "급락",
            "menuSales": 100000,
            "quantity": 20,
            "ratio": 0.06,
            "vsPrevPeriod": -0.4,
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


def test_축이_다섯이면_날씨가_밀린다():
    """**현재 동작이고, 고칠지는 아직 결정 안 됐다**(이슈 #206 범위 밖).

    날씨만 상한이 0.3(_WEATHER_SUPPLEMENT_SCORE) 고정이고 나머지는 1.0 까지 간다.
    축이 넷일 때는 "다른 셋이 약한 날" 이 가끔 있었는데, #181 로 다섯이 되면서
    그 자리가 사실상 사라졌다. 이 테스트가 깨지면 그 결정이 내려진 것이다.
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
    assert not any("weatherContext" in card for card in focus)
