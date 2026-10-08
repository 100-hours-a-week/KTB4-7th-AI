"""문장별 근거 지표 배정 — app/services/insight_focus.py.

지표 6 종을 통째로 던지던 방식이 `수치_정확` 68% 였다(2026-10-06, n=48, 32B). 같은
조건에서 카드당 1 종만 받는 솔루션은 96% 였다. 밀도를 줄이는 게 이 파일의 목적이라,
여기서 가장 중요한 건 "문장마다 하나씩, 겹치지 않게" 다.
"""

from app.services.insight_focus import assign

METRICS = {
    "salesSummary": {
        "totalSales": 7920000,
        "menuSales": 7480000,
        "orderCount": 923,
        "averageOrderValue": 8581,
        "vsPrevPeriod": 0.042,
    },
    "weekdaySales": [
        {"dayOfWeek": "MON", "menuSales": 1420300, "orderCount": 181},
        {"dayOfWeek": "SAT", "menuSales": 2104700, "orderCount": 252},
    ],
    "categorySales": [
        {"categoryName": "커피", "menuSales": 3120000, "ratio": 0.417, "vsPrevPeriod": -0.044}
    ],
}


def test_문장끼리_같은_지표를_받지_않는다():
    keys = [key for item in assign(METRICS, max_count=3) for key in item]

    assert len(keys) == len(set(keys)), f"지표가 두 문장에 들어갔다: {keys}"


def test_요청한_개수를_넘기지_않는다():
    """maxInsightCount 는 BE 계약이다 — 넘기면 _parse 가 거부해 재시도가 돈다."""
    assert len(assign(METRICS, max_count=2)) == 2
    assert len(assign(METRICS, max_count=1)) == 1


def test_지표가_모자라면_그만큼만_배정한다():
    """없는 근거로 문장을 만들게 하느니 개수를 줄인다 — 솔루션과 같은 판단이다."""
    focus = assign({"salesSummary": METRICS["salesSummary"]}, max_count=3)

    assert len(focus) == 1
    assert "salesSummary" in focus[0]


def test_빈_목록은_배정하지_않는다():
    metrics = {**METRICS, "weekdaySales": [], "categorySales": []}
    focus = assign(metrics, max_count=3)

    assert [key for item in focus for key in item] == ["salesSummary"]


def test_비교_기간이_없어도_배정은_된다():
    """첫 업로드 매장은 vsPrevPeriod 가 null 이다 — 점수는 0 이지만 빼지는 않는다.

    totalSales·orderCount 만으로도 "객단가가 8,581원입니다" 같은 관찰은 나온다.
    """
    summary = {**METRICS["salesSummary"], "vsPrevPeriod": None}
    focus = assign({**METRICS, "salesSummary": summary}, max_count=3)

    assert any("salesSummary" in item for item in focus)


def test_지표가_하나도_없으면_빈_배정이다():
    assert assign({}, max_count=3) == []


def test_격차가_큰_지표가_앞에_온다():
    """요일 격차(1 - 1420300/2104700 = 0.33)가 커피 쏠림(0.417)보다 낮다.

    점수 기준 자체는 잠정값이지만, 정렬이 실제로 점수를 따르는지는 고정해 둔다 —
    정렬이 깨지면 "오늘 할 말이 있는 지표" 가 아니라 아무 순서가 된다.
    """
    focus = assign(METRICS, max_count=1)

    assert "categorySales" in focus[0]


def test_0원_행은_최저로_뽑지_않는다():
    """영업시간 밖·휴무일이면 menuSales 가 0 이다. 빼지 않으면 격차 점수가 늘 1.0 이고
    "가장 낮은 때" 가 영업 전 시각으로 뽑힌다 — 솔루션 쪽과 같은 판단이다.
    """
    hours = [
        {
            "dayType": "WEEKDAY",
            "hour": h,
            "menuSales": 0 if h < 8 else 90000 + h * 1000,
            "orderCount": 0 if h < 8 else 12,
        }
        for h in range(24)
    ]
    focus = assign({**METRICS, "hourlySales": hours}, max_count=6)

    rows = next(item["hourlySales"] for item in focus if "hourlySales" in item)
    assert all(row["menuSales"] > 0 for row in rows), f"0원 행이 들어갔다: {rows}"


def test_계열_지표는_상하위_몇_행만_넣는다():
    """salesTrend 는 한 달치, hourlySales 는 24 시간 × 2 dayType 이 올 수 있다."""
    trend = [
        {"date": f"2026-09-{d:02d}", "menuSales": 300000 + d * 7919, "orderCount": 40}
        for d in range(1, 31)
    ]
    focus = assign({**METRICS, "salesTrend": trend}, max_count=6)

    rows = next(item["salesTrend"] for item in focus if "salesTrend" in item)
    assert len(rows) == 4, f"상위 2 + 하위 2 행이어야 한다: {len(rows)}행"
    amounts = [r["menuSales"] for r in rows]
    assert max(amounts) == max(p["menuSales"] for p in trend)
    assert min(amounts) == min(p["menuSales"] for p in trend)


def test_비중_지표는_상위만_넣는다():
    ranks = [
        {
            "rank": i + 1,
            "menuName": f"메뉴{i}",
            "menuSales": 500000 - i * 10000,
            "quantity": 100 - i,
            "ratio": round(0.3 - i * 0.01, 4),
        }
        for i in range(20)
    ]
    focus = assign({**METRICS, "menuRankings": ranks}, max_count=6)

    rows = next(item["menuRankings"] for item in focus if "menuRankings" in item)
    assert len(rows) == 5
    assert rows[0]["menuName"] == "메뉴0"
