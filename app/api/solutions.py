from fastapi import APIRouter

from app.schemas.solution import SolutionRequest, SolutionResponse
from app.services import solution as solution_service

router = APIRouter(prefix="/internal/v1/ai")


@router.post("/solutions/generate", response_model=SolutionResponse)
async def generate_solution(req: SolutionRequest) -> SolutionResponse:
    return await solution_service.generate(req)
