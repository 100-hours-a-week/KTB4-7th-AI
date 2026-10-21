"""프롬프트가 요구하는 규칙을 코드로 검사한다 — 로컬 모델·프롬프트 변경 평가용.

왜 있나. 지난 열흘간 잡은 결함이 전부 *그럴듯한데 틀린* 출력이었다.
`0.042 → "4% 증가"`, ratio 분모 착각, 같은 금액 반복, `WEEKDAY` 를 "금요일"로 바꿔 쓰기 —
전부 눈으로는 정상이라 사람이 20번 읽어도 못 찾는다. pytest 는 목(mock)을 쓰므로
끝까지 초록이고, curl 한 번은 한 표본이라 70% 성공률을 100%로 착각하게 만든다.

쓰는 법. 같은 요청을 N 회 호출해 통과율을 본다. 개별 항목이 95% 여도 곱하면 확 떨어지므로
**모든 항목을 동시에 통과한 비율**이 출하 판정 숫자다.

주의. 여기 규칙은 프롬프트를 그대로 옮긴 것이라 프롬프트가 바뀌면 같이 썩는다. 실제로
2026-10-01(PR #115)에 솔루션 프롬프트가 재설계되면서 이 파일의 이전 판이 **폐기된 규칙을
계속 재고 있었다** — `수치_evidence만`(수치는 evidence 에만)은 그때 반대 방향으로 뒤집혔고
`detail_2문장`은 세 문장으로 바뀌었는데, 채점기는 몰라서 "Claude 가 규칙을 60% 어긴다"는
틀린 결론을 냈다. 그래서 tests/test_grade.py 가 TARGET_* 와 프롬프트 VERSION 이 어긋나면
실패한다 — 프롬프트를 고치면 이 파일을 같이 보게 강제한다.
"""

import json
import re

# app 패키지를 import 하지 않는다. Colab 에 이 파일 하나만 복사해서 쓰려면 anthropic·openai·
# google-genai 까지 깔아야 하는 상황을 만들면 안 된다. 대신 app/clients/llm.py 의 strip_fence
# 를 그대로 옮겨 두고, 둘이 어긋나면 tests/test_grade.py 가 잡는다.
_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_fence(raw: str) -> str:
    """모델이 JSON 을 ```json 펜스로 감싸 내려주는 경우가 있어 벗긴다(서비스와 동일)."""
    match = _FENCE.match(raw.strip())
    return match.group(1) if match else raw


# 이 채점기가 대조한 프롬프트 판. 프롬프트 VERSION 이 올라가면 규칙을 다시 읽고 여기도 올린다.
# 2026-10-11 은 2회차(재시도) 프롬프트에 1회차 위반 피드백을 덧붙이는 변경이다 — 1회차
# 프롬프트와 기존 규칙 문장은 하나도 안 바뀌었다. 이 채점기는 모델 출력만 채점하므로
# 검사 항목은 손대지 않았다.
# 2026-10-08 은 규칙 문장을 하나도 바꾸지 않았다 — 고정 규칙과 지표의 순서만 바꿨고
# (접두 캐싱), 인사이트는 문장별 지표 배정이 추가됐다. 검사 항목은 손대지 않았다.
# 2026-10-07 은 입력 구조만 바뀌었고(카드별 근거 지표 배정) 카드 작성 규칙은 그대로라
# 검사 항목은 손대지 않았다. `카드_지표_중복없음` 이 100% 로 올라가는지 보는 게 이번 변경의
# 측정 목표다.
# 2026-10-14 는 weatherContext(네 번째 근거 축)가 들어오며 "날씨만으로 과거 매출과의
# 인과를 주장하지 말라"는 새 규칙이 추가됐다 — `날씨_인과_주장_없음`을 새로 잰다. 기존
# 항목은 손대지 않았다.
# 2026-10-15 는 DUPLICATE_FIGURE/VAGUE_ACTION에 더해 "현재 기간"처럼 날짜 없이 기간을
# 가리키는 말을 금지하는 규칙이 추가됐다(점주 신고) — `기간_날짜_명시`를 새로 잰다.
# 2026-10-15 는 districtBenchmark(여섯째 근거 축, #157)가 들어오며 "행정동 평균일 뿐
# 매장 개별 실적이 아니고, 상권 상태로 매출 인과를 주장하지 말라"는 규칙이 추가됐다 —
# `상권_인과_주장_없음`을 새로 잰다. 기존 항목은 손대지 않았다.
# 2026-10-21 은 districtBenchmark 중첩 객체를 전용 근거 축에서 빼고, 대신 평평한
# 필드(districtAvgMonthlySalesPerCafe·vsDistrictAvg·peakSalesHourBand·
# peakFootTrafficHourBand)로 쪼개 salesSummary·hourlySales 두 축에 조건부로
# 끼워 넣는 변경이다(#209). "숙주가 그 달 안 뽑힌 것"(정상)과 "뽑혔는데 상권 값을
# 안 쓴 것"(결함)을 분모가 다른 항목으로 나눠 잰다 —
# `salesSummary_선정률`·`hourlySales_선정률`(분모: 전체 요청)과
# `상권_평균매출_반영`·`상권_피크밴드_반영`(분모: 게이트 통과 + 해당 값이 문장에
# 인용된 요청만, 수치뿐 아니라 비교 방향까지 확인)을 새로 잰다. 기존 항목은
# 손대지 않았다.
TARGET_SOLUTION_VERSION = "2026-10-20"
TARGET_INSIGHT_VERSION = "2026-10-21"

# 문장에서 뽑아낼 숫자 (쉼표 제거 후 비교한다)
_ANYNUM = re.compile(r"\d[\d,]*\.?\d*")
# "3만원", "1억2천만원" 처럼 만/억 단위로 줄여 쓴 금액 — 프롬프트가 금지한다.
# app/services/solution.py 의 _ROUNDED_AMOUNT 와 같은 패턴이다(tests 가 대조한다).
_ROUNDED = re.compile(r"\d[\d,]*\s*[억만][\d\s억만천백]*원")
# 12시간제 표기 — 프롬프트는 지표에 있는 24시간제를 그대로 쓰라고 한다
# 서비스의 app/services/solution.py::_WORDS 와 같은 접두어를 봐야 한다. 2026-10-08 측정에서
# `시각_24시간제` 77.8% 가 전부 오탐이었다 — "오후 2시간 동안" 은 지속시간인데 `(?!간)` 이
# 없어서 12 시간제로 셌고, 반대로 "낮"·"아침" 은 아예 안 봐서 치환 버그를 못 잡았다.
_AMPM = re.compile(r"(오전|오후|새벽|아침|낮|저녁|밤)\s*\d{1,2}\s*시(?!간)")
# 배율은 직접 계산하지 말라고 되어 있다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다.
_RATIO_WORD = re.compile(
    r"(?:\d+(?:\.\d+)?|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배(?![달치송포분])"
    r"|\d+\s*분의\s*\d+"
)
# 화면에 보여줄 금액·비율. 실행 지시용 작은 수(21시, 1명)와 구분하려고 자릿수·단위를 본다.
_DISPLAY_NUM = re.compile(r"[\d,]{4,}\s*원|\d+\.?\d*\s*%")

# 행동의 "얼마나" — 지표에 없는 값이라 지어낸 것이다. 마진을 모르는데 할인율을,
# 인건비 대비 생산성을 모르는데 인원을 말할 근거가 없다(2026-10-07). 시각은 지표에
# hour 로 있으므로 _ungrounded 가 따로 본다.
_FABRICATED_AMOUNT = re.compile(
    r"\d+\s*%\s*(?:할인|세일|디스카운트|인하)"
    r"|(?:직원|인력|스태프|알바|인원)[을를]?\s*\d+\s*명"
    r"|\d+\s*명\s*(?:추가|배치|더|이상)"
    r"|\d+\s*(?:kg|키로|g|그램|잔|개|병|박스|리터)\s*[을를]?\s*(?:준비|발주|주문|구비|입고)"
)
# 누구나 할 수 있는 말. 점주가 오늘 무엇을 다르게 할지가 안 나온다.
_VAGUE_ACTION = re.compile(
    # 사이에 다른 말이 끼어도 잡는다. 붙어 있을 때만 보던 옛 패턴은 "프로모션과 추천
    # 강화로" 를 놓쳤고, 실측 218 개 실행 문장에서 **0 개**를 잡았다(2026-10-16) —
    # 교과서 문구만 걸려서 `공허한_조언_없음` 100% 가 아무 의미가 없었다.
    r"(?:마케팅|홍보|프로모션|캠페인|전략|활동|노력|서비스)[^.。\n]{0,10}?"
    r"(?:강화|개선|변경|확대|진행|실행|집중)"
    # 대상이 구체적이어도 "강도만 올려라" 는 점주가 오늘 뭘 다르게 할지 알 수 없다.
    # 진행·실행·집중은 여기 안 넣는다 — "인력을 집중 배치" 같은 구체적 행위가 걸린다.
    r"|(?:추천|이벤트|관리|메뉴|매출|비중|고객층|경험)[^.。\n]{0,10}?"
    r"(?:강화|개선|활성화|제고|증대|도모|최적화|극대화)"
)
# 날짜 없이 기간을 가리키는 말. app/services/solution.py::_VAGUE_PERIOD 와 같은 패턴.
_VAGUE_PERIOD = re.compile(r"(?:현재|이번|해당|지금)\s*기간")
# weatherContext 는 오늘 예보 스냅샷이라 과거 매출과의 인과를 뒷받침할 지표가 없다
# (conditionPatterns 미도입, 2026-10-14). "비가 와서/때문에 매출이 줄었다" 식 주장을 잡는다.
_WEATHER_CAUSAL = re.compile(
    r"(?:비|눈|날씨|기온|강수)[가이]?\s*(?:와서|내려서|오는\s*바람에)?\s*(?:때문에|탓에|영향으로|영향을\s*받아)"
)
# districtBenchmark 는 행정동 평균 추정치일 뿐 매장 개별 실적이 아니다(2026-10-15, #157).
# "상권이 좋아서/나빠서 매출이 ~했다" 식 인과 주장을 잡는다.
_DISTRICT_CAUSAL = re.compile(
    r"(?:상권|행정동|주변\s*(?:카페|업소))[이가]?\s*(?:좋아서|나빠서|활발해서|침체돼서|때문에|탓에|영향으로|영향을\s*받아)"
)

# app/services/insight_focus.py::_district_gate 와 같은 로직이어야 한다 — app 을
# import 하지 않으려고 복사해 둔 값이다(둘이 어긋나면 tests/test_grade.py 가 잡는다).
_MIN_CAFE_STORE_COUNT = 3


def _district_gate(district: dict | None) -> bool:
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0


# app/services/insight_focus.py::district_comparison 과 같은 로직이어야 한다.
def _comparison(total_sales: int, district_avg: int) -> str:
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


# app/services/insight_focus.py::_store_peak_hour·_in_band 와 같은 로직이어야 한다.
def _store_peak_hour(points: list[dict]) -> int | None:
    selling = [p for p in points if (p.get("menuSales") or 0) > 0]
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int, band: str) -> bool:
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end


def _axis_selected(body: str, metrics: dict, key: str) -> bool:
    """그 축이 생성 문장에 실제로 쓰였는지 — assign() 선정 여부의 근사치.

    assign() 의 6 축 점수식을 복제하지 않는다(여긴 app 을 import 하지 않는다는
    전제라 과하다, 모듈 머리말 참고) — 대신 "이 축 숫자가 문장에 등장했는지"로
    선정 여부를 근사한다. _metric_paths/_evidence_group 과 같은 방식이다.

    인덱스는 지표 전체로 만든다. 그 축만으로 만들면 _evidence_group 의 모호성
    필터("여러 지표에 걸치는 숫자는 판단에 쓰지 않는다")가 꺼져서, 다른 축과 값이
    겹치는 숫자(실측: salesSummary.orderCount 923 == menuRankings[].quantity 923)
    하나로 숙주가 선정된 것처럼 오판한다 — 그러면 상권_평균매출_반영이 None 이어야
    할 요청에서 거짓 결함으로 집계된다(#209 최종 리뷰 Important #3).
    """
    if not metrics.get(key):
        return False
    return key in _evidence_group(body, _metric_paths(metrics))


_DIRECTION_WORDS = {
    "ABOVE": ("높", "웃돌", "상회"),
    "BELOW": ("낮", "밑돌", "하회"),
    "EQUAL": ("같습니다", "동일"),
    "SAME": ("겹칩니다", "일치합니다"),
    "DIFFERENT": ("겹치지 않", "다른 시간대", "불일치"),
}
_OPPOSITE = {
    "ABOVE": "BELOW",
    "BELOW": "ABOVE",
    "EQUAL": None,
    "SAME": "DIFFERENT",
    "DIFFERENT": "SAME",
}


# "9,413,000" 같은 천 단위 구분 쉼표는 절 경계가 아니라 숫자의 일부다 — 그대로
# "[,.\n]" 로 나누면 절마다 숫자가 조각나 anchor(예: "9413000")가 어느 절에도
# 통째로 안 남는다(#209 리뷰 Important #1 수정 중 실측으로 발견).
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _split_clauses(body: str) -> list[str]:
    return re.split(r"[,.\n]", _THOUSANDS_COMMA.sub("", body))


def _direction_correct(body: str, comparison: str, anchor: str) -> bool:
    """방향 어휘가 실제 계산 결과와 반대로 쓰였는지만 본다 — 간단한 어휘 대조다
    (완전한 자연어 이해는 아니다, 1 차는 검출 시도 수준). 올바른 어휘가 없어도
    (수치만 언급) 통과시킨다 — 의견 없는 문장을 결함으로 몰지 않는다. 반대
    방향 어휘가 있을 때만 실패시킨다(설계 'C').

    anchor 가 들어간 구(쉼표·마침표로 나눈 절)에서만 반대 방향 어휘를 찾는다.
    본문 전체를 보면 anchor 와 무관한 문장의 반대 어휘에도 오염된다 — 처음엔
    이 함수가 본문 전체를 봤는데, "총 매출은... 상권 평균보다 높습니다, 토요일
    매출이... 가장 낮습니다" 처럼 상권과 무관한 문장의 "낮습니다"가 ABOVE 판정을
    반대로 오판하는 사고가 실제로 났다(#209 리뷰 Important #1). 밴드 두 개가
    한 문장에 같이 있을 때 서로의 반대 어휘에 오염되는 것과 같은 실패 모양이라
    평균 쪽에도 똑같이 절 단위 스캔을 적용한다.
    """
    opposite = _OPPOSITE[comparison]
    if not opposite:
        return True
    for clause in _split_clauses(body):
        if anchor in clause and any(word in clause for word in _DIRECTION_WORDS[opposite]):
            return False
    return True


def _district_avg_reflected(body: str, metrics: dict) -> bool | None:
    """게이트를 통과하고 salesSummary 가 실제로 선정됐을 때만 유효한 측정이다(#209 "A").

    둘 중 하나라도 아니면 None — "선정 안 됨"은 결함이 아니다. devtools/bench.py
    가 None 을 분모에서 뺀다(설계 리뷰 — 안 빼면 실제보다 낮게 보인다). 값이
    보여도 방향이 반대면 실패로 센다(설계 'C') — anchor 는 상권 평균 숫자다.
    """
    district = metrics.get("districtBenchmark")
    if not _district_gate(district):
        return None
    if not _axis_selected(body, metrics, "salesSummary"):
        return None
    avg = str(district["districtAvgMonthlySalesPerCafe"])
    if avg not in _numbers_in(body):
        return False
    summary = metrics.get("salesSummary") or {}
    comparison = _comparison(
        summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"]
    )
    return _direction_correct(body, comparison, avg)


# "2026Q3"·"2026년 3분기" 두 표기 다 잡는다. basisQuarter 는 focus 블록에 안 보내기로
# 했지만(#209), _metric_numbers 가 문자열에서 3자리 이상을 뽑아 "2026" 이 이미 허용
# 집합에 있어 UNGROUNDED_NUMBER 로는 못 잡는다 — 모델이 어디선가 주워 인용해도 통과한다.
_QUARTER_MENTION = re.compile(r"(\d{4})\s*(?:Q([1-4])|년\s*([1-4])\s*분기)")


def _quarter_leak(body: str, metrics: dict) -> bool | None:
    """분기를 인용했으면 그 값이 실제 basisQuarter 와 같은지. 인용 안 했으면 None."""
    match = _QUARTER_MENTION.search(body)
    if not match:
        return None
    quarter = match.group(2) or match.group(3)
    cited = f"{match.group(1)}Q{quarter}"
    real = (metrics.get("districtBenchmark") or {}).get("basisQuarter")
    return cited == real


def _band_mentioned(body: str, band: str) -> bool:
    start, end = band.split("-")
    numbers = _numbers_in(body)
    return start in numbers and end in numbers


def _band_direction_correct(body: str, comparison: str, band: str) -> bool:
    """밴드 쪽 호출부 — anchor 로 그 밴드의 시작 시각을 쓴다(매출·유동인구 두
    비교가 한 문장에 같이 있을 때 서로의 반대 어휘에 오염되지 않게, `_direction_correct`
    참고)."""
    start, _ = band.split("-")
    return _direction_correct(body, comparison, start)


def _district_band_reflected(body: str, metrics: dict) -> bool | None:
    """게이트를 통과하고 두 밴드가 모두 문장에 인용됐을 때만 유효한 측정이다(#209 "A").

    hourlySales candidate는 두 밴드·두 비교 필드를 같은 한 문장에 묶어 넘긴다
    (vsDistrictAvg가 salesSummary 문장에 묶이는 것과 같은 구조, 위 "A" 주석 참고) —
    한쪽만 말하고 다른 쪽을 빠뜨리면 결함이다("문장마다 근거 하나"는 축 사이의
    얘기라 같은 축 번들 안의 누락엔 안 걸린다. 재검토로 "둘 다 요구"로 되돌림,
    2026-10-21(6)). 둘 다 언급 안 됐으면 이번엔 hourlySales 가 선정 안 된 것으로
    보고 None — 결함이 아니다.
    """
    district = metrics.get("districtBenchmark")
    if not _district_gate(district):
        return None
    sales_band = district["peakSalesHourBand"]
    traffic_band = district["peakFootTrafficHourBand"]
    sales_mentioned = _band_mentioned(body, sales_band)
    traffic_mentioned = _band_mentioned(body, traffic_band)
    if not sales_mentioned and not traffic_mentioned:
        return None
    if not (sales_mentioned and traffic_mentioned):
        return False
    peak_hour = _store_peak_hour(metrics.get("hourlySales") or [])
    if peak_hour is None:
        # 우리 매장 피크를 계산할 수 없었던 달이다(app 쪽과 같은 이유로
        # vsDistrictSalesPeak/vsDistrictFootTrafficPeak 가 안 보내진다) — 비교를
        # 요구하지 않고 둘 다 인용됐는지만으로 통과시킨다.
        return True
    sales_comparison = "SAME" if _in_band(peak_hour, sales_band) else "DIFFERENT"
    traffic_comparison = "SAME" if _in_band(peak_hour, traffic_band) else "DIFFERENT"
    return _band_direction_correct(body, sales_comparison, sales_band) and _band_direction_correct(
        body, traffic_comparison, traffic_band
    )


_DOW_KO = {
    "MONDAY": "월요일",
    "TUESDAY": "화요일",
    "WEDNESDAY": "수요일",
    "THURSDAY": "목요일",
    "FRIDAY": "금요일",
    "SATURDAY": "토요일",
    "SUNDAY": "일요일",
}


# 배율은 "지표에 있으면 인용, 없으면 날조" 다(2026-10-16). 서비스가
# app/services/solution_focus.py::derive 로 hourlyPeakRatio 를 넣어 주고, 러너는 채점 전에
# 같은 함수를 부른다 — 안 부르면 지표에 있는 배율을 날조로 센다.
# _metric_numbers 전체를 쓰지 않는 이유: hour 값(14·18)이 섞여 "14배" 가 통과한다.
# app/services/solution.py 의 같은 이름 함수들과 로직이 같아야 한다.
_RATIO_KEYS = ("hourlyPeakRatio",)
_KO_NUMERALS = {
    "두": "2",
    "세": "3",
    "네": "4",
    "다섯": "5",
    "여섯": "6",
    "일곱": "7",
    "여덟": "8",
    "아홉": "9",
    "열": "10",
}


def _allowed_ratios(metrics) -> set[str]:
    out: set[str] = set()
    for key in _RATIO_KEYS:
        for item in metrics.get(key) or []:
            value = item.get("ratio") if isinstance(item, dict) else item
            if isinstance(value, int | float) and not isinstance(value, bool):
                out.add(f"{float(value):g}")
    return out


def _ratio_value(text: str) -> str | None:
    head = text.split("배")[0].strip()
    if head in _KO_NUMERALS:
        return _KO_NUMERALS[head]
    try:
        return f"{float(head):g}"
    except ValueError:
        return None


def _ungrounded_ratios(texts, metrics) -> bool:
    allowed = _allowed_ratios(metrics)
    for text in texts:
        for match in _RATIO_WORD.finditer(text):
            value = _ratio_value(match.group())
            if value is None or value not in allowed:
                return True
    return False


def _metric_numbers(metrics) -> set[str]:
    """지표에 실제로 있는 값들. 금액은 그대로, 비율은 백분율로도 인정한다.

    2026-10-16(PR #161 리뷰, 헥터): 문자열 값은 숫자를 통째로 버리고 있었다.
    `basisQuarter: "2026Q3"`·`salesTrend[].date: "2026-09-12"` 같은 값의 "2026"을 모델이
    그대로 인용해도 허용 집합에 없어 환각(`수치_정확` 실패)으로 오판했다 — 프롬프트가
    인용을 금지하지 않는 값인데 채점기가 막고 있었다. 3자리 미만은 뽑지 않는다 — 2자리
    이하는 `_ungrounded`가 이미 "실행 지시"로 봐주므로 필요가 없고, 그대로 다 뽑으면
    `basisDateTime: "2026-10-07 11:00"`의 "10"이 "10% 할인" 같은 진짜 실행 지시 숫자와
    충돌해 `_metric_figures`(필드간 중복 검사)가 오탐한다(실측: 기존 테스트가 깨짐).
    """
    out: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.add(str(value))
        elif isinstance(value, float):
            out.add(f"{value:g}")
            out.add(f"{abs(value) * 100:g}")  # 0.417 → 41.7
            out.add(f"{round(abs(value) * 100):g}")  # 0.12  → 12
        elif isinstance(value, str):
            out.update(
                m.group() for m in _ANYNUM.finditer(value) if len(m.group().split(".")[0]) >= 3
            )

    walk(metrics)
    return out


def _numbers_in(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _ANYNUM.finditer(text)}


def _ungrounded(text: str, metrics) -> set[str]:
    """지표에 없는 숫자. 자릿수 오류·환각을 잡는다.

    한두 자리는 시각·인원·할인율 같은 실행 지시로 보고 통과시킨다 — 프롬프트가 허용한다.
    """
    allowed = _metric_numbers(metrics)
    bad = set()
    for number in _numbers_in(text):
        if number in allowed:
            continue
        try:  # 12.0 == 12 같은 표기 차이는 허용
            if any(abs(float(number) - float(a)) < 1e-9 for a in allowed):
                continue
        except ValueError:
            pass
        if len(number.split(".")[0]) <= 2:
            continue
        bad.add(number)
    return bad


def _metric_figures(text: str, metrics) -> set[str]:
    """그 문장이 인용한 '지표 수치'. 화면에 금액·비중으로 보이는 값만 센다.

    두 겹으로 거른다. 먼저 금액(네 자리 이상 + 원)과 백분율만 보고, 그중 지표에 실제로
    있는 값만 남긴다.

    - "21시까지"·"직원 1명"은 시각·인원이라 애초에 금액·비율이 아니다. 시각은 지표에도
      들어 있어서(hour: 14) 지표 포함 여부만으로는 거를 수 없다 — 단위를 같이 봐야 한다.
    - "10% 할인"은 백분율이지만 지표에 없는 값이라 실행 지시다.

    둘 다 프롬프트가 명시적으로 허용하는 표현이라 필드 간 중복 금지 대상이 아니다.
    """
    allowed = _metric_numbers(metrics)
    used = {m.group().replace(",", "").rstrip("원% \t") for m in _DISPLAY_NUM.finditer(text)}
    return {n for n in used if n in allowed}


def _label_hallucination(text: str, metrics) -> set[str]:
    """지표에 없는 요일 라벨. 숫자는 맞는데 차원이 틀리는 오류를 잡는다.

    실제로 `dayType: WEEKDAY` 를 "금요일"로 바꿔 쓴 출력이 나왔다. 숫자만 검증하면 통과한다.
    """
    allowed = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "dayOfWeek" and item in _DOW_KO:
                    allowed.add(_DOW_KO[item])
                elif key == "dayType":
                    allowed.add("평일" if item == "WEEKDAY" else "주말")
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(metrics)
    return {ko for ko in _DOW_KO.values() if ko in text} - allowed


def _metric_paths(metrics: dict) -> dict[str, set[str]]:
    """숫자 → 최상위 지표 키 역인덱스. 카드가 같은 지표를 두 번 인용했는지 보려고 쓴다."""
    out: dict[str, set[str]] = {}

    def walk(value, top):
        if isinstance(value, dict):
            for item in value.values():
                walk(item, top)
        elif isinstance(value, list):
            for item in value:
                walk(item, top)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.setdefault(str(value), set()).add(top)
        elif isinstance(value, float):
            for text in (f"{value:g}", f"{abs(value) * 100:g}", f"{round(abs(value) * 100):g}"):
                out.setdefault(text, set()).add(top)

    for key, item in metrics.items():
        walk(item, key)
    return out


def _evidence_group(text: str, index: dict[str, set[str]]) -> set[str]:
    """그 문장이 근거로 삼은 지표 키. 여러 지표에 걸치는 숫자는 판단에 쓰지 않는다."""
    out: set[str] = set()
    for number in _numbers_in(text):
        keys = index.get(number, ())
        if len(keys) == 1:
            out |= set(keys)
    return out


# 서비스가 요청한 카드 수. 2026-10-07(#123) 부터 배정된 지표가 3 종이 안 되면 그만큼만
# 내보내므로, 호출부가 그 수를 넘겨야 한다. 3 으로 박아두면 설계대로 2 장을 낸 응답을
# 결함으로 센다 — 실제로 2026-10-08 측정에서 `카드3장` 66.7% 가 전부 그거였다.
MAX_CARDS = 3


def grade_solution(raw: str, metrics: dict, expected_cards: int = MAX_CARDS) -> dict:
    """솔루션 카드를 app/prompts/solution.py(2026-10-08) 기준으로 채점한다.

    expected_cards 는 서비스가 요청한 장수다(`len(assign_focus(metrics)) or 3`).
    """
    result: dict = {"parsed": False}
    try:
        cards = json.loads(strip_fence(raw))["solutionCards"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["parsed"] = True
    ranks = [c.get("rankNo") for c in cards]
    titles = [c.get("title") or "" for c in cards]
    summaries = [c.get("summaryText") or "" for c in cards]
    details = [c.get("detailText") or "" for c in cards]
    evidences = [c.get("evidence") or "" for c in cards]
    visible = titles + summaries + details  # evidence 는 화면에 안 나온다(2026-10-02 FE 확정)

    # 2026-10-17 제품 결정: 최소 1 장·최대 3 장. 억지로 채우지 않는다 — 배정 수보다
    # 적게 나오는 건 결함이 아니다. 다만 배정 수보다 **많으면** 근거 없는 카드가 생긴
    # 것이므로 결함이다. 그 전에는 "배정 수와 정확히 일치" 를 쟀다(`카드_개수_일치`).
    result["카드_개수_적정"] = 1 <= len(cards) <= expected_cards
    result["rankNo_고유"] = len(set(ranks)) == len(ranks)
    result["title_200자"] = all(len(t) <= 200 for t in titles)
    result["detail_1000자"] = all(len(d) <= 1000 for d in details)
    result["evidence_있음"] = all(e.strip() for e in evidences)

    # 실행 방법 두 문장 + 기대효과 한 문장 = 줄바꿈 2개 (2026-10-01 재설계)
    result["detail_3문장"] = all(d.count("\n") == 2 for d in details)

    # summaryText 가 쓴 지표 수치를 title·detailText 가 다시 쓰면 안 된다. evidence 는 예외.
    # 지표에 없는 수(시각·인원·할인율)는 실행 지시라 중복 대상이 아니다.
    def _fields_disjoint(card_index: int) -> bool:
        groups = [
            _metric_figures(titles[card_index], metrics),
            _metric_figures(summaries[card_index], metrics),
            _metric_figures(details[card_index], metrics),
        ]
        return all(
            not (groups[i] & groups[j])
            for i in range(len(groups))
            for j in range(i + 1, len(groups))
        )

    result["수치_필드간_중복없음"] = all(_fields_disjoint(i) for i in range(len(cards)))

    result["금액_어림_없음"] = not any(_ROUNDED.search(t) for t in visible + evidences)
    result["시각_24시간제"] = not any(_AMPM.search(t) for t in visible)
    result["배율_없음"] = not _ungrounded_ratios(visible, metrics)
    result["요일_환각_없음"] = not any(
        _label_hallucination(t, metrics) for t in visible + evidences
    )
    # title·summaryText 는 그동안 수치 검사 밖이었다(2026-10-16 발견). 배포본에서
    # "남은 시간 동안 253,196원을 추가로 만들어야 합니다"가 summaryText 에 나왔는데
    # 측정에서는 수치_정확 100% 로 보였다 — 화면에 보이는 필드가 검사에서 빠져 있었다.
    result["summary_수치_정확"] = not any(_ungrounded(t, metrics) for t in titles + summaries)
    result["evidence_수치_정확"] = not any(_ungrounded(e, metrics) for e in evidences)
    result["detail_수치_정확"] = not any(_ungrounded(d, metrics) for d in details)

    # 기대효과(detailText 마지막 문장)는 정성적으로만 — "매출 15% 증가" 같은 날조 금지
    # 실행 문장(detailText 앞 두 문장)과 title 만 본다 — 기대효과 문장은 "매출을 늘릴 수
    # 있습니다" 가 허용이라 같은 잣대로 보면 오탐이 난다.
    actions = titles + [line for d in details for line in d.split("\n")[:2]]
    result["실행수치_날조_없음"] = not any(_FABRICATED_AMOUNT.search(t) for t in actions)
    result["공허한_조언_없음"] = not any(_VAGUE_ACTION.search(t) for t in actions)

    result["기대효과_정성적"] = not any(_DISPLAY_NUM.search(d.split("\n")[-1]) for d in details)

    # 카드끼리 같은 지표를 근거로 쓰면 "서로 다른 지표" 지시 위반이다. 문장이 달라도 중복이다.
    index = _metric_paths(metrics)
    groups = [_evidence_group(e, index) for e in evidences]
    result["카드_지표_중복없음"] = all(
        not (groups[i] & groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups))
    )

    result["날씨_인과_주장_없음"] = not any(_WEATHER_CAUSAL.search(t) for t in visible)

    result["기간_날짜_명시"] = not any(_VAGUE_PERIOD.search(t) for t in visible + evidences)

    result["cards"] = cards
    return result


# 규칙 위반이 아니라 "이번 요청에서 그 축이 선정됐는지"·"분기를 인용했는지" 를 재는
# 측정값들. 3 문장 안에 6 축이 다 선정되지 않는 게 정상이고 정상 인사이트는 분기를
# 인용하지 않으므로 False 가 흔하다 — devtools/bench.py 의 전항목(출하 판정) 집계에
# 그대로 넣으면 상시 0% 가 나온다(#209 리뷰 Important #2, #178 카드_개수_일치 사고와
# 같은 모양). per_key 표에는 그대로 찍고 전항목에서만 뺀다.
# 상권_분기_날조_없음은 넣지 않는다 — 인용했는데 값이 틀린 건 진짜 결함이다.
# 키가 태어나는 곳에 둔다(원래 devtools/bench.py 에 있었다) — 등록을 잊었는지는
# tests/test_bench.py 가 grade_insight 결과와 대조해 잡는다.
MEASURE_ONLY = {"salesSummary_선정률", "hourlySales_선정률", "상권_분기_인용됨"}


def grade_insight(raw: str, metrics: dict) -> dict:
    """매출 인사이트를 app/prompts/insight.py(2026-09-23) 기준으로 채점한다."""
    result: dict = {"parsed": False}
    try:
        insights = json.loads(strip_fence(raw))["insights"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    body = " ".join(insights)
    result["parsed"] = True
    result["개수_1_3"] = 1 <= len(insights) <= 3
    result["빈문장_없음"] = all(s.strip() for s in insights)
    result["100자_이내"] = all(len(s) <= 100 for s in insights)
    result["중복_없음"] = len(set(insights)) == len(insights)
    # "3주 연속 감소" 류 — 한 달치 스냅샷이라 연속성을 주장할 근거가 없다
    result["다주표현_없음"] = "연속" not in body
    # 관찰만 하고 처방하지 않는다. "~하세요"로 끝나면 처방이다.
    # 필요조건일 뿐이다 — "~하는 것이 좋습니다."는 "다."로 끝나지만 처방이다.
    result["관찰형_종결"] = all(s.rstrip().endswith("다.") for s in insights)
    result["금액_어림_없음"] = not _ROUNDED.search(body)
    result["수치_정확"] = not _ungrounded(body, metrics)
    result["요일_환각_없음"] = not _label_hallucination(body, metrics)

    # 비율 반올림 금지 — 0.042 는 4.2% 지 4% 가 아니다. 화면에서 티가 안 나 조용히 틀린다.
    ok = True
    changed = metrics["salesSummary"].get("vsPrevPeriod")
    if changed is not None:
        exact = f"{abs(changed) * 100:g}"
        rounded = f"{round(abs(changed) * 100):g}"
        if exact != rounded and f"{rounded}%" in body and f"{exact}%" not in body:
            ok = False
    result["비율_반올림_없음"] = ok

    # ratio 의 분모는 menuSales 다 — "전체의 OO%"·"총 매출의 OO%" 는 틀린 문장이다
    result["ratio_분모_정확"] = not re.search(r"(전체|총\s*매출)의\s*\d", body)

    result["상권_인과_주장_없음"] = not _DISTRICT_CAUSAL.search(body)
    result["salesSummary_선정률"] = _axis_selected(body, metrics, "salesSummary")
    result["hourlySales_선정률"] = _axis_selected(body, metrics, "hourlySales")
    result["상권_평균매출_반영"] = _district_avg_reflected(body, metrics)
    result["상권_피크밴드_반영"] = _district_band_reflected(body, metrics)
    grounded = _quarter_leak(body, metrics)
    result["상권_분기_인용됨"] = grounded is not None
    result["상권_분기_날조_없음"] = grounded

    result["insights"] = insights
    return result
