from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """계약 모델 공통 베이스. 위키 규약: camelCase.

    정의되지 않은 필드는 **무시**한다(2026-09-16 팀 결정). BE와 AI가 따로 배포되므로,
    한쪽이 필드를 먼저 추가해도 다른 쪽이 422로 막지 않아야 배포 순서에 묶이지 않는다.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Evidence(Contract):
    metric: str
    dayType: str | None = None
    period: str | None = None
    value: float | None = None


class SalesSummary(Contract):
    netSales: int
    # 이전 비교 데이터가 없으면 BE 가 null 을 보낸다 — 첫 업로드 매장은 이전 기간 자체가
    # 없다(2026-09-23 실연동에서 422 확인). 필수로 두면 그 매장은 솔루션을 아예 못 받는다.
    vsPrevPeriod: float | None = None
    # 2026-10-15: netSales 가 하루 매출이 아니라 분석 기간(salesAnalysisId 가 집계한 기간)
    # 합계라는 걸 BE가 확인해줬는데, 그 기간의 시작·끝을 받을 필드가 계약에 아직 없었다 —
    # 점주가 "현재 기간 순매출이 ...원이며"처럼 기준 없는 문장을 신고한 원인이다. BE와 최종
    # 필드명을 맞추기 전까지 AI 쪽에서 쓸 이름을 먼저 정해 반영한다(선택값 — BE가 아직
    # 안 보내도 422가 아니다). "2026-01-01~2026-03-31" 같은 자유 문자열로 받는다 —
    # `Evidence.period`(챗봇 응답의 근거 기간)도 같은 모양이라 형식을 맞췄다.
    period: str | None = None


class HourlyPoint(Contract):
    dayType: str
    hour: int
    amount: int


class CategoryPoint(Contract):
    name: str
    share: float
    vsPrevPeriod: float | None = None


class WeatherContext(Contract):
    """V2: 기상청 단기예보 요약(오늘 남은 영업시간분). 2026-10-14 BE 협의 확정.

    maxPop 단위는 BE 확인 대기 중이다 — 일단 소수(0.0~1.0)로 가정한다(AGENTS.md "비율은
    소수" 원칙). BE가 정수(%)로 확정하면 이 필드 타입만 바꾸면 된다.

    precipitationMm 은 2026-10-15(#162)부터 선택값이다. 기상청 PCP가 "1.0mm 미만" 같은
    범주값으로 올 때가 있어 영업시간 합계를 정확한 수로 못 낼 수 있다 — 그 경우 BE가
    null을 보낸다. maxPop·rainHours·skyText·isNotable은 POP·SKY 기반이라 PCP와 무관하게
    항상 값이 있으므로 그대로 필수로 둔다.
    """

    basisDateTime: str
    skyText: str
    minTempC: int
    maxTempC: int
    maxPop: float
    rainHours: list[int]
    precipitationMm: float | None = None
    isNotable: bool


class ConditionMenu(Contract):
    menuName: str
    avgQuantity: int
    baselineAvgQuantity: int
    vsBaseline: float
    avgSales: int
    baselineAvgSales: int


class ConditionPattern(Contract):
    """V2: 과거 강수별 메뉴 판매 패턴. 2026-10-19 BE 확정(BE PR #492).

    최근 완료된 12주의 ASOS 강수 관측과 날짜별 메뉴 판매를 BE 가 비교해 결과만 넘긴다.
    1.0mm 이상이 RAIN, 0.1mm 미만이 기준군이고 그 사이는 양쪽에서 빠진다. 비 온 날과
    무강수 날이 **각각 5일 이상**일 때만 오고, 미달이면 배열 일부나 null 이 아니라
    conditionPatterns 전체가 생략된다.

    **아직 프롬프트·점수식에 연결하지 않았다**(2026-10-20, 이슈 #194). 받아서 버리지만
    않는 단계다 — #187 인사이트 게이트의 A40 효과를 먼저 재야 입력 축을 늘린 영향과
    섞이지 않는다.

    연결할 때 sampleWeekdayRatio·baselineWeekdayRatio 를 먼저 봐야 한다. 두 값이 다르면
    비 온 날과 기준일의 평일/주말 구성이 다르다는 뜻이어서, 판매량 차이가 강수 때문인지
    요일 때문인지 구분되지 않는다. BE 도 "변화율은 상관관계이며 강수의 인과 효과로
    단정하지 않는다" 고 명시했다.
    """

    condition: str
    basisWeeks: int
    thresholdMm: float
    sampleDays: int
    baselineDays: int
    sampleWeekdayRatio: float
    baselineWeekdayRatio: float
    menus: list[ConditionMenu] = []


class DayHours(Contract):
    opensAt: str  # "08:00"
    closesAt: str  # "22:00"


class BusinessHours(Contract):
    """정규 영업시간 (2026-10-19 풀스택 확정, 이미 같은 형식으로 보내고 있음).

    hourlyProfile 이 dayType(WEEKDAY/WEEKEND) 단위 집계라 영업시간도 같은 단위다.
    요일별로 다르면 BE 가 각 그룹에서 가장 흔한 시간을 대표값으로 보낸다 — 평일 중
    하루만 크게 다른 매장은 그날 "마감 2시간 전" 류 표현이 어긋날 수 있다(알고 있는 한계).
    """

    # 계약이 대문자 키라 그대로 쓴다.
    WEEKDAY: DayHours | None = None
    WEEKEND: DayHours | None = None
    closedDaysOfWeek: list[str] = []


class Metrics(Contract):
    salesSummary: SalesSummary
    hourlyProfile: list[HourlyPoint]
    categoryBreakdown: list[CategoryPoint]
    predictedSalesToday: int | None = None
    reviewSummary: dict | None = None
    # 인사이트(InsightMetrics)에 이미 보내고 있는 것과 **같은 모양**이다. BE 가 새로
    # 집계할 필요 없이 그대로 넘기면 된다(2026-10-18 풀스택 협의). 솔루션은 그동안
    # 카테고리 단위("커피 62%")까지만 알아서 "커피 메뉴를 강화하세요" 같은 말이
    # 나왔다 — 무슨 메뉴인지를 몰랐다.
    #
    # MenuRankingPoint 가 아래(인사이트 절)에 정의돼 있어 문자열로 참조하고 모듈 끝에서
    # 해석한다. 클래스를 위로 옮기면 "인사이트 전용 지표" 절의 구성이 흐트러진다.
    menuRankings: list["MenuRankingPoint"] = []
    businessHours: BusinessHours | None = None
    weatherContext: WeatherContext | None = None
    # weatherContext 는 오늘 예보 스냅샷이라 과거 매출과의 인과를 뒷받침할 지표가 없었다.
    # 그 자리를 메우는 값이다 — BE 가 12주 관측과 실제 판매를 비교해 결과만 넘긴다.
    # 선택 필드고, 기본값이 빈 리스트라 BE 가 생략하면 지금과 똑같이 동작한다.
    #
    # 아직 프롬프트·점수식에 연결하지 않았다(이슈 #194). 다만 solution.py 가 metrics 를
    # 통째로 _metric_numbers 에 넘기므로, 연결 전에도 이 값들이 접지 허용 집합에는
    # 들어간다 — 3자리 이상은 avgSales·baselineAvgSales 둘뿐이고 모델이 보지 못하는
    # 값이라 날조가 우연히 일치할 확률은 낮다. 3단계에서 어차피 접지돼야 하는 값이다.
    conditionPatterns: list[ConditionPattern] = []


# ── 인사이트 전용 지표 ──────────────────────────────────────────────
# 2026-09-22 풀스택 확정 계약. 위 Metrics(솔루션용)와 필드명이 거의 겹치지 않아 따로 둔다 —
# 공유 모델을 고치면 승민님 실제 샘플로 검증이 끝난 솔루션 경로가 같이 깨진다.
#
# 금액이 두 종류다. totalSales 는 완료·취소·비메뉴를 모두 합친 화면 KPI 값이고,
# menuSales 는 item_type=MENU 만 합친 값이다(api정의서 SALES-03). 상세 패턴 지표가
# 전부 menuSales 계열이라 총액과 섞어 쓰면 합이 안 맞는 문장이 나온다.


class InsightSalesSummary(Contract):
    totalSales: int
    menuSales: int
    orderCount: int
    averageOrderValue: int
    # 총매출(totalSales) 기준 증감률이다(2026-09-22 BE 확정). 이전 비교 데이터가 없으면 null.
    vsPrevPeriod: float | None = None


class SalesTrendPoint(Contract):
    date: str
    menuSales: int
    orderCount: int


class WeekdaySalesPoint(Contract):
    dayOfWeek: str
    menuSales: int
    orderCount: int


class HourlySalesPoint(Contract):
    dayType: str
    hour: int
    menuSales: int
    orderCount: int


class CategorySalesPoint(Contract):
    categoryName: str
    menuSales: int
    ratio: float
    vsPrevPeriod: float | None = None


class MenuRankingPoint(Contract):
    rank: int
    menuName: str
    menuSales: int
    quantity: int
    ratio: float
    vsPrevPeriod: float | None = None


class DistrictBenchmark(Contract):
    """V2: 서울시 상권분석 Open API 기반 행정동 단위 추정값. 2026-10-14 BE 협의 확정(#157).

    매장 개별 실적이 아니라 행정동 커피·음료 업종 점포당 월평균 추정매출(해당 분기 기준)이다
    — 프롬프트에서 이 구분을 명시해야 한다(app/prompts/insight.py).
    """

    basisQuarter: str
    districtAvgMonthlySalesPerCafe: int
    cafeStoreCount: int
    peakSalesHourBand: str
    peakFootTrafficHourBand: str


class InsightMetrics(Contract):
    salesSummary: InsightSalesSummary
    # 아래 5종은 BE 집계 상황에 따라 빠질 수 있다. 필수로 두면 지표 하나가 비었다고
    # 422 가 나서 인사이트가 통째로 없어진다 — 있는 지표로 만드는 편이 낫다.
    salesTrend: list[SalesTrendPoint] = []
    weekdaySales: list[WeekdaySalesPoint] = []
    hourlySales: list[HourlySalesPoint] = []
    categorySales: list[CategorySalesPoint] = []
    menuRankings: list[MenuRankingPoint] = []
    districtBenchmark: DistrictBenchmark | None = None


# Metrics.menuRankings 가 아래에 정의된 MenuRankingPoint 를 문자열로 참조한다.
Metrics.model_rebuild()
