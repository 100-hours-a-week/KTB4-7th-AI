"""솔루션 카드가 "데이터 없이도 할 수 있는 말" 인지 모델로 판정한다.

왜 필요한가. `grade.py::_VAGUE_ACTION` 은 `마케팅|홍보|프로모션 + 강화|개선` 류 **표현**만
본다. 그래서 표현은 구체적인데 내용이 당연한 조언 — "한가한 시간은 정리에 쓰세요" — 은
통과한다. 공허함은 패턴이 아니라 의미 문제라 정규식으로는 닫히지 않는다.

2026-10-29 실측(출력 237 장)에서 그 격차가 드러났다.

    arm             정규식 `공허한_조언_없음`   judge `specific`
    A 현행                   10.0%                 5.9%
    B 예시추가                29.6%                 6.6%
    C 금지제거+예시만          25.9%                 1.3%

축별로는 다섯 중 **네 축이 100% obvious** 였고(카테고리·매출총액·메뉴·날씨), 데이터가
결론을 바꾼 축은 `hourlyProfile` 하나였다. `specific` 판정의 이유가 하나로 모인다 —
"통상적인 점심 피크가 아니라 18 시에 몰린다는 사실은 이 매장 데이터로만 알 수 있다".

판정 기준을 하나로 좁힌다. **이 조언을 하려면 이 매장의 지표를 봐야 하는가.** 문장이
구체적으로 들리는지가 아니라 결론에 데이터가 필요한지를 본다.

GPU 가 아니라 Claude 로 돌린다 — vLLM 이 꺼져 있어도 쓸 수 있고, 판정자를 측정 대상과
다른 모델로 두는 편이 낫다.

입력은 `bench.py --dump` 가 남긴 파일이다. 행에 케이스 이름이 없어서 순서로 복원한다
(`bench._run` 이 케이스별로 n 번씩 차례로 쌓는다) — bench 의 케이스 수가 바뀌면 여기도
같이 봐야 한다.

    uv run python -m devtools.bench --n 20 --dump bench.json
    uv run python -m devtools.judge --dump bench.json
"""

import argparse
import asyncio
import json
import pathlib
import sys

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.services.solution_focus import assign, derive
from devtools.bench import SOLUTION_CASES

DEFAULT_MODEL = "claude-opus-5-5"
_CONCURRENCY = 6

SYSTEM = """당신은 카페 매출 분석 서비스의 솔루션 카드를 심사합니다.

판정할 것은 하나입니다 — **이 조언을 하려면 이 매장의 매출 데이터를 봐야 하는가.**

데이터를 안 보고도 어느 카페에나 똑같이 할 수 있는 말이면 `obvious`,
이 매장의 숫자를 봐야만 나올 수 있는 말이면 `specific` 입니다.

문장이 구체적으로 **들리는지**가 아니라, 그 결론에 **데이터가 필요한지**를 보세요.
숫자를 인용했는데 결론이 데이터와 무관하게 똑같다면 그건 `obvious` 입니다.

판정 예시:

obvious  "붐비는 점심 전에 준비를 끝내고, 한가한 시간은 정리에 쓰세요"
         → 모든 카페가 이미 그렇게 한다. 데이터가 필요 없다
obvious  "마케팅을 강화하세요"
obvious  "실내 고객 유입을 유도할 수 있는 조치를 마련하세요"
obvious  "매출 감소 원인을 분석하고 대응 전략을 재조정하세요"
obvious  "오늘은 재료를 평소보다 넉넉하게 준비하세요"
         → "많이 팔릴 것 같으면 많이 준비하라" 는 데이터 없이도 자명하다
specific "오후 교대와 저녁 준비를 16시에 몰아 두세요"
         → 피크가 두 번이고 그 사이 골짜기가 16시라는 걸 데이터로만 안다
specific "점심 직전인 11시 30분 전부터 계산대 앞에 디저트를 눈에 띄게 진열하세요"
specific "비 온 날 덜 팔리는 아이스 음료의 얼음 발주를 줄이세요"

카드마다 판정과 한 줄 이유를 주세요. 설명 없이 JSON만 출력하세요."""

_USER = """카드 {count}장을 판정하세요.

{cards}

{{"verdicts":[{{"rankNo":1,"verdict":"obvious|specific","reason":"한 줄"}}]}}"""


def _axis(metrics: dict, rank: int) -> str:
    """그 카드에 배정된 근거 축. 서비스와 같은 순서로 복원한다."""
    focus = assign(derive(metrics))
    return next(iter(focus[rank - 1]), "?") if 0 < rank <= len(focus) else "?"


def _cards_text(cards: list[dict]) -> str:
    return "\n\n".join(
        f"[카드 {card.get('rankNo')}]\n"
        f"title: {card.get('title')}\n"
        f"summaryText: {card.get('summaryText')}\n"
        f"detailText: {card.get('detailText')}"
        for card in cards
    )


def load_jobs(dump: dict, limit: int = 0) -> list[tuple[str, dict, list[dict]]]:
    """(케이스 이름, 지표, 카드들). 케이스는 행 순서로 복원한다."""
    rows = dump.get("solution") or []
    if not rows:
        raise SystemExit("덤프에 solution 행이 없다 — bench.py --endpoint solution 으로 떠야 한다")
    if len(rows) % len(SOLUTION_CASES):
        raise SystemExit(
            f"행 {len(rows)} 개가 케이스 {len(SOLUTION_CASES)} 종으로 나눠지지 않는다 — "
            "bench 의 케이스 구성이 바뀌었는지 확인하라"
        )
    per_case = len(rows) // len(SOLUTION_CASES)
    jobs = []
    for index, row in enumerate(rows):
        cards = row.get("sample")
        if not cards:
            continue
        name, metrics = SOLUTION_CASES[index // per_case]
        jobs.append((name, metrics, cards))
    return jobs[:limit] if limit else jobs


async def _judge(client: AsyncAnthropic, model: str, cards: list[dict]):
    response = await client.messages.create(
        model=model,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _USER.format(count=len(cards), cards=_cards_text(cards)),
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)["verdicts"], response.usage


def report(verdicts: list[dict]) -> None:
    if not verdicts:
        print("판정된 카드가 없다")
        return
    obvious = sum(v["verdict"] == "obvious" for v in verdicts)
    print(f"\n카드 {len(verdicts)}장 · obvious {obvious / len(verdicts) * 100:.1f}%")
    for label, key in (("축", "axis"), ("케이스", "case")):
        print(f"\n{label:<22}{'obvious':>10}{'장수':>8}")
        for value in sorted({v[key] for v in verdicts}):
            rows = [v for v in verdicts if v[key] == value]
            share = sum(r["verdict"] == "obvious" for r in rows) / len(rows) * 100
            print(f"{value:<22}{share:>9.1f}%{len(rows):>8}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, help="bench.py --dump 가 남긴 파일")
    parser.add_argument("--out", default="judge.json", help="판정 결과를 적을 파일")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 이 개수만 (0 이면 전부)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    jobs = load_jobs(json.loads(pathlib.Path(args.dump).read_text(encoding="utf-8")), args.limit)
    print(f"호출 {len(jobs)}건 · 판정자 {args.model} (요금 발생 · GPU 는 쓰지 않는다)")

    # 키는 서비스와 같은 경로로 읽는다 — devtools 가 .env 를 따로 파싱하면 두 곳이 어긋난다.
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY 가 비어 있다 — 판정자는 Claude 로 돌린다")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    gate = asyncio.Semaphore(_CONCURRENCY)
    verdicts: list[dict] = []
    tokens = [0, 0]

    async def run(job):
        name, metrics, cards = job
        async with gate:
            try:
                decided, usage = await _judge(client, args.model, cards)
            except Exception as exc:  # 한 건 실패로 전체를 버리지 않는다
                print(f"  실패 {name}: {type(exc).__name__}: {exc}", flush=True)
                return
        tokens[0] += usage.input_tokens
        tokens[1] += usage.output_tokens
        for item in decided:
            rank = item.get("rankNo") or 0
            verdicts.append(
                {
                    "case": name,
                    "rankNo": rank,
                    "axis": _axis(metrics, rank),
                    "verdict": item.get("verdict"),
                    "reason": item.get("reason"),
                }
            )

    await asyncio.gather(*(run(job) for job in jobs))

    pathlib.Path(args.out).write_text(
        json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    report(verdicts)
    print(f"\n입력 {tokens[0]:,} · 출력 {tokens[1]:,} 토큰")
    print(f"판정 원본: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
