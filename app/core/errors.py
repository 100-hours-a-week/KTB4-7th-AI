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
    """실패 응답 공통 바디.

    `status: "FAILED"` 는 2026-09-22 BE 요청으로 추가했다. 성공 응답의
    COMPLETED/INSUFFICIENT_DATA 와 봉투 모양을 맞춰 BE 가 한 가지 방식으로 파싱하게 한다.
    노션 계약에 필드를 더하는 것이라 버전 상향은 하지 않는다(AGENTS.md "필드 추가는 허용").

    재시도 여부는 이 바디가 아니라 **HTTP 상태 코드**가 정한다 — BE 재시도 정책이
    "연결 실패·503·504만 재시도"로 쓰여 있어서, 실패까지 200 으로 내리면 그 정책이
    아예 발동하지 않는다. 504(모델 타임아웃)만 재시도 대상이고, 500(생성 실패)은
    AI 가 이미 1회 재시도한 뒤라 대상이 아니다.

    주의: 공급자 장애는 현재 502 라 BE 재시도 대상이 아니다. Anthropic 의 429/529 처럼
    재시도하면 풀릴 오류까지 502 로 묶여 한 번에 실패한다. 503 으로 바꾸면 재시도를
    받을 수 있지만 솔루션·챗봇의 같은 경로까지 함께 바뀌므로 BE 와 합의 후에 정한다.
    """
    body = {"message": message, "status": "FAILED", "data": None}
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
