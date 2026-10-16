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
from app.services.solution_focus import derive as derive_metrics

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
# "낮" 은 1~6 시가 오후다("낮 2시" = 14시). 11~12 시는 보정이 필요 없다("낮 11시" = 11시).
# 그 사이(7~10 시)는 뜻이 정해지지 않아 손대지 않는다 — 그런 말을 쓰지 않으니 모델의 실수다.
_NOON_PM_MAX = 6
_NOON_PLAIN_MIN = 11


# 아래 둘은 프롬프트가 금지하는데 실측 준수율이 금액 83%, 배율 77% 다(n=48, Qwen3-32B).
# 시각처럼 치환할 수가 없어서 — "3만원" 이 어느 금액을 어림한 건지, "3배" 를 뭘로 바꿀지
# 코드가 못 정한다 — 검출해서 재시도로 보낸다(#119 동형이의 문자와 같은 경로).
#
# _normalize 가 치환하지 못하고 남은 12 시간제. 애매해서 못 바꾼 것들("낮 7시")이라
# 치환 대신 재시도로 보낸다 — 채점기 devtools/grade.py::_AMPM 과 같은 패턴이어야 하고,
# tests/test_solution_time.py 가 둘이 어긋나면 실패한다.
_AMPM_LEFT = re.compile(rf"(?:{_WORDS})\s*\d{{1,2}}\s*시(?!\uac04)")

# "3만원", "1억2천만원" 처럼 만/억 단위로 줄여 쓴 금액
_ROUNDED_AMOUNT = re.compile(r"\d[\d,]*\s*[억만][\d\s억만천백]*원")
# 배율은 지표에 없는 계산값이다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다.
# "배달"·"배치"·"배송" 이 걸리지 않게 뒤를 본다.
_COMPUTED_RATIO = re.compile(
    r"(?:\d+(?:\.\d+)?|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배(?![달치송포분])"
    r"|\d+\s*분의\s*\d+"
)

# 화면에 보일 금액·비율만 본다. "21시"·"직원 1명" 같은 실행 지시용 작은 수는 애초에 안 걸린다.
# devtools/grade.py::_DISPLAY_NUM 과 같은 패턴.
_DISPLAY_NUM = re.compile(r"[\d,]{4,}\s*원|\d+\.?\d*\s*%")

# 누구나 할 수 있는 말("마케팅을 강화하세요") — 프롬프트에 이미 금지 규칙이 있다(_USER
# 116~118줄). 실측(n=60, Qwen3-32B)에서 거의 절반(43%)이 이걸 어겼는데 지금까지 재시도
# 대상이 아니었다 — 전항목 통과율을 깎아먹는 압도적 1위 원인이라 추가한다(2026-10-15).
# devtools/grade.py::_VAGUE_ACTION 과 같은 패턴이어야 하고, tests/test_solution_rules.py 가
# 둘이 어긋나면 실패한다.
_VAGUE_ACTION = re.compile(
    r"(?:마케팅|홍보|프로모션|캠페인|전략|활동|노력|서비스)[을를]?\s*"
    r"(?:강화|개선|변경|확대|진행|실행|집중)"
)

# 점주 신고(2026-10-15): "현재 기간 순매출이 124,946,029원이며"처럼 기준 없이 기간을
# 가리키는 문장이 나왔다. targetDate 를 그 자리에 박아 넣으면 되지 않을까 했는데, BE 확인
# 결과 salesSummary.netSales 는 하루 매출이 아니라 분석 기간(salesAnalysisId 가 집계한
# 기간) 합계였다 — targetDate 로 대체하면 기간 합계를 "오늘 하루 매출"처럼 더 구체적으로
# 틀리게 말하게 된다. 집계 기간의 시작·끝을 어떤 필드로 받을지 BE 와 합의 전이라, 그
# 필드가 오기 전까지는 "현재/이번/해당/지금 기간" 같은 빈말 자체를 막는다. "이전/전 기간"
# (vsPrevPeriod 비교 대상)은 계약상 정의돼 있어 걸리지 않게 둔다. devtools/grade.py 의
# 같은 이름 패턴과 일치해야 하고, tests/test_solution_rules.py 가 둘이 어긋나면 실패한다.
_VAGUE_PERIOD = re.compile(r"(?:현재|이번|해당|지금)\s*기간")


def _hour24(word: str, hour: int) -> int | None:
    """못 바꾸면 None — 손대지 않는 편이 틀리게 바꾸는 것보다 낫다."""
    if not 1 <= hour <= 12:
        return None
    if word in _PM_WORDS:
        return 12 if hour == 12 else hour + 12
    if word in _AM_WORDS:
        return 0 if hour == 12 else hour
    # 남은 건 "낮" 하나다. "낮 2시" 를 그대로 "2시" 로 내보내면 새벽 2시가 된다 —
    # 12 시간이 틀린 값인데 화면에서는 멀쩡해 보인다(2026-10-08 실측 중 발견).
    if hour <= _NOON_PM_MAX:
        return hour + 12
    if hour >= _NOON_PLAIN_MIN:
        return hour
    return None  # "낮 7시" 는 뜻이 안 정해진다 — 그대로 두면 채점기가 잡아 재시도로 간다


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


# 배율은 "지표에 있으면 인용, 없으면 날조" 다. derive() 가 넣어 주는 hourlyPeakRatio 만
# 인정한다 — _metric_numbers 전체를 쓰면 hour 값(14·18)이 섞여 "14배" 가 통과한다.
_RATIO_KEYS = ("hourlyPeakRatio",)
_KO_NUMERALS = {
    "두": "2",
    "세": "3",
    "네": "4",
    "다섯": "5",
    "여섯": "6",
    "일곱": "7",
    "여덟": "8",
    "아홉": "9",
    "열": "10",
}


def _allowed_ratios(metrics: dict) -> set[str]:
    out: set[str] = set()
    for key in _RATIO_KEYS:
        for item in metrics.get(key) or []:
            value = item.get("ratio") if isinstance(item, dict) else item
            if isinstance(value, int | float) and not isinstance(value, bool):
                out.add(f"{float(value):g}")
    return out


def _ratio_value(text: str) -> str | None:
    """배율 표현에서 숫자를 꺼낸다. "3분의 1" 처럼 못 꺼내면 None — 늘 날조로 본다."""
    head = text.split("배")[0].strip()
    if head in _KO_NUMERALS:
        return _KO_NUMERALS[head]
    try:
        return f"{float(head):g}"
    except ValueError:
        return None


def _ungrounded_ratios(texts, metrics: dict) -> bool:
    allowed = _allowed_ratios(metrics)
    for text in texts:
        for match in _COMPUTED_RATIO.finditer(text):
            value = _ratio_value(match.group())
            if value is None or value not in allowed:
                return True
    return False


def _metric_numbers(metrics: dict) -> set[str]:
    """지표에 실제로 있는 값들. 비율은 백분율로도 인정한다(0.417 → 41.7).

    devtools/grade.py::_metric_numbers 와 같은 로직이어야 한다 — 어긋나면 측정과 실제
    동작이 갈린다.
    """
    out: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.add(str(value))
        elif isinstance(value, float):
            out.add(f"{value:g}")
            out.add(f"{abs(value) * 100:g}")
            out.add(f"{round(abs(value) * 100):g}")

    walk(metrics)
    return out


# 문장에서 뽑아낼 숫자. devtools/grade.py::_ANYNUM 과 같은 패턴.
_ANYNUM = re.compile(r"\d[\d,]*\.?\d*")


def _numbers_in(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _ANYNUM.finditer(text)}


def _ungrounded(text: str, metrics: dict) -> set[str]:
    """지표에 없는 숫자. devtools/grade.py::_ungrounded 와 같은 로직이어야 한다.

    한두 자리는 시각·인원 같은 실행 지시로 보고 통과시킨다 — 프롬프트가 허용한다.
    """
    allowed = _metric_numbers(metrics)
    bad = set()
    for number in _numbers_in(text):
        if number in allowed:
            continue
        try:  # 12.0 == 12 같은 표기 차이는 허용
            if any(abs(float(number) - float(a)) < 1e-9 for a in allowed):
                continue
        except ValueError:
            pass
        if len(number.split(".")[0]) <= 2:
            continue
        bad.add(number)
    return bad


def _metric_figures(text: str, metrics: dict) -> set[str]:
    """그 문장이 인용한 지표 수치. devtools/grade.py::_metric_figures 와 같은 로직."""
    allowed = _metric_numbers(metrics)
    used = {m.group().replace(",", "").rstrip("원% \t") for m in _DISPLAY_NUM.finditer(text)}
    return {n for n in used if n in allowed}


def _parse(raw: str, metrics: dict) -> tuple[list[SolutionCard] | None, set[str]]:
    """계약·ERD 를 만족하는 카드만 돌려준다. 한 장도 안 남으면 None 이라 재시도한다.

    카드별 길이·범위 제약(rankNo ≥ 1, title 200자)은 스키마가 본다. 여기서는 스키마가
    볼 수 없는 것만 본다 — rankNo 가 겹치면 BE 의 UNIQUE (solution_bundle_id, rank_no) 를
    위반해 묶음 전체가 저장되지 않고, 동형이의 문자는 타입상 멀쩡한 문자열이라 통과한다.

    2026-10-08: 위반 카드가 있으면 세 장을 통째로 버렸는데, 그러면 두 번 다 걸릴 때 500 이
    나간다. 실측에서 9 번 중 1 번이 그랬다(Claude 기준). 이 파일 아래 generate() 에
    "카드 2장이 나가는 것보다 500이 나가는 쪽이 점주에게 더 나쁘다"고 적어 둔 판단과
    어긋나서, 위반한 카드만 버리고 남은 걸 돌려준다. 재시도는 그대로 돈다 — 3 장을
    선호하는 건 변하지 않았고, 다만 재시도도 실패하면 빈손이 아니라 남은 카드가 나간다.

    2026-10-11: 위반 사유를 두 번째 값으로 같이 돌려준다. generate() 가 2회차 프롬프트에
    "방금 이 규칙을 어겼다"를 덧붙이는 데 쓴다(`solution_prompt.retry_feedback`) — 실측
    (n=15, Claude Sonnet 4.5)에서 재시도 3건 전부가 COMPUTED_RATIO 였는데, 2회차가 1회차와
    완전히 같은 프롬프트라 같은 종류의 위반이 또 나온 사례가 있었다.
    """
    try:
        data = json.loads(llm.strip_fence(raw))
        cards = [SolutionCard(**_normalize(card)) for card in data["solutionCards"]]
    except Exception:
        return None, set()

    if not 1 <= len(cards) <= MAX_CARDS:
        return None, set()
    ranks = [card.rankNo for card in cards]
    if len(set(ranks)) != len(ranks):
        # 어느 쪽이 맞는 순위인지 알 수 없어 버린다 — 둘 다 남기면 BE 저장이 깨진다.
        return None, set()

    reasons: set[str] = set()
    kept: list[SolutionCard] = []
    for card in cards:
        violations = _violations(card, metrics)
        if violations:
            reasons.update(violations)
        else:
            kept.append(card)
    if not kept:
        return None, reasons
    # 중간이 빠지면 rankNo 가 1·3 으로 나간다. 장수가 줄어드는 경우(배정 지표가 2 종일 때)
    # 는 늘 1·2 였으므로 연속성을 유지한다 — FE 가 번호를 그대로 쓰는지 확인된 바 없다.
    for index, card in enumerate(kept, start=1):
        card.rankNo = index
    return kept, reasons


_TEXT_FIELDS = ("title", "summaryText", "detailText", "evidence")


def _normalize(card: dict) -> dict:
    """화면에 나가는 텍스트를 다듬는다. 지금은 시각 표기 하나뿐이다."""
    return {
        key: to_24h(value) if key in _TEXT_FIELDS and isinstance(value, str) else value
        for key, value in card.items()
    }


def _violations(card: SolutionCard, metrics: dict) -> list[str]:
    """재시도로 보낼 이유. 비어 있으면 통과다. _normalize 를 거친 카드를 받는다.

    여섯 다 프롬프트에 규칙이 있는데 지켜지지 않는 것들이고, 치환으로는 못 고친다.
    시각은 대부분 _normalize 가 치환하지만("오후 2시" → "14시") 뜻이 정해지지 않는
    것들이 남는다("낮 7시") — 틀리게 바꾸느니 재시도가 낫다.
    """
    texts = (card.title, card.summaryText, card.detailText, card.evidence or "")
    reasons = []
    if _foreign_chars(card):
        reasons.append("FOREIGN_CHAR")
    if any(_ROUNDED_AMOUNT.search(text) for text in texts):
        reasons.append("ROUNDED_AMOUNT")
    if _ungrounded_ratios(texts, metrics):
        reasons.append("COMPUTED_RATIO")
    # 지표에 없는 금액을 지어내는 것 — 가장 위험한 종류다. 2026-10-16 배포본에서
    # "남은 시간 동안 253,196원을 추가로 만들어야 합니다"가 나왔다(255,396 - 2,200 을
    # 모델이 계산했다). 채점기에는 있었는데 서비스에는 없어서 그대로 나갔고, 채점기도
    # title·summaryText 는 안 봐서 측정에서는 100% 로 보였다.
    if any(_ungrounded(text, metrics) for text in texts):
        reasons.append("UNGROUNDED_NUMBER")
    if any(_AMPM_LEFT.search(text) for text in texts):
        reasons.append("AMPM_LEFT")
    if any(_VAGUE_PERIOD.search(text) for text in texts):
        reasons.append("VAGUE_PERIOD")

    # summaryText 가 쓴 지표 수치를 title·detailText 가 다시 쓰면 안 된다(_USER 105~109줄).
    # evidence 는 화면에 안 보여서 예외다(2026-10-02 FE 확정). devtools/grade.py::_fields_disjoint
    # 와 같은 로직.
    figure_groups = [
        _metric_figures(card.title, metrics),
        _metric_figures(card.summaryText, metrics),
        _metric_figures(card.detailText, metrics),
    ]
    if any(
        figure_groups[i] & figure_groups[j]
        for i in range(len(figure_groups))
        for j in range(i + 1, len(figure_groups))
    ):
        reasons.append("DUPLICATE_FIGURE")

    # 누구나 할 수 있는 말("마케팅을 강화하세요") — 기대효과 문장(detailText 마지막 줄)은
    # 정성적 표현이 허용이라 보지 않는다(_USER 122~126줄). devtools/grade.py::_VAGUE_ACTION
    # 과 같은 범위(title + detailText 앞 두 줄).
    action_lines = [card.title, *card.detailText.split("\n")[:2]]
    if any(_VAGUE_ACTION.search(line) for line in action_lines):
        reasons.append("VAGUE_ACTION")

    return reasons


def _foreign_chars(card: SolutionCard) -> set[str]:
    """카드 텍스트에 섞인 한글·라틴 밖 글자. 비어 있으면 정상이다."""
    texts = (card.title, card.summaryText, card.detailText, card.evidence or "")
    return {ch for text in texts for ch in text if ch.isalpha() and not _HANGUL_OR_LATIN.match(ch)}


async def generate(req: SolutionRequest) -> SolutionResponse:
    day_of_week, is_weekend = _day_facts(req.targetDate)
    # exclude_none: 값이 없는 지표(이전 기간 비교가 없는 첫 업로드 등)는 프롬프트에서 뺀다.
    metrics = req.metrics.model_dump(exclude_none=True)
    # 코드가 먼저 계산해 둔다. 모델이 직접 계산하지 않아도 되고, _violations 도 같은
    # 값을 봐야 "지표에 있는 배율" 을 날조로 거부하지 않는다.
    metrics = derive_metrics(metrics)
    # 카드마다 쓸 근거 지표를 코드가 배정한다 — 모델이 고르게 두면 같은 지표로 두 장을
    # 만든다(실측 10 번 중 4 번). app/services/solution_focus.py 참고.
    focus = assign_focus(metrics)
    period = req.metrics.salesSummary.period
    base_prompt = solution_prompt.build(focus, req.targetDate, day_of_week, is_weekend, period)

    # 3장을 선호하되, 모자란 응답이라고 버리지는 않는다. 카드 2장이 나가는 것보다
    # 500 이 나가는 쪽이 점주에게 더 나쁘다 — 그날 솔루션이 아예 없어진다.
    wanted = len(focus) or MAX_CARDS
    cards = None
    reasons: set[str] = set()
    for attempt in range(MAX_RETRY + 1):
        # 2026-10-11: 2회차부터는 1회차가 어긴 규칙을 프롬프트에 덧붙인다. 전에는
        # 1·2회차가 완전히 같은 프롬프트라 같은 종류의 위반이 반복될 수 있었다.
        prompt = base_prompt + (solution_prompt.retry_feedback(reasons) if attempt else "")
        parsed, reasons = _parse(await llm.complete(solution_prompt.SYSTEM, prompt), metrics)
        # 더 많이 남은 쪽을 쥔다. `parsed or cards` 로 두면 2 장을 받아둔 뒤 재시도가
        # 1 장을 주면 더 나쁜 쪽으로 덮어쓴다.
        if parsed and (cards is None or len(parsed) > len(cards)):
            cards = parsed
        if cards and len(cards) == wanted:
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
