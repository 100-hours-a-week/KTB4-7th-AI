---
name: ai-endpoint
description: AI 서버에 내부 엔드포인트를 추가하는 표준 절차. schema → 실패 테스트 → service → router → curl 검증 순으로 진행한다. solutions/insights/chat/forecast 처럼 /internal/v1/ai/* 경로를 새로 만들거나 고칠 때 사용한다.
---

# AI 엔드포인트 추가

엔드포인트 4개가 전부 같은 모양이다. 순서를 지키면 계약이 어긋나지 않는다.

**시작 전 확인**: `docs/api정의서.md`·`docs/ERD정의서.md`의 해당 절을 읽었는가? 이 두 문서가
BE와 합의한 최종 계약이다(위키·`contract-diff-wiki-vs-notion.md`는 과거 대조 기록일 뿐, 실제와
다를 수 있다 — 실제로 그랬던 적이 있다). 안 읽었으면 `doc-digger` 에이전트로 먼저 가져온다.
기억으로 쓰지 않는다.

## 절차

### 1. 스키마
`app/schemas/<name>.py` 에 요청·응답 모델을 쓴다.

- `app/schemas/common.py` 의 `Contract` 를 상속한다 (`extra="ignore"` — 2026-09-16 팀 결정. BE/AI가
  따로 배포되므로 한쪽이 필드를 먼저 추가해도 다른 쪽이 422로 막지 않는다. 정의되지 않은 필드는
  무시되고, 필수 필드 누락만 422가 된다).
- 필드명은 **camelCase 그대로**. snake_case로 바꾸지 않는다.
- 금액은 `int`(원), 비율은 `int`(퍼센트 정수, 예: 62 — 2026-09-16 팀 결정으로 소수(0.62) 대신 정수), 날짜는 `str`(YYYY-MM-DD).
- 이미 있는 `Evidence` / `Metrics` 를 재사용한다. 비슷한 걸 새로 만들지 않는다.

→ **확인**: API 정의서의 표와 필드명·타입·필수여부가 전부 일치하는가

### 2. 실패하는 테스트
`tests/test_<name>.py` 에 먼저 쓴다. 최소 3개:

- 정상 경로 (200, 응답 스키마 검증)
- 필수 필드 누락 (422)
- 도메인 실패 경로 (해당 엔드포인트의 특수 상태 — `INSUFFICIENT_HISTORY` 등)

```python
import httpx
from app.main import app


async def test_x():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/internal/v1/ai/...", json={...})
```

LLM 호출은 실제로 때리지 않는다. `app/clients/llm.py` 를 monkeypatch 한다.

→ **확인**: `uv run pytest tests/test_<name>.py` 가 FAIL 한다 (에러가 아니라 실패)

### 3. 서비스
`app/services/<name>.py` 에 로직을 쓴다. 라우터에는 로직을 두지 않는다.

- LLM 재시도는 **1회**. 그 이상 돌리지 않는다 (비용·불안정).
- LLM에 넘기는 건 요청으로 받은 확정 지표뿐. 서비스가 새 수치를 계산하지 않는다.
- 코드단에서 판정 가능한 게이트(최소 데이터 일수 등)는 **LLM 호출 전에** 처리한다.

→ **확인**: `uv run pytest tests/test_<name>.py` PASS

### 4. 라우터
`app/api/<name>.py` → `app/main.py` 에 `include_router`.

```python
router = APIRouter(prefix="/internal/v1/ai")
```

서버 간 인증은 앱 레벨에서 검증하지 않는다(2026-09-16 팀 결정 — 클라우드 보안그룹이 인바운드를
BE로만 제한). `Depends(verify_internal_key)` 를 붙이지 않는다.

→ **확인**: `/docs` 에 노출되고 경로가 API 정의서와 글자 단위로 같은가(`/internal/v1/ai/...`)

### 5. 실호출 검증
```bash
uv run uvicorn app.main:app --port 8000 &
# 정상
curl -s -X POST localhost:8000/internal/v1/ai/<path> \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/<name>_request.json | jq
# 필수 필드 누락 → 422
curl -s -X POST localhost:8000/internal/v1/ai/<path> -d '{}'
```

→ **확인**: 오류 응답이 `{"message":"..."}` 형태인가(특정 상황에만 `failReason` 추가)

### 6. 마무리
- `uv run ruff check --fix . && uv run ruff format .`
- `uv run pytest` 전체 통과
- `docs/STATE.md` 갱신 (`handoff` 스킬)
- **커밋은 사용자에게 요청한다. 직접 하지 않는다.**

## 자주 틀리는 것

- 응답에 `modelVersion`·`promptVersion` 빠뜨리기 — solutions는 필수, insights는 없음(엔드포인트마다 다르니 API 정의서 확인)
- 라우터에서 직접 LLM 호출 — 서비스로 내린다
- 성공 응답을 플랫으로 반환 — API 정의서 기준은 `{"message":"...", "data": {...}}` 래퍼다
- `INSUFFICIENT_*`/`INSUFFICIENT_DATA` 상태를 4xx로 반환 — **200**이다
- `Depends(verify_internal_key)` 되살리기 — 서버 간 인증은 앱 레벨에서 안 한다(4절 참고)
