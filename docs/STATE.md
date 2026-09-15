# 작업 상태

마지막 갱신: 2026-09-15
브랜치: `feat/bootstrap`

## 지금 어디

Task 0 (레포 부트스트랩 + 계약 스키마) 완료. Task 0b (스킬·에이전트) 완료.
다음은 Task 1 (스텁 BE + 클라이언트).

## 마지막으로 통과한 것

- `uv run pytest -q` — 1 passed (test_health)
- `uv run ruff check .` — All checks passed
- 서버 실기동 후 `curl localhost:8000/health` → `{"status":"ok"}` 확인

## 다음 한 걸음

`devtools/stub_backend.py` 작성 — 챗봇 툴 6종을 노션 응답 예시 그대로 반환하는
최소 FastAPI 앱(포트 9000). 그 다음 `app/clients/backend.py` (httpx + tenacity).

## 미해결 결정

전부 **아직 팀에 묻지 않았다.** 9/23 서버연결 전까지 답이 필요하다.

1. **API 계약 — BE 담당자에게**: 위키 기준으로 가기로 했는데 BE가 노션을 보고 있을 수 있다.
   경로(`/internal/ai/*` vs `/internal/v1/ai/*`), 성공 응답(플랫 vs `{"message","data"}`),
   오류 응답 포맷, **툴 6종 경로**(`hourly-profile` vs `hourly-profiles`,
   `/internal/v1/forecast` vs `/internal/v1/sales/forecasts`) 전부 다르다.
   툴 6종은 BE가 구현하므로 특히 위험하다.
2. **클라우드 팀에 통보**: 헬스체크 `GET /health`, 리스닝 포트 `8000`.
   두 문서 어디에도 없어서 AI가 정했다.
3. **클라우드 팀에 질문**: `X-Internal-Api-Key` 발급·주입 방식 (Secrets Manager / SSM / .env?).
   CI의 ECR push 스텝도 리포지토리 이름과 인증 방식(OIDC role vs access key)이 확정돼야 추가 가능.
4. **BE 담당자에게**: `get_category_breakdown` 이 참조할 테이블이 ERD에 없다
   (위키 단계4에 명시된 이슈). 카테고리 단위 분석이 MVP 범위인가?
5. **헥터에게**: 노션 툴 명세는 예측에 `lowerBound`/`upperBound` 를 요구하는데
   위키의 Ridge 설계는 단일값만 낸다. 신뢰구간을 낼 건가?

## 함정

- **GitHub 위키는 WebFetch가 실패한다.** JS 렌더라 "There was an error while loading"만 나온다.
  `curl -sL` + `markdown-body` 파싱을 써야 한다. `doc-digger` 에이전트가 이걸 안다.
- **노션 API 정의서는 90,000자**라 `notion-fetch` 가 통째로 못 읽고 파일로 떨어진다.
  grep으로 위치 찾고 슬라이스할 것.
- 로컬 시스템 python은 3.9다. 반드시 `uv run` 을 거친다.
