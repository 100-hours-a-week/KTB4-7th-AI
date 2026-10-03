import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from app.core.config import settings


def _strip_sensitive_data(event: dict, hint: dict) -> dict:
    for key in ("request", "breadcrumbs", "extra", "message", "logentry"):
        event.pop(key, None)
    error_code = event.get("tags", {}).get("error_code", "[redacted]")
    for exception in event.get("exception", {}).get("values", []):
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
