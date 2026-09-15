from typing import Literal

from app.schemas.common import Contract, Evidence, Metrics


class InsightRequest(Contract):
    storeId: int
    uploadId: int
    dataDays: int
    metrics: Metrics


class Insight(Contract):
    text: str
    evidence: Evidence


class InsightResponse(Contract):
    status: Literal["SUCCESS", "INSUFFICIENT_DATA"]
    insights: list[Insight]
    modelVersion: str
    promptVersion: str
