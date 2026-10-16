"""위키 [AI] 단계4 §4.2. 챗봇이 부족한 지표를 조회할 때 쓰는 툴 8종 중 활성화된 7종
(2026-10-16, Issue #170 — 순이익·날씨·상권 추가).

storeId는 요청 범위 값이라 LLM에 노출하지 않고 클로저로 고정한다.
리뷰(v3)만 app/clients/backend.py TOOL_PATHS 와 동일하게 MVP 범위 밖이다.
get_weather/get_district_benchmark는 경로는 BE와 협의 완료, 응답 필드는 확정 전이라
devtools/stub_backend.py 의 AI 쪽 제안 모양 기준으로만 동작한다.
"""

from langchain_core.tools import tool

from app.clients import backend


def build_tools(store_id: int) -> list:
    @tool
    async def get_sales_summary(
        period: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        """기간 매출 요약과 전기 대비 증감률을 조회한다.
        period: TODAY | THIS_WEEK | THIS_MONTH | CUSTOM.
        period=CUSTOM 이면 start_date/end_date(YYYY-MM-DD)가 필수다."""
        return await backend.call_tool(
            "get_sales_summary",
            {"storeId": store_id, "period": period, "startDate": start_date, "endDate": end_date},
        )

    @tool
    async def get_category_breakdown(
        period: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        """카테고리·메뉴별 매출 비중과 랭킹을 조회한다.
        period: TODAY | THIS_WEEK | THIS_MONTH | CUSTOM.
        period=CUSTOM 이면 start_date/end_date(YYYY-MM-DD)가 필수다."""
        return await backend.call_tool(
            "get_category_breakdown",
            {"storeId": store_id, "period": period, "startDate": start_date, "endDate": end_date},
        )

    @tool
    async def get_hourly_profile(
        period: str,
        day_of_week: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """시간대별 매출 분포를 조회한다.
        period: TODAY | THIS_WEEK | THIS_MONTH | CUSTOM.
        day_of_week(MONDAY..SUNDAY)를 주면 해당 요일로 한정한다.
        period=CUSTOM 이면 start_date/end_date(YYYY-MM-DD)가 필수다."""
        return await backend.call_tool(
            "get_hourly_profile",
            {
                "storeId": store_id,
                "period": period,
                "dayOfWeek": day_of_week,
                "startDate": start_date,
                "endDate": end_date,
            },
        )

    @tool
    async def get_forecast(target_date: str | None = None) -> dict:
        """저장된 매출 예측을 조회한다.
        target_date(YYYY-MM-DD)를 생략하면 다음 영업일부터 반환한다."""
        return await backend.call_tool(
            "get_forecast", {"storeId": store_id, "targetDate": target_date}
        )

    @tool
    async def get_profit(
        period: str, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        """기간 순이익(순매출·원가·고정비·구성비)을 조회한다.
        period: TODAY | THIS_WEEK | THIS_MONTH | CUSTOM.
        period=CUSTOM 이면 start_date/end_date(YYYY-MM-DD)가 필수다."""
        return await backend.call_tool(
            "get_profit",
            {"storeId": store_id, "period": period, "startDate": start_date, "endDate": end_date},
        )

    @tool
    async def get_weather(target_date: str | None = None) -> dict:
        """매장 지역의 날씨 예보를 조회한다.
        target_date(YYYY-MM-DD)를 생략하면 오늘 기준이다."""
        return await backend.call_tool(
            "get_weather", {"storeId": store_id, "targetDate": target_date}
        )

    @tool
    async def get_district_benchmark() -> dict:
        """매장이 속한 상권의 동종업종(카페) 평균 매출·피크 시간대를 조회한다.
        점포 수가 3곳 미만이거나 비교 가능한 상권 데이터가 없으면 빈 값이 올 수 있다."""
        return await backend.call_tool("get_district_benchmark", {"storeId": store_id})

    return [
        get_sales_summary,
        get_category_breakdown,
        get_hourly_profile,
        get_forecast,
        get_profit,
        get_weather,
        get_district_benchmark,
    ]
