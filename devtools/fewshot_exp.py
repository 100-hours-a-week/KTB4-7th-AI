"""few-shot 예시가 "공허한 조언" 을 줄이는지 재는 측정기.

현행 프롬프트는 "마케팅을 강화하세요" 류를 문장째로 **열거해 금지**하는데도 공허한 카드가
남는다(2026-10-26 측정). "더 세게 금지" 는 이미 해봤고 안 통했다. 안 해본 건 **좋은 문장을
보여주는 것** 이라 그걸 재려고 만들었다.

arm 구성:

    A_현행              기준점
    B_예시추가          현행 + 축별 실행안 산문(금지 문단 유지)
    C_금지제거_예시만   금지 문단을 산문 예시로 교체 — 금지 문단의 기여를 가른다
    D_fewshot1          완성 예시 1쌍을 user/assistant 대화로 앞에 붙인다
    D_fewshot2          완성 예시 2쌍
    D_fewshot3          D_fewshot2 와 같은 2쌍인데 categoryBreakdown 카드가 specific 한 것

B·C 는 **프롬프트 문장에 예시를 끼우는** 방식이고 D 는 **대화 쌍**이다. 둘을 섞으면 "모양을
보여주는 것" 의 효과만 떼어낼 수 없어서 arm 을 나눴다. D 계열은 `_USER` 를 현행 그대로 둔다.

**제나 영역 파일(`app/prompts/`)은 건드리지 않는다.** 메모리에서만 템플릿을 바꿔 호출한다.

덤프는 `devtools/bench.py --dump` 와 같은 모양이라 `devtools/judge.py --dump` 로 바로
판정할 수 있다. arm 을 여러 개 돌리면 `<이름>.<arm>.json` 으로 arm 당 한 파일을 쓴다 —
judge 가 한 번에 한 덤프만 읽는다.

    uv run python -m devtools.fewshot_exp --arms D_fewshot3 --n 5 --dump exp_v3.json
    uv run python -m devtools.judge --dump exp_v3.json --out judge_v3.json

GPU 시간이 든다(순차 호출). judge 는 Anthropic 요금이 든다.
"""

import argparse
import asyncio
import functools
import json
import pathlib
import statistics
import sys
import time

import httpx

from app.core.config import settings
from app.prompts import solution as prompt
from app.services import solution as service
from app.services.solution_focus import assign, derive
from devtools import grade
from devtools.bench import SOLUTION_CASES
from devtools.fewshot_shots import (
    SHOTS_RELAXED,
    SHOTS_V2,
    SHOTS_V3,
    SHOTS_V4,
    SHOTS_V5,
    SHOTS_V6,
    SHOTS_V7,
)

print = functools.partial(print, flush=True)  # 파일로 리다이렉트해도 진행이 보이게

_BAN = """그리고 "마케팅을 강화하세요", "프로모션을 진행하세요", "홍보 활동을 확대하세요",
"전략을 변경하세요" 같은 문장은 쓰지 마세요. 누구나 할 수 있는 말이라 점주가 오늘 무엇을
다르게 할지 알 수 없습니다. 무엇을 언제 할지가 드러나야 합니다.
"""

# 우리가 쓴 문장이다 — 외부 저작물을 인용하지 않는다. 메뉴명·수치는 슬롯([])으로 둬서
# 모델이 지표에 없는 이름을 베껴 쓰지 않게 한다.
_PLAYBOOK = """실행 문장은 아래 예시만큼 구체적으로 쓰세요. 새 수치를 지어내지 않고도
"무엇을 언제 어디서" 가 드러납니다. 문장을 그대로 쓰지 말고, 배정받은 지표에 맞춰
같은 구체성으로 다시 쓰세요. [ ] 안은 지표에서 가져와 채울 자리입니다.

- 평일 [한가한 시각] 30분 전에 진열대 디저트를 계산대 앞줄로 옮기고, 그 시간대에는
  커피와 묶어 권하도록 응대 멘트를 정해 두세요.
- [비중이 오른 카테고리] 를 계산대에서 가장 먼저 보이는 자리로 돌리고, [비중이 줄어든
  카테고리] 는 진열을 뒤로 미루세요.
- [늘어난 메뉴] 재료를 먼저 확보하고, [줄어든 메뉴] 발주는 줄이세요.
- 오전에는 핫 음료 기계를 먼저 예열하고, [기온이 오르는 시각] 전에 얼음 재고를 확인하세요.
- 마감 [N] 시간 전에 남은 디저트를 계산대 앞으로 모아 눈에 띄게 두세요.
"""

# ── 2026-11-02 "문제 해결 강제" 완화 (헥터 제안) ─────────────────────────
#
# 현행 _USER 는 카드마다 **문제 → 원인 → 해결 → 기대효과** 를 강제한다. 지표가 아무
# 문제도 가리키지 않는 날에도 모델은 문제를 하나 만들어야 하고, 그래서 "매출이 줄었으니
# 발주를 줄이세요" 류가 나온다 — judge 가 공허하다고 판정하는 바로 그 모양이다.
#
# 완화하는 것은 **서술 구조 강제**뿐이다. 금지 규칙("마케팅을 강화하세요" 류, 행동의
# "얼마나" 금지, 수치 접지)은 하나도 건드리지 않는다 — 금지 문단을 통째로 뺀
# C_금지제거_예시만 이 역효과였다(judge specific 1.3% vs A 5.9%, 수치 정확도도 하락).
#
# detailText 문장 수는 3개로 유지한다. `devtools/grade.py::detail_3문장` 이 줄바꿈을
# 정확히 2개로 세기 때문에, 문장 수를 건드리면 arm 마다 채점 기준이 달라진다. 대신
# **세 문장의 배분 강제**를 푼다 — 기대효과가 뻔하면 그 자리에 실행을 한 문장 더 쓴다.

_FORCED_ORDER = """title 이
결론(무엇을 할지)을 먼저 던지고, 그 다음 문장들이 왜 그런지(문제·원인) → 구체적으로
어떻게 할지 → 그렇게 하면 어떤 효과가 있을지 순서로 뒷받침하게 쓰세요."""

_RELAXED_ORDER = """title 이
결론(무엇을 할지)을 먼저 던지고, 그 다음 문장들이 왜 그렇게 판단했는지(근거) →
구체적으로 어떻게 할지 순서로 뒷받침하게 쓰세요. 지표가 문제를 가리키면 문제를 쓰고,
그렇지 않으면 읽어낸 사실을 그대로 쓰세요 — 없는 문제를 만들지 마세요."""

# 2026-11-06(PR #275): "근거 수치와" 가 "근거 지표와" 로 바뀌었다. 시간대 금액 인용이
# 금지되면서 수치를 못 쓰는 카드가 생겨서다 — 뒤따르는 "hourlyPeakRatio가 없으면 시각만"
# 조항이 그 경로를 열어준다. 그 조항은 이 쌍이 건드리지 않으니 그대로 남는다.
_FORCED_SUMMARY = (
    "summaryText 는 지금 어떤 문제가 있고 왜 그런지를 근거 지표와 함께 한 문장으로 쓰세요."
)

_RELAXED_SUMMARY = """\
summaryText 는 그 카드의 판단 근거를 지표 수치와 함께 한 문장으로 쓰세요. 문제일 수도
있고, 기회일 수도 있고, 평소와 같다는 사실일 수도 있습니다."""

_FORCED_DETAIL = """\
detailText 는 세 문장을 줄바꿈(\\n)으로 구분해 쓰세요: 그 원인을 해결하려면 구체적으로
무엇을 해야 하는지 실행 방법 두 문장, 그리고 마지막에 그렇게 했을 때 기대되는 효과 한
문장."""

_RELAXED_DETAIL = """\
detailText 는 세 문장을 줄바꿈(\\n)으로 구분해 쓰세요. 오늘 무엇을 어떻게 할지가
중심입니다. 기대 효과는 그 행동만 봐도 바로 알 수 있는 내용이면 쓰지 말고, 그 자리에
실행 내용을 한 문장 더 쓰세요."""

# 완화 문단 뒤에 "기대효과 문장에는 ..." 이 그대로 남아 있어서, 앞에서 안 써도 된다고
# 하고 뒤에서 그 문장이 있다고 전제했다. 조건부로 읽히게 어미만 바꾼다 — 새 수치 금지
# 규칙 자체는 그대로다.
_FORCED_EFFECT = "기대효과 문장에는 지표에 없는 새 수치를"
_RELAXED_EFFECT = "기대 효과를 쓸 때는 지표에 없는 새 수치를"

_RELAXED = (
    (_FORCED_ORDER, _RELAXED_ORDER),
    (_FORCED_SUMMARY, _RELAXED_SUMMARY),
    (_FORCED_DETAIL, _RELAXED_DETAIL),
    (_FORCED_EFFECT, _RELAXED_EFFECT),
)


# 문장 수 자체를 푸는 쌍 (2026-11-03). 위 _RELAXED 는 기대효과 칸만 조건으로 바꿨고
# "세 문장" 은 그대로 뒀다 — 할 말이 하나뿐인 카드는 여전히 세 칸을 채운다. 예시 6장을
# 세어보니 세 문장을 버는 건 1장이었다. 상한만 남긴다.
_FORCED_COUNT = """\
detailText 는 세 문장을 줄바꿈(\\n)으로 구분해 쓰세요: 그 원인을 해결하려면 구체적으로
무엇을 해야 하는지 실행 방법 두 문장, 그리고 마지막에 그렇게 했을 때 기대되는 효과 한
문장."""

_FREE_COUNT = """\
detailText 는 근거 지표가 말해주는 만큼만 쓰세요: 한 문장이면 한 문장, 많아도 세
문장까지입니다. 여러 문장이면 줄바꿈(\\n)으로 구분하고, 채우려고 당연한 말이나 앞
문장을 바꿔 말한 문장을 넣지 마세요."""

# 뒤따르는 "기대효과 문장에는 ... 정성적으로만 쓰세요" 도 기대효과 칸을 전제한다.
_FORCED_QUALITATIVE = (
    "기대효과 문장에는 지표에 없는 새 수치를\n"
    '지어내지 말고("매출 15% 증가" 등 금지) "~를 늘릴 수 있습니다"처럼 정성적으로만 쓰세요.'
)
_FREE_QUALITATIVE = (
    "어느 문장에서도 지표에 없는 새 수치를\n"
    '지어내지 마세요 — 특히 결과를 수치로 약속하는 말("매출 15% 증가" 등)은 쓰지 않습니다.'
)

_FREE_LENGTH = (
    (_FORCED_COUNT, _FREE_COUNT),
    (_FORCED_QUALITATIVE, _FREE_QUALITATIVE),
)

# ── 2026-11-03 인력 조언 금지 arm 은 2026-11-06 에 지웠다 ──────────────
#
# 네 arm 334 장에서 카드의 32~42% 가 "인력을 늘리세요" 류였고, 원인이 예시가 아니라
# 프롬프트가 그 문장을 **좋은 본보기로** 들고 있던 것이었다. 그걸 뺀 arm(`G_인력금지_
# 예시V4`)으로 재서 제나님께 넘겼고, PR #275 가 프롬프트에 반영했다 — 본보기에서 인력을
# 빼고 증원·감축·재배치·교대 변경을 금지하고, 시간대 카드는 가장 낮은 시각에 점주 혼자
# 할 수 있는 일을 넣게 했다.
#
# 그래서 이 arm 의 치환 쌍이 기준 문단을 못 찾아 측정 시작을 막았다. 시뮬레이션할 대상이
# 본문이 됐으니 arm 을 지운다. 과거 숫자는 docs/STATE.md 와 git 히스토리에 있다.


def _relaxed_template(pairs=_RELAXED) -> str:
    text = prompt._USER
    for old, new in pairs:
        if old not in text:
            raise SystemExit(f"완화 대상 문단을 못 찾았다 — 프롬프트가 바뀌었다:\n{old[:40]}")
        text = text.replace(old, new, 1)
    return text


# arm 이름 → (USER 템플릿, 예시 쌍)
ARMS: dict[str, tuple[str, list]] = {
    "A_현행": (prompt._USER, []),
    "B_예시추가": (prompt._USER.replace(_BAN, _BAN + "\n" + _PLAYBOOK), []),
    "C_금지제거_예시만": (prompt._USER.replace(_BAN, _PLAYBOOK), []),
    "D_fewshot1": (prompt._USER, SHOTS_V2[:1]),
    "D_fewshot2": (prompt._USER, SHOTS_V2),
    "D_fewshot3": (prompt._USER, SHOTS_V3),
    "E_완화": (_relaxed_template(), []),
    "E_완화_예시1": (_relaxed_template(), SHOTS_RELAXED[:1]),
    "F_길이자유": (_relaxed_template(_FREE_LENGTH), []),
    "F_길이자유_예시V4": (_relaxed_template(_FREE_LENGTH), SHOTS_V4[:1]),
    # V4 의 개선이 시간대 축 한 곳에 몰렸고 거기서도 인력 조언·공허한 마무리가 남았다.
    # 원인이 "시간대 예시가 한 장" 이라고 보고 두 장으로 늘린 arm 이다 — 시각·작업·하루
    # 모양을 다 다르게 둬서 "비는 시각에 준비 작업" 같은 한 규칙으로 뭉개지지 않게 한다.
    # 예시 2 쌍이라 V4(1 쌍)보다 입력이 길다. 근거: devtools/fewshot_shots.py V5 절.
    "H_길이자유_예시V5": (_relaxed_template(_FREE_LENGTH), SHOTS_V5),
    # 예시 user 턴에서 규칙 블록을 뺀 짝. 2026-11-04 측정: 예시 user 턴 1,909 토큰 중
    # 1,529 가 규칙이라 V5(예시 2쌍)는 규칙을 세 번 싣는다. 입력 7,539 → 출력 여유 653 인데
    # 실측 출력이 500~1,000 이라 대부분 잘린다(파싱 실패). 창을 16,384 로 올리면 설계를
    # 안 건드리고 풀리지만 팟이 제나 계정이라 재시작을 안 했다.
    # 예시가 실제 호출과 모양이 달라지는 값을 치르므로 V4 쪽도 같이 바꿔 짝을 맞춘다 —
    # I 와 J 끼리만 비교하고, F·H 나 11/3 n=15 숫자와 섞어 읽지 않는다.
    "I_예시V4_근거만": (_relaxed_template(_FREE_LENGTH), SHOTS_V4[:1]),
    "J_예시V5_근거만": (_relaxed_template(_FREE_LENGTH), SHOTS_V5),
    # V5 예시 6장 중 제대로 일한 게 1장뿐이었다. 셋을 고쳤다 — judge 가 obvious 로
    # 적어둔 문장, 축과 어긋난 내용, 실제 입력에 없는 필드(previousShare)로 한 추론.
    # 매출총액 축은 예시로 살리지 않는다(netSales 가 기간 합계라 예측과 단위가 안 맞는다).
    "K_예시V6": (_relaxed_template(_FREE_LENGTH), SHOTS_V6),
    # V6 + 날씨 쌍. conditionPatterns(이 매장 강수일 실측)를 쓰는 카드를 보여준다.
    "L_예시V7_날씨": (_relaxed_template(_FREE_LENGTH), SHOTS_V7),
    # V6 를 근거만 모양으로. 2026-11-06 에 팟이 재구축되면서 창이 기본값 8,192 로
    # 돌아왔고, 그 창에서 입력을 실측했다.
    #
    #   H(V5 2쌍) 7,565 → 출력 여유   627   실측 출력 500~1,000 이라 반 이상 잘린다
    #   K(V6 2쌍) 7,105 → 출력 여유 1,087
    #   L(V7 3쌍) 8,193+               입력만으로 창을 넘는다
    #   J(V5 근거만) 4,507 → 3,685
    #
    # 팟을 다시 만들면 창이 8,192 로 돌아온다 — 규칙을 예시마다 다시 싣는 모양(H·K·L)은
    # 그 창에서 배포할 수 없다. 근거만 모양이 배포 가능한 쪽이다. J 와 짝으로 비교한다
    # (양쪽 다 규칙을 뺐으니 변수는 예시 내용 V5→V6 하나다).
    "M_예시V6_근거만": (_relaxed_template(_FREE_LENGTH), SHOTS_V6),
}

# 예시 user 턴을 근거 블록만으로 줄이는 arm.
_BLOCKS_ONLY = frozenset({"I_예시V4_근거만", "J_예시V5_근거만", "M_예시V6_근거만"})

KEYS = [
    "공허한_조언_없음",
    "인력_조언_없음",
    "summary_수치_정확",
    "evidence_수치_정확",
    "detail_수치_정확",
    "수치_필드간_중복없음",
    "카드_지표_중복없음",
    "카드_개수_적정",
]


def _check_templates() -> None:
    """B·C 의 치환이 실패하면 arm 이 조용히 A 와 같아진다 — 금지 문단 문구가 바뀌면 깨진다."""
    for name, (text, _) in ARMS.items():
        if text.count("{focus_blocks}") != 1:
            raise SystemExit(f"{name} 템플릿에 focus_blocks 자리가 하나가 아니다")
        if name.startswith(("B_", "C_")) and text == prompt._USER:
            raise SystemExit(f"{name} 치환 실패 — _BAN 문구가 프롬프트와 안 맞는다")
    for name in _BLOCKS_ONLY:
        if name not in ARMS:
            raise SystemExit(f"_BLOCKS_ONLY 의 {name} 이 ARMS 에 없다")
        turns = shot_messages(ARMS[name][1], blocks_only=True)
        leaked = [m for m in turns if m["role"] == "user" and "[카드 1 근거]" not in m["content"]]
        if leaked or any(m["role"] == "user" and "쓰지 마세요" in m["content"] for m in turns):
            raise SystemExit(f"{name} 예시 user 턴에 규칙이 남아 있다 — 창 절약이 안 된다")


def validate(shots: list) -> None:
    """예시가 채점기를 통과하지 않으면 측정을 시작하지 않는다 — 위반을 가르치게 된다."""
    for index, (metrics, output) in enumerate(shots, start=1):
        derived = derive(metrics)
        expected = len(assign(derived)) or grade.MAX_CARDS
        result = grade.grade_solution(json.dumps(output, ensure_ascii=False), derived, expected)
        failed = [
            key
            for key, value in result.items()
            if isinstance(value, bool) and not value and key not in grade.MEASURE_ONLY
        ]
        if not result.get("parsed") or failed:
            raise SystemExit(f"예시 {index} 가 채점기를 못 넘었다: {failed}")


def _blocks(focus: list) -> str:
    """근거 블록 텍스트. 실제 호출과 예시가 같은 글자를 쓰도록 한 군데서 만든다."""
    return "\n\n".join(
        f"[카드 {index} 근거]\n{json.dumps(item, ensure_ascii=False)}"
        for index, item in enumerate(focus, start=1)
    )


def shot_messages(shots: list, blocks_only: bool = False) -> list[dict]:
    """예시를 user/assistant 대화 쌍으로 만든다.

    프롬프트 문장에 끼우지 않는다 — 실제 호출과 같은 모양(근거 블록이 들어오고 카드 JSON 이
    나간다)을 그대로 시연해야 JSON 봉투·필드 관계·카드 간 구조까지 전달된다.

    근거 블록은 `prompt.build` 로 만든다. 사람이 쓴 블록을 쓰면 실제 호출과 모양이 어긋난다.

    `blocks_only` 는 예시 user 턴에서 규칙 블록을 빼고 근거 블록만 남긴다 — 8,192 창에
    안 들어갈 때 쓴다(`_BLOCKS_ONLY` 참고). 위 "같은 모양" 원칙을 깨는 것이므로 기본값이
    아니고, 쓰는 arm 은 이름에 드러낸다.
    """
    messages: list[dict] = []
    for metrics, output in shots:
        focus = assign(derive(metrics))
        messages.append(
            {
                "role": "user",
                "content": _blocks(focus)
                if blocks_only
                else prompt.build(focus, "2026-10-21", "수요일", False),
            }
        )
        messages.append({"role": "assistant", "content": json.dumps(output, ensure_ascii=False)})
    return messages


async def _model_id(client: httpx.AsyncClient, base: str, key: str) -> str:
    """vLLM 은 Pod 를 다시 띄우면 모델 이름이 바뀔 수 있어 서버에 물어본다."""
    response = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    return response.json()["data"][0]["id"]


# 호출 하나의 절대 상한. httpx 의 read 타임아웃은 바이트가 올 때마다 다시 시작해서,
# 프록시가 뭔가 흘려보내면 끊긴 소켓이 영원히 안 끊긴다 — 2026-11-06 메뉴 런에서 두 건이
# 각각 32 분씩 붙잡아 GPU 시간 84 분 중 64 분이 거기 나갔다(호출에 실제로 쓴 건 19.7 분).
# 정상 호출은 p50 20 초·최대 25 초이고, 출력이 창 상한(약 4,000 토큰)까지 가도 90 초쯤이다.
_CALL_CEILING = 120.0


async def _one(
    client: httpx.AsyncClient,
    base: str,
    key: str,
    model: str,
    user_text: str,
    metrics: dict,
    expected: int,
    shots: list[dict],
) -> dict:
    started = time.monotonic()
    response = await client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": prompt.SYSTEM},
                *shots,
                {"role": "user", "content": user_text},
            ],
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    took = time.monotonic() - started
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"]
    row = grade.grade_solution(raw, metrics, expected)
    row["_took"] = took
    row["_raw"] = raw
    # judge.py 가 읽는 자리다 — bench.py 의 덤프와 같은 이름을 쓴다.
    row["sample"] = row.get("cards")
    # 재시도율·폐기율은 채점기 복제본이 아니라 서비스의 판정을 그대로 쓴다. 2026-10-16 에
    # 채점기에만 있던 규칙 때문에 위반이 측정에서 100% 통과로 보인 적이 있다.
    kept, _ = service._parse(raw, metrics)
    row["_retry"] = kept is None
    row["_kept"] = len(kept or [])
    return row


def _user_text(template: str, metrics: dict) -> tuple[str, int]:
    focus = assign(metrics)
    expected = len(focus) or grade.MAX_CARDS
    blocks = _blocks(focus)
    return (
        template.format(
            focus_blocks=blocks,
            card_count=expected,
            target_date="2026-10-28",
            day_of_week="수요일",
            weekend="평일",
            period_line="",
        ),
        expected,
    )


def report(results: dict[str, list[dict]], arms: list[str]) -> None:
    print(f"\n{'항목':<24}" + "".join(f"{arm:>20}" for arm in arms))
    print("-" * (24 + 20 * len(arms)))
    for check in KEYS:
        line = f"{check:<24}"
        for arm in arms:
            values = [r[check] for r in results[arm] if r.get("parsed") and check in r]
            rate = sum(values) / len(values) * 100 if values else float("nan")
            line += f"{rate:>19.1f}%"
        print(line)
    line = f"{'전항목통과':<24}"
    for arm in arms:
        parsed = [r for r in results[arm] if r.get("parsed")]
        passed = [
            all(
                value
                # `_` 로 시작하는 건 채점 항목이 아니라 서비스 동작 기록이다. `_retry` 는
                # False 가 정상(재시도 안 했다)인데 여기서 실패로 세여서 전항목통과가
                # 항상 0.0% 로 나왔다(2026-11-06 발견 — 11/3·11/4 보고에도 0.0% 였다).
                for key, value in row.items()
                if isinstance(value, bool)
                and not key.startswith("_")
                and key not in grade.MEASURE_ONLY
            )
            for row in parsed
        ]
        rate = sum(passed) / len(passed) * 100 if passed else float("nan")
        line += f"{rate:>19.1f}%"
    print(line)

    # 아래 셋은 비율 채점이 아니라 서비스 동작·비용이다. 4번 비교에서 품질이 비슷하면
    # 이쪽이 판단 근거가 된다 — 재시도는 호출을 두 배로 쓴다.
    line = f"{'재시도율(카드 0장)':<24}"
    for arm in arms:
        judged = [r for r in results[arm] if "_retry" in r]
        rate = sum(r["_retry"] for r in judged) / len(judged) * 100 if judged else float("nan")
        line += f"{rate:>19.1f}%"
    print(line)

    line = f"{'카드_폐기율':<24}"
    for arm in arms:
        judged = [r for r in results[arm] if "_retry" in r and r.get("cards")]
        made = sum(len(r["cards"]) for r in judged)
        kept = sum(r["_kept"] for r in judged)
        rate = (1 - kept / made) * 100 if made else float("nan")
        line += f"{rate:>19.1f}%"
    print(line)

    line = f"{'지연 p50(초)':<24}"
    for arm in arms:
        took = [r["_took"] for r in results[arm] if "_took" in r]
        line += f"{statistics.median(took):>20.1f}" if took else f"{'-':>20}"
    print(line)


def _dump_path(dump: str, arm: str, many: bool) -> pathlib.Path:
    path = pathlib.Path(dump)
    return path.with_suffix(f".{arm}{path.suffix}") if many else path


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default="A_현행,D_fewshot2,D_fewshot3")
    parser.add_argument("--n", type=int, default=5, help="arm·케이스당 반복")
    parser.add_argument(
        "--cases",
        help="쉼표로 구분한 케이스 이름. 생략하면 전부. 축을 하나 보강했을 때 이미 돌린 "
        "케이스를 다시 돌리지 않으려고 쓴다 — 두 arm 에 같은 케이스를 돌려야 비교가 선다.",
    )
    parser.add_argument("--dump", help="judge.py 가 읽을 덤프 경로")
    args = parser.parse_args()

    arms = [a for a in args.arms.split(",") if a]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise SystemExit(f"모르는 arm: {unknown} — 가능한 값 {list(ARMS)}")

    base = (settings.llm_base_url or "").rstrip("/")
    if not base:
        raise SystemExit("LLM_BASE_URL 이 비어 있다 — Pod 주소를 .env 에 넣어라")
    cases = SOLUTION_CASES
    if args.cases:
        wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
        known = {name for name, _ in SOLUTION_CASES}
        if unknown_cases := [c for c in wanted if c not in known]:
            raise SystemExit(f"모르는 케이스: {unknown_cases} — 가능한 값 {sorted(known)}")
        cases = [(name, m) for name, m in SOLUTION_CASES if name in wanted]

    _check_templates()
    for arm in arms:
        validate(ARMS[arm][1])

    async with httpx.AsyncClient(timeout=180.0) as client:
        key = settings.openai_api_key
        model = await _model_id(client, base, key)
        total = len(cases) * len(arms) * args.n
        print(f"모델: {model}")
        print(f"케이스 {len(cases)}종 x arm {len(arms)}개 x {args.n}회 = 호출 {total}건")
        print(f"케이스: {', '.join(name for name, _ in cases)}\n")

        results: dict[str, list[dict]] = {}
        for arm in arms:
            template, shots = ARMS[arm]
            messages = shot_messages(shots, blocks_only=arm in _BLOCKS_ONLY)
            rows: list[dict] = []
            for case_name, raw_metrics in cases:
                metrics = derive(raw_metrics)
                user_text, expected = _user_text(template, metrics)
                for _ in range(args.n):
                    started = time.monotonic()
                    try:
                        # 케이스 이름을 행에 남긴다. --cases 로 일부만 돌리기 시작하면서
                        # "행 순서로 케이스를 복원" 이 더 이상 안전하지 않다.
                        rows.append(
                            {
                                "_case": case_name,
                                **await asyncio.wait_for(
                                    _one(
                                        client,
                                        base,
                                        key,
                                        model,
                                        user_text,
                                        metrics,
                                        expected,
                                        messages,
                                    ),
                                    timeout=_CALL_CEILING,
                                ),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 — 한 건 실패로 측정을 멈추지 않는다
                        # 걸린 시간을 반드시 남긴다. 2026-11-06 에 예외 행에만 `_took` 이
                        # 없어서 64 분을 붙잡은 소켓 두 개가 집계에서 0 초로 보였다.
                        rows.append(
                            {
                                "_case": case_name,
                                "parsed": False,
                                "_took": time.monotonic() - started,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
            results[arm] = rows
            parsed = [r for r in rows if r.get("parsed")]
            if parsed:
                p50 = statistics.median(r["_took"] for r in parsed)
                print(f"[{arm}] n={len(rows)} · 파싱 {len(parsed)}/{len(rows)} · p50 {p50:.1f}s")
            else:
                print(f"[{arm}] 전부 실패")

    report(results, arms)

    if args.dump:
        for arm in arms:
            path = _dump_path(args.dump, arm, len(arms) > 1)
            path.write_text(
                json.dumps({"solution": results[arm]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n덤프: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
