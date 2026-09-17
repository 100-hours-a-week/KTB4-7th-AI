---
name: feature-branch
description: 기능 브랜치를 새로 만들기 전에 따르는 절차. Issue 생성/확인 → feat/<이슈번호>-<kebab-case> 브랜치 → 작업 → PR(Closes #번호) → 머지 확인 후 브랜치 삭제. git checkout -b 를 치기 전에 이 스킬부터 확인한다.
---

# 기능 브랜치 절차

브랜치부터 파고 이슈를 나중에(또는 안) 만드는 실수가 실제로 있었다(2026-09-17,
`feat/forecast-interval-docs-sync` — Issue 없이 브랜치·PR #41부터 만들고 나중에 지적받아
Issue #42 + PR #43으로 다시 만듦). 순서를 바꾸지 않는다.

## 절차

### 1. Issue 먼저 — 브랜치보다 먼저
`git checkout -b` 치기 전에 관련 Issue가 있는지 확인한다. 없으면 만든다.

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

### 5. 머지 확인 후 브랜치 정리

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
