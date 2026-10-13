from typing import Literal

from app.schemas.common import Contract


class Period(Contract):
    startDate: str
    endDate: str


class ProfitSummary(Contract):
    totalNetAmount: int
    ingredientCost: int
    fixedCost: int
    netProfit: int
    netProfitRate: float
    # 비교 기간을 계산할 수 없으면 BE 가 null 로 보낸다.
    previousNetProfit: int | None = None
    netProfitChangeRate: float | None = None


class DailyProfit(Contract):
    date: str
    netProfit: int


class ProfitInsightRequest(Contract):
    storeId: int
    period: Period
    summary: ProfitSummary
    dailyProfits: list[DailyProfit]
    maxInsightCount: int


class ProfitInsightData(Contract):
    insights: list[str]


class ProfitInsightResponse(Contract):
    message: str
    status: Literal["COMPLETED", "INSUFFICIENT_DATA"]
    data: ProfitInsightData
