"""위키 [AI] 단계4 §4.2. 챗봇이 부족한 지표를 조회할 때 쓰는 툴 6종 중 활성화된 4종.

storeId는 요청 범위 값이라 LLM에 노출하지 않고 클로저로 고정한다.
나머지 2종(순이익 v2, 리뷰 v3)은 app/clients/backend.py TOOL_PATHS 와 동일하게 MVP 범위 밖이다.
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

    return [get_sales_summary, get_category_breakdown, get_hourly_profile, get_forecast]
