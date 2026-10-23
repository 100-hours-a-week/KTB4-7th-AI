"""매출분석 화면의 "AI가 발견했어요" 영역에 쓸 관찰형 인사이트를 생성한다.

2026-09-16: docs/api정의서.md·docs/ERD정의서.md 확정 반영.
응답이 `insights` 문자열 배열로 단순화됐다(항목별 evidence 없음 — sales_ai_insights.insights 는
문자열 JSON 배열만 저장한다). 행동 처방은 하지 않고 관찰만 한다는 원칙은 그대로 유지한다.

2026-09-21: 금액 인용·비율 표기 지시를 추가했다. 실호출 3회 중 1회에서 18시 매출
210,000 원을 "30만원"으로 말했다 — 비율(7배)은 맞고 절대값만 틀렸다. "새로운 수치를 만들지
마세요"만으로는 이미 있는 값을 어림하는 것까지 막지 못했다.

지시를 금액에만 한정한 이유가 있다. 처음엔 "수치를 그대로 쓰라"고만 썼더니 비율까지 원문
그대로 읽어서 "이전 기간 대비 0.12 감소"가 나왔고, 금액의 천 단위 구분도 사라졌다. 계약상
비율은 소수로 주고받지만(0.62), 점주에게 보여줄 문장에서는 백분율이어야 한다.

2026-10-08(2): 고정 규칙을 앞으로, 지표를 뒤로 옮겼다(순서만, 문장은 그대로). 이유는
app/prompts/solution.py 머리말과 같다. 인사이트는 SYSTEM 이 688자라 이미 그만큼 캐시에
걸리고 USER 고정분은 216자뿐이라 이익이 더 작다 — 두 엔드포인트의 구조를 같게 두려고
같이 바꿨다.

2026-10-08: 문장마다 쓸 근거 지표를 서비스가 하나씩 배정해 넘긴다. 지표 6 종을 통째로
던지던 방식은 실측에서 `수치_정확` 68% 였다(2026-10-06, n=48, 32B) — 인사이트 전 항목 중
최악이고, 같은 조건에서 카드당 1 종만 받는 솔루션은 96% 였다. 숫자를 많이 보여줄수록
모델이 엉뚱한 값을 집는다. 배정 기준은 app/services/insight_focus.py 에 있다.

2026-09-22: 풀스택 확정 계약(metrics 교체)과 생성 규칙 4종을 반영했다.

- **비율 반올림 금지.** 위 2026-09-21 지시가 금액만 막아서, 실호출 3회 중 1회가 0.042 를
  "4% 증가"로 말했다(정답 4.2%). 4.2 → 4 는 화면에서 티가 안 나 조용히 틀린다.
- **totalSales / menuSales 구분.** 상세 지표가 전부 menuSales 계열인데 총액과 섞으면
  부분의 합이 전체를 넘는 문장이 나온다. 실호출 5회 중 1회가 categorySales.ratio(0.417,
  메뉴 매출 대비)를 "전체의 41.7%"라고 말했다 — 총매출 기준이면 39.4% 라 틀린 문장이다.
  ratio 의 분모를 프롬프트에 명시했다.
- **증감률 없음.** 이전 비교 데이터가 없으면 BE 가 `vsPrevPeriod` 를 null 로 보낸다
  (2026-09-23 실연동). 서비스가 `exclude_none` 으로 아예 빼서 넘기지만, 모델이
  `salesTrend` 로 비교를 만들어낼 수 있어 지시도 함께 둔다.
- **vsPrevPeriod 의 주어.** 계약에 분모가 안 적혀 있어 5회 중 1회가 "메뉴 매출이 4.2%
  증가"로 말했다. 풀스택 예시("9월 총 매출은 ... 4.2% 증가")를 따라 총매출 기준으로
  고정했다. 계약 문서에도 명시해달라고 요청해둔다.
- **다주(多週) 표현 금지.** salesTrend·weekdaySales 가 새로 들어오면서 모델이 "3주 연속
  감소" 같은 문장을 만들 재료가 생겼다. V1 은 월 단위 스냅샷이라 연속성을 주장할 근거가 없다.
- **100자 제한.** 프롬프트로도 알리지만 실제 차단은 services/insight.py 가 한다 —
  코드펜스 때 배운 대로, 계약을 어기면 BE 가 깨지는 항목은 프롬프트에 맡기지 않는다.

2026-10-15: districtBenchmark(상권, #157)가 여섯째 근거 축으로 들어왔다. 행정동 전체
카페의 분기 평균 추정치일 뿐 매장 개별 실적이 아니라서, "우리 매장" 성과처럼 쓰거나
상권 상태로 매출 변화를 설명하면 근거 없는 주장이 된다 — weatherContext 인과 금지
규칙(app/prompts/solution.py)과 같은 이유다. 배정 기준(매장-행정동 평균 격차,
표본 가드)은 app/services/insight_focus.py 에 있다.

2026-10-21(#209): districtBenchmark 중첩 객체를 더는 보내지 않는다. 대신
districtAvgMonthlySalesPerCafe·vsDistrictAvg 는 salesSummary 문장에,
peakSalesHourBand·peakFootTrafficHourBand·vsDistrictSalesPeak·
vsDistrictFootTrafficPeak 는 hourlySales 문장에 조건부로 묶여 들어온다
(app/services/insight_focus.py 참고). 비교 방향(vsDistrictAvg)·피크 일치 여부
(vsDistrictSalesPeak·vsDistrictFootTrafficPeak)는 코드가 미리 계산해 주므로
모델에게는 "그대로 따르라"고만 지시한다 — 두 밴드 레이블을 바꿔 말할 위험(설계
리뷰)도 레이블 고정 문구로 같이 막는다.

2026-10-22(#209 최종 리뷰 Important #5, PR #219 머지 전 재검토): hourlySales 는
dayType(평일/주말)별로 행을 따로 보여주는데 피크 비교는 그 구분 없이 단일값이라,
모델이 실제로 말하는 dayType 과 코드가 계산한 비교 방향이 어긋날 수 있었다.
vsDistrictSalesPeak·vsDistrictFootTrafficPeak 를 Weekday/Weekend 접미로
쪼개(app/services/insight_focus.py 참고) dayType 마다 맞는 비교값을 받게
했다.

2026-10-22(2, 1차 실측 원인 분석): `상권_피크밴드_반영`이 13건 중 1건(7.7%)만
통과했다 — 실패 12건 중 11건이 "유동인구 피크 시간대와 다릅니다"처럼 비교
판정(SAME/DIFFERENT)만 말하고 peakFootTrafficHourBand 의 실제 시간대 범위
("17-21")는 빼먹는 패턴이었다(매출 밴드는 자기 매장 피크 시간과 겹쳐서
"자연스럽게" 숫자까지 같이 나왔다). 글자수 제한은 원인이 아니다 — 실패
문장은 보통 45~60자라 범위 숫자(`"(17-21)"`, 7~8자)를 더해도 100자에 한참
못 미친다. "두 범위를 숫자로 그대로 인용하라"는 지시와 올바른 예문을 추가해
빠뜨리지 않게 막는다.

2026-10-22(3): 재측정 중 두 가지가 더 걸렸다. ① "상권"이라는 말을 실제로는 한
번도 정의한 적이 없었다(app/schemas/common.py::DistrictBenchmark 독스트링은
"행정동 단위"라고 명시하고 프롬프트에 그 구분을 반영하라고 적어 뒀는데, 이
프롬프트는 ABOVE/BELOW 설명·인과 금지 문구에서만 "상권"이라고 썼다) — 전부
"행정동"으로 통일했다. ② vsDistrictAvg 쪽도 밴드와 같은 숫자 생략 패턴이
재측정에서 나타났다("행정동 평균보다 낮습니다"만 쓰고 금액은 뺌, 상권_평균매출_반영
20%→6.7%) — 밴드 쪽에 넣은 "숫자를 반드시 같이 써라" 지시를 이 문단에도
추가했다. ③ 밴드 비교 성공 예문이 "행정동 밴드 둘이 서로 다르다"처럼 읽혀
주어(우리 매장)가 빠진 문장이 통과되고 있었다 — 예문·설명 전부에 "우리 매장의"
주어를 명시해 행정동 내부 비교로 오독되지 않게 고쳤다.

2026-10-23(#209 재검토 반영): peakSalesHourBand·peakFootTrafficHourBand 는
이제 SAME(우리 매장 피크와 겹침)이면 그 밴드 자체를 안 보낸다(app/services/
insight_focus.py 참고) — 하나만 오거나 둘 다 오거나 둘 다 안 올 수 있다.
"두 개 다 숫자로 그대로 인용하세요"는 둘 다 온다는 전제가 깨져서, "주어진
필드만 언급하고 없는 건 언급하지 마라"는 조건부 지시로 바꿨다.

2026-10-24(사용자 요청): SAME 비교를 "겹침"으로 서술하라는 지시·예문을
"동일함"으로 바꿨다. devtools/grade.py::_DIRECTION_WORDS["SAME"]에 "동일"
패턴을 추가해 같이 맞췄다 — 안 바꾸면 모델이 "동일하다"로 답해도 채점기가
SAME 어휘로 인식 못 해 방향 검사가 전부 통과(무검증)로 샐 수 있다.
"""

import json

VERSION = "2026-10-24"

SYSTEM = """당신은 카페 매출 분석 어시스턴트입니다.
아래 지표만 근거로 사용하고, 직접 계산하거나 새로운 수치를 만들지 마세요.
금액은 지표에 있는 값을 그대로 쓰고 어림하지 마세요 — 1,183,600원처럼 천 단위로 끊어 씁니다.
비율은 소수가 아니라 백분율로 바꿔 쓰되, 소수점 자리를 반올림하거나 버리지 마세요
(0.042 → 4.2%, 0.417 → 41.7%). "4%"처럼 줄여 쓰면 틀린 값입니다.
전체 매출·객단가를 말할 때는 totalSales 를, 메뉴·카테고리·일별·요일별·시간대별 패턴을
말할 때는 menuSales 계열을 쓰세요. 두 값을 한 문장에서 섞지 마세요.
ratio 는 총매출이 아니라 **메뉴 매출 대비** 비중입니다. "전체의 OO%"가 아니라
"메뉴 매출의 OO%"라고 쓰세요.
salesSummary.vsPrevPeriod 는 **총매출(totalSales)**의 증감률입니다. 메뉴 매출이
늘었다는 뜻으로 쓰지 마세요.
증감률(vsPrevPeriod)이 없는 항목은 이전 기간과 비교하지 마세요. 다른 지표로 추정하지 말고
현재 기간의 사실만 말하세요.
"3주 연속 감소"처럼 여러 주에 걸친 추세나 연속성은 말하지 마세요 — 주어진 지표는 한 달치
스냅샷이라 연속성을 확인할 수 없습니다.
districtAvgMonthlySalesPerCafe·peakSalesHourBand·peakFootTrafficHourBand 는
매장이 속한 **행정동**(행정구역 단위) 값입니다 — "상권"이라고 뭉뚱그리지 말고
항상 "행정동"이라고 쓰세요.
districtAvgMonthlySalesPerCafe 는 그 행정동의 커피·음료 업종 점포당 월평균
추정매출입니다(참고용 추정치). 매장 개별 실적이 아니므로 "우리 매장" 성과처럼 쓰지
마세요. vsDistrictAvg 가 있으면 그 값과 districtAvgMonthlySalesPerCafe 숫자를
**반드시 같이** 쓰고 직접 비교·계산하지 마세요 — ABOVE 는 **우리 매장 매출이**
행정동 평균보다 높음, BELOW 는 낮음, EQUAL 은 같음을 뜻합니다. 숫자 없이 "행정동
평균보다 낮습니다"라고만 쓰면 안 됩니다 — 그 평균 금액을 반드시 같이 쓰세요.
peakSalesHourBand 는 반드시 "매출이 가장 많은 시간대"로, peakFootTrafficHourBand 는
반드시 "유동인구가 가장 많은 시간대"로만 서술하세요 — 두 레이블을 바꿔 쓰지 마세요.
peakSalesHourBand·peakFootTrafficHourBand 는 **둘 중 하나만 주어질 수도, 둘 다
주어질 수도, 둘 다 주어지지 않을 수도** 있습니다 — 주어진 필드만 언급하고, 없는
필드는 언급하지 마세요("유동인구 피크 시간대는 알려지지 않았습니다" 같은 보충
설명도 하지 마세요).
vsDistrictSalesPeakWeekday·vsDistrictSalesPeakWeekend·vsDistrictFootTrafficPeakWeekday·
vsDistrictFootTrafficPeakWeekend 가 있으면 그 값을 그대로 따르고 직접 비교하지
마세요 — Weekday 접미는 평일, Weekend 접미는 주말 매출 피크 시간대를 기준으로
계산한 값입니다. SAME 은 **우리 매장의** 그 요일 유형 매출 피크 시간대가 행정동
밴드와 동일함, DIFFERENT 는 다름을 뜻합니다(SalesPeak 는 peakSalesHourBand,
FootTrafficPeak 는 peakFootTrafficHourBand 와 짝입니다). 평일과 주말의
비교 결과가 다를 수 있으니, 평일 얘기를 할 땐 Weekday 값을, 주말 얘기를 할
땐 Weekend 값을 쓰세요. 주어진 peakSalesHourBand·peakFootTrafficHourBand 의
시간대 범위(예: "11-14")는 **숫자로 그대로 인용하세요** — "유동인구
피크 시간대와 다릅니다"처럼 비교 결과만 말하고 그 범위를 빠뜨리면 안 됩니다.
비교 주어도 분명히 밝히세요 — "행정동 밴드가 다릅니다"가 아니라
"우리 매장 매출 피크가 그 밴드와 같거나 다르다"는 뜻입니다. 올바른 예: "우리
매장의 매출 피크 시간대가 행정동 매출 피크 시간대(11-14)와 동일하고, 행정동
유동인구 피크 시간대(17-21)와는 다릅니다."(둘 다 주어진 경우) 주어진 밴드가
하나뿐이면 그 하나만 같은 형식으로 말하세요. 특정 필드가 없으면 그 요일 유형은
매출 피크 시간을 계산할 수 없었다는 뜻이니, 그 요일 유형과 밴드를 비교해서
"같다/다르다"를 직접 판단해 말하지 마세요. "행정동이 좋아서/나빠서 매출이
~했다"처럼 행정동 상태가 매출에 영향을 줬다고 주장하지 마세요 — 그런 인과를
뒷받침할 지표가 없습니다.
무엇을 하라는 제안은 하지 말고, 데이터에서 관찰되는 사실만 말하세요.
설명 없이 JSON만 출력하세요."""

_USER = """점주가 알아두면 좋을 관찰 사실을 {count}개 찾아주세요.
문장마다 쓸 근거 지표를 아래에 하나씩 배정했습니다. 각 문장은 **자기 근거 지표만** 쓰고,
다른 문장에 배정된 지표를 끌어오지 마세요.

배정된 순서대로 쓰고, 각 문장은 한국어 존댓말 한 문장으로 공백 포함 {max_chars}자 이내로
쓰세요. 같은 내용을 다른 표현으로 반복하지 마세요.

{focus_blocks}

{{"insights":["...", "..."]}}"""


def build(focus: list[dict], max_chars: int) -> str:
    """focus 는 문장 순서대로의 근거 지표다 — app/services/insight_focus.py::assign 참고."""
    blocks = "\n\n".join(
        f"[문장 {index} 근거]\n{json.dumps(item, ensure_ascii=False)}"
        for index, item in enumerate(focus, start=1)
    )
    return _USER.format(
        focus_blocks=blocks,
        count=len(focus),
        max_chars=max_chars,
    )
