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

2026-10-21(#209 최종 리뷰 Important #4): _district_gate 가 peakSalesHourBand·
peakFootTrafficHourBand 의 포맷을 검증하지 않아서, BE 가 그 문자열을 바꾸면(과거
10-19 에 BE 계약 3 건이 통보 없이 바뀐 전례가 있다) _in_band 의 int() 변환이
터져 상권 붙은 모든 인사이트 요청이 500 이 된다 — 이 번들링 변경 전에는 밴드
문자열을 파싱 없이 그대로 프롬프트에 넘겨서 이 크래시 경로가 없었다. 게이트에서
포맷이 안 맞으면 조용히 탈락시킨다 — 상권만 빠지고 인사이트는 정상 생성된다.

2026-10-22(#209 최종 리뷰 Important #5, PR #219 머지 전 재검토): _store_peak_hour 가
dayType 을 구분하지 않고 전역 최대 한 행의 시각을 "우리 매장 피크"로 썼다.
hourlySales 의 다른 모든 구성(_spread_rows)은 dayType 별로 따로 행을 고르는데,
비교 방향(vsDistrictSalesPeak 등)만 평일·주말을 섞은 단일 피크로 계산되면,
모델이 실제로 묘사하는 행(예: WEEKDAY 15 시)과 코드가 계산한 피크(예: WEEKEND
12 시)가 달라 방향이 어긋날 수 있다. dayType 별로 피크를 따로 계산해 비교
필드도 dayType 별로 쪼갰다(vsDistrictSalesPeakWeekday/Weekend,
vsDistrictFootTrafficPeakWeekday/Weekend) — 어느 dayType 피크를 모델이
말해도 그에 맞는 비교값을 받는다.

2026-10-23(#209 재검토 반영): peakSalesHourBand·peakFootTrafficHourBand 는
이제 SAME(우리 매장 피크와 겹침)이면 그 밴드 자체를 안 보낸다 — "다른 가게처럼
바쁘다"는 당연한 사실만 남아 할 말이 없다는 판단이다. 두 밴드는 서로 독립적으로
판단한다 — 매출 피크와 유동인구 피크는 다른 시간대일 수 있어, 하나만
생략되거나 둘 다 생략되거나 둘 다 포함될 수 있다. 존재하는 dayType 비교 중
하나라도 DIFFERENT면 그 밴드와 해당 라벨을 포함하고, 전부 SAME이면 통째로
생략한다. 비교를 계산할 dayType이 하나도 없으면(두 dayType 다 영업 데이터
없음) 밴드 값은 상권 자체의 사실이라 그대로 남긴다(기존과 동일, 2026-10-21(5)).
"""

import re

# 잠정 가중치 — 증감률은 절대값이 작아서(0.042) 격차 점수와 자릿수를 맞춘다.
_CHANGE_WEIGHT = 3.0
_SHARE_CHANGE_WEIGHT = 2.0

# 표본이 1~2 곳인 상권은 평균 자체가 의미가 없다(#157). BE 가 자기 필터링 기준과
# 크로스체크할 수 있게 상수로 분리해 둔다 — 잠정값이다.
_MIN_CAFE_STORE_COUNT = 3

# peakSalesHourBand·peakFootTrafficHourBand 의 기대 포맷("HH-HH") — BE
# DistrictBenchmarkService.VALID_HOUR_BANDS 는 그 서비스 내부 약속일 뿐 우리
# 스키마(str)에는 강제되지 않는다. 안 맞으면 _in_band 의 int() 변환이 터져
# 상권 붙은 모든 요청이 500 이 된다(#209 최종 리뷰 Important #4).
_HOUR_BAND = re.compile(r"^\d{1,2}-\d{1,2}$")

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


def _band_gate(district: dict | None) -> bool:
    """peakSalesHourBand·peakFootTrafficHourBand 포맷이 "HH-HH" 인지만 본다.

    hourlySales 번들링만 그 문자열을 _in_band 로 파싱한다 — salesSummary 쪽은
    평균매출만 쓰고 밴드는 안 건드려 포맷과 무관하다. _district_gate 에 합치지
    않고 hourlySales 호출부에서만 추가로 본다(#209 최종 리뷰 Important #4) —
    합치면 밴드 포맷만 깨져도 상권 평균매출(salesSummary 쪽)까지 같이 멈춘다.
    """
    if not district:
        return False
    return bool(
        _HOUR_BAND.fullmatch(district.get("peakSalesHourBand") or "")
        and _HOUR_BAND.fullmatch(district.get("peakFootTrafficHourBand") or "")
    )


# hourlySales 의 dayType 값 — BE 계약상 고정 2 종(2026-10-22).
_DAY_TYPES = ("WEEKDAY", "WEEKEND")


def _store_peak_hour(points: list[dict], day_type: str) -> int | None:
    """dayType 이 day_type 인, 영업 중(menuSales > 0)인 행 중 매출이 가장 높은 시간.
    없으면 None.
    """
    selling = [p for p in _selling(points) if p.get("dayType") == day_type]
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int, band: str) -> bool:
    """우리 매장 피크 시간이 상권 밴드("HH-HH") 안에 드는지. 밴드 형식은 BE
    DistrictBenchmarkService.VALID_HOUR_BANDS 가 고정 집합으로 보장한다. 호출부가
    hour is None 인 경우를 먼저 걸러내므로 여기선 int 만 받는다.
    """
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end


def _band_included(points: list[dict], band: str) -> bool:
    """band(peakSalesHourBand 류)를 focus 에 넣을지.

    존재하는 dayType(피크를 계산할 수 있는 dayType) 비교 중 하나라도 DIFFERENT
    면 포함한다. 전부 SAME 이면(비교가 하나 이상 있을 때) 생략한다 — "우리
    매장도 다른 가게처럼 바쁘다"는 당연한 사실만 남아 점주에게 할 말이 거의
    없다. 두 밴드(매출/유동인구)는 서로 독립적으로 판단한다. 비교가 하나도
    없으면(두 dayType 다 피크를 못 구함) 밴드 값은 상권 자체의 사실이라 그대로
    포함한다. devtools/grade.py::_band_expected 가 같은 로직을 복제해 검사한다.
    """
    comparisons = [
        _in_band(hour, band)
        for hour in (_store_peak_hour(points, day_type) for day_type in _DAY_TYPES)
        if hour is not None
    ]
    return not comparisons or not all(comparisons)


def _apply_band(
    focus: dict, points: list[dict], band_field: str, label_prefix: str, band: str
) -> None:
    """band_field(peakSalesHourBand 류)와 그 label_prefix 라벨(Weekday/Weekend)을
    조건부로 채운다 — 포함 여부는 _band_included 로 정한다.
    """
    if not _band_included(points, band):
        return
    focus[band_field] = band
    for day_type in _DAY_TYPES:
        peak_hour = _store_peak_hour(points, day_type)
        if peak_hour is None:
            continue
        focus[f"{label_prefix}{day_type.capitalize()}"] = (
            "SAME" if _in_band(peak_hour, band) else "DIFFERENT"
        )


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
        if key == "hourlySales" and _district_gate(district) and _band_gate(district):
            _apply_band(
                focus,
                points,
                "peakSalesHourBand",
                "vsDistrictSalesPeak",
                district["peakSalesHourBand"],
            )
            _apply_band(
                focus,
                points,
                "peakFootTrafficHourBand",
                "vsDistrictFootTrafficPeak",
                district["peakFootTrafficHourBand"],
            )
        candidates.append((focus, _spread(points) if points else -1.0))
    for key in ("categorySales", "menuRankings"):
        points = metrics.get(key) or []
        candidates.append(({key: _share_rows(points)}, _share_score(points) if points else -1.0))

    usable = [(focus, score) for focus, score in candidates if score >= 0.0]
    usable.sort(key=lambda pair: pair[1], reverse=True)
    return [focus for focus, _ in usable[:max_count]]
