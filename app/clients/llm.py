import re

import anthropic
from anthropic import AsyncAnthropic

from app.core.config import settings
from app.core.errors import ApiError

_client: AsyncAnthropic | None = None


def _get() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


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
    try:
        res = await _get().messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APITimeoutError as exc:
        raise ApiError(504, "LLM_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다.") from exc
    except Exception as exc:
        raise ApiError(502, "LLM_ERROR", "모델 공급자 호출에 실패했습니다.") from exc

    return res.content[0].text


# 프롬프트 캐싱(cache_control)은 여기 붙이지 않았다. 솔루션·인사이트의 시스템 프롬프트는
# 캐시 최소 토큰에 한참 못 미쳐서 효과가 없다. 챗봇은 시스템 프롬프트 + 매장 고정 컨텍스트 +
# 툴 스키마가 합쳐져 충분히 커지므로 그때 붙인다 (위키 단계2 §6).
