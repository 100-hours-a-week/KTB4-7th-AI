from typing import Literal

from app.schemas.common import Contract, Metrics


class InsightRequest(Contract):
    storeId: int
    salesAnalysisId: int
    targetMonth: str  # YYYY-MM
    triggerType: Literal["UPLOAD", "RETRY"]
    metrics: Metrics
    maxInsightCount: int = 3


class InsightData(Contract):
    targetMonth: str | None = None
    insights: list[str] | None = None
    missingData: list[str] | None = None


class InsightResponse(Contract):
    message: str
    status: Literal["COMPLETED", "INSUFFICIENT_DATA"]
    data: InsightData
