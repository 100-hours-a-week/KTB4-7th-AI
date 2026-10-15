from fastapi import APIRouter, Depends

from app.core.auth import verify_internal_token
from app.schemas.menu import MenuRecognitionRequest, MenuRecognitionResponse
from app.services import menu as menu_service

router = APIRouter(prefix="/internal/v2/ai", dependencies=[Depends(verify_internal_token)])


@router.post("/menu-recognition", response_model=MenuRecognitionResponse)
async def recognize_menu(req: MenuRecognitionRequest) -> MenuRecognitionResponse:
    data = await menu_service.recognize_menu(req)
    return MenuRecognitionResponse(data=data)
