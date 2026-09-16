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
    vsPrevPeriod: float


class HourlyPoint(Contract):
    dayType: str
    hour: int
    amount: int


class CategoryPoint(Contract):
    name: str
    share: float
    vsPrevPeriod: float


class Metrics(Contract):
    salesSummary: SalesSummary
    hourlyProfile: list[HourlyPoint]
    categoryBreakdown: list[CategoryPoint]
    predictedSalesToday: int | None = None
    reviewSummary: dict | None = None
