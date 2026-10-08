"""측정 스크립트의 집계가 틀리면 결론이 틀어진다 — 분모 처리만 테스트로 고정한다.

이 레포에서 이미 한 번 난 사고다: 채점기가 폐기된 규칙을 계속 재서 "Claude 가 규칙을
60% 어긴다"는 틀린 결론이 나왔다(devtools/grade.py 머리말). 호출·채점은 실호출로만
검증되지만, 분모를 어떻게 세는지는 코드로 막을 수 있다.
"""

from devtools.bench import _checks, _rates


def _row(status: int, model: dict, service: dict) -> dict:
    return {"status": status, "seconds": 1.0, "attempts": 1, "model": model, "service": service}


def test_응답이_없는_요청도_분모에_남는다():
    """500 은 검사 결과가 비어 있다. 있는 항목만 평균하면 통계에서 사라져 숫자가 좋아진다."""
    rows = [
        _row(
            200,
            {"parsed": True, "카드_개수_일치": True},
            {"parsed": True, "카드_개수_일치": True},
        ),
        _row(500, {"parsed": False}, {}),
    ]
    keys, per_key, all_model, all_service = _rates(rows)

    assert keys == ["parsed", "카드_개수_일치"]
    assert per_key["카드_개수_일치"] == (0.5, 0.5), "500 을 빼고 세면 100% 가 된다"
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
        "카드_개수_일치": True,
        "cards": [{"rankNo": 1}],
        "insights": ["문장"],
    }

    assert _checks(graded) == {"parsed": True, "카드_개수_일치": True}


def test_파싱_실패는_error_를_항목으로_세지_않는다():
    assert _checks({"parsed": False, "error": "JSONDecodeError: ..."}) == {"parsed": False}
