import json

import httpx

from app.clients import llm
from app.main import app

REQUEST_BODY = {
    "storeId": 1024,
    "uploadId": 55,
    "dataDays": 30,
    "metrics": {
        "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
        ],
        "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
    },
}

LLM_SUCCESS = json.dumps(
    {
        "insights": [
            {
                "text": "최근 화요일 매출이 3주 연속 감소하고 있어요.",
                "evidence": {"metric": "dow_trend", "period": "TUE", "value": -0.184},
            }
        ]
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
            "/internal/ai/insights/generate",
            json=body,
            headers=headers,
        )


async def test_정상_요청이_인사이트를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert body["insights"][0]["text"]
    assert body["promptVersion"] == "v1"


async def test_dataDays가_14_미만이면_LLM_호출없이_INSUFFICIENT_DATA를_반환한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    body = {**REQUEST_BODY, "dataDays": 13}
    res = await _post(body)

    assert res.status_code == 200
    result = res.json()
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["insights"] == []
    assert calls == [], "14일 미만이면 LLM을 호출하지 않는다"


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
