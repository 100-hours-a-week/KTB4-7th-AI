"""LLM_PROVIDER 값에 따라 llm.complete()가 맞는 SDK 클라이언트로 분기하는지 확인한다.

실제 API 키 없이 SDK 클라이언트 클래스만 페이크로 바꿔 동작을 검증한다.
"""

import pytest

from app.clients import llm
from app.core.config import UPSTAGE_BASE_URL, settings
from app.core.errors import ApiError


class _FakeMessages:
    async def create(self, **kwargs):
        return type("R", (), {"content": [type("C", (), {"text": "anthropic-ok"})()]})()


class _FakeAnthropicClient:
    def __init__(self, **kwargs):
        self.messages = _FakeMessages()


class _FakeCompletions:
    def __init__(self):
        self.last_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        message = type("M", (), {"content": "openai-ok"})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


class _FakeOpenAIClient:
    def __init__(self, **kwargs):
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()
        self.base_url = kwargs.get("base_url")


class _FakeGoogleModels:
    async def generate_content(self, **kwargs):
        return type("R", (), {"text": "google-ok"})()


class _FakeGoogleClient:
    def __init__(self, **kwargs):
        self.aio = type("Aio", (), {"models": _FakeGoogleModels()})()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(settings, "llm_provider", "anthropic")


async def test_anthropic_provider는_AsyncAnthropic으로_생성한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm, "AsyncAnthropic", _FakeAnthropicClient)

    assert await llm.complete("sys", "user") == "anthropic-ok"


async def test_openai_provider는_AsyncOpenAI로_생성한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(llm, "AsyncOpenAI", _FakeOpenAIClient)

    assert await llm.complete("sys", "user") == "openai-ok"


async def test_upstage_provider는_AsyncOpenAI에_upstage_base_url을_지정한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "upstage")
    monkeypatch.setattr(llm, "AsyncOpenAI", _FakeOpenAIClient)

    assert await llm.complete("sys", "user") == "openai-ok"
    assert llm._clients["upstage"].base_url == UPSTAGE_BASE_URL


async def test_google_provider는_genai_Client로_생성한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(llm.genai, "Client", _FakeGoogleClient)

    assert await llm.complete("sys", "user") == "google-ok"


async def test_지원하지_않는_provider면_LLM_ERROR를_던진다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "unknown")

    with pytest.raises(ApiError) as exc_info:
        await llm.complete("sys", "user")

    assert exc_info.value.code == "LLM_ERROR"


async def test_openai_reasoning_모델이면_reasoning_effort를_none으로_보낸다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.6-luna")
    monkeypatch.setattr(llm, "AsyncOpenAI", _FakeOpenAIClient)

    await llm.complete("sys", "user")

    assert llm._clients["openai"].chat.completions.last_kwargs["reasoning_effort"] == "none"


async def test_openai_reasoning_모델이_아니면_reasoning_effort를_안_보낸다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")
    monkeypatch.setattr(llm, "AsyncOpenAI", _FakeOpenAIClient)

    await llm.complete("sys", "user")

    assert "reasoning_effort" not in llm._clients["openai"].chat.completions.last_kwargs


def test_model_label은_provider_model을_합친다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "claude-sonnet-4-5")

    assert llm.model_label() == "anthropic:claude-sonnet-4-5"


def test_model_label은_openai_reasoning_모델을_off로_끈_경우_off가_붙는다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.6-luna")

    assert llm.model_label() == "openai:gpt-5.6-luna-off"


async def test_provider_호출이_타임아웃되면_LLM_TIMEOUT을_던진다(monkeypatch):
    import anthropic
    import httpx

    class _TimeoutClient:
        def __init__(self, **kwargs):
            self.messages = self

        async def create(self, **kwargs):
            raise anthropic.APITimeoutError(
                httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )

    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(llm, "AsyncAnthropic", _TimeoutClient)

    with pytest.raises(ApiError) as exc_info:
        await llm.complete("sys", "user")

    assert exc_info.value.code == "LLM_TIMEOUT"
