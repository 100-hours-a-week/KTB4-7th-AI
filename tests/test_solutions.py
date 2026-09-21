import json

import httpx

from app.clients import llm
from app.main import app

REQUEST_BODY = {
    "storeId": 1024,
    "salesAnalysisId": 771,
    "targetDate": "2026-08-31",  # 월요일
    "triggerType": "UPLOAD",
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
                "rankNo": 1,
                "title": "평일 14~17시 프로모션 진행",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "오후 비피크 시간대 방문 유도를 위해...",
                "evidence": "평일 14시 매출이 주말 대비 크게 낮습니다.",
            }
        ]
    },
    ensure_ascii=False,
)

LLM_SUCCESS_NO_EVIDENCE = json.dumps(
    {
        "solutionCards": [
            {
                "rankNo": 1,
                "title": "평일 14~17시 프로모션 진행",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "오후 비피크 시간대 방문 유도를 위해...",
            }
        ]
    },
    ensure_ascii=False,
)


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/solutions/generate", json=body)


async def test_정상_요청이_솔루션카드를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["message"]
    assert body["data"]["targetDate"] == "2026-08-31"
    assert body["data"]["solutionCards"][0]["rankNo"] == 1
    assert body["data"]["solutionCards"][0]["summaryText"]
    evidence = body["data"]["solutionCards"][0]["evidence"]
    assert evidence == "평일 14시 매출이 주말 대비 크게 낮습니다."
    assert body["data"]["modelVersion"]
    assert "promptVersion" not in body["data"]


async def test_evidence_없는_응답도_200이고_evidence는_null이다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS_NO_EVIDENCE

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["solutionCards"][0]["evidence"] is None


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
    """실제 Claude 는 프롬프트에 "JSON만 출력" 이라고 써도 ```json 펜스를 붙여 내려준다.

    2026-09-21 실호출(devtools/llm_smoke.py)에서 발견 — 이 때문에 두 번 다 파싱에 실패해
    500 이 났다. 단위 테스트는 전부 순수 JSON 만 흘려서 못 잡던 구멍이다.
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return f"```json\n{LLM_SUCCESS}\n```"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["solutionCards"][0]["rankNo"] == 1
