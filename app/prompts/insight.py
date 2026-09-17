"""매출분석 화면의 "AI가 발견했어요" 영역에 쓸 관찰형 인사이트를 생성한다.

v2: docs/api정의서.md·docs/ERD정의서.md 확정 반영 (2026-09-16).
응답이 `insights` 문자열 배열로 단순화됐다(항목별 evidence 없음 — sales_ai_insights.insights 는
문자열 JSON 배열만 저장한다). 행동 처방은 하지 않고 관찰만 한다는 원칙은 v1과 동일.
"""

import json

VERSION = "v2"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
무엇을 하라는 제안은 하지 말고, 데이터에서 관찰되는 사실만 말하세요.
설명 없이 JSON만 출력하세요."""

_USER = """{metrics}

위 지표에서 점주가 알아두면 좋을 관찰 사실을 최대 {max_count}개 찾아주세요.
각 문장은 한 문장으로, 점주에게 말하듯 자연스럽게 쓰세요.

{{"insights":["...", "..."]}}"""


def build(metrics: dict, max_count: int) -> str:
    return _USER.format(metrics=json.dumps(metrics, ensure_ascii=False), max_count=max_count)
