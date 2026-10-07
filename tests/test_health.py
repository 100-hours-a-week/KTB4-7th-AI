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


def test_LLM_BASE_URL_이_있으면_API_키를_요구하지_않는다():
    """로컬 vLLM 은 인증을 안 건다 — 여기서 막으면 로컬 모델로는 기동이 안 된다(이슈 #113)."""
    from app.core.config import Settings, missing_required

    s = Settings(
        llm_provider="openai",
        openai_api_key="",
        llm_base_url="http://10.0.1.9:8000/v1",
        backend_base_url="http://be:8080",
    )

    assert missing_required(s) == []


def test_다른_provider면_LLM_BASE_URL_이_있어도_API_키를_요구한다():
    """llm_base_url 은 openai 분기 전용이다. provider 를 안 보면 범위를 넘어 샌다 —
    로컬 검증 뒤 .env 에 값을 남겨둔 채 LLM_PROVIDER 만 anthropic 으로 되돌리면
    ANTHROPIC_API_KEY 가 비어도 기동 검사를 통과한다(2026-10-07 제나님 리뷰).
    """
    from app.core.config import Settings, missing_required

    s = Settings(
        llm_provider="anthropic",
        anthropic_api_key="",
        llm_base_url="http://10.0.1.9:8000/v1",
        backend_base_url="http://be:8080",
    )

    assert missing_required(s) == ["ANTHROPIC_API_KEY"]


def test_LLM_BASE_URL_이_없으면_API_키를_여전히_요구한다():
    from app.core.config import Settings, missing_required

    s = Settings(llm_provider="openai", openai_api_key="", backend_base_url="http://be:8080")

    assert missing_required(s) == ["OPENAI_API_KEY"]
