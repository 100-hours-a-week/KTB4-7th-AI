"""위키 [AI] 단계4 §3 파이프라인 B. 카드 3장을 1회 호출로 생성.

파싱 실패 시 1회만 재시도한다 (재호출 비교 검증은 두지 않음 — 단계4 §3.3).
"""

import json
import re
from datetime import date

from app.clients import llm
from app.core.errors import ApiError
from app.prompts import solution as solution_prompt
from app.schemas.solution import SolutionCard, SolutionData, SolutionRequest, SolutionResponse
from app.services.solution_focus import assign as assign_focus

MAX_RETRY = 1
MAX_CARDS = 3
_WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# 모델이 라틴 약어를 쓰면서 드물게 다른 스크립트의 동형이의 문자를 섞어낸다 — 배포본에서
# "POP" 이 "POП"(끝 글자가 라틴 P 가 아니라 키릴 П, U+041F)로 나온 사례를 확인했다
# (2026-10-02). 화면 폰트에서는 구분이 거의 안 돼 "글자가 깨졌다"로만 드러난다.
#
# 글자(letter)만 본다. 구두점·기호까지 화이트리스트로 막으면 모델이 즐겨 쓰는 기호 하나에
# 매번 걸려 재시도도 같은 이유로 실패하고, 그날 솔루션이 통째로 없어진다(우리 프롬프트
# 파일에도 "→" 가 들어 있다). 동형이의 문자는 전부 글자라 글자만 봐도 놓치지 않는다 —
# 키릴 П, 전각 Ｐ, 한자 売 가 모두 걸린다.
_HANGUL_OR_LATIN = re.compile(r"[A-Za-z\uac00-\ud7a3\u3131-\u318e]")


def _day_facts(target_date: str) -> tuple[str, bool]:
    code = _WEEKDAY_CODES[date.fromisoformat(target_date).weekday()]
    return code, code in ("SAT", "SUN")


def _parse(raw: str) -> list[SolutionCard] | None:
    """계약·ERD 를 만족하는 카드 목록만 돌려준다. 하나라도 어긋나면 None 이라 재시도한다.

    카드별 길이·범위 제약(rankNo ≥ 1, title 200자)은 스키마가 본다. 여기서는 스키마가
    볼 수 없는 것만 본다 — rankNo 가 겹치면 BE 의 UNIQUE (solution_bundle_id, rank_no) 를
    위반해 묶음 전체가 저장되지 않고, 동형이의 문자는 타입상 멀쩡한 문자열이라 통과한다.
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
    if any(_foreign_chars(card) for card in cards):
        return None
    return cards


def _foreign_chars(card: SolutionCard) -> set[str]:
    """카드 텍스트에 섞인 한글·라틴 밖 글자. 비어 있으면 정상이다."""
    texts = (card.title, card.summaryText, card.detailText, card.evidence or "")
    return {ch for text in texts for ch in text if ch.isalpha() and not _HANGUL_OR_LATIN.match(ch)}


async def generate(req: SolutionRequest) -> SolutionResponse:
    day_of_week, is_weekend = _day_facts(req.targetDate)
    # exclude_none: 값이 없는 지표(이전 기간 비교가 없는 첫 업로드 등)는 프롬프트에서 뺀다.
    metrics = req.metrics.model_dump(exclude_none=True)
    # 카드마다 쓸 근거 지표를 코드가 배정한다 — 모델이 고르게 두면 같은 지표로 두 장을
    # 만든다(실측 10 번 중 4 번). app/services/solution_focus.py 참고.
    focus = assign_focus(metrics)
    prompt = solution_prompt.build(focus, req.targetDate, day_of_week, is_weekend)

    # 3장을 선호하되, 모자란 응답이라고 버리지는 않는다. 카드 2장이 나가는 것보다
    # 500 이 나가는 쪽이 점주에게 더 나쁘다 — 그날 솔루션이 아예 없어진다.
    wanted = len(focus) or MAX_CARDS
    cards = None
    for _ in range(MAX_RETRY + 1):
        parsed = _parse(await llm.complete(solution_prompt.SYSTEM, prompt))
        cards = parsed or cards
        if parsed and len(parsed) == wanted:
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
