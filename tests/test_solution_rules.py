"""프롬프트 규칙 중 치환이 안 되는 것들 — 검출해서 재시도로 보낸다.

시각(#124)은 "오후 2시 → 14시" 가 결정론적이라 치환했다. 금액 어림과 배율은 그게 안 된다 —
"3만원" 이 어느 금액을 어림한 건지, "3배" 를 뭘로 바꿀지 코드가 못 정한다. 틀리게 바꾸느니
재시도가 낫다.

실측 준수율(n=48, Qwen3-32B): 금액 어림 83%, 배율 77%.
"""

import json

import pytest

from app.clients import llm
from app.schemas.solution import SolutionCard
from app.services.solution import (
    _COMPUTED_RATIO,
    _ROUNDED_AMOUNT,
    _VAGUE_ACTION,
    _VAGUE_PERIOD,
    _metric_figures,
    _violations,
)
from app.services.solution_focus import derive, peak_ratios
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


async def test_금액을_어림하면_그_카드를_버린다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "매출이 3만원인 시간대"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 1, "재시도하지 않는다 — 버리고 끝낸다(2026-10-17 최소 1·최대 3장)"
    assert "3만원" not in json.dumps(res.json(), ensure_ascii=False)


async def test_배율을_쓰면_그_카드를_버린다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "주말이 평일의 3배인 시간대"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 1, "재시도하지 않는다 — 버리고 끝낸다(2026-10-17 최소 1·최대 3장)"


async def test_뭉뚱그린_조언은_재시도하지_않고_내보낸다(monkeypatch):
    """2026-10-17 분리. 밋밋한 말은 점주가 믿고 행동해도 손해를 보지 않는다 — 그 한 장을
    버리고 2 장만 주는 쪽이 더 나쁘다.

    A40 5차 실측에서 게이트 8 개로 `카드_개수_일치` 가 23.3% 까지 떨어졌다(게이트 4 개였던
    1 차는 91.7%). MAX_RETRY=1 이라 초과분이 지연이 아니라 카드 손실로 나간다.
    채점기(devtools/grade.py)는 그대로 재므로 측정에서는 계속 보인다.
    """
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return _cards((1, "마케팅을 강화하세요"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 1, "재시도하지 않는다"
    cards = res.json()["data"]["solutionCards"]
    assert len(cards) == 3, "카드를 버리지 않는다"
    assert "마케팅을 강화" in json.dumps(cards, ensure_ascii=False)


async def test_날짜_없는_기간표현이면_그_카드를_버린다(monkeypatch):
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
    assert len(calls) == 1, "재시도하지 않는다 — 버리고 끝낸다(2026-10-17 최소 1·최대 3장)"
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


async def test_수치가_필드_사이에_중복돼도_재시도하지_않는다(monkeypatch):
    """2026-10-17 분리. 같은 수치를 반복하는 건 읽기 아쉬운 것이지 틀린 게 아니다 —
    그 카드를 버리고 2 장만 주는 쪽이 점주에게 더 나쁘다. 채점기는 그대로 잰다.
    """
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
        return _dup_card()

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 1, "재시도하지 않는다"
    assert len(res.json()["data"]["solutionCards"]) == 3, "카드를 버리지 않는다"


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
    assert len(calls) == 1, "위반 카드만 버리고 끝낸다 — 3 장을 채우려 다시 부르지 않는다"
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


# ── 배율 접지 (2026-10-16) ────────────────────────────────────────────
# 배율을 통째로 금지했더니 재시도 1 위가 COMPUTED_RATIO 였다(3/3 건이 hourlyProfile 카드).
# 30,000 대 210,000 이면 "7 배" 가 그 데이터의 핵심 사실이라 모델이 계속 그걸 쓰려 한다.
# 막는 대신 코드가 계산해 넘기고, 지표에 없는 배율만 거부한다.

_RATIO_METRICS = derive(
    {
        "salesSummary": {"netSales": 1183600},
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ],
    }
)


def _ratio_card(text: str) -> SolutionCard:
    return SolutionCard(
        rankNo=1, title="가", summaryText=text, detailText="가.\n나.\n다.", evidence="가"
    )


def test_지표에_있는_배수는_인용해도_된다():
    assert _RATIO_METRICS["hourlyPeakRatio"] == [
        {"dayType": "WEEKDAY", "peakHour": 18, "lowHour": 14, "ratio": 7.0}
    ]
    assert not _violations(_ratio_card("평일 18시 매출이 14시의 7배입니다"), _RATIO_METRICS)


def test_한글_숫자로_써도_인정한다():
    """ "일곱 배" 도 _COMPUTED_RATIO 가 잡는 표현이라 접지 판정을 똑같이 받아야 한다."""
    assert not _violations(_ratio_card("평일 18시 매출이 14시의 일곱 배입니다"), _RATIO_METRICS)


@pytest.mark.parametrize("text", ["14시의 5배입니다", "18시의 3분의 1입니다"])
def test_지표에_없는_배율은_그대로_거부한다(text):
    assert _violations(_ratio_card(text), _RATIO_METRICS) == ["COMPUTED_RATIO"]


def test_지표의_다른_숫자를_배율로_쓰면_거부한다():
    """hour 14·18 은 지표에 있지만 배율이 아니다. _metric_numbers 전체로 접지하면
    "14배" 가 통과한다 — 그래서 hourlyPeakRatio 만 본다.
    """
    assert _violations(_ratio_card("14시의 14배입니다"), _RATIO_METRICS) == ["COMPUTED_RATIO"]


def test_배수는_dayType_별로_따로_낸다():
    """평일 최고와 주말 최저를 섞으면 틀린 문장이 된다."""
    ratios = peak_ratios(
        [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
            {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
            {"dayType": "WEEKEND", "hour": 18, "amount": 110000},
        ]
    )
    assert ratios == [
        {"dayType": "WEEKDAY", "peakHour": 18, "lowHour": 14, "ratio": 7.0},
        {"dayType": "WEEKEND", "peakHour": 18, "lowHour": 14, "ratio": 1.2},
    ]


def test_0원_행은_배수_계산에서_뺀다():
    """영업시간 밖 0 원이 섞이면 배수가 무한대가 된다 — 최저 판단에서 빼는 것과 같은 이유."""
    ratios = peak_ratios(
        [
            {"dayType": "WEEKDAY", "hour": 3, "amount": 0},
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
        ]
    )
    assert ratios == [{"dayType": "WEEKDAY", "peakHour": 18, "lowHour": 14, "ratio": 7.0}]


def test_채점기와_서비스가_같은_배율_접지를_쓴다():
    """둘이 어긋나면 측정과 실제 동작이 갈린다 — 금액·시각 패턴에 이미 같은 테스트가 있다."""
    import json

    from devtools.grade import grade_solution

    for text, grounded in (("14시의 7배입니다", True), ("14시의 5배입니다", False)):
        card = {
            "rankNo": 1,
            "title": "가",
            "summaryText": text,
            "detailText": "가.\n나.\n다.",
            "evidence": "가",
        }
        raw = json.dumps({"solutionCards": [card]}, ensure_ascii=False)
        graded = grade_solution(raw, _RATIO_METRICS, expected_cards=1)
        service_ok = not _violations(_ratio_card(text), _RATIO_METRICS)

        assert graded["배율_없음"] is grounded, text
        assert service_ok is grounded, text


# ── 지표에 없는 수 · 비교 불가 축 (2026-10-16) ────────────────────────
# 배포본 카드 셋에서 나왔다.
#   "남은 시간 동안 253,196원을 추가로 만들어야 합니다"  ← 255,396 - 2,200 을 모델이 계산
#   "평일 9시 매출이 다른 시간대에 비해 현저히 낮습니다"   ← 시간대 행이 하나뿐이었다

_SPARSE = derive(
    {
        "salesSummary": {"netSales": 2200},
        "predictedSalesToday": 255396,
        "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 9, "amount": 2200}],
        "categoryBreakdown": [{"name": "미분류", "share": 1.0}],
    }
)


def test_지표에_없는_금액을_지어내면_거부한다():
    text = (
        "현재까지 순매출이 2,200원인데 오늘 예상은 255,396원으로, 253,196원을 더 만들어야 합니다."
    )
    assert _violations(_ratio_card(text), _SPARSE) == ["UNGROUNDED_NUMBER"]


def test_지표에_있는_금액은_그대로_통과한다():
    text = "현재까지 순매출은 2,200원이고 오늘 예상 매출은 255,396원입니다."
    assert not _violations(_ratio_card(text), _SPARSE)


@pytest.mark.parametrize("text", ["14시까지 입간판을 내어 두세요", "9시에 문을 여세요"])
def test_한두_자리_수는_실행_지시라_통과한다(text):
    """시각·인원은 지표에 없어도 프롬프트가 허용한다 — 막으면 실행 문장을 못 쓴다."""
    assert not _violations(_ratio_card(text), _SPARSE)


def test_비교할_행이_없으면_시간대_축을_배정하지_않는다():
    """0.0 을 돌려주면 "할 말은 없지만 후보" 가 되어 카드로 배정되고, 모델은 배정받은
    지표로 뭐든 써야 하니 없는 비교를 지어낸다.
    """
    from app.services.solution_focus import _hourly_score, assign

    one_row = [{"dayType": "WEEKDAY", "hour": 9, "amount": 2200}]
    assert _hourly_score(one_row) == -1.0
    assert not any("hourlyProfile" in item for item in assign(_SPARSE))


def test_비교할_행이_있으면_그대로_배정한다():
    two_rows = [
        {"dayType": "WEEKDAY", "hour": 9, "amount": 2200},
        {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
    ]
    from app.services.solution_focus import _hourly_score, assign

    assert _hourly_score(two_rows) > 0
    assert any("hourlyProfile" in item for item in assign({**_SPARSE, "hourlyProfile": two_rows}))


def test_채점기가_title_summaryText_의_수치도_본다():
    """그동안 evidence·detailText 만 봤다. 배포본 날조가 summaryText 에 있었는데
    측정에서는 수치_정확 100% 로 보였다.
    """
    import json

    from devtools.grade import grade_solution

    card = {
        "rankNo": 1,
        "title": "가",
        "summaryText": "253,196원을 더 만들어야 합니다.",
        "detailText": "가.\n나.\n다.",
        "evidence": "가",
    }
    raw = json.dumps({"solutionCards": [card]}, ensure_ascii=False)
    graded = grade_solution(raw, _SPARSE, expected_cards=1)

    assert graded["summary_수치_정확"] is False
    assert graded["detail_수치_정확"] is True, "detailText 에는 날조가 없다"


def test_배수에_어느_두_시각인지_같이_준다():
    """배수만 주면 모델이 아무 두 행에 갖다 붙인다 — 실측에서 "12시가 15시의 50.2배" 가
    나왔는데 50.2 는 12시 대 9시 값이고 12시÷15시는 6.7 이다.

    숫자 자체는 지표에 있어서 배율_없음 을 통과하고, 정수부가 두 자리라 _ungrounded 도
    실행 지시로 보고 넘긴다 — 어떤 검사에도 안 걸리는 틀린 문장이 된다. 그래서 코드가
    어느 두 시각 사이인지까지 넘겨야 한다.
    """
    ratios = peak_ratios(
        [
            {"dayType": "WEEKDAY", "hour": 9, "amount": 8200},
            {"dayType": "WEEKDAY", "hour": 12, "amount": 412000},
            {"dayType": "WEEKDAY", "hour": 15, "amount": 61500},
            {"dayType": "WEEKDAY", "hour": 20, "amount": 19800},
        ]
    )

    assert ratios == [{"dayType": "WEEKDAY", "peakHour": 12, "lowHour": 9, "ratio": 50.2}]


def test_잘못_붙인_배수는_어떤_검사에도_안_걸린다():
    """현재 상태를 고정해 둔다 — 코드가 두 시각을 주는 것 말고는 막을 방법이 없다.

    막으려면 "N배" 가 나온 문장이 peakHour·lowHour 를 함께 말하는지 봐야 하는데,
    "피크가 최저의 50.2배" 처럼 시각을 안 쓰는 정상 문장도 있어 오탐이 난다.
    """
    from devtools.grade import _ungrounded

    metrics = derive(
        {
            "salesSummary": {"netSales": 2470300},
            "hourlyProfile": [
                {"dayType": "WEEKDAY", "hour": 9, "amount": 8200},
                {"dayType": "WEEKDAY", "hour": 12, "amount": 412000},
                {"dayType": "WEEKDAY", "hour": 15, "amount": 61500},
            ],
        }
    )
    wrong = "평일 12시 매출이 412,000원으로 15시 61,500원의 50.2배입니다"

    assert not _violations(_ratio_card(wrong), metrics), "서비스는 못 잡는다"
    assert not _ungrounded(wrong, metrics), "채점기도 못 잡는다 — 50.2 는 두 자리다"


# ── 공허한 조언 패턴 확대 (2026-10-16) ──────────────────────────────
# 옛 패턴은 명사와 동사가 붙어 있을 때만 잡아서, 실측 218 개 실행 문장에서 0 개를 잡았다.
# `공허한_조언_없음` 100% 가 "잘 지킨다" 가 아니라 "아무것도 안 본다" 였다.


@pytest.mark.parametrize(
    "text",
    [
        "마케팅을 강화하세요",  # 옛 패턴도 잡던 교과서 문구
        "프로모션을 진행하세요",
        "커피 메뉴 프로모션과 추천 강화로 점유율을 회복하세요",  # 사이에 말이 끼면 못 잡았다
        "14시 이후 평일 오후 메뉴를 강화하세요",
        "커피 메뉴 주문 경험을 개선하세요",
        "논커피 음료 메뉴를 전면에 배치하고 직원 추천을 강화하세요",
    ],
)
def test_공허한_조언을_잡는다(text):
    assert _VAGUE_ACTION.search(text), text


@pytest.mark.parametrize(
    "text",
    [
        "12시 전후로 인력을 집중 배치해 대기 시간을 줄이세요",  # 집중 배치는 구체적 행위다
        "11시부터 13시까지 직원 근무 시간을 집중 편성하세요",
        "14시까지 입간판을 내어 두세요",
        "원두 발주를 줄이세요",
        "인기 메뉴 재고를 오전에 충분히 준비하세요",
        "주문과 서빙 동선을 점검하세요",
    ],
)
def test_구체적인_실행은_통과시킨다(text):
    """넓히다가 좋은 문장을 잡으면 재시도만 늘고 카드가 나빠진다 — 실측 218 개 중
    '집중 배치'·'집중 편성' 류가 가장 흔한 정상 문장이다.
    """
    assert not _VAGUE_ACTION.search(text), text


async def test_틀린_말은_카드를_버려서_막는다(monkeypatch):
    """분리의 반대쪽. 없는 숫자·어림 금액·잘못된 시각은 점주가 믿고 행동하면 손해를
    본다 — 카드를 버려서라도 막는다.
    """
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "매출이 3만원인 시간대"), (2, "B"), (3, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)
    res = await _post(REQUEST_BODY)

    assert len(calls) == 1, "재시도하지 않는다 — 버리고 끝낸다(2026-10-17 최소 1·최대 3장)"
    assert "3만원" not in json.dumps(res.json(), ensure_ascii=False)


async def test_전부_차단되면_재시도하고_밋밋한_사유도_피드백에_싣는다(monkeypatch):
    """재시도는 한 장도 못 건졌을 때만 돈다(2026-10-17). 그때가 피드백이 가장 필요한
    자리이고, 밋밋한 사유도 같이 실어 보낸다 — 호출을 더 쓰지 않고 품질만 챙긴다.
    """
    prompts = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        prompts.append(user)
        if len(prompts) == 1:
            return _cards(
                (1, "매출이 3만원인 시간대"),
                (2, "매출이 5만원이고 마케팅을 강화하세요"),
                (3, "매출이 7만원인 구간"),
            )
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)
    await _post(REQUEST_BODY)

    assert len(prompts) == 2, "한 장도 못 건지면 재시도한다"
    feedback = prompts[1]
    assert "천 단위" in feedback or "어림" in feedback, "차단 사유가 피드백에 있다"
    assert "마케팅" in feedback or "홍보" in feedback, "밋밋한 사유도 같이 실린다"


def test_차단_사유와_측정_전용_사유가_갈려_있다():
    from app.services.solution import _BLOCKING_REASONS

    assert "DUPLICATE_FIGURE" not in _BLOCKING_REASONS
    assert "VAGUE_ACTION" not in _BLOCKING_REASONS
    assert {"UNGROUNDED_NUMBER", "ROUNDED_AMOUNT", "COMPUTED_RATIO"} <= _BLOCKING_REASONS
