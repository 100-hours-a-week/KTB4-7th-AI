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
