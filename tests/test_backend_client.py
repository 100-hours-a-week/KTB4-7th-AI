import httpx
import pytest
from fastapi import FastAPI, Request, Response

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
    assert data["totalSales"] == 3200000
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


async def test_None_값_파라미터는_쿼리에서_빠진다(monkeypatch):
    """챗봇 툴이 선택 파라미터를 안 채우면 None 으로 넘어온다.
    httpx 는 None 을 빈 문자열로 직렬화하므로 call_tool 이 미리 걸러야 한다."""
    captured = {}
    echo_app = FastAPI()

    @echo_app.get(backend.TOOL_PATHS["get_forecast"])
    async def _echo(request: Request) -> dict:
        captured.update(request.query_params)
        return {"message": "조회에 성공했습니다.", "data": {}}

    _use(monkeypatch, echo_app)
    await backend.call_tool("get_forecast", {"storeId": 1, "targetDate": None})

    assert captured == {"storeId": "1"}


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


async def test_토큰이_있으면_Authorization_헤더를_붙인다(monkeypatch):
    """BE 는 날씨·상권 두 경로에서 Bearer 토큰이 없으면 401 이다(2026-10-19, BE PR #507)."""
    monkeypatch.setattr(backend.settings, "internal_ai_token", "s3cret")
    captured = {}
    echo_app = FastAPI()

    @echo_app.get(backend.TOOL_PATHS["get_weather"])
    async def _echo(request: Request) -> dict:
        captured["authorization"] = request.headers.get("authorization")
        return {"status": "READY", "data": {"skyText": "맑음"}}

    _use(monkeypatch, echo_app)
    await backend.call_tool("get_weather", {"storeId": 1})

    assert captured["authorization"] == "Bearer s3cret"


async def test_토큰이_비어_있으면_헤더를_보내지_않는다(monkeypatch):
    """스텁 BE·로컬 개발은 토큰을 검사하지 않는다. 빈 Bearer 를 보내면 그쪽이 깨진다."""
    monkeypatch.setattr(backend.settings, "internal_ai_token", "")
    captured = {}
    echo_app = FastAPI()

    @echo_app.get(backend.TOOL_PATHS["get_weather"])
    async def _echo(request: Request) -> dict:
        captured["authorization"] = request.headers.get("authorization")
        return {"status": "READY", "data": {"skyText": "맑음"}}

    _use(monkeypatch, echo_app)
    await backend.call_tool("get_weather", {"storeId": 1})

    assert captured["authorization"] is None


async def test_모든_경로에_헤더를_붙인다(monkeypatch):
    """BE 는 지금 두 경로만 검사하지만 경로별로 나누지 않는다 — 나머지에 걸릴 때 또 깨진다."""
    monkeypatch.setattr(backend.settings, "internal_ai_token", "s3cret")
    seen = {}
    echo_app = FastAPI()

    for tool, path in backend.TOOL_PATHS.items():

        @echo_app.get(path)
        async def _echo(request: Request, tool: str = tool) -> dict:
            seen[tool] = request.headers.get("authorization")
            return {"status": "READY", "data": {"ok": 1}}

    _use(monkeypatch, echo_app)
    for tool in backend.TOOL_PATHS:
        await backend.call_tool(tool, {"storeId": 1, "period": "THIS_MONTH"})

    assert seen == {tool: "Bearer s3cret" for tool in backend.TOOL_PATHS}


async def test_EMPTY_응답은_빈_결과로_처리한다(monkeypatch):
    """BE 는 정상적인 데이터 부재를 200 {"status":"EMPTY","data":null} 로 보낸다.

    data 키가 있고 값만 null 이라 .get("data", {}) 의 기본값이 쓰이지 않는다 — None 이
    그대로 나가면 chat/graph.py 의 result.get(...) 에서 AttributeError 로 터진다.
    상권은 서울 외 매장·카페 3곳 미만이 전부 EMPTY 라 예외 경로가 아니다.
    """
    empty_app = FastAPI()

    @empty_app.get(backend.TOOL_PATHS["get_district_benchmark"])
    async def _empty() -> dict:
        return {"status": "EMPTY", "data": None}

    _use(monkeypatch, empty_app)
    assert await backend.call_tool("get_district_benchmark", {"storeId": 1}) == {}


async def test_READY_응답은_data_를_반환한다(monkeypatch):
    ready_app = FastAPI()

    @ready_app.get(backend.TOOL_PATHS["get_district_benchmark"])
    async def _ready() -> dict:
        return {"status": "READY", "data": {"basisQuarter": "2026Q2", "cafeStoreCount": 7}}

    _use(monkeypatch, ready_app)
    data = await backend.call_tool("get_district_benchmark", {"storeId": 1})

    assert data == {"basisQuarter": "2026Q2", "cafeStoreCount": 7}
