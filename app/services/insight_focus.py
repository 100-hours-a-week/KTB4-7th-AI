"""인사이트 문장마다 쓸 근거 지표를 코드가 골라 하나씩 배정한다.

왜. 지표를 많이 보여줄수록 모델이 엉뚱한 값을 집는다. 2026-10-06 실측(n=48, 32B)에서
지표 6 종을 통째로 받는 인사이트가 `수치_정확` 68%, 카드당 1 종만 받는 솔루션이 96%
였다 — 전 항목 중 인사이트의 최악 항목이고, 원인이 지표 밀도로 보인다. 솔루션은
2026-10-07(#123)에 같은 방식으로 배정을 코드로 옮겨 `카드_지표_중복없음` 이 66% →
100% 가 됐다.

솔루션(app/services/solution_focus.py)과 점수 구조는 같지만 필드명이 하나도 겹치지
않아(`menuSales`/`ratio` vs `amount`/`share`) 파일을 따로 둔다. 한 함수로 묶으면
필드명 매핑 표가 생겨 두 파일보다 읽기 어려워진다.

**점수 기준은 잠정값이다.** "요일 격차가 크면 할 말이 많다" 는 판단은 기획 영역이라
풀스택·기획과 맞춰야 한다. 상수를 한곳에 모아 뒀으니 합의되면 숫자만 바꾸면 된다.

2026-10-15: districtBenchmark(상권, #157)가 여섯째 축으로 들어왔다.

2026-10-16(PR #161 리뷰, 헥터): 처음엔 매장 매출과 행정동 평균의 격차로 점수를 냈는데,
그 격차는 "이 매장이 상권 평균보다 작다"는 거의 고정된 사실이라 달마다 거의 안
바뀐다(기준도 분기 단위). 실측 없이 계산만으로도 categorySales(0.417)·weekdaySales(0.462)
같은 표준 축을 이겨 매달 1위를 차지하는 게 확인됐다 — solution_focus의 날씨가 겪은
문제(가중치 1.0일 때 거의 항상 1순위)와 같은 실패 모드다. 날씨와 같은 처방을 썼다 —
게이트(표본 수)는 그대로 두고, 점수를 격차 비례값이 아니라 고정 보충값(
_DISTRICT_SUPPLEMENT_SCORE)으로 바꿨다. "다른 세 축이 전부 약할 때만" 상권이 들어온다.

2026-10-21(#209, PR #207·#208 실측): districtBenchmark 를 전용 근거 축에서 완전히
뺐다. 인사이트는 상권이 들어오기 전부터 이미 6 개 축이 경쟁 중이었는데, 고정 보충값
0.3 으로는 여전히 자주 밀렸다(#208 "전부있음" 실측: districtBenchmark 0.300 이 7 개
중 5 위). 전용 축 대신 salesSummary(평균매출 비교)·hourlySales(피크 시간대)에
조건부로 끼워 넣는다 — districtBenchmark 라는 중첩 객체는 더 이상 모델에게 안 보이고,
대신 평평한 필드(districtAvgMonthlySalesPerCafe·vsDistrictAvg·peakSalesHourBand·
peakFootTrafficHourBand)로 쪼개져 두 축에 나뉜다. 비교 방향(vsDistrictAvg)은 코드가
미리 계산한다 — solution_focus.peak_ratios() 와 같은 이유로, 두 숫자 다 지표에 있어
UNGROUNDED_NUMBER 로 못 잡는 "방향 반전" 오류를 막는다.
"""

# 잠정 가중치 — 증감률은 절대값이 작아서(0.042) 격차 점수와 자릿수를 맞춘다.
_CHANGE_WEIGHT = 3.0
_SHARE_CHANGE_WEIGHT = 2.0

# 표본이 1~2 곳인 상권은 평균 자체가 의미가 없다(#157). BE 가 자기 필터링 기준과
# 크로스체크할 수 있게 상수로 분리해 둔다 — 잠정값이다.
_MIN_CAFE_STORE_COUNT = 3

# 프롬프트에 보여줄 행 수 — 잠정값. 상·하위 몇 행, 비중 상위 몇 종.
# hourlySales 는 24 시간 × 2 dayType, salesTrend 는 한 달치가 올 수 있다. 한 문장이
# 쓰는 건 한두 행이고 나머지는 틀릴 숫자를 공급한다.
_ROWS_PER_SERIES = 2
_TOP_SHARES = 5


def _selling(points: list[dict]) -> list[dict]:
    """menuSales 가 0 인 행을 뺀다 — 영업시간 밖이거나 휴무일일 수 있다.

    요청에 영업시간·휴무일이 없어서 "닫은 때" 와 "열었는데 안 팔린 때" 를 구분할 수
    없다. 빼지 않으면 격차 점수가 늘 1.0 으로 포화되고(min=0) "가장 낮은 때" 가 영업
    전 시각이나 휴무일로 뽑힌다. 솔루션 쪽과 같은 판단이다(solution_focus._selling).
    """
    return [p for p in points if (p.get("menuSales") or 0) > 0]


def _spread(points: list[dict]) -> float:
    """menuSales 격차. 가장 낮은 쪽이 가장 높은 쪽보다 많이 낮을수록 할 말이 많다."""
    amounts = [p.get("menuSales") or 0 for p in _selling(points)]
    if len(amounts) < 2 or max(amounts) <= 0:
        return 0.0
    return 1.0 - (min(amounts) / max(amounts))


def _spread_rows(points: list[dict], order_key: str) -> list[dict]:
    """가장 높은·낮은 몇 행만 남긴다. dayType 이 있으면 계열별로 따로 고른다."""
    picked: list[dict] = []
    selling = _selling(points)
    for day_type in dict.fromkeys(p.get("dayType") for p in selling):
        series = sorted(
            (p for p in selling if p.get("dayType") == day_type),
            key=lambda p: p.get("menuSales") or 0,
        )
        chosen = series[:_ROWS_PER_SERIES] + series[-_ROWS_PER_SERIES:]
        unique = {p[order_key]: p for p in chosen}
        picked.extend(sorted(unique.values(), key=lambda p: p[order_key]))
    return picked


def _share_rows(points: list[dict]) -> list[dict]:
    """ratio 상위 몇 종만 남긴다."""
    return sorted(points, key=lambda p: p.get("ratio") or 0.0, reverse=True)[:_TOP_SHARES]


def _summary_score(summary: dict) -> float:
    """총매출 증감. 비교 기간이 없으면(첫 업로드) 증감으로는 할 말이 없다."""
    change = summary.get("vsPrevPeriod")
    if change is None:
        return 0.0
    return min(abs(change) * _CHANGE_WEIGHT, 1.0)


def _share_score(points: list[dict]) -> float:
    """한쪽 쏠림, 또는 항목별 증감 중 큰 쪽."""
    if not points:
        return 0.0
    top_share = max(p.get("ratio") or 0.0 for p in points)
    changes = [abs(p["vsPrevPeriod"]) for p in points if p.get("vsPrevPeriod") is not None]
    top_change = max(changes) * _SHARE_CHANGE_WEIGHT if changes else 0.0
    return min(max(top_share, top_change), 1.0)


def district_comparison(total_sales: int, district_avg: int) -> str:
    """상권 평균 대비 매장 매출의 방향을 코드가 미리 계산한다.

    두 숫자 다 지표에 실재해 UNGROUNDED_NUMBER 게이트로는 못 잡는 오류다 — 모델이
    직접 비교하다 방향을 뒤집어 말할 수 있다. solution_focus.peak_ratios() 가 "어느
    두 시각 사이 배수인지"를 코드가 계산해 넘기는 것과 같은 이유다.
    """
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


def _district_gate(district: dict | None) -> bool:
    """표본이 너무 적은 상권(1~2 곳)은 평균이 의미가 없어 후보에서 뺀다(#157).

    salesSummary·hourlySales 두 번들링 지점이 이 게이트를 공유한다.
    """
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0


def assign(metrics: dict, max_count: int) -> list[dict]:
    """문장 순서대로의 근거 지표를 돌려준다. 최대 max_count 개.

    지표가 max_count 종이 안 되면 그만큼만 돌려준다 — 없는 근거로 문장을 만들게 하느니
    개수를 줄이는 편이 낫다. 호출부는 app/services/insight.py::generate 다.
    """
    summary = metrics.get("salesSummary") or {}
    district = metrics.get("districtBenchmark")

    summary_focus: dict = {"salesSummary": summary}
    if _district_gate(district):
        summary_focus["districtAvgMonthlySalesPerCafe"] = district["districtAvgMonthlySalesPerCafe"]
        summary_focus["vsDistrictAvg"] = district_comparison(
            summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"]
        )

    candidates: list[tuple[dict, float]] = [
        (summary_focus, _summary_score(summary) if summary else -1.0),
    ]
    # 점수는 받은 행 전부로 내고, 프롬프트에 넣는 행만 줄인다.
    series_axes = (("salesTrend", "date"), ("weekdaySales", "dayOfWeek"), ("hourlySales", "hour"))
    for key, order_key in series_axes:
        points = metrics.get(key) or []
        focus = {key: _spread_rows(points, order_key)}
        candidates.append((focus, _spread(points) if points else -1.0))
    for key in ("categorySales", "menuRankings"):
        points = metrics.get(key) or []
        candidates.append(({key: _share_rows(points)}, _share_score(points) if points else -1.0))

    usable = [(focus, score) for focus, score in candidates if score >= 0.0]
    usable.sort(key=lambda pair: pair[1], reverse=True)
    return [focus for focus, _ in usable[:max_count]]
