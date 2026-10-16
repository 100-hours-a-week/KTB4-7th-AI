import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.config import settings
from app.core.errors import ApiError

# docs/api정의서.md 확정 반영 (2026-09-16), 순이익 추가(2026-10-16, Issue #170).
# 리뷰는 아직 v1 MVP 범위 밖이라 비활성 상태다 — 원본 데이터를 만드는 백엔드 잡이 없어
# 호출해도 항상 빈 값이다(계약 대조표 §6 참고).
#
# get_weather/get_district_benchmark 경로는 BE와 협의 완료(2026-10-16, Issue #170).
# v2인 이유는 get_profit과 같다 — 팀 릴리스 버전 체계(v1 MVP / v2 순이익·날씨·상권 / v3
# 리뷰)에서 날씨·상권도 순이익과 같은 V2 묶음이다(docs/STATE.md "v2 의 나머지 — 날씨·
# 공휴일·상권"). 응답 필드 상세는 아직 BE 확정 전이라 devtools/stub_backend.py 는
# AI 쪽 제안 모양(WeatherContext/DistrictBenchmark와 동일)으로 개발·테스트한다.
TOOL_PATHS = {
    "get_sales_summary": "/internal/v1/sales/summary",
    "get_category_breakdown": "/internal/v1/sales/categories",
    "get_hourly_profile": "/internal/v1/sales/hourly-profiles",
    "get_forecast": "/internal/v1/sales/forecasts",
    "get_profit": "/internal/v2/sales/profit-analyses",
    "get_weather": "/internal/v2/sales/weather",
    "get_district_benchmark": "/internal/v2/sales/district-benchmark",
    # "get_review_summary": "/internal/v1/review-summaries",
}


class BackendError(Exception):
    pass


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

    return res.json().get("data", {})
