"""Ridge 학습·추론 — 위키 [AI] 단계2 §5에서 선정한 설정.

피처 7종, 요청마다 재학습(실측 약 14ms 규모).
alpha 는 공휴일 인코딩 개선과 함께 267일 데이터로 재탐색해 12 → 5 로 낮췄다.
규제가 강하면 공휴일 계수가 눌려 평일 공휴일을 과소예측한다 (위키 단계2 §5.11).
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.forecast.features import CATEGORICAL, FEATURES, NUMERIC

# 학습 구성이 바뀐 날짜를 쓴다. 팀의 릴리스 버전(v1 MVP / v2 순이익 / v3 리뷰)과 혼동되지
# 않고, 문자열 정렬만으로 최신 버전이 나와 BE 가 최신 예측을 고르기 쉽다.
# 2026-09-16: 공휴일 인코딩을 is_offday + is_holiday_weekday 로 분리, alpha 12 → 5
MODEL_VERSION = "ridge-2026-09-16"
ALPHA = 5


def _pipeline() -> Pipeline:
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]
    )
    return Pipeline([("pre", pre), ("reg", Ridge(alpha=ALPHA))])


def fit_predict(train: pd.DataFrame, future: pd.DataFrame) -> np.ndarray:
    """학습 후 예측 구간을 한 번에 산출한다(direct 예측)."""
    model = _pipeline().fit(train[FEATURES], train["amount"])
    predicted = model.predict(future[FEATURES])
    return np.clip(predicted, 0, None).round().astype(int)
