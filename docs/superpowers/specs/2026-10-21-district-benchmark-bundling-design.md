# 상권(districtBenchmark) 인사이트 번들링 설계

## 변경 이력

- 2026-10-21: 초안.
- 2026-10-21(2): 헥터가 벤치 케이스에 상권/날씨를 실제로 넣어 머지한 PR #207·#208로
  초안의 "트레이드오프" 절을 실측으로 재현·보강. `salesSummary`가 숙주로 불안정하다는
  점(아래 "A"), `basisQuarter` 접지 누수(아래 "B"), 번들링 특유의 오귀속 위험(아래
  "C") 세 가지를 반영해 설계를 다시 열었다. 세 항목은 성격이 달라 처리 방식도 다르다
  — A·B는 **추측으로 점수·차단 규칙을 바꾸지 않고 먼저 측정**하고, C는 측정만으로는
  못 잡는 구조적 위험이라 **구현 시점에 바로 예방 조치**를 넣는다.
- 2026-10-21(3): 헥터의 PR #210 설계 리뷰 반영. (1) A의 측정 항목이 "숙주 미선정"과
  "선정됐는데 미반영"을 하나로 섞어서 쪼갰다(`salesSummary_선정률` / `상권_평균매출_반영`,
  분모가 다르다). (2) `hourlySales` 번들의 `peakSalesHourBand`/`peakFootTrafficHourBand`
  두 밴드에는 C의 오귀속 예방이 없었다는 지적을 받아 밴드 겹침 계산을 추가했다(1차
  시도 — 아래 (4)에서 다시 바뀜). (3) 트레이드오프 절의 `hourlySales` 선정률 인용이
  PR #207(솔루션 `hourlyProfile`)과 PR #208(인사이트 `hourlySales`)을 혼동한 오류였다
  — 정정. (4) A와 짝을 맞춰 밴드 반영률 측정 항목(`상권_피크밴드_반영`)도 같이 추가했다.
- 2026-10-21(4): 사용자가 헥터 리뷰를 종합 검토하며 (2)의 1차 시도를 다시 열었다 —
  "두 상권 밴드끼리 겹치는지"(`districtPeakAlignment`)는 상권 **내부**의 매출·유동인구
  연관을 암시할 위험이 있고, "이 매장 쪽 대응 데이터가 없다"던 전제도 틀렸다
  (`hourlySales.menuSales`로 우리 매장의 매출 피크 시간을 이미 계산할 수 있다). 그래서
  "두 밴드끼리 비교" 대신 **"우리 매장의 매출 피크가 상권의 각 밴드 안에 드는지"**
  (`vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`)로 바꿨다 — `vsDistrictAvg`와
  같은 "내 수치 vs 상권 수치" 구조라 인과 암시가 없다. 그리고 A의 반영률 측정에
  "언급됐는지"뿐 아니라 "비교 방향이 맞는지"까지 넣었고, `hourlySales_선정률`을
  `salesSummary_선정률`과 짝을 맞춰 추가했고, B도 A와 같은 조건부 분모 방식
  (`상권_분기_인용됨`/`상권_분기_날조_없음`, 인용 안 했으면 `None`)으로 통일했다.
- 2026-10-21(5): 별도 검토(헥터 의견 아님)로 두 가지를 더 고쳤다. (1) 영업 중인
  시간대가 하나도 없으면(`menuSales`가 전부 0) `_store_peak_hour`가 `None`을
  돌려주는데, 그걸 그대로 "안 겹침"(`DIFFERENT`)으로 단정하고 있었다 — "계산할 수
  없음"과 "실제로 다름"은 다른 상태라, 피크를 못 구하면 `vsDistrictSalesPeak`/
  `vsDistrictFootTrafficPeak` 필드 자체를 아예 안 보내기로 바꿨다(아래 핵심 설계
  2번). (2) `상권_피크밴드_반영`의 설계 문구("둘 중 하나라도 안 보이면 실패", 즉
  둘 다 필요)와 실제 짜 둔 채점 로직("하나라도 보이면 통과")이 어긋나 있었다 —
  하나로 합치지 않고 밴드별로 따로 재는 쪽으로 바꿔 모호함을 없앴다(아래 "A").
- 2026-10-21(6): 재검토 끝에 (5)-(2)를 다시 되돌렸다. `hourlySales` candidate는
  두 밴드·두 비교 필드를 **같은 한 문장**에 묶어 넣는다(Task 1의 `vsDistrictAvg`가
  `totalSales`·`districtAvgMonthlySalesPerCafe`를 한 salesSummary 문장에 묶는
  것과 같은 구조) — 그러니 "문장마다 근거 하나" 원칙은 **축 사이**(salesSummary
  vs hourlySales)에 적용되는 것이고, 같은 축의 번들 안에서 일부만 말하고 나머지를
  빠뜨리는 건 그 원칙과 무관한 **진짜 결함**이다. 그래서 두 밴드를 독립 측정으로
  쪼갠 (5)-(2)를 되돌리고, "둘 다 언급 + 둘 다 방향 정확"을 요구하는 단일 지표
  `상권_피크밴드_반영`으로 복귀했다(아래 "A"). 그리고 BE
  `SeoulDistrictQuarterAggregationService`를 직접 읽어 `VALID_HOUR_BANDS`가
  겹치지 않는 고정 6분할(`00-06`·`06-11`·`11-14`·`14-17`·`17-21`·`21-24`,
  `BAND_HOURS`로 폭까지 확인)이라는 걸 확인했다 — 그래서 (1) "두 상권 밴드끼리
  겹치는지"(폐기된 `districtPeakAlignment`)는 BE 파티션 자체가 안 겹쳐서 애초에
  무의미했던 게 맞고, (2) `_in_band`가 쓰는 반열린 구간(`start <= hour < end`)이
  `BAND_HOURS`의 밴드 폭과 정확히 일치해 BE와 같은 경계 해석을 쓴다는 것도
  확인됐다(아래 핵심 설계 2번). `vsDistrictAvg`의 `summary.get("totalSales") or 0`
  방어 코드는 그대로 둔다 — `InsightMetrics.salesSummary.totalSales`가 스키마상
  `int`(필수, `app/schemas/common.py`)라 None이 될 수 없어 손댈 이유가 없다.
  `salesSummary_선정률`/`hourlySales_선정률`이 실제 `assign()` 선정이 아니라
  생성된 문장에서 추정한 값이라는 한계는 문서화만 하고(아래 "A"), 실측 벤치마크에
  실제 선정 축을 같이 찍는 건 이번 범위 밖으로 미뤘다.
- 2026-10-21(7): 위 두 가지(밴드 둘 다 반영 검사, 선정률 추정치 표기)를 "문서만
  고치고 구현 PR에서 빠뜨리면 안 된다"는 요청을 받아, 구현 계획 문서
  (`docs/superpowers/plans/2026-10-21-district-benchmark-bundling.md`)의 Global
  Constraints 바로 뒤에 "구현 PR 필수 검증 항목" 체크리스트로 못박았다 — Task 4
  커밋 전 재확인, Task 6에 STATE.md 표기 확인 Step 추가.

## Context

`POST /internal/v1/ai/sales-insights`는 7개 후보 축(`salesSummary`·`salesTrend`·
`weekdaySales`·`hourlySales`·`categorySales`·`menuRankings`·`districtBenchmark`) 중
`maxInsightCount`(보통 3)개를 골라 문장으로 만든다(`app/services/insight_focus.py::assign`).
축마다 "오늘/이번 달 할 말이 있는가" 점수를 매겨 상위 N개만 쓴다 — 지표를 많이 보여줄수록
모델이 엉뚱한 수치를 집는다는 실측(2026-10-06, n=48, `수치_정확` 68%→96%)이 이 파일 전체의
전제다.

`districtBenchmark`(#157, PR #161)는 2026-10-16에 "격차 비례 점수"에서 "고정 보충값
0.3"으로 바뀌었다(PR #161 리뷰, 헥터) — 날씨(`solution_focus._weather_score`)의 "다른 세
축이 전부 약할 때만 보충" 설계를 그대로 복사한 것이다. 그런데 인사이트는 상권이 들어오기
**전부터 이미 6개 축**이 경쟁 중이었다 — 날씨 쪽 "세 축" 전제를 축 개수도 다시 안 보고
복붙한 실수였다. 실제 샘플(한 달치 데이터가 꽉 찬 경우)로 돌려보면 상권이 다른 6개 축에
자주 밀려 거의 노출되지 않는다.

별개로, BE 쪽에서 상권 데이터가 애초에 AI까지 도착하지 않았을 가능성이 있는 버그 2건이
2026-10-20에 수정됐다 — 분기 데이터 수집 스케줄러 최초 연결(`f417921`), 8자리 행정동
코드 집계 누락 수정(`a9f5a2d`). 이건 "데이터가 오느냐"의 문제고, 이 설계는 "온 데이터를
AI가 쓰느냐"의 문제라 서로 독립적이다 — BE 수정으로 데이터가 도착하기 시작하면 이 설계의
효과가 비로소 드러난다.

**PR #207·#208로 "밀림" 현상이 실측 확인됐다.** 벤치 케이스(`devtools/bench.py`)가
`weatherContext`·`districtBenchmark`를 애초에 입력에 포함한 적이 없어, 0~6차 품질
측정이 전부 "날씨·상권 없음" 조건으로 돌고 있었다(헥터, #206). 케이스를 추가해 돌려본
결과("전부있음", 운영 입력에 가장 가까움):

```
솔루션(5축 경쟁)  hourly 0.86 · category 0.52 · menu 0.42 · summary 0.33 · weather 0.30  → 날씨 밀림
인사이트(7축 경쟁) hourlySales 0.775 · categorySales 0.480 · weekdaySales 0.379 ·
                 districtBenchmark 0.300 · menuRankings 0.266 · salesSummary 0.216(밀림) ·
                 salesTrend 0.137
```

인사이트 쪽에서 **`salesSummary`가 7개 중 6위로 3위 안에 못 들었다** — 이 설계가 상권
평균매출(`districtAvgMonthlySalesPerCafe`)을 묶으려는 숙주 축이 바로 이 축이다. 아래
"A"에서 다룬다.

## 범위

- **포함**: `app/services/insight_focus.py`의 `districtBenchmark` 선발 로직을 전용
  경쟁 축에서 "기존 축에 조건부 번들링"으로 바꾼다. `app/prompts/insight.py`의 관련
  SYSTEM 규칙 문구 조정.
- **제외**: solution의 `weatherContext`(`app/services/solution_focus.py`)는 건드리지
  않는다 — 솔루션 카드는 "오늘 실행할 것 3개" 경쟁 구조에 원래 맞고, 이 레포의 다른
  담당자(헥터)가 벤치 케이스(#206/#207)로 같은 "밀림" 현상을 독립적으로 재현한 상태라
  별도 판단이 필요하다. `peakSalesHourBand`/`peakFootTrafficHourBand`를 어떻게 더
  활용할지(예: 전용 상권 인사이트 신설)도 이번 범위 밖 — 후속 과제로 남긴다.
- **제외**: BE 쪽 데이터 파이프라인 버그(위 Context 참고)는 BE가 이미 수정 완료 —
  이 설계와 무관하다.

## 핵심 설계

`districtBenchmark`를 독립 candidate에서 빼고, 아래 두 지점에 조건부로 끼워 넣는다.
두 경우 모두 **기존 축 자체의 점수 공식은 그대로 유지** — districtBenchmark 유무가
순위에 영향을 주지 않는다(조건부 노출, 사용자 확인 완료).

### 1) `salesSummary` + `districtAvgMonthlySalesPerCafe` (+ 비교 방향 사전 계산 — "C")

`salesSummary` candidate를 구성할 때, 상권 게이트(아래)를 통과하면 focus 블록에
`districtAvgMonthlySalesPerCafe`와 **비교 방향(`vsDistrictAvg`)**을 같이 추가한다.

**왜 비교 방향을 코드가 미리 계산하나.** `totalSales`와 `districtAvgMonthlySalesPerCafe`를
그냥 나란히 주면, 모델이 "어느 쪽이 더 큰지"를 직접 계산하다 방향을 뒤집어 말할 수 있다
— 둘 다 지표에 실재하는 숫자라 기존 `UNGROUNDED_NUMBER` 게이트로는 안 걸린다(숫자는
맞는데 의미가 반전되는 오류). `solution_focus.peak_ratios()`가 "어느 두 시각 사이
배수인지"를 모델에 맡기지 않고 코드가 계산해 넘기는 것과 같은 이유다(실측으로 확인된
오귀속 사례: "12시 대 9시" 값을 "12시 대 15시"로 잘못 붙인 문장이 모든 검사를 통과).
"계산은 코드, 해석만 모델"이라는 이 레포 원칙 그대로다.

```python
def _district_comparison(total_sales: int, district_avg: int) -> str:
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


focus = {"salesSummary": summary}
if _district_gate(district):
    focus["districtAvgMonthlySalesPerCafe"] = district["districtAvgMonthlySalesPerCafe"]
    focus["vsDistrictAvg"] = _district_comparison(
        summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"]
    )
candidates.append((focus, _summary_score(summary) if summary else -1.0))
```

`ABOVE`/`BELOW`/`EQUAL` 세 상태로 나눈다 — 두 값이 같을 때 `BELOW`로 잘못 분류되지
않게 한다(설계 리뷰에서 지적된 경계값 버그).

### 2) `hourlySales` + `peakSalesHourBand`/`peakFootTrafficHourBand` (+ 사전 계산 — "C 확장")

`hourlySales` candidate를 구성할 때, 같은 게이트를 통과하면 두 밴드 필드와
**우리 매장 피크 대비 일치 여부 두 개(`vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`)**
를 같이 추가한다.

**설계가 한 번 바뀌었다.** 처음엔 "두 상권 밴드가 서로 겹치는 시간대인지"
(`districtPeakAlignment`)를 계산하려 했다 — 두 밴드가 형식이 똑같은 "HH-HH"
문자열이라 모델이 레이블을 바꿔 말할 위험(헥터 지적)을 줄이려는 의도였다. 그런데
이 방향엔 두 가지 문제가 있다는 재검토 지적을 받았다: (1) 상권 **내부**의 두
밴드끼리 겹친다는 사실만으로 "매출·유동인구가 서로 관련 있다"는 인과를 암시할
위험이 있고, (2) 애초에 "이 매장 쪽 대응 데이터가 없다"는 전제 자체가 틀렸다 —
`hourlySales`에 `menuSales`가 있어 **우리 매장의 매출 피크 시간**은 이미 계산
가능하다(`_spread_rows`가 상·하위 행을 고를 때 쓰는 것과 같은 데이터).

그래서 "두 상권 밴드끼리 비교"가 아니라 **"우리 매장의 매출 피크가 상권의 각
밴드 안에 드는지"**로 바꿨다 — `vsDistrictAvg`와 같은 구조(내 수치 vs 상권
수치)라 인과 암시 위험이 없고, 사장님에게도 "내 가게가 상권과 같은 시간에
붐비는가"가 "상권 안에서 매출·유동인구가 겹치는가"보다 바로 쓸 수 있는 비교다.
유동인구 쪽은 우리 매장에 대응 데이터가 없어(`hourlySales`엔 `orderCount`만
있고 유동인구 자체는 없다) 우리 매출 피크를 **두 상권 밴드 모두**에 대해 "드는지"
검사한다 — "우리 매출 피크가 상권 매출 피크 시간대와 겹치는가"·"우리 매출 피크가
상권 유동인구 피크 시간대와 겹치는가"는 둘 다 같은 "우리 매출 피크" 값만으로
계산되고 유동인구 데이터가 필요 없다.

**BE 코드로 직접 확인함(2026-10-21(6)).** `KTB4-7th-BE`의
`SeoulDistrictQuarterAggregationService`를 읽어보면 밴드는 `"00-06"·"06-11"·
"11-14"·"14-17"·"17-21"·"21-24"` 여섯 개뿐이고(`BANDS`/`DistrictBenchmarkService.
VALID_HOUR_BANDS`·`ChatDistrictBenchmarkResponse`의 `@Pattern` 전부 같은 여섯
값), 폭도 `BAND_HOURS = {6, 5, 3, 3, 4, 3}`로 하루 24시간을 **겹치지 않게**
전부 나눈다(동적 포맷이 아니라 고정 enum이다). 이게 두 가지를 확정해 준다:

1. 폐기한 `districtPeakAlignment`(두 상권 밴드끼리 겹치는지)는 BE 파티션 자체가
   겹칠 수 없는 구조라 애초에 계산할 가치가 없었다 — 폐기한 게 맞았다.
2. `_in_band`가 쓰는 반열린 구간(`start <= hour < end`, 예: `"06-11"` → 6·7·8·9·10)
   이 `BAND_HOURS`의 밴드 폭과 정확히 일치한다 — BE와 같은 경계 해석을 쓰므로
   경계 시간에서 결과가 달라질 위험이 없다.

밴드 형식(`HH-HH`)은 `devtools/contract_check.py` 픽스처(`"14-17"`, `"11-14"`)와도
일치한다 — 고정 enum이라 포맷이 바뀔 가능성은 낮지만, 혹시 바뀌면 BE에 확인
요청한다.

```python
def _store_peak_hour(points: list[dict]) -> int | None:
    """영업 중(menuSales > 0)인 행 중 매출이 가장 높은 시간. 없으면 None."""
    selling = _selling(points)
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int, band: str) -> bool:
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end


focus = {"hourlySales": _spread_rows(points, "hour")}
if _district_gate(district):
    focus["peakSalesHourBand"] = district["peakSalesHourBand"]
    focus["peakFootTrafficHourBand"] = district["peakFootTrafficHourBand"]
    peak_hour = _store_peak_hour(points)
    if peak_hour is not None:
        focus["vsDistrictSalesPeak"] = (
            "SAME" if _in_band(peak_hour, district["peakSalesHourBand"]) else "DIFFERENT"
        )
        focus["vsDistrictFootTrafficPeak"] = (
            "SAME" if _in_band(peak_hour, district["peakFootTrafficHourBand"]) else "DIFFERENT"
        )
candidates.append((focus, _spread(points) if points else -1.0))
```

**왜 `peak_hour is None`이면 두 필드를 아예 안 보내나(별도 검토, 2026-10-21(5)).**
`hourlySales`가 후보로 뽑혔다고 해서 영업 중인 행이 꼭 있는 건 아니다 — `_spread`
는 영업 중인 행이 전부 0이면(`len(amounts) < 2`) 0.0점을 주는데, 이 값도 다른
축이 전부 음수면 선정될 수 있다. 이때 `_store_peak_hour`는 `None`을 돌려주는데,
`_in_band(None, ...)`을 `False`로 처리해 그대로 `DIFFERENT`를 주면 "계산할 수
없음"과 "실제로 상권과 다름"을 같은 값으로 섞는다 — 데이터가 없는데 "우리
매장은 상권과 다른 시간대"라고 단정하는 잘못된 인사이트가 된다. 그래서 피크를
못 구하면 비교 필드 자체를 안 보낸다(밴드 원본 값은 그대로 보낸다 — 상권
자체의 사실이라 우리 매장 피크와 무관하게 유효하다).

`vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`는 원 밴드 값을 대신하지 않는다
— 구체적 시간대를 말할 근거는 그대로 두고, "우리 매출 피크가 그 밴드 안에
드는지"라는 추가 사실만 코드가 보장해 준다(단, 피크를 계산할 수 있을 때만). 두
필드 다 `SAME`/`DIFFERENT`면 "우리 매장은 상권 매출 피크와 겹치지만 유동인구
피크와는 다르다"처럼 실행
포인트로 쓸 수 있다.

### 게이트 함수 (기존 `_district_score`의 게이트 부분만 재사용)

```python
def _district_gate(district: dict | None) -> bool:
    """두 번들링 지점이 공유하는 유효성 검사. #157 표본 수 가드를 그대로 쓴다."""
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0
```

`_district_score`·`_DISTRICT_SUPPLEMENT_SCORE`·독립 `districtBenchmark` candidate는
삭제한다. `_MIN_CAFE_STORE_COUNT`는 게이트 함수로 옮겨 그대로 유지(BE의 저장 단계
필터와 같은 기준 — 중복 방어지만 스키마·배포가 독립적이라 유지할 가치가 있음, 기존
PR #161 결정 그대로).

### 다루지 않는 필드

- `basisQuarter`: 어느 번들에도 안 들어간다. SYSTEM 프롬프트에 "상권 평균은 참고용
  추정치입니다" 같은 고정 문구로만 다룬다 — 분기(상권 기준) vs 월(매출 기준) 단위
  불일치를 모델이 숫자로 주장하게 두지 않기 위함. **다만 "안 보낸다"가 "모델이 절대
  안 쓴다"를 보장하진 않는다** — 아래 "B. basisQuarter 접지 누수 측정" 참고.
- `cafeStoreCount`: 게이트 판단에만 쓰고 프롬프트에 안 보낸다(기존과 동일).

## 프롬프트 변경 (`app/prompts/insight.py`)

기존 districtBenchmark SYSTEM 규칙("행정동 전체 카페의 월평균 추정매출... 상권
인과 주장 금지")은 내용 그대로 유지한다 — 필드가 어느 문장에 묶이든 규칙 자체는
똑같이 적용돼야 한다. `_DISTRICT_CAUSAL` 채점 정규식(`devtools/grade.py`)도 그대로
쓴다 — 번들링된 문장에도 같은 검사가 적용된다.

**새 규칙 — 비교 방향.** `vsDistrictAvg`가 있으면 그 값(`ABOVE`/`BELOW`/`EQUAL`)을
그대로 따르고 직접 비교·계산하지 말라고 명시한다. 세 상태 전부 프롬프트에서 뜻을
풀어 적는다(`ABOVE`=상권 평균보다 높음, `BELOW`=낮음, `EQUAL`=같음) — 모델이 `EQUAL`을
빠뜨리고 임의로 ABOVE/BELOW 중 하나로 해석하지 않게 한다.

**새 규칙 — 밴드 레이블 고정.** `peakSalesHourBand`는 반드시 "매출이 가장 많은
시간대"로만, `peakFootTrafficHourBand`는 반드시 "유동인구가 가장 많은 시간대"로만
서술하고 두 레이블을 바꿔 쓰지 말라고 명시한다. `vsDistrictSalesPeak`·
`vsDistrictFootTrafficPeak`가 있으면 그 값(`SAME`/`DIFFERENT`)을 그대로 따르고
직접 비교·계산하지 말라고 명시한다(`SAME`=우리 매장의 매출 피크 시간대가 그
밴드와 겹침, `DIFFERENT`=안 겹침) — `vsDistrictSalesPeak`는 `peakSalesHourBand`와,
`vsDistrictFootTrafficPeak`는 `peakFootTrafficHourBand`와 짝이라는 것도 명시한다.
**두 필드가 없으면(우리 매장의 피크 시간을 계산할 수 없었던 경우) 밴드 값만
그대로 전달하고, 우리 매장과 비교해 "같다/다르다"를 직접 판단해 말하지 말라고도
명시한다** — 비교 필드를 안 보낸 건 "계산 불가"를 뜻하지, 모델이 대신 추정해도
된다는 뜻이 아니다(별도 검토, 2026-10-21(5)).

`VERSION` 상수를 오늘 날짜로 올린다.

## A. `salesSummary` 선발 안정성 — 측정 후 판단

`_summary_score`(=`|vsPrevPeriod|×3`)는 매출 변동이 크지 않은 평범한 달엔 다른 축에
구조적으로 밀린다(#208 실측: vsPrevPeriod −7.2%일 때 0.216로 7개 중 6위). 상권이
선정되려면 `salesSummary` 자체가 먼저 뽑혀야 하므로, 이 불안정성이 곧 상권 노출율의
상한이 된다.

**하지 않는 것**: `_summary_score`에 임의의 하한값(예: 상권 있으면 최소 0.3 보장)을
추가하지 않는다. 계산해보면 #208의 "전부있음" 사례(weekdaySales 0.379)조차 못 이기고,
하한을 그 이상으로 올리면 PR #161에서 고친 문제("격차 점수가 거의 고정값이라 매달
1위") — 즉 득표용 숫자를 추측으로 끼워 넣어 다른 축을 상시로 밀어내는 재발 패턴이 될
위험이 있다.

**하는 것**: 설계 그대로 구현하고, `devtools/grade.py`에 측정 항목을 **두 개로
나눠** 추가한다(둘 다 이번 구현 범위에 포함) — 분모가 다른 두 원인을 하나로 세면
안 된다는 지적(설계 리뷰, 헥터)을 반영했다: 숙주(`salesSummary`)가 그 달 안 뽑힌
건 설계상 정상(조건부 노출)이고, 뽑혔는데 상권 값을 안 쓴 건 진짜 결함이다.

- `salesSummary_선정률`: 분모 = **전체 요청**. `assign()` 결과에 `salesSummary`가
  들어있는 비율.
- `hourlySales_선정률`: 분모 = **전체 요청**. 같은 방식으로 `hourlySales` 쪽도
  짝을 맞춘다 — 매출요약 쪽만 선정률을 재면 시간대 번들링이 실제로 효과가
  있었는지 비교할 기준이 없다.
- `상권_평균매출_반영`: 분모 = district 게이트를 통과하고 **`salesSummary`가
  선정된 요청만**. 그 안에서 `districtAvgMonthlySalesPerCafe` 값이 실제 생성
  문장에 안 보이면 실패 — **값이 보여도 비교 방향(`vsDistrictAvg`)이 반대로
  서술되면 실패로 센다.** "언급됐는지"만 보면 숫자는 맞는데 방향이 틀린 오귀속을
  놓친다.
- `상권_피크밴드_반영`: 분모 = district 게이트 통과 + **`hourlySales`가 선정된
  요청만**. `peakSalesHourBand`·`peakFootTrafficHourBand` **둘 다** 문장에
  인용돼야 통과다 — 하나만 설명하고 다른 하나를 빠뜨리면 실패로 센다(아래
  "왜 둘 다 요구하나" 참고). 둘 다 인용됐다면 비교 필드(`vsDistrictSalesPeak`/
  `vsDistrictFootTrafficPeak`)가 있는 쪽만 방향이 반대로 서술되지 않았는지도
  본다. 비교 필드가 없는 경우(우리 매장 피크를 계산 못 한 달, 위 핵심 설계
  2번 참고)는 방향을 요구하지 않고 둘 다 인용됐는지만 본다.

**왜 둘 다 요구하나(2026-10-21(6), 재검토로 되돌림).** 한 번은 "하나라도
보이면 통과"로 완화했었다 — "한 문장엔 근거 하나만"이라는 밀도 원칙과 충돌한다고
판단해서였다. 그런데 이 원칙은 **축 사이**(salesSummary vs hourlySales처럼
서로 다른 근거 축)에 적용되는 것이고, `hourlySales` candidate 자체가 두 밴드·두
비교 필드를 **같은 한 문장**에 묶어서 넘긴다(`vsDistrictAvg`가
`districtAvgMonthlySalesPerCafe`를 salesSummary 문장에 묶는 것과 같은 구조,
위 핵심 설계 1번 참고) — 번들 안에서 일부만 말하고 나머지를 빠뜨리는 건 밀도
원칙과 무관한 **진짜 결함**이다. 그래서 "둘 다 언급 + 둘 다 방향 정확"을
요구하는 단일 지표로 되돌렸다.

`devtools/grade.py::_rates`는 분모를 항상 전체 요청 수로 쓴다 — 조건부 항목을
그대로 그 집계에 끼워 넣으면 실제보다 낮게 보인다(`카드_개수_일치`가 3장을
하드코딩해 시간대없음 케이스를 결함으로 세던 사고, #178과 같은 모양). 그래서
`상권_평균매출_반영`·`상권_피크밴드_반영`은 `_rates` 공통 분모를 쓰지 않고 이
항목만 조건부 분모로 따로 집계한다(구현은 `None` 반환 + `devtools/bench.py`
쪽 분모 처리로 아래 "테스트 계획" 참고).

**측정값의 한계**: `salesSummary_선정률`/`hourlySales_선정률`은 `assign()`의
실제 선정 결과가 아니라, 생성된 문장에 그 축의 수치가 등장했는지로 추정한
값이다(`_axis_selected`, 텍스트 기반 근사치) — "선택은 됐는데 모델이 수치를
생략"하거나 "선택 안 됐는데 다른 카드 설명에서 우연히 같은 숫자가 나오는" 경우
둘 다 못 가린다. `devtools/bench.py`는 `insight_focus.assign()`을 이미 다른
용도로 import하고 있어 실제 선정 축을 나란히 찍는 것도 가능하지만, 이번 범위에는
안 넣는다 — 이 한계를 문서에 남겨 두고, 측정값과 실제 선정이 크게 벌어지면
그때 추가한다.

실제로 `--n 20`으로 돌려서 이 네 비율(선정률 2개 + 반영률 2개)의 실측값을
확인하는 건 머지 후 다음 단계다. 측정 결과가 낮으면 그때 숙주 교체나 점수 조정을
다시 연다(아래 "다음 단계"의 판단 기준 참고).

## B. `basisQuarter` 접지 누수 측정

basisQuarter를 어느 focus 블록에도 안 넣기로 했지만(위 "다루지 않는 필드"), 실측으로
확인된 구멍이 있다 — `_metric_numbers`가 문자열에서 3자리 이상 숫자를 뽑는 동작(#191)
때문에, 전체 요청 metrics 어딘가(예: basisQuarter 자체, 또는 다른 연도 표기)에 "2026"
같은 값이 존재하면 `UNGROUNDED_NUMBER` 검사가 그걸 "접지됨"으로 본다 — 모델이 분기를
지어내 인용해도 걸리지 않을 수 있다.

**하지 않는 것**: 지금 당장 차단 규칙(새 `_INSIGHT_BLOCKING` 사유)을 추가하지 않는다
— 인사이트는 이미 필드 밀도가 가장 빠듯한 영역이고(아래 트레이드오프 참고), 검증 없이
차단을 늘리면 "막고 있다고 믿었는데 0개 적중"(`VAGUE_ACTION` 전례) 같은 사고가 반복될
수 있다.

**하는 것**: `devtools/grade.py`에 측정 항목을 추가한다. 분기 패턴(`\d{4}Q[1-4]`
등)을 인용한 문장을 찾되, 다음 둘을 구분해서 센다 — ① 그 값이 **요청의 실제
`basisQuarter`와 일치**하는 경우(접지는 됐지만 설계상 보내지 않기로 한 걸 모델이
어디서 주워 쓴 "누수"), ② 그 값이 **다른 값**인 경우(순수 날조, 더 심각함).

측정 항목도 "A"와 같은 이유로 분모를 분리한다 — ① 인용 자체의 빈도
(`상권_분기_인용됨`, 분모 = 전체 요청)와 ② 인용했을 때의 정확도
(`상권_분기_날조_없음`, 분모 = **분기를 실제로 인용한 요청만**)는 서로 다른
질문이다. 인용 안 한 요청(설계상 정상 — 애초에 안 보냈으니 안 쓰는 게 맞다)을
"날조 없음" 쪽 분모에 그대로 끼워 넣으면, 인용이 드물고 그중 절반이 날조여도
전체 비율은 거의 100%로 보인다 — "A"에서 고친 것과 같은 희석 문제다. 7차 측정
결과를 보고 차단 규칙 도입 여부를 그때 결정한다.

## 데이터 흐름 검증 (구현 전 이미 확인함)

"선발 로직 문제"와 "선발 후 프롬프트 전달 문제"가 별개 원인일 수 있다는 우려가
있었다 — 코드로 확인했다. `app/services/insight.py::generate()`는 `assign_focus()`가
돌려준 dict를 중간 필터링 없이 그대로 `json.dumps`해서 프롬프트에 넣는다
(`insight_prompt.build()`). 즉 focus 블록에 포함되기만 하면 프롬프트까지 손실 없이
전달된다 — 번들링만으로 충분하고 별도 플러밍 수정은 필요 없다.

## 예시 (변경 전후 비교)

구체적 전/후 비교 3개 시나리오(시간대 축이 뽑히는 달 / 매출요약이 뽑히는 달 / 둘 다
안 뽑히는 달)는 세션 대화에서 검토 완료 — 핵심은 **조건부 노출**이다. `salesSummary`·
`hourlySales` 중 하나라도 그 달 상위 `maxInsightCount` 안에 들면 상권 정보가 묻어
나오고, 둘 다 못 들면(categorySales·menuRankings·salesTrend가 더 강한 달) 상권은
이번 설계에서도 여전히 안 보인다 — 이게 "보장 노출"이 아니라 "번들링"을 선택한 데
따른 트레이드오프다(사용자 확인 완료, 아래 트레이드오프 절 참고).

## 트레이드오프

- **조건부 노출 유지, 특히 salesSummary 쪽이 더 자주 걸림**: salesSummary·hourlySales
  둘 다 그 달 선정되지 않으면 상권 정보는 (게이트를 통과해도) 노출되지 않는다. #208
  실측상(인사이트 4개 케이스) `hourlySales`는 후보로 있을 때 선정률이 높은 편(후보
  2/4 · 뽑힘 2, 있으면 항상 선정)인 반면 `salesSummary`는 후보 4/4 중 3만 선정돼
  매출 변동이 커야만 이긴다 — **상권의 핵심 수치(`districtAvgMonthlySalesPerCafe`)가
  피크 시간대 정보보다 더 자주 빠질 걸로 예상된다.**(정정: 초안에 "5/6, #207"로 인용한
  건 솔루션 `hourlyProfile`의 수치였다 — 인사이트 `hourlySales`와 다른 축이다. 결론
  자체는 바뀌지 않지만, 인사이트 케이스가 4개뿐이라 둘 다 비율로 말하기엔 표본이
  얇다 — "다음 단계"의 `--n 20` 실측으로 보강한다.) "데이터 있으면 무조건 보여준다"는
  보장하지 않는다 — 전용 슬롯 예약 대신 번들링을 택한 데 따른 의도된 트레이드오프이고,
  정확한 빈도는 "A" 절의 측정으로 확정한다.
- **필드 밀도 증가**: `salesSummary` 번들은 필드 5개(기존) + 2개(상권 평균·비교
  방향) = 7개, `hourlySales` 번들은 행별 수치(시간대 2~4행) + 문자열 2개가 한 문장
  근거로 들어간다. "지표 많을수록 수치_정확이 떨어진다"는 이 레포의 실측 전제가 있고,
  인사이트는 이미 A40 6차 기준 `수치_정확` 65.0%로 전 항목 중 가장 약한 지점이라
  여유가 없다 — 적용 후 두 문장 유형의 `수치_정확`을 반드시 측정해야 한다(아래 "다음
  단계").
- **peakSalesHourBand/peakFootTrafficHourBand 활용도 제한**: hourlySales가 그 달
  안 뽑히면 두 밴드 정보는 한 번도 안 쓰인다. 독립 활용(예: 전용 상권 인사이트)은
  이번 범위 밖.
- **오귀속 위험은 비교 방향(`vsDistrictAvg`)·피크 일치 여부(`vsDistrictSalesPeak`/
  `vsDistrictFootTrafficPeak`)를 코드가 미리 계산해 줄였지만, 완전히 없어진 건
  아니다.** 모델이 `vsDistrictAvg=ABOVE`인데 "낮습니다" 같은 반대 어휘를 쓰거나,
  `peakSalesHourBand`/`peakFootTrafficHourBand` 레이블을 서로 바꿔 말할 가능성은
  남아 있다 — 채점기로 검출 가능한지는 "테스트 계획" 참고.

## 테스트 계획

`tests/test_insight_focus.py`:

- `salesSummary`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `districtAvgMonthlySalesPerCafe`·`vsDistrictAvg`가 들어있는지
- `vsDistrictAvg`가 `totalSales > district` → `ABOVE`, `<` → `BELOW`,
  `==` → `EQUAL` 세 경우 모두 정확한지(경계값 포함)
- `hourlySales`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `peakSalesHourBand`/`peakFootTrafficHourBand`/`vsDistrictSalesPeak`/
  `vsDistrictFootTrafficPeak`가 들어있는지
- `vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`가 우리 매장 매출 피크 시간이
  각 밴드 안에 들면 `SAME`, 안 들면 `DIFFERENT`로 정확한지(경계값 포함)
- 영업 중(`menuSales > 0`)인 행이 하나도 없어 피크를 못 구하면(`_store_peak_hour`가
  `None`), `peakSalesHourBand`/`peakFootTrafficHourBand`는 그대로 들어있지만
  `vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`는 focus에 **안 들어있는지**
  (별도 검토, 2026-10-21(5) — "계산 불가"를 `DIFFERENT`로 단정하지 않는지 확인)
- `cafeStoreCount < 3`이거나 `districtAvgMonthlySalesPerCafe <= 0`이면 두 번들
  모두에서 상권 필드가 빠지는지(게이트 재사용 확인)
- `districtBenchmark`가 없으면 기존처럼 두 축이 상권 필드 없이 동작하는지(회귀 없음)
- 독립 `districtBenchmark` candidate가 더 이상 `assign()` 결과에 단독으로 나오지
  않는지(이전 테스트 `test_다른_축이_전부_약하면_상권이_1순위가_된다` 등은 삭제/교체)

`devtools/grade.py` (A·B 측정 항목, 이번 구현 범위에 포함):

- `salesSummary_선정률`/`hourlySales_선정률`: 분모 = 전체 요청. `assign()` 결과에
  각 축이 들어있는 비율(위 "A" 참고)
- `상권_평균매출_반영`: 분모 = district 게이트 통과 + `salesSummary` 선정된 요청만
  (조건 미충족 시 `None` — "테스트 계획" 아래 `devtools/bench.py` 분모 처리 참고).
  `districtAvgMonthlySalesPerCafe` 값이 문장에 실제로 보이고, `vsDistrictAvg`
  방향이 맞는지까지 확인(위 "A" 참고)
- `상권_피크밴드_반영`: 분모 = district 게이트 통과 + `hourlySales` 선정된 요청만
  (조건 미충족 시 `None`). `peakSalesHourBand`·`peakFootTrafficHourBand` **둘
  다** 문장에 보여야 통과 — 하나만 보이면 실패(위 "A" 참고). 둘 다 보인다면
  비교 필드(`vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`)가 있는 쪽만
  방향이 맞는지도 확인
- `상권_분기_인용됨`(분모 = 전체 요청) / `상권_분기_날조_없음`(분모 = 분기를
  실제로 인용한 요청만, 미인용이면 `None`) — 분기 패턴을 인용한 문장 검출 + 요청의
  실제 `basisQuarter`와 일치/불일치 구분(위 "B" 참고)

`devtools/bench.py`: 위 세 조건부 항목(`상권_평균매출_반영`·`상권_피크밴드_반영`·
`상권_분기_날조_없음`)이 `None`을 반환할 수 있게 되면서, `_checks`가 `None`을
그대로 보존하고(`bool()`로 뭉개지 않음) `_rates`가 그 항목만 `None`인 행을
분모에서 빼도록 고친다 — 안 고치면 "해당 없음"이 "결함"으로 잡혀 전체 분모
기준 비율이 실제보다 낮게 보인다(이번 구현 범위에 포함, 설계 리뷰에서 지적).

`devtools/contract_check.py`: 픽스처 구조 변경 없음(districtBenchmark는 여전히
`InsightMetrics` 최상위 필드) — 수정 불필요.

`devtools/bench.py`: 이미 머지된 #208의 "상권있음"·"전부있음" 케이스를 그대로
재사용한다 — 이번 구현에서 새로 안 만들어도 됨.

## 다음 단계 (이번 구현 범위 밖)

- **A 측정**: `salesSummary_선정률`/`hourlySales_선정률`과 `상권_평균매출_반영`/
  `상권_피크밴드_반영`을 #208 케이스로 측정. 측정 결과를 보고 무엇을 볼지 — 아래
  "측정 결과 판단 기준" 참고.
- **B 측정 결과 반영**: `상권_분기_인용됨`/`상권_분기_날조_없음` 비율을 보고 차단
  규칙 도입 여부 결정.
- solution의 `weatherContext` 재검토(#206/#207에서 헥터가 확인한 "밀림" 현상) — 7차
  측정에서 날씨가 실제로 포함된 숫자가 나온 뒤에 별도로 판단한다(헥터 동의).
- `peakSalesHourBand`/`peakFootTrafficHourBand`를 hourlySales 외에 더 활용할지(전용
  상권 인사이트 등).
- BE에 `SeoulDistrictQuarterCollectionScheduler`가 배포 환경에서 최소 1회 성공
  실행돼 `seoul_district_quarter_benchmarks`에 실데이터가 쌓였는지 확인 요청.
- `salesSummary_선정률`/`hourlySales_선정률`이 실제 `assign()` 선정과 얼마나
  벌어지는지 — `devtools/bench.py`가 `insight_focus.assign()`을 직접 호출해
  "실제 선정 축"을 리포트에 같이 찍게 하면 바로 대조할 수 있다(위 "A"의
  "측정값의 한계" 참고. `solution_focus`를 이미 같은 방식으로 import하는 전례가
  있다).

### 측정 결과 판단 기준

처음부터 임의의 합격선을 정하지 않는다 — `--n 20` 결과를 기준선으로 삼고, 아래
조합으로 다음에 뭘 볼지만 미리 정해 둔다.

| 관찰 | 다음에 볼 곳 |
|---|---|
| 선정률(`salesSummary_선정률`/`hourlySales_선정률`)이 낮음 | 숙주가 충분히 안 뽑히는 문제 — 점수식·하한값 재논의("A"의 "하지 않는 것" 참고) |
| 선정률은 괜찮은데 반영률이 낮음 | 모델이 받은 필드를 안 쓰는 문제 — 프롬프트 문구·필드 밀도 재검토 |
| 반영률은 괜찮은데 방향 오류(`_direction_correct` 실패)가 보임 | 비교 방향 계산이나 `_direction_correct`의 어휘 대조 정밀도 재검토 |
| 전후 차이가 불분명함(표본 20개로는 추세가 안 보임) | 같은 입력으로 반복 측정하거나 `--n`을 올려 표본을 늘림 |
