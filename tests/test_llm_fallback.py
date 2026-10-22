"""GPU(로컬 vLLM) 가동 중단 시 Claude API로 자동 폴백하는지 확인한다.

세 층을 각각 잰다.
- circuit breaker(app/clients/circuit_breaker.py) 자체의 상태 전환.
- llm.complete()가 가용성 오류에서만 fallback을 쓰고 영구 오류는 그대로 올리는지.
- 챗봇(app/api/chat.py)이 첫 토큰 전 실패에서만 전환하고, 이미 보낸 뒤엔 안 바꾸는지.
"""

import httpx
import openai
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
    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        self.messages = self

    async def create(self, **kwargs):
        _FakeAnthropicSuccess.calls += 1
        _FakeAnthropicSuccess.last_kwargs = kwargs
        return type("R", (), {"content": [type("C", (), {"text": "fallback-ok"})()]})()


class _SucceedingOpenAI:
    def __init__(self, **kw):
        self.chat = type("Chat", (), {"completions": self})()
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        message = type("M", (), {"content": "primary-ok"})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


def _provider_error(status: int | None) -> Exception:
    exc = RuntimeError("provider said no")
    if status is not None:
        exc.status_code = status
    return exc


def _context_length_error() -> Exception:
    """실제 vLLM(--max-model-len 8192)이 2026-10-22 돌려준 400 본문을 그대로 재현한다."""
    exc = RuntimeError(
        "Error code: 400 - {'error': {'message': \"This model's maximum context "
        "length is 8192 tokens. However, your prompt contains at least 8193 input "
        "tokens, which exceeds this limit even without any output tokens. Please "
        'reduce the length of the input prompt. (parameter=input_tokens, value=8193)", '
        "'type': 'BadRequestError', 'param': 'input_tokens', 'code': 400}}"
    )
    exc.status_code = 400
    return exc


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0))
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "qwen-primary")
    monkeypatch.setattr(settings, "llm_fallback_provider", None)
    monkeypatch.setattr(settings, "llm_fallback_model", None)
    monkeypatch.setattr(settings, "llm_timeout_seconds", 60.0)
    monkeypatch.setattr(settings, "llm_fallback_primary_timeout_seconds", 30.0)
    _FakeAnthropicSuccess.calls = 0
    _FakeAnthropicSuccess.last_kwargs = None


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


async def test_fallback_설정시_primary_타임아웃에_상한이_걸린다(monkeypatch):
    """헥터 PR #185 리뷰: GPU가 멈춘 경우 primary+fallback이 전체 타임아웃을 두 번
    다 쓰면 최악 두 배가 된다 — primary 시도만 짧게 캡을 씌운다."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    fake = _SucceedingOpenAI()
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: fake)

    result = await llm.complete("sys", "user")

    assert result == "primary-ok"
    assert fake.last_kwargs["timeout"] == 30.0, "전역 60초가 아니라 캡(30초)이 걸려야 한다"


async def test_이미_짧은_timeout은_상한보다_작으면_그대로_둔다(monkeypatch):
    """인사이트처럼 호출자가 이미 12초 같은 짧은 값을 요청했으면 늘리지 않는다."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    fake = _SucceedingOpenAI()
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: fake)

    await llm.complete("sys", "user", timeout=12.0)

    assert fake.last_kwargs["timeout"] == 12.0


async def test_fallback_시도는_타임아웃_상한을_안_받는다(monkeypatch):
    """Claude는 hang 걱정이 없어서 원래 timeout(캡보다 커도) 그대로 쓴다."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(None)))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    await llm.complete("sys", "user", timeout=45.0)

    # fallback은 primary용 캡(30초) 영향을 안 받아야 한다.
    assert _FakeAnthropicSuccess.last_kwargs["timeout"] == 45.0


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


async def test_컨텍스트_초과는_영구_오류로_안_묶고_fallback을_쓴다(monkeypatch):
    """vLLM max-model-len(8192) 초과는 모델명 오설정 같은 다른 400과 다르다 — 같은
    요청이 Claude(컨텍스트 훨씬 큼)로는 그대로 성공할 수 있다. 2026-10-22 챗봇 전면
    장애(히스토리가 쌓인 대화가 8192를 넘겨 폴백도 못 타고 전부 실패) 대응."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_context_length_error()))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    result = await llm.complete("sys", "user")

    assert result == "fallback-ok"
    assert _FakeAnthropicSuccess.calls == 1


async def test_컨텍스트_초과는_breaker를_열지_않는다(monkeypatch):
    """컨텍스트 초과는 GPU 가 아니라 이 요청이 크다는 신호다 — breaker 실패로 기록하면
    쌓인 대화 하나가 연속으로 임계치를 넘겨 breaker가 열리고, 그 쿨다운 동안 무관한
    짧은 요청까지 전부 Claude로 샌다."""
    monkeypatch.setattr(llm, "_breaker", CircuitBreaker(failure_threshold=2, cooldown_seconds=30.0))
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    primary = _RaisingOpenAI(_context_length_error())
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: primary)

    await llm.complete("sys", "user")
    await llm.complete("sys", "user")
    await llm.complete("sys", "user")

    assert primary.calls == 3, "컨텍스트 초과가 연속돼도 breaker가 열려 primary를 건너뛰면 안 된다"


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


async def test_breaker가_열려있으면_primary_모델을_안_만들고_fallback으로_바로_간다(
    monkeypatch, caplog
):
    """GPU가 이미 다운인 걸 알고 있는 경우(breaker open) — 로그로 구분 가능해야 한다."""
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

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert "".join(_answer_chunks(res.text)) == "폴백 답변"
    assert built_with == [("anthropic", "claude-fallback")]
    assert "차단기 열림" in _fallback_lines(caplog)[0]


async def test_첫_토큰_전_실패면_fallback으로_전환해_에러_없이_끝난다(monkeypatch, caplog):
    """GPU가 이번 요청에서 처음 응답을 못한 경우(타임아웃 등 가용성 문제) — breaker가
    아직 안 열려 있던 상태에서도 로그로 전환 사실이 남아야 한다(2026-10-22, 이슈 #224
    리뷰 중 발견 — record_failure()만 부르고 로그가 안 남아 "LLM 폴백" 검색으로도
    이 경로의 전환이 안 보이던 공백)."""
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

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert _error_events(res.text) == []
    assert "".join(_answer_chunks(res.text)) == "폴백 답변"
    assert built_with == [("anthropic", "claude-primary"), ("anthropic", "claude-fallback")]
    line = _fallback_lines(caplog)[0]
    assert "primary 호출 실패" in line
    assert "AI_TIMEOUT" in line


class _ContextLengthOpenAIError(openai.OpenAIError):
    """실제 vLLM이 돌려준 400 본문(2026-10-22)을 그대로 흉내낸다. status_code를
    클래스 속성으로 둬 _provider_status()가 인스턴스에서 바로 읽게 한다."""

    status_code = 400

    def __str__(self):
        return (
            "Error code: 400 - {'error': {'message': \"This model's maximum context "
            "length is 8192 tokens. However, your prompt contains at least 8193 input "
            "tokens...\", 'type': 'BadRequestError', 'param': 'input_tokens', "
            "'code': 400}}"
        )


async def test_챗봇에서도_컨텍스트_초과는_fallback을_쓰고_breaker를_안_연다(monkeypatch, caplog):
    """app/api/chat.py의 _stream()은 llm.complete()와 별도 호출 경로라 똑같이 확인한다."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-primary")
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30.0)
    monkeypatch.setattr(llm, "_breaker", breaker)

    def spy_get_model(tools, provider, model_name):
        if model_name == settings.llm_fallback_model:
            return FakeModel(responses=[AIMessage(content="폴백 답변")])
        return FakeModel(responses=[_ContextLengthOpenAIError()])

    monkeypatch.setattr(chat_graph, "get_model", spy_get_model)

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert _error_events(res.text) == []
    assert "".join(_answer_chunks(res.text)) == "폴백 답변"
    assert breaker.should_skip() is False, "컨텍스트 초과는 breaker를 열면 안 된다"
    assert "primary 호출 실패" in _fallback_lines(caplog)[0]


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


# ── 폴백 로그 (2026-10-22, 이슈 #220) ────────────────────────────────
# 2026-10-19 설계에 "폴백 발생 시 logger.warning" 이 적혀 있었는데 구현이 빠져
# 있었다. 그래서 운영 전환용 env var 를 다 넣고 재배포까지 하고도 GPU 가 실제로
# 쓰이는지 아무도 확인하지 못했다 — 죽어서 Claude 로 넘어가도 조용히 넘어간다.


def _fallback_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "LLM 폴백" in r.getMessage()]


async def test_primary_실패로_넘어가면_사유와_함께_남는다(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(None)))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        await llm.complete("sys", "user")

    line = _fallback_lines(caplog)[0]
    assert "openai:qwen-primary" in line
    assert "anthropic:claude-fallback" in line
    assert "primary 호출 실패" in line


async def test_차단기가_열려_있으면_건너뛴_것으로_남는다(monkeypatch, caplog):
    """primary 를 아예 안 부른 경우다 — "쓰다 넘어간 것" 과 구분돼야 한다."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)
    for _ in range(3):
        llm.record_failure()  # 임계치까지 실패시켜 차단기를 연다

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        await llm.complete("sys", "user")

    assert "차단기 열림" in _fallback_lines(caplog)[0]


async def test_폴백이_꺼져_있으면_로그도_안_남는다(monkeypatch, caplog):
    """기본값 운영(anthropic 단독)에서는 이 로그가 아예 없어야 한다."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-4-5")
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        await llm.complete("sys", "user")

    assert _fallback_lines(caplog) == []


async def test_로그에_프롬프트와_응답이_안_남는다(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    monkeypatch.setattr(llm, "AsyncOpenAI", lambda **kw: _RaisingOpenAI(_provider_error(None)))
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicSuccess)

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        await llm.complete("비밀-시스템-프롬프트", "비밀-사용자-입력")

    line = _fallback_lines(caplog)[0]
    assert "비밀-시스템-프롬프트" not in line
    assert "비밀-사용자-입력" not in line
    assert "fallback-ok" not in line


async def test_챗봇_경로에서도_남는다(monkeypatch, caplog):
    """app/api/chat.py 는 모델을 미리 만들어야 해서 별도 경로를 탄다."""
    monkeypatch.setattr(settings, "llm_fallback_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_fallback_model", "claude-fallback")
    for _ in range(3):
        llm.record_failure()

    with caplog.at_level("WARNING", logger="app.clients.llm"):
        provider, model, used = await llm.resolve_primary_or_fallback()

    assert (provider, model, used) == ("anthropic", "claude-fallback", True)
    assert "차단기 열림" in _fallback_lines(caplog)[0]
