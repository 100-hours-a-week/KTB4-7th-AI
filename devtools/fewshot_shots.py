"""few-shot 예시 — 근거 블록(입력) → 카드 JSON(출력) 완성 쌍.

손으로 쓴 문장이다. 외부 저작물을 인용하지 않는다.

**예시는 반드시 채점기를 통과해야 한다.** 통과하지 않는 예시를 주면 모델에게 위반을
가르친다. `fewshot_exp.validate()` 가 각 예시를 `grade.grade_solution` 으로 채점해 전
항목 통과를 요구하고, 실패하면 측정을 시작하지 않는다.

**카드는 자기 축의 소재만 말한다.** 처음엔 시간대 카드가 "베이커리를 계산대 앞줄로
옮기세요" 라고 썼는데 베이커리는 `categoryBreakdown` 소속이다. 채점기의
`카드_지표_중복없음` 은 **수치** 기준이라 안 걸리지만, few-shot 으로 이걸 가르치면 모델이
축을 넘나드는 걸 배운다 — 프롬프트가 "각 카드는 자기 근거 지표만" 이라고 지시하는 것과
정반대다.

**축 배정은 사람이 고르지 않는다.** `solution_focus.assign` 에 예시 지표를 넣어 나온
순서에 카드를 맞춘다. 예시 지표는 벤치 케이스와 다른 숫자로 만들었다 — 측정할 입력을
예시로 흘리면 안 된다.

── V2 와 V3 의 차이 ────────────────────────────────────────────────

2026-10-29 에 V2 예시 6장을 `devtools/judge.py` 로 판정해보니 **4장이 obvious** 였다.
그리고 축별 결과가 정확히 그 선에서 갈렸다(같은 날 측정, arm A→D_fewshot2):

    specific 예시가 있던 축   hourlyProfile  72% → 52% obvious   개선
                            menuRankings  100% → 20% obvious   개선
    obvious 예시만 있던 축    categoryBreakdown  100% → 100%     안 움직임
                            salesSummary        100% →  97%     안 움직임
                            weatherContext      100% → 100%     안 움직임

5/5 로 대응한다. 공허함 20% 천장의 일부는 지표가 아니라 **예시** 였다는 뜻이다.

V3 은 그래서 **categoryBreakdown 카드 한 장만** 바꾼다. 나머지 다섯 장은 오늘 기준으로
더 좋게 쓸 재료가 없다:

  salesSummary    `netSales` 가 기간 합계라 오늘 예측과 비교하려면 일평균이 필요하다.
                  코드가 계산해 근거 블록에 넣어야 한다 — 모델에게 나눗셈을 시키면
                  "계산은 코드, 해석만 모델" 위반이다.
  weatherContext  예보는 **이 매장의** 데이터가 아니다. 판정 기준이 "이 조언을 하려면
                  이 매장의 지표를 봐야 하는가" 라서, 기온·강수만으로 쓴 조언은 같은
                  동네 모든 카페에 똑같이 적용된다 — 이 축은 `conditionPatterns` 를
                  붙이기 전까지(#246) 구조적으로 specific 이 될 수 없다.
  hourlyProfile   기존 카드가 이미 specific 판정을 받았다.
  menuRankings    같다.

바뀐 카드는 2026-10-29 BE PR #636 의 `previousShare` 로만 쓸 수 있다. `share` 만으로는
"비중이 올랐다" 와 "매출이 늘었다" 가 구분되지 않아서, 그 자리에 쓸 수 있는 말이
"비중이 올랐으니 더 밀어라"(obvious) 밖에 없었다.
"""

SHOT1_METRICS = {
    "salesSummary": {"netSales": 2104000, "vsPrevPeriod": 0.18},
    "predictedSalesToday": 2480000,
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 10, "amount": 48000},
        {"dayType": "WEEKDAY", "hour": 13, "amount": 286000},
        {"dayType": "WEEKDAY", "hour": 16, "amount": 74000},
        {"dayType": "WEEKDAY", "hour": 19, "amount": 192000},
    ],
    "categoryBreakdown": [
        {"name": "음료", "share": 0.58, "vsPrevPeriod": 0.05},
        {"name": "베이커리", "share": 0.31, "vsPrevPeriod": 0.42},
        {"name": "기타", "share": 0.11, "vsPrevPeriod": -0.08},
    ],
    "businessHours": {"WEEKDAY": {"opensAt": "09:00", "closesAt": "21:00"}},
}

_SHOT1_CARD1 = {
    "rankNo": 1,
    "title": "오늘은 재료를 평소보다 넉넉하게 준비하세요",
    "summaryText": (
        "순매출이 2,104,000원으로 이전 기간보다 18% 늘었고, "
        "오늘도 그 흐름이 이어질 것으로 보입니다."
    ),
    "detailText": (
        "오늘 예측 매출이 2,480,000원이니, "
        "오픈 전에 원두와 우유 발주를 늘리고 재고를 미리 채워 두세요.\n"
        "이어서 결제 줄이 길어지면 계산대를 더 열 수 있게 미리 준비해 두세요.\n"
        "그러면 늘어난 손님을 놓치지 않고 매출로 연결할 수 있습니다."
    ),
    "evidence": "순매출 2,104,000원, 이전 기간 대비 18% 증가",
}

_SHOT1_CARD2 = {
    "rankNo": 2,
    "title": "오후 교대와 저녁 준비를 16시에 몰아 두세요",
    "summaryText": (
        "평일 피크가 13시 286,000원과 19시 192,000원으로 두 번인데, "
        "그 사이 16시는 74,000원으로 가장 비어 있습니다."
    ),
    "detailText": (
        "그러니 점심 담당이 빠지고 저녁 담당이 들어오는 시간을 그 골짜기에 맞추세요.\n"
        "같은 구간에 저녁에 쓸 재료를 미리 빼두고 기계 청소도 끝내 두세요.\n"
        "그러면 두 피크 모두 인력이 차 있고, 붐비는 동안 준비로 손이 빠지지 않습니다."
    ),
    "evidence": "평일 13시 286,000원, 19시 192,000원, 그 사이 16시 74,000원",
}

_SHOT1_CARD3_V2 = {
    "rankNo": 3,
    "title": "베이커리를 매장에서 가장 먼저 보이는 자리로 옮기세요",
    "summaryText": "베이커리 비중이 31%까지 올라오며 이전 기간 대비 42% 늘었습니다.",
    "detailText": (
        "음료 비중이 58%로 여전히 가장 크니, "
        "음료를 주문하는 손님에게 베이커리를 함께 권하도록 응대 순서를 정해 두세요.\n"
        "이를 위해 진열대에서 베이커리를 눈높이 칸으로 올리고, 구운 순서대로 앞줄에 배치하세요.\n"
        "그러면 음료만 사 가던 손님이 베이커리를 같이 집어 가게 만들 수 있습니다."
    ),
    "evidence": "베이커리 비중 31%, 이전 기간 대비 42% 증가",
}

SHOT1_OUTPUT = {"solutionCards": [_SHOT1_CARD1, _SHOT1_CARD2, _SHOT1_CARD3_V2]}

SHOT2_METRICS = {
    "salesSummary": {"netSales": 1312000, "vsPrevPeriod": -0.07},
    "menuRankings": [
        {
            "rank": 1,
            "menuName": "아이스 아메리카노",
            "menuSales": 388000,
            "quantity": 97,
            "ratio": 0.3,
            "vsPrevPeriod": -0.05,
        },
        {
            "rank": 6,
            "menuName": "딸기 라떼",
            "menuSales": 164000,
            "quantity": 41,
            "ratio": 0.13,
            "vsPrevPeriod": 0.64,
        },
    ],
    "weatherContext": {
        "basisDateTime": "2026-10-28 08:00",
        "skyText": "맑음",
        "minTempC": 9,
        "maxTempC": 21,
        "maxPop": 0.1,
        "isNotable": True,
    },
    "businessHours": {"WEEKDAY": {"opensAt": "09:00", "closesAt": "21:00"}},
}

SHOT2_OUTPUT = {
    "solutionCards": [
        {
            "rankNo": 1,
            "title": "오전에는 따뜻한 음료, 오후에는 얼음을 먼저 챙기세요",
            "summaryText": (
                "오늘 예보는 맑음이고 최저 9도에서 최고 21도까지 올라, "
                "하루 안에서 손님이 찾는 음료가 갈립니다."
            ),
            "detailText": (
                "오픈 직후에는 온음료 기계를 먼저 예열하고, 따뜻한 음료를 메뉴판 앞쪽에 두세요.\n"
                "이어서 기온이 오르기 전에 얼음 재고를 확인하고, 모자라면 오전 중에 채워 두세요.\n"
                "그러면 시간대마다 손님이 찾는 음료가 품절되는 일을 줄일 수 있습니다."
            ),
            "evidence": "오늘 예보 맑음, 최저 9도 최고 21도",
        },
        {
            "rankNo": 2,
            "title": "마감 전에 남는 재료를 줄이도록 발주를 조절하세요",
            "summaryText": "순매출이 1,312,000원으로 이전 기간보다 7% 줄었습니다.",
            "detailText": (
                "우선 상하기 쉬운 재료부터 발주량을 줄이고, "
                "남은 재고를 먼저 쓰도록 순서를 정하세요.\n"
                "이어서 마감 두 시간 전에 남은 수량을 확인해, 다음 발주에 그만큼 반영하세요.\n"
                "그러면 손님이 줄어든 기간에도 버리는 재료를 줄일 수 있습니다."
            ),
            "evidence": "순매출 1,312,000원, 이전 기간 대비 7% 감소",
        },
        {
            "rankNo": 3,
            "title": "딸기 라떼 재료를 먼저 확보해 두세요",
            "summaryText": "딸기 라떼가 41잔 팔리며 이전 기간 대비 64% 늘었습니다.",
            "detailText": (
                "딸기 라떼 매출이 164,000원까지 올라왔으니, "
                "우유와 딸기 재료를 먼저 확보해 두세요.\n"
                "이어서 메뉴판과 계산대 앞 안내에서 딸기 라떼를 잘 보이는 자리로 옮기세요.\n"
                "그러면 지금 손님이 몰리는 메뉴를 품절로 놓치지 않을 수 있습니다."
            ),
            "evidence": "딸기 라떼 41잔, 이전 기간 대비 64% 증가",
        },
    ]
}

# ── V3 ──────────────────────────────────────────────────────────────
# 예시1 의 categoryBreakdown 지표에 previousShare 를 넣고, 카드를 그 필드로만 쓸 수 있는
# 문장으로 바꾼다. share 만 보면 "베이커리를 밀어라" 가 나오고, previousShare 와
# vsPrevPeriod 를 같이 보면 결론이 반대로 뒤집힌다.

SHOT1_METRICS_V3 = dict(SHOT1_METRICS)
SHOT1_METRICS_V3["categoryBreakdown"] = [
    {"name": "음료", "share": 0.58, "vsPrevPeriod": -0.19, "previousShare": 0.63},
    {"name": "베이커리", "share": 0.31, "vsPrevPeriod": -0.06, "previousShare": 0.28},
    {"name": "기타", "share": 0.11, "vsPrevPeriod": 0.42, "previousShare": 0.09},
]

_SHOT1_CARD3_V3 = {
    "rankNo": 3,
    "title": "베이커리 비중이 올랐지만 늘어난 건 아닙니다",
    "summaryText": (
        "베이커리 비중이 이전 기간 28%에서 31%로 올랐는데, "
        "베이커리 매출 자체는 이전 기간 대비 6% 줄었습니다."
    ),
    "detailText": (
        "음료가 19% 줄면서 전체가 더 많이 빠진 탓에 베이커리 비중만 올라간 것이니, "
        "지금은 베이커리를 더 밀 때가 아닙니다.\n"
        "먼저 음료 쪽 진열과 주문 시 권하는 순서를 점검하고, "
        "비중이 63%에서 58%로 내려간 구간을 메우세요.\n"
        "그러면 비중이 올라온 쪽이 아니라 실제로 빠져나간 쪽에 손을 쓸 수 있습니다."
    ),
    "evidence": "베이커리 비중 28% → 31%, 베이커리 매출 이전 기간 대비 6% 감소",
}

SHOT1_OUTPUT_V3 = {"solutionCards": [_SHOT1_CARD1, _SHOT1_CARD2, _SHOT1_CARD3_V3]}

SHOTS_V2 = [(SHOT1_METRICS, SHOT1_OUTPUT), (SHOT2_METRICS, SHOT2_OUTPUT)]
SHOTS_V3 = [(SHOT1_METRICS_V3, SHOT1_OUTPUT_V3), (SHOT2_METRICS, SHOT2_OUTPUT)]
