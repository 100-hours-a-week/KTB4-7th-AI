import logging

import httpx
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.config import settings
from app.core.errors import ApiError
from app.schemas.common import DistrictBenchmark, WeatherContext

logger = logging.getLogger(__name__)

# docs/api정의서.md 확정 반영 (2026-09-16), 순이익 추가(2026-10-16, Issue #170).
#
# get_weather/get_district_benchmark 경로는 BE와 협의 완료(2026-10-16, Issue #170).
# v2인 이유는 get_profit과 같다 — 팀 릴리스 버전 체계(v1 MVP / v2 순이익·날씨·상권)에서
# 날씨·상권도 순이익과 같은 V2 묶음이다(docs/STATE.md "v2 의 나머지 — 날씨·공휴일·상권").
# 응답 DTO(ChatWeatherResponse/ChatDistrictBenchmarkResponse/ChatLookupResponse)는 BE dev에
# 구현돼 있다(KTB4-7th-BE, com.memme.dto.chat). AI 쪽 Pydantic 응답 검증은 아직 붙이지
# 않아 devtools/stub_backend.py 는 AI 쪽 제안 모양(WeatherContext/DistrictBenchmark와
# 동일)으로만 개발·테스트한다 — 응답 검증 추가는 별도 작업으로 진행한다.
TOOL_PATHS = {
    "get_sales_summary": "/internal/v1/sales/summary",
    "get_category_breakdown": "/internal/v1/sales/categories",
    "get_hourly_profile": "/internal/v1/sales/hourly-profiles",
    "get_forecast": "/internal/v1/sales/forecasts",
    "get_profit": "/internal/v2/sales/profit-analyses",
    "get_weather": "/internal/v2/sales/weather",
    "get_district_benchmark": "/internal/v2/sales/district-benchmark",
}

# 날씨·상권 2종만 BE가 ChatLookupResponse<T>(status: READY|EMPTY, data) 로 감싸 응답한다
# (KTB4-7th-BE com.memme.dto.chat). 나머지 5종은 status 래퍼가 없는 기존 {message,data}
# 계약이라 이 표에 없는 툴은 검증하지 않는다(2026-11-04, Issue #269).
CHAT_LOOKUP_SCHEMAS = {
    "get_weather": WeatherContext,
    "get_district_benchmark": DistrictBenchmark,
}


class BackendError(Exception):
    pass


def _headers() -> dict[str, str]:
    """AI→BE 내부 호출에 붙이는 헤더.

    BE 는 날씨·상권 두 경로에만 `Authorization: Bearer {INTERNAL_AI_TOKEN}` 을 요구하고
    없으면 401 이다(2026-10-19 확정, BE PR #507). 경로별로 나누지 않고 전부 붙인다 —
    나머지 경로는 토큰을 무시하므로 해가 없고, BE 가 다른 경로에 토큰을 걸 때 또 깨지지
    않는다.

    토큰이 비어 있으면 헤더를 아예 보내지 않는다 — app/core/auth.py 가 BE→AI 방향에서
    쓰는 기준과 같다. devtools/stub_backend.py 와 로컬 개발은 토큰을 검사하지 않는데,
    빈 Bearer 를 보내면 그쪽이 오히려 깨진다.
    """
    token = settings.internal_ai_token
    return {"Authorization": f"Bearer {token}"} if token else {}


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.2),
    retry=retry_if_exception_type(BackendError),
    reraise=True,
)
async def call_tool(tool: str, params: dict) -> dict:
    """BE 분석 모듈의 사전 집계 조회 API를 호출한다. 위키 목표는 개별 50ms 이내."""
    path = TOOL_PATHS.get(tool)
    if path is None:
        raise ApiError(500, "UNKNOWN_TOOL", f"등록되지 않은 툴입니다: {tool}")

    query = {k: v for k, v in params.items() if v is not None}

    try:
        async with httpx.AsyncClient(
            base_url=settings.backend_base_url,
            timeout=settings.backend_timeout_seconds,
            headers=_headers(),
        ) as client:
            res = await client.get(path, params=query)
    except httpx.HTTPError as exc:
        raise BackendError(f"{tool} 호출 실패: {exc}") from exc

    if res.status_code == 404:
        return {}
    if res.status_code >= 500:
        raise BackendError(f"{tool} 응답 {res.status_code}")
    if res.status_code >= 400:
        raise ApiError(502, "BACKEND_ERROR", f"{tool} 요청이 거부되었습니다({res.status_code}).")

    body = res.json()

    schema = CHAT_LOOKUP_SCHEMAS.get(tool)
    if schema is not None:
        # status=EMPTY 는 오류가 아니라 "조회할 데이터가 없음" 이다(2026-10-19 BE 계약,
        # PR #506). READY인데 data가 스키마를 통과하지 못하거나 status 자체가 없거나
        # READY/EMPTY 가 아니면, EMPTY 로 뭉개지 않고 계약 위반으로 구분한다 — 그래야
        # "데이터가 원래 없음"과 "응답이 깨짐"이 섞이지 않는다(2026-11-04, Issue #269).
        status = body.get("status")
        if status == "EMPTY":
            return {}
        if status != "READY":
            logger.warning("%s 응답 status 가 올바르지 않습니다: %r", tool, status)
            raise ApiError(502, "BACKEND_CONTRACT_ERROR", f"{tool} 응답 형식이 올바르지 않습니다.")
        try:
            return schema.model_validate(body.get("data")).model_dump()
        except ValidationError as exc:
            logger.warning("%s READY 응답이 계약과 다릅니다: %s", tool, exc)
            raise ApiError(
                502, "BACKEND_CONTRACT_ERROR", f"{tool} 응답이 계약과 다릅니다."
            ) from exc

    # 나머지 5종은 status 래퍼가 없는 {message,data} 계약이다. data 키가 있고 값만
    # null 인 응답(EMPTY)에서 .get("data", {}) 기본값이 안 쓰여 None 이 그대로 나가면
    # chat/graph.py 의 result.get(...) 에서 AttributeError 로 터진다 — 404 와 같은 자리에서
    # 빈 값으로 둔다.
    return body.get("data") or {}
