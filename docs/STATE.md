# 작업 상태

마지막 갱신: 2026-09-15
브랜치: `feat/1-초기개발환경설정` (Issue #1)

## 지금 어디

레포 초기 세팅 완료, **아직 원격에 푸시하지 않았다.** 원격 브랜치 0개.

```
* 2441a31 (feat/1-초기개발환경설정)  chore: FastAPI 초기 개발환경 설정
* b0874e2                            docs: AI 개발 규약과 세션 스킬 추가
* 877b26d (dev)                      chore: 저장소 초기화   ← 파일 0개
```

`dev` 는 빈 커밋 하나뿐이다. 모든 실제 내용은 feat 브랜치에 있고 PR로 올린다.

## 마지막으로 통과한 것

- `uv run pytest -q` — 1 passed (test_health)
- `uv run ruff check .` / `ruff format --check .` — 통과
- 서버 실기동 후 `curl localhost:8000/health` → `{"status":"ok"}`
- **미검증**: Docker 이미지 빌드 (로컬 데몬 꺼져 있음). PR CI의 docker job은 push 전용이라 `dev` 머지 후에야 실증된다.

## 🔴 최대 블로커 — API 계약 기준이 갈렸다 (확인됨, 추측 아님)

BE `AGENTS.md`: "API 구현은 API 정의서(노션)" / AI: 위키 기준으로 `app/schemas/` 작성 완료.

대조표: `docs/contract-diff-wiki-vs-notion.md` · 추적: **Issue #2** (결정 필요 13건)

가장 위험한 3가지:
1. **비율 표기가 100배 다르다** — 위키 `0.62` vs 노션 `62.0`. 둘 다 숫자라 스키마 검증을 통과한다. 에러 없이 틀린 값이 점주에게 간다.
2. **AI→BE 툴 경로 3건 불일치** — BE가 구현하는 쪽이라 안 맞으면 챗봇 툴 호출 전부 404.
3. **노션에 서버 간 인증 규약이 없다** — `X-Internal-Api-Key` 0건. AI는 이미 검증 구현됨 → BE가 안 보내면 전부 401.

**계약이 확정되기 전에 엔드포인트를 더 쌓지 말 것.** 지금은 수정 범위가 `app/schemas/` + 라우터 prefix + `errors.py` + 툴 경로 상수뿐이라 반나절이면 뒤집을 수 있다. 엔드포인트가 늘면 그만큼 커진다.

## 다음 한 걸음

계약 확정을 기다리는 동안 **계약에 의존하지 않는 것**부터 한다.

1. `devtools/stub_backend.py` — 툴 6종 스텁. 경로는 상수 하나로 빼서 계약 확정 시 한 줄로 바꾸게.
2. `app/prompts/solution_v1.py` — 프롬프트는 계약과 무관. 위키 단계4 원문 그대로.
3. `app/services/chat/graph.py` — LangGraph `agent ↔ tools` 골격. 툴 시그니처만 나중에 맞춤.

## 미해결 결정

- **Issue #2 의 13건** — 계약 관련. 여기 중복해서 적지 않는다.
- 클라우드 팀 통보 필요: 헬스체크 `GET /health`, 리스닝 포트 `8000`. 두 문서 어디에도 없어 AI가 정했다.
- 클라우드 팀 질문: CI의 ECR push 스텝 — 리포지토리 이름, 인증 방식(OIDC role vs access key). 확정 전까지 비워 둠.
- 헥터 확인: 예측 신뢰구간(Issue #2 11번), 월 합계·요일 평균을 누가 계산하는지(12번).
- 승인 방식: BE 규약은 "최종 승인 1회 후 commit → push → PR 연속 진행"인데, 제나 지시는 커밋마다 요청이다. 현재는 **제나 지시를 따르는 중**.

## 함정

- **GitHub 위키는 WebFetch가 실패한다.** JS 렌더라 "There was an error while loading"만 나온다. `curl -sL` + `markdown-body` 파싱을 써야 한다. `doc-digger` 에이전트가 이걸 안다.
- **노션 API 정의서는 90,000자**라 `notion-fetch` 가 통째로 못 읽고 파일로 떨어진다. grep으로 위치 찾고 슬라이스할 것.
- **BE가 보는 노션 페이지 ID가 제나가 준 링크와 다르다** (`3d57f3fa…` vs `3dcbdeb9…`). BE 쪽은 다른 워크스페이스라 접근이 안 된다. 같은 문서인지 미확인 — Issue #2 1번.
- 로컬 시스템 python은 3.9다. 반드시 `uv run` 을 거친다.
- 팀 표기는 **`memme`** 다. BE가 `mammae` → `memme` 로 개명했다(PR #1).

## 팀 규약 (BE `AGENTS.md` 기준)

- 기능 개발은 GitHub Issue로 시작 → `feat/이슈번호-기능명` → `dev` 대상 PR → 본문에 `Closes #N`
- 커밋은 **한글** Conventional Commit. PR 제목도 한글.
- PR 본문: 주요 변경사항 / 구현 기능 / 테스트 내용·결과 / API 변경 여부 / DB 변경 여부 / `Closes #N`
- 하나의 PR은 하나의 목적만.
