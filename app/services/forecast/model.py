"""Ridge 학습·추론 — 위키 [AI] 단계2 §5에서 선정한 설정.

alpha=12, 피처 7종. 학습+추론 실측 약 14ms 규모라 요청마다 재학습해도 부담이 없다.
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.forecast.features import CATEGORICAL, FEATURES, NUMERIC

MODEL_VERSION = "ridge_v1"
ALPHA = 12


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
