import time
import uuid
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from app.core.config import settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class Vertex:
    x: float
    y: float


@dataclass(frozen=True)
class OcrToken:
    """클로바 OCR `fields[]` 항목 그대로 — 토큰(단어) 단위, 줄 단위로 묶여 있지 않다.

    `line_break`가 True면 이 토큰 뒤에 줄바꿈이 있다는 뜻이다(2026-10-13 실호출 확인,
    `devtools/clova_ocr_check.py`). 줄 묶기는 호출하는 쪽(`app/services/menu.py`)이 한다.
    """

    text: str
    confidence: float
    vertices: tuple[Vertex, Vertex, Vertex, Vertex]
    line_break: bool


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, httpx.TimeoutException) or (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 500, 502, 503)
    )


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0.5),
    reraise=True,
)
async def _call_clova(image_bytes: bytes, image_format: str) -> dict:
    import base64

    body = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [
            {
                "format": image_format,
                "name": "menu",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        ],
    }
    async with httpx.AsyncClient(timeout=settings.clova_ocr_timeout_seconds) as client:
        res = await client.post(
            settings.clova_ocr_invoke_url,
            headers={
                "X-OCR-SECRET": settings.clova_ocr_secret_key,
                "Content-Type": "application/json",
            },
            json=body,
        )
        res.raise_for_status()
        return res.json()


async def extract_text_blocks(image_url: str) -> list[OcrToken]:
    """이미지 URL을 받아 클로바 OCR로 토큰 목록을 뽑는다.

    BE가 주는 서명 URL을 클로바가 직접 fetch할 수 있는지 확인되지 않아, AI가 먼저
    다운로드해 base64로 보낸다(2026-10-13 결정 — 설계 스펙 참고).
    """
    async with httpx.AsyncClient(timeout=settings.clova_ocr_timeout_seconds) as client:
        img_res = await client.get(image_url)
        img_res.raise_for_status()
    image_format = image_url.rsplit(".", 1)[-1].split("?")[0].lower() or "jpg"

    try:
        raw = await _call_clova(img_res.content, image_format)
    except httpx.HTTPStatusError as exc:
        raise ApiError(502, "OCR_PROVIDER_ERROR", "OCR 공급자 호출에 실패했습니다.") from exc
    except httpx.TimeoutException as exc:
        raise ApiError(
            504, "OCR_PROVIDER_TIMEOUT", "OCR 응답이 시간 내에 완료되지 않았습니다."
        ) from exc

    return parse_clova_response(raw)


def parse_clova_response(raw: dict) -> list[OcrToken]:
    """클로바 OCR 원본 JSON 응답을 `OcrToken` 목록으로 바꾼다.

    실호출과 별개로 테스트·검증 스크립트에서 저장된 응답을 재사용할 때도 쓴다.
    """
    image_result = raw["images"][0]
    if image_result.get("inferResult") != "SUCCESS":
        return []

    return [
        OcrToken(
            text=field["inferText"],
            confidence=field["inferConfidence"],
            vertices=tuple(Vertex(v["x"], v["y"]) for v in field["boundingPoly"]["vertices"]),
            line_break=field["lineBreak"],
        )
        for field in image_result.get("fields", [])
    ]
