from app.prompts import insight, solution

METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -12},
    "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
    "categoryBreakdown": [{"name": "커피", "share": 62, "vsPrevPeriod": -12}],
}


def test_솔루션_프롬프트에_지표가_한글_그대로_들어간다():
    prompt = solution.build(METRICS, "2026-08-31", "MON", is_weekend=False)
    assert "커피" in prompt, "ensure_ascii=False 가 아니면 \\uXXXX 로 깨진다"
    assert "1183600" in prompt
    assert "평일" in prompt and "2026-08-31" in prompt


def test_솔루션_프롬프트의_JSON_예시가_깨지지_않는다():
    prompt = solution.build(METRICS, "2026-08-31", "MON", is_weekend=False)
    assert '"solutionCards"' in prompt
    assert '"rankNo":1' in prompt, "format() 이 중괄호를 먹으면 예시가 사라진다"


def test_인사이트_프롬프트는_행동_제안을_금지한다():
    assert "제안은 하지 말고" in insight.SYSTEM
    assert "관찰되는 사실만" in insight.SYSTEM


def test_인사이트_프롬프트에_지표가_들어간다():
    prompt = insight.build(METRICS, max_count=3)
    assert "커피" in prompt
    assert '"insights"' in prompt


def test_프롬프트_버전_상수가_있다():
    """promptVersion 응답 필드는 이 상수와 1:1 대응한다. 프롬프트를 고치면 이 값을 올린다."""
    assert solution.VERSION == "v2"
    assert insight.VERSION == "v2"
