from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_token
from app.schemas.insight import InsightRequest, InsightResponse
from app.services import insight as insight_service

router = APIRouter(prefix="/internal/v1/ai", dependencies=[Depends(verify_internal_token)])


@router.post(
    "/sales-insights",
    response_model=InsightResponse,
    response_model_exclude_none=True,
)
async def generate_insight(req: InsightRequest) -> InsightResponse:
    return await insight_service.generate(req)
