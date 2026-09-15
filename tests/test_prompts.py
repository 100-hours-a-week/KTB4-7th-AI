from app.prompts import insight_v1, solution_v1

METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
}
CONTEXT = {"dayOfWeek": "MON", "isWeekend": False, "dataBasisPeriod": "2026-08-30"}


def test_솔루션_프롬프트에_지표가_한글_그대로_들어간다():
    prompt = solution_v1.build(METRICS, CONTEXT)
    assert "커피" in prompt, "ensure_ascii=False 가 아니면 \\uXXXX 로 깨진다"
    assert "1183600" in prompt
    assert "평일" in prompt and "2026-08-30" in prompt


def test_솔루션_프롬프트의_JSON_예시가_깨지지_않는다():
    prompt = solution_v1.build(METRICS, CONTEXT)
    assert '"solutionCards"' in prompt
    assert '"rank":1' in prompt, "format() 이 중괄호를 먹으면 예시가 사라진다"


def test_인사이트_프롬프트는_행동_제안을_금지한다():
    assert "제안은 하지 말고" in insight_v1.SYSTEM
    assert "관찰되는 사실만" in insight_v1.SYSTEM


def test_인사이트_프롬프트에_지표가_들어간다():
    prompt = insight_v1.build(METRICS)
    assert "커피" in prompt
    assert '"insights"' in prompt


def test_프롬프트_버전이_파일명과_일치한다():
    assert solution_v1.VERSION == "v1"
    assert insight_v1.VERSION == "v1"
