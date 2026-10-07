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
