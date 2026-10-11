import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from app.core.config import settings

# LLM 공급자 SDK가 직접 돌려준 예외는 공급자 서버가 생성한 설명문이라(우리 프롬프트를
# echo하는 구조가 아니다) 원문을 남긴다 — 그래야 "왜 400/401/429가 났는지"를 사후에 알 수
# 있다. 우리 코드가 만든 예외(ApiError 등)는 어차피 고정된 일반 문구라 바꿀 이유가 없어
# 기존대로 error_code로 덮어쓴다.
_PROVIDER_MODULES = ("anthropic", "openai", "google")


def _strip_sensitive_data(event: dict, hint: dict) -> dict:
    for key in ("request", "breadcrumbs", "extra", "message", "logentry"):
        event.pop(key, None)
    error_code = event.get("tags", {}).get("error_code", "[redacted]")
    for exception in event.get("exception", {}).get("values", []):
        if not exception.get("module", "").startswith(_PROVIDER_MODULES):
            exception["value"] = error_code
    return event


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release or None,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        include_source_context=False,
        integrations=[LoggingIntegration(level=None, event_level=None, sentry_logs_level=None)],
        auto_enabling_integrations=False,
        before_send=_strip_sensitive_data,
    )
