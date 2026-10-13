from datetime import date as Date
from typing import Literal

from pydantic import Field

from app.schemas.common import Contract


class Period(Contract):
    startDate: Date
    endDate: Date


class ProfitSummary(Contract):
    totalNetAmount: int
    ingredientCost: int
    fixedCost: int
    netProfit: int
    # 매출이 0원이면 BE 가 null 로 보낸다(0으로 나눌 수 없어서) — 그 경우 서비스가
    # INSUFFICIENT_DATA 로 먼저 걸러낸다.
    netProfitRate: float | None = None
    # 비교 기간을 계산할 수 없으면 BE 가 null 로 보낸다.
    previousNetProfit: int | None = None
    netProfitChangeRate: float | None = None


class DailyProfit(Contract):
    date: Date
    netProfit: int


class ProfitInsightRequest(Contract):
    storeId: int
    period: Period
    summary: ProfitSummary
    dailyProfits: list[DailyProfit]
    maxInsightCount: int = Field(ge=1, le=3)


class ProfitInsightData(Contract):
    insights: list[str]


class ProfitInsightResponse(Contract):
    message: str
    status: Literal["COMPLETED", "INSUFFICIENT_DATA"]
    data: ProfitInsightData
