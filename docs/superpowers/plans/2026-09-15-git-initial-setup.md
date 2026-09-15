# 깃 초기 세팅 · 브랜치 전략 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비어 있는 `KTB4-7th-AI` 레포를 BE 레포와 동일한 관례로 초기화하고, 지금 로컬에만 있는 부트스트랩 결과물을 `dev` + `feat/*` PR 두 단계로 올린다.

**Architecture:** 에이전트 지침의 본문은 도구 중립인 `AGENTS.md`에 두고 `CLAUDE.md`는 `@AGENTS.md` 임포트만 한다. 스킬·서브에이전트는 자동 인식이 되는 `.claude/` 에 남긴다. 커밋은 BE와 같이 에이전트 설정·문서를 `dev`에 먼저 올리고, 앱 골격은 `feat/*` 브랜치에서 PR로 올려 CI를 첫 PR부터 검증한다.

**Tech Stack:** git, GitHub CLI (`gh`), GitHub Actions

---

## ⚠️ 실행 후 정정 (2026-09-15)

BE PR #1(머지됨)과 BE `AGENTS.md` 를 크로스체크한 결과 **아래 항목이 실제와 다르다.** 실행은 정정된 내용으로 했다.

| 플랜 원문 | 실제 |
|---|---|
| 커밋 메시지는 영문 소문자 타입 | **한글** Conventional Commit. BE 실제 예: `chore: 초기 개발환경 설정` |
| 브랜치명 `feat/initial-development-environment` | `feat/1-초기개발환경설정` — BE 규약은 `feat/이슈번호-기능명` |
| `dev` 에 에이전트 설정·문서 커밋 | `dev` 는 **빈 커밋 1개**. 모든 내용이 feat 브랜치로 (사용자 지시) |
| Task 2 / Task 3 를 별도 브랜치로 | 두 커밋 모두 같은 feat 브랜치. BE도 한 브랜치에 여러 커밋 후 PR 1개 |
| PR 제목·본문 영문 | 제목 한글. 본문은 `주요 변경사항 / 구현 기능 / 테스트 내용·결과 / API 변경 여부 / DB 변경 여부 / Closes #N` |
| (없음) | **GitHub Issue 선행 생성 필수.** Issue #1, #2 생성함 |

또한 Task 2 Step 7 이후(`dev` 푸시, 기본 브랜치 지정)는 **실행하지 않았다.** 사용자가 오늘 푸시를 보류했다.

**푸시 전에 Issue #2(API 계약 기준 확정)가 먼저 정리돼야 한다.** BE는 노션, AI는 위키 기준으로 갈려 있다 — `docs/contract-diff-wiki-vs-notion.md` 참조.

---

## Global Constraints

- **커밋·푸시 전에 반드시 사용자 승인을 받는다.** 이 플랜의 모든 커밋 스텝은 승인 요청에서 멈춘다.
- 원격 레포: `https://github.com/100-hours-a-week/KTB4-7th-AI.git` (커밋 0개, 원격 브랜치 0개)
- 기본 브랜치는 `dev`. `main`은 만들지 않는다 — BE(`KTB4-7th-BE`)가 `dev` 단일 기본 브랜치다.
- 커밋 메시지는 Conventional Commits, 영문 소문자 타입. BE 실제 예: `docs: add backend governance skill`, `docs: record task one validation evidence`
- 브랜치명은 `feat/<kebab-case>`. BE 실제 예: `feat/initial-development-environment`
- Claude Code는 `AGENTS.md`를 읽지 않는다. `CLAUDE.md`의 `@AGENTS.md` 임포트로 연결한다.
- 스킬은 `.claude/skills/<name>/SKILL.md`, 서브에이전트는 `.claude/agents/<name>.md` 에서만 자동 인식된다. 다른 경로로 옮기지 않는다.
- 파이썬은 `uv run` 을 거친다 (시스템 python은 3.9).

---

## File Structure

현재 로컬에 있는 파일을 두 커밋으로 나눈다. 분할 기준은 BE의 `dev` / `feat` 브랜치 구성과 같다.

**커밋 A — `dev` (에이전트 설정 · 문서)**
| 파일 | 책임 |
|---|---|
| `AGENTS.md` | 도구 중립 프로젝트 지침 본문 (현 `CLAUDE.md` 내용 이동) |
| `CLAUDE.md` | `@AGENTS.md` 임포트 + Claude Code 전용 안내만 |
| `.claude/skills/ai-endpoint/SKILL.md` | 엔드포인트 추가 표준 절차 |
| `.claude/skills/handoff/SKILL.md` | 세션 인계 절차 |
| `.claude/agents/doc-digger.md` | 위키·노션 발췌 서브에이전트 |
| `docs/STATE.md` | 세션 인계 노트 |
| `docs/superpowers/plans/2026-09-15-git-initial-setup.md` | 이 플랜 |
| `.gitignore` | `.venv/`, `.env` 등 제외 |

`.gitignore`는 BE에선 `feat` 브랜치에 있지만 여기선 커밋 A에 넣는다. 로컬에 이미 `.venv/`(수백 MB)와 `.env`(API 키)가 있어서 첫 커밋부터 없으면 사고가 난다.

**커밋 B — `feat/initial-development-environment` (앱 골격)**
| 파일 | 책임 |
|---|---|
| `pyproject.toml`, `uv.lock` | 의존성 잠금 |
| `app/main.py` | FastAPI 앱 + `GET /health` |
| `app/core/{config,auth,errors}.py` | 설정 · 내부 인증 · 위키 오류 포맷 |
| `app/schemas/*.py` | BE↔AI 계약 (단일 진실 원천) |
| `app/{api,services,clients,prompts}/__init__.py` | 빈 패키지 (다음 Task에서 채움) |
| `tests/test_health.py` | 헬스체크 테스트 |
| `Dockerfile`, `.dockerignore` | 컨테이너 빌드 |
| `.env.example` | 환경변수 예시 |
| `.github/workflows/ci.yml` | PR: ruff+pytest / dev push: docker build + 헬스체크 |

---

### Task 1: AGENTS.md 분리와 CLAUDE.md 임포트 전환

**Files:**
- Create: `AGENTS.md`
- Modify: `CLAUDE.md` (전체 교체)

**Interfaces:**
- Consumes: 현재 `CLAUDE.md` 의 전체 내용
- Produces: `AGENTS.md` (본문), `CLAUDE.md` (임포트 1줄 + Claude 전용 절)

- [ ] **Step 1: 현재 CLAUDE.md를 AGENTS.md로 이동**

```bash
git mv CLAUDE.md AGENTS.md 2>/dev/null || mv CLAUDE.md AGENTS.md
```

커밋 전이라 `git mv`는 실패한다. `mv`가 정상 경로다.

- [ ] **Step 2: AGENTS.md 제목 한 줄 수정**

첫 줄 `# 맴매 AI 서버` 를 아래로 바꾼다. BE의 `# 맴매 Backend Conventions` 와 짝을 맞춘다.

```markdown
# 맴매 AI Conventions
```

- [ ] **Step 3: CLAUDE.md를 임포트 전용으로 새로 작성**

`@AGENTS.md` 는 백틱 밖에 있어야 임포트된다. 코드블록 안에 넣으면 문자열로 취급된다.

```markdown
@AGENTS.md

## Claude Code 전용

- 스킬: `.claude/skills/` — `ai-endpoint`(엔드포인트 추가), `handoff`(세션 인계)
- 서브에이전트: `.claude/agents/doc-digger.md` — 위키·노션에서 필요한 절만 발췌
- 세션을 시작하면 `docs/STATE.md` 부터 읽는다. 위키를 다시 훑지 않는다.
```

- [ ] **Step 4: 임포트가 실제로 로드되는지 확인**

```bash
test -f AGENTS.md && grep -q '^@AGENTS.md' CLAUDE.md && echo "구조 OK"
```
Expected: `구조 OK`

이어서 새 Claude Code 세션에서 `/context` 를 실행하고 **Memory files** 목록에 `CLAUDE.md` 와 `AGENTS.md` 가 둘 다 보이는지 눈으로 확인한다. 안 보이면 `@AGENTS.md` 가 백틱에 감싸였거나 첫 줄이 아닌 것이다.

- [ ] **Step 5: 기존 검증이 여전히 통과하는지 확인**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```
Expected: `All checks passed!` / `23 files already formatted` / `1 passed`

---

### Task 2: dev 브랜치 생성과 첫 푸시

**Files:**
- Modify: 없음 (Task 1 결과물을 커밋만 한다)

**Interfaces:**
- Consumes: Task 1의 `AGENTS.md`, `CLAUDE.md`
- Produces: 원격 `dev` 브랜치, 기본 브랜치 설정

- [ ] **Step 1: dev 브랜치로 이동**

현재 `feat/bootstrap` 에 커밋이 0개라 브랜치를 그냥 바꿔 단다.

```bash
git checkout -b dev
git branch -D feat/bootstrap 2>/dev/null || true
git branch --show-current
```
Expected: `dev`

- [ ] **Step 2: 커밋 A 대상만 스테이징**

```bash
git add AGENTS.md CLAUDE.md .gitignore .claude/ docs/
git status --short
```
Expected: `A` 로 시작하는 줄에 `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.claude/**`, `docs/**` 만 보인다.
`app/`, `tests/`, `Dockerfile`, `pyproject.toml`, `.github/` 는 `??`(untracked)로 남아야 한다.

- [ ] **Step 3: .venv 와 .env 가 섞이지 않았는지 확인**

```bash
git diff --cached --name-only | grep -E '^\.venv/|^\.env$' && echo "위험: 제외 대상 포함" || echo "안전"
```
Expected: `안전`

- [ ] **Step 4: 사용자에게 커밋 승인 요청**

커밋하지 말고 멈춘다. 스테이징된 파일 목록을 보여주고 아래 메시지로 커밋해도 되는지 묻는다.

```
docs: add AI agent conventions and session skills
```

- [ ] **Step 5: 승인 후 커밋**

```bash
git commit -m "docs: add AI agent conventions and session skills"
git log --oneline
```
Expected: 커밋 1개

- [ ] **Step 6: 사용자에게 푸시 승인 요청**

푸시는 별도 승인이다. 커밋 승인이 푸시 승인을 포함하지 않는다.

- [ ] **Step 7: 승인 후 dev 푸시**

```bash
git push -u origin dev
git ls-remote --heads origin
```
Expected: `refs/heads/dev` 한 줄

- [ ] **Step 8: 기본 브랜치를 dev로 지정**

```bash
gh api -X PATCH repos/100-hours-a-week/KTB4-7th-AI -f default_branch=dev
gh repo view 100-hours-a-week/KTB4-7th-AI --json defaultBranchRef
```
Expected: `{"defaultBranchRef":{"name":"dev"}}`

권한이 없어 403이 나면 여기서 멈추고 레포 admin(클라우드 담당자 또는 조직 운영자)에게 요청한다. 직접 우회하지 않는다.

---

### Task 3: feat 브랜치로 앱 골격 PR

**Files:**
- Modify: 없음 (남은 untracked 파일을 커밋한다)

**Interfaces:**
- Consumes: 원격 `dev` 브랜치
- Produces: `feat/initial-development-environment` 브랜치, `dev` 로 향하는 PR, CI 실행 결과

- [ ] **Step 1: feat 브랜치 생성**

BE의 `feat/initial-development-environment` 와 같은 이름을 쓴다.

```bash
git checkout -b feat/initial-development-environment
git branch --show-current
```
Expected: `feat/initial-development-environment`

- [ ] **Step 2: 앱 골격 스테이징**

```bash
git add pyproject.toml uv.lock app/ tests/ Dockerfile .dockerignore .env.example .github/
git status --short
```
Expected: 남는 `??` 가 없다 (`.venv/`, `.env` 는 `.gitignore` 로 빠져 애초에 안 보인다)

- [ ] **Step 3: .env 가 섞이지 않았는지 재확인**

`.env.example` 은 포함, `.env` 는 제외여야 한다.

```bash
git diff --cached --name-only | grep -x '\.env' && echo "위험: 실제 키 포함" || echo "안전"
```
Expected: `안전`

- [ ] **Step 4: 커밋 전 전체 검증**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```
Expected: `All checks passed!` / `already formatted` / `1 passed`

- [ ] **Step 5: 사용자에게 커밋 승인 요청**

아래 메시지로 커밋해도 되는지 묻고 멈춘다.

```
feat: add FastAPI skeleton with BE contract schemas
```

- [ ] **Step 6: 승인 후 커밋과 푸시**

```bash
git commit -m "feat: add FastAPI skeleton with BE contract schemas"
git push -u origin feat/initial-development-environment
```

- [ ] **Step 7: PR 생성 승인 요청 후 생성**

PR 생성도 외부에 드러나는 동작이라 승인을 받는다. 승인 후:

```bash
gh pr create --base dev --head feat/initial-development-environment \
  --title "feat: add FastAPI skeleton with BE contract schemas" \
  --body "$(cat <<'EOF'
## 무엇
AI 서버 초기 골격. 위키 [AI] 단계1(모델 API 설계) 기준으로 BE↔AI 계약 스키마를 먼저 고정했다.

- `app/schemas/` — 계약의 단일 진실 원천. `extra="forbid"` 로 정의되지 않은 요청 필드는 422가 된다.
- `app/core/` — 설정, `X-Internal-Api-Key` 인증, 위키 오류 포맷(`success`/`error.code`/`traceId`)
- `app/main.py` — `GET /health`
- `.github/workflows/ci.yml` — PR에서 ruff + pytest, dev push에서 docker build + 컨테이너 헬스체크

## 확인한 것
- `uv run pytest -q` → 1 passed
- `uv run ruff check .` / `ruff format --check .` → 통과
- 서버 실기동 후 `curl localhost:8000/health` → `{"status":"ok"}`
- Docker 이미지 빌드는 로컬 데몬이 꺼져 있어 **미검증**. 이 PR의 CI로 확인한다.

## 팀 확인 필요
- 예측 모듈(`app/api/forecast.py`, `app/services/forecast/`)은 헥터 담당. `app/schemas/forecast.py` 만 먼저 고정해 뒀다.
- 헬스체크 경로 `/health`, 포트 `8000` 은 위키·클라우드 문서에 없어 AI가 정했다. 클라우드 팀 확인 필요.
- CI의 ECR push 스텝은 리포지토리 이름과 인증 방식이 확정되지 않아 비워 뒀다.
EOF
)"
```

- [ ] **Step 8: CI 결과 확인**

```bash
gh pr checks --watch
```
Expected: `test` job 성공. `docker` job은 `if: github.event_name == 'push'` 라 PR에서는 실행되지 않는다.

`test` 가 실패하면 로그를 보고 고친다. CI 환경에는 `.env` 가 없어서 `INTERNAL_API_KEY` 를 워크플로우의 `env:` 로 주입하고 있다 — 이게 빠지면 `app.core.config` 임포트 시점에 `ValidationError` 로 죽는다.

```bash
gh run view --log-failed
```

- [ ] **Step 9: STATE.md 갱신**

`docs/STATE.md` 의 "지금 어디"와 "다음 한 걸음"을 고친다. 브랜치명도 `feat/initial-development-environment` 로 바꾼다. `handoff` 스킬의 형식을 따른다.

- [ ] **Step 10: 머지는 사용자에게 맡긴다**

PR 머지를 자동으로 하지 않는다. CI 통과 사실만 보고하고 사용자가 머지 여부를 정한다.

---

## Self-Review

**1. 스펙 커버리지**
- BE 관례 맞추기(AGENTS.md) → Task 1
- 기본 브랜치 `dev`, `main` 없음 → Task 2 Step 1·8
- Conventional Commits 영문 → Task 2 Step 4, Task 3 Step 5
- `feat/*` → `dev` PR, CI 검증 → Task 3
- 스킬 자동 인식 유지(`.claude/`) → Task 1에서 경로를 건드리지 않음으로 충족
- 커밋·푸시 사용자 승인 → Task 2 Step 4·6, Task 3 Step 5·7, Step 10

**2. 플레이스홀더**
없음. 모든 스텁 명령과 기대 출력이 구체적이다.

**3. 이름 일관성**
브랜치명 `feat/initial-development-environment` 가 Task 3 Step 1·6·7·8·9 에서 동일하다. 커밋 메시지 두 개가 Task 2 Step 4↔5, Task 3 Step 5↔6 에서 각각 동일하다.

**4. 알려진 미검증**
Docker 이미지 빌드는 로컬 데몬이 꺼져 있어 확인하지 못했다. Task 3의 PR CI에서 `docker` job이 안 돌기 때문에(push 전용), `dev` 머지 후에야 실증된다. Dockerfile이 깨졌다면 그때 드러난다.
