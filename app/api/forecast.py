"""매출 예측 배치 라우터 — 위키 [AI] 단계1 §7.1."""

from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_key
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.forecast import run_forecast

router = APIRouter(prefix="/internal/ai", tags=["forecast"])


@router.post(
    "/forecast/batch",
    response_model=ForecastResponse,
    dependencies=[Depends(verify_internal_key)],
)
def forecast_batch(req: ForecastRequest) -> ForecastResponse:
    """업로드 시 1회 호출. 학습과 추론이 동기 CPU 작업이라 async 가 아닌 def 로 둔다.

    def 로 두면 FastAPI 가 스레드풀에서 실행하므로, 같은 서버의 챗봇 SSE 스트리밍이
    학습 중에 멈추지 않는다.
    """
    return run_forecast(req)
