import json

import httpx

from app.clients import llm
from app.main import app

REQUEST_BODY = {
    "storeId": 1024,
    "salesAnalysisId": 771,
    "targetDate": "2026-08-31",
    "triggerType": "SCHEDULED",
    "context": {
        "dayOfWeek": "MON",
        "isWeekend": False,
        "isHoliday": False,
        "dataBasisPeriod": "2026-08-30",
    },
    "metrics": {
        "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
        "predictedSalesToday": 1250000,
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
        ],
        "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
        "reviewSummary": None,
    },
}

LLM_SUCCESS = json.dumps(
    {
        "solutionCards": [
            {
                "rank": 1,
                "title": "평일 14~17시 프로모션 진행",
                "detailContent": "오후 비피크 시간대 방문 유도를 위해...",
                "evidence": {
                    "metric": "hourly_contribution",
                    "dayType": "WEEKDAY",
                    "period": "14-17",
                    "value": 30000,
                },
            }
        ],
        "aiInsight": "이번 달 매출은 지난달 대비 12% 감소했습니다.",
    },
    ensure_ascii=False,
)


_UNSET = object()


async def _post(body: dict, headers=_UNSET) -> httpx.Response:
    if headers is _UNSET:
        headers = {"X-Internal-Api-Key": "test-key"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/internal/ai/solutions/generate",
            json=body,
            headers=headers,
        )


async def test_정상_요청이_솔루션카드를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert body["targetDate"] == "2026-08-31"
    assert body["solutionCards"][0]["rank"] == 1
    assert body["modelVersion"]
    assert body["promptVersion"] == "v1"


async def test_인증키가_없으면_401():
    res = await _post(REQUEST_BODY, headers={})
    assert res.status_code == 401


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "metrics"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_LLM_파싱이_계속_실패하면_500_이고_1회만_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return "이건 JSON이 아닙니다"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "최초 시도 + 재시도 1회 = 2번 호출되어야 한다"
