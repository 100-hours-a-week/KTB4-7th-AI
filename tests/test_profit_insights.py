import json

import httpx

from app.clients import llm
from app.main import app

# docs/api정의서.md SALES-06 `POST /internal/v2/ai/profit-insights` 요청 예시를 며칠로 늘린 것.
REQUEST_BODY = {
    "storeId": 1,
    "period": {"startDate": "2026-09-01", "endDate": "2026-09-04"},
    "summary": {
        "totalNetAmount": 4000000,
        "ingredientCost": 1200000,
        "fixedCost": 400000,
        "netProfit": 2400000,
        "netProfitRate": 0.6,
        "previousNetProfit": 2000000,
        "netProfitChangeRate": 0.2,
    },
    "dailyProfits": [
        {"date": "2026-09-01", "netProfit": 500000},  # 화
        {"date": "2026-09-02", "netProfit": 900000},  # 수
        {"date": "2026-09-03", "netProfit": 900000},  # 목 — 수요일과 동률
        {"date": "2026-09-04", "netProfit": 100000},  # 금
    ],
    "maxInsightCount": 3,
}

LLM_SUCCESS = json.dumps(
    {"insights": ["선택 기간의 순이익은 2,400,000원이에요."]}, ensure_ascii=False
)


def _insights(*items) -> str:
    return json.dumps({"insights": list(items)}, ensure_ascii=False)


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v2/ai/profit-insights", json=body)


def _fake(monkeypatch, raw: str, calls: list | None = None):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        if calls is not None:
            calls.append(user)
        return raw

    monkeypatch.setattr(llm, "complete", fake_complete)


async def test_정상_요청이_인사이트와_message를_반환한다(monkeypatch):
    _fake(monkeypatch, LLM_SUCCESS)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    expected = json.loads(LLM_SUCCESS)
    assert res.json() == {
        "message": "순이익 인사이트를 생성했습니다.",
        "status": "COMPLETED",
        "data": expected,
    }


async def test_필수_필드가_없으면_422():
    for key in ("storeId", "period", "summary", "dailyProfits", "maxInsightCount"):
        res = await _post({k: v for k, v in REQUEST_BODY.items() if k != key})
        assert res.status_code == 422, key


async def test_비교_값이_null_이어도_422가_아니고_프롬프트에서_빠진다(monkeypatch):
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["summary"]["previousNetProfit"] = None
    body["summary"]["netProfitChangeRate"] = None

    res = await _post(body)

    assert res.status_code == 200
    assert "previousNetProfit" not in calls[0]
    assert "netProfitChangeRate" not in calls[0]


async def test_적자_음수_금액도_받는다(monkeypatch):
    _fake(monkeypatch, LLM_SUCCESS)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["summary"]["netProfit"] = -300000
    body["dailyProfits"][0]["netProfit"] = -300000

    assert (await _post(body)).status_code == 200


async def test_최고_최저_날짜와_요일을_코드가_계산해_프롬프트에_넣는다(monkeypatch):
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)

    await _post(REQUEST_BODY)

    assert "2026-09-02" in calls[0] and "수요일" in calls[0], "동률이면 가장 이른 날짜"
    assert "2026-09-04" in calls[0] and "금요일" in calls[0]


async def test_연속_증감_표현과_일별_집계를_프롬프트에서_금지한다():
    from app.prompts import profit_insight

    assert "연속" in profit_insight.SYSTEM
    assert "합계" in profit_insight.SYSTEM and "평균" in profit_insight.SYSTEM


async def test_불량_응답은_재시도_1회_후_500이다(monkeypatch):
    for raw in (
        "JSON 아님",
        _insights(),
        _insights("가", "나", "다", "라"),
        _insights("  "),
        _insights("가" * 101),
    ):
        calls: list = []
        _fake(monkeypatch, raw, calls)

        res = await _post(REQUEST_BODY)

        assert res.status_code == 500, raw
        assert len(calls) == 2, "최초 시도 + 재시도 1회"


async def test_정확히_100자는_통과한다(monkeypatch):
    _fake(monkeypatch, _insights("가" * 100))

    assert (await _post(REQUEST_BODY)).status_code == 200


async def test_매출이_0원이면_LLM을_부르지_않고_INSUFFICIENT_DATA(monkeypatch):
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["summary"].update(totalNetAmount=0, ingredientCost=0, netProfit=-400000)
    for day in body["dailyProfits"]:
        day["netProfit"] = 0

    res = await _post(body)

    assert res.status_code == 200
    assert res.json() == {
        "message": "순이익 인사이트에 필요한 데이터가 부족합니다.",
        "status": "INSUFFICIENT_DATA",
        "data": {"insights": []},
    }
    assert calls == []


async def test_매출_0원에_순이익률_null_이어도_422가_아니고_INSUFFICIENT_DATA(monkeypatch):
    """BE 는 totalNetAmount == 0 이면 0 으로 나눌 수 없어 netProfitRate 를 null 로 보낸다."""
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["summary"].update(
        totalNetAmount=0, ingredientCost=0, netProfit=-400000, netProfitRate=None
    )
    for day in body["dailyProfits"]:
        day["netProfit"] = 0

    res = await _post(body)

    assert res.status_code == 200
    assert res.json()["status"] == "INSUFFICIENT_DATA"
    assert calls == []


async def test_잘못된_날짜_형식은_500이_아니라_422(monkeypatch):
    _fake(monkeypatch, LLM_SUCCESS)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["dailyProfits"][0]["date"] = "2026-13-40"

    assert (await _post(body)).status_code == 422


async def test_maxInsightCount가_1_3_범위_밖이면_422():
    for value in (0, 4):
        body = json.loads(json.dumps(REQUEST_BODY))
        body["maxInsightCount"] = value
        res = await _post(body)
        assert res.status_code == 422, value


async def test_전기와의_차액을_코드가_계산해_프롬프트에_넣는다(monkeypatch):
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)

    await _post(REQUEST_BODY)  # 2,400,000 - 2,000,000

    assert '"netProfitDifference": 400000' in calls[0]
    assert "netProfitChangeRate" in calls[0], "전기가 흑자면 변화율을 그대로 준다"


async def test_전기가_적자이면_변화율을_빼고_차액만_준다(monkeypatch):
    """BE 정책(v2-profit-calculation-policy): 전기 적자는 비율로 개선 여부를 설명하지 않는다."""
    calls: list = []
    _fake(monkeypatch, LLM_SUCCESS, calls)
    body = json.loads(json.dumps(REQUEST_BODY))
    body["summary"].update(netProfit=-900000, previousNetProfit=-200000, netProfitChangeRate=-3.5)

    await _post(body)

    assert "netProfitChangeRate" not in calls[0]
    assert '"netProfitDifference": -700000' in calls[0]
