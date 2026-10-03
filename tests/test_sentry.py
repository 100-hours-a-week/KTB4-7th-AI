import httpx
import pytest
from fastapi import FastAPI

from app.api.chat import _stream
from app.core import sentry as sentry_config
from app.core.config import settings
from app.core.errors import ApiError, register_error_handlers


def test_설정된_DSN과_release로_Sentry를_초기화한다(monkeypatch):
    options = {}
    monkeypatch.setattr(settings, "sentry_dsn", "https://key@example.com/1")
    monkeypatch.setattr(settings, "sentry_environment", "production")
    monkeypatch.setattr(settings, "sentry_release", "ktb4-ai-server@0.1.0+a1b2c3d")
    monkeypatch.setattr(sentry_config.sentry_sdk, "init", lambda **kwargs: options.update(kwargs))

    sentry_config.init_sentry()

    assert options["release"] == "ktb4-ai-server@0.1.0+a1b2c3d"
    assert options["environment"] == "production"
    assert options["max_request_body_size"] == "never"
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False


def test_이벤트에서_요청과_예외_메시지를_제거한다():
    event = {
        "request": {"data": "prompt secret", "headers": {"Authorization": "Bearer secret"}},
        "breadcrumbs": {"values": [{"message": "prompt secret"}]},
        "extra": {"prompt": "secret"},
        "exception": {"values": [{"value": "prompt secret", "type": "ApiError"}]},
        "tags": {"error_code": "PROVIDER_ERROR"},
    }

    scrubbed = sentry_config._strip_sensitive_data(event, {})

    assert "secret" not in str(scrubbed)
    assert scrubbed["exception"]["values"][0]["value"] == "PROVIDER_ERROR"


@pytest.mark.parametrize("status", [422, 500, 502, 504])
async def test_서버_오류만_Sentry에_수집한다(monkeypatch, status):
    captured = []
    monkeypatch.setattr(
        sentry_config.sentry_sdk,
        "capture_exception",
        lambda exc, **kwargs: captured.append((exc, kwargs)),
    )
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/fail")
    async def fail():
        raise ApiError(status, "TEST_ERROR", "테스트 오류")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/fail")

    assert response.status_code == status
    assert len(captured) == int(status >= 500)
    if captured:
        assert captured[0][1]["tags"] == {"error_code": "TEST_ERROR"}


async def test_처리되지_않은_500도_Sentry에_수집한다(monkeypatch):
    captured = []
    monkeypatch.setattr(
        sentry_config.sentry_sdk,
        "capture_exception",
        lambda exc, **kwargs: captured.append((exc, kwargs)),
    )
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/fail")
    async def fail():
        raise RuntimeError("internal failure")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/fail")

    assert response.status_code == 500
    assert len(captured) == 1
    assert captured[0][1]["tags"] == {"error_code": "INTERNAL_ERROR"}


async def test_챗봇_스트림_오류도_Sentry에_수집한다(monkeypatch):
    captured = []
    monkeypatch.setattr(
        sentry_config.sentry_sdk,
        "capture_exception",
        lambda exc, **kwargs: captured.append((exc, kwargs)),
    )

    class FailingGraph:
        async def astream_events(self, state, version):
            yield {"event": "on_chain_start", "name": "agent"}
            raise ApiError(504, "AI_TIMEOUT", "모델 타임아웃")

    chunks = [chunk async for chunk in _stream(FailingGraph(), {})]

    assert "AI_TIMEOUT" in chunks[0]
    assert chunks[-1] == "data: [DONE]\n\n"
    assert len(captured) == 1
    assert captured[0][1]["tags"] == {"error_code": "AI_TIMEOUT"}
