"""SSE 스트리밍 챗봇 답변. 청크 포맷은 노션 API 정의서 기준 확정 —
docs/contract-diff-wiki-vs-notion.md §5 참고 (위키의 플랫 {"answerChunk":...} 대신
{"event":"answerChunk","data":{"content":...,"evidence":...}} 중첩 구조를 쓴다).

에이전트 루프(app/services/chat/graph.py)를 먼저 끝까지 돌려 완성된 답변을 얻은 뒤
그 텍스트를 청크로 나눠 SSE 로 내보낸다 (모델 토큰 단위 스트리밍은 아직 아님 — docs/STATE.md 참고).
이렇게 하면 그래프 실행 중 발생하는 502/504/500 이 스트림이 열리기 전에 일반 HTTP 에러로 나간다.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.prompts import chat as chat_prompt
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.chat import graph as chat_graph
from app.services.chat.tools import build_tools

router = APIRouter(prefix="/internal/v1/ai")

CHUNK_SIZE = 40


def _to_lc_messages(history: list[ChatMessage]) -> list:
    role_map = {"USER": HumanMessage, "ASSISTANT": AIMessage}
    return [role_map[m.role](m.content) for m in history]


def _sse(answer_chunk: str) -> str:
    body = json.dumps(
        {"event": "answerChunk", "data": {"content": answer_chunk, "evidence": None}},
        ensure_ascii=False,
    )
    return f"data: {body}\n\n"


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


async def _stream(answer: str):
    for piece in _chunk_text(answer):
        yield _sse(piece)
    yield "data: [DONE]\n\n"


@router.post("/chat/messages")
async def chat_messages(req: ChatRequest) -> StreamingResponse:
    tools = build_tools(req.storeId)
    model = chat_graph.get_model(tools)
    compiled = chat_graph.build_graph(model, tools)

    system = chat_prompt.build_system([card.model_dump() for card in req.context])
    messages = [SystemMessage(system), *_to_lc_messages(req.history), HumanMessage(req.question)]

    result = await compiled.ainvoke({"messages": messages, "failures": 0})
    answer = result["messages"][-1].content

    return StreamingResponse(_stream(answer), media_type="text/event-stream")
