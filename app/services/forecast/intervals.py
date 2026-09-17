"""예측구간 — 과거 예측이 얼마나 빗나갔는지로 범위를 만든다.

Ridge 는 점추정만 내므로 구간이 따라오지 않는다. 대신 매장 자신의 데이터로 내부
백테스트를 돌려 상대오차 분포를 구하고, 그 분위수를 예측값에 곱한다.

**예측 기간별로 나누지 않는다.** 267일 실측에서 구간폭이 1~7일 41%, 8~21일 43%,
22~35일 42% 로 거의 같았다. 피처가 시작 달의 직전 달 집계로 고정된 direct 예측이라
예측 기간이 길어져도 오차가 누적되지 않기 때문이다.

분위수는 비대칭이다(하단 -17%, 상단 +25%). 매출은 아래로 빠지는 폭보다 위로 튀는
폭이 커서, 대칭 구간(±x%)을 쓰면 위쪽을 놓친다.
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

COVERAGE = 0.80  # 목표 커버리지. 267일 실측 80.0%
_LOW, _HIGH = 0.10, 0.90

MIN_RESIDUALS = 60  # 이보다 적으면 매장 분위수를 믿지 않는다
MAX_ORIGINS = 120  # 백테스트 원점 상한 — 데이터가 쌓여도 응답 시간을 묶어둔다

# 표본이 모자란 신규 매장용 기본값. 267일 실측 분위수(2026-09-17 측정).
# 매장 한 곳에서 나온 값이라 잠정치다. 매장이 늘면 다시 잡아야 한다.
DEFAULT_QUANTILES = (-0.172, 0.254)


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
        return DEFAULT_QUANTILES
    series = pd.Series(errors)
    return float(series.quantile(_LOW)), float(series.quantile(_HIGH))


def bounds(predicted: np.ndarray, quantiles: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """예측값에 분위수를 곱해 하한·상한을 만든다. 반올림 때문에 순서가 뒤집히지 않게 조인다."""
    low, high = quantiles
    lower = np.clip(predicted * (1 + low), 0, None).round().astype(int)
    upper = np.clip(predicted * (1 + high), 0, None).round().astype(int)
    return np.minimum(lower, predicted), np.maximum(upper, predicted)
