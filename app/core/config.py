from pydantic_settings import BaseSettings, SettingsConfigDict

# Upstage Solar 는 OpenAI 호환 API를 제공한다 (console.upstage.ai/docs/getting-started).
UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"

# reasoning effort를 켤 수 있는(=기본이 reasoning on인) openai 계열 모델.
# GPT-5.6 Luna는 reasoning이 기본값이라 챗봇·단발 생성 모두 지연시간 때문에 꺼야 한다 —
# LLM_MODEL이 이 목록에 없으면(예: 기존 non-reasoning 모델) reasoning_effort 파라미터
# 자체를 보내지 않는다.
OPENAI_REASONING_MODELS = {"gpt-5.6-luna"}

# thinking을 낮출 수 있는(=기본이 thinking on인) google 계열 모델.
# Gemini 3세대부터는 thinking_budget이 폐지되고 thinking_level(low/medium/high)만 쓰는데,
# gemini-3.8-flash는 "minimal"이 아예 에러라 완전히 끌 수는 없고 "low"가 낼 수 있는 최솟값이다
# (ai.google.dev/gemini-api/docs/models/gemini-3.8-flash). OpenAI처럼 reasoning을 off로
# 만들 순 없지만 지연시간 비교 조건을 맞추기 위해 최소치로 고정한다. LLM_MODEL이 이 목록에
# 없으면 thinking 파라미터 자체를 보내지 않는다.
GOOGLE_THINKING_MODELS = {"gemini-3.8-flash"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "anthropic"  # anthropic | openai | google | upstage
    llm_model: str = "claude-sonnet-4-5"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    upstage_api_key: str = ""

    backend_base_url: str = "http://localhost:9000"

    # 비어 있으면 검증하지 않는다 — app/core/auth.py 참고. 보안 그룹이 1차 경계고
    # 이건 그게 빠졌을 때를 위한 2차 방어선이라, 없다고 기동을 막지 않는다.
    internal_ai_token: str = ""

    # SDK 기본값은 읽기 600초에 자체 재시도 2회다. 관측된 정상 응답이 15~20초라
    # 그대로 두면 한 요청이 수십 분을 붙잡는다 — BE 가 먼저 끊어도 이쪽 작업은 계속
    # 돌면서 토큰만 쓴다. 재시도는 서비스 레이어(MAX_RETRY)가 하므로 SDK 쪽은 끈다.
    llm_timeout_seconds: float = 60.0

    # 위키 단계2: 툴 6종은 사전 집계 테이블 조회이므로 개별 50ms가 목표.
    # 네트워크 왕복을 감안해 상한만 강제한다.
    backend_timeout_seconds: float = 2.0


_API_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "google_api_key",
    "upstage": "upstage_api_key",
}


def missing_required(s: "Settings") -> list[str]:
    """배포 후 첫 요청에서야 드러날 설정 누락을 기동 시점에 찾는다.

    둘 다 기본값이 있어서 앱은 정상 기동하고 /health 도 200 을 돌려준다 — 배포는 성공한
    것처럼 보이고 첫 요청에서 터진다. BACKEND_BASE_URL 은 더 고약한데, 에러가 아니라
    기본값(localhost:9000)으로 조용히 돌아가 컨테이너가 자기 자신을 호출한다.
    """
    missing = []
    key_field = _API_KEY_FIELDS.get(s.llm_provider)
    if key_field and not getattr(s, key_field):
        missing.append(key_field.upper())
    if "localhost" in s.backend_base_url or "127.0.0.1" in s.backend_base_url:
        missing.append("BACKEND_BASE_URL(로컬 기본값 그대로다)")
    return missing


settings = Settings()
