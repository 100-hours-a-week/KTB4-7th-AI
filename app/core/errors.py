import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def _body(code: str, message: str, trace_id: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message, "traceId": trace_id}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        trace_id = str(uuid.uuid4())
        logger.warning("%s %s trace=%s", exc.code, exc.message, trace_id)
        return JSONResponse(exc.status, _body(exc.code, exc.message, trace_id))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = str(uuid.uuid4())
        logger.warning("VALIDATION_ERROR %s trace=%s", exc.errors(), trace_id)
        return JSONResponse(
            422,
            _body("VALIDATION_ERROR", "요청 필드가 스키마와 일치하지 않습니다.", trace_id),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        trace_id = str(uuid.uuid4())
        logger.exception("INTERNAL_ERROR trace=%s", trace_id)
        return JSONResponse(
            500, _body("INTERNAL_ERROR", "AI 서버 내부 오류가 발생했습니다.", trace_id)
        )
