"""BE 요청 바디가 AI 스키마와 맞는지 미리 대조한다.

연동 첫날 422 가 나면 어느 필드 때문인지 응답만 봐서는 알 수 없다(`app/core/errors.py` 는
"요청 필드가 스키마와 일치하지 않습니다" 한 줄만 돌려준다). 이 스크립트는 그 422 를
필드 단위로 풀어준다.

    # AI 가 기대하는 요청 모양을 출력한다 — BE 에 보내서 맞춰본다
    uv run python -m devtools.contract_check --example solutions

    # BE 가 준 샘플이 맞는지 검사한다
    uv run python -m devtools.contract_check --check solutions be_sample.json

`metrics` 는 api정의서에 산문 설명만 있고 리터럴 예시가 없어서(2026-09-21 확인) BE 와
필드명이 어긋날 위험이 가장 크다. 연동 전에 세 엔드포인트 모두 --check 를 통과시킨다.
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.chat import ChatRequest
from app.schemas.forecast import ForecastRequest
from app.schemas.insight import InsightRequest
from app.schemas.solution import SolutionRequest

SCHEMAS: dict[str, type[BaseModel]] = {
    "forecast": ForecastRequest,
    "solutions": SolutionRequest,
    "sales-insights": InsightRequest,
    "chat": ChatRequest,
}

_METRICS = {
    "salesSummary": {"netSales": 1183600, "vsPrevPeriod": -0.12},
    "predictedSalesToday": 1250000,
    "hourlyProfile": [
        {"dayType": "WEEKDAY", "hour": 14, "amount": 30000},
        {"dayType": "WEEKEND", "hour": 14, "amount": 92000},
    ],
    "categoryBreakdown": [{"name": "커피", "share": 0.62, "vsPrevPeriod": -0.12}],
    "reviewSummary": None,
}

EXAMPLES: dict[str, dict] = {
    "forecast": {
        "storeId": 1,
        "uploadId": 1,
        "analysisRunId": 1,
        "forecastStartDate": "2026-07-01",
        "dailySales": [{"date": "2026-04-01", "amount": 947100, "orderCnt": 80}],
    },
    "solutions": {
        "storeId": 1,
        "salesAnalysisId": 771,
        "targetDate": "2026-09-21",
        "triggerType": "UPLOAD",
        "metrics": _METRICS,
    },
    "sales-insights": {
        "storeId": 1,
        "salesAnalysisId": 771,
        "targetMonth": "2026-08",
        "triggerType": "UPLOAD",
        "metrics": _METRICS,
        "maxInsightCount": 3,
    },
    "chat": {
        "userId": 7,
        "storeId": 1,
        "question": "이번 달 매출이 지난달보다 어땠어?",
        "history": [{"role": "USER", "content": "안녕"}],
        "context": [
            {
                "rankNo": 1,
                "title": "평일 14~17시 프로모션",
                "summaryText": "오후 비피크 시간대 방문을 유도하세요.",
                "detailText": "14시~17시 아메리카노 20% 할인을 진행하세요.",
                "evidence": "평일 14시 매출이 주말 대비 낮습니다.",
            }
        ],
    },
}


def ignored_keys(model: type[BaseModel], value, path: str = "") -> list[str]:
    """`extra="ignore"` 때문에 조용히 버려지는 키를 찾는다.

    422 는 시끄럽게 실패하지만 이쪽은 아무 말 없이 사라져서 더 위험하다 — BE 가 보낸 지표가
    LLM 에 닿지 않아도 응답은 200 으로 나간다.
    """
    if not isinstance(value, dict):
        return []
    found = []
    for key, sub in value.items():
        if key not in model.model_fields:
            found.append(f"{path}{key}")
            continue
        annotation = model.model_fields[key].annotation
        for inner in (annotation, *getattr(annotation, "__args__", ())):
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                if isinstance(sub, list):
                    for i, item in enumerate(sub):
                        found += ignored_keys(inner, item, f"{path}{key}[{i}].")
                else:
                    found += ignored_keys(inner, sub, f"{path}{key}.")
                break
    return found


def check(name: str, payload: dict) -> int:
    model = SCHEMAS[name]
    print(f"[{name}] {model.__name__}\n")

    try:
        model(**payload)
    except ValidationError as exc:
        print(f"  ✗ 스키마 불일치 {exc.error_count()}건 — 이대로 보내면 422 입니다")
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(최상위)"
            print(f"      {where}: {err['msg']}")
        return 1

    print("  ✓ 스키마 통과 — 422 안 납니다")

    dropped = ignored_keys(model, payload)
    if dropped:
        print(f"\n  ⚠ 조용히 버려지는 필드 {len(dropped)}개 (extra=ignore, 에러 안 남):")
        for key in dropped:
            print(f"      {key}")
        print("      → AI 가 안 쓰는 값이면 정상. 쓰여야 하는 값이면 스키마에 추가해야 합니다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--example", choices=sorted(SCHEMAS), help="기대하는 요청 예시 출력")
    parser.add_argument("--check", nargs=2, metavar=("ENDPOINT", "JSON"), help="샘플 검사")
    args = parser.parse_args()

    if args.example:
        print(json.dumps(EXAMPLES[args.example], ensure_ascii=False, indent=2))
        return 0

    if args.check:
        name, path = args.check
        if name not in SCHEMAS:
            print(f"엔드포인트는 {sorted(SCHEMAS)} 중 하나여야 한다: {name}")
            return 2
        return check(name, json.loads(Path(path).read_text()))

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
