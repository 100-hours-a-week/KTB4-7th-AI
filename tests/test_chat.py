import json

import httpx
from langchain_core.messages import AIMessage

from app.clients import backend
from app.main import app
from app.services.chat import graph as chat_graph

REQUEST_BODY = {
    "userId": 1,
    "storeId": 1024,
    "question": "오늘 솔루션 왜 이렇게 나왔어?",
    "context": {"type": "SOLUTION_DETAIL", "content": "오늘 생성된 솔루션 상세보기 전체 내용"},
    "history": [],
}


class FakeModel:
    """.ainvoke 호출마다 미리 정해둔 AIMessage 를 순서대로 돌려주는 가짜 모델."""

    def __init__(self, responses: list[AIMessage]):
        self._responses = list(responses)
        self.calls = 0

    async def ainvoke(self, messages: list) -> AIMessage:
        self.calls += 1
        return self._responses.pop(0)


def _patch_model(monkeypatch, responses: list[AIMessage]) -> FakeModel:
    fake = FakeModel(responses)
    monkeypatch.setattr(chat_graph, "get_model", lambda tools: fake)
    return fake


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/chat/messages", json=body)


def _answer_chunks(text: str) -> list[str]:
    """SSE 본문에서 [DONE] 을 제외한 answerChunk 들만 순서대로 뽑는다."""
    chunks = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            continue
        chunks.append(json.loads(payload)["data"]["content"])
    return chunks


async def test_컨텍스트만으로_답할_수_있으면_툴을_부르지_않는다(monkeypatch):
    fake = _patch_model(
        monkeypatch, [AIMessage(content="오늘 솔루션은 오후 매출이 낮아서 나왔어요.")]
    )

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.text.rstrip().endswith("data: [DONE]")
    assert "오늘 솔루션은" in "".join(_answer_chunks(res.text))
    assert fake.calls == 1


async def test_부족하면_툴을_호출한_뒤_답한다(monkeypatch):
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_sales_summary", "args": {"period": "TODAY"}, "id": "call_1"}],
    )
    final_msg = AIMessage(content="오늘 매출은 32만원이에요.")
    _patch_model(monkeypatch, [tool_call_msg, final_msg])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        assert tool == "get_sales_summary"
        assert params == {"storeId": 1024, "period": "TODAY"}
        return {"netSales": 320000}

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert "32만원" in "".join(_answer_chunks(res.text))


async def test_툴이_2회_연속_실패하면_실패_문구를_반환한다(monkeypatch):
    tool_call = {"name": "get_sales_summary", "args": {"period": "TODAY"}, "id": "call_x"}
    retry_msg = AIMessage(content="", tool_calls=[tool_call])
    _patch_model(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[tool_call]),
            retry_msg,
        ],
    )

    async def broken_call_tool(tool: str, params: dict) -> dict:
        raise backend.BackendError("boom")

    monkeypatch.setattr(backend, "call_tool", broken_call_tool)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert chat_graph.FAILURE_PHRASE in "".join(_answer_chunks(res.text))


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "context"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]
