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
