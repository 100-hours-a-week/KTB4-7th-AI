# 상권(districtBenchmark) 인사이트 번들링 설계

## 변경 이력

- 2026-10-21: 초안.
- 2026-10-21(2): 헥터가 벤치 케이스에 상권/날씨를 실제로 넣어 머지한 PR #207·#208로
  초안의 "트레이드오프" 절을 실측으로 재현·보강. `salesSummary`가 숙주로 불안정하다는
  점(아래 "A"), `basisQuarter` 접지 누수(아래 "B"), 번들링 특유의 오귀속 위험(아래
  "C") 세 가지를 반영해 설계를 다시 열었다. 세 항목은 성격이 달라 처리 방식도 다르다
  — A·B는 **추측으로 점수·차단 규칙을 바꾸지 않고 먼저 측정**하고, C는 측정만으로는
  못 잡는 구조적 위험이라 **구현 시점에 바로 예방 조치**를 넣는다.

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

### 2) `hourlySales` + `peakSalesHourBand`/`peakFootTrafficHourBand`

`hourlySales` candidate를 구성할 때, 같은 게이트를 통과하면 두 밴드 필드를 추가한다.

```python
focus = {"hourlySales": _spread_rows(points, "hour")}
if _district_gate(district):
    focus["peakSalesHourBand"] = district["peakSalesHourBand"]
    focus["peakFootTrafficHourBand"] = district["peakFootTrafficHourBand"]
candidates.append((focus, _spread(points) if points else -1.0))
```

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

**하는 것**: 설계 그대로 구현하고, `devtools/grade.py`에 측정 항목
`상권_평균매출_반영`(district 게이트를 통과했는데 `districtAvgMonthlySalesPerCafe`
값이 실제 생성 문장에 안 보이면 실패)을 추가한다 — **이번 구현 범위에 포함.** 실제로
`--n 20`으로 돌려서 (1) `salesSummary` 선정률, (2) 선정됐을 때 상권 비교가 문장에
반영된 비율을 확인하는 건 머지 후 다음 단계다. 측정 결과가 낮으면 그때 숙주 교체나
점수 조정을 다시 연다.

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
어디서 주워 쓴 "누수"), ② 그 값이 metrics 어디에도 **진짜로 없는** 경우(순수 날조,
더 심각함). 7차 측정 결과를 보고 차단 규칙 도입 여부를 그때 결정한다.

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
  실측상 `hourlySales`는 선정률이 높은 편(5/6, #207)인 반면 `salesSummary`는 매출
  변동이 커야만 이긴다 — **상권의 핵심 수치(`districtAvgMonthlySalesPerCafe`)가
  피크 시간대 정보보다 더 자주 빠질 걸로 예상된다.** "데이터 있으면 무조건 보여준다"는
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
- **오귀속 위험은 비교 방향(`vsDistrictAvg`)을 코드가 미리 계산해 줄였지만, 완전히
  없어진 건 아니다.** 모델이 `vsDistrictAvg=ABOVE`인데 "낮습니다" 같은 반대 어휘를
  쓸 가능성은 남아 있다 — 채점기로 검출 가능한지는 "테스트 계획" 참고.

## 테스트 계획

`tests/test_insight_focus.py`:

- `salesSummary`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `districtAvgMonthlySalesPerCafe`·`vsDistrictAvg`가 들어있는지
- `vsDistrictAvg`가 `totalSales > district` → `ABOVE`, `<` → `BELOW`,
  `==` → `EQUAL` 세 경우 모두 정확한지(경계값 포함)
- `hourlySales`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `peakSalesHourBand`/`peakFootTrafficHourBand`가 들어있는지
- `cafeStoreCount < 3`이거나 `districtAvgMonthlySalesPerCafe <= 0`이면 두 번들
  모두에서 상권 필드가 빠지는지(게이트 재사용 확인)
- `districtBenchmark`가 없으면 기존처럼 두 축이 상권 필드 없이 동작하는지(회귀 없음)
- 독립 `districtBenchmark` candidate가 더 이상 `assign()` 결과에 단독으로 나오지
  않는지(이전 테스트 `test_다른_축이_전부_약하면_상권이_1순위가_된다` 등은 삭제/교체)

`devtools/grade.py` (A·B 측정 항목, 이번 구현 범위에 포함):

- `상권_평균매출_반영`: district 게이트 통과 + `salesSummary` 선정 시
  `districtAvgMonthlySalesPerCafe` 값이 문장에 실제로 보이는지(위 "A" 참고)
- 분기 패턴을 인용한 문장 검출 + 요청의 실제 `basisQuarter`와 일치/불일치 구분(위 "B"
  참고)
- (가능하면) `vsDistrictAvg`와 반대 방향 어휘("낮습니다"인데 ABOVE 등)를 검출하는
  측정 항목 — 정규식만으로 완전히 잡기는 어려울 수 있어, 1차는 "검출 시도" 수준으로
  두고 실측 후 정밀도를 본다.

`devtools/contract_check.py`: 픽스처 구조 변경 없음(districtBenchmark는 여전히
`InsightMetrics` 최상위 필드) — 수정 불필요.

`devtools/bench.py`: 이미 머지된 #208의 "상권있음"·"전부있음" 케이스를 그대로
재사용한다 — 이번 구현에서 새로 안 만들어도 됨.

## 다음 단계 (이번 구현 범위 밖)

- **A 측정**: `salesSummary` 선정률과, 선정됐을 때 상권 비교 정보가 실제 문장에
  반영된 비율을 #208 케이스로 측정. 결과가 낮으면 숙주 교체·점수 조정 재논의.
- **B 측정 결과 반영**: basisQuarter 누수 비율을 보고 차단 규칙 도입 여부 결정.
- solution의 `weatherContext` 재검토(#206/#207에서 헥터가 확인한 "밀림" 현상) — 7차
  측정에서 날씨가 실제로 포함된 숫자가 나온 뒤에 별도로 판단한다(헥터 동의).
- `peakSalesHourBand`/`peakFootTrafficHourBand`를 hourlySales 외에 더 활용할지(전용
  상권 인사이트 등).
- BE에 `SeoulDistrictQuarterCollectionScheduler`가 배포 환경에서 최소 1회 성공
  실행돼 `seoul_district_quarter_benchmarks`에 실데이터가 쌓였는지 확인 요청.
