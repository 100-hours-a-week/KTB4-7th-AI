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

import logging

logger = logging.getLogger(__name__)

MAX_CARDS = 3

# 잠정 가중치 — 서로 다른 성격의 지표를 한 축으로 줄 세우려고 쓴다. 기획 확정 전까지는
# "어느 지표가 오늘 더 특이한가"의 거친 순서만 보장한다고 본다.
_CHANGE_WEIGHT = 3.0  # 증감률은 절대값이 작아서(0.12) 다른 점수와 자릿수를 맞춘다
_CATEGORY_CHANGE_WEIGHT = 2.0
_PREDICTION_WEIGHT = 2.0

# 2026-10-14: 처음엔 1.0(다른 축의 상한과 동일)으로 뒀더니 표준 fixture 기준 날씨가 거의
# 항상 1 순위를 차지해 기존 세 축 중 하나를 밀어냈다 — "다른 축이 할 말 없을 때만 보충"
# 이라는 의도와 반대로 동작했다(실측: hourly 0.674·category 0.62·total 0.36인 fixture에서
# 날씨가 1 순위, total_focus 탈락). 0.3 으로 낮춰 "그 날의 다른 세 축이 전부 약할 때만"
# 날씨가 들어오게 한다 — 이 값도 다른 가중치처럼 잠정값이다.
_WEATHER_SUPPLEMENT_SCORE = 0.3

# 특보급 날씨는 그 날 가장 할 말이 많다. 보통 날씨의 "보충" 자리와 성격이 다르다.
# 기준은 기상청 주의보 발효 기준을 그대로 쓴다 — 우리가 고른 숫자가 아니다.
_COLD_WAVE_MIN_TEMP = -12  # 한파주의보: 아침 최저기온 -12℃ 이하
_HEAT_WAVE_MAX_TEMP = 33  # 폭염주의보: 최고기온 33℃ 이상
_WEATHER_ALERT_SCORE = 1.0

# 프롬프트에 보여줄 행 수 — 잠정값. dayType 별 상·하위 몇 행, 비중 상위 몇 종.
# 시간대는 24 시간 × 2 dayType = 48 행이 올 수 있고 카테고리도 20 종까지 가능한데,
# 한 카드가 쓰는 건 두세 행이고 나머지는 틀릴 숫자를 공급한다 — 지표를 많이 주면
# 모델이 엉뚱한 값을 집는 걸 실측으로 확인했다(`수치_정확` 68% vs 96%, n=48).
_ROWS_PER_SERIES = 2
_TOP_SHARES = 5


def _open_hours(points: list[dict], hours: dict | None) -> list[dict]:
    """영업시간 밖 행을 뺀다. 영업시간이 없으면 그대로 둔다.

    BE 가 24 시간치를 보내면 문 닫은 시간이 섞여 "가장 낮은 시간대" 가 0 시로 뽑히고
    "0시에 뭘 하세요" 가 나온다. 그동안은 0 원 행을 빼는 것으로 대신했는데(2026-10-08),
    그건 "닫은 시간" 과 "열었는데 안 팔린 시간" 을 구분하지 못하는 임시 방편이었다.
    영업시간을 받으면 정확히 가를 수 있다(2026-10-19 풀스택 확정).

    0 원 행 가드는 그대로 둔다 — 영업 중인데 0 원인 시간은 할 말이 있는 사실이지만,
    그걸 최저로 쓰면 격차 점수가 1.0 으로 포화돼 시간대 축이 늘 1 순위가 된다.
    같이 풀려면 점수식을 손봐야 해서 이번 범위 밖이다.
    """
    if not hours:
        return points
    out = []
    for point in points:
        window = hours.get(point.get("dayType") or "")
        if not window:
            out.append(point)
            continue
        hour = point.get("hour")
        if hour is None:
            continue
        opens = int(str(window.get("opensAt", "00:00")).split(":")[0])
        closes = int(str(window.get("closesAt", "24:00")).split(":")[0]) or 24
        if opens <= hour < closes:
            out.append(point)
    return out


def _selling(points: list[dict]) -> list[dict]:
    """매출이 0 인 행을 뺀다 — 영업시간 밖일 수 있다.

    요청에 영업시간이 없어서 "닫은 시간" 과 "열었는데 안 팔린 시간" 을 구분할 방법이
    없다. 둘 다 "0 시에 뭘 하세요" 라는 쓸 수 없는 솔루션이 되므로 최저 판단에서 뺀다.
    빼지 않으면 24 시간이 통째로 올 때 격차 점수가 늘 1.0 으로 포화되고(min=0) 가장
    낮은 시간대가 영업 전 시각으로 뽑힌다. BE 가 영업시간 밖 행을 보내는지는 확인 중이다.
    """
    return [p for p in points if (p.get("amount") or 0) > 0]


def _hourly_score(points: list[dict], hours: dict | None = None) -> float:
    """시간대 격차. 가장 낮은 때가 가장 높은 때보다 많이 낮을수록 할 말이 많다.

    비교할 행이 2 개가 안 되면 -1.0 으로 후보에서 아예 뺀다. 0.0 을 돌려주면 "할 말은
    없지만 후보" 가 되어 카드로 배정되고, 모델은 배정받은 지표로 뭐든 써야 하니 **없는
    비교를 지어낸다** — 2026-10-16 배포본에서 행이 하나뿐인데 "평일 9시 매출이 다른
    시간대에 비해 현저히 낮습니다"가 나왔다. 비교가 이 축의 존재 이유라, 비교할 게
    없으면 축 자체가 성립하지 않는다.
    """
    amounts = [p.get("amount") or 0 for p in _selling(_open_hours(points, hours))]
    if len(amounts) < 2 or max(amounts) <= 0:
        return -1.0
    return 1.0 - (min(amounts) / max(amounts))


def _hourly_rows(points: list[dict], hours: dict | None = None) -> list[dict]:
    """dayType 별로 가장 높은·낮은 몇 행만 남긴다. 평일과 주말은 다른 계열이라 섞지 않는다."""
    picked: list[dict] = []
    selling = _selling(_open_hours(points, hours))
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


def peak_ratios(points: list[dict], hours: dict | None = None) -> list[dict]:
    """dayType 별 최고/최저 배수. 코드가 계산해 지표로 넘긴다.

    왜. 30,000 대 210,000 이면 "7 배" 가 그 데이터의 핵심 사실인데, 프롬프트는 배율 계산을
    금지한다("계산은 코드, 해석만 모델"). 그래서 모델이 그걸 말하려 할 때마다 거부되고
    재시도가 돌았다 — 2026-10-16 실측에서 재시도 사유 1 위가 COMPUTED_RATIO 였고 3 건 모두
    hourlyProfile 카드였다. 2026-10-11 에 retry_feedback() 으로 "방금 이 규칙을 어겼다" 를
    알려줬는데도 2 회차에 또 쓴 사례가 있었다 — 말하지 말라고 막는 것으로는 안 풀린다.

    계산을 코드가 해서 넘기면 모델은 인용만 하면 된다. 금지할 이유가 없어진다.

    dayType 별로 따로 낸다. 평일 최고와 주말 최저를 섞으면 틀린 문장이 된다.

    어느 두 시각 사이인지(peakHour·lowHour)를 같이 준다. 배수만 주면 모델이 아무 두 행에
    갖다 붙인다 — 실측에서 "12시 412,000원이 15시 61,500원의 50.2배" 가 나왔는데 50.2 는
    12시 대 9시(8,200원) 값이고 12시÷15시는 6.7 이다. 숫자 자체는 지표에 있어서 접지
    검사를 통과하고, 정수부가 두 자리라 _ungrounded 도 실행 지시로 보고 넘긴다 —
    **어떤 검사에도 안 걸리는 틀린 문장**이 된다.
    """
    out = []
    selling = _selling(_open_hours(points, hours))
    for day_type in dict.fromkeys(p.get("dayType") for p in selling):
        series = [p for p in selling if p.get("dayType") == day_type]
        if len(series) < 2:
            continue
        peak = max(series, key=lambda p: p.get("amount") or 0)
        low = min(series, key=lambda p: p.get("amount") or 0)
        if (low.get("amount") or 0) <= 0:
            continue
        out.append(
            {
                "dayType": day_type,
                "peakHour": peak["hour"],
                "lowHour": low["hour"],
                "ratio": round(peak["amount"] / low["amount"], 1),
            }
        )
    return out


def derive(metrics: dict) -> dict:
    """모델이 직접 계산하지 않아도 되게 코드가 미리 내는 파생 지표를 더한 사본.

    호출부는 app/services/solution.py::generate 다. 채점기도 같은 값을 봐야 해서
    devtools/bench.py 가 채점 전에 같이 부른다 — 안 그러면 "지표에 있는 배율" 을
    채점기가 날조로 센다.
    """
    # businessHours 를 넘기지 않으면 peak_ratios 의 기본값(None)으로 떨어져 영업시간
    # 필터가 통째로 건너뛰어진다 — 행은 걸러지는데 배율만 안 걸러져서, 모델에게 23 시
    # 행은 안 보이는데 "52.5 배" 라는 숫자만 주어진다. 그 값은 hourlyPeakRatio 에 실재해
    # UNGROUNDED_NUMBER·COMPUTED_RATIO 둘 다 안 걸린다(2026-10-21 A40 8 차에서 재현).
    ratios = peak_ratios(metrics.get("hourlyProfile") or [], metrics.get("businessHours"))
    return {**metrics, "hourlyPeakRatio": ratios} if ratios else metrics


def _menu_share_delta(point: dict) -> float:
    """이 메뉴의 변화가 전체 매출의 몇 %였나. 부호를 유지한다.

    `ratio`(현재 비중)와 `vsPrevPeriod`(증감률)만으로 전체 매출을 안 받고 낼 수 있다 —
    근사가 아니라 정확히 같은 값이다:

        변화금액/전체 = (menuSales - prev)/전체
                      = (menuSales/전체) x (menuSales - prev)/menuSales
                      = ratio x vsPrevPeriod/(1 + vsPrevPeriod)

    vsPrevPeriod 가 null 이면 비교할 게 없어 0.0 이다. -1.0(전기 매출이 통째로 사라진
    경우)이면 분모가 0 이 되는데, 그 메뉴는 현재 매출이 0 이라 랭킹에 올 수 없다.
    """
    change = point.get("vsPrevPeriod")
    if change is None or change == -1.0:
        return 0.0
    return (point.get("ratio") or 0.0) * change / (1.0 + change)


def _menu_rows(points: list[dict]) -> list[dict]:
    """변화폭 상위 몇 종. 점수와 같은 기준으로 골라야 한다.

    비중으로 고르면 점수와 어긋난다 — "유자차가 52% 급락" 이 점수를 1.0 으로 만들어
    카드가 올라갔는데, 보여주는 5 종은 비중 상위라 유자차가 빠진다. 모델은 ±1~3% 짜리
    메뉴만 받고 "할 말이 있다" 는 카드를 써야 한다.

    증감이 없는 메뉴(vsPrevPeriod 가 null)는 뒤로 민다 — 비교할 게 없으면 할 말도 없다.
    """
    return sorted(points, key=lambda p: abs(_menu_share_delta(p)), reverse=True)[:_TOP_SHARES]


def _category_rows(points: list[dict]) -> list[dict]:
    """비중 상위 몇 종만 남긴다."""
    return sorted(points, key=lambda p: p.get("share") or 0.0, reverse=True)[:_TOP_SHARES]


def _menu_score(points: list[dict]) -> float:
    """메뉴는 **변화**로 본다. 비중으로 보면 안 된다.

    메뉴 비중은 카테고리보다 구조적으로 작다 — 커피 카테고리가 62% 여도 그 안의
    아이스 아메리카노는 26% 다. 같은 잣대로 재면 메뉴 축이 거의 항상 진다.

    그리고 "상위 메뉴가 있다" 는 뉴스가 아니다. 늘 아메리카노가 1 위다. 할 말이
    생기는 건 **많이 움직였을 때**다.

    2026-10-26: 변화 **율** 최댓값으로 재던 걸 변화 **금액**(전체 매출 대비)으로 바꿨다.
    율로 재면 꼬리 메뉴 하나가 점수를 포화시킨다 — POS 실측(92 일, 매장 1 곳)에서 이 축은
    92 일 **전부 정확히 1.000** 이었다(표준편차 0.000). 7 일 창에 메뉴가 135 종 있고 그중
    42 종이 전주 대비 ±50% 이상 움직이는데, `0.5 x 2.0 = 1.0` 이라 6 개 팔린
    "바닐라아이스크림 +500%" 한 종만 있어도 상한에 닿았다. 금액 기준으로 바꾸면 같은
    데이터에서 평균 0.057·표준편차 0.035·포화 0% 가 된다.
    근거: docs/experiments/2026-10-26-solution-axis-scores.md
    """
    deltas = [abs(_menu_share_delta(p)) for p in points]
    if not deltas:
        return 0.0
    return min(max(deltas) * _CATEGORY_CHANGE_WEIGHT, 1.0)


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


def _weather_score(weather: dict | None) -> float:
    """notable 이면 보충 점수, 그중 특보급이면 1 순위.

    2026-10-14 에는 "isNotable 이 참/거짓뿐이라 세부 점수를 매길 근거가 없다" 고 보고
    고정값 하나만 썼는데, **원시값이 같이 온다는 걸 놓쳤다**(minTempC·maxTempC 등).
    그래서 한파든 흐린 날이든 점수가 같았고, A40 8 차에서 날씨가 축 다섯 중 5 위로
    밀렸다(2026-10-21, 이슈 #217).

    한파·폭염은 **기상청 주의보 기준**으로 가른다 — 우리가 고른 숫자가 아니다.
    그 날엔 "오늘 뭘 할까" 의 답이 날씨라서 다른 축보다 앞선다.

    **태풍·대설은 판정할 수 없다.** 풍속도 적설도 계약에 없다(WeatherContext 는
    basisDateTime·skyText·minTempC·maxTempC·maxPop·rainHours·precipitationMm·isNotable).
    BE 에 특보 발효 여부를 받는 쪽이 원시값으로 재구성하는 것보다 정확하다 — 요청해 둘 것.
    """
    if not weather or not weather.get("isNotable"):
        return -1.0
    low, high = weather.get("minTempC"), weather.get("maxTempC")
    if (low is not None and low <= _COLD_WAVE_MIN_TEMP) or (
        high is not None and high >= _HEAT_WAVE_MAX_TEMP
    ):
        return _WEATHER_ALERT_SCORE
    return _WEATHER_SUPPLEMENT_SCORE


def _hourly_focus(metrics: dict, hourly: list[dict]) -> dict:
    """시간대 근거. 배수가 있으면 같이 준다 — derive() 가 metrics 에 넣어 둔 값이다."""
    hours = metrics.get("businessHours")
    focus: dict = {"hourlyProfile": _hourly_rows(hourly, hours)}
    if hours:
        focus["businessHours"] = hours
    ratios = metrics.get("hourlyPeakRatio")
    if ratios:
        focus["hourlyPeakRatio"] = ratios
    return focus


def assign(metrics: dict, store_id: int | None = None) -> list[dict]:
    """카드별 근거 지표를 돌려준다. 앞에서부터 rankNo 1·2·3 에 대응한다.

    `salesSummary` 와 `predictedSalesToday` 는 한 축으로 묶는다 — 둘 다 "오늘 전체 매출"
    얘기라 따로 배정하면 같은 netSales 가 두 카드에 나와 중복이 된다.

    지표가 3 종이 안 되면 그만큼만 돌려준다. 없는 근거로 카드를 만들게 하느니 장수를
    줄이는 편이 낫다 — 서비스가 카드 2 장도 그대로 내보내는 것과 같은 판단이다.

    2026-10-14: 날씨(weatherContext)가 네 번째 축으로 들어왔다. `isNotable` 이 BE 판정이라
    점수를 더 매길 근거가 없어 고정값(`_WEATHER_SUPPLEMENT_SCORE`, 0.3)을 쓴다 — 다른 세
    축이 전부 그보다 약할 때만 날씨가 카드를 차지한다("보충" 설계). 다른 축 중 하나라도
    뚜렷하면 날씨는 밀린다.

    축이 넷이 되면서 "오늘 할 말이 있는 것만 고른다"가 처음으로 실제 선택(= 네 후보 중
    하나 탈락)으로 작동하기 시작한다. 상권(districtBenchmark)은 인사이트로 가서 솔루션
    축에는 포함하지 않는다(2026-10-13 결정).
    """
    summary = metrics.get("salesSummary") or {}
    hourly = metrics.get("hourlyProfile") or []
    category = metrics.get("categoryBreakdown") or []
    predicted = metrics.get("predictedSalesToday")
    weather = metrics.get("weatherContext")
    menus = metrics.get("menuRankings") or []

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
        (
            _hourly_focus(metrics, hourly),
            _hourly_score(hourly, metrics.get("businessHours")) if hourly else -1.0,
        ),
        (
            {"categoryBreakdown": _category_rows(category)},
            _category_score(category) if category else -1.0,
        ),
        (total_focus, total_score if total_focus else -1.0),
        # 맨 뒤에 둔다 — 동점(1.0)이면 안정 정렬이라 앞선 세 축이 우선한다. 날씨는 "다른
        # 축이 오늘 할 말이 없을 때만" 보충하는 자리다.
        ({"weatherContext": weather}, _weather_score(weather)),
        # 메뉴는 카테고리보다 한 단계 구체적이다 — "커피 62%" 로는 행동이 안 나오지만
        # "아이스 아메리카노 912잔" 이면 발주를 말할 수 있다(2026-10-18).
        (
            {"menuRankings": _menu_rows(menus)},
            _menu_score(menus) if menus else -1.0,
        ),
    ]
    usable = [(focus, score) for focus, score in candidates if score >= 0.0]
    usable.sort(key=lambda pair: pair[1], reverse=True)
    picked = [focus for focus, _ in usable[:MAX_CARDS]]
    _log_selection(candidates, usable, picked, store_id)
    return picked


def _axis(focus: dict) -> str:
    """focus 블록의 첫 키가 축 이름이다 — 모든 생성 지점이 축을 먼저 넣는다.

    _hourly_focus 가 businessHours·hourlyPeakRatio 를, total_focus 가
    predictedSalesToday 를 뒤에 더하지만 축 키는 항상 앞이다(dict 는 삽입 순서를 지킨다).
    """
    return next(iter(focus), "?")


def _log_selection(
    candidates: list[tuple[dict, float]],
    usable: list[tuple[dict, float]],
    picked: list[dict],
    store_id: int | None,
) -> None:
    """어느 축이 후보였고 어느 축이 뽑혔는지 남긴다.

    "솔루션에 날씨가 안 나온다" 는 보고가 왔을 때 **BE 가 안 보낸 것**과 **보냈는데
    점수에서 진 것**이 사장님 화면에는 똑같이 보인다(2026-10-21). 그래서 "입력없음" 을
    "탈락" 과 따로 센다 — 이 둘을 가르려고 남기는 로그다.

    **지표 값은 남기지 않는다.** 축 이름과 점수뿐이다 — 매출액 같은 영업 정보가 로그로
    새면 안 된다(Sentry _strip_sensitive_data 와 같은 기준, docs/DEPLOY.md).
    """
    chosen = {id(focus) for focus in picked}
    logger.info(
        "솔루션 근거 축 storeId=%s 선정=[%s] 탈락=[%s] 입력없음=[%s]",
        "-" if store_id is None else store_id,
        ", ".join(f"{_axis(f)} {sc:.2f}" for f, sc in usable if id(f) in chosen),
        ", ".join(f"{_axis(f)} {sc:.2f}" for f, sc in usable if id(f) not in chosen),
        ", ".join(_axis(f) for f, sc in candidates if sc < 0.0),
    )
