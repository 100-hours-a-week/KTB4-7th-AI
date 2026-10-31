"""SSE 스트리밍 챗봇 답변. 청크 포맷은 노션 API 정의서 기준 확정 —
docs/contract-diff-wiki-vs-notion.md §5 참고 (위키의 플랫 {"answerChunk":...} 대신
{"event":"answerChunk","data":{"content":...,"evidence":...}} 중첩 구조를 쓴다).

app/services/chat/graph.py 의 agent_node가 model.astream()으로 토큰 단위 응답을 만들고,
여기서는 compiled.astream_events()로 "agent" 노드의 on_chat_model_stream 이벤트만 걸러
실시간 SSE로 중계한다(계약: 답변은 토큰 단위 스트리밍 — docs/api정의서.md:1149). 도구 호출
결정 턴은 `_text_of` 가 걸러낸다 — 빈 content 가 아니라 블록 리스트로 온다.

evidence는 직전 "tools" 노드가 채운 last_evidence를 on_chain_end 이벤트에서 읽어 그 뒤에
오는 답변 청크마다 함께 실어 보낸다. 도구를 부르지 않고 context만으로 답하면 evidence는
계속 null이다.

스트리밍이 시작된 뒤에는 HTTP 상태를 더 바꿀 수 없어서(app/services/chat/graph.py 참고),
모델 실패는 answerChunk 대신 {"event":"error","data":{"code":...,"message":...}} 로 구분해
내려보낸다 — BE/FE가 문자열을 파싱하지 않고 code로 기계적으로 판단할 수 있게 하기 위함이다.
코드 3종: AI_TIMEOUT(모델 타임아웃), AI_GENERATION_ERROR(모델 호출 실패),
AI_TOOL_ERROR(도구 조회 2회 연속 실패 — 기존엔 실패 문구를 정상 답변처럼 answerChunk로
보냈는데, ERD chat_messages.status 의 FAILED 값과 맞추려면 error 이벤트가 더 맞다).

LLM_FALLBACK_PROVIDER가 설정돼 있으면(app/clients/llm.py의 circuit breaker 참고),
**아직 토큰을 하나도 내보내기 전**에 primary 호출이 가용성 문제로 실패하면 fallback
provider로 그래프를 다시 만들어 처음부터 한 번만 재시도한다. 토큰을 이미 보낸 뒤 실패하면
전환하지 않는다 — 이미 내려간 내용을 되돌릴 수 없어서 기존 error 이벤트로 끝낸다.
"""

import json

import sentry_sdk
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.clients import llm
from app.core.auth import verify_internal_token
from app.core.config import settings
from app.core.errors import ApiError
from app.prompts import chat as chat_prompt
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.chat import graph as chat_graph
from app.services.chat.tools import build_tools

router = APIRouter(prefix="/internal/v1/ai", dependencies=[Depends(verify_internal_token)])

# ChatRequest.history(app/schemas/chat.py)에 길이 제한이 없어 BE가 쌓인 대화를 그대로
# 보내면 시스템 프롬프트 + 툴 스키마 7종 + 히스토리가 로컬 vLLM의 --max-model-len
# (infra/vllm/serve.sh, 8192)을 넘긴다 — 2026-10-22 챗봇 전면 장애 원인.
#
# 처음엔 메시지 12개로 잘랐는데, 터지는 지점이 개수로 정해지지 않는다. Qwen3-32B-AWQ
# 토크나이저로 실측하면(2026-10-26) 한 턴이 짧으면 99 토큰, 길면 319 토큰이라 8192를
# 넘기는 히스토리가 20개~88개 사이 어디서든 나온다. 안전한 개수를 고르면 짧은 대화를
# 과도하게 자르고, 넉넉한 개수를 고르면 안 터진다는 보장이 없다. 그래서 개수가 아니라
# 토큰 예산으로 자른다.
MAX_MODEL_LEN = 8192

# 툴 스키마 7종(app/services/chat/tools.py) 실측값. 시스템 프롬프트는 context 카드 수에
# 따라 변해서 요청마다 추정하고, 이쪽은 고정이다.
TOOL_SCHEMA_TOKENS = 1029

# agent↔tools 사이클(app/services/chat/graph.py)이 한 요청 안에서 쌓는 툴 결과. tools_node는
# json.dumps(result)를 자르지 않고 그대로 메시지에 넣고, 성공하는 한 라운드 수에 상한이 없다.
# 7종을 모두 조회하는 질문에서 2,430 토큰 실측(get_category_breakdown 한 건이 983).
TOOL_RESULT_RESERVE = 2500

# 모델이 답을 쓸 자리. 챗봇 경로는 max_tokens를 보내지 않아서(graph.py get_model) vLLM이
# max_model_len - 프롬프트 만큼만 생성한다 — 프롬프트가 7,900까지 차면 400도 안 나고 폴백도
# 안 타고 답변이 문장 중간에 끊긴다. 실측 답변이 ~320 토큰이라 여유를 둬서 떼놓는다.
OUTPUT_RESERVE = 1024


def _estimate_tokens(text: str) -> int:
    """글자 하나를 토큰 하나로 센다 — 과대 추정이지만 자르기는 그쪽이 안전하다.

    Qwen3 토크나이저 실측(2026-10-26) 토큰/글자 비율은 한국어 산문 0.76~0.85, 숫자·한자·
    이모지가 1.00 이고 1.00 을 넘기는 입력은 찾지 못했다(자모 분리·제로폭 문자·깨진 바이트
    포함). 5 는 chat template 이 메시지 하나에 더하는 고정 토큰(실측).
    """
    return len(text) + 5


def _history_budget(system: str, question: str, provider: str) -> int | None:
    """로컬 vLLM 으로 갈 때만 예산을 매긴다. 아니면 None — 자르지 않는다.

    위 상수는 전부 로컬 vLLM 창(8192) 기준이다. fallback 으로 Claude(200k)에 가는 요청까지
    같은 자로 자르면 이유 없이 대화를 버린다. 조건은 app/services/chat/graph.py 의 get_model
    이 base_url 을 붙이는 분기와 같다 — core.config.uses_local_llm_server 는 settings 의
    provider 를 보는데, 여기서 봐야 하는 건 llm.resolve_primary_or_fallback 이 고른 provider 다.

    요청 중간에 fallback 으로 넘어가면(app/api/chat.py _stream) 이미 자른 히스토리로 Claude 를
    부르게 된다. 좁은 쪽으로 자른 거라 안전한 방향이고, 되돌리려면 메시지를 다시 만들어야 한다.
    """
    if not (provider == "openai" and settings.llm_base_url):
        return None
    return (
        MAX_MODEL_LEN
        - TOOL_SCHEMA_TOKENS
        - TOOL_RESULT_RESERVE
        - OUTPUT_RESERVE
        - _estimate_tokens(system)
        - _estimate_tokens(question)
    )


def _to_lc_messages(history: list[ChatMessage], budget: int | None) -> list:
    """예산 안에 들어가는 만큼 최근 대화부터 담는다. 시간순은 유지한다."""
    role_map = {"USER": HumanMessage, "ASSISTANT": AIMessage}
    if budget is None:
        return [role_map[m.role](m.content) for m in history]
    kept: list = []
    for message in reversed(history):
        budget -= _estimate_tokens(message.content)
        if budget < 0:
            break
        kept.append(role_map[message.role](message.content))
    kept.reverse()
    return kept


def _sse(content: str, evidence: dict | None) -> str:
    body = json.dumps(
        {"event": "answerChunk", "data": {"content": content, "evidence": evidence}},
        ensure_ascii=False,
    )
    return f"data: {body}\n\n"


def _text_of(content: str | list) -> str:
    """모델 청크에서 사용자에게 보낼 텍스트만 뽑는다.

    도구 호출 턴에서 Anthropic 은 content 를 문자열이 아니라 블록 리스트로 스트리밍한다
    (`[{"type": "tool_use", ...}]`, `[{"type": "input_json_delta", ...}]`). 그대로 내보내면
    계약(`content: str`)이 깨지고 도구 ID·인자가 사용자에게 샌다 — 실호출로 확인했다
    (2026-09-21, `devtools/llm_smoke.py`).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _error_sse(code: str, message: str) -> str:
    body = json.dumps(
        {"event": "error", "data": {"code": code, "message": message}}, ensure_ascii=False
    )
    return f"data: {body}\n\n"


async def _stream(
    tools: list, initial_state: dict, provider: str, model_name: str, started_on_fallback: bool
):
    model = chat_graph.get_model(tools, provider, model_name)
    compiled = chat_graph.build_graph(model, tools)
    evidence: dict | None = None
    sent_any = False
    tried_fallback = started_on_fallback

    while True:
        try:
            async for event in compiled.astream_events(initial_state, version="v2"):
                kind = event.get("event")
                if kind == "on_chain_end" and event.get("name") == "tools":
                    output = event.get("data", {}).get("output") or {}
                    evidence = output.get("last_evidence")
                    continue
                if kind == "on_chain_end" and event.get("name") == "give_up":
                    sentry_sdk.capture_exception(
                        ApiError(500, "AI_TOOL_ERROR", "AI_TOOL_ERROR"),
                        tags={"error_code": "AI_TOOL_ERROR"},
                    )
                    yield _error_sse("AI_TOOL_ERROR", chat_graph.FAILURE_PHRASE)
                    sent_any = True
                    continue
                if kind != "on_chat_model_stream":
                    continue
                if event.get("metadata", {}).get("langgraph_node") != "agent":
                    continue
                text = _text_of(event["data"]["chunk"].content)
                if text:
                    sent_any = True
                    yield _sse(text, evidence)
        except ApiError as exc:
            # 토큰을 하나도 안 보냈고, 아직 fallback으로 안 바꿔봤고, 가용성 문제면 —
            # 처음부터(에이전트↔툴 사이클 전체를) fallback provider로 다시 돈다. 이미
            # 뭔가 내보냈으면 내용을 되돌릴 수 없어 기존 error 이벤트로 끝낸다.
            if (
                not sent_any
                and not tried_fallback
                and settings.llm_fallback_provider
                and llm.is_fallback_eligible(exc)
            ):
                if not llm.is_capacity_error(exc):
                    llm.record_failure()
                llm.log_fallback(f"primary 호출 실패 — {exc.code}")
                tried_fallback = True
                model = chat_graph.get_model(
                    tools, settings.llm_fallback_provider, settings.llm_fallback_model
                )
                compiled = chat_graph.build_graph(model, tools)
                evidence = None
                continue
            if exc.status >= 500:
                sentry_sdk.capture_exception(exc, tags={"error_code": exc.code})
            yield _error_sse(exc.code, exc.message)
            break
        except Exception as exc:
            sentry_sdk.capture_exception(exc, tags={"error_code": "AI_GENERATION_ERROR"})
            raise
        else:
            if not started_on_fallback and not tried_fallback:
                llm.record_success()
            break
    yield "data: [DONE]\n\n"


@router.post("/chat/messages")
async def chat_messages(req: ChatRequest) -> StreamingResponse:
    tools = build_tools(req.storeId)
    provider, model_name, started_on_fallback = await llm.resolve_primary_or_fallback()

    system = chat_prompt.build_system([card.model_dump() for card in req.context], req.chatDate)
    history = _to_lc_messages(req.history, _history_budget(system, req.question, provider))
    messages = [SystemMessage(system), *history, HumanMessage(req.question)]
    initial_state = {"messages": messages, "failures": 0, "last_evidence": None}

    return StreamingResponse(
        _stream(tools, initial_state, provider, model_name, started_on_fallback),
        media_type="text/event-stream",
    )
