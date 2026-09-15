from typing import Literal

from pydantic import Field

from app.schemas.common import Contract, Evidence, Metrics


class SolutionContext(Contract):
    dayOfWeek: str
    isWeekend: bool
    dataBasisPeriod: str
    isHoliday: bool | None = None  # v2


class SolutionRequest(Contract):
    storeId: int
    salesAnalysisId: int
    targetDate: str
    triggerType: Literal["UPLOAD", "SCHEDULED"]
    context: SolutionContext
    metrics: Metrics


class SolutionCard(Contract):
    rank: int
    title: str
    evidence: Evidence
    detailContent: str = Field(max_length=1000)


class SolutionResponse(Contract):
    status: Literal["SUCCESS"] = "SUCCESS"
    targetDate: str
    solutionCards: list[SolutionCard]
    aiInsight: str
    modelVersion: str
    promptVersion: str
