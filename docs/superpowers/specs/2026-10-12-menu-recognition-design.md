# 메뉴판 사진 인식 (`POST /internal/v2/ai/menu-recognition`) 설계

## Context

BE가 v2 기능으로 "메뉴판 업로드"(점주가 메뉴판 사진 1~10장을 올리면 AI가 메뉴명·카테고리·
가격을 추출해 후보로 보여주고, 점주가 검토·수정 후 확정 저장하는 흐름)를 개발 중이다.
처음 브레인스토밍할 때는 노션 테크스펙과 당시 로컬 `docs/api정의서.md`/`docs/ERD정의서.md`
기준으로 "이미지 1장, 동기 호출" 계약을 전제했는데, 이후 두 문서가 **노션 원본으로
전면 재동기화**되면서(PR #146, 2026-10-12 병합) 계약이 "배치(최대 10장) 단위, 비동기
업로드"로 바뀌었다. 또한 비전 모델 선택을 두고 "범용 멀티모달 LLM(옵션 1)" vs "전문
OCR(옵션 2)"을 논의했는데, **최종 구현은 옵션 2(OCR)로 간다**. 다만 그 선택을 뒷받침할
근거로, 옵션 1로 했을 때 실제 환각·정확도가 얼마나 나는지 실측 비교가 필요하다. 이 문서는
그 두 가지(최신 계약 + OCR 중심 설계 + 비교 실험 계획)를 반영해 다시 쓴 설계다.

화면·업로드·배치 상태 관리·점주 확인·확정 저장은 전부 BE/FE가 담당하고
(`docs/api정의서.md` "STORE · 메뉴 보기·사진 인식 (ST) [V2, MY-04-01/02]" 섹션,
`docs/ERD정의서.md` `menu_upload_batches`/`menu_images`/`menu_image_items`), AI 서버가
담당할 부분은 **BE가 배치 단위로 1회 호출하는 내부 엔드포인트 하나**로 좁혀진다:
`POST /internal/v2/ai/menu-recognition`. 이 스펙은 그 엔드포인트의 AI 쪽 구현만 다룬다.

## 갱신 (2026-10-12, Upstage 문서 조사 반영) — 아래 "설계" 절보다 우선

> 이슈 #147 구현 착수 전 Upstage 공식 문서를 확인한 결과다. 아래 "설계 — OCR 중심"의 1·2·3절과 "평가" 절 중 이 절과 충돌하는 부분은 이 절이 우선한다. 로컬 비전 LLM·오픈소스 OCR 대안은 검토했으나 이번 PR 은 Upstage 로 가고, 공급자 경계를 `extract_items()` 하나로 좁혀 둔다.

기존 `docs/superpowers/specs/2026-10-12-menu-recognition-design.md` 대비 바뀌는 부분만 적는다.

### 변경 요약

| 절 | 기존 | 갱신 |
|---|---|---|
| OCR 제품 | Document Parse 또는 Information Extract 미정 | **Information Extract** (`POST https://api.upstage.ai/v1/information-extraction`, 모델 별칭 `information-extract`) |
| 이름-가격 짝짓기 | 좌표 기반 직접 구현 가능성 | 불필요. `response_format.json_schema` 로 `{name, price, category}` 배열을 직접 받는다 |
| 카테고리 | 텍스트 LLM 2단계 (`llm.complete`) | 스키마 `category` enum(6종)으로 같은 호출에서 분류. 품질이 나쁘면 그때 2단계로 올린다 |
| confidence | OCR 신뢰도 0~1 | `extra_body={"confidence": true}` 로 필드별 `high`/`low` 라벨만 온다 → 임시 매핑 `high=0.9`, `low=0.5` |
| 병렬 | `asyncio.gather` | 별칭 한도가 동기 1건/초(웹 확인, 제한 페이지는 미확인) → 세마포어 1~2, 429 는 재시도 1회 |
| 이미지 전달 | URL 그대로 | Upstage 가 원격 URL 을 직접 가져오는지 문서에 없음 → AI 가 `httpx` 로 받아 base64 data URL 로 전달 |
| 비교 실험 | 같은 PR | 이번 PR 범위 밖(별도 이슈) |

### 경계 (교체 가능성)

`app/clients/ocr.py::extract_items(image_bytes) -> list[RawItem]` 하나만 공급자를 안다.
`RawItem = {name, price, category, confidence_label}`. 로컬 비전 LLM 으로 바꾸려면 이 함수 안쪽만 교체한다.

### 처리 흐름 (`app/services/menu.py::recognize`)

1. 이미지마다 `httpx` 로 다운로드(타임아웃, 실패 시 해당 이미지는 실패 처리) → `extract_items`
2. 보정: 이름 공백이면 제외 / 가격 음수·1,000,000 초과면 `None` + `priceReviewRequired=true` /
   category 가 6종 밖이면 `OTHER` / 라벨 `low` 이거나 가격 `None` 이면 `priceReviewRequired=true`
3. 항목에 `sourceImageId` 를 붙여 평평하게 합친다 (이미지 간 병합은 BE)
4. 전체 항목 0개 → `ApiError(422, "MENU_TEXT_NOT_FOUND")`. 공급자 오류·다운로드 실패 등 → 500.
   일부 이미지만 실패하면 나머지 항목으로 200 (BE 확인 대기)

### 라우터·스키마

- `app/api/menu.py`: prefix `/internal/v2/ai`, `verify_internal_token`
- `app/schemas/menu.py`: `MenuImageInput`, `MenuRecognitionRequest(images 1~10)`, `DetectedMenuItem`,
  `MenuRecognitionResponse`. 응답에 `message` 를 넣을지는 BE 확인 대기(ST-04 예시에는 있음)

### BE 에 확인할 것

1. 200 응답 `message` 를 AI 가 줘야 하는가 (ST-04 예시에 있음)
2. 422/500 바디: 계약 `{"failReason":...,"data":null}` vs 이 레포 `error.code` 형식
3. 일부 이미지만 실패 시 200 + 나머지 항목이 맞는가
4. BE → AI 호출 타임아웃 (이미지 10장 순차 처리 시 수십 초 가능)
5. `LOW_IMAGE_QUALITY` 판정 기준 (모델 출력만으로는 구분 근거가 없음)

### 테스트 (Upstage·다운로드는 mock)

정상 200 / 이미지 0장·11장 422 / 이름 공백 제외 / 가격 범위 밖 보정 / 카테고리 밖 값 → OTHER /
low 라벨 → priceReviewRequired / 전부 빈 결과 → 422 MENU_TEXT_NOT_FOUND / 공급자 예외 → 500 /
일부 실패 시 나머지 반환. 실호출은 요금 발생이라 승인 후 소량.

## 범위

- **포함**: 배치(이미지 1~10장, 각각 URL)를 받아 이미지별 메뉴 후보(이름·카테고리·가격·
  신뢰도·가격 재확인 필요 여부)를 추출해 반환하는 로직. OCR 기반으로 구현한다.
- **포함(별도 트랙)**: 옵션 1(범용 비전 LLM)과 옵션 2(OCR) 의 환각률·정확도 비교 실험 —
  프로덕션 코드가 아니라 `devtools/` 아래 1회성 평가 스크립트.
- **제외** (BE/FE 담당, 계약 변경 대상 아님): 이미지 업로드·저장, 배치 상태(`PENDING` →
  `PROCESSING` → `COMPLETED`/`FAILED`) 관리, 이미지 간 **동일 후보 병합**(BE가 처리 —
  "BE는 원본 결과를 이미지별로 보관하고 동일 메뉴명·가격·카테고리 후보를 합친 뒤
  `menu_image_items`에 저장"), 점주 검토·수정 화면, 확정 시 `menus` 트랜잭션 저장.

## 요청/응답 계약 (이미 확정 — `docs/api정의서.md` 1604번째 줄)

```
요청: {storeId, batchId, images:[{imageId, imageUrl, order}]}  (최대 10장, imageUrl은 단기 서명 URL)
200: {"data":{"detectedItems":[
  {"sourceImageId":52,"name":"아메리카노","price":4000,"category":"COFFEE",
   "confidence":0.98,"priceReviewRequired":false}
]}}
422: {"failReason":"LOW_IMAGE_QUALITY"|"MENU_TEXT_NOT_FOUND","data":null}
500: {"data":null}  (AI 처리 실패 — BE가 배치 failReason을 AI_PROCESSING_ERROR로 기록)
```

카테고리는 공통 코드로 확정돼 있다: `COFFEE`(커피), `NON_COFFEE`(논커피), `BEVERAGE`(음료),
`CAKE`(케이크), `BAKERY`(베이커리), `OTHER`(기타). 매장별 POS 매출 카테고리(엑셀의
`esp`/`non`/`teabag` 등, 소상공인마다 다름)와는 무관하다 — 이 엔드포인트 요청에 POS
데이터가 들어오지 않아 맞출 방법도 없고, 점주가 화면에서 바로 수정하는 "후보"라 완벽히
맞을 필요도 없다.

`priceReviewRequired`는 ERD `menu_image_items.price_review_required` 설명("낮은 신뢰도·
이상 가격의 행 강조")에 대응하는 **AI가 계산해서 돌려주는 값**이다.

## 설계 — OCR 중심 (최종 구현 방향)

글자를 읽는 작업(OCR)과 메뉴 정보를 해석하는 작업(카테고리 분류)을 분리한다. OCR은
이미지를 보고 "무슨 글자가 어디 있는지"를 정확히 읽는 데 강하고, 범용 비전 LLM처럼
"그럴듯하지만 틀린 값"을 만들어내는(환각) 위험이 적다. 반대로 카테고리 분류("아메리카노는
COFFEE다")는 텍스트만으로 충분한 판단이라 비전이 필요 없다 — 그래서 이 부분은 **이미지가
아니라 텍스트**를 다루는 기존 LLM 경로로 뺀다.

### 1. OCR 클라이언트 (`app/clients/ocr.py`, 신규)

Upstage의 문서 인식 제품(Document Parse / Information Extraction — **구현 시 Upstage
공식 문서로 정확한 엔드포인트와 응답 스키마를 재확인해야 한다**, 지금은 어떤 상품을
쓸지만 정했고 세부 API 형태는 미확인)을 호출해, 이미지에서 텍스트 블록과 가능하면
레이아웃(이름-가격 근접 관계)을 추출한다. `app/clients/llm.py`의 provider들과 달리 chat
completion이 아닌 **일반 REST 엔드포인트**이므로, `app/clients/backend.py`가 쓰는 패턴
(HTTP 클라이언트 + `tenacity` 재시도)을 그대로 따른다 — `app/clients/llm.py`의 SDK 기반
패턴이 아니다.

- 함수: `extract_text_blocks(image_url: str) -> list[OcrBlock]` — 이름 후보가 될 텍스트와
  가격으로 보이는 숫자 패턴(원화 표기)을 1차로 추려낸다. 이름-가격 짝짓기 로직(같은
  줄/근접 좌표를 하나의 메뉴 항목으로 묶기)이 필요한데, Upstage 쪽 응답이 이미 구조화된
  key-value를 주는지(Information Extraction 커스텀 스키마 사용 시) 아니면 레이아웃 좌표만
  주는지(Document Parse)에 따라 이 로직의 필요 여부·복잡도가 달라진다. **구현 착수 시
  가장 먼저 확인해야 할 지점.**
- 설정: 기존 `settings.upstage_api_key`(이미 `app/clients/llm.py`에서 사용 중)를 재사용.
  새 VISION_PROVIDER류 설정은 필요 없다 — OCR은 공급자 전환 대상이 아니라 고정이다.

### 2. 카테고리 분류 — 기존 텍스트 LLM 경로 재사용

OCR이 뽑아낸 메뉴명 리스트를 `app/clients/llm.py::complete(system, user)`(기존 텍스트
전용 함수, 수정 없음)에 그대로 넘겨 6종 카테고리로 분류한다. 비전이 필요 없으므로
`settings.llm_provider`(로컬 Qwen3-32B 전환 대상)를 그대로 써도 무방하다 — **별도
VISION_PROVIDER 설정이 필요 없어진 것**이 옵션 1 대비 이 설계의 가장 큰 단순화다.

- 한 번의 호출에 그 배치·이미지에서 뽑힌 메뉴명 전체를 묶어서 보낸다(메뉴 1개당 호출 1회가
  아니라 — 불필요한 호출 수 증가 방지).
- 업종이 애매하면(식당·주점 메뉴 등) `OTHER`.

### 3. 배치 내 이미지 처리 방식 — 이미지 1장당 OCR 1회

BE가 동일 메뉴명·가격·카테고리 후보를 **이미지 간**에 합치는 걸 명시적으로 맡았으므로
(위 "범위" 참고), AI는 이미지를 섞어서 한 번에 처리할 필요가 없다. 배치의 각 이미지를
독립적으로 `extract_text_blocks()` 호출 1회씩 처리하고, 결과에 `sourceImageId`를 붙여
평평한 리스트로 합쳐 반환한다. 카테고리 분류(2번)는 이미지별로 나눌 필요 없이 배치 전체
메뉴명을 모아 한 번에 호출해도 된다(순서만 유지).

- 이미지 10장이면 OCR 호출 최대 10회 — **동시 처리로 설계**(`asyncio.gather`).
- **부분 실패 처리** (계약에 명시 안 됨 — 가정): 이미지 중 일부만 `LOW_IMAGE_QUALITY`/
  `MENU_TEXT_NOT_FOUND`이어도 나머지 이미지에서 추출된 항목이 있으면 `200`으로 그 항목들만
  반환한다. **배치 전체의 모든 이미지**가 실패한 경우에만 `422`. 이 가정은 계약에 명시돼
  있지 않으므로 구현 전 BE와 확인 필요.

### 4. 스키마 (`app/schemas/menu.py`, 신규)

기존 `Contract` 베이스(camelCase, `extra="ignore"`) 패턴을 따른다.

- `MenuImageInput`: `imageId`, `imageUrl`, `order`
- `MenuRecognitionRequest`: `storeId`, `batchId`, `images: list[MenuImageInput]` (1~10개)
- `DetectedMenuItem`: `sourceImageId`, `name`(str, 공백 불가, ≤100자), `category`(6종 enum),
  `price`(int, 0~1,000,000 또는 `None`), `confidence`(float, 0~1), `priceReviewRequired`(bool)
- `MenuRecognitionData`: `detectedItems: list[DetectedMenuItem]`
- `MenuRecognitionResponse`

가격 상한 1,000,000은 `docs/api정의서.md` "공통 코드·검증"의 FE 입력 검증 규칙
("1,000,000 초과"는 422)에서 가져왔다 — AI 응답에도 같은 상식적 상한을 적용해 과도한
값을 걸러낸다.

### 5. 서비스 (`app/services/menu.py`, 신규)

`recognize_menu(req: MenuRecognitionRequest) -> MenuRecognitionData`

1. `req.images`를 동시에 OCR 처리: 이미지마다 `ocr.extract_text_blocks(image.imageUrl)`.
2. 이름-가격 짝짓기 결과를 `DetectedMenuItem` 초안으로 변환 (`category`는 아직 비움).
3. 모든 이미지의 메뉴명을 모아 `llm.complete()`로 카테고리 일괄 분류 → 각 item에 매핑.
4. 검증:
   - 이름 공백/누락 → 해당 item 제외.
   - `price`가 음수거나 1,000,000 초과 → `None`으로 보정 + `priceReviewRequired=true`.
   - `category`가 6종에 없음/분류 실패 → `OTHER`로 보정.
   - `confidence`는 OCR 자체 추출 신뢰도(필드 존재 시) 기준으로 계산하고, `price is None`
     이거나 이름-가격 짝짓기가 모호했으면 감점 → 임계값 미만이면 `priceReviewRequired=true`.
     **정확한 임계값은 실측 전 임시값** — devtools 측정 후 조정.
5. 이미지 하나가 완전히 실패하면(텍스트 없음/품질 문제) 그 이미지는 `fail_reason` 기록,
   items=[]. 모든 이미지가 실패하면 `ApiError(422, ...)`. 하나라도 성공하면 `200`.
6. OCR/분류 호출 자체가 예외를 던지면(타임아웃 등) 기존 `solutions.py`/`insights.py`가
   `ApiError`를 최종 500 응답으로 매핑하는 방식을 그대로 따른다(구현 시 라우터 예외 처리
   패턴 확인).

### 6. 라우터

신규 `app/api/menu.py` — 기존 라우터들과 동일하게 prefix `/internal/v1/ai`가 아니라
**`/internal/v2/ai`** (계약이 v2로 명시돼 있음), `Depends(verify_internal_token)` 재사용.

## 평가 — 옵션 1(비전 LLM) vs 옵션 2(OCR) 비교 실험

**목적**: 최종 구현은 OCR로 가지만, 그 선택의 근거로 범용 비전 LLM(옵션 1) 대비 실제
환각·정확도 차이를 수치로 확인해둔다.

- `devtools/menu_recognition_compare.py` (신규, 1회성 평가 스크립트 — 프로덕션 코드 아님):
  - **옵션 1 경로**: 이 스크립트 안에서만 쓰는 ad hoc 호출 — Claude/GPT-4o 같은 비전
    모델에 이미지+프롬프트를 직접 호출(이미지, "메뉴명·가격·카테고리를 JSON으로 추출").
    `app/clients/llm.py`에 영구 기능으로 추가하지 않는다 — 채택 안 된 방향이라 프로덕션
    코드에 추상화를 남기지 않는다(YAGNI).
  - **옵션 2 경로**: 실제 구현한 `app/services/menu.py::recognize_menu()`를 그대로 호출.
  - 실제 메뉴판 사진 20~30장(선명/흐림/여러 열)에 사람이 직접 정답(메뉴명·가격)을 매겨두고,
    두 경로의 출력을 정답과 대조해 **환각률**(이미지에 없는 값을 만들어낸 비율)과
    **정확도**(이름·가격 일치율)를 각각 계산해 표로 출력한다.
  - 이 결과는 OCR 파이프라인의 `confidence`/`priceReviewRequired` 임계값을 정하는 데도
    같이 쓴다.

## 검증 (구현 후)

1. `ai-endpoint` 스킬 절차대로: schema → 실패 테스트 → service → router → curl 검증.
2. 위 비교 실험으로 OCR 임계값 확정.
3. `uv run pytest`, `uv run ruff check --fix . && uv run ruff format .` 통과.

## 미확정 — 구현 전 다시 확인 필요

- **Upstage OCR 제품의 정확한 엔드포인트·요청/응답 스키마** — 구현 착수 시 가장 먼저
  Upstage 공식 문서로 확인. 이름-가격 짝짓기를 OCR 응답이 얼마나 대신해주는지가 서비스
  로직 복잡도를 크게 좌우한다.
- **배치 부분 실패 처리** (위 "3. 배치 내 이미지 처리 방식"의 가정) — BE와 확인.
- `confidence`/`priceReviewRequired` 임계값의 정확한 수치 (비교 실험 후 확정).
- provider 예외 → 500 매핑이 기존 라우터들과 정확히 같은 방식인지 구현 시 재확인.
