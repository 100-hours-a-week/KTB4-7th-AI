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

    # 위키 단계2: 툴 6종은 사전 집계 테이블 조회이므로 개별 50ms가 목표.
    # 네트워크 왕복을 감안해 상한만 강제한다.
    backend_timeout_seconds: float = 2.0


settings = Settings()
