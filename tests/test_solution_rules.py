"""프롬프트 규칙 중 치환이 안 되는 것들 — 검출해서 재시도로 보낸다.

시각(#124)은 "오후 2시 → 14시" 가 결정론적이라 치환했다. 금액 어림과 배율은 그게 안 된다 —
"3만원" 이 어느 금액을 어림한 건지, "3배" 를 뭘로 바꿀지 코드가 못 정한다. 틀리게 바꾸느니
재시도가 낫다.

실측 준수율(n=48, Qwen3-32B): 금액 어림 83%, 배율 77%.
"""

import json

import pytest

from app.clients import llm
from app.services.solution import (
    _COMPUTED_RATIO,
    _ROUNDED_AMOUNT,
    _VAGUE_ACTION,
    _VAGUE_PERIOD,
    _metric_figures,
)
from devtools import grade

from .test_solutions import REQUEST_BODY, _cards, _post


@pytest.mark.parametrize("text", ["매출이 3만원입니다", "1억2천만원", "3만 5천원", "매출 1억원"])
def test_금액을_어림하면_걸린다(text):
    assert _ROUNDED_AMOUNT.search(text)


@pytest.mark.parametrize("text", ["1,340,580원입니다", "30,000원", "62,450원으로 가장 높습니다"])
def test_그대로_쓴_금액은_통과한다(text):
    assert not _ROUNDED_AMOUNT.search(text)


@pytest.mark.parametrize(
    "text", ["주말이 평일의 3배입니다", "평일은 주말의 3분의 1", "1.8배 높습니다", "두 배 차이"]
)
def test_배율을_직접_계산하면_걸린다(text):
    """지표에 없는 값이다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다."""
    assert _COMPUTED_RATIO.search(text)


@pytest.mark.parametrize("text", ["배달 매출이 늘었습니다", "직원을 배치하세요", "배송을 늘리세요"])
def test_배달_배치_배송은_배율이_아니다(text):
    assert not _COMPUTED_RATIO.search(text)


def test_채점기와_서비스가_같은_패턴을_쓴다():
    """채점기는 Colab 용이라 app 을 import 하지 않는다 — 복사본이 어긋나면 측정이 틀어진다."""
    cases = [
        "3만원",
        "1억2천만원",
        "1,340,580원",
        "30,000원",
        "3배입니다",
        "3분의 1",
        "배달 매출",
        "직원을 배치",
        "마케팅을 강화하세요",
        "홍보 활동을 확대하세요",
        "배달비를 늘리세요",
        "할인을 거세요",
        "현재 기간 순매출이 124,946,029원이며",
        "이번 기간 매출은 증가했습니다",
        "전 기간 대비 8.85% 증가했습니다",
        "2026-08-31 순매출이 1,183,600원입니다",
    ]
    for case in cases:
        assert bool(_ROUNDED_AMOUNT.search(case)) is bool(grade._ROUNDED.search(case)), case
        assert bool(_COMPUTED_RATIO.search(case)) is bool(grade._RATIO_WORD.search(case)), case
        assert bool(_VAGUE_ACTION.search(case)) is bool(grade._VAGUE_ACTION.search(case)), case
        assert bool(_VAGUE_PERIOD.search(case)) is bool(grade._VAGUE_PERIOD.search(case)), case


def test_그라더와_서비스의_수치_인용_판정이_같다():
    metrics = REQUEST_BODY["metrics"]
    cases = [
        "오늘 예상 매출 1,250,000원을 반영하세요",
        "커피 비중은 62%입니다",
        "직원 1명을 배치하세요",
        "14시까지 준비하세요",
    ]
    for case in cases:
        assert _metric_figures(case, metrics) == grade._metric_figures(case, metrics), case


@pytest.mark.parametrize(
    "text",
    [
        "디저트 메뉴에 대한 마케팅을 강화하세요",
        "홍보 활동을 확대하세요",
        "프로모션을 진행하세요",
        "전략을 변경하세요",
    ],
)
def test_뭉뚱그린_조언은_걸린다(text):
    assert _VAGUE_ACTION.search(text)


@pytest.mark.parametrize(
    "text", ["배달비를 늘리세요", "할인을 거세요", "인력을 늘리세요", "발주를 줄이세요"]
)
def test_구체적인_실행_지시는_통과한다(text):
    assert not _VAGUE_ACTION.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "현재 기간 순매출이 124,946,029원이며 전월보다 늘었습니다",
        "이번 기간 매출은 꾸준히 증가하고 있습니다",
        "해당 기간 동안 커피 매출이 가장 높았습니다",
    ],
)
def test_날짜_없는_기간_표현은_걸린다(text):
    """점주 신고: "현재 기간 순매출이 ...원이며" 처럼 기준 날짜가 어디에도 없었다."""
    assert _VAGUE_PERIOD.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "2026-08-31 순매출이 1,183,600원입니다",
        "전 기간 대비 8.85% 증가했습니다",  # vsPrevPeriod 비교는 계약상 정의된 대상이라 예외
        "이전 기간보다 매출이 늘었습니다",
    ],
)
def test_날짜가_있거나_이전_기간_비교는_통과한다(text):
    assert not _VAGUE_PERIOD.search(text)


async def test_금액을_어림하면_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "매출이 3만원인 시간대"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2
    assert "3만원" not in json.dumps(res.json(), ensure_ascii=False)


async def test_배율을_쓰면_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "주말이 평일의 3배인 시간대"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2


async def test_뭉뚱그린_조언이면_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "마케팅을 강화하세요"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2
    assert "마케팅을 강화" not in json.dumps(res.json(), ensure_ascii=False)


async def test_날짜_없는_기간표현이면_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards(
                (1, "현재 기간 순매출이 124,946,029원이며 전월보다 늘었습니다"), (2, "B"), (3, "C")
            )
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2
    assert "현재 기간" not in json.dumps(res.json(), ensure_ascii=False)


async def test_집계_기간이_요청에_있으면_프롬프트에_전달된다(monkeypatch):
    """salesSummary.period(BE 와 필드명 확정 전 AI 쪽 임시 이름)가 오면 모델에게 그대로

    알려줘야 "현재 기간" 같은 빈말도, targetDate 를 잘못 끌어다 쓰는 것도 막을 수 있다.
    """
    prompts = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        prompts.append(user)
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    body = json.loads(json.dumps(REQUEST_BODY))
    body["metrics"]["salesSummary"]["period"] = "2026-01-01~2026-03-31"

    res = await _post(body)

    assert res.status_code == 200
    assert "집계 기간은 2026-01-01~2026-03-31입니다" in prompts[0]


async def test_수치가_필드_사이에_중복되면_재시도한다(monkeypatch):
    """summaryText 가 쓴 지표 수치(예상 매출 1,250,000원)를 title 이 다시 쓰면 안 된다."""
    calls = []

    def _dup_card() -> str:
        return json.dumps(
            {
                "solutionCards": [
                    {
                        "rankNo": 1,
                        "title": "오늘 예상 매출 1,250,000원을 반영해 재고를 조정하세요",
                        "summaryText": "오늘 예상 매출이 1,250,000원으로 설정되어 있습니다.",
                        "detailText": "상세",
                        "evidence": "근거",
                    },
                    {
                        "rankNo": 2,
                        "title": "B",
                        "summaryText": "요약",
                        "detailText": "상세",
                        "evidence": "근거",
                    },
                    {
                        "rankNo": 3,
                        "title": "C",
                        "summaryText": "요약",
                        "detailText": "상세",
                        "evidence": "근거",
                    },
                ]
            },
            ensure_ascii=False,
        )

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _dup_card()
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2


async def test_두_번_다_위반이면_500_이_아니라_남은_카드가_나간다(monkeypatch):
    """예전에는 위반 카드가 있으면 세 장을 통째로 버려서, 두 번 다 걸리면 500 이었다.

    2026-10-08 실측에서 9 번 중 1 번이 그랬다(Claude 기준). 같은 파일 generate() 에
    "카드 2장이 나가는 것보다 500이 나가는 쪽이 점주에게 더 나쁘다"고 적어 둔 판단과
    어긋난다 — 그날 솔루션이 아예 없어진다.
    """
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return _cards((1, "매출이 3만원인 시간대"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200, "500 이 나가면 그날 솔루션이 없어진다"
    assert len(calls) == 2, "3 장을 선호하는 건 그대로다 — 재시도는 돈다"
    cards = res.json()["data"]["solutionCards"]
    assert len(cards) == 2
    assert "3만원" not in json.dumps(cards, ensure_ascii=False)


async def test_남은_카드의_rankNo_는_다시_연속으로_매긴다(monkeypatch):
    """중간이 빠지면 1·3 으로 나간다. 배정 지표가 2 종일 때는 늘 1·2 였으므로 연속성을
    유지한다 — FE 가 번호를 그대로 쓰는지 확인된 바 없다.
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return _cards((1, "A"), (2, "주말이 평일의 3배"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    cards = res.json()["data"]["solutionCards"]
    assert [card["rankNo"] for card in cards] == [1, 2]


async def test_세_장_다_위반이면_여전히_500_이다(monkeypatch):
    """한 장도 못 건지면 내보낼 게 없다. 빈 배열을 200 으로 주면 화면이 비는 쪽이 더 나쁘다."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return _cards((1, "3만원"), (2, "5만원"), (3, "7만원"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "SOLUTION_GENERATION_FAILED"


async def test_재시도가_더_적게_주면_앞의_결과를_유지한다(monkeypatch):
    """`parsed or cards` 로 두면 2 장을 받아둔 뒤 재시도가 1 장을 주면 더 나쁜 쪽으로 덮어쓴다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "A"), (2, "B"), (3, "3만원"))
        return _cards((1, "3만원"), (2, "5만원"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(res.json()["data"]["solutionCards"]) == 2, "1 장으로 덮어쓰면 안 된다"
