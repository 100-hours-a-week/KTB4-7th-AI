"""예측 피처 생성 — 위키 [AI] 단계1 §3.3·§7.1.

피처 7종은 전부 예측 시점에 이미 확정된 값만 쓴다. 특히 35일 예측 구간은 전부
**예측 시작일이 속한 달의 직전 달** 집계로 고정한다. 예측값을 다시 피처로 되먹이면
(recursive) 오차가 누적되므로 하지 않는다.
"""

import holidays
import pandas as pd

FEATURES = [
    "dow",
    "is_weekend",
    "day_of_month",
    "is_holiday",
    "prev_month_mean",
    "prev_month_dow_mean",
    "prev_growth",
]
CATEGORICAL = ["dow"]
NUMERIC = [f for f in FEATURES if f not in CATEGORICAL]

_KR = holidays.KR()


def _calendar(index: pd.DatetimeIndex) -> pd.DataFrame:
    """날짜만으로 확정되는 달력 피처."""
    df = pd.DataFrame(index=index)
    df["dow"] = index.dayofweek
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["day_of_month"] = index.day
    df["is_holiday"] = [int(d in _KR) for d in index]
    return df


def month_stats(history: pd.Series) -> tuple[pd.Series, pd.Series]:
    """월별 평균과 (월, 요일)별 평균. 전월 피처의 재료다."""
    frame = pd.DataFrame(
        {
            "amount": history.to_numpy(),
            "ym": history.index.to_period("M"),
            "dow": history.index.dayofweek,
        }
    )
    return frame.groupby("ym")["amount"].mean(), frame.groupby(["ym", "dow"])["amount"].mean()


def _growth(means: pd.Series, period: pd.Period) -> float:
    """전전월 대비 전월 증가율. 재료가 없으면 0으로 보정한다(위키 단계2 §5.1)."""
    if period - 1 in means.index and period - 2 in means.index and means[period - 2]:
        return float(means[period - 1] / means[period - 2] - 1)
    return 0.0


def build_training_frame(history: pd.Series) -> pd.DataFrame:
    """학습 행. 전월 집계가 없는 첫 데이터 월은 여기서 빠진다(§3.3 이력 조건)."""
    means, dow_means = month_stats(history)
    df = _calendar(history.index)
    df["amount"] = history.to_numpy()
    ym = history.index.to_period("M")
    df["prev_month_mean"] = (ym - 1).map(means)
    df["prev_month_dow_mean"] = pd.MultiIndex.from_arrays([ym - 1, df["dow"]]).map(dow_means)
    df["prev_growth"] = [_growth(means, p) for p in ym]
    return df.dropna(subset=FEATURES)


def build_future_frame(history: pd.Series, start: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """예측 구간. 35일 전부 시작 달의 직전 달 집계로 고정한다."""
    means, dow_means = month_stats(history)
    base = start.to_period("M") - 1  # 예측 시작 달의 직전 달

    index = pd.date_range(start, periods=horizon)
    df = _calendar(index)
    df["prev_month_mean"] = means[base]
    df["prev_month_dow_mean"] = df["dow"].map(dow_means[base])
    df["prev_growth"] = _growth(means, start.to_period("M"))

    # 직전 달에 특정 요일이 하나도 없으면(휴무 등) 그 달 평균으로 대체한다.
    df["prev_month_dow_mean"] = df["prev_month_dow_mean"].fillna(means[base])
    return df
