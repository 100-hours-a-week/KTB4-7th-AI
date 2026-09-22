from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_token
from app.schemas.solution import SolutionRequest, SolutionResponse
from app.services import solution as solution_service

router = APIRouter(prefix="/internal/v1/ai", dependencies=[Depends(verify_internal_token)])


@router.post("/solutions/generate", response_model=SolutionResponse)
async def generate_solution(req: SolutionRequest) -> SolutionResponse:
    return await solution_service.generate(req)
