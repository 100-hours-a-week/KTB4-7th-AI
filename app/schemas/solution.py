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
    # 제약은 ERD solutions 테이블을 그대로 옮긴 것이다. 여기서 막지 않으면 AI 는 200 을
    # 돌려주고 BE 가 INSERT 할 때 터진다 — AI 로그는 정상이라 원인 추적이 오래 걸린다.
    rankNo: int = Field(ge=1)  # CHECK (rank_no > 0)
    title: str = Field(max_length=200)  # VARCHAR(200)
    summaryText: str
    detailText: str = Field(max_length=1000)
    # NULL 허용: LLM이 근거를 못 뽑는 경우가 있어 필수로 두면 재시도 후에도 500이 난다.
    evidence: str | None = None


class SolutionData(Contract):
    targetDate: str
    solutionCards: list[SolutionCard]
    modelVersion: str


class SolutionResponse(Contract):
    message: str = "솔루션을 생성했습니다."
    data: SolutionData
