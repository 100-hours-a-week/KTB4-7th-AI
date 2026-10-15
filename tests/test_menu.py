import json

import httpx

from app.clients import llm, ocr
from app.core.errors import ApiError
from app.main import app

REQUEST_BODY = {
    "storeId": 1,
    "batchId": 15,
    "images": [
        {"imageId": 52, "imageUrl": "https://example.com/menu1.jpg", "order": 1},
    ],
}


def _token(text: str, x0: float, x1: float, y0: float, y1: float, line_break: bool) -> ocr.OcrToken:
    vertices = (
        ocr.Vertex(x0, y0),
        ocr.Vertex(x1, y0),
        ocr.Vertex(x1, y1),
        ocr.Vertex(x0, y1),
    )
    return ocr.OcrToken(text=text, confidence=0.95, vertices=vertices, line_break=line_break)


AMERICANO_LINE = [_token("아메리카노 4,000", 0, 100, 0, 20, True)]

LLM_COFFEE = json.dumps({"categories": ["COFFEE"]})


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v2/ai/menu-recognition", json=body)


async def test_정상_요청이_detectedItems를_반환한다(monkeypatch):
    async def fake_extract(image_url: str) -> list[ocr.OcrToken]:
        return AMERICANO_LINE

    async def fake_complete(system: str, user: str, max_tokens: int = 1000) -> str:
        return LLM_COFFEE

    monkeypatch.setattr(ocr, "extract_text_blocks", fake_extract)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["message"]
    items = body["data"]["detectedItems"]
    assert len(items) == 1
    assert items[0] == {
        "sourceImageId": 52,
        "name": "아메리카노",
        "category": "COFFEE",
        "price": 4000,
        "confidence": 0.95,
        "priceReviewRequired": False,
    }
    assert body["data"]["failedImages"] == []


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "images"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]
    assert res.json()["data"] is None


async def test_전부_실패하면_422와_failReason을_반환한다(monkeypatch):
    async def fake_extract(image_url: str) -> list[ocr.OcrToken]:
        raise ApiError(502, "OCR_PROVIDER_ERROR", "OCR 공급자 호출에 실패했습니다.")

    monkeypatch.setattr(ocr, "extract_text_blocks", fake_extract)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 422
    body = res.json()
    assert body["failReason"] == "AI_PROCESSING_ERROR"
    assert body["data"] is None


async def test_일부_이미지만_실패하면_200과_failedImages를_함께_반환한다(monkeypatch):
    two_images = {
        **REQUEST_BODY,
        "images": [
            {"imageId": 52, "imageUrl": "https://example.com/menu1.jpg", "order": 1},
            {"imageId": 53, "imageUrl": "https://example.com/menu2.jpg", "order": 2},
        ],
    }

    async def fake_extract(image_url: str) -> list[ocr.OcrToken]:
        if image_url.endswith("menu1.jpg"):
            return AMERICANO_LINE
        raise ApiError(504, "OCR_PROVIDER_TIMEOUT", "OCR 응답이 시간 내에 완료되지 않았습니다.")

    async def fake_complete(system: str, user: str, max_tokens: int = 1000) -> str:
        return LLM_COFFEE

    monkeypatch.setattr(ocr, "extract_text_blocks", fake_extract)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(two_images)

    assert res.status_code == 200
    body = res.json()["data"]
    assert [item["sourceImageId"] for item in body["detectedItems"]] == [52]
    assert body["failedImages"] == [{"sourceImageId": 53, "failReason": "AI_PROCESSING_ERROR"}]


async def test_카테고리_판별_실패시_OTHER가_아니라_null이다(monkeypatch):
    async def fake_extract(image_url: str) -> list[ocr.OcrToken]:
        return AMERICANO_LINE

    async def fake_complete(system: str, user: str, max_tokens: int = 1000) -> str:
        return "JSON 아님"

    monkeypatch.setattr(ocr, "extract_text_blocks", fake_extract)
    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["detectedItems"][0]["category"] is None


async def test_메뉴_텍스트가_없으면_MENU_TEXT_NOT_FOUND로_실패한다(monkeypatch):
    async def fake_extract(image_url: str) -> list[ocr.OcrToken]:
        return []

    monkeypatch.setattr(ocr, "extract_text_blocks", fake_extract)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 422
    assert res.json()["failReason"] == "MENU_TEXT_NOT_FOUND"
