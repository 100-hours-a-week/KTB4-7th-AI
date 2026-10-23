"""devtools/grade.py 가 프롬프트 규칙을 그대로 검사하는지 본다.

가장 중요한 건 맨 위 두 테스트다. 채점기는 프롬프트를 코드로 옮긴 것이라 프롬프트가
바뀌면 조용히 썩는다 — 2026-10-01(PR #115) 재설계 때 실제로 그랬다. 폐기된 규칙
(`수치는 evidence 에만`, `detailText 두 문장`)을 계속 재면서 "Claude 가 규칙을 60%
어긴다"는 틀린 결론을 냈다. 버전이 어긋나면 여기서 먼저 실패하게 둔다.
"""

import json

import pytest

from app.clients import llm
from app.prompts import insight as insight_prompt
from app.prompts import solution as solution_prompt
from app.services import insight_focus
from devtools import grade
from devtools.contract_check import EXAMPLES

SOL_METRICS = EXAMPLES["solutions"]["metrics"]
INS_METRICS = EXAMPLES["sales-insights"]["metrics"]


def test_솔루션_프롬프트가_바뀌면_채점기를_다시_보게_한다():
    assert solution_prompt.VERSION == grade.TARGET_SOLUTION_VERSION, (
        "프롬프트가 바뀌었다. devtools/grade.py 규칙을 다시 읽고 TARGET_SOLUTION_VERSION 을 올려라."
    )


def test_인사이트_프롬프트가_바뀌면_채점기를_다시_보게_한다():
    assert insight_prompt.VERSION == grade.TARGET_INSIGHT_VERSION, (
        "프롬프트가 바뀌었다. devtools/grade.py 규칙을 다시 읽고 TARGET_INSIGHT_VERSION 을 올려라."
    )


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        '{"a": 1}',
        "  설명이 붙은 경우  ",
    ],
)
def test_채점기의_펜스_제거가_서비스와_같다(raw):
    """app 의존을 떼려고 복사해 둔 함수다 — 어긋나면 채점 결과가 서비스와 달라진다."""
    assert grade.strip_fence(raw) == llm.strip_fence(raw)


def _card(rank=1, title="평일 비피크 프로모션 도입", summary="", detail="", evidence=""):
    return {
        "rankNo": rank,
        "title": title,
        "summaryText": summary or "평일 14시 매출이 30,000원으로 하루 중 가장 낮습니다.",
        "detail": None,
        "detailText": detail
        or "14시까지 할인 안내를 띄우세요.\n홀 담당을 늘리세요.\n방문을 늘릴 수 있습니다.",
        "evidence": evidence or "평일 14시 매출이 30,000원입니다.",
    }


def _raw(*cards) -> str:
    cleaned = [{k: v for k, v in c.items() if k != "detail"} for c in cards]
    return json.dumps({"solutionCards": cleaned}, ensure_ascii=False)


def _graded(*cards) -> dict:
    return grade.grade_solution(_raw(*cards), SOL_METRICS)


def _three_cards(**overrides) -> dict:
    """서로 다른 지표를 근거로 한 정상 카드 3장. overrides 로 1번 카드만 비튼다."""
    first = _card(1, **overrides)
    second = _card(
        2,
        title="커피 라인업 보강",
        summary="커피 비중이 62%로 가장 큽니다.",
        detail="신메뉴를 추가하세요.\n시식을 운영하세요.\n재방문을 늘릴 수 있습니다.",
        evidence="커피 매출 비중은 62%입니다.",
    )
    third = _card(
        3,
        title="오늘 예상 매출에 맞춘 준비",
        summary="오늘 예상 매출은 1,250,000원입니다.",
        detail="재료를 그에 맞춰 발주하세요.\n마감 인력을 늘리세요.\n품절을 줄일 수 있습니다.",
        evidence="오늘 예상 매출은 1,250,000원입니다.",
    )
    return _graded(first, second, third)


def test_정상_카드는_모든_항목을_통과한다():
    result = _three_cards()

    failed = [k for k, v in result.items() if isinstance(v, bool) and not v]
    assert failed == [], f"오탐: {failed}"


# ── 2026-10-01 재설계로 새로 생긴 규칙들 ──────────────────────────────


def test_summaryText_수치를_detailText가_다시_쓰면_걸린다():
    """evidence 는 화면에 안 보이니 예외지만, 보이는 세 필드끼리는 겹치면 안 된다."""
    result = _three_cards(
        detail="14시 매출 30,000원을 올리세요.\n직원을 배치하세요.\n늘릴 수 있습니다."
    )

    assert result["수치_필드간_중복없음"] is False


def test_evidence가_summaryText_수치를_반복해도_통과한다():
    """2026-10-02 FE 확정 — evidence 는 솔루션 카드에서 숨긴다."""
    result = _three_cards(evidence="평일 14시 매출이 30,000원으로 가장 낮습니다.")

    assert result["수치_필드간_중복없음"] is True


def test_지표에_없는_수는_실행_지시라_중복으로_보지_않는다():
    """프롬프트가 "21시까지"·"10% 할인"을 명시적으로 허용한다."""
    result = _three_cards(
        summary="평일 14시 매출이 30,000원으로 가장 낮아 10% 할인이 필요합니다.",
        detail="10% 할인을 겁니다.\n21시까지 운영하세요.\n방문을 늘릴 수 있습니다.",
    )

    assert result["수치_필드간_중복없음"] is True


def test_detailText가_세_문장이_아니면_걸린다():
    """실행 2문장 + 기대효과 1문장 — 2026-10-01 재설계. 이전 판은 두 문장이었다."""
    result = _three_cards(detail="할인 안내를 띄우세요.\n방문을 늘릴 수 있습니다.")

    assert result["detail_3문장"] is False


def test_12시간제로_바꿔_쓰면_걸린다():
    result = _three_cards(detail="오후 2시에 안내를 띄우세요.\n직원을 배치하세요.\n늘립니다.")

    assert result["시각_24시간제"] is False


@pytest.mark.parametrize("phrase", ["주말이 평일의 3배입니다", "평일은 주말의 3분의 1입니다"])
def test_배율을_직접_계산하면_걸린다(phrase):
    """실호출에서 "7배"·"3분의 1" 날조가 나왔다 — 지표에 없는 값이다."""
    result = _three_cards(summary=phrase)

    assert result["배율_없음"] is False


def test_기대효과에_수치를_지어내면_걸린다():
    """마지막 문장은 "~를 늘릴 수 있습니다"처럼 정성적으로만 쓰게 돼 있다."""
    result = _three_cards(detail="할인하세요.\n배치하세요.\n매출이 15% 증가합니다.")

    assert result["기대효과_정성적"] is False


@pytest.mark.parametrize(
    "sentence",
    [
        "21시까지 10% 할인을 진행하세요.",
        "직원 1명 이상을 배치하세요.",
        "인력을 2명 더 배치하세요.",
        "원두 5kg 을 발주하세요.",
    ],
)
def test_행동의_얼마나를_지어내면_걸린다(sentence):
    """마진을 모르는데 할인율을, 인건비 대비 생산성을 모르는데 인원을 말할 근거가 없다.

    추상적이면 점주가 안 쓰고 말지만, 구체적이고 틀리면 돈을 잃는다.
    """
    result = _three_cards(detail=f"{sentence}\n직원을 배치하세요.\n늘릴 수 있습니다.")

    assert result["실행수치_날조_없음"] is False


@pytest.mark.parametrize(
    "sentence",
    [
        "14시까지 운영 시간을 늘리세요.",  # 시각은 지표에 있다
        "방문을 유도하는 할인을 거세요.",  # 방향만 말한다
        "원두 발주를 평소보다 줄이세요.",
    ],
)
def test_방향만_말하면_통과한다(sentence):
    result = _three_cards(detail=f"{sentence}\n안내를 띄우세요.\n늘릴 수 있습니다.")

    assert result["실행수치_날조_없음"] is True


@pytest.mark.parametrize(
    "sentence",
    [
        "마케팅을 강화하세요.",
        "프로모션을 진행하세요.",
        "홍보 활동을 확대하세요.",
        "전략을 변경하세요.",
    ],
)
def test_누구나_할_수_있는_말이면_걸린다(sentence):
    """점주가 오늘 무엇을 다르게 할지가 안 나오는 문장이다."""
    result = _three_cards(detail=f"{sentence}\n안내를 띄우세요.\n늘릴 수 있습니다.")

    assert result["공허한_조언_없음"] is False


def test_기대효과_문장은_공허_검사에서_빼준다():
    """마지막 문장은 "매출을 늘릴 수 있습니다" 가 허용이라 같은 잣대로 보면 오탐이다."""
    result = _three_cards(
        detail="14시까지 안내를 띄우세요.\n직원을 배치하세요.\n매출을 늘릴 수 있습니다."
    )

    assert result["공허한_조언_없음"] is True
    assert result["실행수치_날조_없음"] is True


# ── 이전 판에서 이어지는 규칙들 ───────────────────────────────────────


def test_지표에_없는_요일을_쓰면_걸린다():
    """dayType=WEEKDAY 를 "금요일"로 바꿔 쓴 출력이 실제로 나왔다. 숫자는 맞아서 통과한다."""
    result = _three_cards(summary="금요일 14시 매출이 30,000원으로 가장 낮습니다.")

    assert result["요일_환각_없음"] is False


def test_카드_둘이_같은_지표를_근거로_쓰면_걸린다():
    """문장이 달라도 중복이다 — 문자 유사도로는 안 잡힌다(실측 0.13)."""
    same = _card(
        2,
        title="주말 피크 대비",
        summary="주말 14시 매출이 92,000원입니다.",
        evidence="주말 14시 매출은 92,000원입니다.",
    )
    result = _graded(_card(1), same, _card(3, title="세 번째", evidence="커피 비중은 62%입니다."))

    assert result["카드_지표_중복없음"] is False


def test_금액을_어림하면_걸린다():
    result = _three_cards(summary="평일 14시 매출이 3만원으로 가장 낮습니다.")

    assert result["금액_어림_없음"] is False


def test_evidence에_지표에_없는_수치를_쓰면_걸린다():
    result = _three_cards(evidence="평일 14시 매출이 300,000원입니다.")

    assert result["evidence_수치_정확"] is False


def test_파싱에_실패하면_이유를_남긴다():
    result = grade.grade_solution("설명: 카드를 만들었습니다", SOL_METRICS)

    assert result["parsed"] is False
    assert "error" in result


# ── 인사이트 ─────────────────────────────────────────────────────────


def _insight(*sentences) -> dict:
    return grade.grade_insight(
        json.dumps({"insights": list(sentences)}, ensure_ascii=False), INS_METRICS
    )


def test_정상_인사이트는_모든_항목을_통과한다():
    # 2026-10-21(#209 리뷰): salesSummary_선정률·hourlySales_선정률 은 규칙 위반이
    # 아니라 "그 축이 선정됐는지" 를 재는 측정값이다 — 3 문장 안에 6 축이 다
    # 선정되지 않는 게 정상이라(여기선 categorySales·menuRankings·salesSummary
    # 세 축만 쓴다) False 가 흔하다. 처음엔 둘째 문장을 hourlySales 전용으로
    # 바꿔 픽스처를 측정값에 맞춰 비틀었는데, 그러면 측정용 bool 이 하나 더
    # 생길 때마다 "정상 예시"를 또 비틀어야 한다 — 뿌리는 필터였다. 그래서
    # 둘째 문장은 원래대로 두고, 필터에서 grade.MEASURE_ONLY(전항목 집계에서도
    # 빼는 키 집합)를 그대로 재사용해 측정 전용 키를 뺀다.
    result = _insight(
        "커피 카테고리 매출이 메뉴 매출의 41.7%를 차지하고 있습니다.",
        "아메리카노가 메뉴 매출의 28.2%를 차지합니다.",
        "총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 낮습니다.",
    )

    failed = [
        k
        for k, v in result.items()
        if isinstance(v, bool) and not v and k not in grade.MEASURE_ONLY
    ]
    assert failed == [], f"오탐: {failed}"


def test_비율을_반올림하면_걸린다():
    """0.042 는 4.2% 지 4% 가 아니다. 화면에서 티가 안 나 조용히 틀린다."""
    result = _insight("총 매출은 전기 대비 4% 증가했습니다.")

    assert result["비율_반올림_없음"] is False


def test_다른_수치의_백분율이_반올림값과_부분일치해도_안_걸린다():
    """0.018 은 반올림하면 "2%" 다. 본문에 무관한 수치 "1.2%" 가 있으면, "1.2%" 의 끝
    두 글자가 생문자열로 "2%" 와 겹쳐 반올림 위반으로 오판했다(2026-10-22 실측에서
    실제로 재현 — 카테고리 증감률 1.2% 를 쓴 문장이 salesSummary 반올림 위반으로
    잘못 걸렸다). 백분율을 숫자 토큰 단위로 끊어서 대조해야 한다."""
    metrics = {
        **INS_METRICS,
        "salesSummary": {**INS_METRICS["salesSummary"], "vsPrevPeriod": 0.018},
    }
    result = grade.grade_insight(
        json.dumps({"insights": ["커피 매출은 전기 대비 1.2% 증가했습니다."]}, ensure_ascii=False),
        metrics,
    )

    assert result["비율_반올림_없음"] is True


def test_ratio_분모를_총매출로_말하면_걸린다():
    """ratio 의 분모는 menuSales 다. 총매출 기준이면 39.4% 라 틀린 문장이 된다."""
    result = _insight("커피가 전체의 41.7%를 차지합니다.")

    assert result["ratio_분모_정확"] is False


def test_인사이트도_요일_환각을_잡는다():
    result = _insight("금요일 12시 메뉴 매출이 420,000원으로 높습니다.")

    assert result["요일_환각_없음"] is False


def test_요일이_세글자_약어로_와도_환각으로_안_걸린다():
    """weekdaySales[].dayOfWeek 가 "SATURDAY" 대신 "SAT" 같은 세글자 약어로 올 수
    있다(app/services/solution.py::_WEEKDAY_CODES 와 같은 표기, devtools/bench.py
    인사이트 케이스가 이 표기를 쓴다). _DOW_KO 가 영문 전체 이름만 키로 가지고
    있으면 "SAT" 가 안 매칭돼 허용 목록이 비고, AI 가 데이터에 있는 그대로
    "토요일"이라고 정확히 써도 환각으로 오판한다(2026-10-22 실측에서 실제로
    재현 — PR #219)."""
    metrics = {
        **INS_METRICS,
        "weekdaySales": [{"dayOfWeek": "SAT", "menuSales": 1560000, "orderCount": 182}],
    }
    result = grade.grade_insight(
        json.dumps(
            {"insights": ["토요일 매출이 1,560,000원으로 가장 높습니다."]}, ensure_ascii=False
        ),
        metrics,
    )

    assert result["요일_환각_없음"] is True


def test_처방형으로_끝나면_걸린다():
    """인사이트는 관찰만 한다 — "~하세요"는 솔루션 카드의 몫이다."""
    result = _insight("커피 비중이 높으니 신메뉴를 추가하세요.")

    assert result["관찰형_종결"] is False


def test_카드_개수는_배정된_장수로_채점한다():
    """2026-10-07(#123) 부터 배정 지표가 3 종이 안 되면 서비스가 그만큼만 내보낸다.

    3 으로 박아두면 설계대로 2 장을 낸 응답을 결함으로 센다 — 2026-10-08 실측에서
    `카드3장` 66.7% 가 전부 그거였고, 모델 품질로 오해할 숫자였다.
    """
    import json

    from devtools.grade import grade_solution

    metrics = {"salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12}}
    two = json.dumps(
        {
            "solutionCards": [
                {
                    "rankNo": index,
                    "title": "가",
                    "summaryText": "가",
                    "detailText": "가\n가\n가",
                    "evidence": "가",
                }
                for index in (1, 2)
            ]
        },
        ensure_ascii=False,
    )

    assert grade_solution(two, metrics, expected_cards=2)["카드_개수_적정"] is True
    assert grade_solution(two, metrics)["카드_개수_적정"] is True, "2 장은 1~3 안이라 정상이다"


_DISTRICT_METRICS = {
    "salesSummary": {
        "totalSales": 7920000,
        "menuSales": 7480000,
        "orderCount": 923,
        "averageOrderValue": 8581,
        "vsPrevPeriod": 0.042,
    },
    "hourlySales": [
        {"dayType": "WEEKDAY", "hour": 14, "menuSales": 500000, "orderCount": 60},
    ],
    "districtBenchmark": {
        "basisQuarter": "2026Q3",
        "districtAvgMonthlySalesPerCafe": 9413000,
        "cafeStoreCount": 133,
        "peakSalesHourBand": "14-17",
        "peakFootTrafficHourBand": "11-14",
    },
}


def _district_insight(*sentences: str, metrics: dict = _DISTRICT_METRICS) -> dict:
    return grade.grade_insight(json.dumps({"insights": list(sentences)}), metrics)


def test_채점기의_상권_게이트가_서비스와_같다():
    """app 을 import 하지 않으려고 복사해 둔 함수다 — 어긋나면 채점 결과가 서비스와
    달라진다(devtools/grade.py::_district_gate 참고)."""
    cases = [
        None,
        {},
        {"cafeStoreCount": 2, "districtAvgMonthlySalesPerCafe": 9413000},
        # 임계값(_MIN_CAFE_STORE_COUNT) 자체 — app 쪽 임계값이 3→4 로 바뀌어도
        # 다른 케이스들은 전부 같은 답을 내서 드리프트를 못 잡는다(#209 리뷰
        # Important #3). 경계값을 넣어야 그 변화가 보인다.
        {"cafeStoreCount": 3, "districtAvgMonthlySalesPerCafe": 9413000},
        {"cafeStoreCount": 133, "districtAvgMonthlySalesPerCafe": 0},
        {"cafeStoreCount": 133, "districtAvgMonthlySalesPerCafe": 9413000},
    ]
    for district in cases:
        assert grade._district_gate(district) == insight_focus._district_gate(district)


def test_채점기의_밴드_포맷_게이트가_서비스와_같다():
    """app::_band_gate 와 같은 로직이어야 한다 — 어긋나면 한쪽은 밴드가 깨져도
    파싱을 시도해 죽고, 다른 쪽은 조용히 탈락시킨다(#209 최종 리뷰 Important
    #4)."""
    cases = [
        None,
        {},
        {"peakSalesHourBand": "14-17", "peakFootTrafficHourBand": "11-14"},
        {"peakSalesHourBand": "14시-17시", "peakFootTrafficHourBand": "11-14"},
        {"peakSalesHourBand": "14-17", "peakFootTrafficHourBand": ""},
        {"peakSalesHourBand": "14-17"},  # peakFootTrafficHourBand 자체가 없음
    ]
    for district in cases:
        assert grade._band_gate(district) == insight_focus._band_gate(district)


def test_채점기의_비교_방향이_서비스와_같다():
    cases = [(10_000_000, 9_413_000), (7_920_000, 9_413_000), (9_413_000, 9_413_000)]
    for total_sales, district_avg in cases:
        assert grade._comparison(total_sales, district_avg) == insight_focus.district_comparison(
            total_sales, district_avg
        )


def test_채점기의_매장_피크_시간이_서비스와_같다():
    """app 을 import 하지 않으려고 복사해 둔 함수다(devtools/grade.py::_store_peak_hour
    참고) — parity 테스트가 없으면 어긋나도 아무도 못 잡는다(#209 리뷰 Important #3).

    2026-10-22(#209 최종 리뷰 Important #5): dayType 별로 따로 계산하도록 바뀌어
    day_type 인자가 추가됐다 — 평일·주말이 섞인 케이스를 넣어 섞이지 않는지도 본다.
    """
    cases: list[tuple[list[dict], str]] = [
        ([], "WEEKDAY"),
        ([{"dayType": "WEEKDAY", "hour": 9, "menuSales": 0, "orderCount": 0}], "WEEKDAY"),
        (
            [
                {"dayType": "WEEKDAY", "hour": 9, "menuSales": 100, "orderCount": 10},
                {"dayType": "WEEKDAY", "hour": 14, "menuSales": 100, "orderCount": 20},
            ],
            "WEEKDAY",
        ),
        (
            [
                {"dayType": "WEEKDAY", "hour": 9, "menuSales": 50, "orderCount": 5},
                {"dayType": "WEEKEND", "hour": 14, "menuSales": 200, "orderCount": 30},
                {"dayType": "WEEKEND", "hour": 20, "menuSales": 10, "orderCount": 2},
            ],
            "WEEKEND",
        ),
    ]
    for points, day_type in cases:
        assert grade._store_peak_hour(points, day_type) == insight_focus._store_peak_hour(
            points, day_type
        )


def test_채점기의_밴드_경계가_서비스와_같다():
    """`_in_band`(`start <= hour < end`) 의 `<` vs `<=` 경계 하나가 SAME/DIFFERENT 를
    바로 뒤집는다 — 경계값(start·end)을 꼭 넣어 대조한다(#209 리뷰 Important #3)."""
    cases = [(14, "14-17"), (17, "14-17"), (13, "14-17"), (16, "14-17")]
    for hour, band in cases:
        assert grade._in_band(hour, band) == insight_focus._in_band(hour, band)


def test_채점기의_밴드_포함_여부가_서비스와_같다():
    """app::_band_included 와 같은 로직이어야 한다 — 어긋나면 한쪽은 밴드를
    줬는데 다른 쪽은 "안 언급했다"고 결함으로 오판한다."""
    cases: list[tuple[list[dict], str]] = [
        ([{"dayType": "WEEKDAY", "hour": 14, "menuSales": 500000, "orderCount": 60}], "14-17"),
        ([{"dayType": "WEEKDAY", "hour": 11, "menuSales": 500000, "orderCount": 60}], "14-17"),
        (
            [
                {"dayType": "WEEKDAY", "hour": 11, "menuSales": 500000, "orderCount": 60},
                {"dayType": "WEEKEND", "hour": 15, "menuSales": 900000, "orderCount": 90},
            ],
            "14-17",
        ),
        ([{"dayType": "WEEKDAY", "hour": 3, "menuSales": 0, "orderCount": 0}], "14-17"),
    ]
    for points, band in cases:
        assert grade._band_expected(points, band) == insight_focus._band_included(points, band)


def test_매출요약이_선정되면_선정률이_참이다():
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했습니다.")

    assert result["salesSummary_선정률"] is True


def test_매출요약이_선정_안_되면_선정률이_거짓이다():
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["salesSummary_선정률"] is False


def test_다른_축과_값이_겹치는_숫자로는_숙주가_선정됐다고_보지_않는다():
    """#209 최종 리뷰 Important #3 재현 — salesSummary.orderCount(923)와
    menuRankings[].quantity(923)가 같은 값이다. menuRankings 얘기만 하는 문장으로
    salesSummary 가 선정된 것처럼 오판하면, None 이어야 할 상권_평균매출_반영이
    거짓 결함(False)으로 집계된다 — 출하 판정 롤업에 들어가는 항목이다."""
    metrics = {
        **_DISTRICT_METRICS,
        "menuRankings": [
            {"menuName": "아메리카노", "quantity": 923, "menuSales": 2_000_000, "ratio": 0.282}
        ],
    }
    result = _district_insight("아메리카노가 923잔 팔렸습니다.", metrics=metrics)

    assert result["salesSummary_선정률"] is False
    assert result["상권_평균매출_반영"] is None


def test_매출요약이_선정되고_상권_평균을_방향까지_맞게_인용하면_반영으로_통과한다():
    """totalSales(792만)가 districtAvgMonthlySalesPerCafe(941.3만)보다 작으므로
    BELOW다 — "낮습니다"가 맞는 방향이다."""
    result = _district_insight(
        "총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 낮습니다."
    )

    assert result["상권_평균매출_반영"] is True


def test_상권_평균_수치는_맞는데_방향이_반대면_걸린다():
    """숫자는 지표에 있는 값이라 UNGROUNDED_NUMBER 로는 못 잡는 오류다(설계 'C')."""
    result = _district_insight(
        "총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 높습니다."
    )

    assert result["상권_평균매출_반영"] is False


def test_상권_평균_방향_판정은_무관한_문장의_반대_어휘에_오염되지_않는다():
    """#209 리뷰 Important #1 재현 — totalSales(1200만) > districtAvg(941.3만)로
    ABOVE 다. 둘째 문장(weekdaySales 관찰)의 "낮습니다"는 상권과 무관한데, 본문
    전체를 보면 그 "낮"(BELOW 어휘)이 ABOVE 판정을 반대로 오염시킨다 — anchor(상권
    평균 숫자)가 든 절만 보게 고쳐서 더 이상 오염되지 않는다."""
    metrics = {
        **_DISTRICT_METRICS,
        "salesSummary": {**_DISTRICT_METRICS["salesSummary"], "totalSales": 12_000_000},
    }
    result = _district_insight(
        "총 매출은 12,000,000원으로 상권 평균 9,413,000원보다 높습니다.",
        "토요일 메뉴 매출이 310,000원으로 요일 중 가장 낮습니다.",
        metrics=metrics,
    )

    assert result["상권_평균매출_반영"] is True


def test_상권_평균_방향_판정은_절_단위로도_실제_반전은_여전히_잡는다():
    """절 단위로 좁혀도 anchor 가 든 절 안에서 방향이 실제로 반대면 여전히 걸려야
    한다 — 절 분할이 너무 좁아져 방향 반전을 놓치면 측정값이 실제보다 높게 보인다
    (#209 리뷰 Important #1, 양방향 테스트 요구)."""
    metrics = {
        **_DISTRICT_METRICS,
        "salesSummary": {**_DISTRICT_METRICS["salesSummary"], "totalSales": 12_000_000},
    }
    result = _district_insight(
        "총 매출은 12,000,000원으로 상권 평균 9,413,000원보다 낮습니다.",
        "토요일 메뉴 매출이 310,000원으로 요일 중 가장 높습니다.",
        metrics=metrics,
    )

    assert result["상권_평균매출_반영"] is False


def test_매출요약이_선정됐는데_상권_평균이_안_보이면_걸린다():
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했습니다.")

    assert result["상권_평균매출_반영"] is False


def test_매출요약이_선정_안_되면_상권_평균매출_반영은_측정_대상이_아니다():
    """숙주가 안 뽑힌 건 결함이 아니다 — None 이어야 분모에서 빠진다(설계 리뷰)."""
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["상권_평균매출_반영"] is None


def test_두_밴드_모두_정확히_인용하면_반영으로_통과한다():
    """우리 매장 피크(14시)는 peakSalesHourBand(14-17) 안(SAME), peakFootTrafficHourBand
    (11-14) 밖(DIFFERENT)이다. 한 문장에 두 비교를 같이 담는다 — hourlySales candidate가
    둘을 같은 문장에 묶어 넘기기 때문이다(재검토로 "둘 다 요구"로 되돌림, 2026-10-21(6))."""
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지만, "
        "오전 11시부터 오후 2시까지인 상권 유동인구 피크와는 다른 시간대입니다."
    )

    assert result["상권_피크밴드_반영"] is True


def test_한쪽_밴드만_설명하면_걸린다():
    """매출 피크만 설명하고 유동인구 피크를 빠뜨렸다 — 번들로 받은 정보 중 일부를
    누락한 진짜 결함이다. "문장마다 근거 하나" 원칙은 축 사이의 얘기라 여기엔
    안 걸린다(같은 hourlySales 축 안의 번들)."""
    result = _district_insight("오후 2시(14시)부터 17시까지 매출이 가장 높습니다.")

    assert result["상권_피크밴드_반영"] is False


def test_둘_다_설명해도_한쪽_방향이_틀리면_걸린다():
    """실제로는 매출 피크(SAME)·유동인구 피크(DIFFERENT)인데 문장은 반대로 말했다."""
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지 않고, "
        "오전 11시부터 오후 2시까지인 상권 유동인구 피크와 일치합니다."
    )

    assert result["상권_피크밴드_반영"] is False


def test_평일_주말_피크가_같은_방향이면_방향_반전을_여전히_잡는다():
    """평일(14시)·주말(16시) 둘 다 매출 밴드(14-17) 안(SAME)이라 방향이 하나로
    모인다(#209 최종 리뷰 Important #5) — 이때는 기존처럼 반전을 잡아야 한다."""
    metrics = {
        **_DISTRICT_METRICS,
        "hourlySales": [
            {"dayType": "WEEKDAY", "hour": 14, "menuSales": 500000, "orderCount": 60},
            {"dayType": "WEEKEND", "hour": 16, "menuSales": 700000, "orderCount": 70},
        ],
    }
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지 않고, "
        "오전 11시부터 오후 2시까지인 상권 유동인구 피크와 일치합니다.",
        metrics=metrics,
    )

    assert result["상권_피크밴드_반영"] is False


def test_평일_주말_피크_방향이_다르면_본문만으로_못_갈라_판정을_보류한다():
    """평일 피크(11시)는 매출 밴드(14-17) 밖(DIFFERENT), 주말 피크(15시)는 안(SAME)
    이다 — 문장이 어느 dayType 을 말하는지 본문 텍스트만으로 구분할 근거가 없으니,
    어느 쪽 어휘를 써도 결함으로 몰지 않는다(#209 최종 리뷰 Important #5). 밴드
    인용 자체는 둘 다 돼 있으니 전체 판정은 True 로 통과한다."""
    metrics = {
        **_DISTRICT_METRICS,
        "hourlySales": [
            {"dayType": "WEEKDAY", "hour": 11, "menuSales": 500000, "orderCount": 60},
            {"dayType": "WEEKEND", "hour": 15, "menuSales": 900000, "orderCount": 90},
        ],
    }
    result = _district_insight(
        "매출이 가장 높은 시간대는 상권 매출 피크 14-17시와 겹치고, "
        "상권 유동인구 피크 11-14시와는 겹치지 않습니다.",
        metrics=metrics,
    )

    assert result["상권_피크밴드_반영"] is True


def test_밴드를_리터럴_형식으로_인용해도_공유_숫자에_오염되지_않는다():
    """peakSalesHourBand("14-17")의 시작과 peakFootTrafficHourBand("11-14")의
    끝이 같은 "14"다 — anchor로 밴드 시작 시각 하나만 쓰면 서로의 반대 어휘에
    오염된다(#209 최종 리뷰 Important #1). 매출 피크(SAME)·유동인구 피크
    (DIFFERENT) 둘 다 올바른 방향인데, "14-17" 리터럴 안의 "14"가 유동인구
    쪽 "겹치지 않습니다"(DIFFERENT 어휘)와 같은 절에 있어 옛 코드는 매출
    SAME 판정을 거짓으로 뒤집었다."""
    result = _district_insight(
        "매출 피크 14-17시와 겹칩니다. 유동인구 피크 11-14시와는 겹치지 않습니다."
    )

    assert result["상권_피크밴드_반영"] is True


def test_주문_수량_숫자가_밴드_anchor와_substring으로_오매칭되지_않는다():
    """주문 "114건"의 "11"이 유동인구 밴드("11-14") anchor "11"과 생문자열
    substring으로 오매칭되면, 메뉴 얘기만 하는 무관한 절이 반영 판정을 거짓으로
    뒤집는다(#209 최종 리뷰 deferred #4). 토큰 단위 대조(_numbers_in)로 고치면
    "114"는 "11"과 다른 숫자로 구분돼 오염되지 않는다."""
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지만, "
        "오전 11시부터 오후 2시까지인 상권 유동인구 피크와는 다른 시간대입니다. "
        "아메리카노가 114건 팔려 다른 음료와 매출이 같은 시간대에 겹칩니다."
    )

    assert result["상권_피크밴드_반영"] is True


def test_겹치는_시간대입니다_같은_어간형_반전도_잡는다():
    """프롬프트는 "겹침"/"안 겹침" 어간형으로 가르치는데(app/prompts/insight.py),
    옛 어휘 목록("겹칩니다"·"일치합니다")은 완전 활용형만 봐서 "겹치는
    시간대입니다" 같은 변형은 실제 방향과 반대로 써도 못 잡았다(#209 최종
    리뷰 deferred #6). 매출(SAME)은 올바르게, 유동인구(실제 DIFFERENT)는
    반전해서 "겹치는 시간대"라고 틀리게 썼다."""
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치는 "
        "시간대이고, 오전 11시부터 오후 2시까지인 상권 유동인구 피크와도 겹치는 "
        "시간대입니다."
    )

    assert result["상권_피크밴드_반영"] is False


def test_겹치지_않습니다_가_SAME_어간과_혼동되지_않는다():
    """ "겹치지 않습니다"(DIFFERENT 정답 문구)는 SAME 어간 "겹치"를 그대로
    포함한다 — 단순 substring 대조면 SAME 으로도 오매칭된다. "지 않"이
    뒤따르면 SAME 이 아니라고 정규식 음성 lookahead 로 미리 걸러낸다(#209
    최종 리뷰 deferred #6, 단순 어간화의 역효과). 매출은 실제 SAME 인데
    "겹치지 않습니다"로 반전해서 틀리게 썼으니 결함(False)이어야 한다."""
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지 "
        "않습니다. 오전 11시부터 오후 2시까지인 상권 유동인구 피크와는 겹치지 "
        "않습니다."
    )

    assert result["상권_피크밴드_반영"] is False


def test_두_밴드_모두_SAME이라_서비스가_안_줬으면_안_언급해도_결함이_아니다():
    """두 밴드 다 우리 매장 피크(14시)와 겹쳐(SAME) 서비스가 애초에 안 줬을
    상권이다 — 모델이 안 언급해도 결함(False)이 아니라 측정 대상 제외(None)다."""
    metrics = {
        **_DISTRICT_METRICS,
        "districtBenchmark": {
            **_DISTRICT_METRICS["districtBenchmark"],
            "peakFootTrafficHourBand": "13-16",  # 14시가 이 밴드에도 들어 SAME
        },
    }
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했습니다.", metrics=metrics)

    assert result["상권_피크밴드_반영"] is None


def test_한쪽_밴드만_DIFFERENT로_주어지면_그것만_언급해도_통과한다():
    """peakSalesHourBand(14-17)는 우리 매장 피크(14시)와 겹쳐(SAME) 서비스가 안
    줄 밴드고, peakFootTrafficHourBand(11-14)는 안 겹쳐(DIFFERENT) 줄 밴드다 —
    안 준 쪽은 언급 안 해도 되고, 준 쪽만 올바르게 언급하면 반영으로 통과해야 한다."""
    result = _district_insight(
        "오전 11시부터 오후 2시(14시)까지인 상권 유동인구 피크와는 다른 시간대에 매출이 가장 높습니다."
    )

    assert result["상권_피크밴드_반영"] is True


def test_시간대축이_선정_안_되면_상권_피크밴드_반영은_측정_대상이_아니다():
    """두 밴드 숫자 중 어느 것도 안 나왔으면 이번엔 hourlySales 가 선정 안 된 것으로
    본다 — 결함이 아니라 None 이어야 분모에서 빠진다."""
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["상권_피크밴드_반영"] is None


def test_밴드_포맷이_깨지면_상권_피크밴드_반영은_측정_대상이_아니고_안_죽는다():
    """BE 가 peakSalesHourBand 포맷을 바꾸면 _band_mentioned 의 tuple
    unpacking(band.split("-"))이 터질 수 있다 — 채점기가 --n 20 실측 도중
    죽지 않고 조용히 측정 대상 제외(None)로 처리해야 한다(#209 최종 리뷰
    Important #4)."""
    metrics = {
        **_DISTRICT_METRICS,
        "districtBenchmark": {**_DISTRICT_METRICS["districtBenchmark"], "peakSalesHourBand": "14"},
    }
    result = _district_insight(
        "오후 2시(14시)부터 17시까지 매출이 가장 높아 상권 매출 피크와 겹치지만, "
        "오전 11시부터 오후 2시까지인 상권 유동인구 피크와는 다른 시간대입니다.",
        metrics=metrics,
    )

    assert result["상권_피크밴드_반영"] is None


def test_우리_매장_피크를_계산할_수_없으면_밴드_인용만으로도_통과한다():
    """비교 필드(vsDistrictSalesPeakWeekday 등)가 없을 상황이다 — 평일·주말 둘 다
    영업 중인 행이 없으면(_store_peak_hour 가 둘 다 None) 방향을 요구하지 않고
    둘 다 인용됐는지만 본다(별도 검토, 2026-10-21(5))."""
    metrics = {
        **_DISTRICT_METRICS,
        "hourlySales": [{"dayType": "WEEKDAY", "hour": 3, "menuSales": 0, "orderCount": 0}],
    }

    assert grade._store_peak_hour(metrics["hourlySales"], "WEEKDAY") is None
    assert grade._store_peak_hour(metrics["hourlySales"], "WEEKEND") is None
    result = _district_insight(
        "상권의 매출은 14시부터 17시까지, 유동인구는 11시부터 14시까지가 피크입니다.",
        metrics=metrics,
    )

    assert result["상권_피크밴드_반영"] is True


def test_시간대축이_선정되면_hourlySales_선정률이_참이다():
    result = _district_insight("오후 2시(14시)부터 17시까지 매출이 가장 높습니다.")

    assert result["hourlySales_선정률"] is True


def test_시간대축이_선정_안_되면_hourlySales_선정률이_거짓이다():
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["hourlySales_선정률"] is False


def test_분기를_인용하지_않으면_인용됨이_거짓이고_날조는_측정_대상이_아니다():
    result = _insight("커피 카테고리 매출이 메뉴 매출의 41.7%를 차지하고 있습니다.")

    assert result["상권_분기_인용됨"] is False
    assert result["상권_분기_날조_없음"] is None


def test_실제_분기와_같은_값을_인용하면_날조가_아니다():
    """basisQuarter 는 focus 블록에 안 보내지만(#209), 지표 어딘가엔 여전히 있어
    접지 검사로는 못 잡는다 — 그래도 '날조'는 아니라는 걸 구분한다."""
    result = _insight("2026Q3 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is True


def test_실제_분기와_다른_값을_인용하면_날조다():
    result = _insight("2027Q1 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is False


def test_년_분기_표기도_잡는다():
    result = _insight("2026년 3분기 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is True
