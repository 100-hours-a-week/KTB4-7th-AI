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
