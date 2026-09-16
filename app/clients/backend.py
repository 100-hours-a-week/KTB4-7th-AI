import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.core.config import settings
from app.core.errors import ApiError

# docs/api정의서.md 확정 반영 (2026-09-16). v1 MVP는 4종만 활성화한다 —
# 순이익·리뷰는 API 정의서에 있지만 원본 데이터를 만드는 백엔드 잡이 아직 v1에 없어
# 호출해도 항상 빈 값이다(계약 대조표 §6 참고). 스텁 응답은 devtools/stub_backend.py 에 준비돼 있다.
TOOL_PATHS = {
    "get_sales_summary": "/internal/v1/sales/summary",
    "get_category_breakdown": "/internal/v1/sales/categories",
    "get_hourly_profile": "/internal/v1/sales/hourly-profiles",
    "get_forecast": "/internal/v1/sales/forecasts",
    # "get_profit": "/internal/v1/sales/profit-analyses",
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

    try:
        async with httpx.AsyncClient(
            base_url=settings.backend_base_url,
            timeout=settings.backend_timeout_seconds,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        ) as client:
            res = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise BackendError(f"{tool} 호출 실패: {exc}") from exc

    if res.status_code == 404:
        return {}
    if res.status_code >= 500:
        raise BackendError(f"{tool} 응답 {res.status_code}")
    if res.status_code >= 400:
        raise ApiError(502, "BACKEND_ERROR", f"{tool} 요청이 거부되었습니다({res.status_code}).")

    return res.json().get("data", {})
