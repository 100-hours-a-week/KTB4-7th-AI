"""솔루션 카드 3장을 LLM 1회 호출로 생성한다.

v2: docs/api정의서.md·docs/ERD정의서.md 확정 반영 (2026-09-16).
- 요청에서 context(dayOfWeek/isWeekend/dataBasisPeriod)가 빠졌다. 서비스가 targetDate 로부터
  요일·주말 여부를 코드로 계산해 넘긴다 — 달력 계산이라 환각 위험이 없다(매출 수치 계산과는 다르다).
- 카드 필드는 ERD 컬럼명(rankNo/summaryText/detailText)을 쓴다. evidence 는 없다
  — `solutions` 테이블에 evidence 컬럼 자체가 없다(ERD 확인 완료).
- 최상위 aiInsight 는 제거했다 — 매출 AI 인사이트는 별도 `/internal/v1/ai/sales-insights` 담당.
"""

import json

VERSION = "2026-09-17"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
설명 없이 JSON만 출력하세요."""

_USER = """{metrics}

오늘은 {target_date}({day_of_week})이고 {weekend}입니다.

점주가 오늘 실행할 수 있는 솔루션 카드 3장을 생성하세요.
각 카드는 서로 다른 지표를 근거로 하며, 중복된 조언을 내지 마세요.
summaryText 는 한 문장 요약이고, detailText 는 구체적인 실행 방법을 담은 상세 설명입니다.

{{"solutionCards":[{{"rankNo":1,"title":"...","summaryText":"...","detailText":"..."}}]}}"""


def build(metrics: dict, target_date: str, day_of_week: str, is_weekend: bool) -> str:
    return _USER.format(
        metrics=json.dumps(metrics, ensure_ascii=False),
        target_date=target_date,
        day_of_week=day_of_week,
        weekend="주말" if is_weekend else "평일",
    )
