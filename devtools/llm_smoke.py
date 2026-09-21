"""실제 Claude API 로 솔루션·인사이트·챗봇을 한 번씩 호출해 응답을 검증한다.

테스트는 전부 `llm.complete` 를 monkeypatch 하므로 실제 호출 경로(인증·모델명·응답 파싱)는
pytest 로 검증되지 않는다. 이 스크립트가 그 구멍을 메운다.

    uv run python -m devtools.llm_smoke              # 솔루션·인사이트
    uv run python -m devtools.llm_smoke --with-chat  # 챗봇까지 (스텁 BE 필요)

챗봇은 BE 툴을 호출하므로 다른 터미널에서 먼저 띄운다:

    uv run python devtools/stub_backend.py

요금이 발생한다. 엔드포인트당 1회만 호출한다.
"""

import argparse
import asyncio
import json
import sys

import httpx

from app.core.config import settings
from app.main import app

METRICS = {
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
    "reviewSummary": None,
}


class Failed(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failed(message)


async def _post(client: httpx.AsyncClient, path: str, body: dict) -> httpx.Response:
    return await client.post(path, json=body, timeout=120.0)


async def solutions(client: httpx.AsyncClient) -> dict:
    res = await _post(
        client,
        "/internal/v1/ai/solutions/generate",
        {
            "storeId": 1024,
            "salesAnalysisId": 771,
            "targetDate": "2026-09-21",
            "triggerType": "UPLOAD",
            "metrics": METRICS,
        },
    )
    check(res.status_code == 200, f"HTTP {res.status_code}: {res.text[:300]}")
    data = res.json()["data"]
    cards = data["solutionCards"]
    check(len(cards) == 3, f"카드가 3장이 아니다: {len(cards)}장")
    check(
        sorted(c["rankNo"] for c in cards) == [1, 2, 3],
        f"rankNo 가 1·2·3 이 아니다: {[c['rankNo'] for c in cards]}",
    )
    check(all(c["title"] and c["summaryText"] and c["detailText"] for c in cards), "빈 필드가 있다")
    check(len({c["title"] for c in cards}) == 3, "제목이 중복된다")
    check(bool(data["modelVersion"]), "modelVersion 이 비었다")
    return data


async def insights(client: httpx.AsyncClient) -> dict:
    res = await _post(
        client,
        "/internal/v1/ai/sales-insights",
        {
            "storeId": 1024,
            "salesAnalysisId": 771,
            "targetMonth": "2026-08",
            "triggerType": "UPLOAD",
            "metrics": METRICS,
            "maxInsightCount": 3,
        },
    )
    check(res.status_code == 200, f"HTTP {res.status_code}: {res.text[:300]}")
    body = res.json()
    check(body["status"] == "COMPLETED", f"status={body['status']}")
    items = body["data"]["insights"]
    check(1 <= len(items) <= 3, f"인사이트 개수가 1~3 이 아니다: {len(items)}개")
    check(all(isinstance(t, str) and t.strip() for t in items), "빈 문자열이 있다")
    return body["data"]


async def chat(client: httpx.AsyncClient) -> str:
    res = await _post(
        client,
        "/internal/v1/ai/chat/messages",
        {
            "userId": 7,
            "storeId": 1024,
            "question": "이번 달 매출이 지난달보다 어땠어?",
            "history": [],
            "context": [
                {
                    "rankNo": 1,
                    "title": "평일 14~17시 프로모션",
                    "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                    "detailText": "14시~17시 아메리카노 20% 할인을 진행하세요.",
                    "evidence": "평일 14시 매출이 주말 대비 낮습니다.",
                }
            ],
        },
    )
    check(res.status_code == 200, f"HTTP {res.status_code}: {res.text[:300]}")

    answer = ""
    saw_done = False
    for line in res.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            saw_done = True
            continue
        event = json.loads(payload)
        check(event["event"] == "answerChunk", f"예상 밖 이벤트: {event['event']}")
        answer += event["data"]["content"]

    check(saw_done, "[DONE] 이벤트가 없다")
    check(bool(answer.strip()), "답변이 비어 있다")
    return answer


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-chat", action="store_true", help="챗봇까지 검증 (스텁 BE 필요)")
    args = parser.parse_args()

    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY 가 없다. .env 에 넣고 다시 실행한다.")
        return 1

    print(f"모델: {settings.llm_model}\n")

    steps = [("솔루션", solutions), ("인사이트", insights)]
    if args.with_chat:
        steps.append(("챗봇", chat))

    transport = httpx.ASGITransport(app=app)
    failures = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
        for name, step in steps:
            try:
                result = await step(client)
            except Failed as exc:
                print(f"[FAIL] {name} — {exc}\n")
                failures += 1
            except Exception as exc:
                print(f"[FAIL] {name} — {type(exc).__name__}: {exc}\n")
                failures += 1
            else:
                print(f"[OK] {name}")
                print(json.dumps(result, ensure_ascii=False, indent=2)[:1200], "\n")

    print("모두 통과" if not failures else f"{failures}건 실패")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
