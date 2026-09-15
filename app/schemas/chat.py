from typing import Literal

from pydantic import Field

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
    # 위키는 300토큰 상한이나 BE가 이미 공백 제외 300자로 검증한다. 같은 기준을 쓴다.
    question: str = Field(min_length=1, max_length=300)
    context: ChatContext
    history: list[ChatMessage] = []


class ChatChunk(Contract):
    answerChunk: str
    evidence: Evidence | None = None
