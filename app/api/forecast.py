"""매출 예측 배치 라우터 — 노션 API 정의서 `POST /internal/v1/ai/forecast/batch`."""

from fastapi import APIRouter

from app.schemas.forecast import (
    ForecastRequest,
    ForecastResponse,
    InsufficientHistoryResponse,
)
from app.services.forecast import run_forecast

router = APIRouter(prefix="/internal/v1/ai", tags=["forecast"])


@router.post(
    "/forecast/batch",
    response_model=ForecastResponse | InsufficientHistoryResponse,
)
def forecast_batch(req: ForecastRequest) -> ForecastResponse | InsufficientHistoryResponse:
    """업로드 시 1회 호출. 학습과 추론이 동기 CPU 작업이라 async 가 아닌 def 로 둔다.

    def 로 두면 FastAPI 가 스레드풀에서 실행하므로, 같은 서버의 챗봇 SSE 스트리밍이
    학습 중에 멈추지 않는다.

    앱 레벨 인증은 두지 않는다 — 인바운드를 BE 로만 제한하는 보안 그룹이 경계다
    (2026-09-16 팀 결정).
    """
    return run_forecast(req)
