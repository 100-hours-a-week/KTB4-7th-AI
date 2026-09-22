"""오류 응답 바디 — BE 확정 형식(2026-09-22).

`{"status":"FAILED","error":{"code":...,"retryable":...}}` 를 내보낸다. `message` 와
`data` 는 노션 계약이라 그대로 두고 더하기만 했다.

retryable 은 HTTP 상태 코드에서 파생한다. 손으로 관리하는 표로 두면 BE 재시도 정책과
어긋나는 순간을 아무도 못 잡는다.
"""

import httpx
import pytest

from app.core.config import settings
from app.core.errors import _RETRYABLE_STATUSES, _body
from app.main import app

FORECAST_BODY = {
    "storeId": 1,
    "uploadId": 1,
    "forecastStartDate": "2026-04-02",
    "dailySales": [{"date": "2026-04-01", "amount": 947100, "orderCnt": 80}],
}


async def _post(path: str, body: dict, headers: dict | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body, headers=headers or {})


@pytest.mark.parametrize("status", [502, 503, 504])
def test_BE_재시도_대상_상태는_retryable_true(status):
    """BE 정책(2026-09-22): 502·503·504 와 연결 실패만 재시도한다."""
    assert _body("msg", "CODE", status)["error"]["retryable"] is True


@pytest.mark.parametrize("status", [400, 401, 422, 500])
def test_나머지_상태는_retryable_false(status):
    """500 은 AI 가 이미 1회 재시도한 뒤라 BE 가 또 부르면 호출만 2배가 된다."""
    assert _body("msg", "CODE", status)["error"]["retryable"] is False


def test_retryable_은_상태코드에서_파생된다():
    """손으로 관리하는 표를 두면 상태 코드와 조용히 어긋난다."""
    assert _RETRYABLE_STATUSES == frozenset({502, 503, 504})


def test_노션_계약_필드가_그대로_남아_있다():
    """message·data 는 노션 계약이다. error 는 더한 것이지 바꾼 게 아니다."""
    body = _body("실패했습니다.", "SOME_CODE", 500)
    assert body["message"] == "실패했습니다."
    assert body["data"] is None
    assert body["status"] == "FAILED"


def test_failReason_은_있을_때만_붙는다():
    assert "failReason" not in _body("msg", "CODE", 500)
    assert _body("msg", "CODE", 422, "INVALID_X")["failReason"] == "INVALID_X"


async def test_422_는_VALIDATION_ERROR_이고_재시도하지_않는다():
    res = await _post("/internal/v1/ai/sales-insights", {"storeId": 1})

    assert res.status_code == 422
    body = res.json()
    assert body["status"] == "FAILED"
    assert body["error"] == {"code": "VALIDATION_ERROR", "retryable": False}


async def test_401_은_UNAUTHORIZED_이고_재시도하지_않는다(monkeypatch):
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    res = await _post("/internal/v1/ai/forecast/batch", FORECAST_BODY)

    assert res.status_code == 401
    assert res.json()["error"] == {"code": "UNAUTHORIZED", "retryable": False}


async def test_생성_실패는_500이고_재시도하지_않는다(monkeypatch):
    """AI 가 내부에서 이미 1회 재시도했다. BE 가 또 부르면 LLM 호출이 4번이 된다."""
    from app.clients import llm

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return "JSON 아님"

    monkeypatch.setattr(llm, "complete", fake_complete)

    from tests.test_insights import REQUEST_BODY

    res = await _post("/internal/v1/ai/sales-insights", REQUEST_BODY)

    assert res.status_code == 500
    assert res.json()["error"] == {
        "code": "INSIGHT_GENERATION_FAILED",
        "retryable": False,
    }


async def test_공급자_오류는_502이고_재시도한다(monkeypatch):
    """BE 가 502 를 재시도 대상으로 바꿨다(2026-09-22) — 429/529 가 여기 묶여 있다."""
    from app.clients import llm
    from app.core.errors import ApiError

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        raise ApiError(502, "PROVIDER_ERROR", "모델 공급자 호출에 실패했습니다.")

    monkeypatch.setattr(llm, "complete", fake_complete)

    from tests.test_insights import REQUEST_BODY

    res = await _post("/internal/v1/ai/sales-insights", REQUEST_BODY)

    assert res.status_code == 502
    assert res.json()["error"] == {"code": "PROVIDER_ERROR", "retryable": True}


async def test_타임아웃은_504이고_재시도한다(monkeypatch):
    from app.clients import llm
    from app.core.errors import ApiError

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        raise ApiError(504, "PROVIDER_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다.")

    monkeypatch.setattr(llm, "complete", fake_complete)

    from tests.test_insights import REQUEST_BODY

    res = await _post("/internal/v1/ai/sales-insights", REQUEST_BODY)

    assert res.status_code == 504
    assert res.json()["error"] == {"code": "PROVIDER_TIMEOUT", "retryable": True}


async def test_성공_응답에는_error_가_없다(monkeypatch):
    """BE 가 error 유무로 분기해도 되도록, 성공에는 아예 넣지 않는다."""
    from app.clients import llm
    from tests.test_insights import LLM_SUCCESS, REQUEST_BODY

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post("/internal/v1/ai/sales-insights", REQUEST_BODY)

    assert res.status_code == 200
    assert "error" not in res.json()
