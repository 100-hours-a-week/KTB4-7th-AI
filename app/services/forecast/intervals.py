"""예측구간 — 과거 예측이 얼마나 빗나갔는지로 범위를 만든다.

Ridge 는 점추정만 내므로 구간이 따라오지 않는다. 대신 매장 자신의 데이터로 내부
백테스트를 돌려 상대오차 분포를 구하고, 그 분위수를 예측값에 곱한다.

**예측 기간별로 나누지 않는다.** 267일 실측에서 구간폭이 1~7일 41%, 8~21일 43%,
22~35일 42% 로 거의 같았다. 피처가 시작 달의 직전 달 집계로 고정된 direct 예측이라
예측 기간이 길어져도 오차가 누적되지 않기 때문이다.

분위수는 비대칭이다. 매출은 아래로 빠지는 폭보다 위로 튀는 폭이 커서, 대칭 구간(±x%)을
쓰면 위쪽을 놓친다 — 두 매장 실측에서 하단 -16~-15%, 상단 +31~+32% 였다(2026-11-02).
그래서 상·하한을 따로 만든다.

**백테스트 원점이 모자란 매장도 고정값을 받지 않는다.** 그 매장 자신의 학습 잔차로
구간을 만들고 표본 수에 따라 넓힌다 — 아래 `_insample_quantiles` 참고.
"""

import numpy as np
import pandas as pd

from app.schemas.forecast import HORIZON_DAYS, MIN_TRAINING_ROWS
from app.services.forecast.features import (
    build_future_frame,
    build_training_frame,
    incomplete_months,
)
from app.services.forecast.model import fit_predict

COVERAGE = 0.80  # 목표 커버리지. 실측 매장 B 80.0% · 매장 A 76.4% (2026-11-02)
_LOW, _HIGH = 0.10, 0.90

MIN_RESIDUALS = 60  # 이보다 적으면 워크포워드 잔차를 믿지 않는다
MAX_ORIGINS = 120  # 백테스트 원점 상한 — 데이터가 쌓여도 응답 시간을 묶어둔다


def _origins(history: pd.Series) -> list[pd.Timestamp]:
    """예측 조건을 만족하는 백테스트 원점. 최근 것부터 MAX_ORIGINS 개만 쓴다."""
    candidates = []
    for origin in pd.date_range(history.index[0], history.index[-1]):
        past = history[history.index < origin]
        if len(past) < MIN_TRAINING_ROWS or incomplete_months(past, origin):
            continue
        candidates.append(origin)
    return candidates[-MAX_ORIGINS:]


def residual_quantiles(history: pd.Series) -> tuple[float, float]:
    """매장 자신의 상대오차 분위수. 표본이 모자라면 기본값을 돌려준다."""
    errors: list[float] = []
    for origin in _origins(history):
        past = history[history.index < origin]
        train = build_training_frame(past)
        if len(train) < MIN_TRAINING_ROWS:
            continue
        future = build_future_frame(past, origin, HORIZON_DAYS)
        predicted = fit_predict(train, future)
        for day, value in zip(future.index, predicted, strict=True):
            if value > 0 and day in history.index:
                errors.append((history[day] - value) / value)

    if len(errors) < MIN_RESIDUALS:
        return _insample_quantiles(history)
    series = pd.Series(errors)
    return float(series.quantile(_LOW)), float(series.quantile(_HIGH))


def _widened(errors: pd.Series) -> tuple[float, float]:
    """표본이 적을수록 넓어지는 분위수.

    `(n+1)` 로 보정한다 — conformal 예측이 유한표본 커버리지를 보장할 때 쓰는 순서통계량
    위치와 같다. n 이 크면 그냥 분위수와 같아지고, 작으면 양 끝으로 밀려 넓어진다.
    """
    n = len(errors)
    low = max((n + 1) * _LOW - 1, 0.0) / n
    high = min((n + 1) * _HIGH, float(n)) / n
    return float(errors.quantile(low)), float(errors.quantile(high))


def _insample_quantiles(history: pd.Series) -> tuple[float, float]:
    """워크포워드 원점이 모자란 매장. 그 매장 자신의 학습 잔차로 만든다.

    학습 데이터에 맞춘 잔차라 35일 앞 오차보다 좁다. 그래서 `_widened` 로 넓힌다 —
    매장 한 곳에서 고른 고정값을 모든 신규 매장에 주는 것보다, **그 매장 변동성에
    비례하는 폭**이 낫다. 변동이 큰 매장은 넓게, 안정적인 매장은 좁게 받는다.

    게이트를 막 통과한 매장이라 n 이 59 부근이고, 그만큼 보정도 크게 걸린다.
    """
    train = build_training_frame(history)
    predicted = fit_predict(train, train)
    errors = [
        (actual - value) / value
        for actual, value in zip(train["amount"], predicted, strict=True)
        if value > 0
    ]
    return _widened(pd.Series(errors))


def bounds(predicted: np.ndarray, quantiles: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """예측값에 분위수를 곱해 하한·상한을 만든다. 반올림 때문에 순서가 뒤집히지 않게 조인다."""
    low, high = quantiles
    lower = np.clip(predicted * (1 + low), 0, None).round().astype(int)
    upper = np.clip(predicted * (1 + high), 0, None).round().astype(int)
    return np.minimum(lower, predicted), np.maximum(upper, predicted)
