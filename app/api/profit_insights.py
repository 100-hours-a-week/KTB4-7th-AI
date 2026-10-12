from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_token
from app.schemas.profit_insight import ProfitInsightRequest, ProfitInsightResponse
from app.services import profit_insight as profit_insight_service

router = APIRouter(prefix="/internal/v2/ai", dependencies=[Depends(verify_internal_token)])


@router.post(
    "/profit-insights",
    response_model=ProfitInsightResponse,
    response_model_exclude_none=True,
)
async def generate_profit_insight(req: ProfitInsightRequest) -> ProfitInsightResponse:
    return await profit_insight_service.generate(req)
