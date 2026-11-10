"""축 점수 변별력·슬롯 점유율을 POS 실데이터로 잰다.

    uv run python -m devtools.axis_scores \
      --store 매장A ~/Downloads/매출리포트_샘플_*.xlsx \
      --store 매장B ~/Downloads/매출리포트_251201-260601_163942.xlsx \
                    ~/Downloads/매출리포트_260601-260831_169521.xlsx \
      --weather ~/Downloads/extremum_20260908142633.xls

GPU·요금 없다. `app/services/solution_focus.py` 의 점수 함수를 **그대로 불러** 쓴다 —
식을 다시 적지 않는다. 식이 바뀌면 이 스크립트의 숫자도 같이 바뀌어야 한다.

왜 스크립트로 두나. 같은 측정을 2026-10-26 부터 네 번 했는데 매번 새로 짰고, 그래서
한 번 크게 틀렸다 — 여러 파일을 이어 붙인 뒤 `drop_duplicates()` 를 걸어 **같은 시각에
같은 메뉴를 산 다른 손님을 지웠다**(매장 A 행의 21.7%, 총매출 1 억원). 그 숫자로 §8·§9 를
쓰고 나서야 발견했다. 재현 가능한 코드로 남긴다.
근거: docs/experiments/2026-10-26-solution-axis-scores.md §7 정정

**재지 않는 두 축이 있다.**

- `predictedSalesToday`: POS 에 예측이 없다. 축이 후보에서 빠지므로 아래 선택률은
  네 축(시간대·카테고리·매출총액·메뉴) + 날씨 사이의 경쟁이다.
- `conditionPatterns`: BE 가 최근 12 주 ASOS 강수 관측으로 만드는 값이라 POS 로 재현하려면
  BE 선정 로직까지 옮겨야 한다. 빼도 슬롯 점유율은 바뀌지 않는다 — 그 값은 실질적으로
  점수가 아니라 게이트다(발동 시 평균 0.019~0.022 · 최대 0.054 로 다른 축보다 한 자리
  작고, `max()` 로 날씨 축에 묶인다). 근거: `_condition_score` 독스트링의 604 창 실측.

날씨는 `isNotable=true` 를 전체 날짜에 가정한 **상한**이다. BE 판정을 POS 로 재현할 수
없다. 특보(`alerts`)는 데이터가 없어 비운다 — 한파·폭염 문턱은 기온으로 걸린다.
"""

import argparse
import logging
import statistics
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from app.services import solution_focus as focus
from devtools.forecast_check import clean, is_menu

# 점수 함수와 같은 이름을 쓰되, 표에 쓸 짧은 이름으로 바꾼다.
LABELS = {
    "hourlyProfile": "시간대",
    "categoryBreakdown": "카테고리",
    "salesSummary": "매출총액",
    "weatherContext": "날씨",
    "menuRankings": "메뉴",
}

# BE 의 메뉴 랭킹 선정 — 매출 상위 다섯 종에 변화율 상위 다섯 종을 더한 합집합이다
# (`MAX_MENU_RANKING_GROUP_SIZE=5`). 비중 상위만 쓰면 점수와 기준이 어긋난다.
_RANKING_GROUP = 5

SHEET = "상품 주문 상세내역"

# 영업시간으로 볼 문턱 — 그 계열(평일/주말)의 며칠에 그 시각 매출이 있었나.
# 잠정값이다. 두 매장 모두 9 시가 평일 75% · 주말 21~31% 로 갈려서, 0.5 가 "주말은 10 시
# 개점" 을 잡아낸다. BE 의 businessHours 는 점주 등록값이라 이것과 다를 수 있다.
_OPEN_DAY_RATIO = 0.5


def _read_one(path: Path) -> pd.DataFrame:
    """POS 엑셀 한 장을 행 단위로 읽는다.

    취소 행을 포함해 전부 더한다 — POS 는 취소해도 원본 `완료` 행을 남기고 금액·수량이
    음수인 `취소` 행을 덧붙인다(`devtools/forecast_check.py::build_daily_sales` 와 같은 규칙).
    """
    df = pd.read_excel(path, sheet_name=SHEET, skiprows=[1], dtype=str)
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    amount_col = next(c for c in df.columns if c.startswith("실판매금액"))
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["주문기준일자"], format="%Y-%m-%d").dt.normalize(),
            "hour": pd.to_datetime(df["주문시작시각"]).dt.hour,
            "menu": df["상품명"].map(clean),
            "category": df["카테고리"].fillna("미분류").map(clean),
            "amount": df[amount_col].astype(int),
        }
    )
    return out[out["menu"].map(is_menu)].reset_index(drop=True)


def load_pos(paths: list[Path]) -> pd.DataFrame:
    """여러 파일을 날짜 기준으로 이어 붙인다.

    **행 단위 중복 제거를 쓰지 않는다.** 같은 시각에 같은 메뉴를 산 다른 손님이 실재한다
    (매장 A 에 동일 조합 9,038 개, 최다 19 건). 파일 날짜가 겹칠 때만 **그 날을 한 파일에서
    취한다** — 먼저 읽은 파일이 이긴다.
    """
    frames: list[pd.DataFrame] = []
    taken: set = set()
    for path in sorted(paths):
        df = _read_one(path)
        days = set(df["date"].unique())
        if overlap := days & taken:
            print(f"  겹치는 {len(overlap)}일은 먼저 읽은 파일에서 취한다: {path.name}")
            df = df[~df["date"].isin(overlap)]
        taken |= days
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _day_type(day: pd.Timestamp) -> str:
    return "WEEKEND" if day.weekday() >= 5 else "WEEKDAY"


def business_hours(pos: pd.DataFrame) -> dict:
    """매출이 있는 시각으로 영업시간을 추정한다. dayType 별로 따로 잡는다.

    고정값 09:00~24:00 을 쓰면 안 된다. 이 POS 두 매장은 **자정을 넘겨 영업한다** —
    평일 0 시 매출이 9 시의 2.5 배다(매장A 899 만원 vs 366 만원). 0~24 로 자르면 그
    매출이 시간대 축에서 통째로 빠지고, 동시에 주말 9 시(영업일의 21~31%)를 영업시간에
    넣어 유휴를 부풀린다. 둘 다 같은 방향으로 축 점수를 틀리게 만든다.

    그 계열 영업일의 `_OPEN_DAY_RATIO` 이상에서 매출이 있는 시각을 영업시간으로 보고,
    **가장 긴 공백 뒤**를 여는 시각으로 잡는다 — 24 시간을 한 바퀴로 보기 때문에
    "10 시 개점, 다음날 2 시 폐점" 이 하나의 구간으로 나온다. 닫는 시가 여는 시보다
    작게 나오면 `solution_focus._window` 가 24 를 더해 받는다(BE 도 같은 모양을 보낸다).

    **한계: 하루에 두 구간으로 영업하는 매장은 한 구간으로 뭉개진다** — 공백까지 영업으로
    세서 유휴 비중이 부풀려진다. 이 POS 두 매장은 한 구간이라 해당하지 않는다.
    """
    hours: dict = {}
    tagged = pos.assign(dayType=pos["date"].map(_day_type))
    for day_type, part in tagged.groupby("dayType"):
        days = part["date"].nunique()
        covered = part.groupby("hour")["date"].nunique() / days
        open_hours = sorted(int(h) for h, ratio in covered.items() if ratio >= _OPEN_DAY_RATIO)
        if not open_hours:
            continue
        count = len(open_hours)
        gap, index = max(
            ((open_hours[(i + 1) % count] - h) % 24, i) for i, h in enumerate(open_hours)
        )
        opens = open_hours[(index + 1) % count] if gap > 1 else open_hours[0]
        closes = (open_hours[index] + 1) if gap > 1 else open_hours[-1] + 1
        hours[day_type] = {"opensAt": f"{opens:02d}:00", "closesAt": f"{closes:02d}:00"}
    return hours


def _ratio(current: float, previous: float) -> float | None:
    """BE 의 `changeRate` 와 같은 규칙 — 이전이 0 이면 null 이다."""
    return None if previous == 0 else (current - previous) / previous


def build_metrics(cur: pd.DataFrame, prev: pd.DataFrame, hours: dict, weather: dict | None) -> dict:
    """BE 가 보낼 `metrics` 를 POS 로 만든다. 계약 필드명은 app/schemas/common.py 를 따른다."""
    net = int(cur["amount"].sum())
    summary = {
        "netSales": net,
        "vsPrevPeriod": _ratio(net, int(prev["amount"].sum())),
        "period": f"{cur['date'].min().date()}~{cur['date'].max().date()}",
    }

    hourly = [
        {"dayType": day_type, "hour": int(hour), "amount": int(amount)}
        for (day_type, hour), amount in cur.assign(dayType=cur["date"].map(_day_type))
        .groupby(["dayType", "hour"])["amount"]
        .sum()
        .items()
    ]

    # BE 의 categoryBreakdown 은 **현재 기간만** 훑는다 — 이전에만 있던 카테고리는 목록에
    # 아예 없다(`currentTotals.entrySet()`). 그 구멍까지 그대로 재현한다.
    cur_cat = cur.groupby("category")["amount"].sum()
    prev_cat = prev.groupby("category")["amount"].sum()
    categories = [
        {
            "name": name,
            "share": float(amount) / net if net else 0.0,
            "vsPrevPeriod": _ratio(float(amount), float(prev_cat.get(name, 0))),
        }
        for name, amount in cur_cat.items()
    ]

    cur_menu = cur.groupby("menu")["amount"].sum()
    prev_menu = prev.groupby("menu")["amount"].sum()
    rows = [
        {
            "menuName": name,
            "menuSales": int(amount),
            "ratio": float(amount) / net if net else 0.0,
            "vsPrevPeriod": _ratio(float(amount), float(prev_menu.get(name, 0))),
        }
        for name, amount in cur_menu.items()
    ]
    by_sales = sorted(rows, key=lambda r: r["menuSales"], reverse=True)[:_RANKING_GROUP]
    by_change = sorted(rows, key=lambda r: abs(r["vsPrevPeriod"] or 0.0), reverse=True)[
        :_RANKING_GROUP
    ]
    picked = {r["menuName"]: r for r in by_sales + by_change}
    menus = [
        {**row, "rank": rank, "quantity": 0} for rank, row in enumerate(picked.values(), start=1)
    ]

    metrics = {
        "salesSummary": summary,
        "hourlyProfile": hourly,
        "categoryBreakdown": categories,
        "menuRankings": menus,
        "businessHours": hours,
    }
    if weather:
        metrics["weatherContext"] = weather
    return focus.derive(metrics)


def scores(metrics: dict) -> dict[str, float]:
    """축별 점수. `assign` 이 쓰는 함수를 그대로 부른다 — 식을 복사하지 않는다."""
    summary = metrics["salesSummary"]
    return {
        "hourlyProfile": focus._hourly_score(
            metrics["hourlyProfile"], metrics.get("businessHours")
        ),
        "categoryBreakdown": focus._category_score(metrics["categoryBreakdown"]),
        "salesSummary": focus._summary_score(summary),
        "weatherContext": focus._weather_score(metrics.get("weatherContext")),
        "menuRankings": focus._menu_score(metrics["menuRankings"]),
    }


def load_weather(path: Path) -> dict[pd.Timestamp, dict]:
    """기상청 일별 극값(지상관측 조건별 분석).

    확장자가 `.xls` 지만 실제로는 cp949 TSV 다. 검색 조건을 적은 머리말이 앞에 붙고 그
    줄 수가 조회마다 달라서, 머리글 행을 찾아서 거기서부터 읽는다.
    """
    lines = path.read_text(encoding="cp949").splitlines()
    header = next((i for i, line in enumerate(lines) if line.startswith("지역번호")), None)
    if header is None:
        raise SystemExit(f"머리글 행(지역번호...)을 못 찾았다 — 조회 형식이 다르다: {path}")
    df = pd.read_csv(path, sep="\t", encoding="cp949", skiprows=header)
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    day_col = next(c for c in df.columns if c.startswith("일시"))
    # **지역 평균**(`평균최저기온`·`평균최고기온`)을 쓴다. 같은 파일의 `최저기온`·`최고기온`
    # 은 서울경기 전역 극값 — 어느 한 관측소의 최저·최고라 매장 위치의 예보가 아니다.
    # 615 일에서 한파·폭염 문턱(-12℃/33℃)에 걸리는 날이 36 일(6%) vs 115 일(19%) 로 갈린다.
    # `weatherContext.minTempC`·`maxTempC` 는 BE 가 매장 좌표로 받은 단기예보값이다.
    low_col = next(c for c in df.columns if c.startswith("평균최저기온"))
    high_col = next(c for c in df.columns if c.startswith("평균최고기온"))
    out: dict[pd.Timestamp, dict] = {}
    for _, row in df.iterrows():
        day = pd.to_datetime(row[day_col], errors="coerce")
        if pd.isna(day) or pd.isna(row[low_col]) or pd.isna(row[high_col]):
            continue
        out[day.normalize()] = {
            "basisDateTime": f"{day.date()} 06:00",
            "skyText": "",
            "minTempC": int(round(float(row[low_col]))),
            "maxTempC": int(round(float(row[high_col]))),
            "maxPop": 0.0,
            "rainHours": [],
            "isNotable": True,  # 상한 가정 — BE 판정을 POS 로 재현할 수 없다
        }
    return out


def measure(pos: pd.DataFrame, window: int, hours: dict, weather: dict) -> dict:
    """날짜 D 마다 직전 `window` 일을 현재, 그 앞 `window` 일을 이전 기간으로 둔다."""
    by_day = {day: frame for day, frame in pos.groupby("date")}
    days = sorted(by_day)
    axis_scores: dict[str, list[float]] = {key: [] for key in LABELS}
    slots: list[Counter] = [Counter(), Counter(), Counter()]
    short = 0
    guards = Counter()

    for index in range(2 * window, len(days)):
        cur_days = days[index - window : index]
        prev_days = days[index - 2 * window : index - window]
        # 창이 달력상 연속인지 본다 — 휴업으로 날짜가 빠진 창은 "직전 7 일" 이 아니다.
        if (cur_days[-1] - prev_days[0]).days != 2 * window - 1:
            continue
        cur = pd.concat([by_day[day] for day in cur_days])
        prev = pd.concat([by_day[day] for day in prev_days])
        metrics = build_metrics(cur, prev, hours, weather.get(days[index]))

        for key, score in scores(metrics).items():
            if score >= 0.0:  # -1.0 은 "후보에서 빠짐" 이라 분포에 넣지 않는다
                axis_scores[key].append(score)

        picked = [focus._axis(block) for block in focus.assign(metrics)]
        for slot, axis in enumerate(picked):
            slots[slot][axis] += 1
        if len(picked) < focus.MAX_CARDS:
            short += 1

        if len(metrics["categoryBreakdown"]) == 1:
            guards["카테고리가 1종인 날"] += 1
        if max((c["share"] for c in metrics["categoryBreakdown"]), default=0.0) >= 0.95:
            guards["카테고리 최대 비중 >= 0.95 인 날"] += 1
        if len(metrics["menuRankings"]) == 1:
            guards["메뉴가 1종인 날"] += 1

    return {"axes": axis_scores, "slots": slots, "short": short, "guards": guards, "n": index}


def report(label: str, window: int, result: dict, total: int) -> None:
    print(f"\n창 {window}일 · {label} (표본 {total}창)")
    print(f"{'축':<10}{'평균':>9}{'표준편차':>11}{'1.0포화':>9}{'선택률':>9}")
    for key, name in LABELS.items():
        values = result["axes"][key]
        if not values:
            print(f"  {name:<8}{'후보 0회':>30}")
            continue
        chosen = sum(slot[key] for slot in result["slots"])
        mean = statistics.mean(values)
        sigma = statistics.pstdev(values) if len(values) > 1 else 0.0
        saturated = sum(1 for v in values if v >= 1.0) / len(values)
        # 선택률의 분모는 축이 후보였던 창이다 — 날씨처럼 자주 빠지는 축을 전체 창으로
        # 나누면 "뽑혔는데 안 뽑혔다" 로 읽힌다.
        print(
            f"  {name:<8}{mean:>9.3f}{sigma:>11.3f}{saturated:>8.0%}"
            f"{chosen / len(values):>9.0%}"
            + ("" if len(values) == total else f"  (후보 {len(values)}창)")
        )
    for slot, counter in enumerate(result["slots"], start=1):
        if not counter:
            continue
        filled = sum(counter.values())
        share = " · ".join(
            f"{LABELS[axis]} {count / filled:.0%}" for axis, count in counter.most_common()
        )
        print(f"  카드{slot}: {share}")
    print(f"  카드 3장 미달: {result['short']}창")
    for question, count in result["guards"].items():
        print(f"  {question}: {count} / {total}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        nargs="+",
        action="append",
        required=True,
        metavar=("이름", "POS엑셀"),
        help="매장 이름과 POS 엑셀 경로들. 매장마다 반복한다.",
    )
    parser.add_argument("--weather", type=Path, help="기상청 일별 극값 (없으면 날씨 축 제외)")
    parser.add_argument("--windows", type=int, nargs="+", default=[7, 28])
    # 기본값은 데이터 추정이다. 고정값은 2026-10-26 실험 기록(§7·§9)과 대조할 때만 쓴다 —
    # 그 표는 09:00~24:00 으로 쟀다.
    parser.add_argument("--opens", help="영업 시작 (예: 09:00). 생략하면 데이터에서 추정")
    parser.add_argument("--closes", help="영업 종료 (예: 24:00)")
    args = parser.parse_args()

    # assign() 이 창마다 후보·선택을 남긴다 — 수백 창이면 측정 출력이 묻힌다.
    logging.getLogger(focus.__name__).setLevel(logging.CRITICAL)

    fixed = None
    if args.opens or args.closes:
        if not (args.opens and args.closes):
            raise SystemExit("--opens 와 --closes 는 같이 줘야 한다")
        day_hours = {"opensAt": args.opens, "closesAt": args.closes}
        fixed = {"WEEKDAY": day_hours, "WEEKEND": day_hours}
    weather = load_weather(args.weather) if args.weather else {}
    if args.weather:
        print(f"날씨 {len(weather)}일 (isNotable=true 가정 = 상한)")

    for store in args.store:
        label, paths = store[0], [Path(p).expanduser() for p in store[1:]]
        if not paths:
            raise SystemExit(f"--store {label} 에 POS 엑셀 경로가 없다")
        print(f"\n=== {label} ===")
        pos = load_pos(paths)
        days = pos["date"].nunique()
        span = f"{pos['date'].min().date()}~{pos['date'].max().date()}"
        print(f"  {len(pos):,}행 · {days}일 · {span}")
        hours = fixed or business_hours(pos)
        shown = " · ".join(
            f"{key} {value['opensAt']}~{value['closesAt']}" for key, value in hours.items()
        )
        print(f"  영업시간 {'(고정)' if fixed else '(추정)'} {shown}")
        for window in args.windows:
            result = measure(pos, window, hours, weather)
            total = sum(result["slots"][0].values())
            if not total:
                print(f"\n창 {window}일 · {label}: 측정 가능한 창이 없다")
                continue
            report(label, window, result, total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
