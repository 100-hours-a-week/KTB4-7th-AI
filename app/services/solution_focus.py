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
from datetime import date

logger = logging.getLogger(__name__)

MAX_CARDS = 3

# 잠정 가중치 — 서로 다른 성격의 지표를 한 축으로 줄 세우려고 쓴다. 기획 확정 전까지는
# "어느 지표가 오늘 더 특이한가"의 거친 순서만 보장한다고 본다.
_CHANGE_WEIGHT = 3.0  # 증감률은 절대값이 작아서(0.12) 다른 점수와 자릿수를 맞춘다
_CATEGORY_CHANGE_WEIGHT = 2.0
_PREDICTION_WEIGHT = 2.0

# 특보급 날씨는 그 날 가장 할 말이 많다. 기준은 기상청 주의보 발효 기준을 그대로 쓴다 —
# 우리가 고른 숫자가 아니다. 서울경기 일별 극값 615 일에서 36 일(6%)이 여기 걸린다.
_COLD_WAVE_MIN_TEMP = -12  # 한파주의보: 아침 최저기온 -12℃ 이하
_HEAT_WAVE_MAX_TEMP = 33  # 폭염주의보: 최고기온 33℃ 이상
_WEATHER_ALERT_SCORE = 1.0

# 아이스 음료 비중이 기온에 따라 움직이는 구간과 기울기. 둘 다 실측값이다 —
# docs/experiments/2026-09-08-weather-sales.md §1 (267 일, 상관 0.759).
#
#   기온 0℃대 0.338 → 18℃대 0.454 → 20℃대 0.478 (18℃ 위는 포화)
#   18℃ 미만 구간 기울기: 기온 1 도당 아이스 비중 +0.61%p
#
# _ICE_RATIO_SPAN 은 실험이 관측한 전체 변동폭(0.338~0.478)이다. 환산한 변동폭을 이 값으로
# 나눠 0~1 로 만든다 — 다른 축과 자릿수를 맞추려고 임의로 곱하는 가중치를 쓰지 않는다.
_ICE_SATURATION_TEMP = 18.0
_ICE_RATIO_PER_DEGREE = 0.0061
_ICE_RATIO_SPAN = 0.14
# 실험의 최저 기온 구간이 (-10, 5] 라, 그보다 낮은 기온은 기울기를 외삽하지 않는다.
_ICE_RATIO_FLOOR_TEMP = -10.0

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
    """한가한 시간대에서 빠져 있는 매출이 전체의 몇 %인가. dayType 별로 재서 큰 쪽을 쓴다.

    2026-10-27: 격차(`1 - 최저/최고`)로 재던 걸 바꿨다. 그 식이 재는 건 "피크가 있나" 인데
    카페는 늘 피크가 있다 — 639 일 실측에서 평균 0.948~0.971·표준편차 0.010~0.021 이었다.
    날짜와 무관한 구조적 상수라, 0.95 를 늘 넘으니 다른 축이 이길 수가 없었고 카드 1·2 가
    시간대·카테고리로 고정됐다.

    균등하게 팔렸다면 영업시간 n 개가 1/n 씩 가져간다. 그보다 모자란 시간들의 몫을 합치면
    "한가한 시간대에서 빠져 있는 매출 비중" 이다. 0 이면 하루 내내 고르게 팔렸다는 뜻이라
    할 말이 없고, 쏠릴수록 커진다. 자릿수를 맞추려고 곱하는 가중치가 없고, 메뉴·카테고리·
    매출총액과 같은 단위(전체 매출 대비 몫)가 된다.

    평일과 주말은 섞지 않는다 — `_hourly_rows` 와 같은 이유다. 따로 재서 더 쏠린 쪽을
    쓴다. 카드는 한 계열을 짚기 때문이다.

    **이 축은 "오늘 특이한가" 를 재지 않는다.** hourlyProfile 에 이전 기간 값이 없어서
    (`HourlyPoint`: dayType·hour·amount) 비교 대상이 아예 없고, 애초에 비교할 날도 없다 —
    BE 는 업로드마다 분석 기간을 잡고 그 사이에는 같은 기간을 다시 쓴다(BE
    `SalesSolutionGenerationContextResolver.resolve` 가 `latestCompletedRun` 을 쓰고,
    `assemble` 이 `end = periodEnd` 로 고정한다). 그래서 다음 업로드까지 이 축을 포함한
    매출 축 점수가 전부 매일 같은 값이다. 날마다 바뀌는 입력은 예측과 날씨뿐이다.

    재는 건 **이 매장 이 기간의 쏠림**이고, 그건 매장·업로드마다 다르다. 이 변경이 푸는 건
    그래서 변별력이 아니라 **다른 축을 누르던 높이**다(0.96 → 0.255).
    근거: docs/experiments/2026-10-26-solution-axis-scores.md §9

    비교할 행이 2 개가 안 되면 -1.0 으로 후보에서 아예 뺀다. 0.0 을 돌려주면 "할 말은
    없지만 후보" 가 되어 카드로 배정되고, 모델은 배정받은 지표로 뭐든 써야 하니 **없는
    비교를 지어낸다** — 2026-10-16 배포본에서 행이 하나뿐인데 "평일 9시 매출이 다른
    시간대에 비해 현저히 낮습니다"가 나왔다. 비교가 이 축의 존재 이유라, 비교할 게
    없으면 축 자체가 성립하지 않는다.
    """
    selling = _selling(_open_hours(points, hours))
    scores = []
    for day_type in dict.fromkeys(p.get("dayType") for p in selling):
        amounts = [p.get("amount") or 0 for p in selling if p.get("dayType") == day_type]
        total = sum(amounts)
        if len(amounts) < 2 or total <= 0:
            continue
        even = 1.0 / len(amounts)
        scores.append(sum(max(0.0, even - amount / total) for amount in amounts))
    return max(scores) if scores else -1.0


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


def _category_share_shift(points: list[dict]) -> dict[str, float]:
    """카테고리별 비중이 이전 기간 대비 몇 %p 움직였나. 부호를 유지한다.

    전체 매출을 더 받지 않아도 된다 — `share` 와 `vsPrevPeriod` 로 이전 기간 비중이
    복원된다. `prev_i = share_i / (1 + vsPrevPeriod_i)` 는 전체 매출 배수만큼 어긋난
    값이라, 그 합으로 나눠 비중으로 되돌린다.

    vsPrevPeriod 가 null 이면 이전 기간에 없던 카테고리다 — 등장 자체가 구성 변화라
    이전 비중 0 으로 둔다. -1.0(이전 매출이 통째로 사라진 경우)은 분모가 0 이 되는데,
    그 카테고리는 현재 매출이 0 이라 비중도 0 이다 — `_menu_share_delta` 와 같은 처리다.
    """
    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    for point in points:
        share = point.get("share") or 0.0
        change = point.get("vsPrevPeriod")
        current[point.get("name")] = share
        previous[point.get("name")] = (
            0.0 if change is None or change == -1.0 else share / (1.0 + change)
        )
    scale = sum(previous.values())
    if scale <= 0:
        return {}
    return {name: share - previous[name] / scale for name, share in current.items()}


def _category_rows(points: list[dict]) -> list[dict]:
    """비중이 많이 움직인 몇 종. 점수와 같은 기준으로 골라야 한다.

    2026-10-27: 비중 상위로 고르던 걸 바꿨다. 점수를 구성 변동으로 바꾸면서 기준이
    어긋났다 — 매장 2 곳 639 일에서 **가장 많이 움직인 카테고리가 비중 상위 5 종에 없는
    날이 17~23%** 였다. 그 날엔 모델이 "구성이 재편됐다" 는 카드를 받고도 움직이지 않은
    카테고리만 보게 된다. `_menu_rows` 에서 먼저 겪은 것과 같은 문제다.

    비교할 게 없으면(첫 업로드) 변동이 전부 0 이라 비중 상위로 떨어진다.
    """
    shift = _category_share_shift(points)
    return sorted(
        points,
        key=lambda p: (abs(shift.get(p.get("name"), 0.0)), p.get("share") or 0.0),
        reverse=True,
    )[:_TOP_SHARES]


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
    """카테고리 **구성이 얼마나 재편됐나**. 비중의 총변동거리다.

    0 이면 구성이 그대로라 할 말이 없고, 1 이면 통째로 바뀌었다. 비중의 몇 %p 가
    카테고리 사이를 옮겨 갔는지라 0~1 범위가 보장돼, 자릿수용 가중치가 필요 없다.

    2026-10-27: `max(비중, 증감률 최댓값 x 2.0)` 을 바꿨다. 매장 2 곳 639 일에서 **80~90% 의
    날이 1.0 으로 포화**됐고, 포화는 전부 증감항에서 나왔다 — 비중항만 쓰면 평균
    0.414~0.421·표준편차 0.016~0.018 로 상수다. `_menu_score` 가 겪은 꼬리 항목 문제와 같다:
    카테고리가 9~17 종이라 비중 1% 짜리 하나가 +400% 움직이면 `0.5 x 2.0` 으로 상한에 닿는다.

    그런데 메뉴와 **같은 잣대(변화 금액)를 쓰면 안 된다.** 카테고리의 변화 금액은 그
    카테고리에 속한 메뉴들의 변화 금액 합이라 개별 메뉴 최댓값보다 구조적으로 크다 —
    실측에서 메뉴 축의 카드 3 점유가 39% → 16% 로 밀렸다. "메뉴 비중은 카테고리보다
    구조적으로 작다"(`_menu_score`)와 반대 방향인 같은 함정이다.

    그래서 잣대를 가른다. 메뉴는 "한 메뉴가 크게 움직였다"(변화 금액 최댓값), 카테고리는
    "구성이 재편됐다"(총변동). 카드 문장도 그렇게 갈린다.

    비중 쏠림 항(`max(share)`)은 뺐다. "커피가 62%" 는 뉴스가 아니다 — 늘 그렇다
    (`_menu_score` 의 "늘 아메리카노가 1 위다" 와 같은 판단). 639 일 평균 0.414~0.421·표준편차
    0.016~0.018 로, 변별이 아니라 하한을 깔고 있었다. 부수 효과로 "미분류 100%" 같은 퇴화된
    입력은 변동이 0 이라 축에서 탈락한다 — 실매장 639 일에는 그런 날이 0 건이다(§7).
    근거: docs/experiments/2026-10-26-solution-axis-scores.md §9
    """
    shift = _category_share_shift(points)
    return 0.5 * sum(abs(value) for value in shift.values())


def _period_days(period: str | None) -> int:
    """ "2026-01-01~2026-03-31" 에서 일수를 센다. 읽을 수 없으면 0.

    `netSales` 는 하루가 아니라 분석 기간 합계다(2026-10-15 BE 확인). conditionPatterns 의
    `avgSales` 는 **일평균**이라, 둘을 같은 잣대로 놓으려면 기간 일수가 있어야 한다.
    `period` 는 계약상 선택값이다 — BE 어셈블러는 항상 `start + "~" + end` 를 보내지만,
    안 오는 경우 축을 탈락시킨다(아래 `_condition_score`). 없는 분모를 추측하지 않는다.
    """
    if not period or "~" not in period:
        return 0
    start, _, end = period.partition("~")
    try:
        first = date.fromisoformat(start.strip())
        last = date.fromisoformat(end.strip())
    except ValueError:
        return 0
    return (last - first).days + 1 if last >= first else 0


def _rain_patterns(patterns: list[dict] | None) -> list[dict]:
    """강수 조건 패턴만. 지금 BE 가 보내는 condition 은 RAIN 하나뿐이다.

    계약이 배열이라 나중에 다른 조건이 늘 수 있다. 그때 "오늘 비 예보" 게이트로 걸러 놓고
    엉뚱한 조건의 패턴을 쓰면 틀린 문장이 되므로, 조건 이름을 보고 고른다.
    """
    return [p for p in patterns or [] if p.get("condition") == "RAIN"]


def _condition_score(
    patterns: list[dict] | None, summary: dict | None, weather: dict | None
) -> float:
    """과거 비 오는 날의 매출 변화가 하루 매출의 몇 %인가. **오늘 비 예보가 있을 때만.**

    `weatherContext` 는 오늘 예보 스냅샷이라 "비가 와서 매출이 줄었다" 를 뒷받침할 수
    없었고, 그래서 프롬프트가 그 주장을 금지해 왔다. `conditionPatterns` 가 바로 그
    뒷받침 데이터다 — BE 가 최근 12 주의 ASOS 강수 관측과 날짜별 메뉴 판매를 비교해
    결과만 보낸다(1.0mm 이상 RAIN, 0.1mm 미만 기준군, 각 5 일 이상일 때만).

    잣대는 다른 축과 같다 — "전체 매출의 몇 %". `avgSales` 는 일평균이고 `netSales` 는
    기간 합계라, 기간 일수로 나눠 일평균 전체 매출을 만들어 맞춘다. 자릿수를 맞추려고
    곱하는 가중치가 없다.

    **오늘 비 예보가 없으면 후보에서 뺀다.** "비 올 때는 이렇습니다" 는 비 오는 날에만
    할 말이다. 맑은 날에 보내면 점주가 오늘 할 수 있는 게 없다. 판정은 BE 가 보낸
    `rainHours` 를 그대로 쓴다 — 강수확률 몇 %부터 비로 볼지 우리가 고르지 않는다.

    **이 값은 실질적으로 점수가 아니라 게이트다**(2026-10-28 실측). 매장 2 곳 604 창에서
    발동 시 평균 0.019~0.022 · 최대 0.054 로, 다른 축(시간대 0.255 · 매출총액 0.240 ·
    카테고리 0.19)보다 한 자리 작다. 축 순위를 바꾸는 일이 없다.

    그래도 쓸모가 있는 건 `assign` 이 이 값으로 **focus 에 conditionPatterns 를 붙일지**
    정하기 때문이다. 날씨 축은 기온으로 뽑히고(`_weather_score`), 뽑히면 강수 패턴이
    같이 실린다 — 비 예보가 있고 패턴이 성립한 창에서 날씨 카드가 3 장 안에 든 비율이
    18~25% 이고, **든 경우에는 100%(11/11, 13/13) conditionPatterns 를 함께 받았다.**
    `max()` 로 묶여 있어 이 값이 작아도 해가 없다.

    왜 작은가. BE 는 `|vsBaseline|` 가 큰 메뉴 **3 종만** 보낸다 — 상대 변화가 큰 순이라
    절대 금액이 큰 순이 아니다. 그래서 이 세 종의 금액 변화 합은 매장 전체의 강수 영향을
    대표하지 못한다. 매장 전체 효과를 점수로 쓰려면 비 온 날/무강수 날의 **일평균 전체
    매출**이 계약에 있어야 한다(BE 에 요청 예정). 그 값이 오면 `_summary_score` 와 같은
    단위(증감률)가 되고, 점주가 실제로 궁금한 숫자이기도 하다.

    `isNotable` 은 보지 않는다. 그 값은 "오늘 예보가 카드 한 장 값을 하나" 에 대한 BE
    판정이고, 이 값을 만드는 건 과거 실측이다. 게이트를 우회하는 모양이지만 **관측 가능한
    효과가 없다** — 0.02 로는 3 장 안에 못 든다. 실측 전에는 리뷰에서 정할 문제로 올렸는데,
    숫자가 나온 뒤로는 정할 것이 없다.

    BE 가 "변화율은 상관관계이며 강수의 인과 효과로 단정하지 않는다" 고 명시했다.
    `sampleWeekdayRatio`·`baselineWeekdayRatio` 가 다르면 비 온 날과 기준일의 평일/주말
    구성이 달라 요일 효과가 섞인다. 거르는 문턱을 임의로 정하지 않고 두 값을 그대로
    프롬프트에 넘긴다 — 아는 한계이고, 문턱은 실측 후에 정한다.
    """
    rain = _rain_patterns(patterns)
    if not rain:
        return -1.0
    if not (weather or {}).get("rainHours"):
        return -1.0
    days = _period_days((summary or {}).get("period"))
    net_sales = (summary or {}).get("netSales") or 0
    if days <= 0 or net_sales <= 0:
        return -1.0
    daily = net_sales / days
    shifts = [
        sum(
            abs((menu.get("avgSales") or 0) - (menu.get("baselineAvgSales") or 0))
            for menu in pattern.get("menus") or []
        )
        for pattern in rain
    ]
    return min(max(shifts) / daily, 1.0)


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
    """특보급이면 1 순위, 기온이 아이스/핫 구성을 갈라놓는 날이면 그 변동폭만큼.
    둘 다 아니면 **후보에서 뺀다** — 평범한 날에 날씨 카드가 나가지 않는다.

    2026-10-14 에는 isNotable 만 보고 고정값 0.3 을 줬다. 그게 "다른 축이 할 말 없을 때만
    보충" 이라는 설계와 반대로 동작했다 — 매장 2 곳 639 일 실측에서 매출총액 축 점수가
    평균 0.240 이라 **0.3 이 3 번 자리를 65~69% 차지했고** 메뉴 축은 아예 사라졌다.
    그리고 기상청 서울경기 615 일 중 68% 가 "하루 종일 18℃ 위" 또는 "하루 종일 18℃ 아래" —
    즉 아이스/핫 구성이 하루 안에서 갈리지 않는 평범한 날인데 같은 0.3 을 받았다.

    이제 0.3 고정값을 쓰지 않고 실측 기울기로 환산한다. 하루 최저~최고가 아이스 비중
    포화점(18℃)을 **가로지르는** 날은 오전·오후의 음료 구성이 갈려서 "오전엔 핫, 오후엔
    아이스를 준비하세요" 같은 실행 가능한 말이 나온다. 포화점 위아래로만 머문 날은
    구성이 하루 내내 같아 할 말이 없다.
    근거: docs/experiments/2026-09-08-weather-sales.md §1

    isNotable 게이트는 그대로 둔다 — "BE 판정이 우선이고 우리가 덮어쓰지 않는다" 는
    기존 결정이다. 바뀌는 건 그 **안쪽**이다: 예전엔 notable 이면 무조건 0.3 을 줬고,
    이제는 기온이 구성을 갈라놓는 날에만 점수가 나온다. 강수는 conditionPatterns(과거
    강수별 메뉴 판매)로 이미 입력이 오는데 점수식에 연결돼 있지 않다(이슈 #194) —
    비는 그쪽에서 다루는 게 맞다.

    **태풍·대설은 여전히 판정할 수 없다.** 풍속도 적설도 계약에 없다. BE 에 특보 발효
    여부를 받는 쪽이 정확하다 — PR #227(weatherContext.alerts)로 진행 중이다.
    """
    if not weather or not weather.get("isNotable"):
        return -1.0
    low, high = weather.get("minTempC"), weather.get("maxTempC")
    if (low is not None and low <= _COLD_WAVE_MIN_TEMP) or (
        high is not None and high >= _HEAT_WAVE_MAX_TEMP
    ):
        return _WEATHER_ALERT_SCORE
    if low is None or high is None or not low < _ICE_SATURATION_TEMP <= high:
        return -1.0
    swing = (_ICE_SATURATION_TEMP - max(low, _ICE_RATIO_FLOOR_TEMP)) * _ICE_RATIO_PER_DEGREE
    return min(swing / _ICE_RATIO_SPAN, 1.0)


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

    상권(districtBenchmark)은 인사이트로 가서 솔루션 축에는 포함하지 않는다(2026-10-13).

    2026-10-27: 다섯 축의 점수가 처음으로 **같은 단위**가 됐다 — 전부 "전체 매출(또는
    비중)의 몇 %" 다. 자릿수를 맞추려고 곱하는 가중치는 매출총액·예측 두 축에만 남았다.
    그 전까지는 시간대(평균 0.96)와 카테고리(80~90% 포화)가 카드 1·2 를 사실상 고정했고,
    "오늘 할 말이 있는 것만 고른다" 가 선택으로 작동하지 않았다.
    근거: docs/experiments/2026-10-26-solution-axis-scores.md §9
    """
    summary = metrics.get("salesSummary") or {}
    hourly = metrics.get("hourlyProfile") or []
    category = metrics.get("categoryBreakdown") or []
    predicted = metrics.get("predictedSalesToday")
    weather = metrics.get("weatherContext")
    menus = metrics.get("menuRankings") or []
    conditions = metrics.get("conditionPatterns") or []

    total_focus: dict = {"salesSummary": summary} if summary else {}
    if predicted is not None and total_focus:
        total_focus["predictedSalesToday"] = predicted
    total_score = max(
        _summary_score(summary) if summary else -1.0,
        _prediction_score(predicted, summary.get("netSales") or 0) if predicted else -1.0,
    )

    # conditionPatterns 는 weatherContext 와 한 축으로 묶는다 — 둘 다 "오늘 날씨" 얘기라
    # 따로 배정하면 카드 두 장이 같은 소재가 된다(salesSummary + predictedSalesToday 를
    # 묶은 것과 같은 판단). 묶으면 카드 한 장이 "오늘 비 예보 → 과거 비 오는 날 이 메뉴가
    # 이만큼 덜 팔렸다 → 그래서 이렇게 하라" 로 이어진다.
    weather_focus: dict = {"weatherContext": weather} if weather else {}
    condition_score = _condition_score(conditions, summary, weather)
    if condition_score >= 0.0:
        weather_focus["conditionPatterns"] = _rain_patterns(conditions)
    weather_score = max(_weather_score(weather), condition_score)

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
        (weather_focus, weather_score),
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
