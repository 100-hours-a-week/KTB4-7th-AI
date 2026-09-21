import anthropic
import openai
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

from app.core.config import OPENAI_REASONING_MODELS, UPSTAGE_BASE_URL, settings
from app.core.errors import ApiError

_clients: dict[str, object] = {}


def _get_anthropic() -> AsyncAnthropic:
    if "anthropic" not in _clients:
        _clients["anthropic"] = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _clients["anthropic"]


def _get_openai() -> AsyncOpenAI:
    if "openai" not in _clients:
        _clients["openai"] = AsyncOpenAI(api_key=settings.openai_api_key)
    return _clients["openai"]


def _get_upstage() -> AsyncOpenAI:
    if "upstage" not in _clients:
        _clients["upstage"] = AsyncOpenAI(
            api_key=settings.upstage_api_key, base_url=UPSTAGE_BASE_URL
        )
    return _clients["upstage"]


def _get_google() -> genai.Client:
    if "google" not in _clients:
        _clients["google"] = genai.Client(api_key=settings.google_api_key)
    return _clients["google"]


async def _complete_openai_compatible(
    client: AsyncOpenAI, system: str, user: str, max_tokens: int, **extra
) -> str:
    res = await client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
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
            # GPT-5.6 Luna처럼 reasoning이 기본인 모델만 reasoning_effort="none"으로 끈다.
            extra = (
                {"reasoning_effort": "none"}
                if settings.llm_model in OPENAI_REASONING_MODELS
                else {}
            )
            return await _complete_openai_compatible(
                _get_openai(), system, user, max_tokens, **extra
            )
        if provider == "upstage":
            return await _complete_openai_compatible(_get_upstage(), system, user, max_tokens)
        if provider == "google":
            res = await _get_google().aio.models.generate_content(
                model=settings.llm_model,
                contents=user,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system, max_output_tokens=max_tokens
                ),
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


# 프롬프트 캐싱(cache_control)은 여기 붙이지 않았다. 솔루션·인사이트의 시스템 프롬프트는
# 캐시 최소 토큰에 한참 못 미쳐서 효과가 없다. 챗봇은 시스템 프롬프트 + 매장 고정 컨텍스트 +
# 툴 스키마가 합쳐져 충분히 커지므로 그때 붙인다 (위키 단계2 §6).
