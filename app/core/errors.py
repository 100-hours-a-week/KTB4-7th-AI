import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fail_reason: str | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.fail_reason = fail_reason


def _body(message: str, fail_reason: str | None = None) -> dict:
    body = {"message": message}
    if fail_reason:
        body["failReason"] = fail_reason
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        logger.warning("%s %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status, content=_body(exc.message, exc.fail_reason))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("VALIDATION_ERROR %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content=_body("요청 필드가 스키마와 일치하지 않습니다."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("INTERNAL_ERROR")
        return JSONResponse(
            status_code=500,
            content=_body("AI 서버 내부 오류가 발생했습니다."),
        )
