"""솔루션 카드 생성에 붙이는 few-shot 예시.

**왜 프롬프트 본문이 아니라 대화 턴인가.** 예시를 프롬프트 문장으로 적는 방식은
2026-10-29 에 측정했고 안 움직였다(공허한 조언 6.6%·1.3% 개선). user/assistant 턴으로
실제 호출과 같은 모양(근거 블록이 들어오고 카드 JSON 이 나간다)을 시연하면 JSON 봉투·
필드 관계·카드 간 구조까지 전달된다.

**왜 예시 user 턴에 규칙을 안 싣는가.** 규칙까지 넣으면 예시 한 쌍이 약 1,900 토큰이고
그중 1,500 이 규칙이다. 2 쌍이면 규칙을 세 번 싣는다 — 창 8,192(vLLM 기본값, 팟을 다시
만들면 여기로 돌아온다)에서 입력 7,105 · 출력 여유 1,087 이 되고 실측 출력이 500~1,000 이라
꼬리가 잘린다. 근거 블록만 담으면 입력 4,176 · 출력 여유 4,016 이다. 근거 블록은
`solution.focus_blocks` 로 만든다 — 사람이 쓴 블록을 쓰면 실제 호출과 글자가 어긋난다.

**측정**(Qwen3-32B-AWQ, 창 8,192, n=15. judge 는 라벨을 가린 사람 판정).

    축            예시 없음   V5 예시   이 예시(V6)
    메뉴 축           —        49%       90%      (87장, Fisher p = 0.000)
    카테고리 축        —        20%       60%      (50장, p = 0.009)
    시간대 축          —        28%       36%      (50장, p = 0.762)

시간대 축은 예시로 안 움직였다 — 원인이 프롬프트가 "인력을 늘리세요" 를 좋은 예로 들던
것이었고 PR #275 가 고쳐 28% → 84% 가 됐다. 예시와 프롬프트가 서로 다른 축을 열었다.

예시를 고치면 `SHOTS_VERSION` 을 그날 날짜로 올린다. 프롬프트 본문은 안 바뀌므로
`solution.VERSION` 과는 별개다. 측정 기록은 docs/STATE.md 2026-11-04~06 절.
"""

import json

from app.prompts import solution as prompt
from app.services.solution_focus import assign, derive

SHOTS_VERSION = "2026-11-06"

# ── 예시 1 — 시간대 · 매출총액 · 카테고리 (카드 3 장) ──────────────────
_METRICS_1 = {
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 10, "amount": 48000},
        {"dayType": "WEEKDAY", "hour": 13, "amount": 286000},
        {"dayType": "WEEKDAY", "hour": 16, "amount": 74000},
        {"dayType": "WEEKDAY", "hour": 19, "amount": 192000},
    ],
    "salesSummary": {
        "netSales": 1312000,
        "vsPrevPeriod": -0.07,
        "period": "2026-10-14~2026-10-20",
    },
    "categoryBreakdown": [
        {"name": "커피", "share": 0.55, "vsPrevPeriod": -0.15},
        {"name": "디저트", "share": 0.24, "vsPrevPeriod": 0.11},
        {"name": "논커피", "share": 0.21, "vsPrevPeriod": -0.04},
    ],
}

_OUTPUT_1 = {
    "solutionCards": [
        {
            # 금액 대신 배수와 시각만 쓴다 — amount 는 분석 기간 누적이다.
            "rankNo": 1,
            "title": "오전에 미리 만들어 두는 양을 줄이세요",
            "summaryText": "평일 13시 매출이 10시의 6배로, 오전이 하루 중 가장 비어 있습니다.",
            "detailText": (
                "10시에 만들어 둔 음료가 남으니, 오전 준비량을 줄이고 13시 직전에 맞춰 뽑으세요."
            ),
            "evidence": "평일 peakHour 13시 / lowHour 10시, 배율 6.0배",
        },
        {
            # 지표가 두 개뿐이면 한 문장으로 끝낸다는 것도 가르칠 값이 있다.
            "rankNo": 2,
            "title": "발주 정량을 줄어든 매출에 맞춰 다시 잡으세요",
            "summaryText": "집계 기간 순매출이 1,312,000원으로 이전 기간보다 7% 줄었습니다.",
            "detailText": (
                "지금 발주 수량은 매출이 더 높던 이전 기간에 맞춰져 있으니, "
                "품목별 정량을 다시 잡으세요."
            ),
            "evidence": "순매출 1,312,000원, 이전 기간 대비 7% 감소",
        },
        {
            # share x vsPrevPeriod 로 우선순위를 뒤집는다 — 비중 큰 쪽이 빠진 손실은
            # 비중 작은 쪽이 늘어난 것으로 메울 수 없다. "이전 기간보다" 를 문장에 박아
            # 둔다. 빼면 모델이 "디저트는 11% 증가했습니다" 로 바꿔 쓰고 점주는 뭐에
            # 비해서인지 알 수 없다(2026-11-06 측정).
            "rankNo": 3,
            "title": "디저트보다 커피 회복이 먼저입니다",
            "summaryText": "커피가 전체 매출의 55%, 디저트가 24%를 차지합니다.",
            "detailText": (
                "이전 기간보다 커피는 15% 줄고 디저트는 11% 늘었는데, 비중이 큰 커피에서 "
                "빠진 손실은 디저트 증가로 메울 수 없습니다.\n"
                "디저트 추천에 손을 쓰기 전에, 커피 주문이 왜 줄었는지 영수증에서 먼저 보세요."
            ),
            "evidence": "커피 비중 55% 전기 대비 -0.15, 디저트 비중 24% 전기 대비 0.11",
        },
    ]
}

# ── 예시 2 — 시간대 · 메뉴 (카드 2 장) ────────────────────────────────
# 축이 2 개면 카드도 2 장이다. 예시 둘 다 3 장이면 "항상 3 장" 으로 읽힌다.
_METRICS_2 = {
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 11, "amount": 31000},
        {"dayType": "WEEKDAY", "hour": 14, "amount": 97000},
        {"dayType": "WEEKDAY", "hour": 17, "amount": 58000},
        {"dayType": "WEEKDAY", "hour": 20, "amount": 214000},
    ],
    "menuRankings": [
        {
            "rank": 6,
            "menuName": "딸기 라떼",
            "menuSales": 164000,
            "quantity": 41,
            "ratio": 0.13,
            "vsPrevPeriod": 0.64,
        },
        {
            "rank": 1,
            "menuName": "아이스 아메리카노",
            "menuSales": 388000,
            "quantity": 97,
            "ratio": 0.31,
            "vsPrevPeriod": -0.08,
        },
    ],
}

_OUTPUT_2 = {
    "solutionCards": [
        {
            "rankNo": 1,
            "title": "재고 실사와 진열 교체는 11시에 끝내 두세요",
            "summaryText": "평일 매출이 20시에 몰리고, 11시가 하루 중 가장 비어 있습니다.",
            "detailText": (
                "20시 매출이 11시의 6.9배이니, 재고 실사와 진열 교체처럼 손이 묶이는 일은 "
                "11시에 몰아 두세요."
            ),
            "evidence": "평일 peakHour 20시 / lowHour 11시, 배율 6.9배",
        },
        {
            # 단일 품목·한 방향이 아니라 **품목 차등**을 보여준다. 단일 품목 예시를 넣었던
            # V5 는 메뉴 축 judge specific 을 60% → 10% 로 깎았다 — 모델이 예시의 모양을
            # 베껴 차등 판단을 잃었다(2026-11-04 측정).
            "rankNo": 2,
            "title": "아이스 아메리카노는 그대로 두고 딸기 라떼만 늘리세요",
            "summaryText": "딸기 라떼가 41잔으로 이전 기간보다 64% 늘었습니다.",
            "detailText": (
                "딸기 라떼 재료만 늘리고, 1위인 아이스 아메리카노 원두 발주는 건드리지 마세요.\n"
                "아이스 아메리카노는 8% 줄었지만 여전히 순위 1위라, 발주를 줄이면 "
                "품절 쪽이 더 위험합니다."
            ),
            "evidence": "딸기 라떼 41잔 전기 대비 +64%, 아이스 아메리카노 1위 전기 대비 -8%",
        },
    ]
}

SHOTS = ((_METRICS_1, _OUTPUT_1), (_METRICS_2, _OUTPUT_2))


def messages() -> list[dict[str, str]]:
    """system 과 실제 user 턴 사이에 끼울 예시 대화 턴.

    user 턴은 근거 블록만 담는다(모듈 주석 참고). assistant 턴은 카드 JSON 이다.
    """
    out: list[dict[str, str]] = []
    for metrics, output in SHOTS:
        focus = assign(derive(metrics))
        out.append({"role": "user", "content": prompt.focus_blocks(focus)})
        out.append({"role": "assistant", "content": json.dumps(output, ensure_ascii=False)})
    return out
