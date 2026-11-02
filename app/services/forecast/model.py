"""Ridge 학습·추론 — 위키 [AI] 단계2 §5에서 선정한 설정.

피처 7종, 요청마다 재학습.

**규제 강도(alpha)는 매장마다 그 매장 데이터로 고른다.** 고정값을 쓰지 않는다 — 2026-09-16
에 정한 `ALPHA = 5` 는 매장 한 곳(267일)에서 탐색한 값이고, 사용자가 자기 POS 데이터를
올리는 서비스에서는 우리가 미리 고른 값이 그 매장에 맞을 이유가 없다. `RidgeCV` 의 LOO
경로는 한 번의 행렬 분해로 격자 전체를 풀어서, 측정상 **고정 alpha 1회 학습보다 오히려
빠르다**(매장 A 26.2ms → 10.6ms, 매장 B 6.5ms → 4.2ms, 2026-11-02). 비용 없이 상수 하나가
사라지므로 안 할 이유가 없다.

격자는 과거 탐색 범위를 그대로 덮는다. 규제가 강하면 공휴일 계수가 눌려 평일 공휴일을
과소예측하므로(위키 단계2 §5.11) 아래쪽을 넉넉히 두고, 위쪽은 두 매장 실측에서 20 을
넘기면 평일 오차가 늘어나는 걸 보고 50 까지만 둔다.
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.services.forecast.features import CATEGORICAL, FEATURES, NUMERIC

# 학습 구성이 바뀐 날짜를 쓴다. 팀의 릴리스 버전(v1 MVP / v2 순이익 / v3 리뷰)과 혼동되지
# 않고, 문자열 정렬만으로 최신 버전이 나와 BE 가 최신 예측을 고르기 쉽다.
# 2026-09-16: 공휴일 인코딩을 is_offday + is_holiday_weekday 로 분리, alpha 12 → 5
# 2026-11-02: alpha 고정값을 없애고 매장마다 RidgeCV 로 고르게 했다
MODEL_VERSION = "ridge-2026-11-02"
ALPHA_GRID = (0.5, 1.0, 2.0, 5.0, 8.0, 12.0, 20.0, 50.0)


def _pipeline() -> Pipeline:
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]
    )
    return Pipeline([("pre", pre), ("reg", RidgeCV(alphas=ALPHA_GRID))])


def fit_predict(train: pd.DataFrame, future: pd.DataFrame) -> np.ndarray:
    """학습 후 예측 구간을 한 번에 산출한다(direct 예측).

    alpha 는 `train` 안에서 고른다 — 백테스트 원점마다 그 원점 이전 데이터로 다시 고르므로,
    구간을 만드는 잔차도 운영과 같은 절차에서 나온다.
    """
    model = _pipeline().fit(train[FEATURES], train["amount"])
    predicted = model.predict(future[FEATURES])
    return np.clip(predicted, 0, None).round().astype(int)
