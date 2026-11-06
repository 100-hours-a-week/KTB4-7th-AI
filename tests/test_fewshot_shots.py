"""few-shot 예시가 **실제 입력에 있는 필드로만** 추론하는지 지킨다.

2026-11-04: V5 의 카테고리 예시가 `previousShare`(이전 비중)로 "비중은 올랐지만 매출은
줄었다" 를 짚고 있었다. 좋은 추론인데 bench 케이스의 `categoryBreakdown` 은
name·share·vsPrevPeriod 뿐이라 모델이 재현할 수가 없다 — 카테고리 축 judge specific 이
0% 로 고정이던 이유다. 예시가 없는 필드를 쓰면 **아무 일도 안 일어나고, 왜 안 되는지도
안 보인다**(출력은 그대로 나온다).

과거 arm(V2~V5)은 재현을 위해 그대로 둔다 — 지키는 건 앞으로 돌릴 것뿐이다.
"""

from devtools.bench import SOLUTION_CASES
from devtools.fewshot_shots import SHOTS_V6, SHOTS_V7

_LIST_AXES = ("categoryBreakdown", "menuRankings", "hourlyProfile", "conditionPatterns")


def _fields(metrics: dict) -> dict[str, set[str]]:
    """축마다 그 축이 담은 필드 이름. 리스트 축은 행들의 합집합."""
    out: dict[str, set[str]] = {}
    for axis, value in metrics.items():
        if axis in _LIST_AXES and isinstance(value, list):
            out[axis] = {k for row in value if isinstance(row, dict) for k in row}
        elif isinstance(value, dict):
            out[axis] = set(value)
    return out


def _case_fields() -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {}
    for _, raw in SOLUTION_CASES:
        for axis, keys in _fields(raw).items():
            merged.setdefault(axis, set()).update(keys)
    return merged


def test_bench_케이스가_담은_필드를_안다():
    cases = _case_fields()
    # 이 테스트의 전제다 — 케이스에서 축이 사라지면 아래 검사가 공짜로 통과한다.
    for axis in ("salesSummary", "categoryBreakdown", "menuRankings", "hourlyProfile"):
        assert cases.get(axis), f"bench 케이스에 {axis} 가 없다"
    assert "conditionPatterns" in cases, (
        "bench 케이스에 conditionPatterns 가 없다 — 날씨 예시가 헛돈다"
    )


def test_V6_V7_예시는_케이스에_있는_필드만_쓴다():
    cases = _case_fields()
    for name, shots in (("V6", SHOTS_V6), ("V7", SHOTS_V7)):
        for index, (metrics, _) in enumerate(shots, start=1):
            for axis, keys in _fields(metrics).items():
                missing = keys - cases.get(axis, set())
                assert not missing, (
                    f"{name} 예시{index} 의 {axis} 가 bench 케이스에 없는 필드를 쓴다: "
                    f"{sorted(missing)} — 모델이 그 추론을 재현할 수 없다"
                )
