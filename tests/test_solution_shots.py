"""배포되는 few-shot 예시가 제 규칙을 지키는지 본다.

예시는 모델이 베끼는 본보기다 — 위반을 담으면 그걸 가르친다. 2026-11-04 에 실제로
그랬다(단일 품목 예시가 메뉴 축 judge specific 을 60% → 10% 로 깎았다).
"""

import json

import pytest

from app.prompts import solution as solution_prompt
from app.prompts import solution_shots
from app.services.solution_focus import assign, derive
from devtools import grade


def test_예시가_채점기를_통과한다():
    """예시가 프롬프트 규칙을 어기면 모델에게 위반을 시연하는 셈이다."""
    for index, (metrics, output) in enumerate(solution_shots.SHOTS, start=1):
        derived = derive(metrics)
        expected = len(assign(derived)) or grade.MAX_CARDS
        result = grade.grade_solution(json.dumps(output, ensure_ascii=False), derived, expected)
        failed = [
            key
            for key, value in result.items()
            if isinstance(value, bool) and not value and key not in grade.MEASURE_ONLY
        ]
        assert result["parsed"], f"예시{index} 가 파싱되지 않는다"
        assert failed == [], f"예시{index} 가 채점기를 못 넘었다: {failed}"


def test_예시_user_턴은_근거_블록만_담는다():
    """규칙까지 실으면 2 쌍이 규칙을 세 번 싣는다 — 창 8,192 에서 출력 여유가 사라진다.

    2026-11-06 실측: 규칙 포함 2 쌍은 입력 7,105(여유 1,087)이고 실측 출력이 500~1,000
    이라 꼬리가 잘린다. 근거만 담으면 입력 4,176(여유 4,016)이다.
    """
    turns = solution_shots.messages()
    users = [t["content"] for t in turns if t["role"] == "user"]

    assert users, "예시 user 턴이 없다"
    for content in users:
        assert content.startswith("[카드 1 근거]"), "근거 블록으로 시작해야 한다"
        assert "쓰지 마세요" not in content, "규칙이 예시 user 턴에 실렸다 — 창 절약이 안 된다"
        assert "{" in content, "근거 지표 JSON 이 없다"


def test_예시_턴이_user_assistant_순서로_짝을_이룬다():
    turns = solution_shots.messages()

    assert len(turns) == len(solution_shots.SHOTS) * 2
    assert [t["role"] for t in turns] == ["user", "assistant"] * len(solution_shots.SHOTS)
    for turn in turns:
        if turn["role"] == "assistant":
            assert "solutionCards" in json.loads(turn["content"])


def test_근거_블록을_실제_호출과_같은_함수로_만든다():
    """사람이 쓴 블록을 쓰면 예시와 실제 호출의 글자가 어긋난다."""
    metrics, _ = solution_shots.SHOTS[0]
    focus = assign(derive(metrics))

    assert solution_shots.messages()[0]["content"] == solution_prompt.focus_blocks(focus)
    # 실제 호출의 user 턴에도 같은 글자가 들어간다.
    built = solution_prompt.build(focus, "2026-11-07", "토요일", True)
    assert solution_prompt.focus_blocks(focus) in built


@pytest.mark.asyncio
async def test_솔루션_생성이_예시를_실어_보낸다(monkeypatch):
    """예시를 붙여놓고 호출에 안 실으면 조용히 예시 없는 품질로 돌아간다."""
    from app.clients import llm
    from app.schemas.solution import SolutionRequest
    from app.services import solution as service
    from tests.test_solutions import REQUEST_BODY

    seen: dict = {}

    async def fake_complete(system, user, max_tokens=2000, timeout=None, shots=(), **_):
        seen["shots"] = list(shots)
        return json.dumps(
            {
                "solutionCards": [
                    {
                        "rankNo": 1,
                        "title": "14시까지 재고 점검을 끝내 두세요",
                        "summaryText": "평일 14시가 하루 중 매출이 가장 낮습니다.",
                        "detailText": "14시에 재고 점검을 끝내 두세요.",
                        "evidence": "평일 lowHour 14시",
                    }
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(llm, "complete", fake_complete)
    await service.generate(SolutionRequest.model_validate(REQUEST_BODY))

    assert seen["shots"] == solution_shots.messages(), "예시가 호출에 실리지 않았다"
