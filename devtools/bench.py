"""프롬프트·모델 변경의 효과를 실호출 N 회로 측정한다.

왜 있나. `devtools/llm_smoke.py` 는 엔드포인트당 1 회만 부르고(표본 1 개),
`devtools/grade.py` 는 채점만 하고 호출은 안 한다. 그 사이가 비어 있어서 지금까지 측정은
코랩 노트북에서 손으로 프롬프트를 조립해 돌렸다 — 2026-10-07(#123)에 프롬프트 입력이
`metrics` 에서 `focus` 로 바뀌었으니 그 노트북은 이제 폐기된 구조를 재고 있을 수 있다.
같은 사고가 한 번 있었다(채점기가 폐기된 규칙을 계속 재서 "Claude 가 60% 어긴다"는
틀린 결론). 그래서 이 스크립트는 프롬프트를 조립하지 않고 **서비스를 그대로 호출한다.**

두 열을 낸다.
- **모델(1회차)**: `llm.complete` 의 첫 응답. 코랩에서 재던 값과 같은 성격이다.
- **서비스(최종)**: 치환(#124)·재시도(#119·#126)를 거쳐 BE 로 나가는 응답. 점주가 보는 값.

둘이 벌어지는 폭이 재시도가 실제로 사 주는 양이다. 그리고 재시도가 두 번 다 실패하면
서비스는 500 을 내므로(`MAX_RETRY = 1`) 그 비율도 같이 센다 — 어림 금액이 든 카드보다
"솔루션이 없는 날"이 점주에게 더 나쁠 수 있어서, 고르기 전에 숫자가 필요하다.

쓰는 법 (로컬 vLLM):

    LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:8000/v1 \
    LLM_MODEL=Qwen/Qwen3-32B-AWQ \
      uv run python -m devtools.bench --n 50

Claude 와 비교하려면 환경변수 없이 돌린다(`.env` 의 ANTHROPIC_API_KEY 를 쓴다).
요금·GPU 시간이 발생한다. 지연을 재야 하므로 **순차 호출**이다 — n=50 이면 케이스당
50 회, 한 호출 30 초면 솔루션만 1 시간 반이다. 먼저 `--n 3` 으로 한 번 확인한다.

주의. `grade.py` 의 수치 검사는 전체 `metrics` 를 기준으로 한다. 2026-10-07 부터 카드는
배정된 `focus`(metrics 의 부분집합)만 보고 쓰므로, 다른 카드 몫의 수치를 가져다 써도
`수치_정확` 은 통과한다. `카드_지표_중복없음` 이 그걸 따로 잡는다.
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
import unicodedata
from collections import Counter

import httpx

from app.clients import llm
from app.core.config import settings
from app.main import app
from devtools import grade

# ── 케이스 ────────────────────────────────────────────────────────────
# 지표 모양이 달라지면 focus 배정이 달라지고 카드 성격도 달라진다. 셋뿐이지만 서로 다른
# 경로를 지난다 — 마지막 것은 카드 2 장만 나가는 경로다(`wanted = len(focus)`).

SOLUTION_CASES = [
    (
        "기본",
        {
            "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
            "predictedSalesToday": 1250000,
            "hourlyProfile": [
                {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
                {"dayType": "WEEKDAY", "hour": 18, "amount": 210000},
                {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
            ],
            "categoryBreakdown": [
                {"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12},
                {"name": "디저트", "share": 0.21, "vsPrevPeriod": 0.08},
            ],
        },
    ),
    (
        "시간대격차큼",
        {
            "salesSummary": {"netSales": 2470300, "vsPrevPeriod": 0.034},
            "hourlyProfile": [
                {"dayType": "WEEKDAY", "hour": 9, "amount": 8200},
                {"dayType": "WEEKDAY", "hour": 12, "amount": 412000},
                {"dayType": "WEEKDAY", "hour": 15, "amount": 61500},
                {"dayType": "WEEKDAY", "hour": 20, "amount": 19800},
            ],
            "categoryBreakdown": [
                {"name": "커피", "share": 0.44, "vsPrevPeriod": 0.012},
                {"name": "논커피", "share": 0.31, "vsPrevPeriod": -0.007},
                {"name": "베이커리", "share": 0.25, "vsPrevPeriod": 0.004},
            ],
        },
    ),
    (
        # hourlyProfile 이 비면 focus 가 2 개가 되고 카드도 2 장만 나간다. BE 가 시간대
        # 집계를 못 보내는 경우가 계약상 가능한데(2026-09-16) 아직 측정된 적이 없다.
        "시간대없음",
        {
            "salesSummary": {"netSales": 842000, "vsPrevPeriod": -0.287},
            "hourlyProfile": [],
            "categoryBreakdown": [
                {"name": "커피", "share": 0.71, "vsPrevPeriod": -0.31},
                {"name": "디저트", "share": 0.29, "vsPrevPeriod": -0.19},
            ],
        },
    ),
]

INSIGHT_CASES = [
    (
        "기본",
        {
            "salesSummary": {
                "totalSales": 7920000,
                "menuSales": 7480000,
                "orderCount": 923,
                "averageOrderValue": 8581,
                "vsPrevPeriod": 0.042,
            },
            "categorySales": [
                {
                    "categoryName": "커피",
                    "menuSales": 3120000,
                    "ratio": 0.417,
                    "vsPrevPeriod": -0.044,
                }
            ],
        },
    ),
    (
        # 0.138 → "14%" 로 반올림하면 조용히 틀린다. 지표를 여섯 종 주면 `수치_정확` 이
        # 68% 로 떨어졌던 그 조건이다(2026-10-06, n=48).
        "지표많음",
        {
            "salesSummary": {
                "totalSales": 12403500,
                "menuSales": 11890200,
                "orderCount": 1486,
                "averageOrderValue": 8001,
                "vsPrevPeriod": 0.138,
            },
            "salesTrend": [
                {"date": "2026-09-01", "menuSales": 380400, "orderCount": 48},
                {"date": "2026-09-15", "menuSales": 421900, "orderCount": 53},
                {"date": "2026-09-30", "menuSales": 356200, "orderCount": 44},
            ],
            "weekdaySales": [
                {"dayOfWeek": "MON", "menuSales": 1420300, "orderCount": 181},
                {"dayOfWeek": "SAT", "menuSales": 2104700, "orderCount": 252},
            ],
            "hourlySales": [
                {"dayType": "WEEKDAY", "hour": 8, "menuSales": 892000, "orderCount": 142},
                {"dayType": "WEEKDAY", "hour": 14, "menuSales": 2310400, "orderCount": 287},
            ],
            "categorySales": [
                {
                    "categoryName": "커피",
                    "menuSales": 5940100,
                    "ratio": 0.4996,
                    "vsPrevPeriod": 0.091,
                },
                {
                    "categoryName": "디저트",
                    "menuSales": 2378000,
                    "ratio": 0.2,
                    "vsPrevPeriod": -0.023,
                },
            ],
            "menuRankings": [
                {
                    "rank": 1,
                    "menuName": "아이스 아메리카노",
                    "menuSales": 3104200,
                    "quantity": 912,
                    "ratio": 0.2611,
                },
                {
                    "rank": 2,
                    "menuName": "카페라떼",
                    "menuSales": 1420800,
                    "quantity": 331,
                    "ratio": 0.1195,
                },
            ],
        },
    ),
]

# ── 계측 ──────────────────────────────────────────────────────────────
# 서비스가 `from app.clients import llm` 으로 모듈을 들고 `llm.complete(...)` 를 부르므로
# 모듈 속성을 바꿔치면 솔루션·인사이트 양쪽이 같이 잡힌다.

_raws: list[str] = []
_original_complete = llm.complete


async def _recording_complete(*args, **kwargs) -> str:
    raw = await _original_complete(*args, **kwargs)
    _raws.append(raw)
    return raw


SKIP_KEYS = {"cards", "insights", "error"}


def _width(text: str) -> int:
    """한글은 터미널에서 두 칸을 쓴다 — len() 으로 맞추면 표가 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def _checks(result: dict) -> dict[str, bool]:
    return {key: bool(value) for key, value in result.items() if key not in SKIP_KEYS}


async def _one(
    client: httpx.AsyncClient, path: str, body: dict, metrics: dict, grader, payload_key: str
) -> dict:
    """한 번 호출하고 1회차 원문과 최종 응답을 각각 채점한다."""
    _raws.clear()
    started = time.perf_counter()
    res = await client.post(path, json=body, timeout=600.0)
    elapsed = time.perf_counter() - started

    if 400 <= res.status_code < 500:
        # 요청이 스키마와 안 맞는 것은 모델 품질이 아니라 이 스크립트의 케이스가 틀린 거다.
        # 통계에 섞으면 통과율이 낮게 나오고 원인을 모델로 오해한다.
        raise SystemExit(
            f"\n케이스가 스키마와 맞지 않는다 (HTTP {res.status_code}) — bench.py 를 고쳐야 한다:\n"
            f"{res.text[:500]}"
        )

    row: dict = {"status": res.status_code, "seconds": elapsed, "attempts": len(_raws)}
    row["model"] = _checks(grader(_raws[0], metrics)) if _raws else {"parsed": False}

    if res.status_code != 200:
        row["service"] = {}  # 모든 항목 실패로 센다
        row["error"] = res.text[:200]
        return row

    items = res.json()["data"].get(payload_key)
    if not items:
        row["service"] = {}
        row["error"] = f"{payload_key} 가 비었다: {res.text[:200]}"
        return row

    row["service"] = _checks(grader(json.dumps({payload_key: items}), metrics))
    return row


def _rates(rows: list[dict]) -> tuple[list[str], dict[str, tuple[float, float]], float, float]:
    """항목별 (모델, 서비스) 통과율과 전항목 통과율. 분모는 항상 전체 요청 수다.

    행에 없는 항목은 실패로 센다 — 500 과 파싱 실패는 검사 결과가 아예 없기 때문에,
    있는 항목만 평균하면 "응답이 안 온 요청"이 통계에서 사라져 숫자가 좋아 보인다.
    """
    total = len(rows)
    keys: dict[str, None] = {}
    for row in rows:
        keys.update(dict.fromkeys(row["model"]))
        keys.update(dict.fromkeys(row["service"]))

    per_key = {
        key: (
            sum(1 for r in rows if r["model"].get(key)) / total,
            sum(1 for r in rows if r["service"].get(key)) / total,
        )
        for key in keys
    }
    all_model = sum(1 for r in rows if all(r["model"].get(k) for k in keys)) / total
    all_service = sum(1 for r in rows if all(r["service"].get(k) for k in keys)) / total
    return list(keys), per_key, all_model, all_service


def _report(name: str, rows: list[dict]) -> None:
    total = len(rows)
    failed = [r for r in rows if r["status"] != 200]
    seconds = sorted(r["seconds"] for r in rows)
    attempts = [r["attempts"] for r in rows]

    print(f"\n{'=' * 62}\n{name}  n={total}\n{'=' * 62}")
    codes = Counter(r["status"] for r in failed)
    detail = " ".join(f"{code}x{count}" for code, count in sorted(codes.items()))
    print(
        f"  응답 실패         {len(failed) / total:6.1%}  ({len(failed)}/{total})"
        + (f"  {detail}" if detail else "")
    )
    once = sum(1 for a in attempts if a == 1)
    print(f"  호출 1회로 끝     {once / total:6.1%}  (평균 {statistics.mean(attempts):.2f}회)")
    print(
        f"  지연  p50 {seconds[len(seconds) // 2]:.1f}s"
        f"   p95 {seconds[min(int(total * 0.95), total - 1)]:.1f}s"
        f"   max {seconds[-1]:.1f}s"
    )

    # 키 순서는 처음 파싱된 결과가 정한다. 파싱 실패한 행은 parsed 하나뿐이라 순서를 망치지 않는다.
    keys, per_key, all_model, all_service = _rates(rows)

    width = max(_width(k) for k in keys)
    rule = "-" * (width + 31)
    print(f"\n  {_pad('항목', width)}   모델(1회차)   서비스(최종)")
    print(f"  {rule}")
    for key in keys:
        model, service = per_key[key]
        mark = "  <--" if service < 0.95 else ""
        print(f"  {_pad(key, width)}   {f'{model:.1%}':>11}   {f'{service:.1%}':>12}{mark}")

    print(f"  {rule}")
    print(f"  {_pad('전항목', width)}   {f'{all_model:.1%}':>11}   {f'{all_service:.1%}':>12}")
    print("\n  출하 판정은 서비스(최종) 전항목이다 — 실패한 응답은 모든 항목 실패로 셌다.")

    for row in rows:
        if "error" in row:
            print(f"\n  [{row['status']}] {row['error']}")
            break


async def _run(client: httpx.AsyncClient, kind: str, n: int) -> list[dict]:
    rows = []
    if kind == "solution":
        cases, path, grader, key = (
            SOLUTION_CASES,
            "/internal/v1/ai/solutions/generate",
            grade.grade_solution,
            "solutionCards",
        )
    else:
        cases, path, grader, key = (
            INSIGHT_CASES,
            "/internal/v1/ai/sales-insights",
            grade.grade_insight,
            "insights",
        )

    for case_name, metrics in cases:
        for i in range(n):
            if kind == "solution":
                body = {
                    "storeId": 1024,
                    "salesAnalysisId": 771,
                    "targetDate": "2026-09-21",
                    "triggerType": "UPLOAD",
                    "metrics": metrics,
                }
            else:
                body = {
                    "storeId": 1024,
                    "salesAnalysisId": 771,
                    "targetMonth": "2026-08",
                    "triggerType": "UPLOAD",
                    "metrics": metrics,
                    "maxInsightCount": 3,
                }
            rows.append(await _one(client, path, body, metrics, grader, key))
            print(f"\r  {kind} {case_name} {i + 1}/{n}   ", end="", flush=True)
        print()
    return rows


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="케이스당 호출 횟수")
    parser.add_argument("--endpoint", choices=["solution", "insight", "both"], default="both")
    args = parser.parse_args()

    # 호출마다 httpx 가 한 줄씩 찍어 진행 표시를 덮는다
    logging.getLogger("httpx").setLevel(logging.WARNING)

    print(f"모델: {settings.llm_model}   provider: {settings.llm_provider}")
    print(f"base_url: {settings.llm_base_url or '(기본)'}")
    print(
        f"프롬프트 판: 솔루션 {grade.TARGET_SOLUTION_VERSION}"
        f" / 인사이트 {grade.TARGET_INSIGHT_VERSION}"
    )

    llm.complete = _recording_complete
    kinds = ["solution", "insight"] if args.endpoint == "both" else [args.endpoint]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
        for kind in kinds:
            rows = await _run(client, kind, args.n)
            _report("솔루션" if kind == "solution" else "인사이트", rows)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
