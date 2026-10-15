"""네이버 클로바 OCR 실호출 점검 스크립트.

메뉴판 인식(`app/clients/ocr.py`) 구현 전, 클로바 OCR이 실제로 어떤 필드명·구조로
텍스트·좌표·신뢰도를 돌려주는지 실제 이미지로 확인한다. 무료 티어가 월 100회라 소량만
호출한다.

    uv run python -m devtools.clova_ocr_check docs/메뉴_더콤마.png

요금 발생(무료 한도 차감)이 있으니 승인 후 소량으로 실행한다.
"""

import argparse
import base64
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from app.core.config import settings


def call_clova_ocr(image_path: Path) -> dict:
    image_bytes = image_path.read_bytes()
    body = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [
            {
                "format": image_path.suffix.lstrip(".").lower(),
                "name": image_path.stem,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        ],
    }
    res = httpx.post(
        settings.clova_ocr_invoke_url,
        headers={
            "X-OCR-SECRET": settings.clova_ocr_secret_key,
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30.0,
    )
    res.raise_for_status()
    return res.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="메뉴판 이미지 경로")
    args = parser.parse_args()

    if not settings.clova_ocr_secret_key or not settings.clova_ocr_invoke_url:
        print("CLOVA_OCR_SECRET_KEY / CLOVA_OCR_INVOKE_URL 이 .env 에 없습니다.", file=sys.stderr)
        return 1

    result = call_clova_ocr(args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
