# 작업 상태

마지막 갱신: 2026-10-15
브랜치: `feat/164-solution-vague-period` (Issue #164, 제나)

## 지금 어디

점주 신고(솔루션 카드가 "현재 기간 순매출이 124,946,029원이며"처럼 기준 없이 기간을
말함)를 고쳤다. 원인은 `app/prompts/solution.py` SYSTEM 프롬프트 자신이 "현재 기간의
사실만 쓰세요"라고 지시해 모델이 그 문구를 그대로 받아쓴 것이었다.

고치면서 전제가 한 번 틀렸었다 — `targetDate`를 그 자리에 쓰면 된다고 1차로 고쳤는데,
BE 확인 결과 `salesSummary.netSales`는 `targetDate` 하루치가 아니라 **분석 기간
(salesAnalysisId 가 집계한 기간) 합계**였다. targetDate 를 썼으면 기간 합계를 "오늘
하루 매출"처럼 더 구체적으로 틀리게 말할 뻔했다 — 되돌렸다.

반영한 것:
- SYSTEM 지시를 "기간을 특정하는 말(현재/이번/해당/지금 기간) 금지"로 교정 +
  재시도 검출 규칙 `_VAGUE_PERIOD`(`app/services/solution.py`, `devtools/grade.py` 양쪽).
- 집계 기간을 받을 필드가 계약에 없어서, BE 최종 확정 전까지 AI 쪽에서 임시로
  `metrics.salesSummary.period`(문자열, 예: `"2026-01-01~2026-03-31"`, 선택값)를 정해
  `app/schemas/common.py`에 추가했다. 값이 오면 프롬프트가 그 기간을 명시하고, 없으면
  여전히 기간 언급을 피한다.
- 프롬프트 `VERSION`을 `2026-10-14` → `2026-10-15`로 올림(`devtools/grade.py`의
  `TARGET_SOLUTION_VERSION`도 같이).

## 마지막으로 통과한 것

- `uv run pytest` — 332 passed
- `uv run ruff check --fix . && uv run ruff format .` — 통과(수정 없음)

## 다음 한 걸음

사용자 승인 받으면 커밋 → PR(`Closes #164`, base `dev`). 커밋 전에 브랜치에 같이 묻어
있는 무관한 untracked 파일(`KTB4-AI.code-workspace`, `devtools/concurrency_bench.py`,
`docs/` 밑 샘플 엑셀·이미지·PDF)이 스테이징에 끼지 않게 확인할 것 — 이번 작업과 무관하다.

## 미해결 결정

- `metrics.salesSummary.period` 는 AI 가 임시로 정한 이름·모양이다. BE 와 최종 필드명을
  맞춰야 한다 — 확정되면 이름이 바뀔 수 있다.
- 챗봇 `ChatContextCard`에도 같은 집계 기간을 전달할지는 BE 와 별도로 논의 중(targetDate
  추가 여부보다 먼저 집계 기간 공유 방식을 맞추기로 함).

## 함정

- 노션 API 정의서의 `targetDate` 필드 설명("오늘 날짜")과 GitHub 위키의 "salesSummary 는
  기준일 하루"라는 서술을 그대로 믿으면 안 된다 — 실제 BE 집계 로직과 달랐다(이번에 직접
  걸렸다). 계약 문서의 서술과 실제 BE 동작이 어긋날 수 있으니, 금액 규모가 이상하면
  문서보다 BE 확인을 먼저 받는다.
- `dataBasisPeriod` 라는 필드가 과거(2026-09-16 이전) 요청의 `context`에 있었다가
  삭제된 적이 있다 — 지금의 `salesSummary.period`와는 다른 자리(요청 최상위 vs
  salesSummary 내부)이니 혼동하지 않는다.
- `docs/api정의서.md`·`docs/ERD정의서.md` 로컬 사본은 삭제됐다(2026-10-13). 계약 확인은
  `notion-contract` 스킬로 노션 원본을 본다 — 단, Notion MCP 가 서브에이전트(`doc-digger`)
  에는 연결돼 있지 않을 수 있다. 그 경우 메인 세션에서 `notion-search`/`notion-fetch`를
  직접 쓴다(페이지 전체를 `notion-fetch`로 당기면 토큰 초과 — `notion-search`로 좁혀서
  조회한다).
