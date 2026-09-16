from typing import Literal

from pydantic import Field

from app.schemas.common import Contract, Metrics


class SolutionRequest(Contract):
    storeId: int
    # UPLOAD 트리거만 필수. SCHEDULED(00:00 배치)는 이 값을 보내지 않는다 — docs/api정의서.md 참고.
    salesAnalysisId: int | None = None
    targetDate: str
    triggerType: Literal["UPLOAD", "SCHEDULED"]
    metrics: Metrics


class SolutionCard(Contract):
    rankNo: int
    title: str
    summaryText: str
    detailText: str = Field(max_length=1000)


class SolutionData(Contract):
    targetDate: str
    solutionCards: list[SolutionCard]
    modelVersion: str
    promptVersion: str


class SolutionResponse(Contract):
    message: str = "솔루션을 생성했습니다."
    data: SolutionData
