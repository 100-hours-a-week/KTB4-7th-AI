import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from app.clients import backend
from app.main import app
from app.services.chat import graph as chat_graph

REQUEST_BODY = {
    "userId": 1,
    "storeId": 1024,
    "question": "오늘 솔루션 왜 이렇게 나왔어?",
    "context": [
        {
            "rankNo": 1,
            "title": "점심 시간대 할인",
            "summaryText": "점심 할인 프로모션을 제안합니다.",
            "detailText": "12시부터 14시까지 할인 행사를 진행하세요.",
            "evidence": "12~14시 주문 수가 전주 대비 감소했습니다.",
        }
    ],
    "history": [],
}


class FakeModel(BaseChatModel):
    """.astream 호출마다 미리 정해둔 AIMessage 를 실제 모델처럼 토큰 단위로 쪼개 돌려준다.

    tool_calls 가 있는 응답은 빈 content 한 청크로(실제 Anthropic 툴 호출 턴과 동일하게),
    텍스트 응답은 공백 기준 여러 청크로 나눠 진짜 스트리밍과 구분되게 만든다.
    """

    responses: list[Any] = []
    calls: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise NotImplementedError

    @property
    def _llm_type(self) -> str:
        return "fake"

    async def _astream(
        self, messages, stop=None, run_manager=None, **kwargs
    ) -> AsyncIterator[ChatGenerationChunk]:
        message = self.responses[self.calls]
        self.calls += 1
        if isinstance(message, Exception):
            raise message
        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_calls=message.tool_calls)
            )
            return
        words = message.content.split(" ")
        for i, word in enumerate(words):
            piece = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))


def _patch_model(monkeypatch, responses: list[AIMessage]) -> FakeModel:
    fake = FakeModel(responses=responses)
    monkeypatch.setattr(chat_graph, "get_model", lambda tools: fake)
    return fake


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/chat/messages", json=body)


def _sse_messages(text: str) -> list[dict]:
    """SSE 본문에서 [DONE] 을 제외한 이벤트들을 {"event":..., "data":...} 형태로 뽑는다."""
    messages = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            continue
        messages.append(json.loads(payload))
    return messages


def _events(text: str) -> list[dict]:
    """answerChunk 이벤트의 data 들만 순서대로 뽑는다."""
    return [m["data"] for m in _sse_messages(text) if m["event"] == "answerChunk"]


def _error_events(text: str) -> list[dict]:
    """error 이벤트의 data 들만 순서대로 뽑는다."""
    return [m["data"] for m in _sse_messages(text) if m["event"] == "error"]


def _answer_chunks(text: str) -> list[str]:
    return [event["content"] for event in _events(text)]


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


async def test_답변이_한_덩어리가_아니라_토큰_단위로_여러_청크로_온다(monkeypatch):
    _patch_model(monkeypatch, [AIMessage(content="오늘 솔루션은 오후 매출이 낮아서 나왔어요.")])

    res = await _post(REQUEST_BODY)

    chunks = _answer_chunks(res.text)
    assert len(chunks) > 1
    assert "".join(chunks) == "오늘 솔루션은 오후 매출이 낮아서 나왔어요."


async def test_부족하면_툴을_호출한_뒤_답하고_evidence를_함께_보낸다(monkeypatch):
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_sales_summary", "args": {"period": "TODAY"}, "id": "call_1"}],
    )
    final_msg = AIMessage(content="오늘 매출은 32만원이에요.")
    _patch_model(monkeypatch, [tool_call_msg, final_msg])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        assert tool == "get_sales_summary"
        assert params == {
            "storeId": 1024,
            "period": "TODAY",
            "startDate": None,
            "endDate": None,
        }
        return {
            "period": {"type": "TODAY", "startDate": "2026-09-19", "endDate": "2026-09-19"},
            "totalSales": 320000,
            "changeRate": 0.12,
        }

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    events = _events(res.text)
    assert "32만원" in "".join(e["content"] for e in events)
    assert events[-1]["evidence"] == {
        "metric": "sales_summary",
        "period": "2026-09-19",
        "dayType": None,
        "value": 0.12,
    }


async def test_툴을_부르지_않으면_evidence는_null이다(monkeypatch):
    _patch_model(monkeypatch, [AIMessage(content="오늘 솔루션은 오후 매출이 낮아서 나왔어요.")])

    res = await _post(REQUEST_BODY)

    events = _events(res.text)
    assert all(event["evidence"] is None for event in events)


async def test_툴이_2회_연속_실패하면_AI_TOOL_ERROR_이벤트를_반환한다(monkeypatch):
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
    errors = _error_events(res.text)
    assert len(errors) == 1
    assert errors[0] == {"code": "AI_TOOL_ERROR", "message": chat_graph.FAILURE_PHRASE}


async def test_모델_호출이_타임아웃되면_AI_TIMEOUT_이벤트를_반환한다(monkeypatch):
    from anthropic import APITimeoutError

    _patch_model(
        monkeypatch,
        [APITimeoutError(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))],
    )

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    errors = _error_events(res.text)
    assert len(errors) == 1
    assert errors[0]["code"] == "AI_TIMEOUT"


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "context"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]


async def test_history의_role이_BE_DB값인_대문자여도_통과한다(monkeypatch):
    _patch_model(monkeypatch, [AIMessage(content="이전 질문 이어서 답할게요.")])

    body = {
        **REQUEST_BODY,
        "history": [
            {"role": "USER", "content": "어제 매출 어땠어?"},
            {"role": "ASSISTANT", "content": "어제 매출은 28만원이었어요."},
        ],
    }
    res = await _post(body)

    assert res.status_code == 200
    assert "이전 질문 이어서" in "".join(_answer_chunks(res.text))
