from typing import Literal

from app.schemas.common import Contract, Evidence


class ChatMessage(Contract):
    role: Literal["USER", "ASSISTANT"]
    content: str


class ChatContextCard(Contract):
    rankNo: int
    title: str
    summaryText: str
    detailText: str
    evidence: str | None = None


class ChatRequest(Contract):
    userId: int
    storeId: int
    # 대화 시점의 날짜(YYYY-MM-DD). 모델이 "지난달" 같은 상대 기간을 절대 날짜로 바꿔
    # period=CUSTOM 으로 조회하는 데 쓴다 — 없으면 이번 달만 조회하고 나머지는 역산한다.
    # BE 가 안 보내도 422 로 막지 않는다(기존 동작 유지).
    chatDate: str | None = None
    # 길이 검증은 BE 가 이미 한다(공백 제외 1~300자) — 계약 확정본 기준 AI 는 재검증하지 않는다.
    question: str
    context: list[ChatContextCard]
    history: list[ChatMessage] = []


class ChatChunkData(Contract):
    content: str
    evidence: Evidence | None = None


class ChatChunk(Contract):
    event: Literal["answerChunk"] = "answerChunk"
    data: ChatChunkData
