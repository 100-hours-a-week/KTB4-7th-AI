"""메뉴판 이미지 인식 — OCR(클로바) 로 텍스트를 읽고, 텍스트 LLM 으로 카테고리를 분류한다.

짝짓기(이름-가격 연결) 로직 v1(2026-10-13, 실제 메뉴판 3장으로 검증):

1. **열(column) 분리** — 클로바는 토큰을 대략 y좌표 순서로 돌려줘서, 2열 이상
   메뉴판에서는 왼쪽·오른쪽 열의 줄이 섞여서 온다(`AMENU 오른쪽 헤더` 다음에
   `왼쪽 열 가격`이 오는 식). x좌표로 줄을 열 단위로 나눠 각 열을 독립적으로 처리한다.
2. **"메뉴명답게 생긴" 줄을 점수로 고른다** — "가격 바로 앞 줄"(v0)을 이름으로 삼으면
   설명문이 이름 자리를 덮어쓰고, 반대로 "블록의 첫 줄"로 고정하면 메뉴판 맨 위
   상호명·섹션 헤더(THE/COMMA/MENU/COFFEE 등 전부 영문 대문자라 메뉴명과 구분이 안
   됨)가 첫 자리를 차지해버린다(둘 다 실측에서 확인 — 2026-10-13). 그래서 괄호
   `(hot/ice)` 포함 여부·영문 포함 여부·길이로 "메뉴명답게 생긴 정도"를 점수로 매겨,
   블록 안에서 점수가 가장 높은 줄을 이름으로 쓴다(`_name_candidate_score`). 길고
   괄호·영문이 전혀 없는 순(純) 한국어 문장은 설명문일 가능성이 높다고 보고 감점한다.

두 수정 다 `docs/superpowers/specs/2026-10-12-menu-recognition-design.md` "메뉴명-가격
짝짓기" 절의 실측 근거를 따른다. 그래도 100%는 아니다 — 묶기가 애매하면
`priceReviewRequired=true`로 떨어뜨려 점주 검토로 넘기는 게 2차 방어선이다.

2026-10-14: `_name_candidate_score`의 영문 대문자 가산을 한글 포함 가산으로 바꿨다.
실제 메뉴판 3장 전부 큰 글씨(주 메뉴명)가 한글이고 영문은 작은 보조 표기였는데,
영문 가산 때문에 "아메리카노" 대신 "AMERICANO"를 메뉴명으로 고르는 사고가 있었다
(사용자 확인). `tests/fixtures/menu/`·`devtools/menu_recognition_eval.py`로 실제
BE가 받을 JSON 기준 정확도를 측정한다.

2026-10-14(2): 열 분리를 "이름 있는 줄만으로 경계를 정하고 모든 줄을 재배정"하는
식으로 더 정교하게 바꿔보려 했으나(중앙값 배수, 비율과의 조합 등 여러 버전 시도),
더콤마(열 간격이 촘촘해 비율 기준이 아슬아슬함)와 여름(장식 줄이 열 사이 간격을
쪼갬)을 동시에 만족하는 공식을 못 찾았고, 오히려 더콤마 가격 정확도가 88%→7%까지
떨어지는 회귀가 실측으로 확인됐다. 원래 방식(열 분리 로직 자체)은 그대로 두고,
**"줄 전부가 가격뿐인 열"만 사후에 가장 가까운 열로 합치는** 좁은 수정으로
바꿨다(`_merge_price_only_columns`) — 아드프의 실제 문제가 열 분리 자체가 아니라
가격 혼자 떨어져 나가 가짜 열을 만든 것뿐이었기 때문이다. 이 좁은 수정만으로
아드프가 재현율 59%→100%, 가격 정확도 100%까지 오르면서 더콤마·여름은 그대로
유지됐다(실측 확인, 전체 재현율 67%→75%, 가격 92%→93%). 교훈: 범용 공식을 다시
설계하기보다, 실패 사례 하나에 정확히 대응하는 좁은 수정이 더 안전하다.

2026-10-14(3): 더콤마 재현율이 여전히 67%로 낮아 원인을 다시 봤다 — 클로바가 같은
열의 가격 16개를 **이름 없이 연달아** 돌려주는 구간이 있었다(실측 확인, TEA·
SMOOTHIE 섹션). 순서 기반 짝짓기는 버퍼가 하나뿐이라 첫 번째만 짝짓고 나머지
15개는 버렸다 — 이름이 사라진 게 아니라 딴 곳에 있는데 순서가 꼬여서 못 찾을
뿐이었다. 그래서 `_extract_pairs_in_column`을 2단계로 바꿨다: 1차(순서 기반)에서
밀려난 이름 후보·짝 못 찾은 가격을 버리지 않고 모아뒀다가, 2차로 `_rematch_by_y`가
y좌표(세로 위치) 최근접으로 다시 묶는다. 순서가 아니라 좌표로 묶는 거라 1차보다
신뢰도가 낮아 2차 매칭 결과는 항상 `priceReviewRequired=true`로 둔다. 결과:
더콤마 재현율 67%→**94%**, 전체 재현율 75%→**93%**, 가격 정확도 91%, 카테고리
88%(실측 확인, 회귀 없음).

2026-10-14(4) — 보류: 더콤마만 가격 정확도가 85%로 다른 두 메뉴판(100%)보다 낮다.
원인은 찾았다 — "성공한 구간은 밀려난 후보를 버린다"는 (3)의 규칙이, 가격 없이
**다른 품목** 이름이 끼어든 구간(예: "자몽허니블랙티" 바로 뒤에 가격 없이
"연유라떼"가 이어짐)까지 통째로 지워서 진짜 놓친 항목을 같이 날렸다. 밀려난 후보
수가 1개 초과면 구간을 보존하도록 고쳤지만(`_MAX_NORMAL_CYCLE_BUMP`), **수치
변화가 전혀 없었다**(94%/85%/88% 그대로, 환각 품목 이름만 바뀜) — 보존된 구간
안에 "진짜 놓친 항목"과 "이미 처리된 품목의 중복 언어 표기"가 같이 섞여 있어서,
구간째로 살리는 것만으로는 둘을 못 가른다. 하나만 골라내려면 "이 두 줄이 같은
품목의 번역 관계인지" 판단하는 로직이 필요한데, 지금 가진 신호(좌표·점수)로는
안 된다 — 사용자 판단으로 지금은 보류, 추후 고도화 과제로 남긴다.
"""

import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass

from app.clients import llm, ocr
from app.clients.ocr import OcrToken
from app.core.errors import ApiError
from app.prompts import menu as menu_prompt
from app.schemas.menu import (
    DetectedMenuItem,
    FailedImage,
    MenuImageInput,
    MenuRecognitionData,
    MenuRecognitionRequest,
)

_PRICE_COMMA = re.compile(r"^\d{1,3}(,\d{3})+$")
_PRICE_SHORTHAND = re.compile(r"^\d{1,2}\.\d$")
_JUNK_PREFIX = re.compile(r"^[.·\-/\s]+")
_HAS_PAREN = re.compile(r"[()]")
_HAS_HANGUL = re.compile(r"[가-힣]")

# x좌표 전체 폭의 이 비율보다 큰 간격이 있으면 거기서 열을 나눈다. 실측(2026-10-13,
# 메뉴판 3장)으로 고른 값 — 1열 메뉴판은 간격이 이보다 작아 한 묶음으로 남는다.
#
# 2026-10-14: 이 기준을 "이름이 있는 줄만" 또는 "중앙값 배수"로 바꿔보려 했으나
# 더콤마(촘촘한 6열)·여름(장식 줄이 간격을 쪼갬) 둘 다 만족하는 단일 공식을 못
# 찾았다 — 한쪽을 고치면 다른 쪽이 깨졌다(실측 확인, 더콤마 가격 정확도가 88%→7%
# 까지 떨어짐). 그래서 **원래 방식(전체 줄 기준 비율)은 그대로 두고**, "가격만
# 있는 열"만 사후에 가장 가까운 열로 합치는 쪽으로 범위를 좁혔다 — 아래
# `_merge_price_only_columns` 참고. 열 분리 자체는 더콤마에서만 의미가 있었고
# (여름은 1열로 처리해도 "메뉴명답게 생긴" 점수 규칙이 알아서 올바르게 짝지었다 —
# 실측 확인), 아드프의 문제는 애초에 열이 아니라 가격 전용 줄이 좌표상 멀어 보여서
# 생긴 가짜 열이었다.
_COLUMN_GAP_RATIO = 0.2

# 가격과 성공적으로 짝지어진 구간에서 밀려난 후보 수가 이 값 이하면 "같은 품목의
# 다른 언어 표기" 정도로 보고 버린다. 이보다 많으면 가격 없이 다른 품목 이름이
# 끼어든 것으로 보고 버리지 않는다(2026-10-14 실측, 더콤마 참고).
_MAX_NORMAL_CYCLE_BUMP = 1


@dataclass(frozen=True)
class RawPair:
    name: str
    price: int | None
    price_ambiguous: bool


@dataclass(frozen=True)
class Line:
    index: int  # 원래 순서(대략 위→아래) — 열로 나눈 뒤 다시 이 순서로 정렬한다
    text: str
    center_x: float
    center_y: float


def group_lines(tokens: list[OcrToken]) -> list[Line]:
    """`line_break` 가 true 인 토큰까지를 한 줄로 묶는다."""
    lines: list[Line] = []
    current: list[OcrToken] = []

    def _flush() -> None:
        if not current:
            return
        xs = [v.x for t in current for v in t.vertices]
        ys = [v.y for t in current for v in t.vertices]
        lines.append(
            Line(
                index=len(lines),
                text=" ".join(t.text for t in current),
                center_x=(min(xs) + max(xs)) / 2,
                center_y=(min(ys) + max(ys)) / 2,
            )
        )

    for token in tokens:
        current.append(token)
        if token.line_break:
            _flush()
            current = []
    _flush()
    return lines


def _is_price_only(text: str) -> bool:
    found = _find_price_in_line(text)
    return found is not None and not found[2]  # remainder 가 비어 있으면 가격만 있는 줄


def _merge_price_only_columns(columns: list[list[Line]]) -> list[list[Line]]:
    """이름이 하나도 없이 가격만 있는 열을, 가장 가까운(x좌표) 다른 열로 합친다.

    표준 가격이 오른쪽으로 더 정렬돼 있어서 이름 줄과 x좌표가 멀어 보이는 경우
    생기는 가짜 열이다(2026-10-14 실측, 아드프 — "아메리카노 Americano /"는
    x≈288인데 그 가격 "4.3"은 x≈405라 별도 열로 갈라져서, 가격만 있는 열에 이름이
    하나도 없어 전부 버려졌다). 열이 하나뿐이면 합칠 대상이 없어 그대로 둔다.
    """
    if len(columns) <= 1:
        return columns
    price_only_idx = [
        i for i, col in enumerate(columns) if col and all(_is_price_only(line.text) for line in col)
    ]
    if not price_only_idx:
        return columns
    real_idx = [i for i in range(len(columns)) if i not in price_only_idx]
    if not real_idx:
        return columns  # 전부 가격만 있는 열이면(있을 수 없지만) 손대지 않는다

    def _center(col: list[Line]) -> float:
        return sum(line.center_x for line in col) / len(col)

    real_centers = {i: _center(columns[i]) for i in real_idx}
    merged = {i: list(columns[i]) for i in real_idx}
    for i in price_only_idx:
        target = min(real_idx, key=lambda r: abs(real_centers[r] - _center(columns[i])))
        merged[target].extend(columns[i])
    return [sorted(merged[i], key=lambda line: line.index) for i in real_idx]


def cluster_columns(lines: list[Line]) -> list[list[Line]]:
    """줄을 x좌표로 열 단위로 나눈다. 뚜렷한 간격이 없으면 한 열로 묶인다.

    각 열 안에서는 원래 순서(`index`, 위→아래)로 다시 정렬해 읽기 순서를 보존한다.
    """
    if len(lines) <= 1:
        return [lines]
    by_x = sorted(lines, key=lambda line: line.center_x)
    total_range = by_x[-1].center_x - by_x[0].center_x
    if total_range == 0:
        return [lines]
    threshold = total_range * _COLUMN_GAP_RATIO
    split_at = [
        i + 1 for i in range(len(by_x) - 1) if by_x[i + 1].center_x - by_x[i].center_x > threshold
    ]
    if not split_at:
        return [lines]
    columns, start = [], 0
    for pos in split_at:
        columns.append(by_x[start:pos])
        start = pos
    columns.append(by_x[start:])
    columns = [sorted(col, key=lambda line: line.index) for col in columns]
    return _merge_price_only_columns(columns)


def _parse_price(token: str) -> tuple[int, bool] | None:
    if token.startswith("+"):
        return None  # 옵션 추가 요금(예: +500) — 메뉴 자체 가격이 아니다
    stripped = token.rstrip("원₩")
    if _PRICE_COMMA.match(stripped):
        return int(stripped.replace(",", "")), False
    if _PRICE_SHORTHAND.match(stripped):
        # "6.0" 같은 천원 단위 축약 표기 — 실제로 그런지 확신할 수 없어 항상 모호로 둔다.
        return round(float(stripped) * 1000), True
    return None


def _find_price_in_line(text: str) -> tuple[int, bool, str] | None:
    """줄 끝에서부터 가격 토큰을 찾는다. 찾으면 (가격, 모호여부, 가격 제외한 나머지)."""
    words = text.split()
    for i in range(len(words) - 1, max(-1, len(words) - 3), -1):
        candidate = _JUNK_PREFIX.sub("", words[i])
        parsed = _parse_price(candidate)
        if parsed is None:
            continue
        price, ambiguous = parsed
        remainder = " ".join(words[:i] + words[i + 1 :]).strip(" ./-·")
        return price, ambiguous, remainder
    return None


def _name_candidate_score(text: str) -> float:
    """ "메뉴명답게 생긴 정도" 점수. 높을수록 이름 후보로 더 적합하다.

    `(hot/ice)` 같은 괄호가 있으면 가산. 한글 포함이면 가산 — 실제 메뉴판 3장
    전부 큰 글씨(주 메뉴명)가 한글이고 영문은 작은 보조 표기였다(2026-10-14
    사용자 확인). 영문 대문자 가산은 뺐다 — "AMERICANO"처럼 작은 보조 영문
    표기를 "아메리카노"보다 메뉴명으로 잘못 고르는 사고가 있었다(실측 확인).
    길고 괄호가 없는 문장은 설명문일 가능성이 높아 감점한다(한글 여부와 무관 —
    "무스카트와 프랑스 향이 어우러진 디카페인 홍차" 같은 문장도 한글이다).
    """
    score = 0.0
    has_paren = bool(_HAS_PAREN.search(text))
    has_hangul = bool(_HAS_HANGUL.search(text))
    if has_paren:
        score += 2
    if has_hangul:
        score += 1
    length = len(text)
    if 2 <= length <= 30:
        score += 1
    if length > 20 and not has_paren:
        score -= 3
    return score


def _extract_pairs_in_column(lines: list[Line]) -> list[RawPair]:
    """1차: 순서 기반 짝짓기. 밀려난 이름 후보·짝 못 찾은 가격은 버리지 않고
    `_rematch_by_y`(2차)로 넘긴다 — 아래 함수 설명 참고.

    단, **그 구간이 가격과 성공적으로 짝지어지면** 그 구간에서 밀려난 후보는
    버린다(2차 풀에 안 넘긴다) — 같은 품목의 다른 언어 표기(예: "아메리카노"가
    짝지어지면 밀려난 "AMERICANO")일 뿐이라서, 그대로 두면 2차 매칭 때 이미 처리된
    품목의 중복이 엉뚱한 가격을 또 주워가거나(환각) 진짜 놓친 품목을 밀어낸다
    (2026-10-14 실측 확인 — 더콤마 환각 "HONEYDEW MELON LATTE" 등이 이 경로였다).
    """
    pairs: list[RawPair] = []
    pending: Line | None = None
    pending_score = float("-inf")
    cycle_bumped: list[Line] = []  # 현재 이름 수집 구간에서 밀려난 후보
    unmatched_names: list[Line] = []
    unmatched_prices: list[tuple[Line, int, bool]] = []

    for line in lines:
        found = _find_price_in_line(line.text)
        if found is None:
            stripped = line.text.strip()
            if not stripped:
                continue
            score = _name_candidate_score(stripped)
            # 동점이면 더 뒤(가격에 가까운) 줄을 쓴다 — 같은 상호명 헤더가
            # 연달아 나오는 경우 가장 마지막(실제 품목에 가장 가까운) 것이
            # 보통 맞다. 더 높은 점수가 나오면 그게 먼저든 나중이든 우선한다.
            if score >= pending_score:
                if pending is not None:
                    cycle_bumped.append(pending)
                pending, pending_score = line, score
            else:
                cycle_bumped.append(line)
            continue
        price, ambiguous, remainder = found
        if remainder:
            pairs.append(RawPair(name=remainder, price=price, price_ambiguous=ambiguous))
        elif pending is not None:
            pairs.append(RawPair(name=pending.text.strip(), price=price, price_ambiguous=ambiguous))
            pending, pending_score = None, float("-inf")
            # 밀려난 후보가 1개 이하(같은 품목의 다른 언어 표기 정도)면 정상적인 한
            # 품목 처리로 보고 버린다. 2개 이상이면 가격 없이 다른 품목 이름이
            # 끼어들었다는 뜻이라(2026-10-14 실측 — "자몽허니블랙티" 바로 뒤에
            # 가격 없이 "연유라떼"가 와서 밀려났다) 섣불리 버리지 않고 2차로 넘긴다.
            if len(cycle_bumped) <= _MAX_NORMAL_CYCLE_BUMP:
                cycle_bumped = []
            else:
                unmatched_names.extend(cycle_bumped)
                cycle_bumped = []
        else:
            unmatched_prices.append((line, price, ambiguous))
            unmatched_names.extend(cycle_bumped)  # 못 푼 구간은 전부 보존
            cycle_bumped = []

    unmatched_names.extend(cycle_bumped)
    if pending is not None:
        unmatched_names.append(pending)

    pairs.extend(_rematch_by_y(unmatched_names, unmatched_prices))
    return pairs


def _rematch_by_y(
    unmatched_names: list[Line], unmatched_prices: list[tuple[Line, int, bool]]
) -> list[RawPair]:
    """2차: 순서 기반 매칭에서 못 쓴 이름·가격을 y좌표(세로 위치) 최근접으로 묶는다.

    클로바가 같은 열의 가격 여러 개를 이름 없이 연달아 몰아서 반환하는 경우가
    있다(2026-10-14 실측, 더콤마 — 가격 16개가 이름 한 줄 없이 연속으로 나와서
    1차 순서 기반 매칭으로는 첫 번째만 짝짓고 나머지 15개를 버렸다). 이름들은
    보통 딴 곳에 있을 뿐 사라진 게 아니라서, y좌표가 가장 가까운 것끼리 사후에
    다시 묶는다. 순서가 아니라 좌표로 묶는 것이라 1차보다 신뢰도가 낮으므로
    `price_ambiguous`를 항상 true로 둔다(검토 대상으로 표시).
    """
    pairs: list[RawPair] = []
    used: set[int] = set()
    for price_line, price, _ in sorted(unmatched_prices, key=lambda p: p[0].center_y):
        best_idx, best_dist = None, float("inf")
        for i, cand in enumerate(unmatched_names):
            if i in used:
                continue
            dist = abs(cand.center_y - price_line.center_y)
            if dist < best_dist:
                best_dist, best_idx = dist, i
        if best_idx is None:
            continue
        used.add(best_idx)
        pairs.append(
            RawPair(name=unmatched_names[best_idx].text.strip(), price=price, price_ambiguous=True)
        )
    return pairs


def extract_raw_pairs(lines: list[Line]) -> list[RawPair]:
    """줄 목록에서 메뉴명-가격 후보를 뽑는다. 열을 먼저 나누고 열별로 처리한다.

    이름 후보가 없는 가격은 버린다(추측해서 아무 이름이나 붙이지 않는다).
    """
    pairs: list[RawPair] = []
    for column in cluster_columns(lines):
        pairs.extend(_extract_pairs_in_column(column))
    return pairs


async def classify_categories(names: list[str]) -> list[str | None]:
    """메뉴명 목록을 6종 카테고리로 분류한다.

    판별 불가(응답 파싱 실패, 허용 범위 밖 값)는 `null`로 둔다 — OTHER는 "6종 중
    하나로 확정됐지만 그게 OTHER"인 경우에만 쓰는 값이라 둘을 섞지 않는다
    (2026-10-14 노션 ST-04 확인).
    """
    if not names:
        return []
    raw = await llm.complete(menu_prompt.SYSTEM, menu_prompt.build(names), max_tokens=1000)
    try:
        parsed = json.loads(llm.strip_fence(raw))
        categories = parsed["categories"]
        if len(categories) != len(names):
            raise ValueError("개수가 안 맞음")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return [None] * len(names)
    allowed = {"COFFEE", "TEA", "BEVERAGE", "CAKE", "BAKERY", "OTHER"}
    return [c if c in allowed else None for c in categories]


def _assemble_items(
    source_image_id: int, pairs: list[RawPair], categories: list[str | None]
) -> list[DetectedMenuItem]:
    items = []
    for pair, category in zip(pairs, categories, strict=True):
        name = pair.name.strip()
        if not name:
            continue
        price = pair.price
        price_review_required = pair.price_ambiguous
        # ERD menu_image_items.detected_price 제약(0~1,000,000) 밖이면 추측하지 않고
        # null + 검토 요청으로 보정한다(AGENTS.md "금액 어림 계산 거부"와 같은 원칙).
        if price is not None and not (0 <= price <= 1_000_000):
            price = None
            price_review_required = True
        # confidence는 실제 확률이 아니라 검토 우선순위 휴리스틱이다(스펙 "3. 신뢰도
        # 계산" 참고) — 감점 폭은 임시값, devtools 평가 결과로 조정한다.
        confidence = 0.6 if price_review_required else 0.95
        items.append(
            DetectedMenuItem(
                sourceImageId=source_image_id,
                name=name[:100],
                category=category,
                price=price,
                confidence=confidence,
                priceReviewRequired=price_review_required,
            )
        )
    return items


async def build_detected_items(
    source_image_id: int, tokens: list[OcrToken]
) -> list[DetectedMenuItem]:
    """한 이미지의 OCR 토큰을 실제 계약 응답 형태(`DetectedMenuItem`)로 조립한다.

    `POST /internal/v2/ai/menu-recognition` 응답의 `detectedItems`에 그대로 들어가는
    형태다 — BE가 받는 JSON과 동일한 구조로 평가(`devtools/menu_recognition_eval.py`)
    할 수 있게 한다. 배치 전체를 처리하는 `recognize_menu`는 카테고리 분류를 이미지
    단위로 쪼개 부르지 않는다(아래 참고) — 이 함수는 사진 1장만 볼 때(devtools 평가)
    쓰는 편의 함수로 남긴다.
    """
    lines = group_lines(tokens)
    pairs = extract_raw_pairs(lines)
    categories = await classify_categories([p.name for p in pairs])
    return _assemble_items(source_image_id, pairs, categories)


# 스펙 "5. 동시 처리와 재시도" — 공급자 호출 한도·429에 취약해 무제한 동시 호출을 하지
# 않는다. 실측 전 임시값.
_OCR_CONCURRENCY = 2

# OCR은 성공했지만 결과가 흐려 신뢰할 수 없는 수준인지 판단하는 임시 기준. 계약에 값으로
# 박혀있지 않다(스펙 "BE에 확인할 것" 1번 — 아직 미확정) — 토큰 평균 신뢰도가 이 값보다
# 낮으면 LOW_IMAGE_QUALITY, 토큰 자체가 없으면 MENU_TEXT_NOT_FOUND로 가른다.
_LOW_IMAGE_QUALITY_CONFIDENCE = 0.3


def _classify_content_failure(tokens: list[OcrToken]) -> str:
    """OCR 공급자 장애가 아닌, 콘텐츠 문제로 후보를 못 뽑았을 때 실패 사유를 고른다.

    시스템 오류(OCR 공급자 타임아웃/5xx)는 호출부가 `ApiError`를 잡아 바로
    AI_PROCESSING_ERROR로 분류하므로 여기 들어오지 않는다.
    """
    if not tokens:
        return "MENU_TEXT_NOT_FOUND"
    avg_confidence = sum(t.confidence for t in tokens) / len(tokens)
    if avg_confidence < _LOW_IMAGE_QUALITY_CONFIDENCE:
        return "LOW_IMAGE_QUALITY"
    return "MENU_TEXT_NOT_FOUND"


def _majority_fail_reason(reasons: list[str]) -> str:
    """배치 전체가 실패했을 때 최상위 `failReason`을 다수결로 정한다.

    동률이면 LOW_IMAGE_QUALITY 우선(스펙 "6. 배치 처리와 부분 실패" 임시 규칙, 실측 후
    조정 가능).
    """
    counts = Counter(reasons)
    top = max(counts.values())
    tied = [reason for reason, count in counts.items() if count == top]
    return "LOW_IMAGE_QUALITY" if "LOW_IMAGE_QUALITY" in tied else tied[0]


async def _ocr_one(
    image: MenuImageInput, semaphore: asyncio.Semaphore
) -> tuple[MenuImageInput, list[OcrToken], str | None]:
    """이미지 한 장을 OCR 처리한다. 공급자 오류는 그 이미지만의 실패로 담아 돌려준다

    (배치 전체를 500으로 떨어뜨리지 않는다 — 스펙 "6. 배치 처리와 부분 실패"). OCR
    클라이언트의 `_call_clova`가 이미 429·5xx에 한해 1회 재시도하므로, 여기서 잡히는
    `ApiError`는 그 재시도까지 실패한 뒤다.
    """
    async with semaphore:
        try:
            tokens = await ocr.extract_text_blocks(image.imageUrl)
        except ApiError:
            return image, [], "AI_PROCESSING_ERROR"
    return image, tokens, None


async def recognize_menu(req: MenuRecognitionRequest) -> MenuRecognitionData:
    """`POST /internal/v2/ai/menu-recognition` 배치 오케스트레이션.

    이미지별 OCR은 세마포어로 동시성을 제한한다(스펙 5번). 카테고리 분류는 배치 전체
    메뉴명을 모아 한 번만 호출한다 — LLM 재시도 1회 제한·비용 때문에 이미지마다 따로
    부르지 않는다(스펙 4번, `AGENTS.md` "LLM 재시도는 1회로 제한").

    1장 이상 처리에 성공하면(실패해도 OK) 200을 반환하고, 전부 실패하면 422 + 최상위
    `failReason`을 올린다. OCR 공급자 장애로 그 이미지만 실패한 경우는 여기서 잡아
    `failedImages`로 담는다 — 그 밖의 예상 못 한 예외(설정 오류 등 배치 자체를 시도조차
    못 하는 경우)는 잡지 않고 그대로 전파해 공용 500 핸들러가 받게 한다.
    """
    semaphore = asyncio.Semaphore(_OCR_CONCURRENCY)
    results = await asyncio.gather(*(_ocr_one(image, semaphore) for image in req.images))

    failed_images: list[FailedImage] = []
    per_image_pairs: list[tuple[int, list[RawPair]]] = []
    for image, tokens, fail_reason in results:
        if fail_reason is not None:
            failed_images.append(FailedImage(sourceImageId=image.imageId, failReason=fail_reason))
            continue
        pairs = extract_raw_pairs(group_lines(tokens))
        if not pairs:
            failed_images.append(
                FailedImage(
                    sourceImageId=image.imageId, failReason=_classify_content_failure(tokens)
                )
            )
            continue
        per_image_pairs.append((image.imageId, pairs))

    all_names = [pair.name for _, pairs in per_image_pairs for pair in pairs]
    categories = await classify_categories(all_names)

    detected_items: list[DetectedMenuItem] = []
    offset = 0
    for source_image_id, pairs in per_image_pairs:
        item_categories = categories[offset : offset + len(pairs)]
        offset += len(pairs)
        detected_items.extend(_assemble_items(source_image_id, pairs, item_categories))

    if not detected_items:
        reason = _majority_fail_reason([f.failReason for f in failed_images])
        raise ApiError(422, "MENU_RECOGNITION_FAILED", "메뉴를 인식하지 못했습니다.", reason)

    return MenuRecognitionData(detectedItems=detected_items, failedImages=failed_images)
