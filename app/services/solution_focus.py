"""카드 3장이 쓸 근거 지표를 코드가 골라 하나씩 배정한다.

왜 코드가 고르나. 프롬프트는 2026-09-16 부터 "각 카드는 서로 다른 지표를 근거로" 라고
지시해 왔는데 지켜지지 않는다 — 실측에서 10 번 중 4 번이 같은 지표로 카드 두 장을 만들었다
(`카드_지표_중복없음` 66%, n=50). 모델을 바꿔도 같았다. 배정을 코드로 옮기면 겹칠 수가 없다.

부수 효과가 더 클 수 있다. 카드마다 지표 하나만 보여주면 그 카드에서 틀릴 숫자 자체가
줄어든다. 지표 6 종을 한꺼번에 주는 인사이트가 `수치_정확` 68%, 4 종인 솔루션이 96% 였다 —
숫자를 많이 줄수록 모델이 엉뚱한 값을 집는다. V2 에서 순이익·날씨·상권이 들어와 7 종이
되면 이 격차가 더 벌어진다.

**점수 기준은 잠정값이다.** "시간대 격차가 크면 할 말이 많다" 같은 판단은 기획 영역이라
풀스택·기획과 맞춰야 한다. 지금은 효과를 측정해 보려고 합리적인 초안을 넣어 둔 것이고,
상수를 한곳에 모아 두었으니 합의되면 숫자만 바꾸면 된다.
"""

MAX_CARDS = 3

# 잠정 가중치 — 서로 다른 성격의 지표를 한 축으로 줄 세우려고 쓴다. 기획 확정 전까지는
# "어느 지표가 오늘 더 특이한가"의 거친 순서만 보장한다고 본다.
_CHANGE_WEIGHT = 3.0  # 증감률은 절대값이 작아서(0.12) 다른 점수와 자릿수를 맞춘다
_CATEGORY_CHANGE_WEIGHT = 2.0
_PREDICTION_WEIGHT = 2.0

# 프롬프트에 보여줄 행 수 — 잠정값. dayType 별 상·하위 몇 행, 비중 상위 몇 종.
# 시간대는 24 시간 × 2 dayType = 48 행이 올 수 있고 카테고리도 20 종까지 가능한데,
# 한 카드가 쓰는 건 두세 행이고 나머지는 틀릴 숫자를 공급한다 — 지표를 많이 주면
# 모델이 엉뚱한 값을 집는 걸 실측으로 확인했다(`수치_정확` 68% vs 96%, n=48).
_ROWS_PER_SERIES = 2
_TOP_SHARES = 5


def _selling(points: list[dict]) -> list[dict]:
    """매출이 0 인 행을 뺀다 — 영업시간 밖일 수 있다.

    요청에 영업시간이 없어서 "닫은 시간" 과 "열었는데 안 팔린 시간" 을 구분할 방법이
    없다. 둘 다 "0 시에 뭘 하세요" 라는 쓸 수 없는 솔루션이 되므로 최저 판단에서 뺀다.
    빼지 않으면 24 시간이 통째로 올 때 격차 점수가 늘 1.0 으로 포화되고(min=0) 가장
    낮은 시간대가 영업 전 시각으로 뽑힌다. BE 가 영업시간 밖 행을 보내는지는 확인 중이다.
    """
    return [p for p in points if (p.get("amount") or 0) > 0]


def _hourly_score(points: list[dict]) -> float:
    """시간대 격차. 가장 낮은 때가 가장 높은 때보다 많이 낮을수록 할 말이 많다."""
    amounts = [p.get("amount") or 0 for p in _selling(points)]
    if len(amounts) < 2 or max(amounts) <= 0:
        return 0.0
    return 1.0 - (min(amounts) / max(amounts))


def _hourly_rows(points: list[dict]) -> list[dict]:
    """dayType 별로 가장 높은·낮은 몇 행만 남긴다. 평일과 주말은 다른 계열이라 섞지 않는다."""
    picked: list[dict] = []
    selling = _selling(points)
    for day_type in dict.fromkeys(p.get("dayType") for p in selling):
        series = sorted(
            (p for p in selling if p.get("dayType") == day_type),
            key=lambda p: p.get("amount") or 0,
        )
        chosen = series[:_ROWS_PER_SERIES] + series[-_ROWS_PER_SERIES:]
        # 상·하위가 겹칠 수 있다(행이 적을 때). 시각 순으로 되돌려 모델이 읽기 쉽게 둔다.
        unique = {p["hour"]: p for p in chosen}
        picked.extend(sorted(unique.values(), key=lambda p: p["hour"]))
    return picked


def _category_rows(points: list[dict]) -> list[dict]:
    """비중 상위 몇 종만 남긴다."""
    return sorted(points, key=lambda p: p.get("share") or 0.0, reverse=True)[:_TOP_SHARES]


def _category_score(points: list[dict]) -> float:
    """한 카테고리 쏠림, 또는 카테고리별 증감 중 큰 쪽."""
    if not points:
        return 0.0
    top_share = max(p.get("share") or 0.0 for p in points)
    changes = [abs(p["vsPrevPeriod"]) for p in points if p.get("vsPrevPeriod") is not None]
    top_change = max(changes) * _CATEGORY_CHANGE_WEIGHT if changes else 0.0
    return min(max(top_share, top_change), 1.0)


def _summary_score(summary: dict) -> float:
    """전체 매출 증감. 비교 기간이 없으면(첫 업로드) 할 말이 없다."""
    change = summary.get("vsPrevPeriod")
    if change is None:
        return 0.0
    return min(abs(change) * _CHANGE_WEIGHT, 1.0)


def _prediction_score(predicted: int | None, net_sales: int) -> float:
    """오늘 예측이 현재 실적과 많이 다르면 할 말이 있다."""
    if not predicted or net_sales <= 0:
        return 0.0
    return min(abs(predicted - net_sales) / net_sales * _PREDICTION_WEIGHT, 1.0)


def assign(metrics: dict) -> list[dict]:
    """카드별 근거 지표를 돌려준다. 앞에서부터 rankNo 1·2·3 에 대응한다.

    `salesSummary` 와 `predictedSalesToday` 는 한 축으로 묶는다 — 둘 다 "오늘 전체 매출"
    얘기라 따로 배정하면 같은 netSales 가 두 카드에 나와 중복이 된다.

    지표가 3 종이 안 되면 그만큼만 돌려준다. 없는 근거로 카드를 만들게 하느니 장수를
    줄이는 편이 낫다 — 서비스가 카드 2 장도 그대로 내보내는 것과 같은 판단이다.

    지금은 축이 셋뿐이라 사실상 순서만 정해진다. V2 에서 순이익·날씨·상권이 들어와 축이
    여섯이 되면 그때부터 "오늘 할 말이 있는 것만 고른다"가 실제로 작동한다.
    """
    summary = metrics.get("salesSummary") or {}
    hourly = metrics.get("hourlyProfile") or []
    category = metrics.get("categoryBreakdown") or []
    predicted = metrics.get("predictedSalesToday")

    total_focus: dict = {"salesSummary": summary} if summary else {}
    if predicted is not None and total_focus:
        total_focus["predictedSalesToday"] = predicted
    total_score = max(
        _summary_score(summary) if summary else -1.0,
        _prediction_score(predicted, summary.get("netSales") or 0) if predicted else -1.0,
    )

    # 점수는 받은 행 전부로 내고, 프롬프트에 넣는 행만 줄인다 — 격차 판단이 둔해지면
    # 어느 지표가 특이한지부터 틀린다.
    candidates = [
        ({"hourlyProfile": _hourly_rows(hourly)}, _hourly_score(hourly) if hourly else -1.0),
        (
            {"categoryBreakdown": _category_rows(category)},
            _category_score(category) if category else -1.0,
        ),
        (total_focus, total_score if total_focus else -1.0),
    ]
    usable = [(focus, score) for focus, score in candidates if score >= 0.0]
    usable.sort(key=lambda pair: pair[1], reverse=True)
    return [focus for focus, _ in usable[:MAX_CARDS]]
