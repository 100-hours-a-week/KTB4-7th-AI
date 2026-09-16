from typing import Literal

from app.schemas.common import Contract, Evidence


class ChatMessage(Contract):
    role: Literal["user", "assistant"]
    content: str


class ChatContext(Contract):
    type: Literal["SOLUTION_SUMMARY", "SOLUTION_DETAIL", "SAVED_SOLUTION"]
    content: str


class ChatRequest(Contract):
    userId: int
    storeId: int
    # 길이 검증은 BE 가 이미 한다(공백 제외 1~300자) — 계약 확정본 기준 AI 는 재검증하지 않는다.
    question: str
    context: ChatContext
    history: list[ChatMessage] = []


class ChatChunkData(Contract):
    content: str
    evidence: Evidence | None = None


class ChatChunk(Contract):
    event: Literal["answerChunk"] = "answerChunk"
    data: ChatChunkData
