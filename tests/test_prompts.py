from app.prompts import insight, solution

METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
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


def test_인사이트_프롬프트는_금액은_그대로_비율은_백분율로_쓰게_한다():
    """실호출에서 210,000 을 "30만원"으로 어림한 적이 있다(2026-09-21).

    반대로 지시를 금액에 한정하지 않으면 비율까지 원문대로 읽어 "0.12 감소"가 나온다.
    """
    assert "금액은 지표에 있는 값을 그대로 쓰고" in insight.SYSTEM
    assert "천 단위로 끊어" in insight.SYSTEM
    assert "백분율로 바꿔" in insight.SYSTEM


def test_인사이트_프롬프트에_지표가_들어간다():
    prompt = insight.build(METRICS, max_count=3)
    assert "커피" in prompt
    assert '"insights"' in prompt


def test_프롬프트_버전_상수가_있다():
    """프롬프트 내용을 바꾸면 이 값을 그날 날짜(YYYY-MM-DD)로 올린다. 배포 버전(v1/v2)과
    헷갈리지 않도록 v1/v2 형식은 쓰지 않는다."""
    assert solution.VERSION == "2026-09-21"
    assert insight.VERSION == "2026-09-21"
