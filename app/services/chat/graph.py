"""위키 [AI] 단계3 §2.1, 단계4 §4.1. LangGraph 단일 에이전트: agent↔tools 조건부 사이클.

context 만으로 답할 수 있으면 툴을 부르지 않는다. 툴 실행이 연속 2회 실패하면
agent 로 더 돌지 않고 고정 실패 문구를 반환한다 (단계3 §2.1 — "2회 실패 시 실패 문구를 반환한다").
대화 이력은 BE 의 메시지 테이블 책임이라 이 그래프는 checkpointer 를 쓰지 않는다.
"""

import json

from anthropic import AnthropicError, APITimeoutError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.messages import ToolMessage as LCToolMessage
from langgraph.graph import END, MessagesState, StateGraph

from app.core.config import settings
from app.core.errors import ApiError

MAX_TOOL_FAILURES = 2
FAILURE_PHRASE = "죄송합니다. 지금은 데이터를 조회하지 못했어요. 잠시 후 다시 시도해주세요."


class ChatState(MessagesState):
    failures: int


def get_model(tools: list) -> ChatAnthropic:
    return ChatAnthropic(model=settings.llm_model, api_key=settings.anthropic_api_key).bind_tools(
        tools
    )


async def _call_model(model, messages: list) -> AIMessage:
    try:
        return await model.ainvoke(messages)
    except APITimeoutError as exc:
        raise ApiError(504, "LLM_TIMEOUT", "모델 응답이 시간 내에 완료되지 않았습니다.") from exc
    except AnthropicError as exc:
        raise ApiError(502, "LLM_ERROR", "모델 공급자 호출에 실패했습니다.") from exc


def _route_after_agent(state: ChatState) -> str:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END


def _route_after_tools(state: ChatState) -> str:
    return "give_up" if state.get("failures", 0) >= MAX_TOOL_FAILURES else "agent"


def _give_up_node(state: ChatState) -> dict:
    return {"messages": [AIMessage(content=FAILURE_PHRASE)]}


def build_graph(model, tools: list):
    tool_map = {t.name: t for t in tools}

    async def agent_node(state: ChatState) -> dict:
        response = await _call_model(model, state["messages"])
        return {"messages": [response]}

    async def tools_node(state: ChatState) -> dict:
        last = state["messages"][-1]
        failures = state.get("failures", 0)
        outputs = []
        for call in last.tool_calls:
            try:
                result = await tool_map[call["name"]].ainvoke(call["args"])
                failures = 0
                content = json.dumps(result, ensure_ascii=False)
            except Exception as exc:
                failures += 1
                content = f"조회 실패: {exc}"
            outputs.append(LCToolMessage(content=content, tool_call_id=call["id"]))
        return {"messages": outputs, "failures": failures}

    graph = StateGraph(ChatState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("give_up", _give_up_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", END: END})
    graph.add_conditional_edges(
        "tools", _route_after_tools, {"agent": "agent", "give_up": "give_up"}
    )
    graph.add_edge("give_up", END)

    return graph.compile()
