"""매출 예측 배치 — 계약 조건 검증.

기준: 노션 API 정의서 `POST /internal/v1/ai/forecast/batch`, 위키 [AI] 단계1 §3.3
"""

import httpx
import pandas as pd
import pytest

from app.core.errors import ApiError
from app.main import app
from app.schemas.forecast import DailySale, ForecastRequest
from app.services.forecast import run_forecast
from app.services.forecast.features import build_future_frame, month_stats

PATH = "/internal/v1/ai/forecast/batch"


def _daily(first: str, last: str) -> list[DailySale]:
    """요일 패턴이 있는 합성 매출. 주말이 평일의 약 1.8배."""
    index = pd.date_range(first, last)
    return [
        DailySale(
            date=str(day.date()),
            amount=int(1_000_000 * (1.8 if day.dayofweek >= 5 else 1.0) + day.day * 1_000),
            orderCnt=80,
        )
        for day in index
    ]


def _request(first: str, last: str, start: str) -> ForecastRequest:
    return ForecastRequest(
        storeId=1024, uploadId=583, forecastStartDate=start, dailySales=_daily(first, last)
    )


def test_이력이_충분하면_35일을_예측한다():
    res = run_forecast(_request("2025-12-08", "2026-08-31", "2026-09-01"))

    assert res.message == "예측을 생성했습니다."
    assert res.data.horizonDays == 35
    assert len(res.data.predictions) == 35
    assert res.data.forecastEndDate == "2026-10-05"
    assert [p.targetDate for p in res.data.predictions] == [
        str(d.date()) for d in pd.date_range("2026-09-01", periods=35)
    ]
    assert all(p.predictedSalesAmount > 0 for p in res.data.predictions)
    assert {p.modelVersion for p in res.data.predictions} == {"ridge_v2"}


def test_학습_행이_60행_미만이면_이력부족이다():
    """1월 1일 시작 매장이 4월을 예측하는 경우. 학습 행은 2·3월 59행뿐이다."""
    res = run_forecast(_request("2026-01-01", "2026-03-31", "2026-04-01"))

    assert res.status == "INSUFFICIENT_DATA"
    assert res.data.missingData == ["INSUFFICIENT_HISTORY"]
    assert res.data.incompleteMonths == []
    assert res.data.providedTrainingRows == 59
    assert res.data.requiredTrainingRows == 60


def test_직전_두_달이_완전하지_않으면_이력부족이다():
    res = run_forecast(_request("2026-03-10", "2026-04-30", "2026-05-01"))

    assert res.status == "INSUFFICIENT_DATA"
    assert res.data.incompleteMonths == ["2026-03"]


def test_월_중간에_끝나는_데이터도_예측된다():
    """시작 달의 직전 두 달로 판정하므로 말일 업로드가 아니어도 막히지 않는다."""
    res = run_forecast(_request("2025-12-08", "2026-08-14", "2026-08-15"))

    assert res.data.predictions[0].targetDate == "2026-08-15"
    assert res.data.forecastEndDate == "2026-09-18"


def test_시작일이_마지막_날짜_다음_날이_아니면_422():
    with pytest.raises(ApiError) as exc:
        run_forecast(_request("2025-12-08", "2026-08-31", "2026-10-01"))

    assert exc.value.status == 422
    assert exc.value.code == "INVALID_FORECAST_START_DATE"


def test_날짜가_누락되면_422():
    rows = _daily("2026-01-01", "2026-06-30")
    del rows[100]
    req = ForecastRequest(storeId=1, uploadId=1, forecastStartDate="2026-07-01", dailySales=rows)

    with pytest.raises(ApiError) as exc:
        run_forecast(req)

    assert exc.value.status == 422
    assert exc.value.code == "INVALID_DAILY_SALES"


def test_공휴일이_주말과_겹치면_쉬는날_효과를_한_번만_센다():
    """ridge_v2 — is_offday 는 켜지고 is_holiday_weekday 는 꺼져야 한다."""
    future = build_future_frame(
        pd.Series(
            {pd.Timestamp(r.date): float(r.amount) for r in _daily("2025-12-08", "2026-08-14")}
        ),
        pd.Timestamp("2026-08-15"),
        5,
    )
    saturday_holiday = future.loc[pd.Timestamp("2026-08-15")]  # 광복절(토)
    weekday_holiday = future.loc[pd.Timestamp("2026-08-17")]  # 대체공휴일(월)

    assert saturday_holiday["is_offday"] == 1
    assert saturday_holiday["is_holiday_weekday"] == 0
    assert weekday_holiday["is_offday"] == 1
    assert weekday_holiday["is_holiday_weekday"] == 1


def test_35일_전부_시작_달의_직전_달_집계로_고정된다():
    """다음 달로 넘어가는 구간도 기준이 바뀌지 않아야 한다(재귀 예측 금지)."""
    history = pd.Series(
        {pd.Timestamp(row.date): float(row.amount) for row in _daily("2025-12-08", "2026-08-31")}
    )
    future = build_future_frame(history, pd.Timestamp("2026-09-01"), 35)
    means, _ = month_stats(history)

    assert future["prev_month_mean"].nunique() == 1
    assert future["prev_month_mean"].iloc[0] == pytest.approx(means[pd.Period("2026-08")])
    assert future["prev_growth"].nunique() == 1


async def test_필수_필드가_없으면_422():
    """인증 헤더 없이도 라우트에 도달한다 — 경계는 보안 그룹이다."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(PATH, json={})
    assert res.status_code == 422


async def test_라우터가_예측_응답을_돌려준다():
    payload = _request("2025-12-08", "2026-08-31", "2026-09-01").model_dump()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(PATH, json=payload)

    assert res.status_code == 200
    body = res.json()
    assert "status" not in body
    assert body["data"]["horizonDays"] == 35
    assert len(body["data"]["predictions"]) == 35
    assert set(body["data"]["predictions"][0]) == {
        "targetDate",
        "predictedSalesAmount",
        "modelVersion",
    }


async def test_이력이_부족하면_200_에_업무_상태로_내려간다():
    """요청 자체는 정상이라 422 가 아니다 — 노션 공통 원칙의 status 확장형."""
    payload = _request("2026-01-01", "2026-03-31", "2026-04-01").model_dump()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(PATH, json=payload)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["data"]["missingData"] == ["INSUFFICIENT_HISTORY"]
    assert "predictions" not in body["data"]


def test_analysisRunId_가_있어도_없어도_받는다():
    """BE 계약상 필수지만 예측에 쓰지 않아 AI 가 막지 않는다."""
    rows = _daily("2025-12-08", "2026-08-31")
    with_id = ForecastRequest(
        storeId=1, uploadId=1, analysisRunId=77, forecastStartDate="2026-09-01", dailySales=rows
    )

    assert with_id.analysisRunId == 77
    assert run_forecast(with_id).data.horizonDays == 35
