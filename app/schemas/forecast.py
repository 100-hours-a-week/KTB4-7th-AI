from typing import Literal

from app.schemas.common import Contract


class DailySale(Contract):
    date: str
    amount: int
    orderCnt: int


class ForecastRequest(Contract):
    storeId: int
    uploadId: int
    targetMonth: str
    dailySales: list[DailySale]


class Prediction(Contract):
    date: str
    predictedAmount: int
    isHoliday: bool | None = None  # v2


class MonthlyTotal(Contract):
    predictedAmount: int
    vsPrevMonth: float


class DowAverage(Contract):
    dow: Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    predictedAmount: int


class ForecastResponse(Contract):
    status: Literal["SUCCESS", "INSUFFICIENT_HISTORY"]
    targetMonth: str
    predictions: list[Prediction]
    monthlyTotal: MonthlyTotal | None = None
    dowAverage: list[DowAverage] | None = None
    modelVersion: str | None = None
    # INSUFFICIENT_HISTORY 일 때만 채워진다
    requiredMonths: int | None = None
    providedMonths: int | None = None
