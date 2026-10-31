import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from app.api.chat import (
    MAX_MODEL_LEN,
    OUTPUT_RESERVE,
    TOOL_RESULT_RESERVE,
    TOOL_SCHEMA_TOKENS,
    _estimate_tokens,
    _history_budget,
    _to_lc_messages,
)
from app.clients import backend
from app.core.config import settings
from app.main import app
from app.prompts import chat as chat_prompt
from app.schemas.chat import ChatMessage
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

    tool_calls 가 있는 응답은 실제 Anthropic 이 보내는 그대로 **블록 리스트** content 로
    스트리밍한다 — 빈 문자열이 아니다. 이걸 빈 content 로 흉내내던 탓에 도구 호출 내부가
    사용자에게 그대로 새는 버그를 테스트가 못 잡았다(2026-09-21 실호출에서 발견).
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
            call = message.tool_calls[0]
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["name"],
                            "input": {},
                            "index": 0,
                        }
                    ],
                    tool_calls=message.tool_calls,
                )
            )
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "input_json_delta", "partial_json": '{"period"', "index": 0}],
                    tool_calls=message.tool_calls,
                )
            )
            return
        words = message.content.split(" ")
        for i, word in enumerate(words):
            piece = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))


def _patch_model(monkeypatch, responses: list[AIMessage]) -> FakeModel:
    fake = FakeModel(responses=responses)
    monkeypatch.setattr(chat_graph, "get_model", lambda tools, provider, model_name: fake)
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


async def test_순이익을_물어보면_get_profit을_부르고_evidence를_함께_보낸다(monkeypatch):
    tool_call_msg = AIMessage(
        content="", tool_calls=[{"name": "get_profit", "args": {"period": "TODAY"}, "id": "call_1"}]
    )
    final_msg = AIMessage(content="오늘 순이익은 96만원이에요.")
    _patch_model(monkeypatch, [tool_call_msg, final_msg])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        assert tool == "get_profit"
        assert params == {
            "storeId": 1024,
            "period": "TODAY",
            "startDate": None,
            "endDate": None,
        }
        return {"netSales": 3200000, "netProfit": 960000}

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    events = _events(res.text)
    assert "96만원" in "".join(e["content"] for e in events)
    assert events[-1]["evidence"] == {
        "metric": "profit",
        "period": "TODAY",
        "dayType": None,
        "value": 960000,
    }


async def test_날씨를_물어보면_get_weather를_부르고_evidence를_함께_보낸다(monkeypatch):
    tool_call_msg = AIMessage(
        content="", tool_calls=[{"name": "get_weather", "args": {}, "id": "call_1"}]
    )
    final_msg = AIMessage(content="오늘 비가 올 확률은 70%예요.")
    _patch_model(monkeypatch, [tool_call_msg, final_msg])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        assert tool == "get_weather"
        assert params == {"storeId": 1024, "targetDate": None}
        return {"basisDateTime": "2026-10-07 11:00", "maxPop": 0.7}

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    events = _events(res.text)
    assert events[-1]["evidence"] == {
        "metric": "weather",
        "period": "2026-10-07 11:00",
        "dayType": None,
        "value": 0.7,
    }


async def test_상권을_물어보면_get_district_benchmark를_부르고_evidence를_함께_보낸다(monkeypatch):
    tool_call_msg = AIMessage(
        content="", tool_calls=[{"name": "get_district_benchmark", "args": {}, "id": "call_1"}]
    )
    final_msg = AIMessage(content="우리 상권 카페 평균은 1,850만원이에요.")
    _patch_model(monkeypatch, [tool_call_msg, final_msg])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        assert tool == "get_district_benchmark"
        assert params == {"storeId": 1024}
        return {"basisQuarter": "2026Q2", "districtAvgMonthlySalesPerCafe": 18500000}

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    events = _events(res.text)
    assert events[-1]["evidence"] == {
        "metric": "district_benchmark",
        "period": "2026Q2",
        "dayType": None,
        "value": 18500000,
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


async def test_도구_호출_내부가_답변_청크로_새지_않는다(monkeypatch):
    """Anthropic 은 도구 호출 턴 content 를 블록 리스트로 스트리밍한다.

    그대로 내보내면 계약(content: str)이 깨지고 toolu_... ID 와 인자가 사용자에게 샌다.
    2026-09-21 실호출(devtools/llm_smoke.py)에서 발견한 회귀다.
    """
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_sales_summary", "args": {"period": "TODAY"}, "id": "toolu_01AB"}],
    )
    _patch_model(monkeypatch, [tool_call_msg, AIMessage(content="오늘 매출은 32만원이에요.")])

    async def fake_call_tool(tool: str, params: dict) -> dict:
        return {"period": {"startDate": "2026-09-19"}, "totalSales": 320000, "changeRate": 0.12}

    monkeypatch.setattr(backend, "call_tool", fake_call_tool)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    events = _events(res.text)
    assert all(isinstance(e["content"], str) for e in events), "content 는 항상 문자열이어야 한다"
    joined = "".join(e["content"] for e in events)
    assert "toolu_" not in joined
    assert "tool_use" not in joined
    assert "input_json_delta" not in joined
    assert "32만원" in joined


async def test_chatDate_가_시스템_프롬프트에_들어간다(monkeypatch):
    """BE 가 보내는 chatDate 를 받지 않으면 모델이 "지난달"을 조회하지 못하고
    증감률로 금액을 역산한다(2026-09-22 실호출로 확인).
    """
    captured = {}
    real_build = chat_prompt.build_system

    def spy(context, chat_date=None):
        captured["date"] = chat_date
        return real_build(context, chat_date)

    monkeypatch.setattr(chat_prompt, "build_system", spy)
    _patch_model(monkeypatch, [AIMessage(content="네, 확인했어요.")])

    res = await _post({**REQUEST_BODY, "chatDate": "2026-06-30"})

    assert res.status_code == 200
    assert captured["date"] == "2026-06-30"


async def test_chatDate_가_없어도_통과한다(monkeypatch):
    _patch_model(monkeypatch, [AIMessage(content="네, 확인했어요.")])
    res = await _post(REQUEST_BODY)
    assert res.status_code == 200


def _history(count: int, content: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="USER" if i % 2 == 0 else "ASSISTANT", content=content)
        for i in range(count)
    ]


def test_히스토리가_짧으면_그대로_쓴다():
    history = [ChatMessage(role="USER", content="안녕")]
    assert len(_to_lc_messages(history, 1000)) == 1


def test_예산을_넘으면_최근_대화부터_남기고_시간순을_지킨다():
    history = [
        ChatMessage(role="USER" if i % 2 == 0 else "ASSISTANT", content=f"msg-{i}")
        for i in range(10)
    ]

    messages = _to_lc_messages(history, _estimate_tokens("msg-0") * 3)

    assert [m.content for m in messages] == ["msg-7", "msg-8", "msg-9"]


def test_예산이_없으면_히스토리를_전부_버린다():
    assert _to_lc_messages(_history(10, "안녕하세요"), 0) == []


def test_같은_개수여도_메시지가_길면_덜_남는다():
    """2026-10-22 장애가 개수로 안 잡히는 이유 — 터지는 지점이 길이에 달려 있다.
    메시지 12개 제한은 짧은 대화를 과도하게 자르고, 긴 대화에서는 여유가 거의 없었다."""
    budget = 1000
    short = _to_lc_messages(_history(40, "네 알겠습니다"), budget)
    long = _to_lc_messages(_history(40, "이번 달 순매출은 18,420,000원" * 10), budget)

    assert len(short) > 12 > len(long)


def test_예산대로_담으면_출력_자리가_남는다(monkeypatch):
    """프롬프트가 max_model_len 을 꽉 채우면 vLLM 이 생성할 자리가 없어 답변이 문장
    중간에 끊긴다 — 400 도 안 나고 폴백(llm.is_capacity_error)도 안 탄다."""
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:8000/v1")
    system = "시스템 프롬프트" * 200
    question = "이번 달 매출 정리해줘"
    budget = _history_budget(system, question, "openai")
    answer = "이번 달 순매출은 18,420,000원으로 지난달보다 12.5% 늘었습니다. " * 5
    history = _history(200, answer)

    messages = _to_lc_messages(history, budget)

    used = (
        TOOL_SCHEMA_TOKENS
        + TOOL_RESULT_RESERVE
        + _estimate_tokens(system)
        + _estimate_tokens(question)
        + sum(_estimate_tokens(m.content) for m in messages)
    )
    assert MAX_MODEL_LEN - used >= OUTPUT_RESERVE


def test_예산이_None이면_히스토리를_전부_쓴다():
    history = _history(50, "이번 달 순매출은 18,420,000원" * 10)
    assert len(_to_lc_messages(history, None)) == 50


def test_로컬_vLLM일_때만_예산을_매긴다(monkeypatch):
    """상수는 전부 로컬 vLLM 창(8192) 기준이다 — fallback 으로 Claude(200k)에 가는
    요청까지 같은 자로 자르면 이유 없이 대화를 버린다."""
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:8000/v1")

    assert _history_budget("시스템", "질문", "openai") is not None
    assert _history_budget("시스템", "질문", "anthropic") is None


def test_base_url이_없으면_openai여도_자르지_않는다(monkeypatch):
    """LLM_BASE_URL 이 없으면 로컬 서버가 아니라 OpenAI 본진이다 — 창이 좁지 않다."""
    monkeypatch.setattr(settings, "llm_base_url", None)
    assert _history_budget("시스템", "질문", "openai") is None


def test_시스템_프롬프트가_길어지면_히스토리_예산이_줄어든다(monkeypatch):
    """context 카드 수에 따라 시스템 프롬프트가 변한다 — 고정값으로 둘 수 없다."""
    monkeypatch.setattr(settings, "llm_base_url", "http://127.0.0.1:8000/v1")
    assert _history_budget("짧은 시스템", "질문", "openai") > _history_budget(
        "시스템" * 500, "질문", "openai"
    )
