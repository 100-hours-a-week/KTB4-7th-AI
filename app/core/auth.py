from fastapi import Header

from app.core.config import settings
from app.core.errors import ApiError


async def verify_internal_key(x_internal_api_key: str = Header(default="")) -> None:
    if x_internal_api_key != settings.internal_api_key:
        raise ApiError(401, "UNAUTHORIZED", "서비스 토큰이 누락되었거나 올바르지 않습니다.")
