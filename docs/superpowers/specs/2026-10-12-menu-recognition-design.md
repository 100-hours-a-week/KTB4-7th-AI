# 메뉴판 사진 인식 (`POST /internal/v2/ai/menu-recognition`) 설계

## 변경 이력

- 2026-10-12: 초안. 당시 계약(이미지 1장, 동기 호출) 기준으로 "범용 비전 LLM(옵션 1)" 설계.
- 2026-10-12: `docs/api정의서.md`/`docs/ERD정의서.md` 노션 전면 재동기화(PR #146) — 계약이
  "배치 최대 10장, 비동기 업로드"로 바뀜. 최종 구현 방향을 OCR(옵션 2)로 확정하고 설계를
  다시 씀.
- 2026-10-12 밤: Upstage Information Extract 실제 API(스키마 기반 구조화 추출)를 조사.
  이 방향이면 이름-가격 짝짓기·카테고리 분류가 한 번의 호출로 끝남.
- 2026-10-13: **무료로 시작하기 위해 OCR 벤더를 Upstage → 네이버 클로바 OCR로 변경.**
  클로바는 범용 OCR(텍스트+좌표)만 주고 스키마 기반 구조화 추출이 없어, 이름-가격
  짝짓기를 AI가 직접 구현해야 하는 쪽으로 되돌아감. Upstage 조사 내용은 향후 유료 전환
  검토 시 참고용으로 git 히스토리에 남아 있음(이 리비전에서 제거).
- 2026-10-13: 리뷰 반영 — 짝짓기 로직·confidence 분해·동시 호출 제한·부분 실패 계약·
  평가 지표 세분화. 클로바 무료 티어(월 100회)는 **개발·테스트 전용**으로 쓰고 운영 전
  유료로 전환하기로 확정(사용량 보호 로직은 지금 단계에서 불필요).
- 2026-10-13: `docs/api정의서.md` 재동기화 — 업로드가 **비동기 → 동기**로 바뀌었다.
  `POST /v2/menu-images`가 AI 분석 완료까지 같은 HTTP 요청에서 기다려 응답한다(더 이상
  `PENDING` 즉시 응답 + 폴링이 기본 흐름이 아니다 — 폴링용 GET은 화면 재진입·재접속
  전용으로 남음). 부분 실패 계약도 완전히 명시됨: 응답에 `failedImages` 필드가 추가되고,
  200/422/500 분기 규칙이 확정됐다. 아래 "요청/응답 계약"·"6. 배치 처리와 부분 실패"·
  "BE에 확인할 것"을 그 기준으로 갱신했다 — 더는 가정이 아니라 확정 계약이다.

## Context

BE가 v2 기능으로 "메뉴판 업로드"(점주가 메뉴판 사진 1~10장을 올리면 AI가 메뉴명·카테고리·
가격을 추출해 후보로 보여주고, 점주가 검토·수정 후 확정 저장하는 흐름)를 개발 중이다.
화면·업로드·배치 상태 관리·점주 확인·확정 저장은 전부 BE/FE가 담당하고
(`docs/api정의서.md` "STORE · 메뉴 보기·사진 인식 (ST) [V2, MY-04-01/02]" 섹션,
`docs/ERD정의서.md` `menu_upload_batches`/`menu_images`/`menu_image_items`), AI 서버가
담당할 부분은 **BE가 배치 단위로 1회 호출하는 내부 엔드포인트 하나**로 좁혀진다:
`POST /internal/v2/ai/menu-recognition`. 이 스펙은 그 엔드포인트의 AI 쪽 구현만 다룬다.

## 범위

- **포함**: 배치(이미지 1~10장, 각각 URL)를 받아 이미지별 메뉴 후보(이름·카테고리·가격·
  신뢰도·가격 재확인 필요 여부)를 추출해 반환하는 로직. 네이버 클로바 OCR + 기존 텍스트
  LLM(카테고리 분류)으로 구현한다.
- **포함(별도 트랙)**: 범용 비전 LLM(옵션 1)과 OCR(옵션 2)의 환각률·정확도 비교 실험 —
  프로덕션 코드가 아니라 `devtools/` 아래 1회성 평가 스크립트.
- **제외** (BE/FE 담당, 계약 변경 대상 아님): 이미지 업로드·저장, 배치 상태(`PENDING` →
  `PROCESSING` → `COMPLETED`/`FAILED`) 관리, 이미지 간 **동일 후보 병합**(BE가 처리 —
  "BE는 원본 결과를 이미지별로 보관하고 동일 메뉴명·가격·카테고리 후보를 합친 뒤
  `menu_image_items`에 저장"), 점주 검토·수정 화면, 확정 시 `menus` 트랜잭션 저장.

## 요청/응답 계약 (이미 확정 — `docs/api정의서.md` "메뉴 보기·사진 인식" 섹션, 2026-10-13 재동기화 반영)

```
요청: {storeId, batchId, images:[{imageId, imageUrl, order}]}  (1~10장, imageUrl은 단기 서명 URL)

200 (1장 이상 성공): {"message":"메뉴가 인식되었습니다.","data":{
  "detectedItems":[
    {"sourceImageId":52,"name":"아메리카노","price":4000,"category":"COFFEE",
     "confidence":0.98,"priceReviewRequired":false}
  ],
  "failedImages":[
    {"sourceImageId":53,"failReason":"LOW_IMAGE_QUALITY"}
  ]
}}
422 (전부 실패): {"message":"메뉴를 인식하지 못했습니다.","failReason":"LOW_IMAGE_QUALITY"|"MENU_TEXT_NOT_FOUND"|"AI_PROCESSING_ERROR","data":null}
500 (AI 처리 자체가 실패 — 공급자 장애 등): {"message":"메뉴 인식 중 오류가 발생했습니다.","data":null}
```

- `detectedItems`와 `failedImages`는 이미지 ID 기준으로 겹치지 않는다 — 이미지 하나는
  (0개 이상의 `detectedItems`로 기여하는) 성공, 또는 `failedImages`에 사유와 함께 들어가는
  실패, 둘 중 하나다. 후보가 0개인 정상 분석(멀쩡한 사진인데 메뉴가 없음)은 **실패가
  아니다** — 그 이미지는 `failedImages`에 넣지 않는다.
- **업로드가 동기로 바뀌었다** (2026-10-13 재동기화) — `POST /v2/menu-images`가 AI 분석이
  끝날 때까지 같은 HTTP 요청에서 기다렸다가 FE에 최종 상태를 응답한다. 더 이상 `PENDING`
  즉시 응답 + 폴링이 기본 흐름이 아니다(`GET .../menu-image-batches/{batchId}`는 화면
  재진입·재접속 전용으로 남음). 이 말은 **BE→AI 호출 지연이 곧 점주가 체감하는 대기
  시간**이라는 뜻이다 — 아래 "5. 동시 처리와 재시도"의 타임아웃·동시성 설계가 그만큼
  더 중요해졌다.
- `failReason` 3종(`LOW_IMAGE_QUALITY`/`MENU_TEXT_NOT_FOUND`/`AI_PROCESSING_ERROR`)은
  이미지별(`failedImages[].failReason`)과 배치 전체(422 최상위 `failReason`) 양쪽에 다
  쓰인다.
- 카테고리 공통 코드: `COFFEE`(커피), `NON_COFFEE`(논커피), `BEVERAGE`(음료), `CAKE`(케이크),
  `BAKERY`(베이커리), `OTHER`(기타). 매장별 POS 매출 카테고리(엑셀의 `esp`/`non`/`teabag`
  등)와는 무관 — 이 요청에 POS 데이터가 안 들어오고, 점주가 화면에서 바로 수정하는
  "후보"라 완벽히 맞을 필요도 없다.
- `priceReviewRequired`는 ERD `menu_image_items.price_review_required`("낮은 신뢰도·이상
  가격의 행 강조")에 대응하는 **AI가 계산해서 돌려주는 값**이다.

## 설계 — OCR 중심

글자를 읽는 작업(OCR)과 메뉴 정보를 해석하는 작업(카테고리 분류)을 분리한다. OCR은
"무슨 글자가 어디 있는지"를 정확히 읽는 데 강하고 범용 비전 LLM보다 환각 위험이 적다.
카테고리 분류는 텍스트만으로 충분한 판단이라 비전이 필요 없어 기존 텍스트 LLM 경로로 뺀다.

### 1. OCR 클라이언트 (`app/clients/ocr.py`, 신규)

네이버 클로바 OCR(Invoke URL + `X-OCR-SECRET` 헤더)을 호출해 이미지에서 텍스트와 좌표
(bounding box), 텍스트별 인식 신뢰도를 받는다. chat completion이 아닌 **일반 REST
엔드포인트**라 `app/clients/llm.py`의 SDK 패턴이 아니라 `app/clients/backend.py`의 패턴
(HTTP 클라이언트 + 제한적 재시도)을 따른다.

- 함수: `extract_text_blocks(image_url: str) -> list[OcrBlock]` (`OcrBlock = {text, confidence, bbox}`).
- **이미지 전달**: 클로바 OCR 공식 요청 형식에 이미지 URL을 바로 담는 필드가 있다 — 다운로드·
  base64 인코딩 없이 BE가 준 서명 URL을 그대로 전달한다(원래 설계 의도 유지). 다만 ①
  서명 URL의 유효기간이 클로바가 fetch하는 시점까지 충분한지, ② 네이버클라우드 쪽에서
  BE의 비공개 스토리지 도메인에 네트워크 접근이 가능한지는 **구현 시 실제 호출로 확인**
  해야 한다. 안 되면 AI가 다운로드해서 base64로 전달하는 방식으로 대체.
- 설정: 신규 `CLOVA_OCR_SECRET_KEY` / `CLOVA_OCR_INVOKE_URL` (`app/core/config.py`).
- **무료 티어(월 100회) 는 개발·테스트 전용이다.** 이미지 1장 = 1회 호출이면 배치 1건
  (10장)만 올려도 한도의 10%를 쓴다. 운영 전 유료 플랜으로 전환하기로 확정했으므로,
  지금 단계에서 호출량 보호 로직(circuit breaker 등)은 만들지 않는다 — 다만 실제 실호출
  테스트(devtools 등)는 이 한도를 의식해서 적게, 신중히 돌린다.

### 2. 메뉴명-가격 짝짓기 — 가장 큰 기술적 위험

클로바 OCR은 좌표만 주고 "이게 메뉴명, 이게 가격"은 알려주지 않는다. 메뉴판은 여러 열,
줄바꿈, 옵션 가격, 취소선 가격 등으로 레이아웃이 다양해서, 단순히 "가까운 텍스트끼리
묶기"는 서로 다른 메뉴의 가격이 뒤바뀌는 사고로 이어질 수 있다(위 예시: "아메리카노 /
카페라떼"와 "3,000원 / 4,000원"이 두 줄로 나뉜 메뉴판에서 열을 잘못 맞추면 가격이
바뀐다).

- **처음부터 모든 레이아웃을 완벽히 지원하려 하지 않는다.** 좌표 기반 행·열 그룹화
  규칙(같은 행 또는 같은 열 범위 내 최근접 숫자 패턴을 가격으로 묶기)만 먼저 구현한다.
- 묶기가 모호한 경우(후보가 여러 개, 거리가 애매함, 열이 안 맞음 등) → 그 메뉴 항목은
  `priceReviewRequired=true`로 표시한다(추측해서 확정하지 않는다).
- **전용 테스트 필요**: 2열 이상 메뉴판에서 가격이 서로 바뀌어 묶이는 사례를 별도 테스트
  케이스로 만든다(일반 단일 열 메뉴판 테스트와 분리).

### 3. 신뢰도 계산 — 세 가지를 구분한다

OCR이 글자 하나를 정확히 읽었다는 것과, 그 글자가 올바른 메뉴에 연결됐다는 것은 별개
문제다. 외부 응답 스키마는 `confidence`(float) 하나뿐이라 바꿀 수 없지만, 내부적으로는
분리해서 계산하고 마지막에 합친다.

- `ocr_confidence`: 클로바가 주는 텍스트별 인식 신뢰도(0~1).
- `pairing_ambiguous`: 위 2번의 묶기 로직이 애매하다고 판단했는지(bool).
- 최종 `confidence` = `ocr_confidence`에 `pairing_ambiguous`면 감점(예: ×0.6 — 실측 전
  임시값). **이 점수는 실제 확률이 아니라 검토 우선순위를 매기기 위한 휴리스틱**이라는
  점을 코드 주석/문서에 명시한다 — BE·FE가 이 숫자를 정확도로 오해하지 않도록.
- `priceReviewRequired = true` 조건: `price is None` OR `pairing_ambiguous` OR 가격이
  0~1,000,000 범위 밖이었음(보정 전) OR `confidence` < 임계값(실측 후 확정).

### 4. 카테고리 분류 — 기존 텍스트 LLM 경로 재사용

OCR·짝짓기 결과로 얻은 메뉴명 리스트를 `app/clients/llm.py::complete(system, user)`(기존
텍스트 전용 함수, 수정 없음)에 한 번에 묶어 보내 6종 카테고리로 분류한다. 비전이
필요 없으므로 `settings.llm_provider`(로컬 Qwen3-32B 전환 대상)를 그대로 써도 무방하다 —
별도 VISION_PROVIDER 설정이 필요 없다는 게 이 설계의 핵심 단순화다. 업종이 애매하면
(식당·주점 메뉴 등) `OTHER`.

### 5. 동시 처리와 재시도

배치의 이미지마다 OCR 호출이 1회 필요하지만, `asyncio.gather`로 10개를 무제한 동시
호출하지 않는다 — 공급자 호출 한도·일시적 오류·429에 취약하다. 업로드가 동기로 바뀌면서
(위 "요청/응답 계약" 참고) 이 지연이 곧 점주의 대기 시간이 되므로, 동시성과 전체 지연의
균형이 전보다 훨씬 중요하다.

- `asyncio.Semaphore(2)`로 시작(실측 후 조정) — 동시 처리 수를 제한한다.
- 호출마다 개별 timeout을 둔다.
- 재시도는 **429·5xx(일시적 오류)에만** 제한적으로 적용(최대 1회) — 인증 실패 같은 영구
  오류까지 반복하지 않는다. `app/clients/backend.py`의 `tenacity` 패턴을 참고.
- 이미지 10장 × 세마포어 2 × (OCR 지연 + 재시도 가능성)이 BE→AI 타임아웃(아래 "BE에
  확인할 것") 안에 들어오는지 실측으로 확인해야 한다 — 못 맞추면 세마포어를 올리거나
  BE와 타임아웃 값을 다시 협의한다.

### 6. 배치 처리와 부분 실패

BE가 동일 메뉴명·가격·카테고리 후보를 **이미지 간**에 합치는 걸 명시적으로 맡았으므로
(위 "범위" 참고), AI는 이미지를 섞어서 한 번에 처리하지 않는다. 배치의 각 이미지를
독립적으로 OCR 처리하고, 결과에 `sourceImageId`를 붙여 평평한 리스트로 합쳐 반환한다.
카테고리 분류(4번)는 배치 전체 메뉴명을 모아 한 번에 호출해도 된다.

**이제 계약으로 확정됐다** (2026-10-13 재동기화) — 더 이상 가정이 아니다:

- 이미지 **한 장이라도** 처리에 성공하면(0개 이상의 `detectedItems`를 냈으면) `200`을
  반환하고, 성공한 이미지의 항목은 `detectedItems`, 실패한 이미지는
  `failedImages:[{sourceImageId, failReason}]`에 담아 **같이** 돌려준다.
- **배치 전체의 모든 이미지**가 실패한 경우에만 `422` + 최상위 `failReason`.
- AI 처리 자체(공급자 전체 장애 등)가 실패하면 `500`.

**시스템 장애와 콘텐츠 문제를 반드시 구분한다**: OCR 공급자가 타임아웃·5xx로 응답하지
않은 상황을 "메뉴판에 글자가 없다"(`MENU_TEXT_NOT_FOUND`)로 잘못 분류하면 안 된다. 이
구분은 계약에 값으로 못박혀 있지 않고 AI가 내부적으로 판단해야 하는 부분이다 — 이미지별
실패 사유를 정할 때:

- OCR 공급자가 타임아웃·5xx·네트워크 오류를 던지면(그 이미지에 한정된 재시도까지
  실패) → `failedImages`에 `failReason="AI_PROCESSING_ERROR"`로 넣는다(그 이미지만의
  시스템 오류 — 배치 전체를 500으로 떨어뜨리지 않는다. 500은 배치 전체가 처리 불가능할
  때만, 예: OCR 클라이언트 초기화 실패, 모든 이미지가 동시에 공급자 장애).
- OCR은 성공했지만 결과가 흐려서 신뢰할 수 없는 수준 → `LOW_IMAGE_QUALITY`.
- OCR은 성공했고 글자도 읽었는데 메뉴판처럼 보이지 않음(텍스트가 없거나 무관한 사진) →
  `MENU_TEXT_NOT_FOUND`.
- 배치 전체가 실패(422)일 때의 최상위 `failReason`은 이미지별 실패 사유의 다수결로
  정한다(동률이면 `LOW_IMAGE_QUALITY` 우선 — 임시 규칙, 실측 후 조정 가능).

### 7. 스키마 (`app/schemas/menu.py`, 신규)

기존 `Contract` 베이스(camelCase, `extra="ignore"`) 패턴을 따른다.

- `MenuImageInput`: `imageId`, `imageUrl`, `order`
- `MenuRecognitionRequest`: `storeId`, `batchId`, `images: list[MenuImageInput]` (1~10개)
- `DetectedMenuItem`: `sourceImageId`, `name`(str, 공백 불가, ≤100자), `category`(6종 enum),
  `price`(int, 0~1,000,000 또는 `None`), `confidence`(float, 0~1), `priceReviewRequired`(bool)
- `FailedImage`: `sourceImageId`, `failReason`(`LOW_IMAGE_QUALITY`|`MENU_TEXT_NOT_FOUND`|
  `AI_PROCESSING_ERROR`)
- `MenuRecognitionData`: `detectedItems: list[DetectedMenuItem]`, `failedImages: list[FailedImage]`
- `MenuRecognitionResponse` — 다른 엔드포인트들과 동일하게 `message` 필드 포함(성공/실패
  공통 래퍼, `ai-endpoint` 스킬 "자주 틀리는 것" 참고 — 플랫 응답으로 만들지 않는다)

가격 상한 1,000,000은 `docs/api정의서.md` "공통 코드·검증"의 FE 입력 검증 규칙에서
가져왔다.

### 8. 서비스 처리 흐름 (`app/services/menu.py`, 신규)

`recognize_menu(req: MenuRecognitionRequest) -> MenuRecognitionData`

1. `req.images`를 세마포어로 동시성 제한하며 OCR 처리(5번).
2. 이미지별로 좌표 기반 짝짓기(2번) → 초안 item 리스트 + `ocr_confidence`/
   `pairing_ambiguous`.
3. 배치 전체 메뉴명을 모아 카테고리 분류(4번) → 각 item에 매핑(실패 시 `OTHER`).
4. 검증·보정: 이름 공백/누락 제외, 가격 범위 밖 보정 + `priceReviewRequired`, 최종
   `confidence` 계산(3번).
5. 이미지별 실패를 콘텐츠 문제/시스템 오류로 구분해 `failedImages`로 집계(6번) → 한 장이라도
   성공했으면 `200`(`detectedItems` + `failedImages`), 전부 실패면 `422`(최상위
   `failReason`), 배치 전체가 처리 불가능했으면 `500`.

### 9. 라우터

신규 `app/api/menu.py` — prefix `/internal/v2/ai`(계약이 v2로 명시돼 있음),
`Depends(verify_internal_token)` 재사용.

## 평가 — 범용 비전 LLM(옵션 1) vs OCR(옵션 2) 비교 실험

**목적**: 최종 구현은 OCR로 가지만, 그 선택의 근거를 수치로 남긴다. `devtools/
menu_recognition_compare.py`(신규, 1회성 평가 스크립트 — 프로덕션 코드 아님). 옵션 1은
스크립트 안에서만 쓰는 ad hoc 비전 모델 호출(Claude/GPT-4o 등)이고, `app/clients/llm.py`
에 영구 기능으로 추가하지 않는다(YAGNI — 채택 안 된 방향).

실제 메뉴판 사진 20~30장에 사람이 정답(메뉴명·가격·카테고리)을 매겨두고, 전체 정확도
하나가 아니라 아래 항목을 **독립적으로** 측정한다 — 특히 "이름-가격 연결 정확도"는
이름·가격을 각각 정확히 읽어도 서로 잘못 묶이면 실패로 잡아내야 하므로 별도 지표로 둔다.

| 항목 | 확인할 내용 |
|---|---|
| 메뉴명 정확도 | 글자를 정확히 읽었는가 |
| 가격 정확도 | 숫자·원 단위를 정확히 읽었는가 |
| 메뉴-가격 연결 정확도 | 가격이 올바른 메뉴에 연결됐는가 (독립 지표) |
| 카테고리 정확도 | 6종 중 올바르게 분류했는가 |
| 환각률 | 이미지에 없는 메뉴·가격을 만들어냈는가 |
| 검토 필요 판정 품질 | 불확실한 결과를 `priceReviewRequired`로 제대로 표시했는가 |
| 처리 시간·비용 | 이미지 1장/배치 1건당 지연과 비용 |

이 결과로 `confidence`/`priceReviewRequired` 임계값을 확정한다.

## BE에 확인할 것 (구현 전 필수)

2026-10-13 재동기화로 부분 실패 계약(200/422/500 분기, `failedImages` 필드, `message`
필드)은 **해결됨** — 아래만 남는다.

1. 배치 전체가 콘텐츠 문제로 실패했을 때 `LOW_IMAGE_QUALITY` vs `MENU_TEXT_NOT_FOUND`
   판정 기준 — AI 모델 출력만으로는 구분 근거가 약하다(위 "6. 배치 처리와 부분 실패"에
   임시 규칙 적어둠, 실측 후 다시 볼 것).
2. **BE → AI 호출의 타임아웃 설정값** — 업로드가 동기로 바뀌어서(위 "요청/응답 계약"
   참고) 이게 이제 가장 중요하다. 이미지 최대 10장 × 세마포어 2로 처리하면 수십 초
   걸릴 수 있는데, BE의 허용 시간과 안 맞으면 BE 쪽 타임아웃이 먼저 끊어서 우리가 뭘
   반환하든 소용없다.

## 구현 순서

1. 클로바 OCR 공식 API 요청/응답 형식과 계정 사용량 한도를 확인한다.
2. 실제 메뉴판 몇 장으로 텍스트·좌표·신뢰도가 어떤 형태로 오는지 직접 호출해 확인한다
   (무료 한도 의식해서 소량).
3. 좌표 기반 짝짓기 로직과 실패 처리를 구현한다(2번·3번 설계).
4. 기존 텍스트 LLM으로 카테고리 일괄 분류, 스키마·비즈니스 규칙으로 검증한다.
5. 위 "BE에 확인할 것"을 확정하고 통합 테스트한다.
6. `ai-endpoint` 스킬 절차(schema → 실패 테스트 → service → router → curl 검증)로 구현.
7. 비교 실험(20~30장)으로 정확도·임계값을 조정한다.

## 검증

- `uv run pytest`, `uv run ruff check --fix . && uv run ruff format .` 통과.
- 짝짓기 교차 오류(열이 뒤바뀌는 사례) 전용 테스트 포함.
- 실호출(클로바·비교 실험)은 무료 한도·요금이 걸려 있어 소량으로, 승인 후 진행.
