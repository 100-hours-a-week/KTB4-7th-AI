# 맴매 AI 서버

소상공인 매출 데이터로 **매출 예측 · 솔루션 생성 · 매출 인사이트 · 챗봇**을 제공하는 FastAPI
서버다. Backend가 넘겨준 데이터만 쓰고, 서비스 DB에는 직접 접근하지 않는다.

## 기술 스택

- **API**: FastAPI, Pydantic
- **매출 예측**: scikit-learn(Ridge 회귀), pandas, holidays
- **솔루션·인사이트·챗봇**: Anthropic Claude, LangGraph(챗봇 에이전트)
- **패키지 관리**: uv

## 빠른 시작

```bash
uv sync

cp .env.example .env
# .env 에 ANTHROPIC_API_KEY 를 채운다

uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

로컬에서 챗봇 툴(BE 조회 API)을 테스트하려면 스텁 서버를 같이 띄운다:

```bash
uv run python devtools/stub_backend.py   # 9000 포트
```

## 테스트 · 린트

```bash
uv run pytest
uv run ruff check --fix . && uv run ruff format .
```

## 엔드포인트

| 경로 | 방향 | 담당 |
|---|---|---|
| `POST /internal/v1/ai/forecast/batch` | BE → AI | 헥터 |
| `POST /internal/v1/ai/solutions/generate` | BE → AI | 제나 |
| `POST /internal/v1/ai/sales-insights` | BE → AI | 제나 |
| `POST /internal/v1/ai/chat/messages` (SSE) | BE → AI | 제나 |

정확한 요청·응답 스펙은 `docs/api정의서.md`·`docs/ERD정의서.md`가 기준 문서다.

## 프로젝트 구조

```
app/
├── api/        라우터 — 요청 파싱·응답 반환만
├── services/   비즈니스 로직 — LLM 호출, 재시도, 예측 파이프라인
├── schemas/    BE 와의 계약 (Pydantic)
├── prompts/    LLM 프롬프트 (버전별 파일 분리)
├── clients/    외부 호출 래퍼 (Anthropic, BE 조회 API)
└── core/       설정·에러 포맷
```

구조와 설계 이유(왜 이렇게 짰는지)는 `docs/ARCHITECTURE.md`에 정리돼 있다.

## 담당 경계 · 작업 규약

- **제나**: `app/api/{solutions,insights,chat}.py`, `app/services/{solution,insight,chat}`,
  `app/clients/`, `app/core/`, `app/prompts/`
- **헥터**: `app/api/forecast.py`, `app/services/forecast/`

브랜치·커밋·PR 규칙, 계약 변경 절차 등 작업 방식 전반은 `AGENTS.md`를 따른다.
