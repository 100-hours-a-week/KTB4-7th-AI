"""BE 비동기 전환을 가정하고, 동시 요청 몇 건까지 A40(또는 지금 붙인 GPU)이 버티는지 잰다.

`devtools/bench.py` 는 지연을 재기 위해 **순차 호출**한다(AGENTS.md 명령어 표에 명시). 이
스크립트는 반대로 동시성 레벨(`--concurrency`)마다 N건을 한꺼번에 쏴서, 동시성이 오를수록
건당 지연이 얼마나 늘어나는지 — BE에 제안할 "동시 발사 개수 상한"을 찾기 위한 것이다.

케이스 데이터는 `devtools/bench.py`의 `SOLUTION_CASES`/`INSIGHT_CASES`를 그대로 가져다
쓴다(중복 생성 금지). 품질 채점은 안 한다 — 그건 `bench.py`가 이미 하고 있고, 여기 목적은
속도·동시성 한계만이다.

쓰는 법 (로컬 vLLM):

    LLM_PROVIDER=openai LLM_BASE_URL=http://localhost:8000/v1 \
    LLM_MODEL=Qwen/Qwen3-32B-AWQ \
      uv run python -m devtools.concurrency_bench --concurrency 1 3 5 10 --n 20

동시성 레벨은 작은 값부터 순서대로 돈다 — 한 레벨이 끝나야 다음 레벨을 쏜다. 레벨 하나가
무너지면(에러율 급등·지연 폭주) 그보다 큰 값은 의미가 없으니 거기서 멈춰도 된다.
"""

import argparse
import asyncio
import sys
import time

import httpx

from app.core.config import settings
from app.main import app
from devtools.bench import INSIGHT_CASES, SOLUTION_CASES


def _body(kind: str, metrics: dict) -> dict:
    if kind == "solution":
        return {
            "storeId": 1024,
            "salesAnalysisId": 771,
            "targetDate": "2026-09-21",
            "triggerType": "UPLOAD",
            "metrics": metrics,
        }
    return {
        "storeId": 1024,
        "salesAnalysisId": 771,
        "targetMonth": "2026-08",
        "triggerType": "UPLOAD",
        "metrics": metrics,
        "maxInsightCount": 3,
    }


async def _fire(client: httpx.AsyncClient, path: str, body: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        started = time.perf_counter()
        try:
            res = await client.post(path, json=body, timeout=600.0)
            return {"seconds": time.perf_counter() - started, "status": res.status_code}
        except httpx.HTTPError as exc:
            return {"seconds": time.perf_counter() - started, "status": None, "error": str(exc)}


async def _run_level(
    client: httpx.AsyncClient, kind: str, path: str, cases: list, n: int, concurrency: int
) -> tuple[list[dict], float]:
    sem = asyncio.Semaphore(concurrency)
    bodies = [_body(kind, cases[i % len(cases)][1]) for i in range(n)]
    started = time.perf_counter()
    rows = await asyncio.gather(*(_fire(client, path, body, sem) for body in bodies))
    return list(rows), time.perf_counter() - started


def _report(kind: str, concurrency: int, rows: list[dict], wall: float, target_n: int) -> None:
    total = len(rows)
    errors = [r for r in rows if r["status"] != 200]
    seconds = sorted(r["seconds"] for r in rows)
    throughput = total / wall if wall > 0 else 0.0
    projected = target_n / throughput if throughput > 0 else float("inf")

    print(f"\n{'=' * 62}\n{kind}  동시성={concurrency}  n={total}\n{'=' * 62}")
    print(f"  실패              {len(errors) / total:6.1%}  ({len(errors)}/{total})")
    print(
        f"  건당 지연  p50 {seconds[total // 2]:.1f}s"
        f"   p95 {seconds[min(int(total * 0.95), total - 1)]:.1f}s"
        f"   max {seconds[-1]:.1f}s"
    )
    print(f"  전체 소요(n={total})    {wall:.1f}s   처리량 {throughput:.2f} req/s")
    print(f"  {target_n}건 환산 예상 시간    {projected / 60:.1f}분 ({projected / 3600:.2f}시간)")

    for row in errors[:3]:
        print(f"    [{row['status']}] {row.get('error', '')}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 3, 5, 10])
    parser.add_argument("--n", type=int, default=20, help="동시성 레벨당 호출 횟수")
    parser.add_argument("--endpoint", choices=["solution", "insight"], default="solution")
    parser.add_argument("--target-n", type=int, default=1000, help="환산 기준 매장 수")
    args = parser.parse_args()

    cases, path = (
        (SOLUTION_CASES, "/internal/v1/ai/solutions/generate")
        if args.endpoint == "solution"
        else (INSIGHT_CASES, "/internal/v1/ai/sales-insights")
    )

    print(f"모델: {settings.llm_model}   provider: {settings.llm_provider}")
    print(f"base_url: {settings.llm_base_url or '(기본)'}")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bench") as client:
        for concurrency in args.concurrency:
            rows, wall = await _run_level(client, args.endpoint, path, cases, args.n, concurrency)
            _report(args.endpoint, concurrency, rows, wall, args.target_n)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
