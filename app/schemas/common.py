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


class Metrics(Contract):
    salesSummary: SalesSummary
    hourlyProfile: list[HourlyPoint]
    categoryBreakdown: list[CategoryPoint]
    predictedSalesToday: int | None = None
    reviewSummary: dict | None = None


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
