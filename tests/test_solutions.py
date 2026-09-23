import json

import httpx

from app.clients import llm
from app.main import app

REQUEST_BODY = {
    "storeId": 1024,
    "salesAnalysisId": 771,
    "targetDate": "2026-08-31",  # 월요일
    "triggerType": "UPLOAD",
    "metrics": {
        "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
        "predictedSalesToday": 1250000,
        "hourlyProfile": [
            {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
            {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
        ],
        "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
        "reviewSummary": None,
    },
}

LLM_SUCCESS = json.dumps(
    {
        "solutionCards": [
            {
                "rankNo": 1,
                "title": "평일 14~17시 프로모션 진행",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "오후 비피크 시간대 방문 유도를 위해...",
                "evidence": "평일 14시 매출이 주말 대비 크게 낮습니다.",
            }
        ]
    },
    ensure_ascii=False,
)

LLM_SUCCESS_NO_EVIDENCE = json.dumps(
    {
        "solutionCards": [
            {
                "rankNo": 1,
                "title": "평일 14~17시 프로모션 진행",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "오후 비피크 시간대 방문 유도를 위해...",
            }
        ]
    },
    ensure_ascii=False,
)


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/solutions/generate", json=body)


async def test_정상_요청이_솔루션카드를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["message"]
    assert body["data"]["targetDate"] == "2026-08-31"
    assert body["data"]["solutionCards"][0]["rankNo"] == 1
    assert body["data"]["solutionCards"][0]["summaryText"]
    evidence = body["data"]["solutionCards"][0]["evidence"]
    assert evidence == "평일 14시 매출이 주말 대비 크게 낮습니다."
    assert body["data"]["modelVersion"]
    assert "promptVersion" not in body["data"]


async def test_evidence_없는_응답도_200이고_evidence는_null이다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return LLM_SUCCESS_NO_EVIDENCE

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["solutionCards"][0]["evidence"] is None


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "metrics"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]


async def test_LLM_파싱이_계속_실패하면_500_이고_1회만_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return "이건 JSON이 아닙니다"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "최초 시도 + 재시도 1회 = 2번 호출되어야 한다"


async def test_모델이_JSON을_코드펜스로_감싸도_파싱된다(monkeypatch):
    """실제 Claude 는 프롬프트에 "JSON만 출력" 이라고 써도 ```json 펜스를 붙여 내려준다.

    2026-09-21 실호출(devtools/llm_smoke.py)에서 발견 — 이 때문에 두 번 다 파싱에 실패해
    500 이 났다. 단위 테스트는 전부 순수 JSON 만 흘려서 못 잡던 구멍이다.
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return f"```json\n{LLM_SUCCESS}\n```"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["solutionCards"][0]["rankNo"] == 1


def _cards(*specs) -> str:
    return json.dumps(
        {
            "solutionCards": [
                {
                    "rankNo": rank,
                    "title": title,
                    "summaryText": "요약",
                    "detailText": "상세",
                    "evidence": "근거",
                }
                for rank, title in specs
            ]
        },
        ensure_ascii=False,
    )


async def test_rankNo가_겹치면_재시도한다(monkeypatch):
    """BE 의 UNIQUE (solution_bundle_id, rank_no) 를 위반해 묶음 전체가 저장되지 않는다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "A"), (1, "B"), (2, "C"))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert [c["rankNo"] for c in res.json()["data"]["solutionCards"]] == [1, 2, 3]
    assert len(calls) == 2


async def test_title이_200자를_넘으면_재시도한다(monkeypatch):
    """ERD solutions.title 이 VARCHAR(200) 이라 BE INSERT 에서 터진다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _cards((1, "가" * 201))
        return _cards((1, "A"), (2, "B"), (3, "C"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(calls) == 2


async def test_카드가_3장보다_적으면_재시도하되_버리지는_않는다(monkeypatch):
    """500 으로 그날 솔루션을 통째로 잃는 것보다 2장이라도 내보내는 편이 낫다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        calls.append(1)
        return _cards((1, "A"), (2, "B"))

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(res.json()["data"]["solutionCards"]) == 2
    assert len(calls) == 2, "3장이 아니면 한 번 더 시도해야 한다"


async def test_카드가_0장이면_500이다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000) -> str:
        return json.dumps({"solutionCards": []})

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)
    assert res.status_code == 500


async def test_vsPrevPeriod_가_null_이어도_422가_아니다(monkeypatch):
    """BE 는 인사이트 3곳만 보고했지만 솔루션도 같은 구조라 같이 깨졌다.

    인사이트만 고치면 첫 업로드 매장은 인사이트는 나오는데 솔루션에서 422 가 난다 —
    출시 첫날 바로 드러나는 경로다(2026-09-23 재현).
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    body = json.loads(json.dumps(REQUEST_BODY))
    body["metrics"]["salesSummary"]["vsPrevPeriod"] = None
    body["metrics"]["categoryBreakdown"][0]["vsPrevPeriod"] = None

    res = await _post(body)

    assert res.status_code == 200
