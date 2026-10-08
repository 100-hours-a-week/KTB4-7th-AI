"""프롬프트가 요구하는 규칙을 코드로 검사한다 — 로컬 모델·프롬프트 변경 평가용.

왜 있나. 지난 열흘간 잡은 결함이 전부 *그럴듯한데 틀린* 출력이었다.
`0.042 → "4% 증가"`, ratio 분모 착각, 같은 금액 반복, `WEEKDAY` 를 "금요일"로 바꿔 쓰기 —
전부 눈으로는 정상이라 사람이 20번 읽어도 못 찾는다. pytest 는 목(mock)을 쓰므로
끝까지 초록이고, curl 한 번은 한 표본이라 70% 성공률을 100%로 착각하게 만든다.

쓰는 법. 같은 요청을 N 회 호출해 통과율을 본다. 개별 항목이 95% 여도 곱하면 확 떨어지므로
**모든 항목을 동시에 통과한 비율**이 출하 판정 숫자다.

주의. 여기 규칙은 프롬프트를 그대로 옮긴 것이라 프롬프트가 바뀌면 같이 썩는다. 실제로
2026-10-01(PR #115)에 솔루션 프롬프트가 재설계되면서 이 파일의 이전 판이 **폐기된 규칙을
계속 재고 있었다** — `수치_evidence만`(수치는 evidence 에만)은 그때 반대 방향으로 뒤집혔고
`detail_2문장`은 세 문장으로 바뀌었는데, 채점기는 몰라서 "Claude 가 규칙을 60% 어긴다"는
틀린 결론을 냈다. 그래서 tests/test_grade.py 가 TARGET_* 와 프롬프트 VERSION 이 어긋나면
실패한다 — 프롬프트를 고치면 이 파일을 같이 보게 강제한다.
"""

import json
import re

# app 패키지를 import 하지 않는다. Colab 에 이 파일 하나만 복사해서 쓰려면 anthropic·openai·
# google-genai 까지 깔아야 하는 상황을 만들면 안 된다. 대신 app/clients/llm.py 의 strip_fence
# 를 그대로 옮겨 두고, 둘이 어긋나면 tests/test_grade.py 가 잡는다.
_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_fence(raw: str) -> str:
    """모델이 JSON 을 ```json 펜스로 감싸 내려주는 경우가 있어 벗긴다(서비스와 동일)."""
    match = _FENCE.match(raw.strip())
    return match.group(1) if match else raw


# 이 채점기가 대조한 프롬프트 판. 프롬프트 VERSION 이 올라가면 규칙을 다시 읽고 여기도 올린다.
# 2026-10-08 은 규칙 문장을 하나도 바꾸지 않았다 — 고정 규칙과 지표의 순서만 바꿨고
# (접두 캐싱), 인사이트는 문장별 지표 배정이 추가됐다. 검사 항목은 손대지 않았다.
# 2026-10-07 은 입력 구조만 바뀌었고(카드별 근거 지표 배정) 카드 작성 규칙은 그대로라
# 검사 항목은 손대지 않았다. `카드_지표_중복없음` 이 100% 로 올라가는지 보는 게 이번 변경의
# 측정 목표다.
TARGET_SOLUTION_VERSION = "2026-10-08"
TARGET_INSIGHT_VERSION = "2026-10-08"

# 문장에서 뽑아낼 숫자 (쉼표 제거 후 비교한다)
_ANYNUM = re.compile(r"\d[\d,]*\.?\d*")
# "3만원", "1억2천만원" 처럼 만/억 단위로 줄여 쓴 금액 — 프롬프트가 금지한다.
# app/services/solution.py 의 _ROUNDED_AMOUNT 와 같은 패턴이다(tests 가 대조한다).
_ROUNDED = re.compile(r"\d[\d,]*\s*[억만][\d\s억만천백]*원")
# 12시간제 표기 — 프롬프트는 지표에 있는 24시간제를 그대로 쓰라고 한다
_AMPM = re.compile(r"(오전|오후|새벽|저녁|밤)\s*\d{1,2}\s*시")
# 배율은 직접 계산하지 말라고 되어 있다. 실호출에서 "7배"·"3분의 1" 날조가 나왔다.
_RATIO_WORD = re.compile(
    r"(?:\d+(?:\.\d+)?|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*배(?![달치송포분])"
    r"|\d+\s*분의\s*\d+"
)
# 화면에 보여줄 금액·비율. 실행 지시용 작은 수(21시, 1명)와 구분하려고 자릿수·단위를 본다.
_DISPLAY_NUM = re.compile(r"[\d,]{4,}\s*원|\d+\.?\d*\s*%")

# 행동의 "얼마나" — 지표에 없는 값이라 지어낸 것이다. 마진을 모르는데 할인율을,
# 인건비 대비 생산성을 모르는데 인원을 말할 근거가 없다(2026-10-07). 시각은 지표에
# hour 로 있으므로 _ungrounded 가 따로 본다.
_FABRICATED_AMOUNT = re.compile(
    r"\d+\s*%\s*(?:할인|세일|디스카운트|인하)"
    r"|(?:직원|인력|스태프|알바|인원)[을를]?\s*\d+\s*명"
    r"|\d+\s*명\s*(?:추가|배치|더|이상)"
    r"|\d+\s*(?:kg|키로|g|그램|잔|개|병|박스|리터)\s*[을를]?\s*(?:준비|발주|주문|구비|입고)"
)
# 누구나 할 수 있는 말. 점주가 오늘 무엇을 다르게 할지가 안 나온다.
_VAGUE_ACTION = re.compile(
    r"(?:마케팅|홍보|프로모션|캠페인|전략|활동|노력|서비스)[을를]?\s*"
    r"(?:강화|개선|변경|확대|진행|실행|집중)"
)

_DOW_KO = {
    "MONDAY": "월요일",
    "TUESDAY": "화요일",
    "WEDNESDAY": "수요일",
    "THURSDAY": "목요일",
    "FRIDAY": "금요일",
    "SATURDAY": "토요일",
    "SUNDAY": "일요일",
}


def _metric_numbers(metrics) -> set[str]:
    """지표에 실제로 있는 값들. 금액은 그대로, 비율은 백분율로도 인정한다."""
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
            out.add(f"{abs(value) * 100:g}")  # 0.417 → 41.7
            out.add(f"{round(abs(value) * 100):g}")  # 0.12  → 12

    walk(metrics)
    return out


def _numbers_in(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _ANYNUM.finditer(text)}


def _ungrounded(text: str, metrics) -> set[str]:
    """지표에 없는 숫자. 자릿수 오류·환각을 잡는다.

    한두 자리는 시각·인원·할인율 같은 실행 지시로 보고 통과시킨다 — 프롬프트가 허용한다.
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


def _metric_figures(text: str, metrics) -> set[str]:
    """그 문장이 인용한 '지표 수치'. 화면에 금액·비중으로 보이는 값만 센다.

    두 겹으로 거른다. 먼저 금액(네 자리 이상 + 원)과 백분율만 보고, 그중 지표에 실제로
    있는 값만 남긴다.

    - "21시까지"·"직원 1명"은 시각·인원이라 애초에 금액·비율이 아니다. 시각은 지표에도
      들어 있어서(hour: 14) 지표 포함 여부만으로는 거를 수 없다 — 단위를 같이 봐야 한다.
    - "10% 할인"은 백분율이지만 지표에 없는 값이라 실행 지시다.

    둘 다 프롬프트가 명시적으로 허용하는 표현이라 필드 간 중복 금지 대상이 아니다.
    """
    allowed = _metric_numbers(metrics)
    used = {m.group().replace(",", "").rstrip("원% \t") for m in _DISPLAY_NUM.finditer(text)}
    return {n for n in used if n in allowed}


def _label_hallucination(text: str, metrics) -> set[str]:
    """지표에 없는 요일 라벨. 숫자는 맞는데 차원이 틀리는 오류를 잡는다.

    실제로 `dayType: WEEKDAY` 를 "금요일"로 바꿔 쓴 출력이 나왔다. 숫자만 검증하면 통과한다.
    """
    allowed = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "dayOfWeek" and item in _DOW_KO:
                    allowed.add(_DOW_KO[item])
                elif key == "dayType":
                    allowed.add("평일" if item == "WEEKDAY" else "주말")
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(metrics)
    return {ko for ko in _DOW_KO.values() if ko in text} - allowed


def _metric_paths(metrics: dict) -> dict[str, set[str]]:
    """숫자 → 최상위 지표 키 역인덱스. 카드가 같은 지표를 두 번 인용했는지 보려고 쓴다."""
    out: dict[str, set[str]] = {}

    def walk(value, top):
        if isinstance(value, dict):
            for item in value.values():
                walk(item, top)
        elif isinstance(value, list):
            for item in value:
                walk(item, top)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int):
            out.setdefault(str(value), set()).add(top)
        elif isinstance(value, float):
            for text in (f"{value:g}", f"{abs(value) * 100:g}", f"{round(abs(value) * 100):g}"):
                out.setdefault(text, set()).add(top)

    for key, item in metrics.items():
        walk(item, key)
    return out


def _evidence_group(text: str, index: dict[str, set[str]]) -> set[str]:
    """그 문장이 근거로 삼은 지표 키. 여러 지표에 걸치는 숫자는 판단에 쓰지 않는다."""
    out: set[str] = set()
    for number in _numbers_in(text):
        keys = index.get(number, ())
        if len(keys) == 1:
            out |= set(keys)
    return out


# 서비스가 요청한 카드 수. 2026-10-07(#123) 부터 배정된 지표가 3 종이 안 되면 그만큼만
# 내보내므로, 호출부가 그 수를 넘겨야 한다. 3 으로 박아두면 설계대로 2 장을 낸 응답을
# 결함으로 센다 — 실제로 2026-10-08 측정에서 `카드3장` 66.7% 가 전부 그거였다.
MAX_CARDS = 3


def grade_solution(raw: str, metrics: dict, expected_cards: int = MAX_CARDS) -> dict:
    """솔루션 카드를 app/prompts/solution.py(2026-10-08) 기준으로 채점한다.

    expected_cards 는 서비스가 요청한 장수다(`len(assign_focus(metrics)) or 3`).
    """
    result: dict = {"parsed": False}
    try:
        cards = json.loads(strip_fence(raw))["solutionCards"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["parsed"] = True
    ranks = [c.get("rankNo") for c in cards]
    titles = [c.get("title") or "" for c in cards]
    summaries = [c.get("summaryText") or "" for c in cards]
    details = [c.get("detailText") or "" for c in cards]
    evidences = [c.get("evidence") or "" for c in cards]
    visible = titles + summaries + details  # evidence 는 화면에 안 나온다(2026-10-02 FE 확정)

    result["카드_개수_일치"] = len(cards) == expected_cards
    result["rankNo_고유"] = len(set(ranks)) == len(ranks)
    result["title_200자"] = all(len(t) <= 200 for t in titles)
    result["detail_1000자"] = all(len(d) <= 1000 for d in details)
    result["evidence_있음"] = all(e.strip() for e in evidences)

    # 실행 방법 두 문장 + 기대효과 한 문장 = 줄바꿈 2개 (2026-10-01 재설계)
    result["detail_3문장"] = all(d.count("\n") == 2 for d in details)

    # summaryText 가 쓴 지표 수치를 title·detailText 가 다시 쓰면 안 된다. evidence 는 예외.
    # 지표에 없는 수(시각·인원·할인율)는 실행 지시라 중복 대상이 아니다.
    def _fields_disjoint(card_index: int) -> bool:
        groups = [
            _metric_figures(titles[card_index], metrics),
            _metric_figures(summaries[card_index], metrics),
            _metric_figures(details[card_index], metrics),
        ]
        return all(
            not (groups[i] & groups[j])
            for i in range(len(groups))
            for j in range(i + 1, len(groups))
        )

    result["수치_필드간_중복없음"] = all(_fields_disjoint(i) for i in range(len(cards)))

    result["금액_어림_없음"] = not any(_ROUNDED.search(t) for t in visible + evidences)
    result["시각_24시간제"] = not any(_AMPM.search(t) for t in visible)
    result["배율_없음"] = not any(_RATIO_WORD.search(t) for t in visible)
    result["요일_환각_없음"] = not any(
        _label_hallucination(t, metrics) for t in visible + evidences
    )
    result["evidence_수치_정확"] = not any(_ungrounded(e, metrics) for e in evidences)
    result["detail_수치_정확"] = not any(_ungrounded(d, metrics) for d in details)

    # 기대효과(detailText 마지막 문장)는 정성적으로만 — "매출 15% 증가" 같은 날조 금지
    # 실행 문장(detailText 앞 두 문장)과 title 만 본다 — 기대효과 문장은 "매출을 늘릴 수
    # 있습니다" 가 허용이라 같은 잣대로 보면 오탐이 난다.
    actions = titles + [line for d in details for line in d.split("\n")[:2]]
    result["실행수치_날조_없음"] = not any(_FABRICATED_AMOUNT.search(t) for t in actions)
    result["공허한_조언_없음"] = not any(_VAGUE_ACTION.search(t) for t in actions)

    result["기대효과_정성적"] = not any(_DISPLAY_NUM.search(d.split("\n")[-1]) for d in details)

    # 카드끼리 같은 지표를 근거로 쓰면 "서로 다른 지표" 지시 위반이다. 문장이 달라도 중복이다.
    index = _metric_paths(metrics)
    groups = [_evidence_group(e, index) for e in evidences]
    result["카드_지표_중복없음"] = all(
        not (groups[i] & groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups))
    )

    result["cards"] = cards
    return result


def grade_insight(raw: str, metrics: dict) -> dict:
    """매출 인사이트를 app/prompts/insight.py(2026-09-23) 기준으로 채점한다."""
    result: dict = {"parsed": False}
    try:
        insights = json.loads(strip_fence(raw))["insights"]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    body = " ".join(insights)
    result["parsed"] = True
    result["개수_1_3"] = 1 <= len(insights) <= 3
    result["빈문장_없음"] = all(s.strip() for s in insights)
    result["100자_이내"] = all(len(s) <= 100 for s in insights)
    result["중복_없음"] = len(set(insights)) == len(insights)
    # "3주 연속 감소" 류 — 한 달치 스냅샷이라 연속성을 주장할 근거가 없다
    result["다주표현_없음"] = "연속" not in body
    # 관찰만 하고 처방하지 않는다. "~하세요"로 끝나면 처방이다.
    # 필요조건일 뿐이다 — "~하는 것이 좋습니다."는 "다."로 끝나지만 처방이다.
    result["관찰형_종결"] = all(s.rstrip().endswith("다.") for s in insights)
    result["금액_어림_없음"] = not _ROUNDED.search(body)
    result["수치_정확"] = not _ungrounded(body, metrics)
    result["요일_환각_없음"] = not _label_hallucination(body, metrics)

    # 비율 반올림 금지 — 0.042 는 4.2% 지 4% 가 아니다. 화면에서 티가 안 나 조용히 틀린다.
    ok = True
    changed = metrics["salesSummary"].get("vsPrevPeriod")
    if changed is not None:
        exact = f"{abs(changed) * 100:g}"
        rounded = f"{round(abs(changed) * 100):g}"
        if exact != rounded and f"{rounded}%" in body and f"{exact}%" not in body:
            ok = False
    result["비율_반올림_없음"] = ok

    # ratio 의 분모는 menuSales 다 — "전체의 OO%"·"총 매출의 OO%" 는 틀린 문장이다
    result["ratio_분모_정확"] = not re.search(r"(전체|총\s*매출)의\s*\d", body)

    result["insights"] = insights
    return result
