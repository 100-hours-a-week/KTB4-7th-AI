"""솔루션 카드 3장을 LLM 1회 호출로 생성한다.

2026-09-16: docs/api정의서.md·docs/ERD정의서.md 확정 반영.
- 요청에서 context(dayOfWeek/isWeekend/dataBasisPeriod)가 빠졌다. 서비스가 targetDate 로부터
  요일·주말 여부를 코드로 계산해 넘긴다 — 달력 계산이라 환각 위험이 없다(매출 수치 계산과는 다르다).
- 카드 필드는 ERD 컬럼명(rankNo/summaryText/detailText/evidence)을 쓴다.
  evidence 는 `solutions.evidence_text`(TEXT NULL)에 대응한다(2026-09-21 BE에 컬럼 추가 요청).
- 최상위 aiInsight 는 제거했다 — 매출 AI 인사이트는 별도 `/internal/v1/ai/sales-insights` 담당.

2026-09-22: 금액·비율 표기 규칙을 추가했다(인사이트 프롬프트와 같은 규칙). 실호출에서
1,340,580 을 "134만 580원"으로 쓰거나, "전 기간 대비 -8.85% 감소했습니다"처럼 음수 부호와
"감소"를 겹쳐 써서 증가로 읽히는 문장이 나왔다. 계약상 비율은 소수로 주고받지만(0.0885)
점주에게 보여줄 문장에서는 백분율이어야 한다.
"""

import json

VERSION = "2026-09-22"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
금액은 지표에 있는 값을 그대로 쓰고 어림하지 마세요 — 1,340,580원처럼 천 단위로 끊어 씁니다.
비율은 소수가 아니라 백분율로 바꿔 쓰고(0.0885 → 8.85%), 음수 부호와 "감소"를 함께 쓰지 마세요.
설명 없이 JSON만 출력하세요."""

_USER = """{metrics}

오늘은 {target_date}({day_of_week})이고 {weekend}입니다.

점주가 오늘 실행할 수 있는 솔루션 카드 3장을 생성하세요.
각 카드는 서로 다른 지표를 근거로 하며, 중복된 조언을 내지 마세요.
summaryText 는 한 문장 요약이고, detailText 는 구체적인 실행 방법을 담은 상세 설명입니다.
title 은 200자를 넘기지 말고, rankNo 는 1·2·3 을 하나씩만 쓰세요.
evidence 는 이 카드를 제안한 이유를 위 지표에서 그대로 인용한 한 문장입니다
— 지표에 없는 수치를 쓰지 말고, 해법이 아니라 관찰된 사실만 담으세요.

{{"solutionCards":[{{"rankNo":1,"title":"...","summaryText":"...","detailText":"...","evidence":"..."}}]}}"""


def build(metrics: dict, target_date: str, day_of_week: str, is_weekend: bool) -> str:
    return _USER.format(
        metrics=json.dumps(metrics, ensure_ascii=False),
        target_date=target_date,
        day_of_week=day_of_week,
        weekend="주말" if is_weekend else "평일",
    )
