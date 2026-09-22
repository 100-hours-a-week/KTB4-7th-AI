"""위키 [AI] 단계3 §2.1, 단계4 §4.1. LangGraph 단일 에이전트: agent↔tools 조건부 사이클.

context 만으로 답할 수 있으면 툴을 부르지 않는다. 툴 실행이 연속 2회 실패하면
agent 로 더 돌지 않고 고정 실패 문구를 반환한다 (단계3 §2.1 — "2회 실패 시 실패 문구를 반환한다").
대화 이력은 BE 의 메시지 테이블 책임이라 이 그래프는 checkpointer 를 쓰지 않는다.

agent_node는 model.astream()으로 토큰 단위 응답을 만든다 — app/api/chat.py가
compiled.astream_events()로 이 토큰을 실시간 SSE로 중계한다(계약: 답변은 토큰 단위
스트리밍 — docs/api정의서.md:1149). tools_node는 조회에 성공할 때마다 last_evidence를
갱신해, 다음 답변 청크에 "그 수치가 실제 서버 산출값과 일치함"을 실어 보낼 수 있게 한다.

ponytail: 스트리밍이 시작되면(StreamingResponse가 200 헤더를 보낸 시점) HTTP 상태 코드를
더 바꿀 수 없어, 모델 호출 실패(provider별 타임아웃/생성 오류)를 502/504로 올리지 못하고
API 레이어에서 in-stream 실패 문구로만 내려간다 — 업그레이드하려면 클라이언트가 "생성 시작"
ack 이벤트를 받은 뒤에만 안전하다고 간주하는 프로토콜을 BE와 새로 합의해야 한다.
"""

import json

import openai
from anthropic import AnthropicError, APITimeoutError
from google.genai import errors as genai_errors
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages import ToolMessage as LCToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

from app.core.config import (
    GOOGLE_THINKING_MODELS,
    OPENAI_REASONING_MODELS,
    UPSTAGE_BASE_URL,
    settings,
)
from app.core.errors import ApiError

MAX_TOOL_FAILURES = 2

# 프롬프트 캐싱은 아직 붙이지 않았다. 2026-09-22 실측(count_tokens, sonnet-4-5):
#
#   system(프롬프트 + context) 532 토큰 + 툴 스키마 1,569 = 2,101 토큰
#
# Sonnet 최소 단위 1024 를 넘고, agent↔tools 사이클이 모델을 2회 이상 부르므로 조건 자체는
# 맞는다(1회차 쓰기 → 2회차 읽기). 그런데도 미루는 이유가 셋 있다.
#
# 1. 이익이 작다. 2회 루프 기준 입력 토큰의 약 20% 절약인데 입력이 2천 토큰대라 절대액이
#    미미하다. v1 사용자 30명 규모에서는 더 그렇다.
# 2. cache_control 은 Anthropic 전용이다. LLM_PROVIDER 추상화(#61)를 해둔 뒤라 캐싱을
#    붙이면 provider 분기가 다시 생긴다.
# 3. 기본 TTL 이 5분이다. 점주가 5분 안에 다음 질문을 해야 히트한다. 대화가 띄엄띄엄하면
#    쓰기만 반복해 오히려 25% 손해다.
#
# 붙일 시점은 비용이 아니라 지연이 이유가 될 때다 — 캐시 읽기는 TTFB 를 줄여 체감이
# 좋아진다. 툴이 6종으로 늘거나(2,300 토큰대), 재질문이 잦아지거나, provider 를 Claude 로
# 고정하기로 하면 그때 다시 본다.
FAILURE_PHRASE = "죄송합니다. 지금은 데이터를 조회하지 못했어요. 잠시 후 다시 시도해주세요."

_EVIDENCE_METRIC_NAMES = {
    "get_sales_summary": "sales_summary",
    "get_category_breakdown": "category_breakdown",
    "get_hourly_profile": "hourly_profile",
    "get_forecast": "forecast",
}


class ChatState(MessagesState):
    failures: int
    last_evidence: dict | None


def get_model(tools: list) -> BaseChatModel:
    provider = settings.llm_provider
    if provider == "anthropic":
        model = ChatAnthropic(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    elif provider == "openai":
        kwargs = {
            "model": settings.llm_model,
            "api_key": settings.openai_api_key,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": 0,
        }
        if settings.llm_model in OPENAI_REASONING_MODELS:
            # GPT-5.6 Luna처럼 reasoning이 기본인 모델만 non-reasoning으로 고정한다 —
            # reasoning이 없는 openai 모델(LLM_MODEL)에는 이 파라미터 자체를 보내지 않는다.
            kwargs["reasoning_effort"] = "none"
        model = ChatOpenAI(**kwargs)
    elif provider == "upstage":
        model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.upstage_api_key,
            base_url=UPSTAGE_BASE_URL,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    elif provider == "google":
        kwargs = {
            "model": settings.llm_model,
            "google_api_key": settings.google_api_key,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": 0,
        }
        if settings.llm_model in GOOGLE_THINKING_MODELS:
            # Gemini 3+는 thinking_level="low"가 최솟값이다 — thinking_budget=0 같은
            # 완전 off는 없다 (app/core/config.py의 GOOGLE_THINKING_MODELS 주석 참고).
            kwargs["thinking_level"] = "low"
        model = ChatGoogleGenerativeAI(**kwargs)
    else:
        raise ValueError(f"지원하지 않는 LLM_PROVIDER: {provider}")
    return model.bind_tools(tools)


async def _stream_model(model, messages: list, config) -> AIMessage:
    try:
        chunk: AIMessageChunk | None = None
        async for piece in model.astream(messages, config=config):
            chunk = piece if chunk is None else chunk + piece
        return chunk
    except (APITimeoutError, openai.APITimeoutError, TimeoutError) as exc:
        raise ApiError(
            504, "AI_TIMEOUT", "응답 생성이 시간을 초과했습니다. 다시 시도해주세요."
        ) from exc
    except (AnthropicError, openai.OpenAIError, genai_errors.APIError) as exc:
        raise ApiError(
            500, "AI_GENERATION_ERROR", "답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
        ) from exc


def _build_evidence(tool_name: str, args: dict, result: dict) -> dict | None:
    """도구 조회 결과에서 답변 근거로 쓸 구조화된 지표를 뽑는다.

    result는 서버(BE)가 계산해 돌려준 값 그대로이므로, 여기서 골라 담는 value는 항상
    서버 산출값과 일치한다 — 모델이 만든 숫자가 아니다.
    """
    metric = _EVIDENCE_METRIC_NAMES.get(tool_name)
    if metric is None:
        return None
    if tool_name == "get_sales_summary":
        period = result.get("period") or {}
        return {
            "metric": metric,
            "period": period.get("startDate"),
            "dayType": None,
            "value": result.get("changeRate"),
        }
    if tool_name == "get_forecast":
        forecasts = result.get("forecasts") or []
        if not forecasts:
            return None
        first = forecasts[0]
        return {
            "metric": metric,
            "period": first.get("targetDate"),
            "dayType": None,
            "value": first.get("predictedSalesAmount"),
        }
    return {
        "metric": metric,
        "period": args.get("period"),
        "dayType": args.get("day_of_week"),
        "value": None,
    }


def _route_after_agent(state: ChatState) -> str:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END


def _route_after_tools(state: ChatState) -> str:
    return "give_up" if state.get("failures", 0) >= MAX_TOOL_FAILURES else "agent"


def _give_up_node(state: ChatState) -> dict:
    return {"messages": [AIMessage(content=FAILURE_PHRASE)], "last_evidence": None}


def build_graph(model, tools: list):
    tool_map = {t.name: t for t in tools}

    async def agent_node(state: ChatState, config) -> dict:
        response = await _stream_model(model, state["messages"], config)
        return {"messages": [response]}

    async def tools_node(state: ChatState) -> dict:
        last = state["messages"][-1]
        failures = state.get("failures", 0)
        evidence = state.get("last_evidence")
        outputs = []
        for call in last.tool_calls:
            try:
                result = await tool_map[call["name"]].ainvoke(call["args"])
                failures = 0
                evidence = _build_evidence(call["name"], call["args"], result)
                content = json.dumps(result, ensure_ascii=False)
            except Exception as exc:
                failures += 1
                content = f"조회 실패: {exc}"
            outputs.append(LCToolMessage(content=content, tool_call_id=call["id"]))
        return {"messages": outputs, "failures": failures, "last_evidence": evidence}

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
