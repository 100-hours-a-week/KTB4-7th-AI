import httpx
import pytest
from fastapi import FastAPI, Response

from app.clients import backend
from app.core.errors import ApiError
from devtools.stub_backend import app as stub_app


def _use(monkeypatch, asgi_app):
    """call_tool 이 만드는 httpx 클라이언트를 ASGI 앱에 물린다. 실서버를 띄우지 않는다."""
    original = httpx.AsyncClient

    def factory(**kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=asgi_app)
        return original(**kwargs)

    monkeypatch.setattr(backend.httpx, "AsyncClient", factory)


async def test_모든_툴이_스텁에서_응답한다(monkeypatch):
    _use(monkeypatch, stub_app)
    for tool in backend.TOOL_PATHS:
        data = await backend.call_tool(tool, {"storeId": 1, "period": "THIS_MONTH"})
        assert data, f"{tool} 이 빈 응답을 반환했다"


async def test_data_래퍼를_벗겨서_반환한다(monkeypatch):
    _use(monkeypatch, stub_app)
    data = await backend.call_tool("get_sales_summary", {"storeId": 1, "period": "TODAY"})
    assert data["netSales"] == 3200000
    assert "message" not in data


async def test_등록되지_않은_툴은_500(monkeypatch):
    _use(monkeypatch, stub_app)
    with pytest.raises(ApiError) as exc:
        await backend.call_tool("get_unknown", {})
    assert exc.value.status == 500


async def test_404는_빈_결과로_처리한다(monkeypatch):
    """조회할 데이터가 없는 경우. 재시도하지 않고 빈 dict 를 준다."""
    _use(monkeypatch, FastAPI())  # 라우트가 없으니 전부 404
    assert await backend.call_tool("get_forecast", {"storeId": 1}) == {}


async def test_5xx는_재시도_후_실패한다(monkeypatch):
    calls = []
    broken = FastAPI()

    @broken.get(backend.TOOL_PATHS["get_sales_summary"])
    async def _boom() -> Response:
        calls.append(1)
        return Response(status_code=500)

    _use(monkeypatch, broken)
    with pytest.raises(backend.BackendError):
        await backend.call_tool("get_sales_summary", {"storeId": 1})
    assert len(calls) == 2, "재시도 포함 2회 호출되어야 한다"
