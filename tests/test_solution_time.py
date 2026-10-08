"""시각 12시간제 → 24시간제 치환 — app/services/solution.py::to_24h.

프롬프트가 2026-10-01 부터 24시간제를 지시하는데 실측 준수율이 40% 였다(n=48, Qwen3-32B).
전항목 통과율 27% 의 거의 전부가 이 한 항목 때문이라, 재시도 대신 코드로 치환한다.
"""

import json

import pytest

from app.services.solution import _AMPM_LEFT, _parse, to_24h
from devtools import grade


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("오후 2시에 할인", "14시에 할인"),
        ("오전 9시 오픈", "9시 오픈"),
        ("새벽 3시", "3시"),
        ("밤 10시 마감", "22시 마감"),
        ("저녁 7시~9시", "19~21시"),  # 뒤쪽 숫자가 접두어를 물려받는다
        ("오후 2~5시 프로모션", "14~17시 프로모션"),
        ("아침 7시—9시", "7~9시"),  # em dash
        ("오후 2시부터 오후 5시까지", "14시부터 17시까지"),
        ("낮 12시", "12시"),
        ("오전 12시", "0시"),  # 자정
        ("오후 12시", "12시"),  # 정오
    ],
)
def test_12시간제를_24시간제로_바꾼다(text, expected):
    assert to_24h(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "2시간 동안 진행하세요",  # 시각이 아니다
        "오후 시간대 매출이 낮습니다",  # 숫자가 없다
        "14시에 이미 24시간제입니다",  # 이미 맞다
        "오후 13시",  # 12시간제가 아니다 — 잘못된 입력은 손대지 않는다
        "오후 11~1시",  # 접두어를 넘어가 뜻이 모호하다
    ],
)
def test_시각이_아니거나_모호하면_손대지_않는다(text):
    assert to_24h(text) == text


def _raw(detail: str) -> str:
    return json.dumps(
        {
            "solutionCards": [
                {
                    "rankNo": 1,
                    "title": "오후 2시 프로모션",
                    "summaryText": "오후 2시 매출이 낮습니다.",
                    "detailText": detail,
                    "evidence": "오후 2시 매출은 30,000원입니다.",
                }
            ]
        },
        ensure_ascii=False,
    )


def test_파싱_단계에서_네_필드_모두_치환된다():
    cards = _parse(_raw("오후 2시에 안내하세요.\n오후 3시에 점검하세요.\n방문을 늘릴 수 있습니다."))

    assert cards is not None
    card = cards[0]
    assert "14시" in card.title
    assert "14시" in card.summaryText
    assert "14시" in card.detailText and "15시" in card.detailText
    assert "14시" in (card.evidence or "")
    assert "오후" not in json.dumps(card.model_dump(), ensure_ascii=False)


def test_치환하면_채점기의_시각_24시간제를_통과한다():
    """치환이 실제로 결함을 없애는지 채점기로 되짚는다."""
    from devtools.grade import grade_solution

    metrics = {
        "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
        "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
        "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
    }
    raw = _raw("오후 2시에 안내하세요.\n직원을 배치하세요.\n방문을 늘릴 수 있습니다.")

    assert grade_solution(raw, metrics)["시각_24시간제"] is False, "치환 전에는 걸려야 한다"

    cards = _parse(raw)
    fixed = json.dumps({"solutionCards": [c.model_dump() for c in cards]}, ensure_ascii=False)
    assert grade_solution(fixed, metrics)["시각_24시간제"] is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("낮 2시", "14시"),
        ("낮 6시", "18시"),
        ("낮 11시", "11시"),
        ("낮 12시", "12시"),
        ("낮 2시~4시", "14~16시"),
    ],
)
def test_낮_한시부터_여섯시는_오후다(text, expected):
    """`"낮 2시"` 를 `"2시"` 로 내보내면 새벽 2시가 된다 — 12 시간이 틀린 값인데 화면에서는
    멀쩡해 보인다. 2026-10-08 실측 중 발견했고, 그 전까지 `_hour24` 는 "낮" 을 보정이
    필요 없는 경우로 분류해 접두어만 떼고 있었다.
    """
    assert to_24h(text) == expected


@pytest.mark.parametrize("text", ["낮 7시", "낮 8시", "낮 10시"])
def test_뜻이_안_정해지는_낮은_손대지_않는다(text):
    """ "낮 7시" 는 아침 7시도 저녁 7시도 아니다 — 쓰지 않는 말이라 모델의 실수다.
    단정해서 바꾸느니 그대로 두고 재시도로 보낸다(`_violations` 의 AMPM_LEFT).
    """
    assert to_24h(text) == text
    assert _AMPM_LEFT.search(text), "치환도 안 하고 거부도 안 하면 틀린 값이 그대로 나간다"


@pytest.mark.parametrize("text", ["오후 2시간 동안", "저녁 3시간", "밤 10시간 영업"])
def test_지속시간은_시각이_아니다(text):
    """ "오후 2시간" 은 12 시간제 표기가 아니라 지속시간이다. 채점기에 `(?!간)` 이 없어서
    2026-10-08 측정에서 `시각_24시간제` 77.8% 가 전부 이 오탐이었다 — 모델 품질로
    오해할 숫자였다.
    """
    assert to_24h(text) == text
    assert not _AMPM_LEFT.search(text)
    assert not grade._AMPM.search(text)


def test_채점기와_서비스가_같은_시각_패턴을_쓴다():
    """채점기가 잡는 것은 서비스가 치환하거나 거부해야 한다. 둘이 어긋나면 한쪽은
    조용히 통과시키고 다른 쪽은 결함으로 센다 — `낮` 누락과 `(?!간)` 누락이 각각
    그 두 방향으로 한 번씩 났다.
    """
    cases = [
        "오후 2시",
        "오전 9시",
        "새벽 1시",
        "아침 8시",
        "낮 2시",
        "낮 7시",
        "저녁 7시",
        "밤 11시",
        "오후 2시~5시",
        "저녁 7시~9시",
        "오후 2시간 동안",
        "밤 10시간",
        "14시",
        "9시 30분",
    ]
    for case in cases:
        converted = to_24h(case)
        # 치환 뒤에 채점기가 잡는 게 남아 있으면, 서비스도 거부해 재시도로 보내야 한다
        if grade._AMPM.search(converted):
            assert _AMPM_LEFT.search(converted), f"채점기만 잡는다: {case!r} → {converted!r}"
        else:
            assert not _AMPM_LEFT.search(converted), f"서비스만 잡는다: {case!r} → {converted!r}"
