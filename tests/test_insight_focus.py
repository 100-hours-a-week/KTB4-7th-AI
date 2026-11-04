"""문장별 근거 지표 배정 — app/services/insight_focus.py.

지표 6 종을 통째로 던지던 방식이 `수치_정확` 68% 였다(2026-10-06, n=48, 32B). 같은
조건에서 카드당 1 종만 받는 솔루션은 96% 였다. 밀도를 줄이는 게 이 파일의 목적이라,
여기서 가장 중요한 건 "문장마다 하나씩, 겹치지 않게" 다.
"""

from app.services.insight_focus import assign, district_comparison

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


DISTRICT = {
    "basisQuarter": "2026Q3",
    "districtAvgMonthlySalesPerCafe": 9413000,
    "cafeStoreCount": 133,
    "peakSalesHourBand": "14-17",
    "peakFootTrafficHourBand": "11-14",
}


def test_매장_매출이_상권_평균보다_크면_ABOVE():
    assert district_comparison(10_000_000, 9_413_000) == "ABOVE"


def test_매장_매출이_상권_평균보다_작으면_BELOW():
    assert district_comparison(7_920_000, 9_413_000) == "BELOW"


def test_매장_매출이_상권_평균과_같으면_EQUAL():
    assert district_comparison(9_413_000, 9_413_000) == "EQUAL"


def test_매출요약이_선정되면_상권_평균매출이_같이_묻는다():
    focus = assign({**METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert summary_focus["districtAvgMonthlySalesPerCafe"] == 9413000
    assert summary_focus["vsDistrictAvg"] in ("ABOVE", "BELOW", "EQUAL")


def test_표본이_너무_적은_상권은_매출요약에_안_묻는다():
    """cafeStoreCount 가 1~2 곳이면 평균이 의미가 없다(#157)."""
    district = {**DISTRICT, "cafeStoreCount": 2}
    focus = assign({**METRICS, "districtBenchmark": district}, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert "districtAvgMonthlySalesPerCafe" not in summary_focus


def test_상권_필드가_없으면_매출요약에_안_묻는다():
    focus = assign(METRICS, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert "districtAvgMonthlySalesPerCafe" not in summary_focus


def test_독립_상권_축은_더_이상_없다():
    """districtBenchmark 를 그 자체로 담은 focus 블록이 나오면 안 된다(#209)."""
    focus = assign({**METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    assert not any(set(item) == {"districtBenchmark"} for item in focus)


HOURLY_METRICS = {
    **METRICS,
    "hourlySales": [
        {"dayType": "WEEKDAY", "hour": 11, "menuSales": 850000, "orderCount": 95},
        {"dayType": "WEEKDAY", "hour": 19, "menuSales": 210000, "orderCount": 24},
        {"dayType": "WEEKEND", "hour": 15, "menuSales": 760000, "orderCount": 80},
        {"dayType": "WEEKEND", "hour": 20, "menuSales": 190000, "orderCount": 20},
    ],
}


def test_시간대_축이_선정되면_매출_밴드와_평일_주말_피크를_비교없이_같이_묻는다():
    """2026-11-03(사용자 요청): 유동인구 밴드는 더 이상 보내지 않는다. 대신
    우리 매장의 평일·주말 매출 최고 시간을 비교 없이 사실로만 전달한다."""
    focus = assign({**HOURLY_METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["peakSalesHourBand"] == "14-17"
    assert "peakFootTrafficHourBand" not in hourly_focus
    assert hourly_focus["storePeakHourWeekday"] == 11
    assert hourly_focus["storePeakHourWeekend"] == 15


def test_주말_영업_데이터가_없으면_주말_피크는_안_묻는다():
    """dayType 중 하나에 영업 데이터가 없으면(_store_peak_hour 가 None) 그
    요일 유형만 생략한다 — 없는 근거로 문장을 만들게 하지 않는다."""
    metrics = {
        **METRICS,
        "hourlySales": [{"dayType": "WEEKDAY", "hour": 11, "menuSales": 850000, "orderCount": 95}],
    }
    focus = assign({**metrics, "districtBenchmark": DISTRICT}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["storePeakHourWeekday"] == 11
    assert "storePeakHourWeekend" not in hourly_focus


def test_우리_매장_피크와_겹쳐도_매출_밴드는_그대로_포함된다():
    """예전엔 우리 매장 피크와 겹치면(SAME) 그 밴드를 통째로 생략했다 — 비교를
    없앤 뒤로는 겹침 여부와 무관하게 늘 포함된다. HOURLY_METRICS 의 평일
    피크(11시)가 밴드("10-13") 안에 들어가는 경우다."""
    district = {**DISTRICT, "peakSalesHourBand": "10-13"}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["peakSalesHourBand"] == "10-13"
    assert hourly_focus["storePeakHourWeekday"] == 11
    assert hourly_focus["storePeakHourWeekend"] == 15


def test_매출이_동률이면_입력_순서와_무관하게_더_이른_시각을_고른다():
    """2026-11-03(사용자 요청): max() 가 BE 가 보낸 배열 순서에 의존하면 같은
    지표를 다른 순서로 받았을 때 다른 문장이 나올 수 있다 — 동률이면 항상 더
    이른 시각을 고르도록 고쳤다. 입력 순서를 뒤집어도 같은 결과여야 한다."""
    forward = [
        {"dayType": "WEEKDAY", "hour": 13, "menuSales": 100000, "orderCount": 50},
        {"dayType": "WEEKDAY", "hour": 15, "menuSales": 100000, "orderCount": 50},
    ]
    reversed_rows = list(reversed(forward))

    focus_forward = assign(
        {**METRICS, "hourlySales": forward, "districtBenchmark": DISTRICT}, max_count=4
    )
    focus_reversed = assign(
        {**METRICS, "hourlySales": reversed_rows, "districtBenchmark": DISTRICT}, max_count=4
    )

    forward_hourly = next(item for item in focus_forward if "hourlySales" in item)
    reversed_hourly = next(item for item in focus_reversed if "hourlySales" in item)
    assert forward_hourly["storePeakHourWeekday"] == 13
    assert reversed_hourly["storePeakHourWeekday"] == 13


def test_평일_주말_피크가_같은_시각이어도_둘_다_그대로_묻는다():
    """평일·주말 매출 최고 시간이 우연히 같은 시(hour)여도 "같다" 판단 없이
    둘 다 사실로 전달한다 — 비교를 안 하므로 특별 취급도 없다."""
    metrics = {
        **METRICS,
        "hourlySales": [
            {"dayType": "WEEKDAY", "hour": 15, "menuSales": 850000, "orderCount": 95},
            {"dayType": "WEEKEND", "hour": 15, "menuSales": 760000, "orderCount": 80},
        ],
    }
    focus = assign({**metrics, "districtBenchmark": DISTRICT}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["storePeakHourWeekday"] == 15
    assert hourly_focus["storePeakHourWeekend"] == 15


def test_상권_필드가_없으면_시간대_축에_안_묻는다():
    focus = assign(HOURLY_METRICS, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert "peakSalesHourBand" not in hourly_focus
    assert "storePeakHourWeekday" not in hourly_focus
    assert "storePeakHourWeekend" not in hourly_focus


def test_표본이_너무_적은_상권은_시간대_축에_안_묻는다():
    district = {**DISTRICT, "cafeStoreCount": 2}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert "peakSalesHourBand" not in hourly_focus
    assert "storePeakHourWeekday" not in hourly_focus


def test_밴드_포맷이_깨지면_시간대_축에_안_묻고_500으로_안_죽는다():
    """BE 가 peakSalesHourBand 포맷을 바꾸면(과거 전례 있음, 통보 없이 계약
    변경) 이상한 문자열이 그대로 모델에 들어간다 — 게이트에서 조용히
    탈락시킨다(#209 최종 리뷰 Important #4)."""
    district = {**DISTRICT, "peakSalesHourBand": "14시-17시"}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert "peakSalesHourBand" not in hourly_focus
    assert "storePeakHourWeekday" not in hourly_focus


def test_유동인구_밴드_포맷이_깨져도_매출_밴드는_그대로_포함된다():
    """2026-11-03: 유동인구 밴드는 문장에 안 쓰므로 포맷 검증 대상에서 뺐다 —
    그 값이 깨져도 매출 밴드·우리 매장 피크는 영향받지 않아야 한다."""
    district = {**DISTRICT, "peakFootTrafficHourBand": "11시-14시"}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["peakSalesHourBand"] == "14-17"
    assert hourly_focus["storePeakHourWeekday"] == 11


def test_밴드_포맷이_깨져도_매출요약의_상권_평균은_그대로_묻는다():
    """밴드 포맷 검증은 hourlySales 번들링에만 건다 — salesSummary 쪽은
    평균매출만 쓰고 밴드를 안 건드리므로 밴드가 깨져도 영향이 없어야 한다
    (#209 최종 리뷰 Important #4, 게이트를 합치지 않은 이유)."""
    district = {**DISTRICT, "peakSalesHourBand": "14시-17시"}
    focus = assign({**METRICS, "districtBenchmark": district}, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert summary_focus["districtAvgMonthlySalesPerCafe"] == 9413000


def test_양쪽_dayType_모두_휴무면_밴드는_유지하고_피크_필드는_둘_다_뺀다():
    """매출이 전부 0 이면(영업 전·휴무) 우리 매장 피크를 계산할 수 없다 —
    밴드 원본 값은 상권 자체의 사실이라 그대로 남긴다(2026-11-04 리뷰로
    복원 — 2026-10-27 비교 제거 때 같이 지워졌던 회귀 테스트)."""
    closed = {
        **HOURLY_METRICS,
        "hourlySales": [
            {"dayType": "WEEKDAY", "hour": 3, "menuSales": 0, "orderCount": 0},
            {"dayType": "WEEKEND", "hour": 3, "menuSales": 0, "orderCount": 0},
        ],
    }
    focus = assign({**closed, "districtBenchmark": DISTRICT}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["peakSalesHourBand"] == "14-17"
    assert "storePeakHourWeekday" not in hourly_focus
    assert "storePeakHourWeekend" not in hourly_focus
