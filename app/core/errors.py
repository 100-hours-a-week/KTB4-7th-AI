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


# BE 재시도 정책(2026-09-22 확정): 502·503·504 와 연결 실패만 500ms 후 최대 1회 재시도.
# retryable 을 손으로 관리하는 표로 두면 상태 코드와 어긋날 수 있어 여기서 파생시킨다.
_RETRYABLE_STATUSES = frozenset({502, 503, 504})


def _body(message: str, code: str, status: int, fail_reason: str | None = None) -> dict:
    """실패 응답 공통 바디.

    `status: "FAILED"` 는 2026-09-22 BE 요청으로 추가했다. 성공 응답의
    COMPLETED/INSUFFICIENT_DATA 와 봉투 모양을 맞춰 BE 가 한 가지 방식으로 파싱하게 한다.
    노션 계약에 필드를 더하는 것이라 버전 상향은 하지 않는다(AGENTS.md "필드 추가는 허용").

    `error.code` 와 `error.retryable` 은 2026-09-22 BE 확정 형식이다. 재시도 판단은
    HTTP 상태 코드로도 되지만, BE 가 바디로도 받길 원해 둘 다 내보낸다. 두 신호가
    어긋나지 않도록 retryable 은 상태 코드에서 파생시킨다.

    상태 코드 구분도 같은 날 BE 와 맞췄다.

        500  AI 생성/내부 실패        재시도 X (AI 가 이미 1회 재시도한 뒤다)
        502  외부 LLM 공급자 오류      재시도 O
        503  AI 서버 일시 장애/과부하   재시도 O — **현재 이 경로는 없다**
        504  외부 LLM 타임아웃         재시도 O

    503 은 과부하 차단을 두지 않아 어떤 요청도 만들지 않는다. 자리만 잡아둔 것이다.
    """
    body = {
        "message": message,
        "status": "FAILED",
        "error": {"code": code, "retryable": status in _RETRYABLE_STATUSES},
        "data": None,
    }
    if fail_reason:
        body["failReason"] = fail_reason
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        logger.warning("%s %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status,
            content=_body(exc.message, exc.code, exc.status, exc.fail_reason),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("VALIDATION_ERROR %s", exc.errors())
        return JSONResponse(
            status_code=422,
            content=_body("요청 필드가 스키마와 일치하지 않습니다.", "VALIDATION_ERROR", 422),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("INTERNAL_ERROR")
        return JSONResponse(
            status_code=500,
            content=_body("AI 서버 내부 오류가 발생했습니다.", "INTERNAL_ERROR", 500),
        )
