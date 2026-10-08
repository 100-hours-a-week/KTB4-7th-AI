from app.prompts import insight, solution
from app.services.insight_focus import assign as assign_insight_focus
from app.services.solution_focus import assign

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
    prompt = solution.build(assign(METRICS), "2026-08-31", "MON", is_weekend=False)
    assert "커피" in prompt, "ensure_ascii=False 가 아니면 \\uXXXX 로 깨진다"
    assert "1183600" in prompt
    assert "평일" in prompt and "2026-08-31" in prompt


def test_솔루션_프롬프트는_카드마다_근거를_하나씩만_보여준다():
    """전체 metrics 를 던지면 모델이 같은 지표로 카드 두 장을 만든다(실측 66%)."""
    prompt = solution.build(assign(METRICS), "2026-08-31", "MON", is_weekend=False)

    assert "[카드 1 근거]" in prompt and "[카드 3 근거]" in prompt
    assert "자기 근거 지표만" in prompt
    # 각 지표는 한 카드에만 나타난다
    for metric in ("hourlyProfile", "categoryBreakdown", "salesSummary"):
        assert prompt.count(f'"{metric}"') == 1, f"{metric} 이 여러 카드에 들어갔다"


def test_솔루션_프롬프트의_JSON_예시가_깨지지_않는다():
    prompt = solution.build(assign(METRICS), "2026-08-31", "MON", is_weekend=False)
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
    """2026-10-08 부터 metrics 전체가 아니라 문장별로 배정된 focus 가 들어간다."""
    focus = assign_insight_focus(INSIGHT_METRICS, max_count=3)
    prompt = insight.build(focus, max_chars=100)

    assert "커피" in prompt
    assert '"insights"' in prompt
    assert "100자 이내" in prompt, "길이 제한을 모델에게도 알려야 재시도가 줄어든다"


def test_인사이트_프롬프트는_문장마다_근거를_하나씩_붙인다():
    """지표 6 종을 통째로 주면 모델이 엉뚱한 값을 집는다(`수치_정확` 68%, n=48).

    배정한 개수만큼 블록이 나가야 한다 — 개수가 어긋나면 모델이 빈 근거로 문장을 만든다.
    """
    focus = assign_insight_focus(INSIGHT_METRICS, max_count=3)
    prompt = insight.build(focus, max_chars=100)

    assert len(focus) == 2, "INSIGHT_METRICS 는 salesSummary·categorySales 둘뿐이다"
    assert "[문장 1 근거]" in prompt and "[문장 2 근거]" in prompt
    assert "[문장 3 근거]" not in prompt
    assert "관찰 사실을 2개" in prompt
    assert "자기 근거 지표만" in prompt


def test_프롬프트_버전_상수가_있다():
    """프롬프트 내용을 바꾸면 이 값을 그날 날짜(YYYY-MM-DD)로 올린다. 배포 버전(v1/v2)과
    헷갈리지 않도록 v1/v2 형식은 쓰지 않는다."""
    assert solution.VERSION == "2026-10-07"
    assert insight.VERSION == "2026-10-08"


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


def test_솔루션_프롬프트는_detailText_를_줄바꿈으로_나누게_한다():
    """상세 내용이 한 문단으로 길게 나와 읽기 어렵다는 피드백(2026-09-28).

    줄바꿈이 화면에 보존되는 것은 배포본으로 확인했다(2026-09-29). 챗봇과 다르다.
    2026-10-01 에 실행 방법 두 문장에 기대효과 한 문장을 더해 세 문장이 됐다.
    """
    prompt = solution.build(METRICS, "2026-09-29", "MON", is_weekend=False)

    assert "세 문장" in prompt
    assert "줄바꿈" in prompt
    assert "같은 내용을 반복하지 않게" in prompt


def test_솔루션_프롬프트는_summaryText_수치_반복을_금지한다():
    """evidence 가 화면에 노출된다는 걸 2026-09-29 에 확인해 수치를 evidence 한 곳에만
    쓰게 했었다. 2026-10-01, FE 가 상세보기에서 evidence 를 숨기기로 가정하면서(미확정)
    유일하게 화면에 보이는 숫자 자리를 summaryText 로 옮겼다 — title·detailText 가
    summaryText 의 수치를 다시 반복하는 것만 금지한다.
    """
    prompt = solution.build(METRICS, "2026-09-29", "MON", is_weekend=False)

    assert "summaryText 에서 이미 쓴 지표 수치를 title·detailText 에서 또 쓰지 마세요" in prompt
    assert "근거 수치와 함께 한 문장으로 쓰세요" in prompt


def test_솔루션_프롬프트는_행동의_얼마나를_금지한다():
    """시각은 지표에 있지만 할인율·인원은 없다.

    2026-10-07 에 뒤집었다. 그 전까지는 "실행에 필요한 시각·인원·할인율"을 허용했는데,
    마진을 모르는데 "10% 할인"을, 인건비 대비 생산성을 모르는데 "직원 1명 추가"를 말할
    근거가 없다. 추상적이면 점주가 안 쓰고 말지만 구체적이고 틀리면 돈을 잃는다.
    """
    prompt = solution.build(assign(METRICS), "2026-09-29", "MON", is_weekend=False)

    assert "14시까지" in prompt, "시각은 지표에 있으므로 허용한다"
    assert "할인율·인원·수량은 지표에 없는 값" in prompt
    assert "누구나 할 수 있는 말" in prompt, "공허한 조언 금지도 같이 들어간다"


def test_솔루션_프롬프트의_줄바꿈_안내가_한_줄로_나간다():
    r"""`줄바꿈(\n)`을 소스에 `\n` 으로 적으면 파이썬이 실제 개행으로 바꿔 문장이 쪼개진다.

    모델에게 "\n 으로 구분하라"고 문자 그대로 알려야 하는 자리라 `\\n` 이어야 한다.
    깨져 있어도 모델이 의도를 알아들어 출력은 맞게 나왔기 때문에 실호출로도 안 잡혔다.
    """
    prompt = solution.build(METRICS, "2026-09-30", "WED", is_weekend=False)

    assert r"줄바꿈(\n)으로 구분해 쓰세요" in prompt

    line = next(li for li in prompt.split("\n") if "줄바꿈(" in li)
    assert "구분해 쓰세요" in line, f"안내 문장이 개행으로 쪼개졌다: {line!r}"
