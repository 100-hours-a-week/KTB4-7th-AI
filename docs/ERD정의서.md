## 1. 문서 정보

- ERD: https://www.erdcloud.com/d/YCaxgrtSfbvMcQCHM
- 설계 목적: 매장 단위 매출 업로드, 분석, AI 솔루션, 랭킹, 알림 기능을 지원한다. MVP에서는 업로드·분석·당일 솔루션 생성을 동기 처리하고, 향후 처리 시간과 작업량이 증가하면 큐·워커 기반 비동기 처리로 확장한다.
- 표기: PK는 기본키, FK는 외래키, NULL은 값 생략 가능을 의미한다.

### 테이블 정의 작성 기준

- 각 테이블에 역할, 컬럼명·타입·제약사항, PK/FK 및 연결 관계를 명시한다.
- ID와 참조 키는 `BIGINT UNSIGNED`를 사용한다. 원화 금액은 기본적으로 `BIGINT`를 사용하며, 취소 행처럼 음수값을 보존해야 하는 SALES 원천·집계 금액은 signed 타입을 사용한다. 비율·좌표처럼 소수점이 필요한 값은 `DECIMAL`을 사용한다.
- FK 설명에는 참조 대상과 업무 관계를 함께 기록한다.

## 2. 도메인별 테이블

| 도메인 코드 | 도메인명 | 테이블 |
| --- | --- | --- |
| AUTH | 인증·계정 | users, user_auth_providers, user_sessions, password_reset_tokens |
| STORE | 매장 | stores, store_business_hours, store_holidays, menus, menu_images, menu_image_items |
| SOL | 솔루션 | solution_bundles, solutions, saved_solutions, chat_messages |
| SALES | 매출 분석 | sales_uploads, sales_orders, sales_order_items, store_menu_categories, sales_daily_summaries, sales_hourly_summaries, sales_daily_category_summaries, sales_daily_menu_summaries, sales_forecasts, analysis_runs, sales_analyses, sales_ai_insights, analysis_metrics, menu_analysis_results, review_analyses, store_cost_items, reviews, weather_observations |
| RANK | 성장 랭킹 | ranking_profiles, ranking_snapshots, ranking_entries |
| NOTI | 알림 | notifications, notification_preferences |

## 3. AUTH · 인증/계정

회원가입, 로그인, 로그아웃, 비밀번호 찾기·수정, 세션 관리, 기본 회원 정보 조회 및 회원 탈퇴를 담당한다.

### ✅users - 사용자

로그인 계정과 사용자 상태를 저장한다. 탈퇴는 deleted_at에 시점을 남기는 논리 삭제로 처리한다.

추가 권장: status는 ACTIVE, SUSPENDED, WITHDRAWN 값만 허용한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 사용자 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 사용자 식별자 |
| 이메일 | `email` | NOT NULL, UNIQUE | VARCHAR(100) | 로그인 및 계정 식별용 이메일 |
| 비밀번호 해시 | `password_hash` | NOT NULL | VARCHAR(255) | 암호화된 비밀번호 해시값 |
| 이름 | `name` | NOT NULL | VARCHAR(50) | 사용자 실명 또는 표시 이름 |
| 휴대폰 번호 | `phone` | NOT NULL, UNIQUE | VARCHAR(20) | 사용자 휴대폰 번호 |
| 마지막 로그인 일시 | `last_login_at` | NULL 허용 | DATETIME | 가장 최근 로그인 시각 |
| 탈퇴 일시 | `deleted_at` | NULL 허용 | DATETIME | 회원 탈퇴 처리 시각 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 계정 생성 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 계정 정보 최종 수정 시각 |

### ✅user_auth_providers - 외부 본인인증 식별값 연동

V2에서 도입하는 토스 본인인증 완료 후 제공되는 사용자 고유 식별값을 내부 사용자 계정과 연결한다. V1은 이메일·비밀번호와 세션 기반 인증만 사용하며, 소셜 로그인 OAuth 계정을 저장하는 테이블이 아니다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 인증 계정 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 본인인증 연동 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL | BIGINT UNSIGNED | 연동 대상 사용자 식별자 |
| 인증 제공자 | `provider` | NOT NULL | VARCHAR(20) | 본인인증 제공자명. V2에서 `TOSS`를 사용 |
| 제공자 계정 식별값 | `provider_subject` | NOT NULL, UNIQUE (`provider`, `provider_subject`) | VARCHAR(255) | 제공자가 발급한 사용자 고유 식별값 |
| 연동 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 토스 본인인증 식별값 연동 시각 |

테이블 제약: UNIQUE(provider, provider_subject), UNIQUE(user_id, provider).

**V2 회원가입·로그인 연결 기준:** 토스 인증이 완료되면 `provider='TOSS'`와 `provider_subject`로 기존 연결을 먼저 조회한다. 연결된 사용자가 있으면 세션을 발급해 로그인하고, 없으면 약관 동의와 사업자·매장 정보 등록을 완료한 뒤 `users`·`stores`·이 테이블을 하나의 트랜잭션으로 생성한다. V1 가입·로그인은 기존 이메일·비밀번호 방식을 유지한다. 이름·휴대폰 번호·인증번호 원문은 이 테이블에 저장하지 않는다.

### ✅user_sessions - 로그인 세션

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 세션 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 로그인 세션 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL | BIGINT UNSIGNED | 세션을 소유한 사용자 식별자 |
| 세션 토큰 해시 | `session_token_hash` | NOT NULL, UNIQUE | CHAR(64) | 세션 토큰의 SHA-256 해시값 |
| 만료 일시 | `expires_at` | NOT NULL | DATETIME | 세션이 만료되는 시각 |
| 폐기 일시 | `revoked_at` | NULL 허용 | DATETIME | 로그아웃 또는 강제 종료된 시각 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 세션 생성 시각 |

기기별 로그인 세션, 만료, 강제 로그아웃 상태를 관리한다.

추가 권장: expires_at은 created_at보다 뒤여야 한다.

### ✅password_reset_tokens - 이메일 비밀번호 재설정

비밀번호 찾기 요청 시 이메일로 발송하는 일회성 비밀번호 재설정 링크의 토큰을 저장한다. 토큰 원문은 저장하지 않고 해시만 저장하며, 링크 사용 또는 만료 후에는 재사용할 수 없다.

**향후 확장성:** 현재는 비밀번호 재설정 토큰·만료 시간·사용 여부를 DB 테이블에 저장한다. 향후 Redis를 도입하면 단기 토큰과 만료 상태를 Redis에서 관리하고, 이 테이블은 삭제 또는 감사 이력 용도로 축소할 수 있다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 인증 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 비밀번호 재설정 인증 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL | BIGINT UNSIGNED | 비밀번호 재설정을 요청한 사용자 식별자 |
| 재설정 토큰 해시 | `token_hash` | NOT NULL | CHAR(64) | 이메일 재설정 링크에 포함한 토큰의 SHA-256 해시값 |
| 만료 일시 | `expires_at` | NOT NULL | DATETIME | 재설정 링크 만료 시각 |
| 사용 일시 | `used_at` | NULL 허용 | DATETIME | 재설정 링크 사용 완료 시각 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 재설정 링크 발급 시각 |

## 4. STORE · 매장

사업자등록번호, 매장 기본 정보, 영업시간·휴무일, 메뉴 및 메뉴 이미지(OCR)를 담당한다. 메뉴 등록·조회·수정은 V2 확장 범위다.

### ✅stores - 매장

매출과 분석의 기준 단위인 사업자 매장을 저장한다. MVP에서는 사용자 1명당 매장 1개를 관리한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 매장 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 매장 식별자 |
| 소유자 사용자 ID | `owner_user_id` | FK → `users.id`, NOT NULL, UNIQUE | BIGINT UNSIGNED | MVP에서 사용자 1명당 매장 1개를 보장 |
| 사업자등록번호 | `business_registration_no` | NOT NULL, UNIQUE | CHAR(10) | 하이픈을 제외한 사업자등록번호 |
| 사업자 인증 일시 | `business_verified_at` | NOT NULL | DATETIME | 사업자 인증 완료 시각 |
| 매장명 | `name` | NOT NULL | VARCHAR(100) | 매장 이름 |
| 우편번호 | `postal_code` | NOT NULL | CHAR(5) | 도로명 주소 우편번호 |
| 도로명 주소 | `address` | NOT NULL | VARCHAR(255) | 매장 도로명 주소 |
| 상세 주소 | `address_detail` | NULL 허용 | VARCHAR(255) | 건물·호수 등 상세 주소 |
| 위도 | `latitude` | NOT NULL, CHECK (latitude BETWEEN -90 AND 90) | DECIMAL(10,7) | 매장 위치 위도 |
| 경도 | `longitude` | NOT NULL, CHECK (longitude BETWEEN -180 AND 180) | DECIMAL(10,7) | 매장 위치 경도 |
| 매장 상태 | `status` | NOT NULL, DEFAULT 'ACTIVE', CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')) | VARCHAR(20) | 정상 운영·운영 중지·이용 제한 상태 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 매장 등록 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 매장 정보 최종 수정 시각 |

확장 고려: 다매장 지원 시 `owner_user_id`의 UNIQUE를 제거하고 `store_members` 테이블을 추가한다.

### ✅store_business_hours - 영업 시간

요일별 영업시간을 저장한다. 자정 이후 마감은 closes_at이 opens_at보다 이른 값이면 다음 날 마감으로 해석한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 영업 시간 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 영업 시간 정보 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 영업 시간 대상 매장 식별자 |
| 요일 | `day_of_week` | NOT NULL, CHECK (`day_of_week` BETWEEN 1 AND 7), UNIQUE (`store_id`, `day_of_week`) | TINYINT UNSIGNED | `1`: 월요일, `7`: 일요일 |
| 영업 시작 시간 | `opens_at` | NULL 허용 | TIME | 휴무가 아닐 때의 영업 시작 시간 |
| 영업 종료 시간 | `closes_at` | NULL 허용 | TIME | 휴무가 아닐 때의 영업 종료 시간 |
| 휴무 여부 | `is_closed` | NOT NULL, DEFAULT FALSE | BOOLEAN | 해당 요일의 정기 휴무 여부 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 영업 시간 등록 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 영업 시간 최종 수정 시각 |

테이블 제약: UNIQUE(store_id, day_of_week). 

추가 권장: 휴무면 시작·마감 시간이 모두 NULL, 영업이면 둘 다 NOT NULL이어야 한다.

### ✅store_holidays - 매장 휴무일

특정 날짜의 임시 휴무를 저장한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 휴무일 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 매장 휴무일 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 휴무일이 등록된 매장 식별자 |
| 휴무 날짜 | `holiday_date` | NOT NULL, UNIQUE (`store_id`, `holiday_date`) | DATE | 매장 휴무 날짜 |
| 휴무 사유 | `reason` | NULL 허용 | VARCHAR(255) | 휴무 사유 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 휴무일 등록 시각 |

테이블 제약: UNIQUE(store_id, holiday_date).

### ✅menus - 메뉴

매장이 관리하는 메뉴와 판매 상태를 저장한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 메뉴 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 메뉴 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 메뉴가 등록된 매장 식별자 |
| 메뉴명 | `name` | NOT NULL | VARCHAR(100) | 메뉴 이름 |
| 메뉴 카테고리 | `category` | NOT NULL | VARCHAR(50) | 메뉴 분류 |
| 메뉴 가격 | `price` | NOT NULL, CHECK (`price` >= 0) | BIGINT
UNSIGNED | 메뉴 판매 가격 |
| 판매 상태 | `status` | NOT NULL, DEFAULT `'ACTIVE'`, CHECK (`status` IN ('ACTIVE', 'INACTIVE', 'SOLD_OUT')) | VARCHAR(20) | 메뉴 판매 가능 상태 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 메뉴 등록 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 메뉴 정보 최종 수정 시각 |

테이블 제약: UNIQUE(store_id, name). 추가 권장: price >= 0, status 허용값 제한.

### ✅menu_images - 메뉴 이미지 및 OCR 결과

메뉴판 이미지와 OCR 작업 결과 원본을 저장한다. 인식된 개별 메뉴 후보와 확정 상태는 `menu_image_items`에서 관리한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 메뉴 이미지 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 메뉴 이미지 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 이미지가 등록된 매장 식별자 |
| 이미지 주소 | `image_url` | NOT NULL | VARCHAR(2048) | 메뉴판 이미지 저장 주소 |
| OCR 처리 상태 | `ocr_status` | NOT NULL, DEFAULT `'PENDING'`, CHECK (`ocr_status` IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')) | VARCHAR(20) | 이미지 OCR 작업 진행 상태 |
| OCR 결과 | `ocr_result` | NULL 허용 | JSON | OCR로 추출한 메뉴 정보 원본 결과 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 메뉴 이미지 등록 시각 |

추가 권장: ocr_status는 PENDING, PROCESSING, COMPLETED, FAILED 값만 허용한다. OCR 후보별 확정·제외 상태는 `menu_image_items.status`에서 관리한다.

### ✅menu_image_items - OCR 메뉴 후보

메뉴판 이미지에서 인식한 메뉴 후보를 항목별로 저장한다. 사용자가 후보별로 메뉴명·카테고리·가격을 검토한 뒤 확정하거나 제외한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| OCR 메뉴 후보 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | OCR로 추출한 메뉴 후보 식별자 |
| 메뉴 이미지 ID | `menu_image_id` | FK → `menu_images.id`, NOT NULL | BIGINT UNSIGNED | 후보가 추출된 메뉴판 이미지 |
| 확정 메뉴 ID | `menu_id` | FK → `menus.id`, NULL 허용 | BIGINT UNSIGNED | 확정 후 생성·연결된 메뉴. 확정 전 또는 제외된 후보는 NULL |
| 인식 메뉴명 | `detected_name` | NOT NULL | VARCHAR(100) | OCR이 인식한 메뉴명 후보 |
| 인식 카테고리 | `detected_category` | NULL 허용 | VARCHAR(50) | OCR이 추정한 메뉴 카테고리 |
| 인식 가격 | `detected_price` | NULL 허용, CHECK (`detected_price` >= 0) | BIGINT UNSIGNED | OCR이 인식한 가격 후보 |
| 신뢰도 | `confidence` | NULL 허용, CHECK (`confidence` BETWEEN 0 AND 1) | DECIMAL(5,4) | OCR 인식 신뢰도 |
| 검토 상태 | `status` | NOT NULL, DEFAULT `'PENDING'`, CHECK (`status` IN ('PENDING', 'CONFIRMED', 'REJECTED')) | VARCHAR(20) | 사용자 검토 전·확정·제외 상태 |
| 검토 일시 | `reviewed_at` | NULL 허용 | DATETIME | 후보 메뉴 검토 완료 시각 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | OCR 후보 생성 시각 |

테이블 제약: CHECK(detected_price IS NULL OR detected_price >= 0), CHECK(confidence IS NULL OR confidence BETWEEN 0 AND 1), CHECK(status IN ('PENDING', 'CONFIRMED', 'REJECTED')), CHECK(status <> 'CONFIRMED' OR menu_id IS NOT NULL).

## 5. SOL · 솔루션

홈 대시보드, AI 챗봇 및 매출 분석 기반 운영 제안의 조회·저장을 담당한다.

### ✅solutions - 솔루션

AI가 생성한 개별 솔루션 카드를 저장한다. 각 카드는 하나의 솔루션 묶음에 속하며 묶음 안에서 표시 순서를 가진다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 솔루션 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 개별 솔루션 카드 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 솔루션 대상 매장 |
| 매출 분석 ID | `sales_analysis_id` | FK → `sales_analyses.id`, NOT NULL | BIGINT UNSIGNED | 솔루션 생성 근거가 된 분석 |
| 솔루션 묶음 ID | `solution_bundle_id` | FK → `solution_bundles.id`, NOT NULL | BIGINT UNSIGNED | 오늘의 솔루션 묶음 |
| 솔루션 유형 | `solution_type` | NOT NULL, CHECK (`solution_type` IN ('DAILY', 'MANUAL')) | VARCHAR(30) | 일일 자동 생성 또는 수동 생성 |
| 솔루션 제목 | `title` | NOT NULL | VARCHAR(200) | 카드 제목 |
| 솔루션 요약 | `summary_text` | NOT NULL | TEXT | 목록에 표시할 요약 |
| 솔루션 상세 내용 | `detail_text` | NOT NULL | TEXT | 상세 화면 내용 |
| AI 생성 일시 | `generated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | AI가 생성한 시각 |
| 저장 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | DB 저장 시각 |
| 표시 순서 | `rank_no` | NOT NULL, CHECK (`rank_no` > 0) | INT UNSIGNED | 묶음 안의 노출 순서 |

테이블 제약: UNIQUE (`solution_bundle_id`, `rank_no`).

### ✅solution_bundles - 솔루션 묶음

예측 모델 기반으로 생성한 매장별 솔루션 카드 묶음을 관리한다. 매출 AI 인사이트는 `sales_ai_insights`에서 별도로 관리한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 솔루션 묶음 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 솔루션 묶음 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 솔루션 대상 매장 |
| 매출 분석 ID | `sales_analysis_id` | FK → `sales_analyses.id`, NOT NULL, INDEX | BIGINT UNSIGNED | 솔루션 생성 근거 분석. 다음 날짜 솔루션이 같은 분석 결과를 재사용할 수 있으므로 단독 UNIQUE는 두지 않는다. |
| 대상 일자 | `target_date` | NOT NULL | DATE | 오늘의 솔루션 노출 기준일 |
| 생성 상태 | `status` | NOT NULL, DEFAULT 'PENDING', CHECK (`status` IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')) | VARCHAR(20) | MVP 동기 처리에서는 생성 요청 안에서 GENERATING → COMPLETED 또는 FAILED로 완료한다. 향후 비동기 처리에서는 PENDING(대기) → GENERATING → COMPLETED 또는 FAILED로 관리한다. |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 생성 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 상태·내용 수정 시각 |

테이블 제약: UNIQUE (`store_id`, `target_date`)로 업로드 직후 생성과 00:00 배치의 동일 매장·동일 날짜 중복 생성을 방지한다. `sales_analysis_id`는 조회 성능을 위한 일반 인덱스(INDEX)로 둔다.

### ✅saved_solutions - 저장한 솔루션

사용자가 나중에 다시 보기 위해 저장한 솔루션 이력을 보관한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 저장 이력 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 저장 이력 식별자 |
| 사용자 ID | user_id | FK → users.id, NOT NULL | BIGINT UNSIGNED | 저장 사용자 |
| 솔루션 ID | solution_id | FK → solutions.id, NOT NULL | BIGINT UNSIGNED | 저장 솔루션 |
| 저장 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 저장 시각 |

테이블 제약: UNIQUE(user_id, solution_id)

### ✅chat_messages - AI 챗봇 메시지

사용자 질문과 AI 답변, 답변 근거 및 스트리밍 처리 상태를 저장한다. 별도 대화방 테이블 없이 사용자와 참조한 솔루션 묶음을 기준으로 최근 대화 이력을 조회하는 현재 MVP 구조다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 채팅 메시지 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 메시지 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL | BIGINT UNSIGNED | 메시지 소유 사용자 |
| 솔루션 묶음 ID | `solution_bundle_id` | FK → `solution_bundles.id`, NULL 허용 | BIGINT UNSIGNED | 답변 생성 시 참조한 솔루션 |
| 발화 주체 | `role` | NOT NULL, CHECK (`role` IN ('USER', 'ASSISTANT')) | VARCHAR(20) | 질문·답변 구분 |
| 메시지 내용 | `content` | NOT NULL | TEXT | 질문 또는 AI 답변 |
| 답변 근거 | `evidence_json` | NULL 허용 | JSON | 답변에 사용한 지표·근거 |
| 처리 상태 | `status` | NOT NULL, DEFAULT 'COMPLETED', CHECK (`status` IN ('PENDING', 'STREAMING', 'COMPLETED', 'FAILED')) | VARCHAR(20) | PENDING, STREAMING, COMPLETED, FAILED |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 메시지 생성 시각 |

## 6. SALES · 매출 분석

매출 파일 업로드, 주문 원천 데이터, KPI·메뉴 성과·리뷰 분석, 비용·날씨 데이터 기반 AI 인사이트를 담당한다. 매출 달력은 V3 확장 범위다.

### 매출 업로드와 주문

### ✅sales_uploads - 매출 파일 업로드

토스 POS 원본 파일과 파일이 포함하는 전체 매출 기간, 검증·처리 상태를 저장한다. 한 파일에 여러 달이 포함될 수 있으며 동일·중첩 기간 파일도 업로드 이력으로 보존한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 업로드 ID |
| `requested_by_user_id` | BIGINT UNSIGNED | FK → `users.id`, NOT NULL | 요청 사용자 |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `period_start` | DATE | NOT NULL | 파일의 첫 매출일 |
| `period_end` | DATE | NOT NULL | 데이터 기준 시트의 종료일 |
| `source_type` | VARCHAR(30) | NOT NULL, DEFAULT `TOSS_POS` | 원본 파일 유형 |
| `original_file_name` | VARCHAR(255) | NOT NULL | 원본 파일명 |
| `storage_key` | VARCHAR(512) | NOT NULL, UNIQUE | 비공개 저장소 객체 키 |
| `file_checksum` | CHAR(64) | NOT NULL | SHA-256 체크섬. 차단이 아닌 추적용 |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT `PENDING` | PENDING/PROCESSING/COMPLETED/FAILED |
| `processing_phase` | VARCHAR(20) | NULL | VALIDATING/NORMALIZING/AGGREGATING/ANALYZING |
| `total_row_count` | INT UNSIGNED | NOT NULL, DEFAULT 0 | 전체 데이터 행 수 |
| `valid_row_count` | INT UNSIGNED | NOT NULL, DEFAULT 0 | 검증 통과 행 수 |
| `invalid_row_count` | INT UNSIGNED | NOT NULL, DEFAULT 0 | 오류 행 수 |
| `error_code` | VARCHAR(50) | NULL | 구조화된 실패 코드 |
| `error_message` | TEXT | NULL | 사용자 안내용 실패 사유 |
| `uploaded_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 업로드 시각 |
| `processed_at` | DATETIME | NULL | 기본 매출 반영 완료 시각 |

테이블 제약:

- `CHECK(period_start <= period_end)`
- `CHECK(total_row_count = valid_row_count + invalid_row_count)`
- `INDEX(store_id, uploaded_at)`, `INDEX(store_id, period_start, period_end)`, `INDEX(store_id, file_checksum)`
- 동일 체크섬과 기간 중첩 업로드를 막는 UNIQUE 제약은 두지 않는다.

### ✅sales_orders - 매출 주문

토스 POS 주문을 `(channel, pos_order_no, ordered_at)` 기준으로 묶은 주문 단위다. 주문번호는 재사용되므로 단독 식별자로 사용하지 않는다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 주문 ID |
| `sales_upload_id` | BIGINT UNSIGNED | FK → `sales_uploads.id`, NOT NULL | 현재 주문을 반영한 업로드 |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `channel` | VARCHAR(20) | NOT NULL | KIOSK/POS/DELIVERY |
| `pos_order_no` | VARCHAR(100) | NOT NULL | 앞자리 0을 보존한 POS 주문번호 |
| `ordered_at` | DATETIME | NOT NULL | 주문 시작 시각(KST) |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 생성 시각 |

테이블 제약:

- `UNIQUE(store_id, channel, pos_order_no, ordered_at)`
- `INDEX(store_id, ordered_at)`, `INDEX(sales_upload_id)`

### ✅sales_order_items - 주문 항목

토스 POS `상품 주문 상세내역`의 각 행을 정규화해 저장한다. 완료와 취소 행을 모두 보존하며 취소 행의 수량·금액은 음수 그대로 저장한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 주문 항목 ID |
| `sales_order_id` | BIGINT UNSIGNED | FK → `sales_orders.id`, NOT NULL | 상위 주문 |
| `order_date` | DATE | NOT NULL | 주문기준일자 |
| `status` | VARCHAR(20) | NOT NULL | COMPLETED/CANCELED |
| `menu_name_raw` | VARCHAR(255) | NOT NULL | POS 원본 상품명 |
| `menu_name` | VARCHAR(255) | NOT NULL | 이모지·공백 정리 상품명 |
| `menu_key` | VARCHAR(255) | NOT NULL | 괄호·공백 등을 제거한 매칭 키 |
| `category_raw` | VARCHAR(100) | NULL | POS 원본 카테고리 |
| `option_raw` | VARCHAR(500) | NULL | POS 원본 옵션 문자열 |
| `quantity` | INT | NOT NULL | 완료 양수, 취소 음수 |
| `line_price` | BIGINT | NOT NULL | 수량이 반영된 상품가격 |
| `unit_price` | BIGINT | NOT NULL | `line_price / quantity` 파생 단가 |
| `option_price` | BIGINT | NOT NULL, DEFAULT 0 | 옵션 금액. 취소 행은 음수 가능 |
| `item_discount_name` | VARCHAR(255) | NULL | 상품 할인명 |
| `item_discount_amount` | BIGINT | NOT NULL, DEFAULT 0 | 상품 할인. 원본 부호 보존 |
| `order_discount_name` | VARCHAR(255) | NULL | 주문 할인명 |
| `order_discount_amount` | BIGINT | NOT NULL, DEFAULT 0 | 주문 할인. 원본 부호 보존 |
| `net_amount` | BIGINT | NOT NULL | 실판매금액. 취소 행은 음수 가능 |
| `is_taxable` | BOOLEAN | NOT NULL | 과세 여부 |
| `vat_amount` | BIGINT | NOT NULL, DEFAULT 0 | 부가세. 취소 행은 음수 가능 |
| `item_type` | VARCHAR(30) | NOT NULL | MENU/PARKING/PREPAID_CARD/DELIVERY_FEE/PLATFORM_PLACEHOLDER/EVENT/GOODS |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 저장 시각 |

테이블 제약:

- `CHECK(quantity <> 0)`
- `CHECK(status IN ('COMPLETED','CANCELED'))`
- `CHECK(net_amount = line_price + option_price + item_discount_amount + order_discount_amount)`
- `INDEX(sales_order_id)`, `INDEX(order_date)`, `INDEX(menu_key)`, `INDEX(item_type)`

### ✅store_menu_categories - 매장별 메뉴 카테고리

메뉴명 표기 차이와 배달 주문의 카테고리 누락을 보완하기 위한 매장별 최종 카테고리 결정값이다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 매핑 ID |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `menu_key` | VARCHAR(255) | NOT NULL | 정규화 메뉴 키 |
| `menu_name` | VARCHAR(255) | NOT NULL | 최근 표시 메뉴명 |
| `category` | VARCHAR(30) | NOT NULL | 표준 카테고리 |
| `source` | VARCHAR(20) | NOT NULL | OVERRIDE/POS_LATEST/KEY_MATCH/UNMAPPED |
| `last_seen_at` | DATETIME | NOT NULL | 마지막 관측 시각 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 생성 시각 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 수정 시각 |

테이블 제약: `UNIQUE(store_id, menu_key)`.

### ✅sales_daily_summaries - 일별 매출 요약

화면 KPI와 일별 추이를 위한 매장·날짜 단위 집계다. 커버리지 내 매출 없는 날도 0원 행을 생성한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 요약 ID |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `sales_date` | DATE | NOT NULL | 매출 일자 |
| `total_net_amount` | BIGINT | NOT NULL, DEFAULT 0 | 전체 항목 실판매금액 합계 |
| `menu_net_amount` | BIGINT | NOT NULL, DEFAULT 0 | MENU 항목 실판매금액 합계 |
| `order_count` | INT UNSIGNED | NOT NULL, DEFAULT 0 | 유효 주문 수 |
| `menu_quantity` | INT | NOT NULL, DEFAULT 0 | MENU 순수량 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 갱신 시각 |

테이블 제약: `UNIQUE(store_id, sales_date)`.

### ✅sales_hourly_summaries - 시간대별 매출 요약

`ordered_at`의 KST 시간 기준 MENU 매출과 유효 주문 수를 집계한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 요약 ID |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `sales_date` | DATE | NOT NULL | 매출 일자 |
| `hour_of_day` | TINYINT UNSIGNED | NOT NULL | 0~23시 |
| `menu_net_amount` | BIGINT | NOT NULL, DEFAULT 0 | MENU 실판매금액 합계 |
| `order_count` | INT UNSIGNED | NOT NULL, DEFAULT 0 | 유효 주문 수 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 생성 시각 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 갱신 시각 |

테이블 제약: `UNIQUE(store_id, sales_date, hour_of_day)`.

### ✅sales_daily_category_summaries - 일별 카테고리 매출 요약

MENU 항목만 표준 카테고리별로 집계한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 요약 ID |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `sales_date` | DATE | NOT NULL | 매출 일자 |
| `category` | VARCHAR(30) | NOT NULL | 표준 카테고리 |
| `net_amount` | BIGINT | NOT NULL, DEFAULT 0 | 실판매금액 합계 |
| `quantity` | INT | NOT NULL, DEFAULT 0 | 순수량 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 갱신 시각 |

테이블 제약: `UNIQUE(store_id, sales_date, category)`.

### ✅sales_daily_menu_summaries - 일별 메뉴 매출 요약

MENU 항목을 정규화된 메뉴 키별로 집계한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| `id` | BIGINT UNSIGNED | PK, AUTO_INCREMENT | 요약 ID |
| `store_id` | BIGINT UNSIGNED | FK → `stores.id`, NOT NULL | 대상 매장 |
| `sales_date` | DATE | NOT NULL | 매출 일자 |
| `menu_key` | VARCHAR(255) | NOT NULL | 정규화 메뉴 키 |
| `menu_name` | VARCHAR(255) | NOT NULL | 표시 메뉴명 |
| `net_amount` | BIGINT | NOT NULL, DEFAULT 0 | 실판매금액 합계 |
| `quantity` | INT | NOT NULL, DEFAULT 0 | 순수량 |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | 갱신 시각 |

테이블 제약: `UNIQUE(store_id, sales_date, menu_key)`.

### ✅sales_forecasts - 매출 예측

예측 모델이 생성한 매장별 일자 단위 매출 예측 결과를 저장한다. 매출 분석 화면의 오늘 예측 매출과 AI 솔루션 생성 metrics에서 조회한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 매출 예측 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 예측 결과 식별자 |
| 매장 ID | `store_id` | FK → `stores.id`, NOT NULL | BIGINT UNSIGNED | 예측 대상 매장 |
| 예측 대상 일자 | `target_date` | NOT NULL | DATE | 매출을 예측하는 날짜 |
| 예측 기준 일자 | `basis_date` | NOT NULL | DATE | 예측 생성 시점의 기준 날짜 |
| 예상 매출액 | `predicted_sales_amount` | NOT NULL, CHECK (`predicted_sales_amount` &gt;= 0) | BIGINT UNSIGNED | 원 단위 정수로 저장하는 예측 매출 금액 |
| 예측 모델 버전 | `model_version` | NOT NULL | VARCHAR(50) | 예측에 사용한 모델 버전 |
| 예측 생성 일시 | `generated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 예측 결과 생성 시각 |

테이블 제약: UNIQUE (`store_id`, `target_date`, `model_version`).

### 분석

### ✅analysis_runs - 분석 실행

비동기 분석 요청의 상태, 재시도, 실패 사유를 관리한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 분석 실행 ID |
| based_on_upload_id | BIGINT UNSIGNED | FK → sales_uploads.id, NOT NULL | 기준 업로드 |
| store_id | BIGINT UNSIGNED | FK → stores.id, NOT NULL | 분석 매장 |
| requested_by_user_id | BIGINT UNSIGNED | FK → users.id, NOT NULL | 요청 사용자 |
| analysis_type | VARCHAR(30) | NOT NULL | SALES, REVIEW 등 분석 유형 |
| period_start | DATE | NOT NULL | 분석 기간 시작일 |
| period_end | DATE | NOT NULL, CHECK (period_start <= period_end) | 분석 기간 종료일 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'PENDING', CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')) | 처리 상태 |
| engine_version | VARCHAR(50) | NOT NULL | 분석 엔진 버전 |
| idempotency_key | VARCHAR(100) | NOT NULL, UNIQUE | 중복 요청 방지 키 |
| error_message | VARCHAR(500) | NULL 허용 | 실패 사유 |
| started_at | DATETIME | NULL 허용 | 실제 시작 시점 |
| completed_at | DATETIME | NULL 허용, CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at) | 실제 종료 시점 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 요청 시점 |

테이블 제약: INDEX(based_on_upload_id), INDEX(store_id, status).

### ✅sales_analyses - 매출 분석 결과

분석 실행 1건의 매출 요약을 저장한다. 월별 매출 AI 인사이트의 내용과 생성 상태는 `sales_ai_insights`에서 관리한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 결과 ID |
| analysis_run_id | BIGINT UNSIGNED | FK → analysis_runs.id, NOT NULL, UNIQUE | 원본 분석 실행. 분석 실행 1건당 결과 1건을 보장한다. |
| summary_text | TEXT | NULL 허용 | 매출 분석 요약 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 결과 생성 시점 |

### ✅sales_ai_insights - 월별 매출 AI 인사이트

매장별 매출 데이터를 집계·비교하여 생성한 화면용 인사이트를 월 단위로 저장한다. 누적 매출 데이터가 2주(14일) 이상인 경우에만 생성하며, 같은 월에는 기존 인사이트를 재사용한다. FE의 “AI가 발견했어요” 영역은 1~3개의 불릿을 표시하므로 단일 TEXT가 아닌 JSON 배열로 저장한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 인사이트 ID |
| store_id | BIGINT UNSIGNED | FK → stores.id, NOT NULL | 인사이트 대상 매장 |
| sales_analysis_id | BIGINT UNSIGNED | FK → sales_analyses.id, NOT NULL, INDEX | 인사이트 생성 근거가 된 매출 분석 결과 |
| target_month | DATE | NOT NULL | 인사이트를 노출하는 월의 첫째 날 |
| insights | JSON | NOT NULL, JSON 배열 | 화면에 표시할 1~3개 인사이트 문구. 예: [“최근 화요일 매출이 3주 연속 감소하고 있어요.”, “오후 3~5시는 다른 시간대보다 매출이 낮아요.”] |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'PENDING', CHECK (status IN ('PENDING', 'GENERATING', 'COMPLETED', 'FAILED')) | 인사이트 생성 상태 |
| generated_at | DATETIME | NULL 허용 | 인사이트 생성 완료 시각 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 레코드 생성 시각 |
| updated_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | 상태·내용 수정 시각 |

테이블 제약: UNIQUE(`store_id`, `target_month`)로 매장별 월 1건만 저장한다. INDEX(`sales_analysis_id`), INDEX(`store_id`, `target_month`, `status`). `insights`는 JSON 배열만 저장하며, 서비스 계층에서 배열 길이 1~3개·각 항목의 비어 있지 않은 문자열 여부를 검증한다.

### ✅analysis_metrics - 분석 지표

확장 가능한 KPI를 코드와 값의 행 단위로 저장한다. 금액·건수·비율 등 단위가 서로 다른 지표를 하나의 테이블에 저장하므로 값 컬럼은 소수점 비율을 표현할 수 있는 DECIMAL을 사용한다. 금액 지표는 소수부 없이 저장한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 지표 ID |
| sales_analysis_id | BIGINT UNSIGNED | FK → sales_analyses.id, NOT NULL | 상위 매출 분석 |
| metric_code | VARCHAR(50) | NOT NULL | NET_SALES 등 지표 코드 |
| metric_value | DECIMAL(18,4) | NOT NULL | 현재 기간의 지표 값. KRW는 소수부 없이 저장하고, 비율은 소수점 값을 저장한다. |
| comparison_value | DECIMAL(18,4) | NULL 허용 | 비교 기간 지표 값 |
| unit | VARCHAR(20) | NOT NULL, CHECK (unit IN ('KRW', 'COUNT', 'PERCENT')) | 지표 단위 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 생성 시점 |
|  |  |  |  |

테이블 제약: UNIQUE(sales_analysis_id, metric_code), INDEX(metric_code).

### ✅menu_analysis_results - 메뉴 분석 결과

분석 시점의 메뉴별 매출, 판매량, 순위를 저장한다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 결과 ID |
| sales_analysis_id | BIGINT UNSIGNED | FK → sales_analyses.id, NOT NULL | 상위 매출 분석 |
| menu_id | BIGINT UNSIGNED | FK → menus.id, NULL 허용 | 현재 메뉴 연결. 삭제·미매칭된 메뉴의 과거 분석도 보존할 수 있어 NULL을 허용한다. |
| menu_name_snapshot | VARCHAR(100) | NOT NULL | 분석 당시 메뉴명 |
| sales_amount | BIGINT UNSIGNED | NOT NULL, CHECK (sales_amount >= 0) | 메뉴 매출액(원) |
| sales_quantity | INT UNSIGNED | NOT NULL, CHECK (sales_quantity >= 0) | 판매 수량 |
| sales_rank | INT UNSIGNED | NULL 허용, CHECK (sales_rank IㅑS NULL OR sales_rank > 0) | 매출 순위 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 결과 생성 시점 |

테이블 제약: UNIQUE(sales_analysis_id, menu_id). 동점이 허용될 수 있으므로 `sales_rank`에는 UNIQUE 제약을 두지 않는다.

### ✅review_analyses - 리뷰 분석 결과

리뷰 분석 실행 1건의 요약·키워드 결과를 저장한다. 매장과 분석 기간은 `analysis_runs`에서 조회하므로 중복 저장하지 않는다.

| 물리명 | 타입 | 제약사항 | 설명 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK, NOT NULL, AUTO_INCREMENT | 결과 ID |
| analysis_run_id | BIGINT UNSIGNED | FK → analysis_runs.id, NOT NULL, UNIQUE | 원본 리뷰 분석 실행. 실행 1건당 결과 1건을 보장한다. |
| summary_text | TEXT | NULL 허용 | 리뷰 분석 요약 |
| keyword_result | JSON | NULL 허용 | AI가 추출한 키워드·언급 수 결과 |
| sentiment_result | JSON | NOT NULL | AI가 분석한 긍정·중립·부정 리뷰의 건수와 비율 |
| engine_version | VARCHAR(50) | NOT NULL | 리뷰 분석 엔진 버전 |
| created_at | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 결과 생성 시점 |

테이블 제약: INDEX(analysis_run_id). `analysis_run_id`의 UNIQUE 제약으로 분석 실행 1건당 리뷰 결과를 하나만 저장한다.

### 비용 및 외부 데이터

### ✅store_cost_items - 비용 항목(순이익 계산)

매장별 월 단위 임대료·인건비와 원가율을 저장해 순이익 분석에 사용한다. 금액은 원 단위로 저장하고, 원가율만 비율 계산을 위해 DECIMAL을 사용한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 비용 항목 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 비용 항목 식별자 |
| 매장 ID | store_id | FK → stores.id, NOT NULL | BIGINT UNSIGNED | 비용이 적용되는 매장 |
| 비용 기준 월 | cost_month | NOT NULL | DATE | 비용 적용 월. 해당 월의 첫째 날로 저장 |
| 임대료 | rent_amount | NOT NULL, DEFAULT 0 | BIGINT UNSIGNED | 월 임대료(원) |
| 인건비 | labor_amount | NOT NULL, DEFAULT 0 | BIGINT UNSIGNED | 월 인건비(원) |
| 원가율 | ingredient_cost_rate | NOT NULL | DECIMAL(5,2) | 매출 대비 재료비 비율(%) |
| 생성 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 비용 정보 생성 시각 |
| 수정 일시 | updated_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 비용 정보 최종 수정 시각 |

테이블 제약: UNIQUE(store_id, cost_month), CHECK(ingredient_cost_rate BETWEEN 0 AND 100).

### ✅reviews - 리뷰

네이버에서 크롤링한 원본 리뷰를 저장한다. 리뷰 분석 결과는 review_analyses에 저장하며, 이 테이블은 화면의 관련 리뷰 조회와 재분석의 원본 데이터로 사용한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 리뷰 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 리뷰 식별자 |
| 매장 ID | store_id | FK → stores.id, NOT NULL | BIGINT UNSIGNED | 리뷰 대상 매장 |
| 외부 리뷰 ID | external_review_id | NOT NULL | VARCHAR(100) | 네이버에서 제공하는 리뷰 고유 식별값 |
| 별점 | rating | NULL 허용, CHECK(rating BETWEEN 0 AND 5) | DECIMAL(3,2) | 네이버 별점. 별점이 없는 경우 NULL |
| 리뷰 본문 | content | NULL 허용 | TEXT | 크롤링한 리뷰 원문 |
| 리뷰 작성 일시 | reviewed_at | NULL 허용 | DATETIME | 네이버에 표시된 작성 시각 |
| 수집 일시 | collected_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 시스템이 크롤링해 저장한 시각 |

테이블 제약: UNIQUE(store_id, external_review_id).

### ✅weather_observations - 날씨 관측값

날짜와 좌표 기준의 날씨 정보를 저장해 매출 달력과 향후 날씨 연동 분석에 사용한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 날씨 관측 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 날씨 관측값 식별자 |
| 관측 일자 | observation_date | NOT NULL | DATE | 일 단위 날씨 관측 기준일 |
| 위도 | latitude | NOT NULL | DECIMAL(10,7) | 날씨 조회 위치의 위도 |
| 경도 | longitude | NOT NULL | DECIMAL(10,7) | 날씨 조회 위치의 경도 |
| 날씨 코드 | weather_code | NOT NULL | VARCHAR(30) | 날씨 상태 코드. 예: CLEAR, RAIN, SNOW |
| 기온 | temperature_celsius | NULL 허용 | DECIMAL(5,2) | 섭씨 기온. 영하값 저장 가능 |
| 강수량 | precipitation_mm | NULL 허용 | DECIMAL(8,2) | 강수량(mm) |
| 날씨 제공처 | source | NOT NULL | VARCHAR(50) | 날씨 API 제공처 |
| 생성 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 날씨 정보 수집 시각 |

테이블 제약:

- UNIQUE(observation_date, latitude, longitude)
- CHECK(latitude BETWEEN -90 AND 90)
- CHECK(longitude BETWEEN -180 AND 180)
- CHECK(precipitation_mm IS NULL OR precipitation_mm >= 0)

## 7. RANK · 성장 랭킹 (V2 예정)

성장률 순위 산정·조회 및 순위 변동 알림의 기준 데이터를 담당한다.

### ✅ranking_profiles - 랭킹 프로필

랭킹 대상 매장과 외부 공개용 익명 닉네임을 저장한다. 랭킹 참여 조건을 충족한 매장은 자동으로 랭킹에 포함한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 랭킹 프로필 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 랭킹 프로필 식별자 |
| 매장 ID | store_id | FK → stores.id, NOT NULL | BIGINT UNSIGNED | 랭킹 대상 매장 |
| 익명 닉네임 | anonymous_nickname | NOT NULL | VARCHAR(50) | 외부 랭킹에 표시할 익명 닉네임 |
| 생성 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 랭킹 프로필 생성 시각 |

테이블 제약:

- UNIQUE(store_id)
- UNIQUE(anonymous_nickname)

### ✅ranking_snapshots - 랭킹 집계

비교 기간별 랭킹 집계 실행 정보를 저장한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 랭킹 집계 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 랭킹 집계 식별자 |
| 선정 기간 시작일 | period_start | NOT NULL | DATE | 랭킹 산정 대상 기간 시작일 |
| 선정 기간 종료일 | period_end | NOT NULL | DATE | 랭킹 산정 대상 기간 종료일 |
| 비교 기간 시작일 | comparison_start | NOT NULL | DATE | 성장률 비교 기준 기간 시작일 |
| 비교 기간 종료일 | comparison_end | NOT NULL | DATE | 성장률 비교 기준 기간 종료일 |
| 집계 완료 일시 | calculated_at | NULL 허용 | DATETIME | 랭킹 집계가 완료된 시각 |
| 집계 상태 | status | NOT NULL, DEFAULT 'PENDING' | VARCHAR(20) | 랭킹 집계 처리 상태 |
| 생성 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 집계 요청 레코드가 생성된 시각 |

테이블 제약:

- UNIQUE(period_start, period_end, comparison_start, comparison_end)
- CHECK(period_start <= period_end)
- CHECK(comparison_start <= comparison_end)
- CHECK(status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'))

### ✅ranking_entries - 랭킹 결과

랭킹 집계별 매장 순위와 성장률·비교 매출을 저장한다. 성장률과 선정 기간 총매출이 모두 같은 경우 공동 순위를 허용한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 랭킹 결과 ID | id | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 랭킹 결과 식별자 |
| 랭킹 집계 ID | ranking_snapshot_id | FK → ranking_snapshots.id, NOT NULL | BIGINT UNSIGNED | 상위 랭킹 집계 |
| 랭킹 프로필 ID | ranking_profile_id | FK → ranking_profiles.id, NOT NULL | BIGINT UNSIGNED | 랭킹 대상 프로필 |
| 순위 | rank_no | NOT NULL | INT UNSIGNED | 집계 내 순위. 공동 순위 허용 |
| 성장률 | growth_rate | NOT NULL | DECIMAL(10,4) | 매출 성장률(%). 음수 가능 |
| 선정 기간 매출 | selected_period_sales | NOT NULL | BIGINT UNSIGNED | 선정 기간 총매출(원) |
| 비교 기간 매출 | comparison_period_sales | NOT NULL | BIGINT UNSIGNED | 비교 기간 총매출(원) |
| 생성 일시 | created_at | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 랭킹 결과가 저장된 시각 |

테이블 제약:

- UNIQUE(ranking_snapshot_id, ranking_profile_id)
- CHECK(rank_no > 0)
- 동일 집계 내 rank_no는 공동 순위를 위해 중복 허용한다.

## 8. NOTI · 알림

분석 완료, 솔루션 제공, 랭킹 변동 등 알림 목록·읽음 처리·수신 설정을 담당한다.

### ✅notifications - 알림

사용자에게 발송되는 분석 완료·랭킹 변동 알림과 읽음 상태를 저장한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 알림 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 알림 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL | BIGINT UNSIGNED | 알림 수신 사용자 식별자 |
| 알림 유형 | `notification_type` | NOT NULL | VARCHAR(50) | 예: `SOLUTION`, `RANKING_CHANGE` |
| 제목 | `title` | NOT NULL | VARCHAR(255) | 알림 제목 |
| 내용 | `content` | NOT NULL | TEXT | 알림 본문 |
| 예약 발송 일시 | `scheduled_at` | NULL 허용 | DATETIME | 예약된 알림 발송 시각 |
| 발송 일시 | `sent_at` | NULL 허용 | DATETIME | 실제 알림 발송 시각 |
| 읽음 일시 | `read_at` | NULL 허용 | DATETIME | 사용자가 알림을 읽은 시각 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 알림 생성 시각 |

### ✅notification_preferences - 알림 설정

사용자별 알림 수신 설정을 저장한다.

| 논리명 | 물리명 | 제약사항 | 타입 | 부가 설명 |
| --- | --- | --- | --- | --- |
| 알림 설정 ID | `id` | PK, NOT NULL, AUTO_INCREMENT | BIGINT UNSIGNED | 알림 설정 식별자 |
| 사용자 ID | `user_id` | FK → `users.id`, NOT NULL, UNIQUE | BIGINT UNSIGNED | 사용자별 알림 설정을 하나만 유지 |
| 솔루션 제공 알림 수신 여부 | `solution_enabled` | NOT NULL, DEFAULT TRUE | BOOLEAN | 솔루션 제공 관련 알림 수신 여부 |
| 매출 업로드 알림 수신 여부 | `sales_upload_reminder_enabled` | NOT NULL, DEFAULT TRUE | BOOLEAN | 매출 업로드 리마인드 알림 수신 여부 |
| 랭킹 변동 알림 수신 여부 | `ranking_change_enabled` | NOT NULL, DEFAULT TRUE | BOOLEAN | 랭킹 변동 알림 수신 여부 |
| 생성 일시 | `created_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP | DATETIME | 알림 설정 생성 시각 |
| 수정 일시 | `updated_at` | NOT NULL, DEFAULT CURRENT_TIMESTAMP, ON UPDATE CURRENT_TIMESTAMP | DATETIME | 알림 설정 최종 수정 시각 |

## 9. 핵심 관계와 설계 근거

- 사용자 1명은 여러 세션, 인증 토큰, 알림을 가질 수 있다.
- 사용자와 매장은 MVP에서 1:1이다. owner_user_id의 UNIQUE가 이를 보장한다.
- 매장 1곳은 여러 메뉴, 업로드, 주문, 분석, 솔루션을 가진다.
- 업로드 1건은 여러 주문을, 주문 1건은 완료·취소를 포함한 여러 주문 항목을 가진다.
- 주문은 `(store_id, channel, pos_order_no, ordered_at)`으로 식별하고, 기간 중첩 재업로드는 새 커버리지의 기존 주문 항목을 교체한다.
- 매장별 메뉴 카테고리는 `store_menu_categories`에서 관리하며 일별·시간대별·카테고리별·메뉴별 집계를 재계산한다.
- 분석 실행과 분석 결과를 분리해 비동기 상태, 재시도, 실패 원인을 안전하게 관리한다.
- 원본 메뉴명과 정규화 메뉴명·메뉴 키를 함께 보존해 과거 주문과 분석 결과를 재현한다.

## 10. 요구사항 추적

| 도메인 | 요구사항 ID | ERD 반영 |
| --- | --- | --- |
| AUTH | BR-AUTH-05, BR-AUTH-21, BR-AUTH-25 | users, user_sessions, password_reset_tokens |
| STORE | BR-STORE-05 ~ 08 | stores, store_business_hours, store_holidays, menus, menu_images, menu_image_items |
| SOL | BR-SOL-03 ~ 16 | solutions, saved_solutions |
| SALES | BR-SALES-04, BR-SALES-07 ~ 16 | sales_uploads, sales_orders, sales_order_items, store_menu_categories, sales_daily_summaries, sales_hourly_summaries, sales_daily_category_summaries, sales_daily_menu_summaries, sales_forecasts, analysis_runs, sales_analyses, sales_ai_insights, analysis_metrics, menu_analysis_results, review_analyses |
| RANK | BR-RANK-05 ~ 10 | ranking_profiles, ranking_snapshots, ranking_entries |
| NOTI | BR-NOTI-02 ~ 07 | notifications, notification_preferences |

## 11. MySQL 8.0 기준 수정 DDL

첨부된 초안의 `DEFAULT AS`, 금액 컬럼의 `TIMESTAMP`, 누락된 PK·FK·UNIQUE·CHECK 제약을 수정했다. 금액 데이터와 업로드 데이터의 정합성을 위해 주문·주문항목·일별 집계·분석 실행에 필요한 키와 인덱스를 포함한다.

### AUTH

```sql
CREATE TABLE users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  last_login_at DATETIME NULL,
  deleted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_email (email),
  UNIQUE KEY uk_users_phone (phone)
) ENGINE=InnoDB;

CREATE TABLE user_auth_providers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  provider VARCHAR(20) NOT NULL,
  provider_subject VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_auth_provider_subject (provider, provider_subject),
  UNIQUE KEY uk_auth_user_provider (user_id, provider),
  CONSTRAINT fk_auth_provider_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE user_sessions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  session_token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_session_token_hash (session_token_hash),
  KEY idx_sessions_user_expires (user_id, expires_at),
  CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT ck_session_expires CHECK (expires_at > created_at)
) ENGINE=InnoDB;

CREATE TABLE password_reset_tokens (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_reset_token_user_expiry (user_id, expires_at),
  CONSTRAINT fk_reset_token_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;
```

### STORE

```sql
CREATE TABLE stores (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  owner_user_id BIGINT UNSIGNED NOT NULL,
  business_registration_no CHAR(10) NOT NULL,
  business_verified_at DATETIME NOT NULL,
  name VARCHAR(100) NOT NULL,
  postal_code CHAR(5) NOT NULL,
  address VARCHAR(255) NOT NULL,
  address_detail VARCHAR(255) NULL,
  latitude DECIMAL(10,7) NOT NULL,
  longitude DECIMAL(10,7) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_stores_owner (owner_user_id),
  UNIQUE KEY uk_stores_business_registration_no (business_registration_no),
  CONSTRAINT fk_store_owner FOREIGN KEY (owner_user_id) REFERENCES users(id),
  CONSTRAINT ck_store_latitude CHECK (latitude BETWEEN -90 AND 90),
  CONSTRAINT ck_store_longitude CHECK (longitude BETWEEN -180 AND 180),
  CONSTRAINT ck_store_status CHECK (status IN ('ACTIVE','INACTIVE','SUSPENDED'))
) ENGINE=InnoDB;

CREATE TABLE store_business_hours (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  day_of_week TINYINT UNSIGNED NOT NULL,
  opens_at TIME NULL,
  closes_at TIME NULL,
  is_closed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_business_hours_store_day (store_id, day_of_week),
  CONSTRAINT fk_business_hours_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_business_hours_day CHECK (day_of_week BETWEEN 1 AND 7),
  CONSTRAINT ck_business_hours_open_close CHECK (
    (is_closed = TRUE AND opens_at IS NULL AND closes_at IS NULL) OR
    (is_closed = FALSE AND opens_at IS NOT NULL AND closes_at IS NOT NULL)
  )
) ENGINE=InnoDB;

CREATE TABLE store_holidays (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  holiday_date DATE NOT NULL,
  reason VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_holiday_store_date (store_id, holiday_date),
  CONSTRAINT fk_holiday_store FOREIGN KEY (store_id) REFERENCES stores(id)
) ENGINE=InnoDB;

CREATE TABLE menus (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(50) NOT NULL,
  price BIGINT UNSIGNED NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_menu_store_name (store_id, name),
  CONSTRAINT fk_menu_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_menu_status CHECK (status IN ('ACTIVE','INACTIVE','SOLD_OUT'))
) ENGINE=InnoDB;

CREATE TABLE menu_images (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  image_url VARCHAR(2048) NOT NULL,
  ocr_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  ocr_result JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_menu_images_store (store_id),
  CONSTRAINT fk_menu_image_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_menu_image_ocr_status CHECK (ocr_status IN ('PENDING','PROCESSING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE menu_image_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  menu_image_id BIGINT UNSIGNED NOT NULL,
  menu_id BIGINT UNSIGNED NULL,
  detected_name VARCHAR(100) NOT NULL,
  detected_category VARCHAR(50) NULL,
  detected_price BIGINT UNSIGNED NULL,
  confidence DECIMAL(5,4) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  reviewed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_menu_image_items_image_status (menu_image_id, status),
  KEY idx_menu_image_items_menu (menu_id),
  CONSTRAINT fk_menu_image_item_image FOREIGN KEY (menu_image_id) REFERENCES menu_images(id),
  CONSTRAINT fk_menu_image_item_menu FOREIGN KEY (menu_id) REFERENCES menus(id),
  CONSTRAINT ck_menu_image_item_price CHECK (detected_price IS NULL OR detected_price >= 0),
  CONSTRAINT ck_menu_image_item_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  CONSTRAINT ck_menu_image_item_status CHECK (status IN ('PENDING','CONFIRMED','REJECTED')),
  CONSTRAINT ck_menu_image_item_confirmed_menu CHECK (status <> 'CONFIRMED' OR menu_id IS NOT NULL)
) ENGINE=InnoDB;
```

### SALES

```sql
CREATE TABLE sales_uploads (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  requested_by_user_id BIGINT UNSIGNED NOT NULL,
  store_id BIGINT UNSIGNED NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  source_type VARCHAR(30) NOT NULL DEFAULT 'TOSS_POS',
  original_file_name VARCHAR(255) NOT NULL,
  storage_key VARCHAR(512) NOT NULL,
  file_checksum CHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  processing_phase VARCHAR(20) NULL,
  total_row_count INT UNSIGNED NOT NULL DEFAULT 0,
  valid_row_count INT UNSIGNED NOT NULL DEFAULT 0,
  invalid_row_count INT UNSIGNED NOT NULL DEFAULT 0,
  error_code VARCHAR(50) NULL,
  error_message TEXT NULL,
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sales_upload_storage_key (storage_key),
  KEY idx_sales_upload_store_uploaded (store_id, uploaded_at),
  KEY idx_sales_upload_store_period (store_id, period_start, period_end),
  KEY idx_sales_upload_store_checksum (store_id, file_checksum),
  CONSTRAINT fk_sales_upload_user FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
  CONSTRAINT fk_sales_upload_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_sales_upload_period CHECK (period_start <= period_end),
  CONSTRAINT ck_sales_upload_status CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED')),
  CONSTRAINT ck_sales_upload_phase CHECK (
    processing_phase IS NULL OR processing_phase IN ('VALIDATING','NORMALIZING','AGGREGATING','ANALYZING')
  ),
  CONSTRAINT ck_sales_upload_row_count CHECK (total_row_count = valid_row_count + invalid_row_count)
) ENGINE=InnoDB;

CREATE TABLE sales_orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sales_upload_id BIGINT UNSIGNED NOT NULL,
  store_id BIGINT UNSIGNED NOT NULL,
  channel VARCHAR(20) NOT NULL,
  pos_order_no VARCHAR(100) NOT NULL,
  ordered_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sales_order_business_key (store_id, channel, pos_order_no, ordered_at),
  KEY idx_sales_orders_upload (sales_upload_id),
  KEY idx_sales_orders_store_ordered (store_id, ordered_at),
  CONSTRAINT fk_sales_order_upload FOREIGN KEY (sales_upload_id) REFERENCES sales_uploads(id),
  CONSTRAINT fk_sales_order_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_sales_order_channel CHECK (channel IN ('KIOSK','POS','DELIVERY'))
) ENGINE=InnoDB;

CREATE TABLE sales_order_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sales_order_id BIGINT UNSIGNED NOT NULL,
  order_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL,
  menu_name_raw VARCHAR(255) NOT NULL,
  menu_name VARCHAR(255) NOT NULL,
  menu_key VARCHAR(255) NOT NULL,
  category_raw VARCHAR(100) NULL,
  option_raw VARCHAR(500) NULL,
  quantity INT NOT NULL,
  line_price BIGINT NOT NULL,
  unit_price BIGINT NOT NULL,
  option_price BIGINT NOT NULL DEFAULT 0,
  item_discount_name VARCHAR(255) NULL,
  item_discount_amount BIGINT NOT NULL DEFAULT 0,
  order_discount_name VARCHAR(255) NULL,
  order_discount_amount BIGINT NOT NULL DEFAULT 0,
  net_amount BIGINT NOT NULL,
  is_taxable BOOLEAN NOT NULL,
  vat_amount BIGINT NOT NULL DEFAULT 0,
  item_type VARCHAR(30) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sales_item_order (sales_order_id),
  KEY idx_sales_item_order_date (order_date),
  KEY idx_sales_item_menu_key (menu_key),
  KEY idx_sales_item_type (item_type),
  CONSTRAINT fk_sales_item_order FOREIGN KEY (sales_order_id) REFERENCES sales_orders(id),
  CONSTRAINT ck_sales_item_status CHECK (status IN ('COMPLETED','CANCELED')),
  CONSTRAINT ck_sales_item_quantity CHECK (quantity <> 0),
  CONSTRAINT ck_sales_item_type CHECK (
    item_type IN ('MENU','PARKING','PREPAID_CARD','DELIVERY_FEE','PLATFORM_PLACEHOLDER','EVENT','GOODS')
  ),
  CONSTRAINT ck_sales_item_net CHECK (
    net_amount = line_price + option_price + item_discount_amount + order_discount_amount
  )
) ENGINE=InnoDB;

CREATE TABLE store_menu_categories (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  menu_key VARCHAR(255) NOT NULL,
  menu_name VARCHAR(255) NOT NULL,
  category VARCHAR(30) NOT NULL,
  source VARCHAR(20) NOT NULL,
  last_seen_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_store_menu_category_key (store_id, menu_key),
  CONSTRAINT fk_store_menu_category_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_store_menu_category_source CHECK (source IN ('OVERRIDE','POS_LATEST','KEY_MATCH','UNMAPPED'))
) ENGINE=InnoDB;

CREATE TABLE sales_daily_summaries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_date DATE NOT NULL,
  total_net_amount BIGINT NOT NULL DEFAULT 0,
  menu_net_amount BIGINT NOT NULL DEFAULT 0,
  order_count INT UNSIGNED NOT NULL DEFAULT 0,
  menu_quantity INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_daily_summary_store_date (store_id, sales_date),
  CONSTRAINT fk_daily_summary_store FOREIGN KEY (store_id) REFERENCES stores(id)
) ENGINE=InnoDB;

CREATE TABLE sales_hourly_summaries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_date DATE NOT NULL,
  hour_of_day TINYINT UNSIGNED NOT NULL,
  menu_net_amount BIGINT NOT NULL DEFAULT 0,
  order_count INT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_hourly_summary_store_date_hour (store_id, sales_date, hour_of_day),
  CONSTRAINT fk_hourly_summary_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_hourly_summary_hour CHECK (hour_of_day BETWEEN 0 AND 23)
) ENGINE=InnoDB;

CREATE TABLE sales_daily_category_summaries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_date DATE NOT NULL,
  category VARCHAR(30) NOT NULL,
  net_amount BIGINT NOT NULL DEFAULT 0,
  quantity INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_daily_category_store_date (store_id, sales_date, category),
  CONSTRAINT fk_daily_category_store FOREIGN KEY (store_id) REFERENCES stores(id)
) ENGINE=InnoDB;

CREATE TABLE sales_daily_menu_summaries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_date DATE NOT NULL,
  menu_key VARCHAR(255) NOT NULL,
  menu_name VARCHAR(255) NOT NULL,
  net_amount BIGINT NOT NULL DEFAULT 0,
  quantity INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_daily_menu_store_date (store_id, sales_date, menu_key),
  CONSTRAINT fk_daily_menu_store FOREIGN KEY (store_id) REFERENCES stores(id)
) ENGINE=InnoDB;

CREATE TABLE sales_forecasts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  target_date DATE NOT NULL,
  basis_date DATE NOT NULL,
  predicted_sales_amount BIGINT UNSIGNED NOT NULL,
  model_version VARCHAR(50) NOT NULL,
  generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_sales_forecast_store
    FOREIGN KEY (store_id)
    REFERENCES stores(id)
    ON DELETE RESTRICT
    ON UPDATE RESTRICT,
  CONSTRAINT uk_sales_forecast_store_target_model
    UNIQUE (store_id, target_date, model_version),
  CONSTRAINT ck_sales_forecast_amount
    CHECK (predicted_sales_amount >= 0)
) ENGINE=InnoDB;

CREATE TABLE analysis_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  based_on_upload_id BIGINT UNSIGNED NOT NULL,
  store_id BIGINT UNSIGNED NOT NULL,
  requested_by_user_id BIGINT UNSIGNED NOT NULL,
  analysis_type VARCHAR(30) NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  engine_version VARCHAR(50) NOT NULL,
  idempotency_key VARCHAR(100) NOT NULL,
  error_message VARCHAR(500) NULL,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_analysis_run_idempotency_key (idempotency_key),
  KEY idx_analysis_runs_store_period (store_id, period_start, period_end),
  CONSTRAINT fk_analysis_run_upload FOREIGN KEY (based_on_upload_id) REFERENCES sales_uploads(id),
  CONSTRAINT fk_analysis_run_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT fk_analysis_run_user FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
  CONSTRAINT ck_analysis_run_period CHECK (period_start <= period_end),
  CONSTRAINT ck_analysis_run_status CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE sales_analyses (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  analysis_run_id BIGINT UNSIGNED NOT NULL,
  summary_text TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sales_analysis_run (analysis_run_id),
  CONSTRAINT fk_sales_analysis_run FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id)
) ENGINE=InnoDB;

CREATE TABLE sales_ai_insights (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_analysis_id BIGINT UNSIGNED NOT NULL,
  target_month DATE NOT NULL,
  content TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  generated_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sales_ai_insight_store_month (store_id, target_month),
  KEY idx_sales_ai_insight_analysis (sales_analysis_id),
  KEY idx_sales_ai_insight_store_month_status (store_id, target_month, status),
  CONSTRAINT fk_sales_ai_insight_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT fk_sales_ai_insight_analysis FOREIGN KEY (sales_analysis_id) REFERENCES sales_analyses(id),
  CONSTRAINT ck_sales_ai_insight_status CHECK (status IN ('PENDING','GENERATING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE analysis_metrics (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sales_analysis_id BIGINT UNSIGNED NOT NULL,
  metric_code VARCHAR(50) NOT NULL,
  metric_value DECIMAL(18,4) NOT NULL,
  comparison_value DECIMAL(18,4) NULL,
  unit VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_analysis_metric_code (sales_analysis_id, metric_code),
  CONSTRAINT fk_metric_sales_analysis FOREIGN KEY (sales_analysis_id) REFERENCES sales_analyses(id)
) ENGINE=InnoDB;

CREATE TABLE menu_analysis_results (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sales_analysis_id BIGINT UNSIGNED NOT NULL,
  menu_id BIGINT UNSIGNED NULL,
  menu_name_snapshot VARCHAR(100) NOT NULL,
  sales_amount BIGINT UNSIGNED NOT NULL,
  sales_quantity INT UNSIGNED NOT NULL,
  sales_rank INT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_menu_analysis_menu (sales_analysis_id, menu_id),
  CONSTRAINT fk_menu_analysis_sales_analysis FOREIGN KEY (sales_analysis_id) REFERENCES sales_analyses(id),
  CONSTRAINT fk_menu_analysis_menu FOREIGN KEY (menu_id) REFERENCES menus(id),
  CONSTRAINT ck_menu_analysis_rank CHECK (sales_rank IS NULL OR sales_rank > 0)
) ENGINE=InnoDB;

CREATE TABLE review_analyses (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  analysis_run_id BIGINT UNSIGNED NOT NULL,
  summary_text TEXT NULL,
  keyword_result JSON NULL,
  sentiment_result JSON NOT NULL,
  engine_version VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_review_analysis_run (analysis_run_id),
  CONSTRAINT fk_review_analysis_run FOREIGN KEY (analysis_run_id) REFERENCES analysis_runs(id)
) ENGINE=InnoDB;

CREATE TABLE store_cost_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  cost_month DATE NOT NULL,
  rent_amount BIGINT UNSIGNED NOT NULL DEFAULT 0,
  labor_amount BIGINT UNSIGNED NOT NULL DEFAULT 0,
  ingredient_cost_rate DECIMAL(5,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_cost_store_month (store_id, cost_month),
  CONSTRAINT fk_cost_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_ingredient_cost_rate CHECK (ingredient_cost_rate BETWEEN 0 AND 100)
) ENGINE=InnoDB;

CREATE TABLE reviews (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  external_review_id VARCHAR(100) NOT NULL,
  rating DECIMAL(3,2) NULL,
  content TEXT NULL,
  reviewed_at DATETIME NULL,
  collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_review_store_external (store_id, external_review_id),
  KEY idx_reviews_store_reviewed_at (store_id, reviewed_at),
  CONSTRAINT fk_review_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT ck_review_rating CHECK (rating IS NULL OR rating BETWEEN 0 AND 5)
) ENGINE=InnoDB;

CREATE TABLE weather_observations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  observation_date DATE NOT NULL,
  latitude DECIMAL(10,7) NOT NULL,
  longitude DECIMAL(10,7) NOT NULL,
  weather_code VARCHAR(30) NOT NULL,
  temperature_celsius DECIMAL(5,2) NULL,
  precipitation_mm DECIMAL(8,2) NULL,
  source VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_weather_location_date (observation_date, latitude, longitude),
  CONSTRAINT ck_weather_latitude CHECK (latitude BETWEEN -90 AND 90),
  CONSTRAINT ck_weather_longitude CHECK (longitude BETWEEN -180 AND 180),
  CONSTRAINT ck_weather_precipitation CHECK (precipitation_mm IS NULL OR precipitation_mm >= 0)
) ENGINE=InnoDB;
```

### SOL, RANK, NOTI

```sql
CREATE TABLE solution_bundles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_analysis_id BIGINT UNSIGNED NOT NULL,
  target_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_solution_bundle_analysis (sales_analysis_id),
  UNIQUE KEY uk_solution_bundle_store_date (store_id, target_date),
  CONSTRAINT fk_solution_bundle_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT fk_solution_bundle_analysis FOREIGN KEY (sales_analysis_id) REFERENCES sales_analyses(id),
  CONSTRAINT ck_solution_bundle_status CHECK (status IN ('PENDING','GENERATING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE solutions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  sales_analysis_id BIGINT UNSIGNED NOT NULL,
  solution_bundle_id BIGINT UNSIGNED NOT NULL,
  solution_type VARCHAR(30) NOT NULL,
  title VARCHAR(200) NOT NULL,
  summary_text TEXT NOT NULL,
  detail_text TEXT NOT NULL,
  generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rank_no INT UNSIGNED NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_solutions_bundle_rank (solution_bundle_id, rank_no),
  KEY idx_solutions_store_created (store_id, created_at),
  CONSTRAINT fk_solution_store FOREIGN KEY (store_id) REFERENCES stores(id),
  CONSTRAINT fk_solution_sales_analysis FOREIGN KEY (sales_analysis_id) REFERENCES sales_analyses(id),
  CONSTRAINT fk_solution_bundle FOREIGN KEY (solution_bundle_id) REFERENCES solution_bundles(id),
  CONSTRAINT ck_solution_type CHECK (solution_type IN ('DAILY','MANUAL')),
  CONSTRAINT ck_solution_rank_no CHECK (rank_no > 0)
) ENGINE=InnoDB;

CREATE TABLE saved_solutions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  solution_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_saved_solution_user_solution (user_id, solution_id),
  CONSTRAINT fk_saved_solution_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_saved_solution_solution FOREIGN KEY (solution_id) REFERENCES solutions(id)
) ENGINE=InnoDB;

CREATE TABLE chat_messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  solution_bundle_id BIGINT UNSIGNED NULL,
  role VARCHAR(20) NOT NULL,
  content TEXT NOT NULL,
  evidence_json JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_chat_messages_user_created (user_id, created_at),
  KEY idx_chat_messages_bundle_created (solution_bundle_id, created_at),
  CONSTRAINT fk_chat_message_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_chat_message_solution_bundle FOREIGN KEY (solution_bundle_id) REFERENCES solution_bundles(id),
  CONSTRAINT ck_chat_message_role CHECK (role IN ('USER','ASSISTANT')),
  CONSTRAINT ck_chat_message_status CHECK (status IN ('PENDING','STREAMING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE ranking_profiles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  store_id BIGINT UNSIGNED NOT NULL,
  anonymous_nickname VARCHAR(50) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ranking_profile_store (store_id),
  UNIQUE KEY uk_ranking_profile_nickname (anonymous_nickname),
  CONSTRAINT fk_ranking_profile_store FOREIGN KEY (store_id) REFERENCES stores(id)
) ENGINE=InnoDB;

CREATE TABLE ranking_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  comparison_start DATE NOT NULL,
  comparison_end DATE NOT NULL,
  calculated_at DATETIME NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ranking_snapshot_periods (period_start, period_end, comparison_start, comparison_end),
  CONSTRAINT ck_ranking_period CHECK (period_start <= period_end),
  CONSTRAINT ck_ranking_comparison_period CHECK (comparison_start <= comparison_end),
  CONSTRAINT ck_ranking_snapshot_status CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED'))
) ENGINE=InnoDB;

CREATE TABLE ranking_entries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ranking_snapshot_id BIGINT UNSIGNED NOT NULL,
  ranking_profile_id BIGINT UNSIGNED NOT NULL,
  rank_no INT UNSIGNED NOT NULL,
  growth_rate DECIMAL(10,4) NOT NULL,
  selected_period_sales BIGINT UNSIGNED NOT NULL,
  comparison_period_sales BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ranking_entry_snapshot_profile (ranking_snapshot_id, ranking_profile_id),
  KEY idx_ranking_entries_snapshot_rank (ranking_snapshot_id, rank_no),
  CONSTRAINT fk_ranking_entry_snapshot FOREIGN KEY (ranking_snapshot_id) REFERENCES ranking_snapshots(id),
  CONSTRAINT fk_ranking_entry_profile FOREIGN KEY (ranking_profile_id) REFERENCES ranking_profiles(id),
  CONSTRAINT ck_ranking_entry_rank CHECK (rank_no > 0)
) ENGINE=InnoDB;

CREATE TABLE notifications (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  notification_type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  scheduled_at DATETIME NULL,
  sent_at DATETIME NULL,
  read_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_notifications_user_read_created (user_id, read_at, created_at),
  CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE notification_preferences (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  solution_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  sales_upload_reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  ranking_change_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_notification_preference_user (user_id),
  CONSTRAINT fk_notification_preference_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;
```