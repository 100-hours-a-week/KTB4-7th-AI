"""프롬프트가 요구하는 규칙을 코드로 검사한다 — 로컬 모델·프롬프트 변경 평가용.

왜 있나. 지난 열흘간 잡은 결함이 전부 *그럴듯한데 틀린* 출력이었다.
`0.042 → "4% 증가"`, ratio 분모 착각, 같은 금액 반복, `WEEKDAY` 를 "금요일"로 바꿔 쓰기 —
전부 눈으로는 정상이라 사람이 20번 읽어도 못 찾는다. pytest 는 목(mock)을 쓰므로
끝까지 초록이고, curl 한 번은 한 표본이라 70% 성공률을 100%로 착각하게 만든다.

쓰는 법. 같은 요청을 N 회 호출해 통과율을 본다. 개별 항목이 95% 여도 곱하면 확 떨어지므로
**모든 항목을 동시에 통과한 비율**이 출하 판정 숫자다.

주의. 여기 규칙은 프롬프트를 그대로 옮긴 것이라 프롬프트가 바뀌면 같이 썩는다. 실제로
2026-10-01(PR #115)에 솔루션 프롬프트가 재설계되면서 이 파일의 이전 판이 **폐기된 규칙을
계속 재고 있었다** — `수치_evidence만`(수치는 evidence 에만)은 그때 반대 방향으로 뒤집혔고
`detail_2문장`은 세 문장으로 바뀌었는데, 채점기는 몰라서 "Claude 가 규칙을 60% 어긴다"는
틀린 결론을 냈다. 그래서 tests/test_grade.py 가 TARGET_* 와 프롬프트 VERSION 이 어긋나면
실패한다 — 프롬프트를 고치면 이 파일을 같이 보게 강제한다.
"""

import json
import re

# app 패키지를 import 하지 않는다. Colab 에 이 파일 하나만 복사해서 쓰려면 anthropic·openai·
# google-genai 까지 깔아야 하는 상황을 만들면 안 된다. 대신 app/clients/llm.py 의 strip_fence
# 를 그대로 옮겨 두고, 둘이 어긋나면 tests/test_grade.py 가 잡는다.
_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_fence(raw: str) -> str:
    """모델이 JSON 을 ```json 펜스로 감싸 내려주는 경우가 있어 벗긴다(서비스와 동일)."""
    match = _FENCE.match(raw.strip())
    return match.group(1) if match else raw


# 이 채점기가 대조한 프롬프트 판. 프롬프트 VERSION 이 올라가면 규칙을 다시 읽고 여기도 올린다.
# 2026-10-11 은 2회차(재시도) 프롬프트에 1회차 위반 피드백을 덧붙이는 변경이다 — 1회차
# 프롬프트와 기존 규칙 문장은 하나도 안 바뀌었다. 이 채점기는 모델 출력만 채점하므로
# 검사 항목은 손대지 않았다.
# 2026-10-08 은 규칙 문장을 하나도 바꾸지 않았다 — 고정 규칙과 지표의 순서만 바꿨고
# (접두 캐싱), 인사이트는 문장별 지표 배정이 추가됐다. 검사 항목은 손대지 않았다.
# 2026-10-07 은 입력 구조만 바뀌었고(카드별 근거 지표 배정) 카드 작성 규칙은 그대로라
# 검사 항목은 손대지 않았다. `카드_지표_중복없음` 이 100% 로 올라가는지 보는 게 이번 변경의
# 측정 목표다.
# 2026-10-14 는 weatherContext(네 번째 근거 축)가 들어오며 "날씨만으로 과거 매출과의
# 인과를 주장하지 말라"는 새 규칙이 추가됐다 — `날씨_인과_주장_없음`을 새로 잰다. 기존
# 항목은 손대지 않았다.
# 2026-10-15 는 DUPLICATE_FIGURE/VAGUE_ACTION에 더해 "현재 기간"처럼 날짜 없이 기간을
# 가리키는 말을 금지하는 규칙이 추가됐다(점주 신고) — `기간_날짜_명시`를 새로 잰다.
# 2026-10-15 는 districtBenchmark(여섯째 근거 축, #157)가 들어오며 "행정동 평균일 뿐
# 매장 개별 실적이 아니고, 상권 상태로 매출 인과를 주장하지 말라"는 규칙이 추가됐다 —
# `상권_인과_주장_없음`을 새로 잰다. 기존 항목은 손대지 않았다.
# 2026-10-21 은 districtBenchmark 중첩 객체를 전용 근거 축에서 빼고, 대신 평평한
# 필드(districtAvgMonthlySalesPerCafe·vsDistrictAvg·peakSalesHourBand·
# peakFootTrafficHourBand)로 쪼개 salesSummary·hourlySales 두 축에 조건부로
# 끼워 넣는 변경이다(#209). "숙주가 그 달 안 뽑힌 것"(정상)과 "뽑혔는데 상권 값을
# 안 쓴 것"(결함)을 분모가 다른 항목으로 나눠 잰다 —
# `salesSummary_선정률`·`hourlySales_선정률`(분모: 전체 요청)과
# `상권_평균매출_반영`·`상권_피크밴드_반영`(분모: 게이트 통과 + 해당 값이 문장에
# 인용된 요청만, 수치뿐 아니라 비교 방향까지 확인)을 새로 잰다. 기존 항목은
# 손대지 않았다.
# 2026-10-22 는 vsDistrictSalesPeak·vsDistrictFootTrafficPeak 를 dayType(평일/주말)
# 별로 쪼갠 변경이다(#209 최종 리뷰 Important #5, PR #219 머지 전 재검토) — 평일·
# 주말 피크가 다른 방향을 가리킬 수 있는데 이전엔 섞은 단일 피크로만 비교했다.
# `상권_피크밴드_반영`의 방향 판정이 dayType 별 두 비교값 중 어느 쪽이 맞는지
# 가린다 — 두 dayType 의 방향이 서로 다르면 본문만으로는 어느 쪽을 말하는지 구분
# 못 해 판정을 보류한다(아래 `_district_band_reflected` 참고). 밴드 인용 여부
# 검사(`_band_mentioned`)는 손대지 않았다.
# 2026-10-23 은 peakSalesHourBand·peakFootTrafficHourBand 가 SAME 이면(우리
# 매장 피크와 겹치면) 서비스가 그 밴드 자체를 안 보내도록 바뀐 변경이다
# (app/services/insight_focus.py::_apply_band). `상권_피크밴드_반영` 은
# "서비스가 실제로 줬을 밴드"만 언급을 요구하도록 고쳤다 — 전부 SAME 이라
# 안 준 밴드를 "안 언급했다"고 결함으로 오판하면 안 된다. 언급된 밴드는(줬을
# 밴드가 아니어도) 여전히 방향까지 확인한다 — `_band_mentioned`·
# `_band_direction_correct`는 손대지 않았다.
# 2026-10-24 는 SAME 서술 어휘를 "겹침"에서 "동일함"으로 바꾼 변경이다(사용자
# 요청). `_DIRECTION_WORDS["SAME"]`에 "동일" 패턴을 추가했다 — 안 더하면
# 모델이 "동일하다"로 답해도 방향 오류를 못 잡는다.
# 2026-10-24(2) 는 외부 리뷰로 "동일함"이 "포함됨"으로 다시 바뀐 변경이다 —
# `_DIRECTION_WORDS["SAME"]`에 "포함" 패턴을 추가했다. "동일" 패턴은 그대로 둔다.
# 2026-10-28 은 conditionPatterns(과거 강수일·무강수일 판매 차이)를 조건부로
# 서술하도록 허용한 변경이다(#246, PR #254).
#
# PR #254 는 "금지 문구는 기존 `_WEATHER_CAUSAL` 이 그대로 잡으므로 새 검사가
# 필요 없다" 고 적었는데, 재보니 **프롬프트가 적어 둔 금지 예시 세 개 중 하나만
# 걸렸다.** 매출어를 필수로 두고 있어서 "비가 와서 덜 팔렸습니다"(동사형)와
# "강수 영향으로 감소했습니다"(주어 생략)를 놓쳤고, 프롬프트 자신의 표현인
# "날씨가 매출 변화를 **일으켰다**" 와 "비가 판매 감소의 **원인**" 형태도
# 연결어 목록에 없어 빠졌다. 매출어를 선택으로 돌리고 인과 단정어를 더했다.
#
# 그리고 "conditionPatterns 가 없으면 과거 날씨별 판매 차이를 추측하지 마라" 는
# **새 규칙에는 검사가 아예 없었다.** 인과 연결어가 없어도 성립하는 서술이고
# ("비 오는 날에는 아이스 음료가 덜 팔립니다") 숫자가 없으면 접지 검사에도 안
# 걸린다. `과거날씨_판매_추측_없음` 을 새로 잰다 — conditionPatterns 가 근거로
# 들어온 카드에서만 허용한다.
#
# avgQuantity 가 두 자리라 `_ungrounded` 가 날조를 못 잡던 구멍은 PR #255 에서
# 수량 토큰을 자릿수 면제에서 빼면서 닫혔다.
#
# 2026-10-30 은 예시 문장의 "비 온 날" 을 "강수가 있었던 날" 로 고친 변경이다(PR #254
# 후속) — BE 의 RAIN 분류(precipitation_mm >= 1.0mm)가 적설의 수상당량도 포함해 비로
# 한정되지 않는다. 규칙·검사 대상은 그대로고 문구만 바뀌었다.
#
# 2026-10-31 은 weatherContext.alerts(기상청 특보 발효 현황)를 받은 변경이다(#226,
# PR #227). 특보명은 BE 가 완성 문자열로 주므로 그대로 인용하게 했다 — 규칙이 "주어진
# 문자열을 그대로" 라서 접지 검사가 그대로 잰다. 새 검사 항목은 추가하지 않았다.
TARGET_SOLUTION_VERSION = "2026-10-31"
TARGET_INSIGHT_VERSION = "2026-10-24"

# 문장에서 뽑아낼 숫자 (쉼표 제거 후 비교한다)
_ANYNUM = re.compile(r"\d[\d,]*\.?\d*")
# "3만원", "1억2천만원" 처럼 만/억 단위로 줄여 쓴 금액 — 프롬프트가 금지한다.
# app/services/solution.py 의 _ROUNDED_AMOUNT 와 같은 패턴이다(tests 가 대조한다).
_ROUNDED = re.compile(r"\d[\d,]*\s*[억만][\d\s억만천백]*원")
# 12시간제 표기 — 프롬프트는 지표에 있는 24시간제를 그대로 쓰라고 한다
# 서비스의 app/services/solution.py::_WORDS 와 같은 접두어를 봐야 한다. 2026-10-08 측정에서
# `시각_24시간제` 77.8% 가 전부 오탐이었다 — "오후 2시간 동안" 은 지속시간인데 `(?!간)` 이
# 없어서 12 시간제로 셌고, 반대로 "낮"·"아침" 은 아예 안 봐서 치환 버그를 못 잡았다.
_AMPM = re.compile(r"(오전|오후|새벽|아침|낮|저녁|밤)\s*\d{1,2}\s*시(?!간)")
# 배율은 직접 계산하지 말라고 되어 있다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다.
_RATIO_WORD = re.compile(
    r"(?:\d+(?:\.\d+)?|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배(?![달치송포분])"
    r"|\d+\s*분의\s*\d+"
)
# 화면에 보여줄 금액·비율. 실행 지시용 작은 수(21시, 1명)와 구분하려고 자릿수·단위를 본다.
_DISPLAY_NUM = re.compile(r"[\d,]{4,}\s*원|\d+\.?\d*\s*%")

# 백분율 토큰 전체(숫자+%)를 끊어서 뽑는다. 생문자열 substring 대조("2%" in "1.2%")는
# "1.2%"(카테고리 증감률 같은 무관한 값)의 끝 두 글자가 "2%"(salesSummary 반올림값)와
# 겹쳐 오탐한다(2026-10-22 실측에서 재현, PR #219) — 토큰 단위로 끊어야 한다.
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")

# 수량 단위가 붙은 숫자. 백분율과 같은 이유로 자릿수 면제에서 뺀다 — "비 온 날에는
# 12잔 팔렸습니다" 는 실행 지시가 아니라 **사실 주장**이고, 수량은 거의 항상 두 자리다.
#
# 단위는 **지표에 그 차원이 실재하는 것만** 넣는다 — 잔·개는 `quantity`·`avgQuantity`·
# `baselineAvgQuantity`, 건은 주문 건수다. 접지 검사는 맞으면 통과하고 틀리면 걸려야
# 의미가 있는데, 지표에 없는 차원(`명`·`kg`·`리터`)은 **무조건 미접지**가 되어 검사가
# 아니라 금지가 된다. 그 영역은 `_FABRICATED_AMOUNT` 가 이미 잡으므로, 여기서 또 잡으면
# 한 결함이 두 항목을 깎아 측정이 흐려진다.
#
# 자릿수 그룹(쉼표)도 _ANYNUM 과 같이 받는다 — 그래야 _numbers_in() 이 "1,234" 에서
# 뽑는 토큰("1234")과 여기서 뽑는 토큰이 같아진다. 다르면 쉼표 낀 수량이 검사를 비껴간다
# (2026-10-30 리뷰, #255). 단 이건 토큰 일치를 맞추는 것일 뿐, "1,5잔" 같은 비정상
# 쉼표 표기 자체를 틀렸다고 잡아주지는 않는다 — 정규화하면 "15" 가 되어 버려서, 지표에
# 실제로 15가 있으면 그대로 통과한다. 쉼표 형식 자체의 정합성은 이번 변경의 범위 밖이다.
_QUANTITY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:잔|개|건)(?![수당])")

# 행동의 "얼마나" — 지표에 없는 값이라 지어낸 것이다. 마진을 모르는데 할인율을,
# 인건비 대비 생산성을 모르는데 인원을 말할 근거가 없다(2026-10-07). 시각은 지표에
# hour 로 있으므로 _ungrounded 가 따로 본다.
_FABRICATED_AMOUNT = re.compile(
    r"\d+\s*%\s*(?:할인|세일|디스카운트|인하)"
    r"|(?:직원|인력|스태프|알바|인원)[을를]?\s*\d+\s*명"
    r"|\d+\s*명\s*(?:추가|배치|더|이상)"
    r"|\d+\s*(?:kg|키로|g|그램|잔|개|병|박스|리터)\s*[을를]?\s*(?:준비|발주|주문|구비|입고)"
)
# 누구나 할 수 있는 말. 점주가 오늘 무엇을 다르게 할지가 안 나온다.
_VAGUE_ACTION = re.compile(
    # 사이에 다른 말이 끼어도 잡는다. 붙어 있을 때만 보던 옛 패턴은 "프로모션과 추천
    # 강화로" 를 놓쳤고, 실측 218 개 실행 문장에서 **0 개**를 잡았다(2026-10-16) —
    # 교과서 문구만 걸려서 `공허한_조언_없음` 100% 가 아무 의미가 없었다.
    r"(?:마케팅|홍보|프로모션|캠페인|전략|활동|노력|서비스)[^.。\n]{0,10}?"
    r"(?:강화|개선|변경|확대|진행|실행|집중)"
    # 대상이 구체적이어도 "강도만 올려라" 는 점주가 오늘 뭘 다르게 할지 알 수 없다.
    # 진행·실행·집중은 여기 안 넣는다 — "인력을 집중 배치" 같은 구체적 행위가 걸린다.
    r"|(?:추천|이벤트|관리|메뉴|매출|비중|고객층|경험)[^.。\n]{0,10}?"
    r"(?:강화|개선|활성화|제고|증대|도모|최적화|극대화)"
)
# 날짜 없이 기간을 가리키는 말. app/services/solution.py::_VAGUE_PERIOD 와 같은 패턴.
_VAGUE_PERIOD = re.compile(r"(?:현재|이번|해당|지금)\s*기간")
# weatherContext 는 오늘 예보 스냅샷이라 과거 매출과의 인과를 뒷받침할 지표가 없다
# (2026-10-14). "비가 와서/때문에 매출이 줄었다" 식 주장을 잡는다.
#
# 2026-10-28: 옛 패턴은 주석이 말하는 것의 **절반만** 잡고, 잡아서는 안 되는 것을 잡았다.
# `(?:와서|내려서|오는 바람에)?` 가 선택이고 `(?:때문에|탓에|...)` 가 필수여서:
#
#   안 걸림  비가 와서 매출이 줄었습니다      ← 주석이 잡는다고 적어둔 문장
#   안 걸림  비가 내려서 손님이 줄었습니다
#   걸림     비 때문에 우산 거치대를 내놓으세요  ← 오늘 예보 기반 준비. 프롬프트가 허용한다
#
# 결과를 같이 보게 바꿨다. 막아야 하는 건 "날씨 → 과거 매출 변화" 주장 하나이고, 오늘
# 예보에 맞춰 무엇을 준비하라는 문장은 프롬프트가 명시적으로 허용한다. 어순이 뒤집힌
# "매출이 비 때문에 줄었다" 도 같이 본다.
# 한글은 단어 경계가 없다 — `비` 를 그냥 두면 **대비·준비·소비** 안에서 걸린다.
# 실측에서 "이전 기간 대비 매출 감소 원인을 분석하세요" 가 날씨 인과로 잡혔다(84 건 중 6).
# 앞 글자가 한글이면 날씨어가 아니다.
_WEATHER_WORD = r"(?<![가-힣])(?:날씨|기온|강수|더위|추위|비|눈)[가이은는]?\s*"
# 인과 단정 분기용. 주격 조사를 **필수**로 둔다 — "눈에 띄게" 의 `눈` 을 빼려면 조사까지
# 봐야 한다("강수 자체가" 는 허용).
_WEATHER_SUBJ = r"(?<![가-힣])(?:날씨|기온|강수|더위|추위|비|눈)(?:\s*자체)?[가이]\s*"
_WEATHER_LINK = (
    r"(?:와서|내려서|오는\s*바람에|때문에|탓에|영향으로|영향을\s*받아|영향을\s*줘서"
    r"|떨어져서|떨어지면서|올라서|오르면서|낮아서|높아서|추워서|더워서)"
)
# 인과를 **명사·동사로 단정**하는 형태. 연결어와 달리 결과를 따로 요구하지 않는다 —
# 이 말들은 평범한 준비 문장에 나오지 않는다("비 때문에 우산을 내놓으세요" 와 달리
# "비가 원인입니다" 는 그 자체가 인과 주장이다).
_WEATHER_BLAME = r"(?:원인|초래|일으켰|일으켜|일으킨|기인)"
_SALES_WORD = r"(?:매출|판매|손님|고객|방문|객수|주문)"
_PAST_CHANGE = r"(?:줄었|늘었|감소|증가|떨어졌|올랐|하락|상승|빠졌|덜\s*팔|더\s*팔|팔렸|팔린)"
_WEATHER_CAUSAL = re.compile(
    # 날씨 + 인과연결 + (매출어는 있어도 없어도 된다) + 과거 변화
    # 매출어를 필수로 두면 "강수 영향으로 감소했습니다"(주어 생략)·"비가 와서 덜
    # 팔렸습니다"(동사형)를 놓친다 — 둘 다 프롬프트가 금지 예시로 적어 둔 문장이다.
    _WEATHER_WORD
    + _WEATHER_LINK
    + r"[^.。\n]{0,30}?"
    + _PAST_CHANGE
    # 어순 역전 — "매출이 비 때문에 줄었다"
    + r"|"
    + _SALES_WORD
    + r"[^.。\n]{0,15}?"
    + _WEATHER_WORD
    + _WEATHER_LINK
    + r"[^.。\n]{0,15}?"
    + _PAST_CHANGE
    # 명사·동사로 단정 — "비가 판매 감소의 원인입니다", "날씨가 매출 변화를 일으켰습니다".
    # 연결어가 없는 분기라 범위를 좁힌다 — 주격 조사와 매출어를 둘 다 요구한다.
    # 안 좁히면 "매출 감소 원인을 분석하세요"(날씨와 무관)가 통째로 걸린다.
    + r"|"
    + _WEATHER_SUBJ
    + r"[^.。\n]{0,20}?"
    + _SALES_WORD
    + r"[^.。\n]{0,12}?"
    + _WEATHER_BLAME
)

# conditionPatterns 가 **없을 때** 과거 날씨별 판매 차이를 서술하면 근거가 없다
# (2026-10-28, PR #254: "conditionPatterns가 없으면 과거 날씨별 판매 차이를 추측하지
# 말고, 오늘 예보와 정성적인 준비만 설명하세요"). 인과 연결어가 없어도 성립하는
# 서술이라 _WEATHER_CAUSAL 로는 안 걸린다 — 숫자도 없으면 접지 검사에도 안 걸린다.
_WEATHER_DAY = r"(?:비\s*(?:온|오는|내린|내리는)|강수일|무강수|우천)"
_SOLD = (
    r"(?:팔렸|팔린|팔립|팔리|판매(?:됐|되었|된|됩)"
    r"|(?:매출|주문|객수|손님)[이가]?\s*(?:적었|많았|줄었|늘었))"
)
_PAST_WEATHER_SALES = re.compile(_WEATHER_DAY + r"[^.。\n]{0,30}?" + _SOLD)
# districtBenchmark 는 행정동 평균 추정치일 뿐 매장 개별 실적이 아니다(2026-10-15, #157).
# "상권이 좋아서/나빠서 매출이 ~했다" 식 인과 주장을 잡는다.
_DISTRICT_CAUSAL = re.compile(
    r"(?:상권|행정동|주변\s*(?:카페|업소))[이가]?\s*(?:좋아서|나빠서|활발해서|침체돼서|때문에|탓에|영향으로|영향을\s*받아)"
)

# app/services/insight_focus.py::_district_gate 와 같은 로직이어야 한다 — app 을
# import 하지 않으려고 복사해 둔 값이다(둘이 어긋나면 tests/test_grade.py 가 잡는다).
_MIN_CAFE_STORE_COUNT = 3


def _district_gate(district: dict | None) -> bool:
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0


# app/services/insight_focus.py::_band_gate 와 같은 로직이어야 한다. 포맷이
# 안 맞으면 _band_mentioned 의 tuple unpacking(band.split("-"))이나 _in_band
# 의 int() 변환이 터진다 — _district_band_reflected 전용으로, salesSummary
# 쪽(_district_avg_reflected)은 밴드를 안 써서 이 게이트가 필요 없다(#209
# 최종 리뷰 Important #4).
_HOUR_BAND = re.compile(r"^\d{1,2}-\d{1,2}$")


def _band_gate(district: dict | None) -> bool:
    if not district:
        return False
    return bool(
        _HOUR_BAND.fullmatch(district.get("peakSalesHourBand") or "")
        and _HOUR_BAND.fullmatch(district.get("peakFootTrafficHourBand") or "")
    )


# app/services/insight_focus.py::district_comparison 과 같은 로직이어야 한다.
def _comparison(total_sales: int, district_avg: int) -> str:
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


# app/services/insight_focus.py::_DAY_TYPES 와 같은 값이어야 한다.
_DAY_TYPES = ("WEEKDAY", "WEEKEND")


# app/services/insight_focus.py::_store_peak_hour·_in_band 와 같은 로직이어야 한다.
def _store_peak_hour(points: list[dict], day_type: str) -> int | None:
    selling = [p for p in points if p.get("dayType") == day_type and (p.get("menuSales") or 0) > 0]
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int, band: str) -> bool:
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end


# app/services/insight_focus.py::_band_included 와 같은 로직이어야 한다 —
# 어긋나면 한쪽은 밴드를 줬는데 다른 쪽은 "안 언급했다"고 결함(False)으로
# 오판한다.
def _band_expected(points: list[dict], band: str) -> bool:
    comparisons = [
        _in_band(h, band)
        for h in (_store_peak_hour(points, dt) for dt in _DAY_TYPES)
        if h is not None
    ]
    return not comparisons or not all(comparisons)


def _axis_selected(body: str, metrics: dict, key: str) -> bool:
    """그 축이 생성 문장에 실제로 쓰였는지 — assign() 선정 여부의 근사치.

    assign() 의 6 축 점수식을 복제하지 않는다(여긴 app 을 import 하지 않는다는
    전제라 과하다, 모듈 머리말 참고) — 대신 "이 축 숫자가 문장에 등장했는지"로
    선정 여부를 근사한다. _metric_paths/_evidence_group 과 같은 방식이다.

    인덱스는 지표 전체로 만든다. 그 축만으로 만들면 _evidence_group 의 모호성
    필터("여러 지표에 걸치는 숫자는 판단에 쓰지 않는다")가 꺼져서, 다른 축과 값이
    겹치는 숫자(실측: salesSummary.orderCount 923 == menuRankings[].quantity 923)
    하나로 숙주가 선정된 것처럼 오판한다 — 그러면 상권_평균매출_반영이 None 이어야
    할 요청에서 거짓 결함으로 집계된다(#209 최종 리뷰 Important #3).
    """
    if not metrics.get(key):
        return False
    return key in _evidence_group(body, _metric_paths(metrics))


# 완전 활용형이 아니라 정규식으로 둔다(#209 최종 리뷰 deferred #6) — 프롬프트는
# "겹침"/"안 겹침" 어간형으로 가르치는데 "겹칩니다"만 찾으면 "겹치는 시간대입니다"
# 같은 변형의 반전을 못 잡는다. 그런데 "겹치"를 그냥 어간으로 쓰면 DIFFERENT의
# 정답 문구 "겹치지 않습니다"에도 포함돼 있어 SAME으로 오매칭된다 — 부정 접미
# "지 않"이 뒤따르면 SAME이 아니라고 미리 걸러낸다(음성 lookahead). "일치"도
# DIFFERENT의 "불일치"에 포함되므로 같은 이유로 "불" 접두를 제외한다.
# 2026-10-24: 프롬프트가 SAME을 "겹침" 대신 "동일함"으로 가르치도록 바뀌어서
# "동일" 패턴을 추가했다 — "동일하지 않습니다"(DIFFERENT의 정답 문구일 수
# 있다)는 겹치/일치와 같은 이유로 부정 접미를 lookahead로 제외한다.
# 2026-10-24(2): "동일함"도 글자 그대로 같은 값이라는 뜻으로 읽혀 부정확하다는
# 외부 리뷰를 받아, 프롬프트는 "포함됨"으로 다시 바뀌었다 — "포함" 패턴을
# 추가한다(같은 이유로 "포함되지 않"/"포함하지 않" 부정형은 lookahead로 제외).
# "동일" 패턴은 프롬프트가 더는 안 가르쳐도, 모델이 그렇게 말할 가능성에
# 대비해 지우지 않고 그대로 둔다.
_DIRECTION_WORDS = {
    "ABOVE": (re.compile("높"), re.compile("웃돌"), re.compile("상회")),
    "BELOW": (re.compile("낮"), re.compile("밑돌"), re.compile("하회")),
    "EQUAL": (re.compile("같습니다"), re.compile("동일")),
    "SAME": (
        re.compile(r"겹치(?!지\s*않)"),
        re.compile(r"(?<!불)일치"),
        re.compile(r"동일(?!하지\s*않)"),
        re.compile(r"포함(?!되지\s*않|하지\s*않)"),
    ),
    "DIFFERENT": (re.compile(r"겹치지\s*않"), re.compile(r"다른\s*시간대"), re.compile("불일치")),
}
_OPPOSITE = {
    "ABOVE": "BELOW",
    "BELOW": "ABOVE",
    "EQUAL": None,
    "SAME": "DIFFERENT",
    "DIFFERENT": "SAME",
}


# "9,413,000" 같은 천 단위 구분 쉼표는 절 경계가 아니라 숫자의 일부다 — 그대로
# "[,.\n]" 로 나누면 절마다 숫자가 조각나 anchor(예: "9413000")가 어느 절에도
# 통째로 안 남는다(#209 리뷰 Important #1 수정 중 실측으로 발견).
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _split_clauses(body: str) -> list[str]:
    return re.split(r"[,.\n]", _THOUSANDS_COMMA.sub("", body))


def _direction_correct(body: str, comparison: str, anchor: str) -> bool:
    """방향 어휘가 실제 계산 결과와 반대로 쓰였는지만 본다 — 간단한 어휘 대조다
    (완전한 자연어 이해는 아니다, 1 차는 검출 시도 수준). 올바른 어휘가 없어도
    (수치만 언급) 통과시킨다 — 의견 없는 문장을 결함으로 몰지 않는다. 반대
    방향 어휘가 있을 때만 실패시킨다(설계 'C').

    anchor 가 들어간 구(쉼표·마침표로 나눈 절)에서만 반대 방향 어휘를 찾는다.
    anchor 는 숫자 토큰으로 대조한다 — 생문자열 substring 으로 찾으면 주문
    "114건" 이 든 절에서 밴드 anchor "11" 이 걸려 오판한다(#209 최종 리뷰
    deferred #4). _band_mentioned 가 쓰는 _numbers_in 과 같은 방식이다.
    본문 전체를 보면 anchor 와 무관한 문장의 반대 어휘에도 오염된다 — 처음엔
    이 함수가 본문 전체를 봤는데, "총 매출은... 상권 평균보다 높습니다, 토요일
    매출이... 가장 낮습니다" 처럼 상권과 무관한 문장의 "낮습니다"가 ABOVE 판정을
    반대로 오판하는 사고가 실제로 났다(#209 리뷰 Important #1). 밴드 두 개가
    한 문장에 같이 있을 때 서로의 반대 어휘에 오염되는 것과 같은 실패 모양이라
    평균 쪽에도 똑같이 절 단위 스캔을 적용한다.

    SAME 어간("겹치")은 DIFFERENT 의 정답 문구("겹치지 않습니다")에도 포함돼
    단순 substring 대조로는 구분이 안 된다 — _DIRECTION_WORDS 쪽에서 부정
    접미("지 않")가 뒤따르면 SAME 이 아니라고 정규식으로 미리 걸러낸다(#209
    최종 리뷰 deferred #6, "일치"/"불일치"도 같은 이유).
    """
    opposite = _OPPOSITE[comparison]
    if not opposite:
        return True
    for clause in _split_clauses(body):
        if anchor in _numbers_in(clause) and any(
            pattern.search(clause) for pattern in _DIRECTION_WORDS[opposite]
        ):
            return False
    return True


def _district_avg_reflected(body: str, metrics: dict) -> bool | None:
    """게이트를 통과하고 salesSummary 가 실제로 선정됐을 때만 유효한 측정이다(#209 "A").

    둘 중 하나라도 아니면 None — "선정 안 됨"은 결함이 아니다. devtools/bench.py
    가 None 을 분모에서 뺀다(설계 리뷰 — 안 빼면 실제보다 낮게 보인다). 값이
    보여도 방향이 반대면 실패로 센다(설계 'C') — anchor 는 상권 평균 숫자다.
    """
    district = metrics.get("districtBenchmark")
    if not _district_gate(district):
        return None
    if not _axis_selected(body, metrics, "salesSummary"):
        return None
    avg = str(district["districtAvgMonthlySalesPerCafe"])
    if avg not in _numbers_in(body):
        return False
    summary = metrics.get("salesSummary") or {}
    comparison = _comparison(
        summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"]
    )
    return _direction_correct(body, comparison, avg)


# "2026Q3"·"2026년 3분기" 두 표기 다 잡는다. basisQuarter 는 focus 블록에 안 보내기로
# 했지만(#209), _metric_numbers 가 문자열에서 3자리 이상을 뽑아 "2026" 이 이미 허용
# 집합에 있어 UNGROUNDED_NUMBER 로는 못 잡는다 — 모델이 어디선가 주워 인용해도 통과한다.
_QUARTER_MENTION = re.compile(r"(\d{4})\s*(?:Q([1-4])|년\s*([1-4])\s*분기)")


def _quarter_leak(body: str, metrics: dict) -> bool | None:
    """분기를 인용했으면 그 값이 실제 basisQuarter 와 같은지. 인용 안 했으면 None."""
    match = _QUARTER_MENTION.search(body)
    if not match:
        return None
    quarter = match.group(2) or match.group(3)
    cited = f"{match.group(1)}Q{quarter}"
    real = (metrics.get("districtBenchmark") or {}).get("basisQuarter")
    return cited == real


def _band_mentioned(body: str, band: str) -> bool:
    start, end = band.split("-")
    numbers = _numbers_in(body)
    return start in numbers and end in numbers


def _band_direction_correct(body: str, comparisons: set[str], band: str, other_band: str) -> bool:
    """밴드 쪽 호출부 — anchor 로 두 밴드의 배타적 숫자(대칭차)를 쓴다.

    매출·유동인구 두 비교가 한 문장에 같이 있어 서로의 반대 어휘에 오염되지 않게
    절 단위로 좁히는데(`_direction_correct` 참고), 밴드 시작 시각을 anchor 로 쓰면
    그 좁히기가 안 된다 — 서울 상권 밴드는 연속 버킷이라 인접 밴드가 경계 숫자를
    공유하는 게 기본값이다("11-14" 의 끝과 "14-17" 의 시작이 같은 "14"). 실측:
    "유동인구 피크 11-14시와 겹칩니다. 매출 피크 14-17시와는 겹치지 않습니다" 가
    완전히 올바른데, 매출 밴드 anchor "14" 가 첫 절에도 걸려 결함으로 셌다
    (#209 최종 리뷰 Important #1). 공유 숫자를 뺀 숫자로만 절을 고른다 — 두 밴드가
    완전히 같으면 배타적 숫자가 없고, 그때는 비교 자체가 무의미해 검사를 건너뛴다.

    comparisons 는 dayType(평일/주말) 별로 계산된 비교값의 집합이다(2026-10-22,
    #209 최종 리뷰 Important #5) — 평일·주말 피크가 다른 방향을 가리키면 두 값이
    섞여 들어온다. 이때 본문만으로는 모델이 어느 dayType 을 말하는지 구분할 수
    없어, 어느 방향 어휘든 "그 dayType 기준으로는 맞을 수 있다"고 보고 검사를
    건너뛴다 — 없는 근거로 결함을 만들지 않는다(`_direction_correct` 와 같은 원칙).
    """
    exclusive = set(band.split("-")) - set(other_band.split("-"))
    if not exclusive or len(comparisons) != 1:
        return True
    (comparison,) = comparisons
    return all(_direction_correct(body, comparison, anchor) for anchor in exclusive)


def _district_band_reflected(body: str, metrics: dict) -> bool | None:
    """게이트를 통과하고, hourlySales 가 선정됐을 때만 유효한 측정이다.

    2026-10-23 부터 두 밴드는 독립적으로 포함 여부가 갈린다(app/services/
    insight_focus.py::_apply_band 참고) — 전부 SAME 이라 서비스가 애초에
    안 줬을 밴드를 "안 언급했다"고 반영 실패로 오판하면 안 된다. `_band_expected`
    로 그 판단을 복제해, **포함됐어야 할 밴드만** 언급을 요구한다. 언급된
    밴드는(포함 예정 여부와 무관하게) 방향까지 `_band_direction_correct` 로
    확인한다 — DIFFERENT라서 줬는데 모델이 방향을 틀리거나 안 언급하면 여전히
    결함이다.

    선정 판정(최종 리뷰, 2026-10-24 Important #1): 예전엔 "두 밴드 숫자 중
    하나도 안 보이면 hourlySales 가 선정 안 된 것"으로 봤는데, 이 전제가
    깨졌다 — 두 밴드가 둘 다 DIFFERENT라 서비스가 둘 다 줬는데 모델이 둘 다
    빠뜨린 경우도 똑같이 "밴드가 안 보임"이라 None(측정 대상 아님)으로
    새면서, 가장 심한 누락이 반영률 분모에서 빠졌다. `_district_avg_reflected`
    가 이미 쓰는 `_axis_selected`(그 축 자체의 숫자가 문장에 있는지)를 OR로
    더해 판정한다 — 밴드 숫자가 안 보여도 축 자체가 선정된 걸 알면 그때는
    "선정 안 됨"이 아니라 진짜 누락(False)이다. 밴드 숫자만으로도 선정이
    맞다(기존 경로 유지) — 피크를 못 구해 상권 밴드만 언급하는 문장(비교
    필드가 없는 경우, 2026-10-21(5))은 `_axis_selected`가 False여도 여전히
    선정으로 잡아야 하기 때문이다.
    """
    district = metrics.get("districtBenchmark")
    if not _district_gate(district) or not _band_gate(district):
        return None
    sales_band = district["peakSalesHourBand"]
    traffic_band = district["peakFootTrafficHourBand"]
    sales_mentioned = _band_mentioned(body, sales_band)
    traffic_mentioned = _band_mentioned(body, traffic_band)
    if not (sales_mentioned or traffic_mentioned or _axis_selected(body, metrics, "hourlySales")):
        return None  # 이번엔 hourlySales 가 선정 안 된 것으로 본다

    hourly = metrics.get("hourlySales") or []
    if _band_expected(hourly, sales_band) and not sales_mentioned:
        return False
    if _band_expected(hourly, traffic_band) and not traffic_mentioned:
        return False

    peak_hours = [h for h in (_store_peak_hour(hourly, dt) for dt in _DAY_TYPES) if h is not None]
    if not peak_hours:
        return True
    ok = True
    if sales_mentioned:
        sales_comparisons = {
            ("SAME" if _in_band(h, sales_band) else "DIFFERENT") for h in peak_hours
        }
        ok = ok and _band_direction_correct(body, sales_comparisons, sales_band, traffic_band)
    if traffic_mentioned:
        traffic_comparisons = {
            ("SAME" if _in_band(h, traffic_band) else "DIFFERENT") for h in peak_hours
        }
        ok = ok and _band_direction_correct(body, traffic_comparisons, traffic_band, sales_band)
    return ok


# weekdaySales[].dayOfWeek 표기가 영문 전체 이름("SATURDAY")인지 세글자 약어
# ("SAT", app/services/solution.py::_WEEKDAY_CODES 와 같은 표기)인지 계약상
# 고정돼 있지 않다 — devtools/contract_check.py 예시는 전체 이름을 쓰지만
# devtools/bench.py 인사이트 케이스는 약어를 쓴다. 약어 키가 없으면 "SAT" 가
# 전혀 매칭이 안 돼 허용 목록이 비고, AI 가 데이터 그대로 "토요일"이라고 정확히
# 써도 환각으로 오판한다(2026-10-22 실측에서 재현, PR #219) — 둘 다 받는다.
_DOW_KO = {
    "MONDAY": "월요일",
    "MON": "월요일",
    "TUESDAY": "화요일",
    "TUE": "화요일",
    "WEDNESDAY": "수요일",
    "WED": "수요일",
    "THURSDAY": "목요일",
    "THU": "목요일",
    "FRIDAY": "금요일",
    "FRI": "금요일",
    "SATURDAY": "토요일",
    "SAT": "토요일",
    "SUNDAY": "일요일",
    "SUN": "일요일",
}


# 배율은 "지표에 있으면 인용, 없으면 날조" 다(2026-10-16). 서비스가
# app/services/solution_focus.py::derive 로 hourlyPeakRatio 를 넣어 주고, 러너는 채점 전에
# 같은 함수를 부른다 — 안 부르면 지표에 있는 배율을 날조로 센다.
# _metric_numbers 전체를 쓰지 않는 이유: hour 값(14·18)이 섞여 "14배" 가 통과한다.
# app/services/solution.py 의 같은 이름 함수들과 로직이 같아야 한다.
_RATIO_KEYS = ("hourlyPeakRatio",)
_KO_NUMERALS = {
    "두": "2",
    "세": "3",
    "네": "4",
    "다섯": "5",
    "여섯": "6",
    "일곱": "7",
    "여덟": "8",
    "아홉": "9",
    "열": "10",
}


def _allowed_ratios(metrics) -> set[str]:
    out: set[str] = set()
    for key in _RATIO_KEYS:
        for item in metrics.get(key) or []:
            value = item.get("ratio") if isinstance(item, dict) else item
            if isinstance(value, int | float) and not isinstance(value, bool):
                out.add(f"{float(value):g}")
    return out


def _ratio_value(text: str) -> str | None:
    head = text.split("배")[0].strip()
    if head in _KO_NUMERALS:
        return _KO_NUMERALS[head]
    try:
        return f"{float(head):g}"
    except ValueError:
        return None


def _ungrounded_ratios(texts, metrics) -> bool:
    allowed = _allowed_ratios(metrics)
    for text in texts:
        for match in _RATIO_WORD.finditer(text):
            value = _ratio_value(match.group())
            if value is None or value not in allowed:
                return True
    return False


def _metric_numbers(metrics) -> set[str]:
    """지표에 실제로 있는 값들. 금액은 그대로, 비율은 백분율로도 인정한다.

    2026-10-16(PR #161 리뷰, 헥터): 문자열 값은 숫자를 통째로 버리고 있었다.
    `basisQuarter: "2026Q3"`·`salesTrend[].date: "2026-09-12"` 같은 값의 "2026"을 모델이
    그대로 인용해도 허용 집합에 없어 환각(`수치_정확` 실패)으로 오판했다 — 프롬프트가
    인용을 금지하지 않는 값인데 채점기가 막고 있었다. 3자리 미만은 뽑지 않는다 — 2자리
    이하는 `_ungrounded`가 이미 "실행 지시"로 봐주므로 필요가 없고, 그대로 다 뽑으면
    `basisDateTime: "2026-10-07 11:00"`의 "10"이 "10% 할인" 같은 진짜 실행 지시 숫자와
    충돌해 `_metric_figures`(필드간 중복 검사)가 오탐한다(실측: 기존 테스트가 깨짐).
    """
    out: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.add(str(value))
        elif isinstance(value, float):
            out.add(f"{value:g}")
            out.add(f"{abs(value) * 100:g}")  # 0.417 → 41.7
            out.add(f"{round(abs(value) * 100):g}")  # 0.12  → 12
        elif isinstance(value, str):
            out.update(
                m.group() for m in _ANYNUM.finditer(value) if len(m.group().split(".")[0]) >= 3
            )

    walk(metrics)
    return out


def _numbers_in(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _ANYNUM.finditer(text)}


# 수량 접지는 이 차원의 필드에서만 받는다 — _metric_numbers 전체를 쓰면 hour·rank·연도
# 같은 무관한 숫자가 우연히 일치해도 통과한다. hourlyPeakRatio 전용 _allowed_ratios 와
# 같은 이유(504~506줄 참고).
_QUANTITY_KEYS = ("quantity", "avgQuantity", "baselineAvgQuantity", "orderCount")


def _quantity_numbers(metrics) -> set[str]:
    out: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in _QUANTITY_KEYS and isinstance(item, int) and not isinstance(item, bool):
                    out.add(str(item))
                elif key in _QUANTITY_KEYS and isinstance(item, float):
                    out.add(f"{item:g}")
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(metrics)
    return out


# 지표 비율을 백분율로 적을 때 한 자리까지 반올림하는 건 환각이 아니다 — 프롬프트가
# 0.0885 → 8.85% 로 바꿔 쓰라고 하고, _metric_numbers 가 정수 반올림("9")까지는 이미
# 허용 집합에 넣는다. 한 자리("8.9")가 비면 반올림을 날조로 오판한다.
_PERCENT_ROUNDING_TOLERANCE = 0.05 + 1e-9


def _percent_grounded(token: str, metrics) -> bool:
    """ "40%" 의 40 이 지표 비율에서 나온 값인가. 반올림 오차만 허용한다."""
    try:
        value = float(token)
    except ValueError:
        return True
    for allowed in _metric_numbers(metrics):
        try:
            if abs(value - float(allowed)) <= _PERCENT_ROUNDING_TOLERANCE:
                return True
        except ValueError:
            continue
    return False


def _ungrounded(text: str, metrics) -> set[str]:
    """지표에 없는 숫자. 자릿수 오류·환각을 잡는다.

    한두 자리는 시각·인원 같은 실행 지시로 보고 통과시킨다 — 시각은 지표에 hour 로
    들어 있고, 인원·수량·할인율은 `_FABRICATED_AMOUNT` 가 따로 잡는다.

    **백분율은 자릿수 면제를 받지 않는다**(2026-10-28). 비율 주장은 실행 지시가 아니라
    사실 주장인데, 거의 항상 두 자리라 검사에서 통째로 빠져 있었다 — 지표에 40% 하나만
    있는 입력에서 "77%"·"99%" 가 그대로 통과했다. 이 구멍은 conditionPatterns(강수별
    메뉴 판매, #246)에서 특히 아프다. 그 축의 가치가 전부 "N% 덜 팔렸다" 이고 N 은
    두 자리다 — 모델이 40% 를 77% 로 바꿔 써도 못 잡고 있었다.
    **수량도 같은 이유로 면제에서 뺀다**(2026-10-28). `conditionPatterns` 를 축에 연결하면서
    (#246) `avgQuantity`·`baselineAvgQuantity` 가 카드 근거로 들어오는데, 잔 수는 거의 항상
    두 자리라 "비 온 날 12잔" 을 "15잔" 으로 바꿔 써도 통과했다. 백분율(#248)과 같은 구멍의
    다른 쪽이다.

    수량은 `_metric_numbers`(지표 전체)가 아니라 `_quantity_numbers`(수량 차원만)로
    접지한다(2026-10-30 리뷰, #255) — `allowed`를 먼저 보면 수량 숫자가 hour·rank 같은
    무관한 지표 숫자와 우연히 같아도 통과해 버린다.
    """
    allowed = _metric_numbers(metrics)
    quantity_allowed = _quantity_numbers(metrics)
    percents = {m.group(1) for m in _PERCENT.finditer(text)}
    quantities = {m.group(1).replace(",", "").rstrip(".") for m in _QUANTITY.finditer(text)}
    bad = set()
    for number in _numbers_in(text):
        if number in quantities:
            # allowed(지표 전체)를 먼저 보면 hour·rank 같은 무관한 숫자와 우연히
            # 일치해도 통과한다 — 수량 전용 집합으로만 판정한다.
            if number in quantity_allowed:
                continue
            try:  # 12.0 == 12 같은 표기 차이는 허용
                if any(abs(float(number) - float(a)) < 1e-9 for a in quantity_allowed):
                    continue
            except ValueError:
                pass
            bad.add(number)
            continue
        if number in allowed:
            continue
        try:  # 12.0 == 12 같은 표기 차이는 허용
            if any(abs(float(number) - float(a)) < 1e-9 for a in allowed):
                continue
        except ValueError:
            pass
        if number in percents:
            if not _percent_grounded(number, metrics):
                bad.add(number)
            continue
        if len(number.split(".")[0]) <= 2:
            continue
        bad.add(number)
    return bad


def _metric_figures(text: str, metrics) -> set[str]:
    """그 문장이 인용한 '지표 수치'. 화면에 금액·비중으로 보이는 값만 센다.

    두 겹으로 거른다. 먼저 금액(네 자리 이상 + 원)과 백분율만 보고, 그중 지표에 실제로
    있는 값만 남긴다.

    - "21시까지"·"직원 1명"은 시각·인원이라 애초에 금액·비율이 아니다. 시각은 지표에도
      들어 있어서(hour: 14) 지표 포함 여부만으로는 거를 수 없다 — 단위를 같이 봐야 한다.
    - "10% 할인"은 백분율이지만 지표에 없는 값이라 실행 지시다.

    둘 다 프롬프트가 명시적으로 허용하는 표현이라 필드 간 중복 금지 대상이 아니다.
    """
    allowed = _metric_numbers(metrics)
    used = {m.group().replace(",", "").rstrip("원% \t") for m in _DISPLAY_NUM.finditer(text)}
    return {n for n in used if n in allowed}


def _label_hallucination(text: str, metrics) -> set[str]:
    """지표에 없는 요일 라벨. 숫자는 맞는데 차원이 틀리는 오류를 잡는다.

    실제로 `dayType: WEEKDAY` 를 "금요일"로 바꿔 쓴 출력이 나왔다. 숫자만 검증하면 통과한다.
    """
    allowed = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "dayOfWeek" and item in _DOW_KO:
                    allowed.add(_DOW_KO[item])
                elif key == "dayType":
                    allowed.add("평일" if item == "WEEKDAY" else "주말")
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(metrics)
    return {ko for ko in _DOW_KO.values() if ko in text} - allowed


def _metric_paths(metrics: dict) -> dict[str, set[str]]:
    """숫자 → 최상위 지표 키 역인덱스. 카드가 같은 지표를 두 번 인용했는지 보려고 쓴다."""
    out: dict[str, set[str]] = {}

    def walk(value, top):
        if isinstance(value, dict):
            for item in value.values():
                walk(item, top)
        elif isinstance(value, list):
            for item in value:
                walk(item, top)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.setdefault(str(value), set()).add(top)
        elif isinstance(value, float):
            for text in (f"{value:g}", f"{abs(value) * 100:g}", f"{round(abs(value) * 100):g}"):
                out.setdefault(text, set()).add(top)

    for key, item in metrics.items():
        walk(item, key)
    return out


def _evidence_group(text: str, index: dict[str, set[str]]) -> set[str]:
    """그 문장이 근거로 삼은 지표 키. 여러 지표에 걸치는 숫자는 판단에 쓰지 않는다."""
    out: set[str] = set()
    for number in _numbers_in(text):
        keys = index.get(number, ())
        if len(keys) == 1:
            out |= set(keys)
    return out


# 서비스가 요청한 카드 수. 2026-10-07(#123) 부터 배정된 지표가 3 종이 안 되면 그만큼만
# 내보내므로, 호출부가 그 수를 넘겨야 한다. 3 으로 박아두면 설계대로 2 장을 낸 응답을
# 결함으로 센다 — 실제로 2026-10-08 측정에서 `카드3장` 66.7% 가 전부 그거였다.
MAX_CARDS = 3


def grade_solution(raw: str, metrics: dict, expected_cards: int = MAX_CARDS) -> dict:
    """솔루션 카드를 app/prompts/solution.py(2026-10-08) 기준으로 채점한다.

    expected_cards 는 서비스가 요청한 장수다(`len(assign_focus(metrics)) or 3`).
    """
    result: dict = {"parsed": False}
    try:
        cards = json.loads(strip_fence(raw))["solutionCards"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["parsed"] = True
    ranks = [c.get("rankNo") for c in cards]
    titles = [c.get("title") or "" for c in cards]
    summaries = [c.get("summaryText") or "" for c in cards]
    details = [c.get("detailText") or "" for c in cards]
    evidences = [c.get("evidence") or "" for c in cards]
    visible = titles + summaries + details  # evidence 는 화면에 안 나온다(2026-10-02 FE 확정)

    # 2026-10-17 제품 결정: 최소 1 장·최대 3 장. 억지로 채우지 않는다 — 배정 수보다
    # 적게 나오는 건 결함이 아니다. 다만 배정 수보다 **많으면** 근거 없는 카드가 생긴
    # 것이므로 결함이다. 그 전에는 "배정 수와 정확히 일치" 를 쟀다(`카드_개수_일치`).
    result["카드_개수_적정"] = 1 <= len(cards) <= expected_cards
    result["rankNo_고유"] = len(set(ranks)) == len(ranks)
    result["title_200자"] = all(len(t) <= 200 for t in titles)
    result["detail_1000자"] = all(len(d) <= 1000 for d in details)
    result["evidence_있음"] = all(e.strip() for e in evidences)

    # 실행 방법 두 문장 + 기대효과 한 문장 = 줄바꿈 2개 (2026-10-01 재설계)
    result["detail_3문장"] = all(d.count("\n") == 2 for d in details)

    # summaryText 가 쓴 지표 수치를 title·detailText 가 다시 쓰면 안 된다. evidence 는 예외.
    # 지표에 없는 수(시각·인원·할인율)는 실행 지시라 중복 대상이 아니다.
    def _fields_disjoint(card_index: int) -> bool:
        groups = [
            _metric_figures(titles[card_index], metrics),
            _metric_figures(summaries[card_index], metrics),
            _metric_figures(details[card_index], metrics),
        ]
        return all(
            not (groups[i] & groups[j])
            for i in range(len(groups))
            for j in range(i + 1, len(groups))
        )

    result["수치_필드간_중복없음"] = all(_fields_disjoint(i) for i in range(len(cards)))

    result["금액_어림_없음"] = not any(_ROUNDED.search(t) for t in visible + evidences)
    result["시각_24시간제"] = not any(_AMPM.search(t) for t in visible)
    result["배율_없음"] = not _ungrounded_ratios(visible, metrics)
    result["요일_환각_없음"] = not any(
        _label_hallucination(t, metrics) for t in visible + evidences
    )
    # title·summaryText 는 그동안 수치 검사 밖이었다(2026-10-16 발견). 배포본에서
    # "남은 시간 동안 253,196원을 추가로 만들어야 합니다"가 summaryText 에 나왔는데
    # 측정에서는 수치_정확 100% 로 보였다 — 화면에 보이는 필드가 검사에서 빠져 있었다.
    result["summary_수치_정확"] = not any(_ungrounded(t, metrics) for t in titles + summaries)
    result["evidence_수치_정확"] = not any(_ungrounded(e, metrics) for e in evidences)
    result["detail_수치_정확"] = not any(_ungrounded(d, metrics) for d in details)

    # 기대효과(detailText 마지막 문장)는 정성적으로만 — "매출 15% 증가" 같은 날조 금지
    # 실행 문장(detailText 앞 두 문장)과 title 만 본다 — 기대효과 문장은 "매출을 늘릴 수
    # 있습니다" 가 허용이라 같은 잣대로 보면 오탐이 난다.
    actions = titles + [line for d in details for line in d.split("\n")[:2]]
    result["실행수치_날조_없음"] = not any(_FABRICATED_AMOUNT.search(t) for t in actions)
    result["공허한_조언_없음"] = not any(_VAGUE_ACTION.search(t) for t in actions)

    result["기대효과_정성적"] = not any(_DISPLAY_NUM.search(d.split("\n")[-1]) for d in details)

    # 카드끼리 같은 지표를 근거로 쓰면 "서로 다른 지표" 지시 위반이다. 문장이 달라도 중복이다.
    index = _metric_paths(metrics)
    groups = [_evidence_group(e, index) for e in evidences]
    result["카드_지표_중복없음"] = all(
        not (groups[i] & groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups))
    )

    result["날씨_인과_주장_없음"] = not any(_WEATHER_CAUSAL.search(t) for t in visible)
    # conditionPatterns 가 근거로 들어온 카드에서만 과거 관측 차이를 말할 수 있다.
    result["과거날씨_판매_추측_없음"] = bool(metrics.get("conditionPatterns")) or not any(
        _PAST_WEATHER_SALES.search(t) for t in visible
    )

    result["기간_날짜_명시"] = not any(_VAGUE_PERIOD.search(t) for t in visible + evidences)

    result["cards"] = cards
    return result


# 규칙 위반이 아니라 "이번 요청에서 그 축이 선정됐는지"·"분기를 인용했는지" 를 재는
# 측정값들. 3 문장 안에 6 축이 다 선정되지 않는 게 정상이고 정상 인사이트는 분기를
# 인용하지 않으므로 False 가 흔하다 — devtools/bench.py 의 전항목(출하 판정) 집계에
# 그대로 넣으면 상시 0% 가 나온다(#209 리뷰 Important #2, #178 카드_개수_일치 사고와
# 같은 모양). per_key 표에는 그대로 찍고 전항목에서만 뺀다.
# 상권_분기_날조_없음은 넣지 않는다 — 인용했는데 값이 틀린 건 진짜 결함이다.
# 키가 태어나는 곳에 둔다(원래 devtools/bench.py 에 있었다) — 등록을 잊었는지는
# tests/test_bench.py 가 grade_insight 결과와 대조해 잡는다.
MEASURE_ONLY = {"salesSummary_선정률", "hourlySales_선정률", "상권_분기_인용됨"}


def grade_insight(raw: str, metrics: dict) -> dict:
    """매출 인사이트를 app/prompts/insight.py(2026-09-23) 기준으로 채점한다."""
    result: dict = {"parsed": False}
    try:
        insights = json.loads(strip_fence(raw))["insights"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    body = " ".join(insights)
    result["parsed"] = True
    result["개수_1_3"] = 1 <= len(insights) <= 3
    result["빈문장_없음"] = all(s.strip() for s in insights)
    result["100자_이내"] = all(len(s) <= 100 for s in insights)
    result["중복_없음"] = len(set(insights)) == len(insights)
    # "3주 연속 감소" 류 — 한 달치 스냅샷이라 연속성을 주장할 근거가 없다
    result["다주표현_없음"] = "연속" not in body
    # 관찰만 하고 처방하지 않는다. "~하세요"로 끝나면 처방이다.
    # 필요조건일 뿐이다 — "~하는 것이 좋습니다."는 "다."로 끝나지만 처방이다.
    result["관찰형_종결"] = all(s.rstrip().endswith("다.") for s in insights)
    result["금액_어림_없음"] = not _ROUNDED.search(body)
    result["수치_정확"] = not _ungrounded(body, metrics)
    result["요일_환각_없음"] = not _label_hallucination(body, metrics)

    # 비율 반올림 금지 — 0.042 는 4.2% 지 4% 가 아니다. 화면에서 티가 안 나 조용히 틀린다.
    ok = True
    changed = metrics["salesSummary"].get("vsPrevPeriod")
    if changed is not None:
        exact = f"{abs(changed) * 100:g}"
        rounded = f"{round(abs(changed) * 100):g}"
        percents = _PERCENT.findall(body)
        if exact != rounded and rounded in percents and exact not in percents:
            ok = False
    result["비율_반올림_없음"] = ok

    # ratio 의 분모는 menuSales 다 — "전체의 OO%"·"총 매출의 OO%" 는 틀린 문장이다
    result["ratio_분모_정확"] = not re.search(r"(전체|총\s*매출)의\s*\d", body)

    result["상권_인과_주장_없음"] = not _DISTRICT_CAUSAL.search(body)
    result["salesSummary_선정률"] = _axis_selected(body, metrics, "salesSummary")
    result["hourlySales_선정률"] = _axis_selected(body, metrics, "hourlySales")
    result["상권_평균매출_반영"] = _district_avg_reflected(body, metrics)
    result["상권_피크밴드_반영"] = _district_band_reflected(body, metrics)
    grounded = _quarter_leak(body, metrics)
    result["상권_분기_인용됨"] = grounded is not None
    result["상권_분기_날조_없음"] = grounded

    result["insights"] = insights
    return result
