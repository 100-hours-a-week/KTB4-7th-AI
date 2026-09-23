from app.prompts import insight, solution

METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "hourlyProfile": [{"dayType": "WEEKDAY", "hour": 14, "amount": 30000}],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
}

# 인사이트는 2026-09-22 계약으로 지표 구조가 통째로 바뀌었다 — 솔루션과 더는 같은 모양이 아니다.
INSIGHT_METRICS = {
    "salesSummary": {
        "totalSales": 7920000,
        "menuSales": 7480000,
        "orderCount": 923,
        "averageOrderValue": 8581,
        "vsPrevPeriod": 0.042,
    },
    "categorySales": [
        {"categoryName": "커피", "menuSales": 3120000, "ratio": 0.417, "vsPrevPeriod": -0.044}
    ],
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


def test_인사이트_프롬프트는_비율_반올림을_금지한다():
    """실호출 3회 중 1회가 0.042 를 "4% 증가"로 반올림했다(2026-09-22, 정답 4.2%).

    금액만 막는 지시로는 비율의 소수점이 사라지는 걸 잡지 못했다. 4.2 → 4 는 화면에서
    티가 안 나기 때문에 조용히 틀린 값이 나간다.
    """
    assert "반올림하거나 버리지 마세요" in insight.SYSTEM
    assert "0.042 → 4.2%" in insight.SYSTEM


def test_인사이트_프롬프트는_총액과_메뉴매출을_구분시킨다():
    """상세 지표가 전부 menuSales 계열이라 totalSales 와 섞으면 합이 안 맞는다."""
    assert "totalSales" in insight.SYSTEM
    assert "menuSales" in insight.SYSTEM


def test_인사이트_프롬프트는_다주_연속_표현을_금지한다():
    """salesTrend·weekdaySales 가 들어오면서 "3주 연속 감소"를 만들 재료가 생겼다.

    V1 은 한 달치 스냅샷이라 연속성을 확인할 근거가 없다(2026-09-22 풀스택 계약).
    """
    assert "연속성은 말하지 마세요" in insight.SYSTEM


def test_인사이트_프롬프트에_지표가_들어간다():
    prompt = insight.build(INSIGHT_METRICS, max_count=3, max_chars=100)
    assert "커피" in prompt
    assert '"insights"' in prompt
    assert "100자 이내" in prompt, "길이 제한을 모델에게도 알려야 재시도가 줄어든다"


def test_프롬프트_버전_상수가_있다():
    """프롬프트 내용을 바꾸면 이 값을 그날 날짜(YYYY-MM-DD)로 올린다. 배포 버전(v1/v2)과
    헷갈리지 않도록 v1/v2 형식은 쓰지 않는다."""
    assert solution.VERSION == "2026-09-23"
    assert insight.VERSION == "2026-09-23"


def test_챗봇_프롬프트는_chatDate_를_오늘로_넣는다():
    """툴 period 는 TODAY/THIS_WEEK/THIS_MONTH/CUSTOM 뿐이라, "지난달"을 조회하려면
    모델이 절대 날짜를 계산해 CUSTOM 으로 불러야 한다. 날짜가 없으면 못 한다.
    """
    from app.prompts import chat

    with_date = chat.build_system([], "2026-06-30")
    assert "2026-06-30" in with_date
    assert "역산하지 마세요" in with_date

    # BE 가 안 보내는 경우에도 프롬프트가 깨지지 않아야 한다
    without = chat.build_system([])
    assert "오늘은" not in without
    assert "지금 보고 있는 솔루션" in without


def test_솔루션_프롬프트는_금액은_천단위로_비율은_백분율로_쓰게_한다():
    """실호출에서 1,340,580 을 "134만 580원"으로, 0.0885 를 "-8.85% 감소"로 썼다.

    후자는 음수 부호와 "감소"가 겹쳐 증가로 읽힌다(2026-09-22).
    """
    assert "천 단위로 끊어" in solution.SYSTEM
    assert "백분율로 바꿔" in solution.SYSTEM
    assert '음수 부호와 "감소"를 함께 쓰지' in solution.SYSTEM


def test_챗봇_프롬프트는_마크다운을_금지한다():
    """FE 챗봇 말풍선이 평문 출력이다(2026-09-23 풀스택 확인).

    지시가 없으면 모델이 볼드와 불릿을 자연스럽게 쓴다 — QA(#96) C-01 에서 실제로
    `**평일 오후 …**` 와 `- 평일 14시 매출: 30,000원` 이 나왔다. 평문으로 표시하면
    사용자에게 기호가 그대로 보인다.
    """
    from app.prompts import chat

    assert "서식 없이 일반 문장으로만" in chat.SYSTEM
    assert "빈 줄로 문단 나누기" in chat.SYSTEM


def test_챗봇_프롬프트는_금액을_천_단위로_쓰게_한다():
    """인사이트·솔루션엔 있던 규칙이 챗봇에만 빠져 있었다.

    같은 매장 금액이 솔루션 카드에서는 "1,340,580원", 챗봇에서는 "134만 580원" 으로
    다르게 보인다. 값은 맞지만 화면 간 일관성이 깨진다.
    """
    from app.prompts import chat

    assert "3,247,891원처럼 천 단위로" in chat.SYSTEM
    assert "만 단위로 줄이지" in chat.SYSTEM
