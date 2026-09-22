import re

import anthropic
import openai
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

from app.core.config import (
    GOOGLE_THINKING_MODELS,
    OPENAI_REASONING_MODELS,
    UPSTAGE_BASE_URL,
    settings,
)
from app.core.errors import ApiError

_clients: dict[str, object] = {}


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
        _clients["openai"] = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
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


async def _complete_openai_compatible(client: AsyncOpenAI, system: str, user: str, **extra) -> str:
    res = await client.chat.completions.create(
        model=settings.llm_model,
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


async def complete(system: str, user: str, max_tokens: int = 2000) -> str:
    """단발 생성. 솔루션·인사이트용. 스트리밍이 필요한 챗봇은 별도 경로를 쓴다."""
    provider = settings.llm_provider
    try:
        if provider == "anthropic":
            res = await _get_anthropic().messages.create(
                model=settings.llm_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return res.content[0].text
        if provider == "openai":
            is_reasoning = settings.llm_model in OPENAI_REASONING_MODELS
            # reasoning 모델(o-series/GPT-5.x)은 max_tokens를 거부하고 max_completion_tokens를
            # 요구한다 (openai SDK의 max_tokens 필드 docstring: "deprecated ... not compatible
            # with o-series models"). GPT-5.6 Luna처럼 reasoning이 기본인 모델만
            # reasoning_effort="none"으로 끈다.
            extra = {"max_completion_tokens" if is_reasoning else "max_tokens": max_tokens}
            if is_reasoning:
                extra["reasoning_effort"] = "none"
            return await _complete_openai_compatible(_get_openai(), system, user, **extra)
        if provider == "upstage":
            return await _complete_openai_compatible(
                _get_upstage(), system, user, max_tokens=max_tokens
            )
        if provider == "google":
            config_kwargs: dict[str, object] = {
                "system_instruction": system,
                "max_output_tokens": max_tokens,
            }
            if settings.llm_model in GOOGLE_THINKING_MODELS:
                # Gemini 3+는 thinking_budget이 아니라 thinking_level(low/medium/high)을 쓰고
                # "low"가 최솟값이다 — thinking_budget=0 같은 완전 off는 없다.
                config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="LOW")
            res = await _get_google().aio.models.generate_content(
                model=settings.llm_model,
                contents=user,
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
            return res.text
        raise ApiError(502, "LLM_ERROR", f"지원하지 않는 LLM_PROVIDER: {provider}")
    except ApiError:
        raise
    except (anthropic.APITimeoutError, openai.APITimeoutError, TimeoutError) as exc:
        raise ApiError(504, "LLM_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다.") from exc
    # ponytail: google-genai 는 타임아웃을 별도 예외 타입이 아니라 errors.ClientError(499
    # CANCELLED)로 던진다. 문자열로 구분하는 건 취약해서 일단 LLM_ERROR 로 뭉뚱그렸다 —
    # google provider의 타임아웃을 LLM_TIMEOUT으로 분리하려면 errors.ClientError.code로 분기.
    except Exception as exc:
        raise ApiError(502, "LLM_ERROR", "모델 공급자 호출에 실패했습니다.") from exc


# 프롬프트 캐싱(cache_control)은 붙이지 않는다. 2026-09-22 실측(count_tokens, sonnet-4-5):
#
#   솔루션   742 토큰  (SYSTEM 215)
#   인사이트 535 토큰  (SYSTEM 229)
#
# Sonnet 캐시 최소 단위가 1024 토큰이라 둘 다 애초에 캐시가 만들어지지 않는다. 설령
# 넘더라도 여기는 단발 호출이라 캐시를 읽을 두 번째 호출이 없다 — 쓰기 비용(1.25배)만
# 더 든다. 챗봇 쪽 판단은 app/services/chat/graph.py 참고.
