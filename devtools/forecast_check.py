"""BE ↔ AI `forecast/batch` 연동 점검 스크립트.

POS 엑셀에 전처리 규칙(위키 [AI] 단계1 §3.3)을 적용해 `dailySales` 를 만들고,
AI 서버 응답이 계약대로 나오는지 시나리오별로 확인한다.

    # 기본: 서버를 띄우지 않고 앱을 직접 호출 (-m 으로 실행해야 app 패키지를 찾는다)
    uv run python -m devtools.forecast_check --pos 매출리포트.xlsx

    # 실제 서버 대상
    uv run python -m devtools.forecast_check --pos 매출리포트.xlsx --url http://localhost:8000

    # BE 가 만든 일별 집계와 대조 ([{"date","amount","orderCnt"}, ...])
    uv run python -m devtools.forecast_check --pos 매출리포트.xlsx --be-daily be_daily.json

값이 다르면 예측도 달라지므로, BE 연동 시 `--be-daily` 대조를 먼저 통과시키는 것이 중요하다.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import pandas as pd

EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿️‍]")
NON_MENU_EXACT = {
    "배달비",
    "배달료",
    "쿠팡이츠",
    "배민1",
    "영수증 포토리뷰 이벤트",
    "블로그 인스타 체험단",
    "루미코르 행주타월",
}
PASS, FAIL = "  ✓", "  ✗"
failures = 0


def report(ok: bool, label: str, detail: str = "") -> None:
    global failures
    if not ok:
        failures += 1
    print(f"{PASS if ok else FAIL} {label}{f' — {detail}' if detail else ''}")


def clean(name: str) -> str:
    return " ".join(EMOJI.sub("", str(name)).split())


def is_menu(name: str) -> bool:
    return not (name.startswith("주차권") or "선불카드" in name or name in NON_MENU_EXACT)


def build_daily_sales(pos_path: Path) -> list[dict]:
    """전처리 규칙대로 일별 메뉴 매출과 유효 주문 수를 만든다.

    취소 행을 포함해서 합산한다. POS 는 주문을 취소해도 원본 `완료` 행을 남기고 금액·수량이
    음수인 `취소` 행을 덧붙이므로, 전부 더해야 취소분이 상쇄된 순매출이 나온다.
    `결제상태 == "완료"` 로 거르면 취소된 주문이 매출로 잡힌다.
    """
    df = pd.read_excel(pos_path, sheet_name="상품 주문 상세내역", skiprows=[1], dtype=str)
    df.columns = [" ".join(str(c).split()) for c in df.columns]
    amount_col = next(c for c in df.columns if c.startswith("실판매금액"))

    df["amount"] = df[amount_col].astype(int)
    df["quantity"] = df["수량"].astype(int)
    df["date"] = pd.to_datetime(df["주문기준일자"], format="%Y-%m-%d")
    df["menu_name"] = df["상품명"].map(clean)
    menu = df[df["menu_name"].map(is_menu)].copy()

    amounts = menu.groupby("date")["amount"].sum()
    # 주문 식별은 (채널, 주문번호) 까지다. 주문시작시각을 키에 넣으면 같은 주문이 쪼개져
    # 주문 수가 부풀려진다 — BE 집계와 대조해서 확인했다(2026-09-21).
    menu["order_key"] = list(zip(menu["주문채널"], menu["주문번호"], strict=True))
    per_order = menu.groupby(["date", "order_key"])["quantity"].sum()
    counts = per_order[per_order > 0].reset_index().groupby("date").size()

    index = pd.date_range(amounts.index.min(), amounts.index.max())
    amounts = amounts.reindex(index, fill_value=0)
    counts = counts.reindex(index, fill_value=0)
    return [
        {"date": str(day.date()), "amount": int(amounts[day]), "orderCnt": int(counts[day])}
        for day in index
    ]


def next_day(date: str) -> str:
    return str((pd.Timestamp(date) + pd.Timedelta(days=1)).date())


class Ai:
    """--url 이 없으면 서버 없이 앱을 직접 호출한다."""

    def __init__(self, url: str | None):
        self.base = url or "http://ai"
        if url:
            self.transport = None
        else:
            from app.main import app

            self.transport = httpx.ASGITransport(app=app)

    async def post(self, rows: list[dict], start: str | None = None) -> httpx.Response:
        payload = {
            "storeId": 1024,
            "uploadId": 1,
            "forecastStartDate": start or next_day(rows[-1]["date"]),
            "dailySales": rows,
        }
        async with httpx.AsyncClient(
            transport=self.transport, base_url=self.base, timeout=30
        ) as client:
            return await client.post("/internal/v1/ai/forecast/batch", json=payload)


def compare_with_be(mine: list[dict], be_path: Path) -> None:
    payload = json.loads(be_path.read_text())
    # BE 가 보내주는 파일이 요청 바디 통째일 때도 있고 dailySales 배열만일 때도 있다.
    be_rows = payload["dailySales"] if isinstance(payload, dict) else payload
    be = {r["date"]: r for r in be_rows}
    ours = {r["date"]: r for r in mine}
    only_ai = sorted(set(ours) - set(be))
    only_be = sorted(set(be) - set(ours))
    report(
        not only_ai and not only_be,
        "날짜 범위 일치",
        f"AI만 {len(only_ai)}일 / BE만 {len(only_be)}일",
    )

    diffs = [
        (d, ours[d], be[d])
        for d in sorted(set(ours) & set(be))
        if ours[d]["amount"] != be[d].get("amount") or ours[d]["orderCnt"] != be[d].get("orderCnt")
    ]
    report(not diffs, "일별 금액·주문 수 일치", f"{len(diffs)}일 불일치")
    for date, a, b in diffs[:5]:
        print(
            f"      {date}  AI {a['amount']:,}/{a['orderCnt']}"
            f"  BE {b.get('amount'):,}/{b.get('orderCnt')}"
        )


async def run(rows: list[dict], ai: Ai) -> None:
    print(f"\n[0] 전처리 결과 — {len(rows)}일 ({rows[0]['date']} ~ {rows[-1]['date']})")
    print(f"      메뉴 매출 합계 {sum(r['amount'] for r in rows):,}원")

    print("\n[1] 정상 요청")
    res = await ai.post(rows)
    body = res.json()
    report(res.status_code == 200, "200 응답", f"status={res.status_code}")
    if res.status_code == 200 and "status" not in body:
        data = body["data"]
        preds = data["predictions"]
        dates = [p["targetDate"] for p in preds]
        expected = [str(d.date()) for d in pd.date_range(data["forecastStartDate"], periods=35)]
        report(len(preds) == 35, "예측 35건", f"{len(preds)}건")
        report(dates == expected, "날짜 연속·시작일 일치")
        report(
            data.get("forecastEndDate") == expected[-1],
            "forecastEndDate",
            str(data.get("forecastEndDate")),
        )
        report(
            "monthlyTotal" not in data and "dowAverage" not in data,
            "월 합계·요일 평균 없음(BE 집계)",
        )
        report(all(p["predictedSalesAmount"] >= 0 for p in preds), "예측값 0 이상")
        report(
            all(isinstance(p["predictedSalesAmount"], int) for p in preds),
            "예측값 정수(원)",
        )
        report(
            all(p["lowerBound"] <= p["predictedSalesAmount"] <= p["upperBound"] for p in preds),
            "예측구간이 예측값을 감쌈",
        )
        widths = [(p["upperBound"] - p["lowerBound"]) / p["predictedSalesAmount"] for p in preds]
        print(f"      80% 예측구간 폭 중앙값 {sorted(widths)[len(widths) // 2]:.0%}")
    else:
        report(False, "성공 응답", json.dumps(body, ensure_ascii=False)[:120])

    print("\n[2] 이력 부족 (앞 60일만)")
    res = await ai.post(rows[:60])
    body = res.json()
    data = body.get("data") or {}
    report(res.status_code == 200, "200 응답(422 아님)", f"status={res.status_code}")
    report(
        body.get("status") == "INSUFFICIENT_DATA",
        "status=INSUFFICIENT_DATA",
        str(body.get("status")),
    )
    report(
        data.get("missingData") == ["INSUFFICIENT_HISTORY"],
        "missingData=[INSUFFICIENT_HISTORY]",
        str(data.get("missingData")),
    )
    print(
        f"      학습 행 {data.get('providedTrainingRows')}"
        f" / 필요 {data.get('requiredTrainingRows')}"
        f", 불완전한 달 {data.get('incompleteMonths')}"
    )

    print("\n[3] 날짜 누락")
    gap = len(rows) // 2
    broken = rows[:gap] + rows[gap + 1 :]
    res = await ai.post(broken, start=next_day(rows[-1]["date"]))
    report(res.status_code == 422, "422 응답", f"status={res.status_code}")
    report(res.json().get("failReason") == "INVALID_DAILY_SALES", "failReason=INVALID_DAILY_SALES")

    print("\n[4] 시작일 불일치")
    res = await ai.post(rows, start=next_day(next_day(rows[-1]["date"])))
    report(res.status_code == 422, "422 응답", f"status={res.status_code}")
    report(
        res.json().get("failReason") == "INVALID_FORECAST_START_DATE",
        "failReason=INVALID_FORECAST_START_DATE",
    )

    print("\n[5] 연속 업로드 겹침")
    # 운영과 같게 "완전한 월의 말일까지" 두 번 업로드한 상황을 만든다.
    by_month: dict[str, list[dict]] = {}
    for row in rows:
        by_month.setdefault(row["date"][:7], []).append(row)
    complete = [
        month for month, days in by_month.items() if len(days) == pd.Period(month).days_in_month
    ]
    if len(complete) < 2:
        print("      완전한 월이 2개 미만이라 건너뜀")
        return
    earlier, later = sorted(complete)[-2:]
    first_cut = [r for r in rows if r["date"][:7] <= earlier]
    second_cut = [r for r in rows if r["date"][:7] <= later]
    print(f"      업로드 1: ~{earlier} 말일 / 업로드 2: ~{later} 말일")
    a = (await ai.post(first_cut)).json()
    b = (await ai.post(second_cut)).json()
    if "status" not in a and "status" not in b:
        first, second = a["data"]["predictions"], b["data"]["predictions"]
        overlap = {p["targetDate"] for p in first} & {p["targetDate"] for p in second}
        report(
            len(overlap) > 0,
            "겹치는 예측 날짜 존재",
            f"{len(overlap)}일 — BE는 최신 예측으로 교체해야 함",
        )
        for date in sorted(overlap)[:3]:
            old = next(p["predictedSalesAmount"] for p in first if p["targetDate"] == date)
            new = next(p["predictedSalesAmount"] for p in second if p["targetDate"] == date)
            print(f"      {date}  이전 {old:,} → 최신 {new:,}")
    else:
        print("      두 업로드 중 하나가 이력 부족이라 건너뜀")


def main() -> int:
    parser = argparse.ArgumentParser(description="forecast/batch 연동 점검")
    parser.add_argument("--pos", type=Path, required=True, help="POS 매출리포트 엑셀 경로")
    parser.add_argument("--url", help="AI 서버 주소 (생략하면 앱을 직접 호출)")
    parser.add_argument("--be-daily", type=Path, help="BE 가 만든 일별 집계 JSON")
    parser.add_argument("--dump", type=Path, help="생성한 dailySales 를 JSON 으로 저장")
    args = parser.parse_args()

    rows = build_daily_sales(args.pos)
    if args.dump:
        args.dump.write_text(json.dumps(rows, ensure_ascii=False))
        print(f"dailySales 저장: {args.dump}")
    if args.be_daily:
        print("\n[BE 집계 대조]")
        compare_with_be(rows, args.be_daily)

    asyncio.run(run(rows, Ai(args.url)))
    print(f"\n{'실패 ' + str(failures) + '건' if failures else '전체 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
