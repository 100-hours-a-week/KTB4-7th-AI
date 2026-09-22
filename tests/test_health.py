import httpx

from app.main import app


async def test_health():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_provider_키가_비면_기동_시_찾아낸다():
    """기본값이 있어서 앱은 정상 기동하고 /health 도 200 이다 — 첫 요청에서야 터진다."""
    from app.core.config import Settings, missing_required

    s = Settings(llm_provider="anthropic", anthropic_api_key="", backend_base_url="http://be:8080")
    assert missing_required(s) == ["ANTHROPIC_API_KEY"]


def test_BACKEND_BASE_URL이_로컬_기본값이면_찾아낸다():
    """에러가 아니라 기본값으로 조용히 돌아가 컨테이너가 자기 자신을 호출한다."""
    from app.core.config import Settings, missing_required

    s = Settings(anthropic_api_key="sk-x")
    assert missing_required(s) == ["BACKEND_BASE_URL(로컬 기본값 그대로다)"]


def test_설정이_갖춰지면_비어_있다():
    from app.core.config import Settings, missing_required

    s = Settings(anthropic_api_key="sk-x", backend_base_url="http://be:8080")
    assert missing_required(s) == []
