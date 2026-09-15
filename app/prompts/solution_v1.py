"""솔루션 카드 3장 + AI 인사이트를 LLM 1회 호출로 동시 생성한다.

위키 [AI] 단계4 원문 기준. 3회 개별 호출 대비 지연·비용이 1/3이고 카드 간 조언 중복도 막는다.
프롬프트를 고치면 VERSION 을 올리고 파일을 새로 만든다 (solution_v2.py).
"""

import json

VERSION = "v1"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
설명 없이 JSON만 출력하세요."""

_USER = """{metrics}

오늘은 {day_of_week}이고 {weekend}입니다. 위 지표는 {basis} 기준입니다.

점주가 오늘 실행할 수 있는 솔루션 카드 3장을 생성하세요.
각 카드는 서로 다른 지표를 근거로 하며, 중복된 조언을 내지 마세요.
evidence.value 에는 위 지표에 실제로 있는 숫자만 쓰세요.

{{"solutionCards":[{{"rank":1,"title":"...","detailContent":"...",
"evidence":{{"metric":"...","period":"...","value":0}}}}],
 "aiInsight":"..."}}"""


def build(metrics: dict, context: dict) -> str:
    return _USER.format(
        metrics=json.dumps(metrics, ensure_ascii=False),
        day_of_week=context["dayOfWeek"],
        weekend="주말" if context["isWeekend"] else "평일",
        basis=context["dataBasisPeriod"],
    )
