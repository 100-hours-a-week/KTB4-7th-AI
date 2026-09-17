"""예측구간 커버리지 실측.

    uv run python -m devtools.interval_backtest --pos <POS 엑셀> [<POS 엑셀> ...]

원점(origin)마다 그 이전 데이터만으로 학습·예측하고, 구간을 만드는 분위수도
**그 원점 이전 원점들의 잔차로만** 뽑는다. 같은 잔차로 구간을 만들고 같은 잔차로
커버리지를 재면 정의상 목표치가 나오므로 의미가 없다.

`app/services/forecast/intervals.py` 의 기본 분위수와 "예측 기간별로 나누지 않는다"는
판단이 이 스크립트 결과에서 나왔다. 데이터가 더 쌓이면 다시 돌려 확인한다.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from app.schemas.forecast import HORIZON_DAYS, MIN_TRAINING_ROWS
from app.services.forecast.features import (
    build_future_frame,
    build_training_frame,
    incomplete_months,
)
from app.services.forecast.model import fit_predict
from devtools.forecast_check import build_daily_sales

BUCKETS = [(1, 7), (8, 21), (22, 35)]
WARMUP = 40  # 구간을 만들기 전에 필요한 최소 잔차 수
LEVELS = [("80%", 0.10, 0.90), ("90%", 0.05, 0.95)]


def bucket_of(h: int) -> str:
    for lo, hi in BUCKETS:
        if lo <= h <= hi:
            return f"{lo}-{hi}일"
    raise ValueError(h)


def load_series(paths: list[Path]) -> pd.Series:
    rows: dict[str, int] = {}
    for path in paths:
        for row in build_daily_sales(path):
            rows[row["date"]] = row["amount"]
        print(f"  {path.name}: {len(rows)}일 누적")
    index = pd.to_datetime(sorted(rows))
    return pd.Series([float(rows[str(d.date())]) for d in index], index=index)


def backtest(series: pd.Series) -> pd.DataFrame:
    rows = []
    for origin in pd.date_range(series.index[0], series.index[-1]):
        past = series[series.index < origin]
        if len(past) < MIN_TRAINING_ROWS or incomplete_months(past, origin):
            continue
        train = build_training_frame(past)
        if len(train) < MIN_TRAINING_ROWS:
            continue
        future = build_future_frame(past, origin, HORIZON_DAYS)
        predicted = fit_predict(train, future)
        for h, (day, value) in enumerate(zip(future.index, predicted, strict=True), start=1):
            if value > 0 and day in series.index:
                rows.append(
                    {
                        "origin": origin,
                        "bucket": bucket_of(h),
                        "pred": float(value),
                        "actual": float(series[day]),
                        "relerr": (float(series[day]) - float(value)) / float(value),
                    }
                )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="예측구간 커버리지 실측")
    parser.add_argument("--pos", type=Path, nargs="+", required=True, help="POS 매출리포트 엑셀")
    args = parser.parse_args()

    print("[0] 전처리")
    series = load_series(args.pos)
    df = backtest(series)
    print(
        f"\n[1] 백테스트 — 원점 {df.origin.nunique()}개"
        f" ({df.origin.min().date()} ~ {df.origin.max().date()}), 예측-실측 쌍 {len(df)}건"
    )

    names = [f"{lo}-{hi}일" for lo, hi in BUCKETS]
    print("\n[2] 상대오차 분포 (참고용, 전체 기간)")
    print(f"{'구간':<9}{'건수':>7}{'중앙값':>10}{'10%':>9}{'90%':>9}")
    for name in names:
        g = df[df.bucket == name].relerr
        print(
            f"{name:<9}{len(g):>7}{g.median():>10.1%}"
            f"{g.quantile(0.10):>9.1%}{g.quantile(0.90):>9.1%}"
        )

    for level, qlo, qhi in LEVELS:
        print(f"\n[3] {level} 예측구간 — 구간은 과거 잔차로만 만든다")
        print(f"{'구간':<9}{'평가건수':>9}{'실측 커버리지':>15}{'구간폭(중앙값)':>17}")
        hit_total = n_total = 0
        for name in names:
            sub = df[df.bucket == name].sort_values("origin")
            hits: list[bool] = []
            widths: list[float] = []
            for origin in sub.origin.unique():
                past = sub[sub.origin < origin].relerr
                if len(past) < WARMUP:
                    continue
                low, high = past.quantile(qlo), past.quantile(qhi)
                cur = sub[sub.origin == origin]
                lower, upper = cur.pred * (1 + low), cur.pred * (1 + high)
                hits.extend(((cur.actual >= lower) & (cur.actual <= upper)).tolist())
                widths.extend(((upper - lower) / cur.pred).tolist())
            if hits:
                print(f"{name:<9}{len(hits):>9}{np.mean(hits):>14.1%}{np.median(widths):>16.0%}")
                hit_total += sum(hits)
                n_total += len(hits)
        if n_total:
            print(f"{'전체':<9}{n_total:>9}{hit_total / n_total:>14.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
