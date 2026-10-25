import logging
import re

import anthropic
import httpx
import openai
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

from app.clients.circuit_breaker import CircuitBreaker
from app.core.config import (
    GOOGLE_THINKING_MODELS,
    OPENAI_REASONING_MODELS,
    UPSTAGE_BASE_URL,
    settings,
    thinking_off_body,
    uses_local_llm_server,
)
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

_clients: dict[str, object] = {}

# GPU(로컬 vLLM) 서빙 예산이 한정돼 상시 가동하지 않는다(2026-10-19) — primary 호출이
# 가용성 문제로 계속 실패하면 이 breaker 가 열려서, 쿨다운 동안은 매 요청마다 타임아웃을
# 반복해서 기다리지 않고 바로 LLM_FALLBACK_PROVIDER 로 보낸다. LLM_FALLBACK_PROVIDER 가
# 비어 있으면(기본값) should_use_fallback() 이 breaker 를 건드리지도 않아 기존 동작과
# 100% 동일하다.
_breaker = CircuitBreaker(
    failure_threshold=settings.llm_fallback_failure_threshold,
    cooldown_seconds=settings.llm_fallback_cooldown_seconds,
)


def _get_anthropic() -> AsyncAnthropic:
    if "anthropic" not in _clients:
        _clients["anthropic"] = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    return _clients["anthropic"]


def _get_openai() -> AsyncOpenAI:
    if "openai" not in _clients:
        # LLM_BASE_URL 이 있으면 OpenAI 호환 서버(vLLM 등)를 가리킨다. 그쪽은 보통 인증을
        # 안 걸지만 SDK 가 키 자리를 요구해서 자리값을 넣는다 — vLLM 문서의 관례다.
        base_url = settings.llm_base_url
        _clients["openai"] = AsyncOpenAI(
            api_key=settings.openai_api_key or ("EMPTY" if base_url else ""),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
            **({"base_url": base_url} if base_url else {}),
        )
    return _clients["openai"]


def _get_upstage() -> AsyncOpenAI:
    if "upstage" not in _clients:
        _clients["upstage"] = AsyncOpenAI(
            api_key=settings.upstage_api_key,
            base_url=UPSTAGE_BASE_URL,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    return _clients["upstage"]


def _get_google() -> genai.Client:
    if "google" not in _clients:
        _clients["google"] = genai.Client(api_key=settings.google_api_key)
    return _clients["google"]


async def _complete_openai_compatible(
    client: AsyncOpenAI, model: str, system: str, user: str, **extra
) -> str:
    res = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        **extra,
    )
    return res.choices[0].message.content


def model_label() -> str:
    """응답의 modelVersion에 쓰는 "{provider}:{model}" 식별자.

    reasoning 모델(OPENAI_REASONING_MODELS)을 reasoning_effort="none"으로 꺼서 호출했으면
    "-off"를 붙여, 같은 모델이어도 reasoning on/off 결과를 구분할 수 있게 한다.
    """
    label = f"{settings.llm_provider}:{settings.llm_model}"
    if settings.llm_provider == "openai" and settings.llm_model in OPENAI_REASONING_MODELS:
        label += "-off"
    return label


_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_fence(raw: str) -> str:
    """모델이 JSON 을 ```json 펜스로 감싸 내려주는 경우가 있어 벗긴다.

    "설명 없이 JSON만 출력하세요" 를 프롬프트에 써도 지켜지지 않는다 — 실제 호출로 확인했다
    (2026-09-21, devtools/llm_smoke.py). 펜스가 없으면 원문을 그대로 돌려준다.
    """
    match = _FENCE.match(raw.strip())
    return match.group(1) if match else raw


# 공급자가 영구적으로 거절하는 상태. 재호출로 바뀌지 않는다 — 요청·키·권한·모델명·크레딧
# 문제다. 429(쿼터)와 5xx·연결 실패는 빠져 있다 — 그쪽은 시간이 지나면 풀린다.
#
# provider SDK 세 종이 예외 타입이 다 달라서 타입으로 분기하지 않고 상태 코드만 본다.
# anthropic·openai 는 APIStatusError.status_code, google-genai 는 APIError.code 다.
# 상태 코드를 못 꺼내면(연결 실패 등) 일시 오류로 본다 — 영구로 단정하면 복구 가능한
# 장애에서 BE 재시도를 막는다.
_PERMANENT_PROVIDER_STATUSES = frozenset({400, 401, 403, 404, 413, 422})


def _provider_status(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


# vLLM이 --max-model-len(infra/vllm/serve.sh, 8192)을 넘는 프롬프트에 돌려주는 400의
# 본문 문구. 2026-10-22 챗봇 전면 장애 — 히스토리가 쌓인 대화가 로컬 vLLM 컨텍스트를
# 넘겨 400이 났는데, 400이 영구 오류로 묶여 있어 Claude(컨텍스트 훨씬 큼)로도 못 넘어가고
# 그대로 실패했다. 모델명 오설정 등 "다시 불러도 안 되는" 다른 400과 성격이 달라 분리한다.
_CONTEXT_LENGTH_ERROR = re.compile(r"maximum context length", re.IGNORECASE)


def _is_context_length_error(cause: Exception) -> bool:
    return _provider_status(cause) == 400 and bool(_CONTEXT_LENGTH_ERROR.search(str(cause)))


def is_capacity_error(exc: ApiError) -> bool:
    """breaker가 "GPU 가용성" 신호로 취급하면 안 되는 폴백 사유인가.

    컨텍스트 초과는 이 요청이 크다는 뜻이지 GPU가 죽었다는 신호가 아니다. 이걸로
    breaker 실패를 기록하면, 쌓인 대화 하나가 연속으로 임계치를 넘겨 breaker가 열리고
    그 쿨다운 동안 무관한 짧은 요청까지 전부 Claude로 샌다(2026-10-22).
    """
    return _is_context_length_error(exc.__cause__)


def is_fallback_eligible(exc: ApiError) -> bool:
    """가용성 문제(연결실패·타임아웃·5xx)거나 컨텍스트 초과면 True — 그때만 fallback
    provider로 넘긴다.

    exc.__cause__ 로 원본 SDK 예외를 본다(전부 `raise ... from exc`로 체인돼 있다).
    원인이 없으면(예: 지원 안 하는 LLM_PROVIDER 설정 오류) 가용성 문제가 아니므로 False.
    모델 출력이 스키마를 어기는 건 이 레이어에 안 온다 — complete()가 텍스트를 이미
    정상적으로 반환한 뒤 서비스 레이어(MAX_RETRY)가 보는 영역이라 서로 안 겹친다.

    primary 호출 실패 판정 전용이다 — 예외가 어느 provider 것인지 안 받고 전역
    primary 설정(settings)을 보므로, fallback 쪽 예외에 부르면 잘못 분류한다.
    """
    cause = exc.__cause__
    if cause is None:
        return False
    if isinstance(cause, (anthropic.APITimeoutError, openai.APITimeoutError, TimeoutError)):
        return True
    if _is_context_length_error(cause):
        return True
    # RunPod 프록시는 Pod가 꺼져 있으면 연결거부가 아니라 404를 준다(2026-10-25, 이슈 #232).
    if _provider_status(cause) == 404 and uses_local_llm_server(settings):
        return True
    return _provider_status(cause) not in _PERMANENT_PROVIDER_STATUSES


async def _vllm_healthy() -> bool:
    """vLLM의 /health를 짧은 타임아웃으로 찔러본다. half-open 복구 확인용 — 자주 안 부른다.

    LLM_BASE_URL은 "{host}/v1" 모양이고 vLLM은 /health를 루트에 둔다. OPENAI_API_KEY가
    설정돼 있으면 같이 보낸다 — vLLM에 --api-key를 걸면 /health도 인증을 요구할 수
    있는데, 토큰 없이 찔러서 매번 401이 나면 breaker가 GPU가 멀쩡해도 영원히 안 닫힌다.
    """
    base = (settings.llm_base_url or "").removesuffix("/v1")
    token = settings.openai_api_key
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{base}/health", headers=headers)
        return res.status_code == 200
    except Exception:
        return False


def log_fallback(reason: str) -> None:
    """폴백이 실제로 발동했음을 남긴다. app/api/chat.py도 직접 부른다(모듈 경계 넘는
    공개 API라 밑줄 없이 둔다) — 챗봇 스트리밍 도중 전환은 llm.py 내부를 안 거친다.

    2026-10-19 설계에 "폴백 발생 시 logger.warning" 이 적혀 있었는데 구현이 빠져
    있었다(2026-10-20 제나 발견, 이슈 #220). 그래서 운영 전환용 env var 를 다 넣고
    재배포까지 했는데도 **GPU 가 실제로 쓰이는지 아무도 확인하지 못했다** — GPU 가
    죽어 Claude 로 넘어가도 조용히 넘어가고, 비용이 그쪽으로 새도 모른다.

    챗봇 스트리밍 중 "첫 토큰 전 전환"(app/api/chat.py의 _stream())도 같은 공백이
    있었다 — record_failure()만 부르고 이 로그는 안 남겨서, 그 경로로 조용히 Claude로
    넘어간 건 "LLM 폴백" 검색으로도 안 보였다(2026-10-22 발견, 이슈 #224 리뷰 중).

    WARNING 이다. 정상 동작이 아니라 "GPU 가 안 쓰이고 있다" 는 신호다.
    **프롬프트·응답 본문은 남기지 않는다** — provider·모델·사유뿐이다.
    """
    logger.warning(
        "LLM 폴백 primary=%s:%s → fallback=%s:%s 사유=%s",
        settings.llm_provider,
        settings.llm_model,
        settings.llm_fallback_provider,
        settings.llm_fallback_model,
        reason,
    )


async def should_use_fallback() -> bool:
    """지금 이 호출을 primary 대신 LLM_FALLBACK_PROVIDER로 보내야 하면 True.

    fallback이 설정 안 됐으면(기본값) breaker를 건드리지도 않는다 — 기존 동작과
    완전히 동일한 경로를 탄다. breaker가 막 half-open으로 넘어온 순간(쿨다운 방금
    끝남)이고 primary가 로컬 vLLM이면, 실제 생성 요청 대신 가벼운 /health로 먼저
    찔러본다 — 아직 죽어 있는 GPU에 비싼 타임아웃을 또 치르게 하지 않으려는 것.
    """
    if not settings.llm_fallback_provider:
        return False
    # provider가 같아도(예: anthropic의 가벼운 모델→무거운 모델) 모델까지 같으면
    # 폴백이 의미가 없다 — 그때만 막는다.
    if (settings.llm_fallback_provider, settings.llm_fallback_model) == (
        settings.llm_provider,
        settings.llm_model,
    ):
        return False
    if _breaker.should_skip():
        return True
    if _breaker.probing and uses_local_llm_server(settings) and not await _vllm_healthy():
        _breaker.record_failure()
        return True
    return False


def record_success() -> None:
    _breaker.record_success()


def record_failure() -> None:
    _breaker.record_failure()


async def resolve_primary_or_fallback() -> tuple[str, str, bool]:
    """지금 쓸 (provider, model, used_fallback)을 고른다.

    챗봇처럼 모델 객체를 요청 시작 전에 미리 만들어야 하는 호출자가 쓴다(app/api/chat.py).
    complete()는 같은 결정을 내부에서 직접 한다 — 단발 호출이라 모델을 미리 안 만든다.
    """
    if await should_use_fallback():
        log_fallback("차단기 열림 — primary 를 건너뛴다")
        return settings.llm_fallback_provider, settings.llm_fallback_model, True
    return settings.llm_provider, settings.llm_model, False


async def _complete_once(
    provider: str, model: str, system: str, user: str, max_tokens: int, timeout: float | None
) -> str:
    try:
        if provider == "anthropic":
            res = await _get_anthropic().messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                **({"timeout": timeout} if timeout else {}),
            )
            return res.content[0].text
        if provider == "openai":
            is_reasoning = model in OPENAI_REASONING_MODELS
            # reasoning 모델(o-series/GPT-5.x)은 max_tokens를 거부하고 max_completion_tokens를
            # 요구한다 (openai SDK의 max_tokens 필드 docstring: "deprecated ... not compatible
            # with o-series models"). GPT-5.6 Luna처럼 reasoning이 기본인 모델만
            # reasoning_effort="none"으로 끈다.
            extra = {"max_completion_tokens" if is_reasoning else "max_tokens": max_tokens}
            if is_reasoning:
                extra["reasoning_effort"] = "none"
            if timeout:
                extra["timeout"] = timeout
            if settings.llm_temperature is not None:
                extra["temperature"] = settings.llm_temperature
            body = thinking_off_body()
            if body:
                extra["extra_body"] = body
            return await _complete_openai_compatible(_get_openai(), model, system, user, **extra)
        if provider == "upstage":
            return await _complete_openai_compatible(
                _get_upstage(),
                model,
                system,
                user,
                max_tokens=max_tokens,
                **({"timeout": timeout} if timeout else {}),
            )
        if provider == "google":
            config_kwargs: dict[str, object] = {
                "system_instruction": system,
                "max_output_tokens": max_tokens,
            }
            if model in GOOGLE_THINKING_MODELS:
                # Gemini 3+는 thinking_budget이 아니라 thinking_level(low/medium/high)을 쓰고
                # "low"가 최솟값이다 — thinking_budget=0 같은 완전 off는 없다.
                config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="LOW")
            if timeout:
                # google-genai 는 클라이언트가 아니라 요청 config 로 받고 단위가 ms 다.
                config_kwargs["http_options"] = genai_types.HttpOptions(timeout=int(timeout * 1000))
            res = await _get_google().aio.models.generate_content(
                model=model,
                contents=user,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
            return res.text
        raise ApiError(502, "PROVIDER_ERROR", f"지원하지 않는 LLM_PROVIDER: {provider}")
    except ApiError:
        raise
    # 코드 이름은 2026-09-22 BE 계약 예시(PROVIDER_ERROR)에 맞췄다. provider 를 4종
    # 지원하므로 LLM_* 보다 이쪽이 실제와도 맞는다. 챗봇 SSE 의 AI_TIMEOUT 은 다른 표면이다.
    except (anthropic.APITimeoutError, openai.APITimeoutError, TimeoutError) as exc:
        raise ApiError(
            504, "PROVIDER_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다."
        ) from exc
    # ponytail: google-genai 는 타임아웃을 별도 예외 타입이 아니라 errors.ClientError(499
    # CANCELLED)로 던진다. 문자열로 구분하는 건 취약해서 일단 PROVIDER_ERROR 로 뭉뚱그렸다 —
    # google provider의 타임아웃을 PROVIDER_TIMEOUT으로 분리하려면 errors.ClientError.code로 분기.
    except Exception as exc:
        # 영구 오류는 재시도하면 안 된다. 2026-10-14 운영 장애가 이 경로였다 — LLM_MODEL 이
        # 없는 모델 ID 로 설정돼 솔루션 생성이 전부 실패했는데, 502(재시도 O)로 나가서 BE 가
        # 전부 한 번씩 더 때렸고 실패가 DB 에 고정됐다(docs/STATE.md 장애 기록, 이슈 #141).
        # 모델명·키·권한·크레딧은 재호출로 바뀌지 않는다.
        status = _provider_status(exc)
        if status in _PERMANENT_PROVIDER_STATUSES:
            raise ApiError(500, "PROVIDER_ERROR", "모델 공급자가 요청을 거절했습니다.") from exc
        raise ApiError(502, "PROVIDER_ERROR", "모델 공급자 호출에 실패했습니다.") from exc


def _primary_timeout(timeout: float | None) -> float | None:
    """primary 시도에만 쓸 타임아웃 — fallback이 설정돼 있으면 상한을 씌운다.

    GPU가 "꺼진"(연결거부) 게 아니라 "멈춘"(응답 없음) 경우, primary가 전체 타임아웃을
    다 기다린 뒤 fallback이 또 전체 타임아웃을 쓰면 최악 두 배가 된다(헥터 PR #185
    리뷰). 호출자가 이미 더 짧은 값을 요청했으면(인사이트의 12초) 그대로 둔다 — 상한은
    늘리지 않고 줄이기만 한다.
    """
    if not settings.llm_fallback_provider:
        return timeout
    cap = settings.llm_fallback_primary_timeout_seconds
    effective = timeout if timeout is not None else settings.llm_timeout_seconds
    return min(effective, cap)


async def complete(
    system: str, user: str, max_tokens: int = 2000, timeout: float | None = None
) -> str:
    """단발 생성. 솔루션·인사이트용. 스트리밍이 필요한 챗봇은 별도 경로를 쓴다.

    timeout 을 주면 이 호출만 그 값으로 덮는다(초). 기본값은 전역 LLM_TIMEOUT_SECONDS 다.
    BE 쪽 응답 제한이 엔드포인트마다 달라서 필요하다 — 인사이트는 BE 가 30초에 끊는데
    전역 60초에 서비스 재시도 1회면 최악 120초라, 끊긴 뒤로도 토큰만 태운다.

    LLM_FALLBACK_PROVIDER가 설정돼 있으면, primary 호출이 가용성 문제로 실패할 때
    같은 요청을 fallback provider로 한 번 더 시도한다(app/clients/circuit_breaker.py
    참고) — 콘텐츠 품질 재시도(MAX_RETRY, 서비스 레이어)와는 완전히 별개 축이다. primary
    시도 자체의 타임아웃은 `_primary_timeout()`으로 짧게 잡는다 — fallback(Claude)
    시도는 원래 timeout 그대로 쓴다.
    """
    use_fallback = await should_use_fallback()
    if use_fallback:
        log_fallback("차단기 열림 — primary 를 건너뛴다")
    provider = settings.llm_fallback_provider if use_fallback else settings.llm_provider
    model = settings.llm_fallback_model if use_fallback else settings.llm_model
    attempt_timeout = timeout if use_fallback else _primary_timeout(timeout)

    try:
        result = await _complete_once(provider, model, system, user, max_tokens, attempt_timeout)
    except ApiError as exc:
        if use_fallback or not settings.llm_fallback_provider or not is_fallback_eligible(exc):
            # 이미 fallback을 쓰고 있었거나(더 넘어갈 데 없음), 기능이 꺼져 있거나,
            # 가용성 문제가 아니면(영구 오류 등) 그대로 올린다 — 기존 동작과 동일.
            raise
        if not is_capacity_error(exc):
            record_failure()
        log_fallback(f"primary 호출 실패 — {exc.code}")
        return await _complete_once(
            settings.llm_fallback_provider,
            settings.llm_fallback_model,
            system,
            user,
            max_tokens,
            timeout,
        )

    if not use_fallback:
        record_success()
    return result


# 프롬프트 캐싱(cache_control)은 붙이지 않는다. 2026-09-22 실측(count_tokens, sonnet-4-5):
#
#   솔루션   742 토큰  (SYSTEM 215)
#   인사이트 535 토큰  (SYSTEM 229)
#
# Sonnet 캐시 최소 단위가 1024 토큰이라 둘 다 애초에 캐시가 만들어지지 않는다. 설령
# 넘더라도 여기는 단발 호출이라 캐시를 읽을 두 번째 호출이 없다 — 쓰기 비용(1.25배)만
# 더 든다. 챗봇 쪽 판단은 app/services/chat/graph.py 참고.
