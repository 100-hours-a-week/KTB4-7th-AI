"""BE 분석 모듈 스텁. 실 BE가 붙기 전까지 챗봇 툴 개발·테스트에 쓴다.

    uv run python devtools/stub_backend.py

응답 값은 API 정의서(docs/api정의서.md)의 예시를 그대로 옮겼다 — 비율·증감률은 소수 표기다
(2026-09-17 BE 확인: 금액은 정수, 비율은 소수). 스텁이 명세와 어긋나면 테스트가 틀린 계약을
검증하게 되므로 예시 값과 타입을 명세에 맞춘다.
"""

import uvicorn
from fastapi import FastAPI

from app.clients.backend import TOOL_PATHS

RESPONSES = {
    "get_sales_summary": {
        "period": {"type": "THIS_MONTH", "startDate": "2026-09-01", "endDate": "2026-09-08"},
        "totalSales": 3200000,
        "orderCount": 420,
        "averageOrderValue": 7619,
        "changeRate": 0.125,
    },
    "get_category_breakdown": {
        "categories": [{"categoryName": "커피", "menuSales": 1800000, "ratio": 0.563}],
        "menuRankings": [
            {"rank": 1, "menuName": "아메리카노", "menuSales": 800000, "quantity": 250}
        ],
    },
    "get_hourly_profile": {
        "hourlyProfiles": [
            {"hour": 12, "menuSales": 420000, "orderCount": 55},
            {"hour": 13, "menuSales": 380000, "orderCount": 49},
            {"hour": 15, "menuSales": 90000, "orderCount": 11},
        ]
    },
    "get_forecast": {
        "forecasts": [
            {
                "targetDate": "2026-09-09",
                "predictedSalesAmount": 420000,
                "lowerBound": 360000,
                "upperBound": 480000,
            }
        ],
        "generatedAt": "2026-09-08T00:10:00+09:00",
    },
    # 아래 2종은 TOOL_PATHS 에서 주석 처리돼 있어 지금은 라우트로 등록되지 않는다.
    # v1 MVP 포함으로 결정되면 TOOL_PATHS 주석만 풀면 바로 살아난다.
    "get_profit": {
        "netSales": 3200000,
        "ingredientCost": 1040000,
        "fixedCost": 1200000,
        "netProfit": 960000,
        "composition": [{"type": "NET_PROFIT", "amount": 960000, "ratio": 0.3}],
    },
    "get_review_summary": {
        "summary": "커피 맛과 친절한 응대에 대한 긍정 반응이 많습니다.",
        "sentiment": {"positive": 0.82, "neutral": 0.14, "negative": 0.04},
        "keywords": ["커피", "친절", "대기시간"],
    },
}

app = FastAPI(title="스텁 BE 분석 모듈")


def _register(tool: str, path: str) -> None:
    @app.get(path, name=tool)
    async def _handler() -> dict:
        return {"message": "조회에 성공했습니다.", "data": RESPONSES[tool]}


_missing = set(TOOL_PATHS) - set(RESPONSES)
if _missing:
    raise RuntimeError(f"스텁 응답이 없는 툴: {sorted(_missing)}")

for _tool, _path in TOOL_PATHS.items():
    _register(_tool, _path)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
