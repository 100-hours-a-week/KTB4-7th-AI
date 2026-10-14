from typing import Literal

from pydantic import Field

from app.schemas.common import Contract

MenuCategory = Literal["COFFEE", "TEA", "BEVERAGE", "CAKE", "BAKERY", "OTHER"]
MenuFailReason = Literal["LOW_IMAGE_QUALITY", "MENU_TEXT_NOT_FOUND", "AI_PROCESSING_ERROR"]


class MenuImageInput(Contract):
    imageId: int
    imageUrl: str
    order: int


class MenuRecognitionRequest(Contract):
    storeId: int
    batchId: int
    images: list[MenuImageInput] = Field(min_length=1, max_length=10)


class DetectedMenuItem(Contract):
    sourceImageId: int
    name: str = Field(min_length=1, max_length=100)  # VARCHAR(100), 공백 거부는 서비스에서 검증
    # NULL 허용: 판별 불가 시 OTHER로 강제하지 않는다(2026-10-14 노션 ST-04 확인)
    category: MenuCategory | None = None
    # NULL 허용: 가격이 불명확하면 추측하지 않는다(ERD detected_price, menus.category 제약 참고)
    price: int | None = Field(default=None, ge=0, le=1_000_000)
    confidence: float = Field(ge=0, le=1)
    priceReviewRequired: bool


class FailedImage(Contract):
    sourceImageId: int
    failReason: MenuFailReason


class MenuRecognitionData(Contract):
    detectedItems: list[DetectedMenuItem] = []
    failedImages: list[FailedImage] = []


class MenuRecognitionResponse(Contract):
    message: str = "메뉴가 인식되었습니다."
    data: MenuRecognitionData
