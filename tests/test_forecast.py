"""매출 예측 배치 — 계약 조건(위키 [AI] 단계1 §3.3·§7.1) 검증."""

import httpx
import pandas as pd
import pytest

from app.core.config import settings
from app.core.errors import ApiError
from app.main import app
from app.schemas.forecast import DailySale, ForecastRequest
from app.services.forecast import run_forecast
from app.services.forecast.features import build_future_frame, month_stats


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

    assert res.status == "SUCCESS"
    assert res.horizonDays == 35
    assert len(res.predictions) == 35
    assert res.forecastEndDate == "2026-10-05"
    assert res.modelVersion == "ridge_v2"
    assert [p.date for p in res.predictions] == [
        str(d.date()) for d in pd.date_range("2026-09-01", periods=35)
    ]
    assert all(p.predictedAmount > 0 for p in res.predictions)


def test_학습_행이_60행_미만이면_이력부족이다():
    """1월 1일 시작 매장이 4월을 예측하는 경우. 학습 행은 2·3월 59행뿐이다."""
    res = run_forecast(_request("2026-01-01", "2026-03-31", "2026-04-01"))

    assert res.status == "INSUFFICIENT_HISTORY"
    assert res.predictions == []
    assert res.incompleteMonths == []
    assert res.providedTrainingRows == 59
    assert res.requiredTrainingRows == 60


def test_직전_두_달이_완전하지_않으면_이력부족이다():
    res = run_forecast(_request("2026-03-10", "2026-04-30", "2026-05-01"))

    assert res.status == "INSUFFICIENT_HISTORY"
    assert res.incompleteMonths == ["2026-03"]


def test_월_중간에_끝나는_데이터도_예측된다():
    """시작 달의 직전 두 달로 판정하므로 말일 업로드가 아니어도 막히지 않는다."""
    res = run_forecast(_request("2025-12-08", "2026-08-14", "2026-08-15"))

    assert res.status == "SUCCESS"
    assert res.predictions[0].date == "2026-08-15"
    assert res.forecastEndDate == "2026-09-18"


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


async def test_인증키가_없으면_401():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/internal/ai/forecast/batch", json={})
    assert res.status_code == 401


async def test_라우터가_예측_응답을_돌려준다(monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "test-key")
    payload = _request("2025-12-08", "2026-08-31", "2026-09-01").model_dump()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/internal/ai/forecast/batch",
            json=payload,
            headers={"X-Internal-Api-Key": "test-key"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert len(body["predictions"]) == 35
