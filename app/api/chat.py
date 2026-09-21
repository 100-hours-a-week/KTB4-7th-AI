"""SSE 스트리밍 챗봇 답변. 청크 포맷은 노션 API 정의서 기준 확정 —
docs/contract-diff-wiki-vs-notion.md §5 참고 (위키의 플랫 {"answerChunk":...} 대신
{"event":"answerChunk","data":{"content":...,"evidence":...}} 중첩 구조를 쓴다).

app/services/chat/graph.py 의 agent_node가 model.astream()으로 토큰 단위 응답을 만들고,
여기서는 compiled.astream_events()로 "agent" 노드의 on_chat_model_stream 이벤트만 걸러
실시간 SSE로 중계한다(계약: 답변은 토큰 단위 스트리밍 — docs/api정의서.md:1149). 도구 호출
결정 턴은 보통 빈 content만 스트리밍하므로 `if chunk.content` 로 자연스럽게 걸러진다.

evidence는 직전 "tools" 노드가 채운 last_evidence를 on_chain_end 이벤트에서 읽어 그 뒤에
오는 답변 청크마다 함께 실어 보낸다. 도구를 부르지 않고 context만으로 답하면 evidence는
계속 null이다.

스트리밍이 시작된 뒤에는 HTTP 상태를 더 바꿀 수 없어서(app/services/chat/graph.py 참고),
모델 실패는 answerChunk 대신 {"event":"error","data":{"code":...,"message":...}} 로 구분해
내려보낸다 — BE/FE가 문자열을 파싱하지 않고 code로 기계적으로 판단할 수 있게 하기 위함이다.
코드 3종: AI_TIMEOUT(모델 타임아웃), AI_GENERATION_ERROR(모델 호출 실패),
AI_TOOL_ERROR(도구 조회 2회 연속 실패 — 기존엔 실패 문구를 정상 답변처럼 answerChunk로
보냈는데, ERD chat_messages.status 의 FAILED 값과 맞추려면 error 이벤트가 더 맞다).
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.errors import ApiError
from app.prompts import chat as chat_prompt
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.chat import graph as chat_graph
from app.services.chat.tools import build_tools

router = APIRouter(prefix="/internal/v1/ai")


def _to_lc_messages(history: list[ChatMessage]) -> list:
    role_map = {"USER": HumanMessage, "ASSISTANT": AIMessage}
    return [role_map[m.role](m.content) for m in history]


def _sse(content: str, evidence: dict | None) -> str:
    body = json.dumps(
        {"event": "answerChunk", "data": {"content": content, "evidence": evidence}},
        ensure_ascii=False,
    )
    return f"data: {body}\n\n"


def _error_sse(code: str, message: str) -> str:
    body = json.dumps(
        {"event": "error", "data": {"code": code, "message": message}}, ensure_ascii=False
    )
    return f"data: {body}\n\n"


async def _stream(compiled, initial_state: dict):
    evidence: dict | None = None
    try:
        async for event in compiled.astream_events(initial_state, version="v2"):
            kind = event.get("event")
            if kind == "on_chain_end" and event.get("name") == "tools":
                output = event.get("data", {}).get("output") or {}
                evidence = output.get("last_evidence")
                continue
            if kind == "on_chain_end" and event.get("name") == "give_up":
                yield _error_sse("AI_TOOL_ERROR", chat_graph.FAILURE_PHRASE)
                continue
            if kind != "on_chat_model_stream":
                continue
            if event.get("metadata", {}).get("langgraph_node") != "agent":
                continue
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield _sse(chunk.content, evidence)
    except ApiError as exc:
        yield _error_sse(exc.code, exc.message)
    yield "data: [DONE]\n\n"


@router.post("/chat/messages")
async def chat_messages(req: ChatRequest) -> StreamingResponse:
    tools = build_tools(req.storeId)
    model = chat_graph.get_model(tools)
    compiled = chat_graph.build_graph(model, tools)

    system = chat_prompt.build_system([card.model_dump() for card in req.context])
    messages = [SystemMessage(system), *_to_lc_messages(req.history), HumanMessage(req.question)]

    initial_state = {"messages": messages, "failures": 0, "last_evidence": None}
    return StreamingResponse(_stream(compiled, initial_state), media_type="text/event-stream")
