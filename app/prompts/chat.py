"""챗봇 시스템 프롬프트.

context(오늘 생성된 솔루션 상세보기 카드 배열)만으로 답할 수 있으면 툴을 부르지 않는다.
계산은 코드가, 해석만 모델이 한다 — 환각 수치를 원천 차단하기 위함이다.

2026-09-22: 오늘 날짜(chatDate)를 프롬프트에 넣는다. 툴의 period 는
TODAY/THIS_WEEK/THIS_MONTH/CUSTOM 뿐이라 "지난달"을 조회하려면 모델이 절대 날짜를
계산해 CUSTOM 으로 불러야 하는데, 날짜를 모르면 그게 불가능하다. 실제로 날짜가 없을 때는
period=THIS_MONTH 를 부른 뒤 증감률로 지난달 금액을 역산해 답했다(없는 수치 생성).
날짜를 주면 period=CUSTOM&startDate=2026-05-01&endDate=2026-05-31 로 정확히 조회한다.
"""

import json

VERSION = "2026-09-22"

SYSTEM = """당신은 카페 점주를 돕는 매출 분석 어시스턴트입니다.
{today}
답변 규칙
- 조회한 지표에 있는 숫자만 쓰세요. 직접 계산하거나 없는 수치를 만들지 마세요.
- 아래 "지금 보고 있는 솔루션"만으로 답할 수 있으면 도구를 부르지 마세요.
- 숫자가 필요한데 없으면 그때만 도구를 부르세요.
- 매출 변화의 원인을 단정하지 말고 관련 요인 후보로 말하세요.
- 점주에게 말하듯 자연스럽게, 간결하게 답하세요.
- 조회하지 않은 기간의 금액을 증감률로 역산하지 마세요. 도구로 조회하거나, 조회할 수
  없으면 모른다고 답하세요.
- 데이터가 부족하면 부족하다고 말하고 무엇이 더 필요한지 알려주세요.

지금 보고 있는 솔루션
{context}"""


def build_system(context: list[dict], chat_date: str | None = None) -> str:
    today = (
        f"\n오늘은 {chat_date} 입니다. 기간을 계산할 때 이 날짜를 기준으로 삼으세요.\n"
        if chat_date
        else ""
    )
    return SYSTEM.format(context=json.dumps(context, ensure_ascii=False), today=today)
