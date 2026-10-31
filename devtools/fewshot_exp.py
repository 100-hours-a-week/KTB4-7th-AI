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
from app.services.solution_focus import assign, derive
from devtools import grade
from devtools.bench import SOLUTION_CASES
from devtools.fewshot_shots import SHOTS_V2, SHOTS_V3

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

# arm 이름 → (USER 템플릿, 예시 쌍)
ARMS: dict[str, tuple[str, list]] = {
    "A_현행": (prompt._USER, []),
    "B_예시추가": (prompt._USER.replace(_BAN, _BAN + "\n" + _PLAYBOOK), []),
    "C_금지제거_예시만": (prompt._USER.replace(_BAN, _PLAYBOOK), []),
    "D_fewshot1": (prompt._USER, SHOTS_V2[:1]),
    "D_fewshot2": (prompt._USER, SHOTS_V2),
    "D_fewshot3": (prompt._USER, SHOTS_V3),
}

KEYS = [
    "공허한_조언_없음",
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


def shot_messages(shots: list) -> list[dict]:
    """예시를 user/assistant 대화 쌍으로 만든다.

    프롬프트 문장에 끼우지 않는다 — 실제 호출과 같은 모양(근거 블록이 들어오고 카드 JSON 이
    나간다)을 그대로 시연해야 JSON 봉투·필드 관계·카드 간 구조까지 전달된다.

    근거 블록은 `prompt.build` 로 만든다. 사람이 쓴 블록을 쓰면 실제 호출과 모양이 어긋난다.
    """
    messages: list[dict] = []
    for metrics, output in shots:
        focus = assign(derive(metrics))
        messages.append(
            {"role": "user", "content": prompt.build(focus, "2026-10-21", "수요일", False)}
        )
        messages.append({"role": "assistant", "content": json.dumps(output, ensure_ascii=False)})
    return messages


async def _model_id(client: httpx.AsyncClient, base: str, key: str) -> str:
    """vLLM 은 Pod 를 다시 띄우면 모델 이름이 바뀔 수 있어 서버에 물어본다."""
    response = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
    response.raise_for_status()
    return response.json()["data"][0]["id"]


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
    return row


def _user_text(template: str, metrics: dict) -> tuple[str, int]:
    focus = assign(metrics)
    expected = len(focus) or grade.MAX_CARDS
    blocks = "\n\n".join(
        f"[카드 {index} 근거]\n{json.dumps(item, ensure_ascii=False)}"
        for index, item in enumerate(focus, start=1)
    )
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
                for key, value in row.items()
                if isinstance(value, bool) and key not in grade.MEASURE_ONLY
            )
            for row in parsed
        ]
        rate = sum(passed) / len(passed) * 100 if passed else float("nan")
        line += f"{rate:>19.1f}%"
    print(line)


def _dump_path(dump: str, arm: str, many: bool) -> pathlib.Path:
    path = pathlib.Path(dump)
    return path.with_suffix(f".{arm}{path.suffix}") if many else path


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default="A_현행,D_fewshot2,D_fewshot3")
    parser.add_argument("--n", type=int, default=5, help="arm·케이스당 반복")
    parser.add_argument("--dump", help="judge.py 가 읽을 덤프 경로")
    args = parser.parse_args()

    arms = [a for a in args.arms.split(",") if a]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        raise SystemExit(f"모르는 arm: {unknown} — 가능한 값 {list(ARMS)}")

    base = (settings.llm_base_url or "").rstrip("/")
    if not base:
        raise SystemExit("LLM_BASE_URL 이 비어 있다 — Pod 주소를 .env 에 넣어라")
    _check_templates()
    for arm in arms:
        validate(ARMS[arm][1])

    async with httpx.AsyncClient(timeout=180.0) as client:
        key = settings.openai_api_key
        model = await _model_id(client, base, key)
        total = len(SOLUTION_CASES) * len(arms) * args.n
        print(f"모델: {model}")
        print(f"케이스 {len(SOLUTION_CASES)}종 x arm {len(arms)}개 x {args.n}회 = 호출 {total}건\n")

        results: dict[str, list[dict]] = {}
        for arm in arms:
            template, shots = ARMS[arm]
            messages = shot_messages(shots)
            rows: list[dict] = []
            for _, raw_metrics in SOLUTION_CASES:
                metrics = derive(raw_metrics)
                user_text, expected = _user_text(template, metrics)
                for _ in range(args.n):
                    try:
                        rows.append(
                            await _one(
                                client, base, key, model, user_text, metrics, expected, messages
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 — 한 건 실패로 측정을 멈추지 않는다
                        rows.append({"parsed": False, "error": f"{type(exc).__name__}: {exc}"})
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
