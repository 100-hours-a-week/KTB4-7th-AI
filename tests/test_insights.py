import json

import httpx

from app.clients import llm
from app.main import app

REQUEST_BODY = {
    "storeId": 1024,
    "salesAnalysisId": 771,
    "targetMonth": "2026-08",
    "triggerType": "UPLOAD",
    "maxInsightCount": 3,
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
            "최근 화요일 매출이 3주 연속 감소하고 있어요.",
            "오후 3~5시는 다른 시간대보다 매출이 낮아요.",
        ]
    },
    ensure_ascii=False,
)


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/sales-insights", json=body)


async def test_정상_요청이_인사이트를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["data"]["targetMonth"] == "2026-08"
    assert body["data"]["insights"][0]
    assert "missingData" not in body["data"]


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "metrics"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]


async def test_LLM_파싱이_계속_실패하면_500_이고_1회만_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return "이건 JSON이 아닙니다"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "최초 시도 + 재시도 1회 = 2번 호출되어야 한다"


async def test_모델이_JSON을_코드펜스로_감싸도_파싱된다(monkeypatch):
    """솔루션과 같은 이유 — tests/test_solutions.py 의 같은 이름 테스트 참고."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return f"```json\n{LLM_SUCCESS}\n```"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["insights"]


def _insights(*items) -> str:
    return json.dumps({"insights": list(items)}, ensure_ascii=False)


async def test_빈_배열이면_재시도하고_그래도_비면_500이다(monkeypatch):
    """`insights is not None` 으로 끊던 탓에 빈 배열이 재시도 없이 200 으로 나갔다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return _insights()

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "빈 배열도 재시도해야 한다"


async def test_maxInsightCount_를_넘으면_재시도한다(monkeypatch):
    """BE 가 3개를 요청했는데 5개가 나가면 AN-01 화면이 넘친다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _insights("1", "2", "3", "4", "5")
        return _insights("문장1", "문장2", "문장3")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(res.json()["data"]["insights"]) == 3
    assert len(calls) == 2


async def test_빈_문장이_섞이면_재시도한다(monkeypatch):
    """화면에 빈 불릿이 생긴다 — 에러가 아니라 화면이 이상해지는 방식으로 드러난다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _insights("정상 문장", "   ", "또 정상")
        return _insights("문장1", "문장2")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["insights"] == ["문장1", "문장2"]
    assert len(calls) == 2
