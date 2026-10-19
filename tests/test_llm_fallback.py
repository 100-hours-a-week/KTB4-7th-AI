"""GPU(로컬 vLLM) 가동 중단 시 Claude API로 자동 폴백하는지 확인한다.

세 층을 각각 잰다.
- circuit breaker(app/clients/circuit_breaker.py) 자체의 상태 전환.
- llm.complete()가 가용성 오류에서만 fallback을 쓰고 영구 오류는 그대로 올리는지.
- 챗봇(app/api/chat.py)이 첫 토큰 전 실패에서만 전환하고, 이미 보낸 뒤엔 안 바꾸는지.
"""

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.api.chat import _stream
from app.clients import llm
from app.clients.circuit_breaker import CircuitBreaker
from app.core.config import settings
from app.core.errors import ApiError
from app.services.chat import graph as chat_graph
from tests.test_chat import REQUEST_BODY, FakeModel, _answer_chunks, _error_events, _post


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _breaker(threshold: int = 3, cooldown: float = 30.0) -> tuple[CircuitBreaker, _FakeClock]:
    clock = _FakeClock()
    breaker = CircuitBreaker(failure_threshold=threshold, cooldown_seconds=cooldown, clock=clock)
    return breaker, clock


# ── circuit breaker 단위 ──────────────────────────────────────────────


def test_닫힌_상태에서는_건너뛰지_않는다():
    breaker, _ = _breaker()
    assert breaker.should_skip() is False


def test_연속_실패가_임계치_미만이면_안_열린다():
    breaker, _ = _breaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.should_skip() is False


def test_연속_실패가_임계치에_도달하면_열린다():
    breaker, _ = _breaker(threshold=3)
    for _ in range(3):
        breaker.record_failure()
    assert breaker.should_skip() is True


def test_쿨다운_중에는_계속_건너뛴다():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure()
    clock.now += 10.0
    assert breaker.should_skip() is True


def test_쿨다운이_지나면_probe_기회를_한번만_준다():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure()
    clock.now += 31.0
    assert breaker.should_skip() is False
    assert breaker.probing is True


def test_probe_성공하면_닫히고_다시_정상_판정된다():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure()
    clock.now += 31.0
    breaker.should_skip()
    breaker.record_success()
    assert breaker.probing is False
    assert breaker.should_skip() is False


def test_probe_실패하면_즉시_다시_연다():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure()
    clock.now += 31.0
    breaker.should_skip()
    breaker.record_failure()
    assert breaker.should_skip() is True


def test_probe가_진행중이면_동시_요청은_건너뛴다():
    """헥터 PR #185 리뷰: should_skip()이 probing을 쓰기만 하고 안 읽어서,
    쿨다운이 끝난 순간 동시 요청이 전부 probe를 탈 수 있었다 — 회귀 테스트."""
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure()
    clock.now += 31.0

    first = breaker.should_skip()
    concurrent = [breaker.should_skip() for _ in range(5)]

    assert first is False, "첫 요청은 probe 기회를 받아야 한다"
    assert concurrent == [True] * 5, "probe 결과가 나오기 전 동시 요청은 전부 건너뛰어야 한다"


# ── llm.complete() 통합 ────────────────────────────────────────────────


class _RaisingOpenAI:
    """OpenAI 호환 클라이언트 모양(.chat.completions.create)으로 예외를 던진다.

    실제로 쓰는 primary가 llm_provider="openai"(로컬 vLLM 흉내)라 이 모양이어야 한다 —
    Anthropic 모양(.messages.create)으로 만들면 .chat 접근에서 AttributeError가 나고,
    그게 우연히 또 502로 뭉개져서 진짜 테스트하려던 상태코드를 가린다."""

    def __init__(self, exc: Exception):
        self._exc = exc
        self.calls = 0
        self.chat = type("Chat", (), {"completions": self})()

    async def create(self, **kwargs):
        self.calls += 1
        raise self._exc


class _FakeAnthropicSuccess:
    calls = 0

    def __init__(self, **kwargs):
        self.messages = self

    async def create(self, **kwargs):
        _FakeAnthropicSuccess.calls += 1
        return type("R", (), {"content": [type("C", (), {"text": "fallback-ok"})()]})()


def _provider_error(status: int | None) -> Exception:
    exc = RuntimeError("provider said no")
    if status is not None:
        exc.status_code = status
    return exc


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "qwen-primary")
    monkeypatch.setattr(settings, "llm_fallback_provider", None)
    monkeypatch.setattr(settings, "llm_fallback_model", None)
    _FakeAnthropicSuccess.calls = 0


async def test_폴백_미설정이면_가용성_오류도_그대로_올린다(monkeypatch):
    """기존 운영(anthropic 단독) 동작과 100% 동일해야 한다 — 가장 중요한 회귀 보장."""
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(None)))

    with pytest.raises(ApiError) as caught:
        await llm.complete("sys", "user")

    assert caught.value.status == 502


async def test_가용성_오류면_fallback_provider로_재시도한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(None)))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    result = await llm.complete("sys", "user")

    assert result == "fallback-ok"
    assert _FakeAnthropicSuccess.calls == 1


async def test_영구_오류면_fallback을_쓰지_않는다(monkeypatch):
    """모델명·키·권한 오류는 fallback으로 바뀌지 않는다 — #166/#167 영구오류 분류 재사용."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(401)))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    with pytest.raises(ApiError) as caught:
        await llm.complete("sys", "user")

    assert caught.value.status == 500
    assert _FakeAnthropicSuccess.calls == 0


async def test_연속_실패가_임계치에_닿으면_breaker가_열려_primary를_건너뛴다(monkeypatch):
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0))
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    primary = _RaisingOpenAI(_provider_error(None))
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: primary)

    await llm.complete("sys", "user")  # 1차 실패
    await llm.complete("sys", "user")  # 2차 실패 → breaker 임계치 도달, 열림
    await llm.complete("sys", "user")  # 열린 상태 — primary 호출 자체가 없어야 함

    assert primary.calls == 2, "breaker가 열린 뒤엔 primary를 다시 시도하지 않아야 한다"
    assert _FakeAnthropicSuccess.calls == 3


# ── 챗봇 첫 토큰 전 전환 ─────────────────────────────────────────────────
# _reset(위)이 모듈 전체에 autouse라 llm_provider/llm_model을 openai/qwen-primary로
# 깔아두는데, 여기선 챗봇의 primary를 anthropic:claude-primary로 재설정한다.


async def test_breaker가_열려있으면_primary_모델을_안_만들고_fallback으로_바로_간다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-primary")
    opened = CircuitBreaker(failure_threshold=1, cooldown_seconds=9999.0)
    opened.record_failure()
    monkeypatch.setattr(llm, "_breaker", opened)
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")

    built_with: list[tuple[str, str]] = []

    def spy_get_model(tools, provider, model_name):
        built_with.append((provider, model_name))
        return FakeModel(responses=[AIMessage(content="폴백 답변")])

    monkeypatch.setattr(chat_graph, "get_model", spy_get_model)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert "".join(_answer_chunks(res.text)) == "폴백 답변"
    assert built_with == [("anthropic", "claude-fallback")]


async def test_첫_토큰_전_실패면_fallback으로_전환해_에러_없이_끝난다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-primary")
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))

    from anthropic import APITimeoutError

    built_with: list[tuple[str, str]] = []

    def spy_get_model(tools, provider, model_name):
        built_with.append((provider, model_name))
        if model_name == settings.llm_fallback_model:
            return FakeModel(responses=[AIMessage(content="폴백 답변")])
        return FakeModel(
            responses=[APITimeoutError(httpx.Request("POST", "https://api.anthropic.com"))]
        )

    monkeypatch.setattr(chat_graph, "get_model", spy_get_model)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert _error_events(res.text) == []
    assert "".join(_answer_chunks(res.text)) == "폴백 답변"
    assert built_with == [("anthropic", "claude-primary"), ("anthropic", "claude-fallback")]


async def test_토큰을_이미_보낸_뒤_실패하면_전환하지_않는다(monkeypatch):
    """내용을 되돌릴 수 없어서 기존 error 이벤트 동작을 유지해야 한다 — 회귀.

    graph.py의 agent↔tools 사이클을 FakeModel로 재현하기보다, test_sentry.py와 같은
    방식으로 astream_events 자체를 흉내내 "텍스트 한 조각을 보낸 뒤 실패"를 직접 만든다
    — 그래야 sent_any=True가 된 뒤의 실패라는 걸 확실히 보장할 수 있다.
    """
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))

    build_count = 0

    class PartiallyStreamedThenFailingGraph:
        async def astream_events(self, state, version):
            yield {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "agent"},
                "data": {"chunk": AIMessageChunk(content="첫 토큰")},
            }
            raise ApiError(504, "AI_TIMEOUT", "모델 타임아웃")

    def spy_build_graph(model, tools):
        nonlocal build_count
        build_count += 1
        return PartiallyStreamedThenFailingGraph()

    monkeypatch.setattr(chat_graph, "get_model", lambda tools, provider, model_name: object())
    monkeypatch.setattr(chat_graph, "build_graph", spy_build_graph)

    chunks = [
        chunk
        async for chunk in _stream(
            tools=[],
            initial_state={},
            provider="anthropic",
            model_name="claude-primary",
            started_on_fallback=False,
        )
    ]

    text = "".join(chunks)
    assert "첫 토큰" in text
    assert "AI_TIMEOUT" in text
    assert text.rstrip().endswith("data: [DONE]")
    assert build_count == 1, "이미 토큰을 보낸 뒤라 fallback으로 다시 만들면 안 된다"
