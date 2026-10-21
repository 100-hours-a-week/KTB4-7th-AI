# 상권(districtBenchmark) 인사이트 번들링 설계

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

### 1) `salesSummary` + `districtAvgMonthlySalesPerCafe`

`salesSummary` candidate를 구성할 때, 상권 게이트(아래)를 통과하면 focus 블록에
`districtAvgMonthlySalesPerCafe` 한 필드만 추가한다.

```python
focus = {"salesSummary": summary}
if _district_gate(district):
    focus["districtAvgMonthlySalesPerCafe"] = district["districtAvgMonthlySalesPerCafe"]
candidates.append((focus, _summary_score(summary) if summary else -1.0))
```

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
  불일치를 모델이 숫자로 주장하게 두지 않기 위함.
- `cafeStoreCount`: 게이트 판단에만 쓰고 프롬프트에 안 보낸다(기존과 동일).

## 프롬프트 변경 (`app/prompts/insight.py`)

기존 districtBenchmark SYSTEM 규칙("행정동 전체 카페의 월평균 추정매출... 상권
인과 주장 금지")은 내용 그대로 유지한다 — 필드가 어느 문장에 묶이든 규칙 자체는
똑같이 적용돼야 한다. `_DISTRICT_CAUSAL` 채점 정규식(`devtools/grade.py`)도 그대로
쓴다 — 번들링된 문장에도 같은 검사가 적용된다.

`VERSION` 상수를 오늘 날짜로 올린다.

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

- **조건부 노출 유지**: salesSummary·hourlySales 둘 다 그 달 선정되지 않으면 상권
  정보는 (게이트를 통과해도) 노출되지 않는다. "데이터 있으면 무조건 보여준다"는
  보장하지 않는다 — 전용 슬롯 예약 대신 번들링을 택한 데 따른 의도된 트레이드오프다.
- **필드 밀도 증가**: `salesSummary` 번들은 필드 5개(기존) + 1개(상권) = 6개,
  `hourlySales` 번들은 행별 수치(시간대 2~4행) + 문자열 2개가 한 문장 근거로 들어간다.
  "지표 많을수록 수치_정확이 떨어진다"는 이 레포의 실측 전제가 있어, 적용 후 두 문장
  유형의 `수치_정확`을 측정해야 한다(아래 "다음 단계" 참고 — 이번 구현 범위엔 미포함).
- **peakSalesHourBand/peakFootTrafficHourBand 활용도 제한**: hourlySales가 그 달
  안 뽑히면 두 밴드 정보는 한 번도 안 쓰인다. 독립 활용(예: 전용 상권 인사이트)은
  이번 범위 밖.

## 테스트 계획

`tests/test_insight_focus.py`:

- `salesSummary`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `districtAvgMonthlySalesPerCafe`가 들어있는지
- `hourlySales`가 선정될 때, 게이트 통과한 district가 있으면 focus 블록에
  `peakSalesHourBand`/`peakFootTrafficHourBand`가 들어있는지
- `cafeStoreCount < 3`이면 두 번들 모두에서 상권 필드가 빠지는지(기존 게이트 유지)
- `districtBenchmark`가 없으면 기존처럼 두 축이 상권 필드 없이 동작하는지(회귀 없음)
- 독립 `districtBenchmark` candidate가 더 이상 `assign()` 결과에 단독으로 나오지
  않는지(이전 테스트 `test_다른_축이_전부_약하면_상권이_1순위가_된다` 등은 삭제/교체)

`devtools/contract_check.py`: 픽스처 구조 변경 없음(districtBenchmark는 여전히
`InsightMetrics` 최상위 필드) — 수정 불필요.

## 다음 단계 (이번 구현 범위 밖)

- 적용 후 실측: 상권 정보가 실제로 몇 %나 노출되는지, 번들된 문장의 `수치_정확`이
  떨어지는지.
- solution의 `weatherContext` 재검토(#206/#207에서 헥터가 확인한 "밀림" 현상) — 날씨는
  카드 경쟁 구조라 같은 번들링 해법이 그대로 맞는지 별도 판단 필요.
- `peakSalesHourBand`/`peakFootTrafficHourBand`를 hourlySales 외에 더 활용할지(전용
  상권 인사이트 등).
- BE에 `SeoulDistrictQuarterCollectionScheduler`가 배포 환경에서 최소 1회 성공
  실행돼 `seoul_district_quarter_benchmarks`에 실데이터가 쌓였는지 확인 요청.
