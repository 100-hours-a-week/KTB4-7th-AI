"""위키 [AI] 단계4 §3 파이프라인 B. 카드 3장을 1회 호출로 생성.

파싱 실패 시 1회만 재시도한다 (재호출 비교 검증은 두지 않음 — 단계4 §3.3).
"""

import json
from datetime import date

from app.clients import llm
from app.core.errors import ApiError
from app.prompts import solution as solution_prompt
from app.schemas.solution import SolutionCard, SolutionData, SolutionRequest, SolutionResponse

MAX_RETRY = 1
MAX_CARDS = 3
_WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_TEXT_FIELDS = ("title", "summaryText", "detailText", "evidence")

# 한글·라틴·숫자·흔한 구두점만 허용한다. 배포본에서 "POP" 이 "POП"(끝 글자가 키릴 문자
# П, U+041F)으로 나온 사례(2026-10-01) — 화면에서는 생김새가 같아 구분이 안 가는
# 동형이의 문자를 모델이 드물게 섞어 낸다.
_ALLOWED_RANGES = (
    (0x0000, 0x007F),  # Basic Latin
    (0x0080, 0x00FF),  # Latin-1 Supplement (· ° 등)
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x2000, 0x206F),  # General Punctuation (스마트 따옴표·줄임표·대시)
    (0x20A0, 0x20CF),  # Currency Symbols (₩)
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0xAC00, 0xD7A3),  # Hangul Syllables
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
)


def _day_facts(target_date: str) -> tuple[str, bool]:
    code = _WEEKDAY_CODES[date.fromisoformat(target_date).weekday()]
    return code, code in ("SAT", "SUN")


def _has_foreign_script(text: str) -> bool:
    return any(not any(lo <= ord(ch) <= hi for lo, hi in _ALLOWED_RANGES) for ch in text)


def _parse(raw: str) -> list[SolutionCard] | None:
    """계약·ERD 를 만족하는 카드 목록만 돌려준다. 하나라도 어긋나면 None 이라 재시도한다.

    카드별 제약(rankNo ≥ 1, title 200자)은 스키마가 본다. 여기서는 카드 사이 제약만 본다 —
    rankNo 가 겹치면 BE 의 UNIQUE (solution_bundle_id, rank_no) 를 위반해 묶음 전체가
    저장되지 않는다.
    """
    try:
        data = json.loads(llm.strip_fence(raw))
        cards = [SolutionCard(**card) for card in data["solutionCards"]]
    except Exception:
        return None

    if not 1 <= len(cards) <= MAX_CARDS:
        return None
    ranks = [card.rankNo for card in cards]
    if len(set(ranks)) != len(ranks):
        return None
    for card in cards:
        for field in _TEXT_FIELDS:
            value = getattr(card, field)
            if value and _has_foreign_script(value):
                return None
    return cards


async def generate(req: SolutionRequest) -> SolutionResponse:
    day_of_week, is_weekend = _day_facts(req.targetDate)
    # exclude_none: 값이 없는 지표(이전 기간 비교가 없는 첫 업로드 등)는 프롬프트에서 뺀다.
    metrics = req.metrics.model_dump(exclude_none=True)
    prompt = solution_prompt.build(metrics, req.targetDate, day_of_week, is_weekend)

    # 3장을 선호하되, 모자란 응답이라고 버리지는 않는다. 카드 2장이 나가는 것보다
    # 500 이 나가는 쪽이 점주에게 더 나쁘다 — 그날 솔루션이 아예 없어진다.
    cards = None
    for _ in range(MAX_RETRY + 1):
        parsed = _parse(await llm.complete(solution_prompt.SYSTEM, prompt))
        cards = parsed or cards
        if parsed and len(parsed) == MAX_CARDS:
            break

    if not cards:
        raise ApiError(500, "SOLUTION_GENERATION_FAILED", "솔루션 생성에 실패했습니다.")

    return SolutionResponse(
        data=SolutionData(
            targetDate=req.targetDate,
            solutionCards=cards,
            modelVersion=llm.model_label(),
        )
    )
