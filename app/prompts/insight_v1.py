"""매출분석 화면의 "AI가 발견했어요" 영역에 쓸 관찰형 인사이트를 생성한다.

위키 [AI] 단계1 §7.3 기준. 솔루션과 달리 **행동 처방을 하지 않는다** — 관찰만 한다.
실측 집계만 입력이고 예측 이력과 무관하다.
"""

import json

VERSION = "v1"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
무엇을 하라는 제안은 하지 말고, 데이터에서 관찰되는 사실만 말하세요.
설명 없이 JSON만 출력하세요."""

_USER = """{metrics}

위 지표에서 점주가 알아두면 좋을 관찰 사실을 최대 3개 찾아주세요.
각 문장은 한 문장으로, 점주에게 말하듯 자연스럽게 쓰세요.
evidence.value 에는 위 지표에 실제로 있는 숫자만 쓰세요.

{{"insights":[{{"text":"...","evidence":{{"metric":"...","period":"...","value":0}}}}]}}"""


def build(metrics: dict) -> str:
    return _USER.format(metrics=json.dumps(metrics, ensure_ascii=False))
