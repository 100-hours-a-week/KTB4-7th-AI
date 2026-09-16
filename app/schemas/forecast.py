from typing import Literal

from app.schemas.common import Contract

# 위키 [AI] 단계1 §3.3 — 예측 계약 상수
HORIZON_DAYS = 35
REQUIRED_COMPLETE_MONTHS = 2  # 예측 시작 달의 직전 두 달
MIN_TRAINING_ROWS = 60  # 첫 데이터 월은 전월 피처가 없어 학습 행에서 빠진다


class DailySale(Contract):
    date: str  # YYYY-MM-DD, 오름차순·연속(매출 없는 날은 0)
    amount: int  # 메뉴 매출(menu_net_amount) — 주차권·선불카드 충전 등 비메뉴 제외
    orderCnt: int  # 유효 주문 수(메뉴 수량 합 > 0인 주문)


class ForecastRequest(Contract):
    storeId: int
    uploadId: int
    forecastStartDate: str  # dailySales 마지막 날짜 + 1일. 다르면 422
    dailySales: list[DailySale]


class Prediction(Contract):
    date: str
    predictedAmount: int
    isHoliday: bool | None = None  # v2


class ForecastResponse(Contract):
    """월 합계·요일 평균은 넣지 않는다.

    35일 예측은 두 달에 걸치고 다음 업로드 때 겹치는 4~7일이 교체되므로, 여기서 한 번
    계산해 넘긴 합계는 곧 낡는다. 저장된 일별 예측에서 BE 분석 모듈이 집계한다 (위키 §7.1).
    """

    status: Literal["SUCCESS", "INSUFFICIENT_HISTORY"]
    forecastStartDate: str
    forecastEndDate: str | None = None
    horizonDays: int | None = None
    predictions: list[Prediction]
    modelVersion: str | None = None
    # INSUFFICIENT_HISTORY 일 때만 채워진다
    incompleteMonths: list[str] | None = None
    requiredTrainingRows: int | None = None
    providedTrainingRows: int | None = None
