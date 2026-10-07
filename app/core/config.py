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

    # OpenAI 호환 서버를 가리킬 때만 채운다(vLLM 등). 비어 있으면 OpenAI 공식 엔드포인트다.
    # 로컬 LLM 검증용이다 — RunPod 등에 띄운 vLLM 의 /v1 주소를 넣는다(이슈 #113).
    llm_base_url: str | None = None

    # vLLM 이 Qwen3 계열을 서빙하면 thinking 이 기본으로 켜져 있다. <think> 블록이 본문 앞에
    # 붙어 JSON 파싱이 전부 깨지는데, OpenAI 호환 API 로는 chat_template_kwargs 로만 끌 수
    # 있다. 모델명으로 자동 판별하지 않는 이유는 로컬 모델명이 임의 문자열이기 때문이다
    # (Qwen/Qwen3-14B-AWQ, my-finetune-v3 …) — OPENAI_REASONING_MODELS 처럼 목록으로
    # 둘 수가 없다.
    llm_disable_thinking: bool = False

    backend_base_url: str = "http://localhost:9000"

    sentry_dsn: str = ""
    sentry_environment: str = "local"
    sentry_release: str = ""

    # 비어 있으면 검증하지 않는다 — app/core/auth.py 참고. 보안 그룹이 1차 경계고
    # 이건 그게 빠졌을 때를 위한 2차 방어선이라, 없다고 기동을 막지 않는다.
    internal_ai_token: str = ""

    # SDK 기본값은 읽기 600초에 자체 재시도 2회다. 관측된 정상 응답이 15~20초라
    # 그대로 두면 한 요청이 수십 분을 붙잡는다 — BE 가 먼저 끊어도 이쪽 작업은 계속
    # 돌면서 토큰만 쓴다. 재시도는 서비스 레이어(MAX_RETRY)가 하므로 SDK 쪽은 끈다.
    llm_timeout_seconds: float = 60.0

    # 인사이트만 따로 둔다. BE 응답 제한이 30초인데 서비스 재시도 1회가 붙어서,
    # 전역 60초를 그대로 쓰면 최악 120초다 — BE 가 끊은 뒤에도 토큰만 태운다.
    # 실측 3.2~4.0초(2026-09-22, sonnet-4-5)라 12초면 3배 여유고 최악 24초다.
    # 솔루션은 15~20초를 쓰므로 전역값을 함께 낮출 수 없어 분리했다.
    insight_llm_timeout_seconds: float = 12.0

    # 위키 단계2: 툴 6종은 사전 집계 테이블 조회이므로 개별 50ms가 목표.
    # 네트워크 왕복을 감안해 상한만 강제한다.
    backend_timeout_seconds: float = 2.0


_API_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "google_api_key",
    "upstage": "upstage_api_key",
}


def uses_local_llm_server(s: "Settings") -> bool:
    """LLM_BASE_URL 로 OpenAI 호환 서버(vLLM 등)를 가리키고 있는가.

    provider 까지 같이 본다. llm_base_url 은 openai 분기 전용 설정인데 provider 를 안 보면
    범위를 넘어 샌다 — 로컬 검증 뒤 .env 에 LLM_BASE_URL 을 남겨둔 채 LLM_PROVIDER 만
    anthropic 으로 되돌리면(운영 복귀 때 흔한 실수) ANTHROPIC_API_KEY 가 비어도 기동
    검사를 통과한다(2026-10-07 제나님 리뷰).
    """
    return s.llm_provider == "openai" and bool(s.llm_base_url)


def missing_required(s: "Settings") -> list[str]:
    """배포 후 첫 요청에서야 드러날 설정 누락을 기동 시점에 찾는다.

    둘 다 기본값이 있어서 앱은 정상 기동하고 /health 도 200 을 돌려준다 — 배포는 성공한
    것처럼 보이고 첫 요청에서 터진다. BACKEND_BASE_URL 은 더 고약한데, 에러가 아니라
    기본값(localhost:9000)으로 조용히 돌아가 컨테이너가 자기 자신을 호출한다.
    """
    missing = []
    key_field = _API_KEY_FIELDS.get(s.llm_provider)
    # 로컬 서버를 가리키면 API 키가 없는 게 정상이다 — vLLM 은 기본적으로 인증을 걸지
    # 않는다. 여기서 막으면 로컬 모델로는 기동 자체가 안 된다.
    if key_field and not getattr(s, key_field) and not uses_local_llm_server(s):
        missing.append(key_field.upper())
    if "localhost" in s.backend_base_url or "127.0.0.1" in s.backend_base_url:
        missing.append("BACKEND_BASE_URL(로컬 기본값 그대로다)")
    return missing


settings = Settings()


def thinking_off_body() -> dict:
    """vLLM 에 Qwen3 계열을 띄웠을 때 thinking 을 끄는 extra_body. 꺼져 있으면 빈 dict.

    챗봇(app/services/chat/graph.py)도 같은 값을 써야 해서 여기 둔다 — 한쪽만 끄면
    단발 생성은 멀쩡한데 챗봇 답변 앞에만 <think> 가 붙는다.
    """
    # LLM_BASE_URL 없이 플래그만 남아 있으면 실제 OpenAI API 에 extra_body 가 그대로
    # 나간다. 로컬 서버를 가리킬 때만 보낸다(2026-10-07 제나님 리뷰).
    if not (settings.llm_disable_thinking and uses_local_llm_server(settings)):
        return {}
    return {"chat_template_kwargs": {"enable_thinking": False}}
