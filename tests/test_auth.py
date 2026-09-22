"""선택적 내부 토큰 검증 — app/core/auth.py.

핵심은 **기본값이 "검증 안 함"이라는 것**이다. 필수로 두면 배포 때 BE 와 AI 의 시크릿이
어긋나는 순간 전부 401 이 되어 연동 테스트 당일을 통째로 막는다.
"""

import httpx

from app.core.config import settings
from app.main import app

BODY = {
    "storeId": 1,
    "uploadId": 1,
    "analysisRunId": 1,
    "forecastStartDate": "2026-04-02",
    "dailySales": [{"date": "2026-04-01", "amount": 947100, "orderCnt": 80}],
}


async def _post(headers: dict | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/forecast/batch", json=BODY, headers=headers or {})


async def test_토큰이_설정되지_않으면_헤더_없이도_통과한다(monkeypatch):
    """2026-09-16 "앱 레벨 인증 없음" 결정의 기본 동작. 보안 그룹이 1차 경계다."""
    monkeypatch.setattr(settings, "internal_ai_token", "")

    res = await _post()

    assert res.status_code != 401


async def test_토큰이_설정되면_헤더가_없을_때_401(monkeypatch):
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    res = await _post()

    assert res.status_code == 401
    assert res.json()["status"] == "FAILED"


async def test_토큰이_틀리면_401(monkeypatch):
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    res = await _post({"Authorization": "Bearer wrong"})

    assert res.status_code == 401


async def test_Bearer_접두사가_없으면_401(monkeypatch):
    """BE 계약이 `Authorization: Bearer {INTERNAL_AI_TOKEN}` 이다."""
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    res = await _post({"Authorization": "s3cret"})

    assert res.status_code == 401


async def test_토큰이_맞으면_통과한다(monkeypatch):
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    res = await _post({"Authorization": "Bearer s3cret"})

    assert res.status_code != 401


async def test_health_는_토큰과_무관하게_열려_있다(monkeypatch):
    """로드밸런서가 부른다. 여기에 인증이 붙으면 헬스체크가 통째로 죽는다."""
    monkeypatch.setattr(settings, "internal_ai_token", "s3cret")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")

    assert res.status_code == 200
