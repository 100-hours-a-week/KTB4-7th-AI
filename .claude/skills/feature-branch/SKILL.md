---
name: feature-branch
description: 브랜치·PR을 다루기 전에 따르는 절차. 브랜치 생성/삭제, PR 생성/머지는 전부 사용자
  확인 후에만 실행한다. git checkout -b, git branch -d, gh pr create 를 치기 전에 이 스킬부터 확인한다.
---

# 브랜치·PR 절차

## 최우선 규칙 — 항상 먼저 물어본다

**브랜치 생성·삭제·리네임, PR 생성·머지는 사용자 확인 없이 실행하지 않는다**
(2026-09-17 결정). 작은 수정이라도 "이 정도는 그냥 처리해도 되겠지"라고 판단하지 않는다.

배경: 같은 세션에서 사소한 수정마다 Issue·브랜치·PR을 계속 새로 만들다가(#39/#40, #41,
#42/#43, #44, #45/#46) 불필요한 PR이 난립했다. 사용자가 "더 이상 브랜치 만들기/삭제 하지
말라"고 직접 제지했다. 판단은 사용자 몫이지 내가 알아서 할 일이 아니다.

**적용 방법**: 브랜치를 새로 파거나 지워야 할 것 같으면, 먼저 그 필요성과 이유를 사용자에게
말하고 대답을 기다린다. `AskUserQuestion`으로 물어도 되고, 그냥 텍스트로 제안하고 답을
기다려도 된다. PR도 마찬가지로 `gh pr create`/`gh pr merge` 실행 전에 확인받는다.

## 확인받은 뒤의 절차

### 1. Issue 먼저 — 브랜치보다 먼저

```bash
gh issue list --search "<키워드>" --state all
gh issue create --title "..." --body "..."
```

→ **확인**: 브랜치명에 쓸 이슈 번호를 손에 쥐고 있는가

### 2. 브랜치명은 `feat/<이슈번호>-<kebab-case>`

이슈 번호 없는 브랜치는 이 레포 관례가 아니다(`feat/21-...`, `feat/27-...`, `feat/39-...` 참고).

```bash
git checkout -b feat/<이슈번호>-<kebab-case>
```

### 3. 작업 → 커밋 → 푸시

평소 절차(테스트·린트 통과 확인, 커밋은 사용자 승인 후)를 그대로 따른다.

### 4. PR 본문에 `Closes #<이슈번호>` 필수

빠뜨리면 머지해도 Issue가 자동으로 안 닫힌다.

```bash
gh pr create --base dev --title "..." --body "...

Closes #<이슈번호>"
```

→ **확인**: `gh pr view <번호> --json body` 에 `Closes #`가 실제로 들어갔는가

### 5. 머지 확인 후 브랜치 정리 (이것도 실행 전 확인)

```bash
gh pr view <PR번호> --json state,mergedAt
git branch -d feat/...
git push origin --delete feat/...
```

## 브랜치 리네임 금지 (이미 PR이 열려 있으면)

`gh api repos/.../branches/<name>/rename`로 브랜치를 리네임하면, 이미 그 브랜치를 head로 하는
PR이 **자동으로 닫혀버린다**(GitHub 웹 UI에서 리네임하는 것과 다르게 동작함 — 2026-09-17 실측
확인). 브랜치명을 잘못 지었을 때:

- PR을 아직 안 열었으면: `git branch -m`으로 로컬만 바꾸고 새로 push하면 된다.
- PR이 이미 열려 있으면: **리네임하지 않는다.** 그 이름 그대로 진행하거나, 필요하면 새 브랜치로
  새 PR을 열고 기존 PR엔 대체 사실을 코멘트로 남긴 뒤 닫는다.
