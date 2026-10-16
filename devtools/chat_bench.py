"""챗봇(SSE 스트리밍) 경로의 지연·툴 선택 정확도를 실호출 N회로 측정한다.

왜 있나. `devtools/bench.py`는 솔루션·인사이트의 단발 blocking 호출(`llm.complete()`)만
잰다. 챗봇은 `app/services/chat/graph.py`의 `model.astream()` → SSE로 토큰 단위
스트리밍이라 측정 축 자체가 다르다 — "답이 끝나는 시간"보다 "답이 시작되는 시간"(TTFT)이
체감 지연을 결정한다. `devtools/llm_smoke.py --with-chat`은 질의 1개로 "응답이 비어있지
않다"만 보는 스모크 테스트라 반복 측정도 품질(툴 선택)도 재지 않는다 — 이 스크립트가 그
사이를 메운다.

측정하는 두 축:
- **지연**: TTFT(첫 토큰까지) / 전체 완료까지. 각각 따로 잰다.
- **툴 선택 정확도**: `get_sales_summary`/`get_category_breakdown`/`get_hourly_profile`/
  `get_forecast` 중 기대한 도구가 실제로 불렸는지. SSE 프레임 자체엔 도구 이름이 없지만,
  `graph._build_evidence`가 도구마다 고유한 `evidence.metric`(sales_summary 등)을 붙여
  내려주므로 역매핑해서 판별한다 — 내부 구현을 훅킹하지 않고 계약(SSE 응답)만으로 잰다.

쓰는 법 (로컬 vLLM, 먼저 다른 터미널에서 `uv run python devtools/stub_backend.py`):

    LLM_PROVIDER=openai LLM_BASE_URL=http://<pod>:<port>/v1 \
    LLM_MODEL=Qwen/Qwen3-32B-AWQ LLM_DISABLE_THINKING=true \
      uv run python -m devtools.chat_bench --n 5

Claude와 비교하려면 환경변수 없이 돌린다(`.env`의 ANTHROPIC_API_KEY를 쓴다). 요금·GPU
시간이 발생한다. 지연을 재야 하므로 순차 호출이다.
"""

import argparse
import asyncio
import json
import sys
import time
import unicodedata
from collections import Counter

import httpx

from app.core.config import settings, uses_local_llm_server
from app.main import app
from app.services.chat.graph import _EVIDENCE_METRIC_NAMES

STORE_ID = 1024
USER_ID = 7
CHAT_DATE = "2026-10-16"

# metric → tool 역매핑. graph._build_evidence가 붙이는 값과 어긋나면 여기서 바로 깨진다.
_METRIC_TO_TOOL = {v: k for k, v in _EVIDENCE_METRIC_NAMES.items()}

# ── 질의 6종 ──────────────────────────────────────────────────────────
# 과거 위키 실험(Colab, qwen3-14b)의 "질의 × 정답 도구" 방식을 지금 활성화된 툴 4종
# 기준으로 다시 짰다. 5번은 컨텍스트만으로 답해야 하는 케이스(도구 호출이 없는 게 정답)다.

QUERIES = [
    ("매출요약", "이번 달 매출이 지난달보다 어땠어?", [], "get_sales_summary"),
    ("카테고리분석", "요즘 어떤 카테고리가 제일 잘 팔려?", [], "get_category_breakdown"),
    ("시간대분석", "오늘 피크 시간대가 언제야?", [], "get_hourly_profile"),
    ("매출예측", "내일 매출이 얼마나 나올 것 같아?", [], "get_forecast"),
    (
        "컨텍스트만",
        "방금 추천해준 솔루션 카드 다시 한번 요약해줄래?",
        [
            {
                "rankNo": 1,
                "title": "평일 14~17시 프로모션",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "14시~17시 아메리카노 20% 할인을 진행하세요.",
                "evidence": "평일 14시 매출이 주말 대비 낮습니다.",
            }
        ],
        None,
    ),
    ("커스텀기간", "9월 1일부터 9월 15일까지 매출이 어땠어?", [], "get_sales_summary"),
]


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


async def _one_call(client: httpx.AsyncClient, question: str, context: list) -> dict:
    """SSE를 한 번 소비하며 TTFT·전체완료시간·사용된 도구·에러를 잰다."""
    body = {
        "userId": USER_ID,
        "storeId": STORE_ID,
        "chatDate": CHAT_DATE,
        "question": question,
        "context": context,
        "history": [],
    }
    started = time.perf_counter()
    ttft: float | None = None
    tool_used: str | None = None
    error: str | None = None
    answer = ""
    saw_done = False

    async with client.stream(
        "POST", "/internal/v1/ai/chat/messages", json=body, timeout=180.0
    ) as res:
        if res.status_code != 200:
            text = await res.aread()
            raise SystemExit(
                f"\n요청이 스키마와 안 맞는다 (HTTP {res.status_code}) — chat_bench.py를 "
                f"고쳐야 한다:\n{text[:500]}"
            )
        async for line in res.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                saw_done = True
                break
            event = json.loads(payload)
            if event["event"] == "error":
                error = event["data"]["code"]
                break
            data = event["data"]
            if data["content"] and ttft is None:
                ttft = time.perf_counter() - started
            answer += data["content"]
            evidence = data.get("evidence")
            if evidence and evidence.get("metric"):
                tool_used = _METRIC_TO_TOOL.get(evidence["metric"])

    total = time.perf_counter() - started
    return {
        "ttft": ttft,
        "total": total,
        "tool_used": tool_used,
        "error": error,
        "saw_done": saw_done,
        "answer": answer,
    }


async def _check_backend() -> None:
    try:
        async with httpx.AsyncClient() as probe:
            res = await probe.get(f"{settings.backend_base_url}/health", timeout=3.0)
            res.raise_for_status()
    except Exception as exc:
        raise SystemExit(
            f"\n스텁 BE({settings.backend_base_url})에 연결할 수 없다: {exc}\n"
            "다른 터미널에서 먼저 띄운다: uv run python devtools/stub_backend.py"
        ) from exc


def _report(rows: list[dict]) -> None:
    total = len(rows)
    errors = [r for r in rows if r["error"] or not r["saw_done"]]
    ttfts = sorted(r["ttft"] for r in rows if r["ttft"] is not None)
    totals = sorted(r["total"] for r in rows)

    print(f"\n{'=' * 70}\n챗봇  n={total}  (도구 호출 유무 상관없이 전체)\n{'=' * 70}")
    codes = Counter(r["error"] for r in errors if r["error"])
    detail = " ".join(f"{code}x{count}" for code, count in sorted(codes.items()))
    print(
        f"  에러/[DONE]없음    {len(errors) / total:6.1%}  ({len(errors)}/{total})"
        + (f"  {detail}" if detail else "")
    )
    if ttfts:
        print(
            f"  TTFT(첫 토큰)      p50 {ttfts[len(ttfts) // 2]:.2f}s"
            f"   p95 {ttfts[min(int(total * 0.95), len(ttfts) - 1)]:.2f}s"
            f"   max {ttfts[-1]:.2f}s"
        )
    print(
        f"  전체 완료          p50 {totals[len(totals) // 2]:.1f}s"
        f"   p95 {totals[min(int(total * 0.95), total - 1)]:.1f}s"
        f"   max {totals[-1]:.1f}s"
    )

    by_query: dict[str, list[dict]] = {}
    for r in rows:
        by_query.setdefault(r["query_name"], []).append(r)

    width = max(_width(name) for name in by_query)
    print(f"\n  {_pad('질의', width)}   기대 도구          툴정확    TTFT p50   완료 p50")
    print(f"  {'-' * (width + 46)}")
    for name, group in by_query.items():
        expected = group[0]["expected_tool"]
        correct = sum(1 for r in group if r["tool_used"] == expected) / len(group)
        g_ttfts = sorted(r["ttft"] for r in group if r["ttft"] is not None)
        g_totals = sorted(r["total"] for r in group)
        ttft_p50 = g_ttfts[len(g_ttfts) // 2] if g_ttfts else float("nan")
        total_p50 = g_totals[len(g_totals) // 2]
        mark = "  <--" if correct < 1.0 else ""
        print(
            f"  {_pad(name, width)}   {_pad(expected or '(없음)', 16)}   "
            f"{correct:5.0%}   {ttft_p50:7.2f}s   {total_p50:7.1f}s{mark}"
        )

    wrong = next((r for r in rows if r["tool_used"] != r["expected_tool"]), None)
    if wrong:
        print(
            f"\n  툴 선택 어긴 첫 사례 [{wrong['query_name']}]: "
            f"기대={wrong['expected_tool']} 실제={wrong['tool_used']}"
        )
        print(f"    답변: {wrong['answer'][:300]}")

    err_row = next((r for r in rows if r["error"] or not r["saw_done"]), None)
    if err_row:
        print(
            f"\n  에러 첫 사례 [{err_row['query_name']}]: "
            f"error={err_row['error']}  saw_done={err_row['saw_done']}"
        )
        print(f"    답변: {err_row['answer'][:200]}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="질의당 호출 횟수")
    parser.add_argument("--dump", help="시도별 원문을 JSON으로 적을 경로")
    args = parser.parse_args()

    print(f"모델: {settings.llm_model}   provider: {settings.llm_provider}")
    print(f"base_url: {settings.llm_base_url or '(기본)'}")
    if uses_local_llm_server(settings) and not settings.llm_disable_thinking:
        print(
            "경고: 로컬 vLLM인데 LLM_DISABLE_THINKING=true가 아니다 — Qwen3는 thinking이 "
            "기본 ON이라 <think> 블록이 답변에 그대로 섞여 나올 수 있다."
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://chat-bench") as client:
        await _check_backend()

        rows: list[dict] = []
        for name, question, context, expected_tool in QUERIES:
            for attempt in range(args.n):
                result = await _one_call(client, question, context)
                result.update(query_name=name, question=question, expected_tool=expected_tool)
                rows.append(result)
                print(f"\r  {name} {attempt + 1}/{args.n}   ", end="", flush=True)
            print()

    _report(rows)

    if args.dump:
        import pathlib

        pathlib.Path(args.dump).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n  시도별 원문을 적었다: {args.dump}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
