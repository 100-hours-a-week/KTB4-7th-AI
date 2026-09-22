# AI 서버 배포 설정

컨테이너를 띄울 때 필요한 값만 적는다. 코드 변경 없이 환경변수로만 주입한다.

## 환경변수

`.env` 는 `.dockerignore` 에 있어 이미지에 들어가지 않는다. **런타임에 환경변수로 넣어야 한다.**

| 이름 | 필수 | 예시 | 안 넣으면 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | `sk-ant-...` | 모든 LLM 호출이 **502** |
| `BACKEND_BASE_URL` | ✅ | `http://backend:8080` | 챗봇이 **컨테이너 자기 자신**을 호출해 `BACKEND_ERROR` |
| `LLM_PROVIDER` | | `anthropic` (기본) | — |
| `LLM_MODEL` | | `claude-sonnet-4-5` (기본) | — |
| `LLM_TIMEOUT_SECONDS` | | `60` (기본) | — |
| `BACKEND_TIMEOUT_SECONDS` | | `2.0` (기본) | — |
| `INSIGHT_LLM_TIMEOUT_SECONDS` | | `12` (기본) | — |
| `INTERNAL_AI_TOKEN` | | (없음) | 토큰 검증을 하지 않는다 |

`LLM_PROVIDER` 를 바꾸면 해당 provider 의 키가 대신 필요하다
(`OPENAI_API_KEY` / `GOOGLE_API_KEY` / `UPSTAGE_API_KEY`).
**anthropic 외 provider 는 실호출로 검증된 적이 없다.**

## 주의: 설정이 틀려도 기동은 성공한다

두 필수값 모두 코드에 기본값이 있어서 **앱은 정상 기동하고 `/health` 도 200 을 돌려준다.**
배포는 성공한 것처럼 보이고 첫 요청에서 터진다.

기동 로그에서 아래 줄이 보이면 환경변수가 빠진 것이다.

```
ERROR app.main 환경변수가 비어 있다 — 배포 설정을 확인한다: ANTHROPIC_API_KEY, BACKEND_BASE_URL(로컬 기본값 그대로다)
```

## 컨테이너

| | |
|---|---|
| 포트 | `8000` |
| 헬스체크 | `GET /health` → `{"status":"ok"}` |
| 이미지 태그 | full commit SHA (위키 CI 설계 기준) |

`/health` 는 **설정 상태를 보지 않는다.** 로드밸런서용 생존 확인이므로 키가 비어 있어도 200 이다.

## 인바운드

**인바운드를 BE 로만 제한하는 보안 그룹이 1차 경계다**(2026-09-16 팀 결정).
AI 서버가 외부에 열리면 인증 없이 LLM 을 호출할 수 있게 되므로, 보안 그룹 설정이 반드시 필요하다.

`INTERNAL_AI_TOKEN` 은 그 보안 그룹이 빠졌을 때를 위한 2차 방어선이다.
**값을 넣으면 검증이 켜지고, 비워 두면 기존대로 검증하지 않는다.**
BE 는 `Authorization: Bearer {INTERNAL_AI_TOKEN}` 으로 보낸다(2026-09-22 계약).

켤 때는 **BE 와 AI 양쪽에 같은 값**을 넣어야 한다. 한쪽만 설정하면 모든 요청이 401 이다.
연동 테스트는 비워 둔 채로 통과시키고, 끝난 뒤에 양쪽 동시에 주입하는 순서를 권한다.

## 장애 응답 재현 (BE 연동 테스트용)

BE 재시도 정책이 504 를 재시도 대상으로 둔다. 실제로 그 경로가 도는지 확인할 때 쓴다.

| 응답 | 재현 |
|---|---|
| `504` 모델 타임아웃 | `INSIGHT_LLM_TIMEOUT_SECONDS=0.001` 로 기동 |
| `502` 공급자 오류 | `ANTHROPIC_API_KEY=` (빈 값)으로 기동 |
| `401` 토큰 불일치 | `INTERNAL_AI_TOKEN` 을 설정하고 헤더 없이 호출 |
| `200 INSUFFICIENT_DATA` | `metrics.salesSummary.orderCount` 를 `0` 으로 |

`INSIGHT_LLM_TIMEOUT_SECONDS` 는 인사이트 경로에만 적용된다. 솔루션·챗봇은
`LLM_TIMEOUT_SECONDS` 를 쓴다 — 두 값이 분리된 이유는 `app/core/config.py` 주석 참고.

500(생성 실패)은 모델 응답이 깨져야 나와서 환경변수로 재현할 수 없다.

## 아직 안 된 것

ECR push 단계는 붙었다(#85, OIDC). **GitHub 레포 변수 4개가 비어 있어 건너뛴다.**

- `AWS_ACCOUNT_ID`
- `AWS_REGION`
- `AWS_ROLE_TO_ASSUME`
- `ECR_REPOSITORY`

네 값이 채워지면 `dev` push 마다 커밋 SHA 태그로 이미지가 올라간다. 그 전까지는
빌드와 컨테이너 기동 확인(`/health`)까지만 돈다.
