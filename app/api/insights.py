from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_key
from app.schemas.insight import InsightRequest, InsightResponse
from app.services import insight as insight_service

router = APIRouter(prefix="/internal/ai", dependencies=[Depends(verify_internal_key)])


@router.post("/insights/generate", response_model=InsightResponse)
async def generate_insight(req: InsightRequest) -> InsightResponse:
    return await insight_service.generate(req)
