"""프롬프트 규칙 중 치환이 안 되는 것들 — 검출해서 재시도로 보낸다.

시각(#124)은 "오후 2시 → 14시" 가 결정론적이라 치환했다. 금액 어림과 배율은 그게 안 된다 —
"3만원" 이 어느 금액을 어림한 건지, "3배" 를 뭘로 바꿀지 코드가 못 정한다. 틀리게 바꾸느니
재시도가 낫다.

실측 준수율(n=48, Qwen3-32B): 금액 어림 83%, 배율 77%.
"""

import json

import pytest

from app.clients import llm
from app.services.solution import _COMPUTED_RATIO, _ROUNDED_AMOUNT
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
    ]
    for case in cases:
        assert bool(_ROUNDED_AMOUNT.search(case)) is bool(grade._ROUNDED.search(case)), case
        assert bool(_COMPUTED_RATIO.search(case)) is bool(grade._RATIO_WORD.search(case)), case


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
