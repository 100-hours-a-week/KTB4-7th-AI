from typing import Literal

from app.schemas.common import Contract, InsightMetrics


class InsightRequest(Contract):
    storeId: int
    salesAnalysisId: int
    # 2026-09-22 계약 추가. 없이도 생성은 되지만 BE 로그와 대조할 때 쓰므로 받아둔다 —
    # 스키마에 없으면 extra="ignore" 가 조용히 버린다.
    analysisRunId: int | None = None
    targetMonth: str  # YYYY-MM
    triggerType: Literal["UPLOAD", "RETRY"]
    metrics: InsightMetrics
    maxInsightCount: int = 3


class InsightData(Contract):
    targetMonth: str | None = None
    insights: list[str] | None = None
    missingData: list[str] | None = None


class InsightResponse(Contract):
    message: str
    status: Literal["COMPLETED", "INSUFFICIENT_DATA"]
    data: InsightData
