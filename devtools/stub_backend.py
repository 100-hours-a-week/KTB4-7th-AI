"""BE 분석 모듈 스텁. 실 BE가 붙기 전까지 챗봇 툴 개발·테스트에 쓴다.

    uv run python devtools/stub_backend.py

응답 값은 노션 API 정의서의 예시를 그대로 옮겼다. 비율이 퍼센트 표기(12.5, 56.3)인데
위키는 소수 표기(0.125, 0.563)다 — Issue #2 6번. 계약이 정해지면 여기도 같이 고친다.
"""

import uvicorn
from fastapi import FastAPI

from app.clients.backend import TOOL_PATHS

RESPONSES = {
    "get_sales_summary": {
        "period": {"type": "THIS_MONTH", "startDate": "2026-09-01", "endDate": "2026-09-08"},
        "netSales": 3200000,
        "orderCount": 420,
        "averageOrderValue": 7619,
        "changeRate": 12.5,
    },
    "get_category_breakdown": {
        "categories": [{"categoryName": "커피", "netSales": 1800000, "ratio": 56.3}],
        "menuRankings": [
            {"rank": 1, "menuName": "아메리카노", "netSales": 800000, "quantity": 250}
        ],
    },
    "get_hourly_profile": {
        "hourlyProfiles": [
            {"hour": 12, "netSales": 420000, "orderCount": 55},
            {"hour": 13, "netSales": 380000, "orderCount": 49},
            {"hour": 15, "netSales": 90000, "orderCount": 11},
        ]
    },
    "get_forecast": {
        "forecasts": [
            {
                "targetDate": "2026-09-09",
                "predictedSales": 420000,
                "lowerBound": 360000,
                "upperBound": 480000,
            }
        ],
        "generatedAt": "2026-09-08T00:10:00+09:00",
    },
}

app = FastAPI(title="스텁 BE 분석 모듈")


def _register(tool: str, path: str) -> None:
    @app.get(path, name=tool)
    async def _handler() -> dict:
        return {"message": "조회에 성공했습니다.", "data": RESPONSES[tool]}


for _tool, _path in TOOL_PATHS.items():
    _register(_tool, _path)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
