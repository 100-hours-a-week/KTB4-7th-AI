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


class HourlyPoint(Contract):
    dayType: str
    hour: int
    amount: int


class CategoryPoint(Contract):
    name: str
    share: float
    vsPrevPeriod: float | None = None


class DistrictBenchmark(Contract):
    """반경 500m 상권 업소 수 (2026-10-12 승민님 제안 기준).

    소상공인시장진흥공단 상가(상권)정보에는 매출이 없다 — 업소 수뿐이다. 그래서 "상권 평균
    대비" 는 만들 수 없고, 현황 설명에만 쓴다. 우리 매장도 집계에 포함될 수 있어서
    "경쟁 카페 수" 가 아니라 "반경 내 카페 수" 다.

    basisYm·queriedAt 은 받아서 로그·추적에만 쓰고 **프롬프트에는 넘기지 않는다**
    (app/services/solution_focus.py::_district_focus). 상권 API 응답에 기준월이 없어서
    시점을 단정하면 틀리는데, "시점을 쓰지 마세요" 를 프롬프트로 부탁하면 지켜지는 비율이
    90% 대다(실측: 공허한 조언 금지 88.9%, 금액 어림 금지 83%). 안 보여주는 쪽이 확실하다.
    """

    cafeCount: int
    # 음식업 전체 조회만 실패하면 BE 가 생략한다. 0 이면 분모가 없어 비중을 못 만든다.
    foodBizCount: int | None = None
    basisYm: str | None = None
    queriedAt: str | None = None


class Metrics(Contract):
    salesSummary: SalesSummary
    hourlyProfile: list[HourlyPoint]
    categoryBreakdown: list[CategoryPoint]
    predictedSalesToday: int | None = None
    reviewSummary: dict | None = None
    districtBenchmark: DistrictBenchmark | None = None


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


class InsightMetrics(Contract):
    salesSummary: InsightSalesSummary
    # 아래 5종은 BE 집계 상황에 따라 빠질 수 있다. 필수로 두면 지표 하나가 비었다고
    # 422 가 나서 인사이트가 통째로 없어진다 — 있는 지표로 만드는 편이 낫다.
    salesTrend: list[SalesTrendPoint] = []
    weekdaySales: list[WeekdaySalesPoint] = []
    hourlySales: list[HourlySalesPoint] = []
    categorySales: list[CategorySalesPoint] = []
    menuRankings: list[MenuRankingPoint] = []
