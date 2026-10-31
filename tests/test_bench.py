"""측정 스크립트의 집계가 틀리면 결론이 틀어진다 — 분모 처리만 테스트로 고정한다.

이 레포에서 이미 한 번 난 사고다: 채점기가 폐기된 규칙을 계속 재서 "Claude 가 규칙을
60% 어긴다"는 틀린 결론이 나왔다(devtools/grade.py 머리말). 호출·채점은 실호출로만
검증되지만, 분모를 어떻게 세는지는 코드로 막을 수 있다.
"""

import json

from devtools import grade
from devtools.bench import MEASURE_ONLY, _checks, _rates


def _row(status: int, model: dict, service: dict) -> dict:
    return {"status": status, "seconds": 1.0, "attempts": 1, "model": model, "service": service}


def test_응답이_없는_요청도_분모에_남는다():
    """500 은 검사 결과가 비어 있다. 있는 항목만 평균하면 통계에서 사라져 숫자가 좋아진다."""
    rows = [
        _row(
            200,
            {"parsed": True, "카드_개수_적정": True},
            {"parsed": True, "카드_개수_적정": True},
        ),
        _row(500, {"parsed": False}, {}),
    ]
    keys, per_key, all_model, all_service = _rates(rows)

    assert keys == ["parsed", "카드_개수_적정"]
    assert per_key["카드_개수_적정"] == (0.5, 0.5), "500 을 빼고 세면 100% 가 된다"
    assert all_service == 0.5


def test_재시도가_살린_항목은_두_열이_갈라진다():
    """1회차에서 어림 금액으로 거부됐다가 재시도로 통과한 경우다(#126).

    모델 열이 코랩에서 재던 값이고 서비스 열이 점주가 보는 값이다. 둘을 같이 봐야
    재시도가 실제로 사 주는 양이 보인다.
    """
    rows = [
        _row(
            200,
            {"parsed": True, "금액_어림_없음": False},
            {"parsed": True, "금액_어림_없음": True},
        )
    ]
    _, per_key, all_model, all_service = _rates(rows)

    assert per_key["금액_어림_없음"] == (0.0, 1.0)
    assert (all_model, all_service) == (0.0, 1.0)


def test_채점_결과에서_카드_본문은_항목으로_세지_않는다():
    """grade_solution 은 검사 결과에 cards 를, grade_insight 는 insights 를 같이 담아 준다.

    그걸 항목으로 세면 비어 있지 않은 리스트가 늘 True 라 통과율이 부풀려진다.
    """
    graded = {
        "parsed": True,
        "카드_개수_적정": True,
        "cards": [{"rankNo": 1}],
        "insights": ["문장"],
    }

    assert _checks(graded) == {"parsed": True, "카드_개수_적정": True}


def test_파싱_실패는_error_를_항목으로_세지_않는다():
    assert _checks({"parsed": False, "error": "JSONDecodeError: ..."}) == {"parsed": False}


def test_인사이트_케이스가_모든_근거_축을_덮는다():
    """솔루션과 같은 구멍이 인사이트에도 있었다 — districtBenchmark(#161) 후보 0/2.

    상권이 인사이트 측정에 한 번도 포함되지 않아서, "상권이 경쟁에서 밀린다" 를
    벤치로 확인할 수 없었다(2026-10-21).
    """
    from app.schemas.common import InsightMetrics
    from devtools.bench import INSIGHT_CASES

    axes = set(InsightMetrics.model_fields)
    covered = {key for _, metrics in INSIGHT_CASES for key, value in metrics.items() if value}

    assert not (axes - covered), f"케이스가 덮지 않는 지표: {sorted(axes - covered)}"


def test_솔루션_케이스가_모든_근거_축을_덮는다():
    """축을 추가하고 케이스를 안 고치면 그 축은 영원히 측정되지 않는다.

    2026-10-21 에 실제로 그 상태였다 — weatherContext(#155)·menuRankings(#181)·
    businessHours(#183) 가 케이스 셋 어디에도 없어서 0~6 차 측정이 전부 축 3 개짜리
    입력으로 돌았다. "솔루션에 날씨가 안 나온다" 를 벤치로 잡을 수 없었던 이유다 —
    입력에 없으면 카드도 안 나오니 통과율은 멀쩡해 보인다.

    Metrics 에 축을 더하면 이 테스트가 깨진다. 그때 케이스를 같이 추가한다.
    """
    from app.schemas.common import Metrics
    from devtools.bench import SOLUTION_CASES

    # 카드 생성에 실제로 쓰이는 지표만 센다.
    #   reviewSummary      — v3 범위, 아직 안 쓴다
    #   conditionPatterns  — 받기만 하고 프롬프트·점수식에 연결 전이다(#194). 연결하면
    #                        tests/test_condition_patterns.py 의 "아직 연결되지 않았다"
    #                        테스트가 먼저 깨진다 — 그때 여기 제외 목록에서도 뺀다.
    #   districtBenchmark  — 같은 이유다(#149). BE 가 2026-10-29(PR #637)부터 보내지만
    #                        _category_rows 처럼 focus 에 실어 주는 자리가 아직 없다.
    axes = set(Metrics.model_fields) - {"reviewSummary", "conditionPatterns", "districtBenchmark"}
    covered = {key for _, metrics in SOLUTION_CASES for key, value in metrics.items() if value}

    assert not (axes - covered), f"케이스가 덮지 않는 지표: {sorted(axes - covered)}"


def test_조건부_항목의_None은_분모에서_빠진다():
    """선정 안 된 조건부 항목(None)을 결함으로 세면 실제보다 낮게 보인다(#209, 헥터)."""
    rows = [
        _row(
            200,
            {"parsed": True, "상권_평균매출_반영": None},
            {"parsed": True, "상권_평균매출_반영": None},
        ),
        _row(
            200,
            {"parsed": True, "상권_평균매출_반영": True},
            {"parsed": True, "상권_평균매출_반영": False},
        ),
    ]
    _, per_key, all_model, all_service = _rates(rows)

    assert per_key["상권_평균매출_반영"] == (1.0, 0.0), "None 인 행은 분모에서 빠져야 한다"
    assert all_model == 1.0, "None 은 결함이 아니라 전항목 집계에서 통과로 센다"
    assert all_service == 0.5, "False 는 여전히 결함이다 — None 과 다르게 센다"


def test_선정률은_전항목_집계에서_빠진다():
    """선정률(salesSummary_선정률·hourlySales_선정률)은 규칙 위반이 아니라 "이번
    요청에서 그 축이 선정됐는지" 를 재는 측정값이다 — 3 문장 안에 6 축이 다
    선정되지 않는 게 정상이라 False 가 흔하다. 그대로 전항목(출하 판정)에 넣으면
    상시 0% 가 된다(#209 리뷰 Important #2, #178 카드_개수_일치 사고와 같은 모양).
    per_key 표에는 그대로 찍되 전항목 집계에서만 뺀다."""
    rows = [
        _row(
            200,
            {"parsed": True, "hourlySales_선정률": False, "상권_평균매출_반영": None},
            {"parsed": True, "hourlySales_선정률": False, "상권_평균매출_반영": None},
        ),
    ]
    _, per_key, all_model, all_service = _rates(rows)

    assert per_key["hourlySales_선정률"] == (0.0, 0.0), "표에는 선정률 그대로 찍는다"
    assert (all_model, all_service) == (1.0, 1.0), "선정률은 전항목 집계에서 뺀다"


def test_checks가_None을_bool로_뭉개지_않는다():
    """브리프 산출물 — bool(None) 으로 뭉개면 _rates 의 None 처리가 전부 무력화된다
    (#209 리뷰 Important #4). _row() 로 dict 를 직접 만드는 다른 테스트들은 _checks
    를 우회하므로, 이 동작만 따로 고정해 둔다."""
    assert _checks({"parsed": True, "상권_평균매출_반영": None}) == {
        "parsed": True,
        "상권_평균매출_반영": None,
    }


def test_선정률_측정값이_전부_MEASURE_ONLY에_등록돼_있다():
    """grade_insight 가 실제로 내는 선정률 키와 대조한다 — 리터럴끼리 비교하면
    새 선정률 키를 등록하지 않아도 통과해서 Important #2 가 조용히 무력화된다
    (#209 최종 리뷰 Important #2). 뒤쪽 단언은 반대 방향 — 진짜 결함 항목을
    MEASURE_ONLY 에 넣으면 전항목(출하 판정)이 조용히 느슨해진다."""
    from devtools.contract_check import EXAMPLES

    metrics = EXAMPLES["sales-insights"]["metrics"]
    body = json.dumps({"insights": ["총 매출은 전기 대비 4.2% 증가했습니다."]}, ensure_ascii=False)
    result = grade.grade_insight(body, metrics)

    rates = {k for k in result if k.endswith("선정률")}

    assert rates, "선정률 키가 하나도 없다 — 대조가 무의미하다"
    assert rates <= MEASURE_ONLY
    assert MEASURE_ONLY == {"salesSummary_선정률", "hourlySales_선정률", "상권_분기_인용됨"}
