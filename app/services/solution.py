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

# 프롬프트는 2026-10-01 부터 "지표에 있는 24시간제 그대로 쓰고 '오후 2시'로 바꾸지 마세요"
# 라고 지시한다. 실측 준수율 40%(n=48, Qwen3-32B) — 전항목 통과율 27% 의 거의 전부가 이
# 항목 때문이다. 재시도로 때우기엔 너무 자주 틀리고, 다행히 변환이 결정론적이라 코드로
# 치환한다. 모델이 뭘 쓰든 화면에는 24시간제만 나간다.
#
# "2시간" 처럼 시각이 아닌 표현은 건드리면 안 되므로 "시" 뒤에 "간" 이 오면 제외한다.
# 범위는 "오후 2~5시" 와 "저녁 7시~9시" 두 모양 다 온다 — 뒤쪽 숫자가 접두어를 물려받아야
# 해서 따로 잡는다. 안 그러면 "저녁 7시~9시" 가 "19시~9시" 가 된다.
_WORDS = "오전|오후|새벽|아침|낮|저녁|밤"
_CLOCK = re.compile(
    rf"(?P<rw>{_WORDS})\s*(?P<h1>\d{{1,2}})\s*시?\s*[~\u2013\u2014-]\s*(?P<h2>\d{{1,2}})\s*시(?!\uac04)"
    rf"|(?P<sw>{_WORDS})\s*(?P<h>\d{{1,2}})\s*시(?!\uac04)"
)
# 접두어별 12시간제 → 24시간제 보정
_PM_WORDS = {"오후", "저녁", "밤"}
_AM_WORDS = {"오전", "새벽", "아침"}


# 아래 둘은 프롬프트가 금지하는데 실측 준수율이 금액 83%, 배율 77% 다(n=48, Qwen3-32B).
# 시각처럼 치환할 수가 없어서 — "3만원" 이 어느 금액을 어림한 건지, "3배" 를 뭘로 바꿀지
# 코드가 못 정한다 — 검출해서 재시도로 보낸다(#119 동형이의 문자와 같은 경로).
#
# "3만원", "1억2천만원" 처럼 만/억 단위로 줄여 쓴 금액
_ROUNDED_AMOUNT = re.compile(r"\d[\d,]*\s*[억만][\d\s억만천백]*원")
# 배율은 지표에 없는 계산값이다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다.
# "배달"·"배치"·"배송" 이 걸리지 않게 뒤를 본다.
_COMPUTED_RATIO = re.compile(
    r"(?:\d+(?:\.\d+)?|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배(?![달치송포분])"
    r"|\d+\s*분의\s*\d+"
)


def _hour24(word: str, hour: int) -> int | None:
    """못 바꾸면 None — 손대지 않는 편이 틀리게 바꾸는 것보다 낫다."""
    if not 1 <= hour <= 12:
        return None
    if word in _PM_WORDS:
        return 12 if hour == 12 else hour + 12
    if word in _AM_WORDS:
        return 0 if hour == 12 else hour
    return hour  # "낮 12시" 처럼 보정이 필요 없는 경우


def to_24h(text: str) -> str:
    """\"오후 2시\" → \"14시\", \"오후 2~5시\" → \"14~17시\"."""

    def swap(match: re.Match) -> str:
        if match.group("sw"):
            hour = _hour24(match.group("sw"), int(match.group("h")))
            return f"{hour}시" if hour is not None else match.group(0)

        word = match.group("rw")
        first = _hour24(word, int(match.group("h1")))
        second = _hour24(word, int(match.group("h2")))
        # "오후 11~1시" 처럼 접두어를 넘어가는 구간은 뜻이 모호하니 그대로 둔다
        if first is None or second is None or second <= first:
            return match.group(0)
        return f"{first}~{second}시"

    return _CLOCK.sub(swap, text)


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
        cards = [SolutionCard(**_normalize(card)) for card in data["solutionCards"]]
    except Exception:
        return None

    if not 1 <= len(cards) <= MAX_CARDS:
        return None
    ranks = [card.rankNo for card in cards]
    if len(set(ranks)) != len(ranks):
        return None
    if any(_violations(card) for card in cards):
        return None
    return cards


_TEXT_FIELDS = ("title", "summaryText", "detailText", "evidence")


def _normalize(card: dict) -> dict:
    """화면에 나가는 텍스트를 다듬는다. 지금은 시각 표기 하나뿐이다."""
    return {
        key: to_24h(value) if key in _TEXT_FIELDS and isinstance(value, str) else value
        for key, value in card.items()
    }


def _violations(card: SolutionCard) -> list[str]:
    """재시도로 보낼 이유. 비어 있으면 통과다.

    셋 다 프롬프트에 규칙이 있는데 지켜지지 않는 것들이고, 치환으로는 못 고친다.
    """
    texts = (card.title, card.summaryText, card.detailText, card.evidence or "")
    reasons = []
    if _foreign_chars(card):
        reasons.append("FOREIGN_CHAR")
    if any(_ROUNDED_AMOUNT.search(text) for text in texts):
        reasons.append("ROUNDED_AMOUNT")
    if any(_COMPUTED_RATIO.search(text) for text in texts):
        reasons.append("COMPUTED_RATIO")
    return reasons


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
