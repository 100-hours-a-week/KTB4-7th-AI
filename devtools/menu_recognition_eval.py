"""메뉴판 인식 파이프라인 정확도 평가.

실제 메뉴판 사진 3장의 클로바 OCR 응답(저장된 픽스처)으로 `app/services/menu.py`
파이프라인을 돌려, BE가 받을 것과 동일한 형태(`DetectedMenuItem`)의 JSON을 만들고
사람이 직접 읽은 정답지(`tests/fixtures/menu/ground_truth.json`)와 대조한다.

클로바는 재호출하지 않는다(저장된 응답 재사용 — 무료 한도 보호). 카테고리 분류는
`app/clients/llm.py`로 실제 호출한다(소액 과금).

    uv run python -m devtools.menu_recognition_eval
    uv run python -m devtools.menu_recognition_eval --save-json  # 사진별 JSON을 파일로도 저장
"""

import argparse
import asyncio
import difflib
import json
import sys
from pathlib import Path

from app.clients.ocr import parse_clova_response
from app.services.menu import build_detected_items

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "menu"
PHOTOS = {
    "더콤마": "더콤마_ocr.json",
    "아드프": "아드프_ocr.json",
    "여름": "여름_ocr.json",
}

_NAME_MATCH_THRESHOLD = 0.55


def _normalize(name: str) -> str:
    return name.replace(" ", "").lower()


def _name_similarity(gt_norm: str, detected_norm: str) -> float:
    """포함 관계를 먼저 본다 — "아메리카노"와 "아메리카노Americano(onlyiced)"처럼

    한쪽이 다른 쪽을 그대로 담고 있으면(언어 혼용 표기 등) 길이 차이와 무관하게
    확실한 매칭으로 친다. SequenceMatcher 비율만 쓰면 짧은 쪽이 긴 쪽에 묻혀 낮게
    나온다(2026-10-14 실측 — "아메리카노" vs 영문 포함 긴 문자열에서 0.3대로 떨어짐).
    """
    if not gt_norm or not detected_norm:
        return 0.0
    if gt_norm in detected_norm or detected_norm in gt_norm:
        return 1.0
    return difflib.SequenceMatcher(None, gt_norm, detected_norm).ratio()


def _match_items(gt_items: list[dict], detected: list[dict]) -> tuple[list[dict], list[dict]]:
    """정답 항목마다 가장 비슷한 이름의 추출 항목을 하나씩 greedy로 짝짓는다."""
    remaining = list(enumerate(detected))
    results = []
    for gt in gt_items:
        gt_norm = _normalize(gt["name"])
        best_idx, best_ratio = None, 0.0
        for pos, (_orig_idx, item) in enumerate(remaining):
            ratio = _name_similarity(gt_norm, _normalize(item["name"]))
            if ratio > best_ratio:
                best_ratio, best_idx = ratio, pos
        matched = None
        if best_idx is not None and best_ratio >= _NAME_MATCH_THRESHOLD:
            _, matched = remaining.pop(best_idx)
        results.append({"gt": gt, "matched": matched, "name_ratio": best_ratio})
    extras = [item for _, item in remaining]
    return results, extras


async def eval_photo(key: str, ocr_filename: str, gt_sections: list[dict]) -> dict:
    raw = json.loads((FIXTURES / ocr_filename).read_text())
    tokens = parse_clova_response(raw)
    detected_items = await build_detected_items(source_image_id=1, tokens=tokens)
    detected = [item.model_dump() for item in detected_items]

    gt_flat = [
        {"name": name, "price": price, "category": cat}
        for section in gt_sections
        for item in section["items"]
        for name, price, cat, *_ in [item + [None] * (4 - len(item))]
    ]

    matches, extras = _match_items(gt_flat, detected)
    matched_count = sum(1 for m in matches if m["matched"])
    price_checkable = [m for m in matches if m["matched"] and m["gt"]["price"] is not None]
    price_correct = sum(1 for m in price_checkable if m["matched"]["price"] == m["gt"]["price"])
    cat_correct = sum(
        1 for m in matches if m["matched"] and m["matched"]["category"] == m["gt"]["category"]
    )

    return {
        "key": key,
        "gt_total": len(gt_flat),
        "matched": matched_count,
        "detected_total": len(detected),
        "price_checkable": len(price_checkable),
        "price_correct": price_correct,
        "cat_correct": cat_correct,
        "extras": extras,
        "misses": [m["gt"] for m in matches if not m["matched"]],
        "mismatches": [
            m
            for m in matches
            if m["matched"]
            and (
                m["matched"]["price"] != m["gt"]["price"]
                or m["matched"]["category"] != m["gt"]["category"]
            )
        ],
        "detected_raw": detected,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-json", action="store_true", help="사진별 detectedItems JSON도 파일로 저장"
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="전체 평가 결과(재현율·불일치 등)를 JSON으로 저장"
    )
    args = parser.parse_args()
    report: dict = {}

    gt_data = json.loads((FIXTURES / "ground_truth.json").read_text())

    overall = {
        "gt_total": 0,
        "matched": 0,
        "price_checkable": 0,
        "price_correct": 0,
        "cat_correct": 0,
    }
    for key, ocr_filename in PHOTOS.items():
        result = await eval_photo(key, ocr_filename, gt_data[key]["sections"])
        print(f"\n=== {key} ===")
        print(
            f"  재현율(recall): {result['matched']}/{result['gt_total']}"
            f" ({result['matched'] / result['gt_total']:.0%})"
            f"  추출 총 {result['detected_total']}개 (잉여 {len(result['extras'])}개)"
        )
        if result["price_checkable"]:
            print(
                f"  가격 정확도: {result['price_correct']}/{result['price_checkable']}"
                f" ({result['price_correct'] / result['price_checkable']:.0%})"
            )
        if result["matched"]:
            print(
                f"  카테고리 정확도: {result['cat_correct']}/{result['matched']}"
                f" ({result['cat_correct'] / result['matched']:.0%})"
            )
        if result["misses"]:
            print(
                f"  놓친 항목({len(result['misses'])}): "
                + ", ".join(m["name"] for m in result["misses"])
            )
        if result["mismatches"]:
            print(f"  값 틀림({len(result['mismatches'])}):")
            for m in result["mismatches"]:
                gt, got = m["gt"], m["matched"]
                print(
                    f"    {gt['name']}: 정답 price={gt['price']} cat={gt['category']}"
                    f" / 추출 price={got['price']} cat={got['category']}"
                )
        if result["extras"]:
            print(
                f"  환각(정답에 없는 추출, {len(result['extras'])}): "
                + ", ".join(e["name"] for e in result["extras"])
            )

        for k in overall:
            overall[k] += result[k]
        report[key] = {k: v for k, v in result.items() if k != "detected_raw"}

        if args.save_json:
            out = FIXTURES / f"{key}_detected.json"
            out.write_text(json.dumps(result["detected_raw"], ensure_ascii=False, indent=2))
            print(f"  → {out} 저장")

    print("\n=== 전체 ===")
    recall = overall["matched"] / overall["gt_total"]
    print(f"  재현율: {overall['matched']}/{overall['gt_total']} ({recall:.0%})")
    if overall["price_checkable"]:
        print(
            f"  가격 정확도: {overall['price_correct']}/{overall['price_checkable']}"
            f" ({overall['price_correct'] / overall['price_checkable']:.0%})"
        )
    if overall["matched"]:
        print(
            f"  카테고리 정확도: {overall['cat_correct']}/{overall['matched']}"
            f" ({overall['cat_correct'] / overall['matched']:.0%})"
        )

    if args.report:
        args.report.write_text(
            json.dumps({"overall": overall, "photos": report}, ensure_ascii=False, indent=2)
        )
        print(f"\n→ {args.report} 저장")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
