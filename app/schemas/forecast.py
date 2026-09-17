from typing import Literal

from app.schemas.common import Contract

# 노션 API 정의서 `POST /internal/v1/ai/forecast/batch`, 위키 [AI] 단계1 §3.3
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
    analysisRunId: int | None = None  # 계약상 필수지만 예측에 쓰지 않아 여기서 막지 않는다


class Prediction(Contract):
    """lowerBound·upperBound 는 80% 예측구간이다(`services/forecast/intervals.py`).

    비대칭이라 `predictedSalesAmount ± x` 로 복원할 수 없다. 두 값을 그대로 저장해야 한다.
    """

    targetDate: str
    predictedSalesAmount: int
    lowerBound: int
    upperBound: int
    modelVersion: str


class ForecastData(Contract):
    """basisDate·storeId·generatedAt 은 BE 가 저장할 때 채운다(노션 응답 예시 기준).

    월 합계·요일 평균도 넣지 않는다. 35일 예측은 두 달에 걸치고 다음 업로드 때 겹치는
    4~7일이 교체되므로, 여기서 한 번 계산해 넘긴 합계는 곧 낡는다. 저장된 일별 예측에서
    BE 분석 모듈이 집계한다.
    """

    forecastStartDate: str
    forecastEndDate: str
    horizonDays: int
    predictions: list[Prediction]


class ForecastResponse(Contract):
    message: str = "예측을 생성했습니다."
    data: ForecastData


class InsufficientHistoryData(Contract):
    """missingData 외 세 필드는 어느 조건에 걸렸는지 BE 가 로그로 남기기 위한 확장이다.

    완전월 2개와 학습 60행은 AND 조건이라, 월 수만으로는 어느 쪽이 걸렸는지 알 수 없다.
    """

    missingData: list[str]
    incompleteMonths: list[str]
    requiredTrainingRows: int
    providedTrainingRows: int


class InsufficientHistoryResponse(Contract):
    """이력 부족은 200 이다 — 요청 자체는 정상이고 업무 상태로 구분한다(노션 공통 원칙)."""

    message: str = "예측에 필요한 매출 이력이 부족합니다."
    status: Literal["INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"
    data: InsufficientHistoryData
