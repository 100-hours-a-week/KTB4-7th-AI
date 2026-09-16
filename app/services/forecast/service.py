"""매출 예측 배치 — 요청 검증, 이력 조건 판정, 학습·예측 오케스트레이션.

계약 기준: 위키 [AI] 단계1 §3.3·§7.1
"""

import pandas as pd

from app.core.errors import ApiError
from app.schemas.forecast import (
    HORIZON_DAYS,
    MIN_TRAINING_ROWS,
    DailySale,
    ForecastRequest,
    ForecastResponse,
    Prediction,
)
from app.services.forecast.features import build_future_frame, build_training_frame
from app.services.forecast.model import MODEL_VERSION, fit_predict


def _invalid(message: str) -> ApiError:
    return ApiError(422, "INVALID_DAILY_SALES", message)


def _to_series(daily_sales: list[DailySale]) -> pd.Series:
    """일별 매출을 시계열로 바꾸면서 계약 조건(오름차순·연속·중복 없음)을 검증한다."""
    if not daily_sales:
        raise _invalid("dailySales 가 비어 있습니다.")

    try:
        index = pd.to_datetime([row.date for row in daily_sales], format="%Y-%m-%d")
    except ValueError as exc:
        raise _invalid("dailySales[].date 형식은 YYYY-MM-DD 여야 합니다.") from exc

    series = pd.Series([row.amount for row in daily_sales], index=index, dtype="float64")
    if not series.index.is_monotonic_increasing or series.index.has_duplicates:
        raise _invalid("dailySales 는 날짜 오름차순이며 중복이 없어야 합니다.")

    expected = pd.date_range(series.index[0], series.index[-1])
    if len(expected) != len(series):
        missing = expected.difference(series.index)
        raise _invalid(
            f"dailySales 에 날짜 누락이 있습니다({len(missing)}일). "
            "매출이 없는 날도 amount 0 으로 포함해야 합니다."
        )
    return series


def _start_date(req: ForecastRequest, series: pd.Series) -> pd.Timestamp:
    """예측 시작일은 dailySales 마지막 날짜 + 1일이어야 한다."""
    try:
        start = pd.Timestamp(req.forecastStartDate)
    except ValueError as exc:
        raise ApiError(
            422, "INVALID_FORECAST_START_DATE", "forecastStartDate 형식은 YYYY-MM-DD 여야 합니다."
        ) from exc

    expected = series.index[-1] + pd.Timedelta(days=1)
    if start != expected:
        raise ApiError(
            422,
            "INVALID_FORECAST_START_DATE",
            f"forecastStartDate 는 dailySales 마지막 날짜 다음 날({expected.date()})이어야 합니다.",
        )
    return start


def _incomplete_months(series: pd.Series, start: pd.Timestamp) -> list[str]:
    """예측 시작 달의 직전 두 달 중 완전하지 않은 달을 돌려준다."""
    first, last = series.index[0], series.index[-1]
    start_period = start.to_period("M")
    incomplete = []
    for back in (1, 2):
        period = start_period - back
        covered = first <= period.start_time and last >= period.end_time.normalize()
        if not covered:
            incomplete.append(str(period))
    return sorted(incomplete)


def run_forecast(req: ForecastRequest) -> ForecastResponse:
    series = _to_series(req.dailySales)
    start = _start_date(req, series)

    incomplete = _incomplete_months(series, start)
    train = build_training_frame(series)

    # 첫 데이터 월은 전월 피처가 없어 학습 행에서 빠진다.
    # 그래서 실질적으로 "첫 달 + 완전한 2개월"이 필요하다.
    if incomplete or len(train) < MIN_TRAINING_ROWS:
        return ForecastResponse(
            status="INSUFFICIENT_HISTORY",
            forecastStartDate=req.forecastStartDate,
            predictions=[],
            incompleteMonths=incomplete,
            requiredTrainingRows=MIN_TRAINING_ROWS,
            providedTrainingRows=len(train),
        )

    future = build_future_frame(series, start, HORIZON_DAYS)
    predicted = fit_predict(train, future)

    return ForecastResponse(
        status="SUCCESS",
        forecastStartDate=req.forecastStartDate,
        forecastEndDate=str(future.index[-1].date()),
        horizonDays=HORIZON_DAYS,
        predictions=[
            Prediction(
                date=str(day.date()),
                predictedAmount=int(amount),
                isHoliday=bool(is_holiday),
            )
            for day, amount, is_holiday in zip(
                future.index, predicted, future["is_holiday"], strict=True
            )
        ],
        modelVersion=MODEL_VERSION,
    )
