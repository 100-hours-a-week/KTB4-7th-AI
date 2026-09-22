import json

import httpx

from app.clients import llm
from app.main import app

# 2026-09-22 풀스택 확정 계약. 지표 구조가 통째로 바뀌어 솔루션과 더는 같은 모양이 아니다.
REQUEST_BODY = {
    "storeId": 1024,
    "salesAnalysisId": 771,
    "analysisRunId": 34,
    "targetMonth": "2026-09",
    "triggerType": "UPLOAD",
    "maxInsightCount": 3,
    "metrics": {
        "salesSummary": {
            "totalSales": 7920000,
            "menuSales": 7480000,
            "orderCount": 923,
            "averageOrderValue": 8581,
            "vsPrevPeriod": 0.042,
        },
        "salesTrend": [{"date": "2026-09-12", "menuSales": 2140000, "orderCount": 231}],
        "weekdaySales": [{"dayOfWeek": "SATURDAY", "menuSales": 1560000, "orderCount": 182}],
        "hourlySales": [{"dayType": "WEEKDAY", "hour": 12, "menuSales": 420000, "orderCount": 55}],
        "categorySales": [
            {"categoryName": "커피", "menuSales": 3120000, "ratio": 0.417, "vsPrevPeriod": -0.044}
        ],
        "menuRankings": [
            {
                "rank": 1,
                "menuName": "아메리카노",
                "menuSales": 2108000,
                "quantity": 620,
                "ratio": 0.282,
                "vsPrevPeriod": 0.031,
            }
        ],
    },
}

LLM_SUCCESS = json.dumps(
    {
        "insights": [
            "9월 총 매출은 7,920,000원으로 이전 기간보다 4.2% 증가했습니다.",
            "아메리카노 매출은 2,108,000원으로 메뉴 매출의 28.2%를 차지했습니다.",
        ]
    },
    ensure_ascii=False,
)


async def _post(body: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/internal/v1/ai/sales-insights", json=body)


async def test_정상_요청이_인사이트를_반환한다(monkeypatch):
    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["data"]["targetMonth"] == "2026-09"
    assert body["data"]["insights"][0]
    assert "missingData" not in body["data"]


async def test_필수_필드가_없으면_422():
    body = {k: v for k, v in REQUEST_BODY.items() if k != "metrics"}
    res = await _post(body)
    assert res.status_code == 422
    assert res.json()["message"]


async def test_LLM_파싱이_계속_실패하면_500_이고_1회만_재시도한다(monkeypatch):
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        return "이건 JSON이 아닙니다"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "최초 시도 + 재시도 1회 = 2번 호출되어야 한다"


async def test_모델이_JSON을_코드펜스로_감싸도_파싱된다(monkeypatch):
    """솔루션과 같은 이유 — tests/test_solutions.py 의 같은 이름 테스트 참고."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return f"```json\n{LLM_SUCCESS}\n```"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["insights"]


def _insights(*items) -> str:
    return json.dumps({"insights": list(items)}, ensure_ascii=False)


async def test_빈_배열이면_재시도하고_그래도_비면_500이다(monkeypatch):
    """`insights is not None` 으로 끊던 탓에 빈 배열이 재시도 없이 200 으로 나갔다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        return _insights()

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500
    assert len(calls) == 2, "빈 배열도 재시도해야 한다"


async def test_maxInsightCount_를_넘으면_재시도한다(monkeypatch):
    """BE 가 3개를 요청했는데 5개가 나가면 AN-01 화면이 넘친다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _insights("1", "2", "3", "4", "5")
        return _insights("문장1", "문장2", "문장3")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(res.json()["data"]["insights"]) == 3
    assert len(calls) == 2


async def test_빈_문장이_섞이면_재시도한다(monkeypatch):
    """화면에 빈 불릿이 생긴다 — 에러가 아니라 화면이 이상해지는 방식으로 드러난다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _insights("정상 문장", "   ", "또 정상")
        return _insights("문장1", "문장2")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["insights"] == ["문장1", "문장2"]
    assert len(calls) == 2


async def test_100자를_넘는_문장이_있으면_재시도한다(monkeypatch):
    """풀스택 확정 계약(2026-09-22)이 문장당 최대 100자다.

    프롬프트로도 알리지만 차단은 코드가 한다 — 코드펜스 때 배운 대로, 계약을 어기면
    화면이 깨지는 항목을 모델의 선의에 맡기지 않는다.
    """
    calls = []
    긴문장 = "가" * 101

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        if len(calls) == 1:
            return _insights("정상 문장입니다.", 긴문장)
        return _insights("문장1", "문장2")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert res.json()["data"]["insights"] == ["문장1", "문장2"]
    assert len(calls) == 2
    assert all(len(i) <= 100 for i in res.json()["data"]["insights"])


async def test_정확히_100자는_통과한다(monkeypatch):
    """경계값. 초과만 막고 같은 건 통과해야 한다."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return _insights("나" * 100)

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 200
    assert len(res.json()["data"]["insights"][0]) == 100


async def test_analysisRunId_가_스키마에_있어_버려지지_않는다():
    """extra="ignore" 라 스키마에 없으면 조용히 사라진다 — 에러도 안 난다."""
    from app.schemas.insight import InsightRequest

    assert "analysisRunId" in InsightRequest.model_fields
    parsed = InsightRequest(**REQUEST_BODY)
    assert parsed.analysisRunId == 34


async def test_analysisRunId_가_없어도_422가_아니다():
    """BE 가 아직 안 보내는 단계에서도 인사이트는 나가야 한다."""
    from app.schemas.insight import InsightRequest

    body = {k: v for k, v in REQUEST_BODY.items() if k != "analysisRunId"}
    assert InsightRequest(**body).analysisRunId is None


async def test_실패_응답에_status_FAILED_가_붙는다(monkeypatch):
    """BE 가 성공·실패를 한 가지 방식으로 파싱하게 한다(2026-09-22 요청).

    재시도 여부는 이 필드가 아니라 HTTP 상태 코드가 정한다 — BE 재시도 정책이
    "503/504만"이라 실패를 200 으로 내리면 그 정책이 발동하지 않는다.
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return "JSON 아님"

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 500, "200 이면 BE 재시도 정책과 모니터링이 동시에 죽는다"
    assert res.json()["status"] == "FAILED"
    assert res.json()["data"] is None


async def test_모델_타임아웃은_504라_BE가_재시도한다(monkeypatch):
    """BE 재시도 정책이 504 를 재시도 대상으로 둔다. 500 으로 새면 재시도가 안 붙는다.

    APITimeoutError → 504 매핑 자체는 tests/test_llm_providers.py 가 본다. 여기서는
    그 504 가 서비스·핸들러를 지나 응답까지 그대로 나가는지만 확인한다.
    """
    from app.core.errors import ApiError

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        raise ApiError(504, "LLM_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다.")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(REQUEST_BODY)

    assert res.status_code == 504
    assert res.json()["status"] == "FAILED"


async def test_BE_응답제한_30초_안에_들어오는_타임아웃을_쓴다(monkeypatch):
    """재시도 1회까지 포함해 BE 의 30초 제한 안에 끝나야 한다.

    전역 LLM_TIMEOUT_SECONDS(60)를 그대로 쓰면 최악 120초라, BE 가 끊은 뒤에도
    이쪽만 토큰을 계속 태운다.
    """
    from app.core.config import settings
    from app.services import insight as insight_service

    seen = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        seen.append(timeout)
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)
    await _post(REQUEST_BODY)

    budget = settings.insight_llm_timeout_seconds
    assert seen == [budget], "전역값이 아니라 인사이트 전용 예산을 써야 한다"
    assert budget * (insight_service.MAX_RETRY + 1) < 30


async def test_인사이트_타임아웃은_환경변수로_조절된다(monkeypatch):
    """운영에서 조절할 수 없으면 504 재현도 못 한다 — BE 가 테스트 가능 여부를 물었다."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "insight_llm_timeout_seconds", 0.5)
    seen = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        seen.append(timeout)
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)
    await _post(REQUEST_BODY)

    assert seen == [0.5]


def _metrics(**overrides) -> dict:
    m = json.loads(json.dumps(REQUEST_BODY["metrics"]))
    m.update(overrides)
    return m


async def test_주문이_0건이면_LLM을_부르지_않고_INSUFFICIENT_DATA(monkeypatch):
    """BE 가 영업일 14일 미만은 거르지만, 그 검사를 통과하고도 지표가 빌 수 있다."""
    calls = []

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        calls.append(1)
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    summary = dict(REQUEST_BODY["metrics"]["salesSummary"], orderCount=0)
    res = await _post({**REQUEST_BODY, "metrics": _metrics(salesSummary=summary)})

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["data"]["missingData"] == ["SALES_HISTORY"]
    assert "insights" not in body["data"]
    assert calls == [], "재료가 없으면 LLM 을 부르지 않는다 — 토큰만 쓴다"


async def test_총매출이_0원이면_INSUFFICIENT_DATA(monkeypatch):
    """ "총매출은 0원입니다" 같은 문장이 200 으로 화면까지 나가던 경로다."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        raise AssertionError("호출되면 안 된다")

    monkeypatch.setattr(llm, "complete", fake_complete)

    summary = dict(REQUEST_BODY["metrics"]["salesSummary"], totalSales=0)
    res = await _post({**REQUEST_BODY, "metrics": _metrics(salesSummary=summary)})

    assert res.json()["status"] == "INSUFFICIENT_DATA"


async def test_상세_지표가_전부_비면_INSUFFICIENT_DATA(monkeypatch):
    """상세 지표 5종이 스키마에서 전부 기본값 [] 이라 salesSummary 만으로도 요청이 통과한다.

    그 상태로 생성하면 요약 한 줄을 돌려 쓰는데 AN-01 은 3불릿 화면이다.
    """

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        raise AssertionError("호출되면 안 된다")

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(
        {
            **REQUEST_BODY,
            "metrics": {"salesSummary": REQUEST_BODY["metrics"]["salesSummary"]},
        }
    )

    assert res.json()["status"] == "INSUFFICIENT_DATA"


async def test_상세_지표가_하나라도_있으면_생성한다(monkeypatch):
    """경계값. 5종 중 하나만 있어도 관찰할 재료는 있다."""

    async def fake_complete(system: str, user: str, max_tokens: int = 2000, timeout=None) -> str:
        return LLM_SUCCESS

    monkeypatch.setattr(llm, "complete", fake_complete)

    res = await _post(
        {
            **REQUEST_BODY,
            "metrics": {
                "salesSummary": REQUEST_BODY["metrics"]["salesSummary"],
                "categorySales": REQUEST_BODY["metrics"]["categorySales"],
            },
        }
    )

    assert res.json()["status"] == "COMPLETED"
