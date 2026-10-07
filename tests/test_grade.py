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
        or "14시까지 할인 안내를 띄우세요.\n직원 1명을 홀로 배치하세요.\n방문을 늘릴 수 있습니다.",
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
        detail="신메뉴를 1종 추가하세요.\n시식을 운영하세요.\n재방문을 늘릴 수 있습니다.",
        evidence="커피 매출 비중은 62%입니다.",
    )
    third = _card(
        3,
        title="오늘 예상 매출에 맞춘 준비",
        summary="오늘 예상 매출은 1,250,000원입니다.",
        detail="재료를 그에 맞춰 발주하세요.\n마감 인력을 1명 두세요.\n품절을 줄일 수 있습니다.",
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
    result = _insight(
        "커피 카테고리 매출이 메뉴 매출의 41.7%를 차지하고 있습니다.",
        "아메리카노가 메뉴 매출의 28.2%를 차지합니다.",
        "총 매출은 전기 대비 4.2% 증가했습니다.",
    )

    failed = [k for k, v in result.items() if isinstance(v, bool) and not v]
    assert failed == [], f"오탐: {failed}"


def test_비율을_반올림하면_걸린다():
    """0.042 는 4.2% 지 4% 가 아니다. 화면에서 티가 안 나 조용히 틀린다."""
    result = _insight("총 매출은 전기 대비 4% 증가했습니다.")

    assert result["비율_반올림_없음"] is False


def test_ratio_분모를_총매출로_말하면_걸린다():
    """ratio 의 분모는 menuSales 다. 총매출 기준이면 39.4% 라 틀린 문장이 된다."""
    result = _insight("커피가 전체의 41.7%를 차지합니다.")

    assert result["ratio_분모_정확"] is False


def test_인사이트도_요일_환각을_잡는다():
    result = _insight("금요일 12시 메뉴 매출이 420,000원으로 높습니다.")

    assert result["요일_환각_없음"] is False


def test_처방형으로_끝나면_걸린다():
    """인사이트는 관찰만 한다 — "~하세요"는 솔루션 카드의 몫이다."""
    result = _insight("커피 비중이 높으니 신메뉴를 추가하세요.")

    assert result["관찰형_종결"] is False
