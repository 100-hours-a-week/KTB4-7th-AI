from fastapi import APIRouter

from app.schemas.insight import InsightRequest, InsightResponse
from app.services import insight as insight_service

router = APIRouter(prefix="/internal/v1/ai")


@router.post(
    "/sales-insights",
    response_model=InsightResponse,
    response_model_exclude_none=True,
)
async def generate_insight(req: InsightRequest) -> InsightResponse:
    return await insight_service.generate(req)
