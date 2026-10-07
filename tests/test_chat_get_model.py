"""LLM_PROVIDER 값에 따라 get_model()이 맞는 LangChain 챗 모델을 반환하는지 확인한다."""

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.chat import graph as chat_graph


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")


def test_anthropic_provider는_ChatAnthropic을_반환한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")

    model = chat_graph.get_model([])

    assert isinstance(model.bound, ChatAnthropic)


def test_openai_provider는_ChatOpenAI를_반환한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    model = chat_graph.get_model([])

    assert isinstance(model.bound, ChatOpenAI)


def test_upstage_provider는_ChatOpenAI를_upstage_base_url로_반환한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "upstage")
    monkeypatch.setattr(settings, "upstage_api_key", "test-key")

    model = chat_graph.get_model([])

    assert isinstance(model.bound, ChatOpenAI)


def test_google_provider는_ChatGoogleGenerativeAI를_반환한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "google_api_key", "test-key")

    model = chat_graph.get_model([])

    assert isinstance(model.bound, ChatGoogleGenerativeAI)


def test_지원하지_않는_provider면_ValueError(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "unknown")

    with pytest.raises(ValueError):
        chat_graph.get_model([])


def test_openai_reasoning_모델이면_reasoning_effort를_none으로_고정한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.6-luna")

    model = chat_graph.get_model([])

    assert model.bound.reasoning_effort == "none"


def test_openai_reasoning_모델이_아니면_reasoning_effort를_보내지_않는다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "gpt-4o-mini")

    model = chat_graph.get_model([])

    assert model.bound.reasoning_effort is None


def test_google_thinking_모델이면_thinking_level을_low로_고정한다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "gemini-3.8-flash")

    model = chat_graph.get_model([])

    assert model.bound.thinking_level == "low"


def test_google_thinking_모델이_아니면_thinking_level을_보내지_않는다(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-pro")

    model = chat_graph.get_model([])

    assert model.bound.thinking_level is None


def test_LLM_BASE_URL_이_있으면_챗봇도_그_주소를_쓴다(monkeypatch):
    """단발 생성만 로컬 서버로 돌리면 챗봇은 조용히 OpenAI 로 나간다 — 이슈 #113."""
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "http://10.0.1.9:8000/v1")

    model = chat_graph.get_model([])

    assert str(model.bound.openai_api_base) == "http://10.0.1.9:8000/v1"
    assert model.bound.openai_api_key.get_secret_value() == "EMPTY"


def test_챗봇도_thinking을_같은_설정으로_끈다(monkeypatch):
    """한쪽만 끄면 단발 생성은 멀쩡한데 챗봇 답변 앞에만 <think> 가 붙는다."""
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", "http://10.0.1.9:8000/v1")
    monkeypatch.setattr(settings, "llm_disable_thinking", True)

    model = chat_graph.get_model([])

    assert model.bound.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}
