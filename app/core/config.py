from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internal_api_key: str
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"
    backend_base_url: str = "http://localhost:9000"

    # 위키 단계2: 툴 6종은 사전 집계 테이블 조회이므로 개별 50ms가 목표.
    # 네트워크 왕복을 감안해 상한만 강제한다.
    backend_timeout_seconds: float = 2.0


settings = Settings()
