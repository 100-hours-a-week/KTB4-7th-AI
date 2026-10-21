# 상권(districtBenchmark) 인사이트 번들링 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `districtBenchmark`를 인사이트의 전용 경쟁 축에서 빼고, `salesSummary`(평균매출
비교)·`hourlySales`(피크 시간대)에 조건부로 번들링해서 "상권이 매달 거의 안 보인다"는
문제를 해결한다.

**Architecture:** `app/services/insight_focus.py::assign()`의 `districtBenchmark` 독립
candidate를 삭제하고, 같은 함수 안에서 `salesSummary`·`hourlySales` candidate를 구성할
때 게이트(`_district_gate`)를 통과하면 관련 필드를 그 focus dict에 추가한다. 매출
비교 방향(`vsDistrictAvg`)과 우리 매장의 매출 피크가 상권 밴드 안에 드는지
(`vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`)는 모델이 계산하지 않고 코드가
미리 결정한다(`district_comparison`·`_store_peak_hour`/`_in_band`). `app/prompts/insight.py`는
새 필드명에 맞춰 규칙 문구를 갱신한다. `devtools/grade.py`에 측정 전용 항목(A: 상권
선정률·반영률 분리, B: basisQuarter 접지 누수)을 추가한다 — 생성을 막지 않는 순수
측정값이다. 조건부 항목(선정 안 됐으면 측정 대상이 아님)은 `None`으로 표시하고,
`devtools/bench.py`가 그 `None`을 분모에서 빼도록 집계 로직도 같이 고친다 — 안
고치면 "선정 안 됨"이 "결함"으로 잡혀 실제보다 낮은 비율이 나온다(설계 리뷰).

**Tech Stack:** Python 3.12, FastAPI, pytest, ruff. 외부 의존성 추가 없음.

## Global Constraints

- 설계 문서: `docs/superpowers/specs/2026-10-21-district-benchmark-bundling-design.md`
  (이 플랜의 모든 결정은 그 문서의 "핵심 설계"·"A"·"B" 절, 그리고 핵심 설계 1)·2)
  안의 "C"(비교 방향 사전 계산·우리 매장 피크 vs 상권 밴드) 하위 절을 따른다)
- 커밋 메시지는 Conventional Commits 영문 소문자 타입, 본문은 한국어(`AGENTS.md`)
- 커밋 메시지·PR 본문에 `Co-Authored-By: Claude` 등 생성 배너를 넣지 않는다(`CLAUDE.md`)
- `app/services/{solution,insight}` 영역만 수정 — `app/api/forecast.py`·
  `app/services/forecast/`는 건드리지 않는다(`AGENTS.md` 담당 경계)
- 금액은 정수, 비율은 소수(`AGENTS.md` 계약 규칙) — 이번 작업은 계약(스키마) 자체를
  바꾸지 않는다(필드 재배치만, `InsightMetrics`/`DistrictBenchmark` 구조 변경 없음)
- 매 태스크 끝에 `uv run pytest`와 `uv run ruff check --fix . && uv run ruff format .`
  가 통과해야 커밋한다
- 모든 코드 주석은 "왜"만 — 비자명한 이유가 있을 때만 한 줄(`AGENTS.md`)

---

## Task 1: `salesSummary`에 상권 평균매출 번들링

**Files:**
- Modify: `app/services/insight_focus.py` (모듈 docstring, `_district_score`/
  `_DISTRICT_SUPPLEMENT_SCORE` 삭제, `district_comparison`·`_district_gate` 추가,
  `assign()` 수정)
- Test: `tests/test_insight_focus.py` (기존 district 테스트 4개 교체)

**Interfaces:**
- Produces: `district_comparison(total_sales: int, district_avg: int) -> str`
  (`"ABOVE"`/`"BELOW"`/`"EQUAL"`), `_district_gate(district: dict | None) -> bool`
  — Task 2가 그대로 재사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_insight_focus.py`의 기존 district 관련 블록(`DISTRICT`·`_FLAT_METRICS`
정의와 그 아래 테스트 4개: `test_다른_축이_전부_약하면_상권이_1순위가_된다`,
`test_다른_축이_뚜렷하면_상권이_밀린다`, `test_표본이_너무_적은_상권은_배정되지_않는다`,
`test_상권_필드가_없으면_배정되지_않는다`)를 전부 지우고 아래로 교체한다.

```python
from app.services.insight_focus import assign, district_comparison

# (파일 상단 import 줄을 이 내용으로 바꾼다 — 기존은 `from app.services.insight_focus
# import assign` 한 줄이었다)
```

```python
DISTRICT = {
    "basisQuarter": "2026Q3",
    "districtAvgMonthlySalesPerCafe": 9413000,
    "cafeStoreCount": 133,
    "peakSalesHourBand": "14-17",
    "peakFootTrafficHourBand": "11-14",
}


def test_매장_매출이_상권_평균보다_크면_ABOVE():
    assert district_comparison(10_000_000, 9_413_000) == "ABOVE"


def test_매장_매출이_상권_평균보다_작으면_BELOW():
    assert district_comparison(7_920_000, 9_413_000) == "BELOW"


def test_매장_매출이_상권_평균과_같으면_EQUAL():
    assert district_comparison(9_413_000, 9_413_000) == "EQUAL"


def test_매출요약이_선정되면_상권_평균매출이_같이_묻는다():
    focus = assign({**METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert summary_focus["districtAvgMonthlySalesPerCafe"] == 9413000
    assert summary_focus["vsDistrictAvg"] in ("ABOVE", "BELOW", "EQUAL")


def test_표본이_너무_적은_상권은_매출요약에_안_묻는다():
    """cafeStoreCount 가 1~2 곳이면 평균이 의미가 없다(#157)."""
    district = {**DISTRICT, "cafeStoreCount": 2}
    focus = assign({**METRICS, "districtBenchmark": district}, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert "districtAvgMonthlySalesPerCafe" not in summary_focus


def test_상권_필드가_없으면_매출요약에_안_묻는다():
    focus = assign(METRICS, max_count=4)

    summary_focus = next(item for item in focus if "salesSummary" in item)
    assert "districtAvgMonthlySalesPerCafe" not in summary_focus


def test_독립_상권_축은_더_이상_없다():
    """districtBenchmark 를 그 자체로 담은 focus 블록이 나오면 안 된다(#209)."""
    focus = assign({**METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    assert not any(set(item) == {"districtBenchmark"} for item in focus)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_insight_focus.py -v`
Expected: `district_comparison` import 실패(`ImportError`) + 나머지 district 테스트
전부 실패(`districtAvgMonthlySalesPerCafe`/`vsDistrictAvg` 키가 없음).

- [ ] **Step 3: 모듈 docstring에 변경 이력 추가**

`app/services/insight_focus.py` 맨 위 docstring, 기존 `2026-10-16(PR #161 리뷰,
헥터): ...` 문단 바로 뒤에 이어 붙인다(문단 끝의 `"""` 앞):

```python
2026-10-21(#209, PR #207·#208 실측): districtBenchmark 를 전용 근거 축에서 완전히
뺐다. 인사이트는 상권이 들어오기 전부터 이미 6 개 축이 경쟁 중이었는데, 고정 보충값
0.3 으로는 여전히 자주 밀렸다(#208 "전부있음" 실측: districtBenchmark 0.300 이 7 개
중 5 위). 전용 축 대신 salesSummary(평균매출 비교)·hourlySales(피크 시간대)에
조건부로 끼워 넣는다 — districtBenchmark 라는 중첩 객체는 더 이상 모델에게 안 보이고,
대신 평평한 필드(districtAvgMonthlySalesPerCafe·vsDistrictAvg·peakSalesHourBand·
peakFootTrafficHourBand)로 쪼개져 두 축에 나뉜다. 비교 방향(vsDistrictAvg)은 코드가
미리 계산한다 — solution_focus.peak_ratios() 와 같은 이유로, 두 숫자 다 지표에 있어
UNGROUNDED_NUMBER 로 못 잡는 "방향 반전" 오류를 막는다.
```

- [ ] **Step 4: `_district_score`·`_DISTRICT_SUPPLEMENT_SCORE` 삭제, 새 헬퍼 추가**

`_DISTRICT_SUPPLEMENT_SCORE = 0.3` 상수 줄과 그 위 주석 2줄을 삭제한다.

`_district_score` 함수 전체(현재 102~115번째 줄)를 아래로 교체한다:

```python
def district_comparison(total_sales: int, district_avg: int) -> str:
    """상권 평균 대비 매장 매출의 방향을 코드가 미리 계산한다.

    두 숫자 다 지표에 실재해 UNGROUNDED_NUMBER 게이트로는 못 잡는 오류다 — 모델이
    직접 비교하다 방향을 뒤집어 말할 수 있다. solution_focus.peak_ratios() 가 "어느
    두 시각 사이 배수인지"를 코드가 계산해 넘기는 것과 같은 이유다.
    """
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


def _district_gate(district: dict | None) -> bool:
    """표본이 너무 적은 상권(1~2 곳)은 평균이 의미가 없어 후보에서 뺀다(#157).

    salesSummary·hourlySales 두 번들링 지점이 이 게이트를 공유한다.
    """
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0
```

- [ ] **Step 5: `assign()`에서 `salesSummary` candidate에 번들링**

```python
def assign(metrics: dict, max_count: int) -> list[dict]:
    """문장 순서대로의 근거 지표를 돌려준다. 최대 max_count 개.

    지표가 max_count 종이 안 되면 그만큼만 돌려준다 — 없는 근거로 문장을 만들게 하느니
    개수를 줄이는 편이 낫다. 호출부는 app/services/insight.py::generate 다.
    """
    summary = metrics.get("salesSummary") or {}
    district = metrics.get("districtBenchmark")

    summary_focus: dict = {"salesSummary": summary}
    if _district_gate(district):
        summary_focus["districtAvgMonthlySalesPerCafe"] = district["districtAvgMonthlySalesPerCafe"]
        summary_focus["vsDistrictAvg"] = district_comparison(
            summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"]
        )

    candidates: list[tuple[dict, float]] = [
        (summary_focus, _summary_score(summary) if summary else -1.0),
    ]
    # 점수는 받은 행 전부로 내고, 프롬프트에 넣는 행만 줄인다.
    series_axes = (("salesTrend", "date"), ("weekdaySales", "dayOfWeek"), ("hourlySales", "hour"))
    for key, order_key in series_axes:
        points = metrics.get(key) or []
        focus = {key: _spread_rows(points, order_key)}
        candidates.append((focus, _spread(points) if points else -1.0))
    for key in ("categorySales", "menuRankings"):
        points = metrics.get(key) or []
        candidates.append(({key: _share_rows(points)}, _share_score(points) if points else -1.0))

    usable = [(focus, score) for focus, score in candidates if score >= 0.0]
    usable.sort(key=lambda pair: pair[1], reverse=True)
    return [focus for focus, _ in usable[:max_count]]
```

(`hourlySales`의 피크 시간대 번들링은 Task 2에서 `series_axes` 루프에 추가한다 —
이 Step에서는 아직 건드리지 않는다. 기존 `district = metrics.get("districtBenchmark")`
+ `candidates.append(({"districtBenchmark": district}, _district_score(district)))`
두 줄은 완전히 삭제됐다.)

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_insight_focus.py -v`
Expected: 전부 PASS.

- [ ] **Step 7: 린트 + 커밋**

```bash
uv run ruff check --fix . && uv run ruff format .
git add app/services/insight_focus.py tests/test_insight_focus.py
git commit -m "feat: 상권 평균매출을 매출요약 문장에 번들링한다

districtBenchmark 전용 경쟁 축을 없애고, 게이트를 통과하면
districtAvgMonthlySalesPerCafe·vsDistrictAvg 를 salesSummary candidate 에 끼워
넣는다. 비교 방향은 코드가 미리 계산해 모델의 방향 반전 오류를 막는다(#209)."
```

---

## Task 2: `hourlySales`에 상권 피크 시간대 번들링

**설계가 한 번 바뀌었다(아래 Step 3 참고)**: 처음엔 "두 상권 밴드끼리 겹치는지"
(`districtPeakAlignment`)를 계산하려 했지만, 상권 내부 두 지표(매출·유동인구)의
인과를 암시할 위험이 있고 "매장 쪽 대응 데이터가 없다"던 전제도 틀렸다 —
`hourlySales.menuSales`로 우리 매장의 매출 피크 시간을 이미 계산할 수 있다. 그래서
"우리 매장의 매출 피크가 상권의 각 밴드 안에 드는지"(`vsDistrictSalesPeak`/
`vsDistrictFootTrafficPeak`)로 바꿨다 — `vsDistrictAvg`와 같은 "내 수치 vs 상권
수치" 구조라 인과 암시가 없다(설계 문서 핵심 설계 2번 참고).

**Files:**
- Modify: `app/services/insight_focus.py` (`assign()`의 `series_axes` 루프)
- Test: `tests/test_insight_focus.py`

**Interfaces:**
- Consumes: Task 1의 `_district_gate(district: dict | None) -> bool`, `assign()`
  안의 `district` 지역변수.
- Produces: `_store_peak_hour(points: list[dict]) -> int | None`,
  `_in_band(hour: int | None, band: str) -> bool` — Task 4의 `상권_피크밴드_반영`
  측정이 같은 계산을 참고한다(직접 재사용은 안 함, grade.py 는 app 비import
  전제라 복제한다).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_insight_focus.py`에 아래를 추가한다(Task 1에서 추가한 테스트들 뒤):

```python
HOURLY_METRICS = {
    **METRICS,
    "hourlySales": [
        {"dayType": "WEEKDAY", "hour": 11, "menuSales": 850000, "orderCount": 95},
        {"dayType": "WEEKDAY", "hour": 19, "menuSales": 210000, "orderCount": 24},
    ],
}


def test_시간대_축이_선정되면_상권_피크시간대가_같이_묻는다():
    """우리 매장 매출 피크(11시)는 peakSalesHourBand(14-17)엔 안 들고
    peakFootTrafficHourBand(11-14)엔 든다."""
    focus = assign({**HOURLY_METRICS, "districtBenchmark": DISTRICT}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["peakSalesHourBand"] == "14-17"
    assert hourly_focus["peakFootTrafficHourBand"] == "11-14"
    assert hourly_focus["vsDistrictSalesPeak"] == "DIFFERENT"
    assert hourly_focus["vsDistrictFootTrafficPeak"] == "SAME"


def test_우리_매출_피크가_상권_매출_피크와_겹치면_SAME():
    district = {**DISTRICT, "peakSalesHourBand": "10-13"}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert hourly_focus["vsDistrictSalesPeak"] == "SAME"


def test_상권_필드가_없으면_시간대_축에_안_묻는다():
    focus = assign(HOURLY_METRICS, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert "peakSalesHourBand" not in hourly_focus
    assert "peakFootTrafficHourBand" not in hourly_focus
    assert "vsDistrictSalesPeak" not in hourly_focus
    assert "vsDistrictFootTrafficPeak" not in hourly_focus


def test_표본이_너무_적은_상권은_시간대_축에_안_묻는다():
    district = {**DISTRICT, "cafeStoreCount": 2}
    focus = assign({**HOURLY_METRICS, "districtBenchmark": district}, max_count=4)

    hourly_focus = next(item for item in focus if "hourlySales" in item)
    assert "peakSalesHourBand" not in hourly_focus
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_insight_focus.py -v`
Expected: 새 테스트 4개 FAIL(`peakSalesHourBand`/`vsDistrictSalesPeak` 키가 없음).
나머지는 PASS.

- [ ] **Step 3: `series_axes` 루프에 번들링 추가**

`assign()` 안의 아래 블록을

```python
    series_axes = (("salesTrend", "date"), ("weekdaySales", "dayOfWeek"), ("hourlySales", "hour"))
    for key, order_key in series_axes:
        points = metrics.get(key) or []
        focus = {key: _spread_rows(points, order_key)}
        candidates.append((focus, _spread(points) if points else -1.0))
```

이렇게 바꾼다(`_store_peak_hour`·`_in_band`는 `assign()` 바로 앞, 모듈 레벨에
정의한다):

```python
def _store_peak_hour(points: list[dict]) -> int | None:
    """영업 중(menuSales > 0)인 행 중 매출이 가장 높은 시간. 없으면 None."""
    selling = _selling(points)
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int | None, band: str) -> bool:
    """우리 매장 피크 시간이 상권 밴드("HH-HH") 안에 드는지. 밴드 형식은 BE
    DistrictBenchmarkService.VALID_HOUR_BANDS 가 고정 집합으로 보장한다.
    """
    if hour is None:
        return False
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end
```

```python
    series_axes = (("salesTrend", "date"), ("weekdaySales", "dayOfWeek"), ("hourlySales", "hour"))
    for key, order_key in series_axes:
        points = metrics.get(key) or []
        focus = {key: _spread_rows(points, order_key)}
        if key == "hourlySales" and _district_gate(district):
            peak_hour = _store_peak_hour(points)
            focus["peakSalesHourBand"] = district["peakSalesHourBand"]
            focus["peakFootTrafficHourBand"] = district["peakFootTrafficHourBand"]
            focus["vsDistrictSalesPeak"] = (
                "SAME" if _in_band(peak_hour, district["peakSalesHourBand"]) else "DIFFERENT"
            )
            focus["vsDistrictFootTrafficPeak"] = (
                "SAME" if _in_band(peak_hour, district["peakFootTrafficHourBand"]) else "DIFFERENT"
            )
        candidates.append((focus, _spread(points) if points else -1.0))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_insight_focus.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 린트 + 커밋**

```bash
uv run ruff check --fix . && uv run ruff format .
git add app/services/insight_focus.py tests/test_insight_focus.py
git commit -m "feat: 상권 피크 시간대를 시간대별 매출 문장에 번들링한다

게이트를 통과하면 peakSalesHourBand·peakFootTrafficHourBand 를 hourlySales
candidate 에 끼워 넣는다. 우리 매장의 매출 피크가 각 밴드 안에 드는지
(vsDistrictSalesPeak·vsDistrictFootTrafficPeak)도 코드가 미리 계산해 모델이
두 레이블을 바꿔 말할 위험을 줄인다(#209)."
```

---

## Task 3: 프롬프트 규칙 문구 갱신

**Files:**
- Modify: `app/prompts/insight.py` (SYSTEM, 모듈 docstring, VERSION)
- Modify: `tests/test_prompts.py` (VERSION 단언)

**Interfaces:**
- Consumes: Task 1·2에서 만든 필드명(`districtAvgMonthlySalesPerCafe`·
  `vsDistrictAvg`·`peakSalesHourBand`·`peakFootTrafficHourBand`·
  `vsDistrictSalesPeak`·`vsDistrictFootTrafficPeak`) — 프롬프트 문구가 이 이름들을
  직접 가리킨다.

- [ ] **Step 1: 실패하는 테스트로 VERSION 고정**

`tests/test_prompts.py` 140번째 줄을

```python
    assert insight.VERSION == "2026-10-15"
```

이렇게 바꾼다:

```python
    assert insight.VERSION == "2026-10-21"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_prompts.py -k 버전 -v`
Expected: FAIL (`insight.VERSION == "2026-10-15"`, `"2026-10-21"` 아님).

- [ ] **Step 3: SYSTEM 규칙 문구 교체**

`app/prompts/insight.py`의 SYSTEM 안 아래 블록(현재 70~73번째 줄)을

```python
districtBenchmark 는 매장이 속한 행정동의 커피·음료 업종 점포당 월평균 추정매출입니다
(해당 분기 기준 추정치). 매장 개별 실적이 아니므로 "우리 매장" 성과처럼 쓰지 마세요.
"상권이 좋아서/나빠서 매출이 ~했다"처럼 상권 상태가 매출에 영향을 줬다고 주장하지 마세요
— 그런 인과를 뒷받침할 지표가 없습니다.
```

이렇게 바꾼다:

```python
districtAvgMonthlySalesPerCafe 는 매장이 속한 행정동의 커피·음료 업종 점포당 월평균
추정매출입니다(참고용 추정치). 매장 개별 실적이 아니므로 "우리 매장" 성과처럼 쓰지
마세요. vsDistrictAvg 가 있으면 그 값을 그대로 따르고 직접 비교·계산하지 마세요 —
ABOVE 는 상권 평균보다 높음, BELOW 는 낮음, EQUAL 은 같음을 뜻합니다.
peakSalesHourBand 는 반드시 "매출이 가장 많은 시간대"로, peakFootTrafficHourBand 는
반드시 "유동인구가 가장 많은 시간대"로만 서술하세요 — 두 레이블을 바꿔 쓰지 마세요.
vsDistrictSalesPeak·vsDistrictFootTrafficPeak 가 있으면 그 값을 그대로 따르고 직접
비교하지 마세요 — SAME 은 우리 매장의 매출 피크 시간대가 그 밴드와 겹침, DIFFERENT 는
안 겹침을 뜻합니다(vsDistrictSalesPeak 는 peakSalesHourBand, vsDistrictFootTrafficPeak
는 peakFootTrafficHourBand 와 짝입니다). "상권이 좋아서/나빠서 매출이 ~했다"처럼
상권 상태가 매출에 영향을 줬다고 주장하지 마세요 — 그런 인과를 뒷받침할 지표가
없습니다.
```

- [ ] **Step 4: 모듈 docstring에 변경 이력 추가, VERSION 갱신**

기존 `2026-10-15: districtBenchmark(상권, #157)가...` 문단 뒤에 이어 붙인다:

```python
2026-10-21(#209): districtBenchmark 중첩 객체를 더는 보내지 않는다. 대신
districtAvgMonthlySalesPerCafe·vsDistrictAvg 는 salesSummary 문장에,
peakSalesHourBand·peakFootTrafficHourBand·vsDistrictSalesPeak·
vsDistrictFootTrafficPeak 는 hourlySales 문장에 조건부로 묶여 들어온다
(app/services/insight_focus.py 참고). 비교 방향(vsDistrictAvg)·피크 일치 여부
(vsDistrictSalesPeak·vsDistrictFootTrafficPeak)는 코드가 미리 계산해 주므로
모델에게는 "그대로 따르라"고만 지시한다 — 두 밴드 레이블을 바꿔 말할 위험(설계
리뷰)도 레이블 고정 문구로 같이 막는다.
```

`VERSION = "2026-10-15"`를 `VERSION = "2026-10-21"`로 바꾼다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: 전부 PASS.

- [ ] **Step 6: 린트 + 커밋**

```bash
uv run ruff check --fix . && uv run ruff format .
git add app/prompts/insight.py tests/test_prompts.py
git commit -m "feat: 인사이트 프롬프트 규칙을 상권 번들링 필드명에 맞춘다

districtBenchmark 중첩 객체 대신 districtAvgMonthlySalesPerCafe·vsDistrictAvg·
peakSalesHourBand·peakFootTrafficHourBand·vsDistrictSalesPeak·
vsDistrictFootTrafficPeak 평평한 필드를 가리키도록 SYSTEM 규칙을 고친다. VERSION
2026-10-15 → 2026-10-21(#209)."
```

---

## Task 4: 채점기 측정 A — 숙주 선정률과 상권 반영률을 분리한다

**설계 리뷰 반영(헥터)**: "숙주(salesSummary/hourlySales)가 그 달 안 뽑힌 것"(설계상
정상, 조건부 노출)과 "뽑혔는데 상권 값을 안 쓴 것"(진짜 결함)을 하나로 세면 못
가린다. 분모가 다른 두 측정 항목으로 나눈다 — 그리고 `devtools/bench.py::_rates`가
분모를 항상 전체 요청 수로 쓰는 전제도 고친다(안 고치면 조건부 항목이 실제보다
낮게 보인다).

**Files:**
- Modify: `devtools/grade.py`
- Modify: `devtools/bench.py` (`_checks`·`_rates`·`_report`)
- Test: `tests/test_grade.py`, `tests/test_bench.py`

**Interfaces:**
- Produces: `grade._district_gate(district: dict | None) -> bool`(app 쪽과 동일 로직
  복사본), `grade._axis_selected(body: str, metrics: dict, key: str) -> bool`,
  `grade._comparison(total_sales: int, district_avg: int) -> str`(app 쪽
  `district_comparison` 복사본), `grade._store_peak_hour(points: list[dict]) ->
  int | None`·`grade._in_band(hour: int | None, band: str) -> bool`(app 쪽 복사본),
  `grade._direction_correct(body: str, comparison: str) -> bool`,
  `grade._district_avg_reflected(body: str, metrics: dict) -> bool | None`,
  `grade._district_band_reflected(body: str, metrics: dict) -> bool | None`.
  `grade_insight()` 결과 dict에 `"salesSummary_선정률"`·`"hourlySales_선정률"`
  (둘 다 bool)·`"상권_평균매출_반영"`·`"상권_피크밴드_반영"`(둘 다 bool | None) 키
  추가. `bench._checks`가 `None` 값을 그대로 보존(`bool()`로 뭉개지 않음),
  `bench._rates`가 `None`을 그 항목의 분모에서 뺀다.

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_grade.py`**

상단 import에 `from app.services import insight_focus` 를 추가한다. 그리고
`test_카드_개수는_배정된_장수로_채점한다` 함수 뒤(파일 끝 근처)에 아래를 추가한다.
아래 상권 관련 테스트들은 `_insight()` 헬퍼(내부에 고정된 `INS_METRICS`를 쓴다)에
안 묶이고 `grade.grade_insight()`를 직접 불러 자체 metrics를 쓴다 — 어떤 값이
ABOVE/BELOW가 되는지 추측하지 않고 테스트 안에서 직접 통제한다:

```python
_DISTRICT_METRICS = {
    "salesSummary": {
        "totalSales": 7920000,
        "menuSales": 7480000,
        "orderCount": 923,
        "averageOrderValue": 8581,
        "vsPrevPeriod": 0.042,
    },
    "hourlySales": [
        {"dayType": "WEEKDAY", "hour": 14, "menuSales": 500000, "orderCount": 60},
    ],
    "districtBenchmark": {
        "basisQuarter": "2026Q3",
        "districtAvgMonthlySalesPerCafe": 9413000,
        "cafeStoreCount": 133,
        "peakSalesHourBand": "14-17",
        "peakFootTrafficHourBand": "11-14",
    },
}


def _district_insight(*sentences: str, metrics: dict = _DISTRICT_METRICS) -> dict:
    return grade.grade_insight(json.dumps({"insights": list(sentences)}), metrics)


def test_채점기의_상권_게이트가_서비스와_같다():
    """app 을 import 하지 않으려고 복사해 둔 함수다 — 어긋나면 채점 결과가 서비스와
    달라진다(devtools/grade.py::_district_gate 참고)."""
    cases = [
        None,
        {},
        {"cafeStoreCount": 2, "districtAvgMonthlySalesPerCafe": 9413000},
        {"cafeStoreCount": 133, "districtAvgMonthlySalesPerCafe": 0},
        {"cafeStoreCount": 133, "districtAvgMonthlySalesPerCafe": 9413000},
    ]
    for district in cases:
        assert grade._district_gate(district) == insight_focus._district_gate(district)


def test_채점기의_비교_방향이_서비스와_같다():
    cases = [(10_000_000, 9_413_000), (7_920_000, 9_413_000), (9_413_000, 9_413_000)]
    for total_sales, district_avg in cases:
        assert grade._comparison(total_sales, district_avg) == insight_focus.district_comparison(
            total_sales, district_avg
        )


def test_매출요약이_선정되면_선정률이_참이다():
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했습니다.")

    assert result["salesSummary_선정률"] is True


def test_매출요약이_선정_안_되면_선정률이_거짓이다():
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["salesSummary_선정률"] is False


def test_매출요약이_선정되고_상권_평균을_방향까지_맞게_인용하면_반영으로_통과한다():
    """totalSales(792만)가 districtAvgMonthlySalesPerCafe(941.3만)보다 작으므로
    BELOW다 — "낮습니다"가 맞는 방향이다."""
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 낮습니다.")

    assert result["상권_평균매출_반영"] is True


def test_상권_평균_수치는_맞는데_방향이_반대면_걸린다():
    """숫자는 지표에 있는 값이라 UNGROUNDED_NUMBER 로는 못 잡는 오류다(설계 'C')."""
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 높습니다.")

    assert result["상권_평균매출_반영"] is False


def test_매출요약이_선정됐는데_상권_평균이_안_보이면_걸린다():
    result = _district_insight("총 매출은 전기 대비 4.2% 증가했습니다.")

    assert result["상권_평균매출_반영"] is False


def test_매출요약이_선정_안_되면_상권_평균매출_반영은_측정_대상이_아니다():
    """숙주가 안 뽑힌 건 결함이 아니다 — None 이어야 분모에서 빠진다(설계 리뷰)."""
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["상권_평균매출_반영"] is None


def test_시간대축이_선정되고_피크밴드를_인용하면_반영으로_통과한다():
    """우리 매장 피크(14시)는 peakSalesHourBand(14-17) 안에 든다 — SAME 이다.
    방향 어휘가 없는 문장이라 "반대로 서술"도 아니므로 통과한다."""
    result = _district_insight("오후 2시(14시)부터 17시까지 매출이 가장 높습니다.")

    assert result["상권_피크밴드_반영"] is True


def test_피크밴드_방향이_반대로_서술되면_걸린다():
    result = _district_insight("오후 2시(14시)부터 17시까지는 상권 매출 피크와 겹치지 않습니다.")

    assert result["상권_피크밴드_반영"] is False


def test_시간대축이_선정_안_되면_상권_피크밴드_반영은_측정_대상이_아니다():
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["상권_피크밴드_반영"] is None


def test_시간대축이_선정되면_hourlySales_선정률이_참이다():
    result = _district_insight("오후 2시(14시)부터 17시까지 매출이 가장 높습니다.")

    assert result["hourlySales_선정률"] is True


def test_시간대축이_선정_안_되면_hourlySales_선정률이_거짓이다():
    result = _district_insight("아메리카노가 메뉴 매출의 28.2%를 차지합니다.")

    assert result["hourlySales_선정률"] is False
```

`test_정상_인사이트는_모든_항목을_통과한다`의 세 번째 문장은 그대로 둔다(상권
평균매출을 이미 인용한다) — 다만 `salesSummary_선정률`이 새로 생겨서, `INS_METRICS`
의 실제 `totalSales`와 `districtBenchmark.districtAvgMonthlySalesPerCafe` 값을
**먼저 확인**하고(추측하지 않는다) 그 결과(ABOVE/BELOW/EQUAL)와 문장의 방향
어휘("낮습니다")가 실제로 맞는지 대조한다 — 안 맞으면 이 테스트가 `상권_평균매출_반영`
에서 깨지므로, 그때는 문장의 방향 어휘를 실제 값에 맞게 고친다:

```python
def test_정상_인사이트는_모든_항목을_통과한다():
    result = _insight(
        "커피 카테고리 매출이 메뉴 매출의 41.7%를 차지하고 있습니다.",
        "아메리카노가 메뉴 매출의 28.2%를 차지합니다.",
        "총 매출은 전기 대비 4.2% 증가했으며 상권 평균 9,413,000원보다 낮습니다.",
    )

    failed = [k for k, v in result.items() if isinstance(v, bool) and not v]
    assert failed == [], f"오탐: {failed}"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: 새 테스트들이 `AttributeError`(`grade._district_gate`/`grade._comparison`
없음) 또는 `KeyError`(새 키 없음)로 FAIL.

- [ ] **Step 3: `devtools/grade.py`에 게이트 복사본 + 선정/반영 함수 추가**

`_DISTRICT_CAUSAL = re.compile(...)` 정의 바로 뒤(현재 102~104번째 줄 다음)에
추가한다:

```python
# app/services/insight_focus.py::_district_gate 와 같은 로직이어야 한다 — app 을
# import 하지 않으려고 복사해 둔 값이다(둘이 어긋나면 tests/test_grade.py 가 잡는다).
_MIN_CAFE_STORE_COUNT = 3


def _district_gate(district: dict | None) -> bool:
    if not district:
        return False
    if (district.get("cafeStoreCount") or 0) < _MIN_CAFE_STORE_COUNT:
        return False
    return (district.get("districtAvgMonthlySalesPerCafe") or 0) > 0


# app/services/insight_focus.py::district_comparison 과 같은 로직이어야 한다.
def _comparison(total_sales: int, district_avg: int) -> str:
    if total_sales > district_avg:
        return "ABOVE"
    if total_sales < district_avg:
        return "BELOW"
    return "EQUAL"


# app/services/insight_focus.py::_store_peak_hour·_in_band 와 같은 로직이어야 한다.
def _store_peak_hour(points: list[dict]) -> int | None:
    selling = [p for p in points if (p.get("menuSales") or 0) > 0]
    if not selling:
        return None
    return max(selling, key=lambda p: p.get("menuSales") or 0)["hour"]


def _in_band(hour: int | None, band: str) -> bool:
    if hour is None:
        return False
    start, end = (int(x) for x in band.split("-"))
    return start <= hour < end


def _axis_selected(body: str, metrics: dict, key: str) -> bool:
    """그 축이 생성 문장에 실제로 쓰였는지 — assign() 선정 여부의 근사치.

    assign() 의 6 축 점수식을 복제하지 않는다(여긴 app 을 import 하지 않는다는
    전제라 과하다, 모듈 머리말 참고) — 대신 "이 축 숫자가 문장에 등장했는지"로
    선정 여부를 근사한다. _metric_paths/_evidence_group 과 같은 방식이다.
    """
    axis = metrics.get(key) or {}
    if not axis:
        return False
    index = _metric_paths({key: axis})
    return bool(_evidence_group(body, index))


_DIRECTION_WORDS = {
    "ABOVE": ("높", "웃돌", "상회"),
    "BELOW": ("낮", "밑돌", "하회"),
    "EQUAL": ("같습니다", "동일"),
    "SAME": ("겹칩니다", "일치합니다"),
    "DIFFERENT": ("겹치지 않", "다른 시간대", "불일치"),
}
_OPPOSITE = {"ABOVE": "BELOW", "BELOW": "ABOVE", "EQUAL": None, "SAME": "DIFFERENT", "DIFFERENT": "SAME"}


def _direction_correct(body: str, comparison: str) -> bool:
    """방향 어휘가 실제 계산 결과와 반대로 쓰였는지만 본다 — 간단한 어휘 대조다
    (완전한 자연어 이해는 아니다, 1 차는 검출 시도 수준). 올바른 어휘가 없어도
    (수치만 언급) 통과시킨다 — 의견 없는 문장을 결함으로 몰지 않는다. 반대
    방향 어휘가 있을 때만 실패시킨다(설계 'C').
    """
    opposite = _OPPOSITE[comparison]
    if opposite and any(word in body for word in _DIRECTION_WORDS[opposite]):
        return False
    return True


def _district_avg_reflected(body: str, metrics: dict) -> bool | None:
    """게이트를 통과하고 salesSummary 가 실제로 선정됐을 때만 유효한 측정이다(#209 "A").

    둘 중 하나라도 아니면 None — "선정 안 됨"은 결함이 아니다. devtools/bench.py
    가 None 을 분모에서 뺀다(설계 리뷰 — 안 빼면 실제보다 낮게 보인다). 값이
    보여도 방향이 반대면 실패로 센다(설계 'C').
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
    comparison = _comparison(summary.get("totalSales") or 0, district["districtAvgMonthlySalesPerCafe"])
    return _direction_correct(body, comparison)


def _band_mentioned(body: str, band: str) -> bool:
    start, end = band.split("-")
    numbers = _numbers_in(body)
    return start in numbers and end in numbers


def _district_band_reflected(body: str, metrics: dict) -> bool | None:
    """위와 같은 조건부 측정이다 — hourlySales 쪽(#209 "A").

    peakSalesHourBand/peakFootTrafficHourBand 중 언급된 쪽만 방향(vsDistrictSalesPeak/
    vsDistrictFootTrafficPeak)이 반대로 서술됐는지 본다.
    """
    district = metrics.get("districtBenchmark")
    if not _district_gate(district):
        return None
    if not _axis_selected(body, metrics, "hourlySales"):
        return None
    peak_hour = _store_peak_hour(metrics.get("hourlySales") or [])
    bands = {
        "peakSalesHourBand": "SAME" if _in_band(peak_hour, district["peakSalesHourBand"]) else "DIFFERENT",
        "peakFootTrafficHourBand": (
            "SAME" if _in_band(peak_hour, district["peakFootTrafficHourBand"]) else "DIFFERENT"
        ),
    }
    mentioned = [key for key in bands if _band_mentioned(body, district[key])]
    if not mentioned:
        return False
    return all(_direction_correct(body, bands[key]) for key in mentioned)
```

`grade_insight()` 함수 안, `result["상권_인과_주장_없음"] = ...` 줄 바로 뒤에 추가:

```python
    result["salesSummary_선정률"] = _axis_selected(body, metrics, "salesSummary")
    result["hourlySales_선정률"] = _axis_selected(body, metrics, "hourlySales")
    result["상권_평균매출_반영"] = _district_avg_reflected(body, metrics)
    result["상권_피크밴드_반영"] = _district_band_reflected(body, metrics)
```

- [ ] **Step 4: `tests/test_grade.py` 통과 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 실패하는 테스트 작성 — `tests/test_bench.py`**

기존 테스트들 뒤에 추가한다:

```python
def test_조건부_항목의_None은_분모에서_빠진다():
    """선정 안 된 조건부 항목(None)을 결함으로 세면 실제보다 낮게 보인다(#209, 헥터)."""
    rows = [
        _row(
            200,
            {"parsed": True, "상권_평균매출_반영": None},
            {"parsed": True, "상권_평균매출_반영": None},
        ),
        _row(
            200,
            {"parsed": True, "상권_평균매출_반영": True},
            {"parsed": True, "상권_평균매출_반영": False},
        ),
    ]
    _, per_key, all_model, all_service = _rates(rows)

    assert per_key["상권_평균매출_반영"] == (1.0, 0.0), "None 인 행은 분모에서 빠져야 한다"
    assert all_model == 1.0, "None 은 결함이 아니라 전항목 집계에서 통과로 센다"
    assert all_service == 0.5, "False 는 여전히 결함이다 — None 과 다르게 센다"
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `uv run pytest tests/test_bench.py -v`
Expected: `test_조건부_항목의_None은_분모에서_빠진다` FAIL(`bool(None)` 이 `False`로
뭉개져 `per_key["상권_평균매출_반영"] == (0.5, 0.0)`가 나온다).

- [ ] **Step 7: `devtools/bench.py`의 `_checks`·`_rates`·`_report` 수정**

```python
def _checks(result: dict) -> dict[str, bool | None]:
    return {
        key: (value if value is None else bool(value))
        for key, value in result.items()
        if key not in SKIP_KEYS
    }
```

```python
def _rates(rows: list[dict]) -> tuple[list[str], dict[str, tuple[float | None, float | None]], float, float]:
    """항목별 (모델, 서비스) 통과율과 전항목 통과율.

    분모는 보통 전체 요청 수다 — 행에 없는 항목(500·파싱 실패)은 결함으로 센다,
    있는 항목만 평균하면 "응답이 안 온 요청"이 통계에서 사라져 숫자가 좋아 보인다.
    다만 조건부 항목(값이 None)은 그 요청에서 측정 대상이 아니라는 뜻이라 분모에서
    뺀다 — 그대로 결함으로 세면 "선정 안 됨"이 "결함"으로 잡혀 실제보다 낮게 보인다
    (#209 설계 리뷰, 헥터 — #178 카드_개수_일치 사고와 같은 모양).
    """
    total = len(rows)
    keys: dict[str, None] = {}
    for row in rows:
        keys.update(dict.fromkeys(row["model"]))
        keys.update(dict.fromkeys(row["service"]))

    def _rate(column: str, key: str) -> float | None:
        numerator = 0
        denominator = 0
        for row in rows:
            values = row[column]
            if key not in values:
                denominator += 1  # 응답 실패·파싱 실패 — 결함으로 센다
                continue
            value = values[key]
            if value is None:
                continue  # 조건부 항목의 "해당 없음" — 분모에서 뺀다
            denominator += 1
            numerator += 1 if value else 0
        return numerator / denominator if denominator else None

    def _effective(values: dict, key: str) -> bool:
        if key not in values:
            return False
        value = values[key]
        return True if value is None else bool(value)

    per_key = {key: (_rate("model", key), _rate("service", key)) for key in keys}
    all_model = sum(1 for r in rows if all(_effective(r["model"], k) for k in keys)) / total
    all_service = sum(1 for r in rows if all(_effective(r["service"], k) for k in keys)) / total
    return list(keys), per_key, all_model, all_service
```

`_report()` 안, 항목별 줄을 찍는 부분을 `None` 안전하게 바꾼다:

```python
    for key in keys:
        model, service = per_key[key]
        model_text = f"{model:.1%}" if model is not None else "N/A"
        service_text = f"{service:.1%}" if service is not None else "N/A"
        mark = "  <--" if service is not None and service < 0.95 else ""
        print(f"  {_pad(key, width)}   {model_text:>11}   {service_text:>12}{mark}")
```

`failed_keys` 계산 줄도 `None` 안전하게 바꾼다:

```python
    failed_keys = [
        key for key in keys if per_key[key][1] is not None and per_key[key][1] < 1.0
    ]
```

- [ ] **Step 8: 전체 테스트 통과 확인**

Run: `uv run pytest tests/test_grade.py tests/test_bench.py -v`
Expected: 전부 PASS.

- [ ] **Step 9: 린트 + 커밋**

```bash
uv run ruff check --fix . && uv run ruff format .
git add devtools/grade.py devtools/bench.py tests/test_grade.py tests/test_bench.py
git commit -m "feat: 상권 숙주 선정률과 반영률을 분리해 채점기·집계에 추가한다

salesSummary_선정률·hourlySales_선정률(분모: 전체 요청)과 상권_평균매출_반영·
상권_피크밴드_반영(분모: 게이트 통과 + 숙주 선정된 요청만, 수치뿐 아니라 비교
방향까지 확인)을 나눈다. bench.py._rates 가 None 을 분모에서 빼도록 고쳤다 —
안 고치면 '선정 안 됨'이 '결함'으로 잡혀 실제보다 낮게 보인다(#209 설계 'A')."
```

---

## Task 5: 채점기 측정 B — basisQuarter 접지 누수

**설계가 한 번 바뀌었다**: 처음엔 "미인용"·"날조_없음" 둘 다 전체 요청을 분모로
써서, `grounded is None`(미인용)을 "날조_없음" 쪽에선 통과로 셌다. 이러면 인용
자체가 드물 때(예: 10 건 중 1 건만 인용, 그마저 날조) "날조_없음"이 90%대로
보여 실제 날조율을 가린다 — Task 4에서 A를 고친 것과 같은 희석 문제라는 지적을
반영해, B도 **인용 빈도**(`상권_분기_인용됨`, 분모 전체)와 **인용했을 때의 정확도**
(`상권_분기_날조_없음`, 분모 = 인용한 요청만)로 나눈다.

**Files:**
- Modify: `devtools/grade.py`
- Test: `tests/test_grade.py`

**Interfaces:**
- Produces: `grade._quarter_leak(body: str, metrics: dict) -> bool | None`.
  `grade_insight()` 결과 dict에 `"상권_분기_인용됨"`(bool)·`"상권_분기_날조_없음"`
  (bool | None) 키 추가.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_grade.py`에 Task 4에서 추가한 테스트들 뒤에 이어 붙인다:

```python
def test_분기를_인용하지_않으면_인용됨이_거짓이고_날조는_측정_대상이_아니다():
    result = _insight("커피 카테고리 매출이 메뉴 매출의 41.7%를 차지하고 있습니다.")

    assert result["상권_분기_인용됨"] is False
    assert result["상권_분기_날조_없음"] is None


def test_실제_분기와_같은_값을_인용하면_날조가_아니다():
    """basisQuarter 는 focus 블록에 안 보내지만(#209), 지표 어딘가엔 여전히 있어
    접지 검사로는 못 잡는다 — 그래도 '날조'는 아니라는 걸 구분한다."""
    result = _insight("2026Q3 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is True


def test_실제_분기와_다른_값을_인용하면_날조다():
    result = _insight("2027Q1 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is False


def test_년_분기_표기도_잡는다():
    result = _insight("2026년 3분기 기준 상권 평균은 9,413,000원입니다.")

    assert result["상권_분기_인용됨"] is True
    assert result["상권_분기_날조_없음"] is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: 새 테스트 4개 `KeyError`(`"상권_분기_인용됨"` 없음)로 FAIL.

- [ ] **Step 3: `devtools/grade.py`에 분기 누수 검출 함수 추가**

Task 4에서 추가한 `_district_avg_reflected` 함수 뒤에 이어 붙인다:

```python
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
```

`grade_insight()` 함수 안, Task 4에서 추가한
`result["상권_평균매출_반영"] = ...` 줄 바로 뒤에 추가:

```python
    grounded = _quarter_leak(body, metrics)
    result["상권_분기_인용됨"] = grounded is not None
    result["상권_분기_날조_없음"] = grounded
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: `devtools/bench.py`가 `상권_분기_날조_없음`도 조건부 분모로 세는지 확인**

Task 4에서 `_rates`를 이미 `None`을 일반적으로 처리하도록 고쳤으므로
(`devtools/bench.py` 수정 없이) `상권_분기_날조_없음`도 자동으로 "인용한 요청만"을
분모로 쓴다. 확인만 한다:

```bash
uv run pytest tests/test_bench.py -v
```

Expected: 전부 PASS(코드 변경 없음, Task 4의 `_rates`가 이미 일반적으로 처리한다).

- [ ] **Step 6: 린트 + 커밋**

```bash
uv run ruff check --fix . && uv run ruff format .
git add devtools/grade.py tests/test_grade.py
git commit -m "feat: basisQuarter 접지 누수 측정 항목을 채점기에 추가한다

인용 빈도(상권_분기_인용됨, 분모: 전체 요청)와 인용했을 때의 정확도(상권_분기_날조_없음,
분모: 인용한 요청만)를 나눠서 잰다 — 인용이 드물면 하나로 합친 비율이 실제 날조율을
가린다. 차단 규칙은 추가 안 함 — 7차 측정 결과를 보고 결정한다(#209 설계 'B')."
```

---

## Task 6: 전체 검증 + STATE.md 갱신

**Files:**
- Modify: `docs/STATE.md`

- [ ] **Step 1: 전체 테스트·린트 실행**

```bash
uv run pytest -q
uv run ruff check --fix . && uv run ruff format .
```

Expected: 전부 PASS, ruff 추가 수정 없음(있으면 diff 확인 후 재실행).

- [ ] **Step 2: `devtools/contract_check.py` 수동 점검**

이 변경은 `InsightMetrics`/`DistrictBenchmark` 스키마를 안 건드리므로
`devtools/contract_check.py`의 `_INSIGHT_METRICS` 픽스처는 그대로 둔다. 확인만 한다:

```bash
uv run python -m devtools.contract_check --example sales-insights
```

Expected: `districtBenchmark` 객체가 요청 예시에 그대로 나온다(요청 계약은 안
바뀌었다 — 서버 내부에서 어떻게 쓰는지만 바뀌었다).

- [ ] **Step 3: `docs/STATE.md` 갱신**

`docs/STATE.md` 맨 위 `# 작업 상태` 바로 다음에 새 섹션을 추가한다(기존 "## 2026-10-20
..." 절들은 그대로 둔다 — 덮어쓰지 않고 위에 새 절을 쌓는 게 이 팀의 실제 관행이다):

```markdown
## 2026-10-21 — 상권(districtBenchmark) 인사이트 번들링 (Issue #209)

전용 경쟁 축(고정 보충값 0.3)을 없애고 salesSummary(평균매출 비교)·hourlySales(피크
시간대)에 조건부로 번들링했다. 배경: PR #207·#208(헥터) 실측에서 상권이 7개 축 중
"전부있음" 케이스 기준 5위로 밀리는 게 확인됐다 — 인사이트는 상권 추가 전부터 이미
6개 축이 경쟁 중이었는데 날씨의 "다른 세 축" 전제를 그대로 복사한 설계 실수였다.

설계 문서: `docs/superpowers/specs/2026-10-21-district-benchmark-bundling-design.md`

- `app/services/insight_focus.py`: `district_comparison()`(ABOVE/BELOW/EQUAL 사전
  계산)·`_store_peak_hour()`/`_in_band()`(우리 매장 피크 vs 상권 밴드)·
  `_district_gate()` 추가. `_district_score`/`_DISTRICT_SUPPLEMENT_SCORE` 삭제.
- `app/prompts/insight.py`: districtBenchmark 중첩 객체 대신 평평한 필드명을
  가리키도록 규칙 갱신. VERSION → 2026-10-21.
- `devtools/grade.py`: 측정 전용 항목 추가(차단 아님) — `salesSummary_선정률`·
  `hourlySales_선정률`(분모: 전체 요청), `상권_평균매출_반영`·`상권_피크밴드_반영`
  (분모: 게이트 통과 + 숙주 선정된 요청만, 조건 미충족 시 `None`)(A), `상권_분기_인용됨`·
  `상권_분기_날조_없음`(조건부, B).
- `devtools/bench.py`: `_checks`·`_rates`·`_report`가 `None`(조건부 항목의 "해당
  없음")을 분모에서 빼도록 수정.

### 마지막으로 통과한 것
- `uv run pytest` — (Step 1 결과 수를 여기 적는다)
- `uv run ruff check --fix . && uv run ruff format .` — 통과

### 다음 한 걸음
- `devtools/bench.py`의 #208 "상권있음"·"전부있음" 케이스로 `--n 20` 실측 — 네
  선정률·반영률(salesSummary_선정률/hourlySales_선정률/상권_평균매출_반영/
  상권_피크밴드_반영)과 `상권_분기_인용됨`/`상권_분기_날조_없음` 비율을 확인한다.
- 측정 결과가 낮으면 salesSummary 숙주 교체·점수 조정 재검토(설계 문서 "A").
- basisQuarter 누수가 유의미하면 차단 규칙 도입 검토(설계 문서 "B").
- solution의 weatherContext는 이번 범위 밖 — 7차 측정(#207 케이스 포함) 이후 별도
  판단.

### 미해결 결정
- 노션 API 정의서의 districtBenchmark 확정 여부(PR #161부터 이어진 미해결 건) — 이번
  작업은 요청 계약을 안 건드려서 무관하지만, 리뷰 때 다시 확인 필요.

### 함정
- `devtools/grade.py`는 `app` 패키지를 import하지 않는다(Colab 이식성) — 그래서
  `_district_gate`·`_comparison`·`_store_peak_hour`·`_in_band`를 두 군데(서비스·
  채점기)에 복사해 뒀다. 한쪽만 고치면 어긋난다 —
  `tests/test_grade.py::test_채점기의_상권_게이트가_서비스와_같다`·
  `test_채점기의_비교_방향이_서비스와_같다`가 잡는다.
```

- [ ] **Step 4: 커밋**

```bash
git add docs/STATE.md
git commit -m "docs: STATE.md에 상권 번들링 작업 내용을 반영한다(#209)"
```

---

## Self-Review 메모 (설계 리뷰 반영 후 다시 확인함, 2026-10-21)

- **스펙 커버리지**: 설계 문서의 "핵심 설계" 1)·2) → Task 1·2. "프롬프트 변경" →
  Task 3. "A"·"B" → Task 4·5. 핵심 설계 1) 안의 "C"(비교 방향 사전 계산)는 Task 1에
  포함(단일 지점이라 별도 태스크로 안 쪼갬), 핵심 설계 2) 안의 "C 확장"(우리 매장
  피크 vs 상권 밴드)는 Task 2에 포함. "다루지 않는 필드"(basisQuarter·
  cafeStoreCount 미인용)는 Task 1·2에서 자연히 지켜진다(둘 다 focus 블록에 안
  넣음).
- **타입 일관성**: `district_comparison`이 Task 1에서 정의한 반환값
  (`"ABOVE"`/`"BELOW"`/`"EQUAL"`)을 Task 3 프롬프트 문구·Task 4의 `grade._comparison`
  복사본이 그대로 쓴다. Task 2의 `vsDistrictSalesPeak`/`vsDistrictFootTrafficPeak`
  (`"SAME"`/`"DIFFERENT"`)도 Task 3·4에서 이름·값이 일관된다. `_district_gate`
  시그니처(`dict | None -> bool`)가 Task 1·2·4에서 동일하다.
- **분모 일관성**: Task 4에서 고친 `devtools/bench.py::_rates`의 `None`-분모-제외
  처리가 Task 5의 `상권_분기_날조_없음`에도 코드 변경 없이 그대로 적용된다 — Task 5
  Step 5가 이걸 확인만 하고 넘어가는 이유다.
- **플레이스홀더 없음**: 모든 Step에 실제 코드·실제 명령을 적었다. "에러 처리 추가"
  류 모호한 지시 없음.
- **설계 리뷰 반영 확인(헥터 + 사용자 종합)**: (1) 선정률/반영률 분모 분리 — Task 4.
  (2) 밴드 오귀속 예방 — 처음 제안(두 상권 밴드끼리 겹침)은 인과 암시 위험과 틀린
  전제(매장 쪽 대응 데이터 없음) 때문에 폐기하고, "우리 매장 피크 vs 상권 밴드"로
  재설계 — Task 2. (3) `hourlySales` 선정률 인용 오류 정정 — 설계 문서 트레이드오프
  절. (4) `hourlySales_선정률`·반영률의 비교 방향까지 검증 — Task 4.
