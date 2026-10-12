## 입력 검증 오류 응답 규칙

- DTO·쿼리 파라미터의 단순 입력 검증 실패는 `400 Bad Request`로 응답한다.
- 이미 사용 중인 이메일·휴대폰 번호·사업자등록번호처럼 특정 입력 필드의 중복은 `409 Conflict`로 응답한다.
- 단순 입력 검증 `400`과 필드 중복 `409`의 `data.fieldErrors`는 아래 형식을 사용한다. 여러 필드가 동시에 잘못된 경우 배열에 모두 포함한다.

```json
{
  "message": "입력값을 확인해 주세요.",
  "data": {
    "fieldErrors": [
      {
        "field": "email",
        "message": "올바른 이메일 형식을 입력해 주세요."
      }
    ]
  }
}
```

- `400`은 JSON 본문 형식 자체가 잘못되었거나 요청을 해석할 수 없는 경우에는 `fieldErrors` 없이, DTO·쿼리 파라미터의 단순 입력 검증 실패에는 `fieldErrors`와 함께 반환한다. `410`은 토큰·인증 결과 만료, `500`·`502`는 서버·외부 연동 오류에 사용한다.

# API 정의서

---

# API 설계 공통 원칙

## HTTP 메서드 사용 원칙

- **GET**: 상태를 변경하지 않고 캐시·재시도가 가능한 멱등한 조회에 사용한다. 목록/상세 조회, 업로드·분석 진행 상태 폴링, 챗봇의 내부 지표 조회 툴이 모두 GET이다.
- **POST**: 새 리소스를 생성하거나(회원가입, 매출 업로드, 솔루션 저장), 부수효과가 있어 멱등하지 않은 동작(로그인/로그아웃, 인증코드 발송·검증, AI 호출, 챗봇 메시지 전송)에 사용한다.
- **PATCH**: 기존 리소스의 일부 필드만 선택적으로 수정할 때 사용한다(비밀번호, 매장 정보, 메뉴 정보, 비밀번호 재설정 등).
- **PUT**: V2 월별 비용처럼 하나의 월 리소스에 필요한 모든 필드를 함께 저장하거나 전체 교체할 때 사용한다. 같은 매장·월에 반복 요청해도 행을 중복 생성하지 않는다.
- **DELETE**: 리소스 삭제에 사용한다(메뉴 단건 삭제, 저장 솔루션 다건 삭제).

## GET·DELETE 요청 파라미터 기준

- **GET·DELETE 요청 본문은 사용하지 않는다.** 시트의 요청 본문 칸은 비워 둔다.
- URL의 `{id}` 형태 값은 **경로 파라미터**다. 예: `/v1/sales/uploads/{uploadId}/status`의 `uploadId`.
- 조회 조건·목록 범위는 **쿼리 파라미터**로 URL 뒤에 붙인다. 예: `/v1/addresses/search?query=강남역&size=10`.
- 쿼리 파라미터가 없는 GET·DELETE API는 세션 쿠키와 URL 경로만 사용한다.

### 정의된 쿼리 파라미터

- `GET /v1/addresses/search`: `query`(필수), `cursor`(선택), `size`(선택, 기본 10·최대 10)
- `GET /v1/sales/uploads`: `page`(선택, 기본 1·최대 5), `size`(선택, 10 고정)
- `GET /internal/v1/sales/summary`, `categories`, `review-summaries`: `storeId`·`period`·`startDate`·`endDate`
- `GET /internal/v2/sales/profit-analyses`: `storeId`·`period`·`startDate`·`endDate`
- `GET /internal/v1/sales/hourly-profiles`: 위 값과 `dayOfWeek`(선택)
- `GET /internal/v1/sales/forecasts`: `storeId`·`targetDate`
- `GET /v1/sales/analyses`, `GET /v2/sales/profit-analyses`, `GET /v3/sales/analyses`: `periodType`(필수), `startDate`·`endDate`(CUSTOM일 때 필수)
- `GET /v1/saved-solutions`: `cursor`(선택), `size`(선택, 기본 10·최대 20)
- `DELETE /v1/saved-solutions`: `savedIds`(필수, 다중 값)
- `GET /v1/notifications`: `readStatus`·`cursor`(선택), `size`(선택, 기본 20·최대 50)
- `GET /v2/auth/toss/callback`: `code`·`state`, `error`(실패 시)
- `GET /v2/rankings/growth`: `period`(선택)
- `GET /v3/sales/calendar`: `month`(필수)

## 인증 방식

로그인 성공 시 발급되는 **세션 쿠키** 기반 인증을 기본으로 한다. 세션이 아직 없는 회원가입 2단계(매장 정보 등록)에서만 예외적으로 1단계에서 발급받은 `Signup-Token` 헤더로 사용자를 식별한다 — 미완료 계정 상태로 정식 세션을 먼저 내주면 로그인 가능한 상태가 되어버리는 문제를 피하기 위함이다.

## 상태 코드 및 에러 응답 구조

전체 API가 공통으로 쓰는 HTTP 상태 코드의 의미는 다음과 같다.

| 상태 코드 | 의미 |
| --- | --- |
| 200 | 요청 처리·조회 성공. 데이터 없음·분석 실패 같은 업무 상태는 본문의 status(EMPTY·FAILED 등)로 구분 |
| 201 | 새 리소스 생성 성공 |
| 202 | 요청 접수 성공. 비동기 작업이 시작됐으며 즉시 결과는 없음 |
| 204 | 성공. 응답 본문 없음 |
| 302 | 외부 인증 완료 후 FE 화면으로 리다이렉트(Location 헤더 사용) |
| 400 | 요청 형식 또는 값이 잘못됨 |
| 401 | 로그인(세션 인증) 필요 |
| 403 | 인증은 됐지만 해당 리소스 접근 권한 없음, 또는 상태 변경 요청의 CSRF 토큰 검증 실패 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 현재 상태와 충돌(중복 가입·중복 작업 등) |
| 410 | 인증 코드·임시 토큰 등 리소스가 만료됨 |
| 413 | 업로드 파일 용량 초과 |
| 415 | 지원하지 않는 파일 형식 또는 Media Type |
| 416 | 조회 가능한 매출 기간 범위를 벗어남 |
| 422 | 요청 형식은 유효하지만 파일 스키마 불일치처럼 요구사항상 처리할 수 없음 |
| 429 | 짧은 시간에 요청이 너무 많음. 재시도 가능 시점은 retryAfterSeconds로 안내 |
| 500 | 서버 또는 AI 처리 중 예상하지 못한 내부 오류 |
| 502 | 국세청·주소 검색 등 외부 제공자 연동 실패 |
| 504 | AI 처리 시간 초과 |

일반 성공 응답은 `{"message":"안내 문구","data":{...}}` 형태를 기본으로 하며, `COMPLETED`·`EMPTY`·`FAILED`·`PROCESSING`·`INSUFFICIENT_DATA` 같은 업무 상태가 필요한 API만 `status`를 최상위에 추가한다. 성공 데이터는 모두 `data` 안에 넣고 최상위에는 `message`, `status`와 페이징 커서 등 응답 제어 값만 둔다. 실패 응답은 기본적으로 `{"message":"사용자에게 보여줄 한글 안내 문구","data":null}` 형태를 따르고, 상황에 따라 `failReason`(예: `INSUFFICIENT_HISTORY`), `status`(예: `PROCESSING`/`FAILED`), `retryAfterSeconds`처럼 클라이언트가 분기 처리할 수 있는 부가 필드를 함께 내려주는 확장형을 쓴다. `204`와 `302`는 응답 본문이 없다. 현재는 HTTP status 코드 + message 조합만으로 에러를 구분하고 있고, 별도의 숫자/영문 `errorCode` 체계는 아직 정의하지 않았다 — 다국어 지원 등이 필요해지기 전까지는 이 정도로 충분하다고 판단했다.

- 요청 본문에 API별로 정의되지 않은 필드가 포함되어도 422로 거절하지 않고 무시한다. BE와 AI의 독립 배포 중 한쪽이 필드를 먼저 추가해도 기존 계약이 중단되지 않게 한다.
- 기본적으로 비율·증감률은 소수로 반환한다(예: 62%는 `0.62`). 단, 성장 랭킹 API의 `growthRate`는 기존 화면 형식에 맞춰 소수 첫째 자리 퍼센트 숫자(예: `28.5`)로 반환하며, FE는 `%`만 붙인다.

## 페이징 · 정렬 · 필터링 정책

- 주소 검색, 마이 솔루션 저장 목록(SOL-03), 알림 목록(NOTI-01), 챗봇 대화 내역(SOL-05)은 **cursor 기반** 페이징을 적용했다. 주소 검색은 기본·최대 10개, 저장 솔루션은 기본 10개·최대 20개, 알림은 기본 20개·최대 50개, 챗봇 대화 내역은 기본 20개를 반환한다.
- 기간이 있는 조회(월별 업로드 SALES-01, 기간별 분석 SALES-04)는 `targetMonth`/`period` 파라미터로 필터링한다.
- 정렬은 대부분 최신순·랭킹순으로 고정했고 별도 `sort` 파라미터는 두지 않았다 — 1인 소상공인 매장을 대상으로 한 MVP 특성상 정렬 옵션을 노출할 실익이 낮다고 판단했기 때문이며, 추후 필요해지면 파라미터를 추가하는 방식으로 확장 가능하다.

---

# AUTH · 인증/계정 (AU)

## AU-00 · GET `/v1/auth/csrf-token`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

브라우저 기반 세션 인증에서 상태 변경 요청을 보호하기 위한 CSRF 토큰을 발급한다. 응답 본문은 없으며 `Set-Cookie` 헤더로 JavaScript가 읽을 수 있는 `XSRF-TOKEN` 쿠키를 내려준다.

**클라이언트 처리**

앱 시작 시 한 번 호출한다. 이후 `POST`·`PATCH`·`PUT`·`DELETE` 요청마다 쿠키의 값을 `X-XSRF-TOKEN` 헤더에 넣어 전송한다. `GET`·`HEAD`·`OPTIONS` 요청에는 토큰 헤더가 필요 없다.

**응답**

| status | body |
| --- | --- |
| 204 | 응답 본문 없음. `Set-Cookie: XSRF-TOKEN=...` 포함 |

**공통 오류**

상태 변경 요청에서 토큰 쿠키 또는 `X-XSRF-TOKEN` 헤더가 없거나 값이 일치하지 않으면 아래 `403`을 반환한다.

```json
{
  "message": "CSRF 토큰이 유효하지 않습니다.",
  "data": null
}
```

---

## AU-01 · POST `/v1/auth/login`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
email (필수) password (필수)
```

**설명**

이메일과 비밀번호를 전달하여 로그인한다. 로그인 실패 응답은 이메일 존재 여부와 관계없이 동일한 401을 반환하며, FE는 이메일 입력값을 유지하고 비밀번호 입력값만 초기화한다. 성공 시 Set-Cookie 헤더로 세션 쿠키를 발급한다. 계정별로 정규화 이메일 기준 최근 15분 실패 횟수를 집계해 5~9회는 30초, 10~14회는 1분, 15~19회는 5분, 20회 이상은 15분간 제한한다. 해당 단계에 도달한 실패 응답은 401이며 제한 중 후속 요청은 429다. 제한 중 요청은 실패 횟수에 포함하지 않고 제한 시간을 연장하지 않는다. IP별 최근 10분 30회 실패 후의 요청도 429로 제한하며, 계정/IP 제한은 독립적으로 적용한다. 로그인 성공 시 계정 실패 이력만 초기화하고 IP 실패 이력은 유지한다.

**설계 근거**

로그인은 세션이라는 새 리소스를 생성하는 부수효과가 있고 매번 같은 결과를 보장하는 멱등한 동작이 아니라서 GET이 아닌 POST를 사용했다. 이메일과 비밀번호만 받는 최소한의 요청 본문으로 설계했다. 여러 BE 인스턴스에서 같은 제한 상태를 적용하기 위해 HMAC 처리한 이메일·IP 키와 MySQL named lock을 사용하며, 원문 이메일·IP는 저장하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"로그인에 성공했습니다.","data":{"user":{"id":1,"email":"example@email.com"}}}` |
| 401 | `{"message":"이메일 또는 비밀번호가 올바르지 않습니다.","data":null}` |
| 429 | `{"message":"요청이 너무 많습니다. 잠시 후 다시 시도해주세요.","data":null,"retryAfterSeconds":30}`. 계정 또는 IP 제한 초과 시 원인을 구분하지 않고 반환한다. `retryAfterSeconds`는 다음 요청 가능 시점까지의 초 단위 값이다. |

## AU-01 · POST `/v1/auth/logout`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
(없음, 세션 쿠키 필요)
```

**설명**

로그아웃 처리, 서버 세션 삭제 및 세션 쿠키 만료

**설계 근거**

로그아웃은 서버 세션 삭제라는 상태 변경을 일으키므로 POST를 사용했다(GET으로 상태를 바꾸면 CSRF에 취약해질 수 있어 지양). 세션 쿠키만으로 사용자를 식별할 수 있어 별도 요청 본문이 필요 없고, 돌려줄 데이터도 없어 204로 응답한다.

**응답**

| status | body |
| --- | --- |
| 204 | `응답 본문 없음.` |

---

## AU-02 · POST `/v1/auth/signup/account`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
phone (필수, 010으로 시작하는 11자리)
email (필수)
password (필수)
passwordConfirm (필수)
agreements.termsOfService (필수, boolean)
agreements.termsOfServiceVersion (필수)
agreements.privacyPolicy (필수, boolean)
agreements.privacyPolicyVersion (필수)
```

**설명**

회원가입 1단계의 휴대폰 번호, 이메일, 비밀번호와 FE에 고정 노출된 필수 약관의 동의 여부·버전을 검증하고 가입 정보를 임시 저장한다. 이 단계에서는 `users` 계정을 생성하지 않는다. 성공 시 ST-01 매장·사업자 정보 등록에 사용할 발급 시각부터 1시간 동안 유효한 만료형 `signupToken`을 반환하며, 응답의 `expiresAt`은 해당 만료 시각이다.

**설계 근거**

FR-AUTH-015에 따라 AU-02 완료만으로 정식 계정을 생성하지 않는다. 검증된 가입 초안을 임시 리소스로 생성하므로 POST와 201을 사용하며, ST-01 성공 시 사용자와 매장을 하나의 트랜잭션으로 최종 생성한다. 이메일·휴대폰 중복 여부는 최종 생성 시 다시 검증한다.

**응답**

| status | body |
| --- | --- |
| 201 | `{"message":"가입 정보가 임시 저장되었습니다.","data":{"signupToken":"signup_abc123","expiresAt":"2026-09-08T15:30:00+09:00"}}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"password","message":"비밀번호는 8~20자이며 대문자·소문자·숫자·특수문자를 각각 포함해야 합니다."},{"field":"agreements.termsOfService","message":"이용약관에 동의해 주세요."}]}}` |
| 409 | `{"message":"이미 가입된 이메일입니다.","data":{"fieldErrors":[{"field":"email","message":"이미 사용 중인 이메일입니다."}]}}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"passwordConfirm","message":"비밀번호와 일치하지 않습니다."}]}}` |

---

## AU-05 · GET `/v1/users/me`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

세션 쿠키로 인증된 사용자의 마이페이지 정보를 조회한다. 이메일과 휴대폰 번호는 조회 전용이며, 대표 매장명을 함께 반환한다.

**설계 근거**

별도 사용자 ID를 받지 않고 세션 사용자와 연결된 `users`, `stores`만 조회해 다른 사용자의 정보 접근을 차단한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"user":{"id":1,"email":"example@email.com","phone":"01012345678","storeName":"맴매카페"}}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## AU-05 · DELETE `/v1/users/me`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
(없음, 세션 쿠키 필요)
```

**설명**

회원탈퇴를 확정한다. 세션 사용자 기준으로 `users`의 상태와 `deleted_at`을 탈퇴 상태로 변경하고 모든 로그인 세션을 종료한다. 법령상 보관이 필요한 데이터는 보관 정책에 따라 분리하고, 즉시 삭제 가능한 개인정보는 삭제 또는 비식별화한다.

**설계 근거**

계정 리소스의 사용을 종료하는 동작이므로 DELETE를 사용한다. 사용자 상태 변경과 전체 세션 종료는 하나의 트랜잭션으로 처리하며, 중간 단계가 실패하면 기존 로그인 상태와 계정 정보를 유지한다.

**응답**

| status | body |
| --- | --- |
| 204 | 응답 본문 없음. 세션 쿠키 만료 |
| 400 | `{"message":"현재 비밀번호가 일치하지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 500 | `{"message":"회원탈퇴에 실패했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

## AU-04 · PATCH `/v1/users/me/password`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
currentPassword (필수)
newPassword (필수)
confirmPassword (필수)
```

**설명**

현재 비밀번호를 검증한 뒤 새 비밀번호로 변경한다. 새 비밀번호는 기존 비밀번호와 달라야 하고 비밀번호 정책을 충족하며 확인값과 일치해야 한다. 변경 성공 시 현재 요청에 사용된 세션은 유지하고 다른 기기의 세션은 모두 종료한다.

**설계 근거**

비밀번호 필드만 변경하므로 PATCH를 사용한다. 비밀번호 변경과 다른 세션 폐기는 하나의 트랜잭션으로 처리한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"비밀번호가 변경되었습니다.","data":{"revokedSessionCount":2}}` |
| 400 | `{"message":"현재 비밀번호가 일치하지 않습니다.","data":null}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"newPassword","message":"비밀번호 정책을 확인해 주세요."},{"field":"confirmPassword","message":"새 비밀번호와 일치하지 않습니다."}]}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## AU-03 · POST `/v1/auth/password-reset/email`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
email (필수)
```

**설명**

비밀번호 찾기 요청을 받아 일회용 비밀번호 재설정 링크를 발송한다. 실제 재설정 링크는 가입된 이메일에만 발송하며, 등록 여부를 노출하지 않기 위해 응답 메시지는 가입 여부와 관계없이 동일하게 반환한다. 이메일은 정규화 기준 최근 2분에 1회, 최근 24시간에 최대 5회 요청할 수 있고, 요청 IP별 최근 1시간 최대 20회로 제한한다. 제한 초과 시 토큰 저장·메일 발송 없이 429와 `retryAfterSeconds`를 반환한다. 서버는 원문 이메일·IP 대신 요청 제한용 HMAC 해시와 비밀번호 재설정 토큰 해시, 만료 시각, 사용 시각만 저장한다.

**응답**

| status | body |
| --- | --- |
| 202 | `{"message":"입력한 이메일로 비밀번호 재설정 안내를 보냈습니다.","data":null}` |
| 400 | `{"message":"이메일 형식이 올바르지 않습니다.","data":null}` |
| 429 | `{"message":"요청이 너무 많습니다. 잠시 후 다시 시도해주세요.","data":null,"retryAfterSeconds":120}`. 이메일 또는 요청 IP의 제한 초과 시 반환하며, `retryAfterSeconds`는 다음 요청 가능 시점까지의 초 단위 값이다. |

---

## AU-03 · PATCH `/v1/auth/password-reset`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
token (필수, 이메일 링크의 일회용 토큰)
newPassword (필수)
confirmPassword (필수)
```

**설명**

이메일 링크의 토큰이 유효하고 만료·사용되지 않은 경우에만 새 비밀번호로 변경한다. 변경 성공 시 토큰을 즉시 사용 처리하고 기존 로그인 세션을 모두 종료한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"비밀번호가 변경되었습니다.","data":null}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"newPassword","message":"비밀번호 정책을 확인해 주세요."},{"field":"confirmPassword","message":"새 비밀번호와 일치하지 않습니다."}]}}` |
| 410 | `{"message":"비밀번호 재설정 링크가 만료되었거나 이미 사용되었습니다.","data":null}` |

---

## ST-01 · POST `/v1/auth/signup/business`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
Header: Signup-Token (필수)
storeName (필수)
businessRegNumber (선택, 숫자 10자리)
businessVerificationId (선택, 번호를 입력할 때 함께 전달)
postalCode (필수)
address (필수, 기본 주소)
addressDetail (선택)
businessHours (필수, 요일별 영업시간 배열)
- dayOfWeek (필수, MONDAY~SUNDAY)
- isClosed (필수, boolean)
- openTime, closeTime (isClosed=false일 때 필수, HH:mm, 10분 단위)
- openTime과 closeTime이 같으면 24시간 영업(00:00~24:00)
- closeTime이 openTime보다 이르면 익일 영업으로 처리하며, closeTime은 06:00 이하여야 함
```

**설명**

회원가입 최종 단계다. AU-02 일반 가입 또는 AU-10 토스 가입에서 발급한 `signupToken`의 가입 초안·인증·약관 동의 상태와 사업자등록번호 인증 결과, 매장 입력값을 다시 검증한다. MVP에서는 주소 검색 결과의 우편번호와 기본 주소만 저장한다. 위도·경도는 V2에서 카카오 로컬 API 지오코딩 결과로 저장하며, 날씨·주변상권 분석에 활용한다. 영업시간은 요일별로 저장하며, 가입 화면에서는 동일한 시간을 모든 요일에 적용한 뒤 필요한 경우에만 요일별 시간을 수정한다. 매주 휴무는 해당 요일의 `isClosed=true`으로 표현하고, 매월 휴무 정책은 지원하지 않는다. 일반 가입은 `users`, `stores`, `store_business_hours`, 기본 `notification_preferences`를, 토스 가입은 여기에 `user_auth_providers` 연결을 더해 하나의 트랜잭션으로 생성한다. 성공 후 자동 로그인하지 않으며 AU-01 로그인 화면으로 이동한다.

**설계 근거**

FR-AUTH-015와 FR-STORE-009에 따라 AU-02에서는 정식 계정을 만들지 않고 ST-01 성공 시 계정과 매장을 함께 생성한다. 일부 저장 후 실패하는 상태를 막기 위해 전체 생성을 하나의 트랜잭션으로 처리한다. `signupToken`은 발급 시각부터 1시간 동안만 유효하다. 사업자등록번호와 `businessVerificationId`는 둘 다 생략할 수 있으며, 하나만 전달하면 422를 반환한다. 번호를 입력하면 인증 결과가 해당 번호와 일치하고 발급 후 10분 이내이며 아직 사용되지 않은 경우에만 회원가입을 허용한다. 회원가입 성공 시 해당 인증 결과의 `used_at`을 기록하여 즉시 재사용을 막는다. 만료된 `signupToken` 또는 사업자 인증 결과로 요청하면 410을 반환한다.

**응답**

| status | body |
| --- | --- |
| 201 | `{"message":"회원가입이 완료되었습니다.","data":{"user":{"id":1,"email":"example@email.com"},"store":{"id":1,"storeName":"맴매카페"},"next":"LOGIN"}}` |
| 409 | `{"message":"이미 등록된 정보가 있습니다.","data":{"fieldErrors":[{"field":"email","message":"이미 사용 중인 이메일입니다."}]}}` |
| 410 | `{"message":"회원가입 또는 사업자 인증 정보가 만료되었습니다.","data":null}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"businessVerificationId","message":"사업자 인증 결과가 유효하지 않거나 만료되었습니다."}]}}` |
| 500 | `{"message":"회원가입 정보를 저장하지 못했습니다. 다시 시도해주세요.","data":null}` |

---

## ST-01, ST-02 · GET `/v1/addresses/search`

- **방향**: FE → BE → 행정안전부 도로명주소 검색 API
- **버전**: v1

**요청 값**

```
query (필수, 도로명·지번·건물명 검색어)
cursor (선택)
size (선택, 기본 10, 최대 10)
```

**설명**

회원가입 또는 매장 수정 화면에서 행정안전부 도로명주소 검색 API를 통해 주소 검색 결과를 조회한다. MVP 응답은 우편번호·도로명주소·지번주소만 제공하며, 상세주소는 사용자가 별도로 입력한다. V2에서는 선택한 기본 주소를 카카오 로컬 API로 지오코딩해 매장 위도·경도를 저장한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"addresses":[{"postalCode":"06236","roadAddress":"서울특별시 강남구 테헤란로 123","jibunAddress":"서울특별시 강남구 역삼동 123"}],"nextCursor":null}}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"query","message":"주소 검색어를 입력해 주세요."}]}}` |
| 502 | `{"message":"주소 검색 서비스를 이용할 수 없습니다. 다시 시도해주세요.","data":null}` |

---

## ST-01 · POST `/v1/auth/business-verifications`

- **방향**: FE → BE → 국세청 상태 조회 API
- **버전**: v1

**요청 값**

```
businessRegNumber (필수, 숫자 10자리)
```

**설명**

사업자등록번호 형식과 사업자 상태를 확인한다. 성공하면 인증 결과를 `business_verifications`에 저장하고, 회원가입 완료 또는 ST-02의 번호 등록·변경 요청에서 사용할 숫자형 `businessVerificationId`와 만료 시각을 반환한다. 인증 결과는 발급 후 10분 동안만 유효하며, 회원가입 또는 매장 정보 수정에서 한 번만 사용할 수 있다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"business_number_verification_success","data":{"businessVerificationId":1,"expiresAt":"2026-09-17T12:10:00+09:00"}}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"businessRegNumber","message":"사업자등록번호는 숫자 10자리여야 합니다."}]}}` |
| 409 | `{"message":"business_number_already_exists","data":{"fieldErrors":[{"field":"businessRegNumber","message":"이미 등록된 사업자등록번호입니다."}]}}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"businessRegNumber","message":"사업자등록번호를 확인해 주세요."}]}}`
사업자 상태 오류(휴업·폐업·미등록) |
| 502 | `{"message":"business_verification_failed","data":null}` |

---

## ST-02 · GET `/v1/stores/me`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

본인 매장의 사업자등록번호, 매장명, 주소와 요일별 영업시간 7건을 조회한다. `businessHours[].isClosed=true`인 요일은 매주 반복되는 휴무일이며, 해당 요일의 `openTime`·`closeTime`은 `null`이다. 월간·격주 휴무 규칙은 MVP에서 지원하지 않는다. 사업자등록번호는 기존 마스킹 표시 형식으로 반환하며 전체 번호는 응답에 포함하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"store":{"id":1,"businessRegNumber":"123-45-*****","storeName":"맴매카페","address":{"postalCode":"06236","roadAddress":"서울특별시 강남구 테헤란로 123","addressDetail":"2층"},"businessHours":[{"dayOfWeek":"MONDAY","isClosed":false,"openTime":"09:00","closeTime":"22:00"},{"dayOfWeek":"SUNDAY","isClosed":true,"openTime":null,"closeTime":null}]}}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"매장 정보를 찾을 수 없습니다.","data":null}` |

---

## ST-02 · PATCH `/v1/stores/me`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
storeName (선택)
address.postalCode (선택)
address.roadAddress (선택)
address.addressDetail (선택)
businessRegNumber (선택, 숫자 10자리; 등록·변경 시 businessVerificationId와 함께 전달)
businessVerificationId (선택, 사업자번호 등록·변경 시 필수)
businessHours (선택, 요일별 영업시간 7개 배열)
businessHours[].dayOfWeek (필수, MONDAY ~ SUNDAY)
businessHours[].isClosed (필수, boolean)
businessHours[].openTime (영업일일 때 필수, HH:mm)
businessHours[].closeTime (영업일일 때 필수, HH:mm)
```

**설명**

본인 매장의 매장명, 주소, 요일별 영업시간, 사업자등록번호를 부분 수정한다. 사업자번호와 인증 ID를 모두 생략하면 기존 번호를 유지한다. 번호가 없는 매장은 번호를 새로 등록할 수 있고, 기존 번호는 새 인증을 거친 경우에만 변경할 수 있다. 두 필드 중 하나만 보내면 400으로 거절하며 번호 삭제는 지원하지 않는다. 인증 ID가 존재하고 요청 번호와 일치하며 발급 후 10분 이내이고 아직 사용되지 않은 경우에만 변경을 허용한다. 인증 결과 사용 처리, 사업자 번호·인증 시각 변경과 매장 정보 수정은 하나의 트랜잭션으로 처리한다. 번호가 다른 매장에 이미 등록되어 있으면 409를 반환한다. 전체 사업자등록번호는 응답에 포함하지 않는다. 영업시간을 수정하면 월요일부터 일요일까지 7개를 함께 전달하며, `isClosed=true`인 요일은 매주 반복 휴무로 저장한다. 월간·격주 휴무 규칙은 MVP에서 지원하지 않는다.

**설계 근거**

변경된 필드만 받는 부분 수정이므로 PATCH를 사용한다. 사업자등록번호 변경과 인증 결과의 사용 처리는 매장 정보 변경과 원자적으로 반영하며, 하나라도 검증 또는 저장에 실패하면 기존 정보를 유지한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"수정되었습니다.","data":{"store":{"id":1,"storeName":"수정된 매장명","address":{"postalCode":"06236","roadAddress":"서울특별시 강남구 테헤란로 123","addressDetail":"3층"},"businessHours":[{"dayOfWeek":"MONDAY","isClosed":false,"openTime":"09:00","closeTime":"22:00"},{"dayOfWeek":"SUNDAY","isClosed":true,"openTime":null,"closeTime":null}]}}}` |
| 400 | `{"message":"변경할 매장 정보가 없습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"매장 정보를 찾을 수 없습니다.","data":null}` |
| 409 | `{"message":"이미 등록된 사업자등록번호입니다.","data":{"fieldErrors":[{"field":"businessRegNumber","message":"이미 등록된 사업자등록번호입니다."}]}}` |
| 410 | `{"message":"사업자 인증 결과가 만료되었습니다.","data":null}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"businessVerificationId","message":"사업자 인증 결과가 유효하지 않습니다. (인증 결과가 없거나 요청 번호와 불일치하거나 이미 사용됨)"}]}}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"storeName","message":"매장명을 확인해 주세요."},{"field":"address","message":"주소를 확인해 주세요."},{"field":"businessHours","message":"요일별 영업시간을 확인해 주세요."}]}}` |
| 500 | `{"message":"매장 정보를 저장하지 못했습니다. 기존 정보는 유지됩니다.","data":null}` |

---

# SALES · 매출 데이터 업로드 (SALES)

## SALES-01 · POST `/v1/sales/uploads`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
multipart/form-data
file (필수, 토스 POS 매출리포트 .xlsx, 1개, 최대 10MB)
```

**설명**

토스 POS 매출리포트를 비동기로 접수한다. 주문 플랫폼은 요청에서 선택하지 않고 파일 내부의 주문채널 `키오스크/포스/배달`을 `KIOSK/POS/DELIVERY`로 변환한다. 서버는 확장자·용량·MIME·파일 시그니처를 기본 검증하고 원본 파일을 비공개 저장소에 저장한 뒤 `sales_uploads`와 `analysis_runs`를 생성한다.

동일 체크섬 또는 기존 기간과 겹치는 파일도 새 업로드 이력으로 허용한다. 파일 검증이 성공하면 하나의 트랜잭션에서 새 파일 커버리지의 기존 주문 항목을 삭제하고 새 행을 삽입한 뒤 집계를 재계산한다. 실제로 동일한 메뉴 행이 여러 건일 수 있으므로 행 단위 중복 제거는 하지 않는다. 검증 또는 교체 실패 시 기존 정상 데이터와 결과는 유지한다.

**설계 근거**

32,199행의 다개월 파일 검증·정규화·집계와 AI 호출은 요청 시간 안에 끝난다고 보장할 수 없으므로 접수 결과만 `202 Accepted`로 반환한다. FE는 `uploadId`로 상태 조회 API를 폴링한다.

**응답**

| status | body |
| --- | --- |
| 202 | `{"message":"매출 파일 업로드를 접수했습니다.","status":"PENDING","data":{"uploadId":12,"analysisRunId":34,"processingPhase":null}}` |
| 400 | `{"message":"업로드 요청값이 올바르지 않습니다.","data":null}` |
| 413 | `{"message":"파일 크기가 10MB를 초과했습니다.","data":null}` |
| 415 | `{"message":"토스 POS .xlsx 파일만 업로드할 수 있습니다.","data":null}` |
| 500 | `{"message":"업로드 접수에 실패했습니다. 기존 데이터는 유지됩니다.","data":null}` |

---

## SALES-01 · GET `/v1/sales/uploads`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: page (선택, 기본 1, 1~5), size (선택, 10 고정)

**설명**

본인 매장의 데이터 연결 상태와 업로드 이력을 최신순으로 조회한다. 페이지 번호 방식으로 한 페이지에 10개씩, 최대 5페이지까지 제공한다. 동일·기간 중첩 파일도 각각의 업로드 이력으로 표시하며 행 중복 제거를 하지 않으므로 `duplicateRecordCount`는 반환하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"connection":{"lastUploadedAt":"2026-09-08T14:20:00+09:00","totalAppliedRecordCount":32199,"latestStatus":"PROCESSING"},"items":[{"uploadId":12,"fileName":"toss-pos-sales.xlsx","sourceType":"TOSS_POS","periodStart":"2025-12-08","periodEnd":"2026-06-01","uploadedAt":"2026-09-08T14:20:00+09:00","totalRowCount":32199,"appliedRecordCount":0,"status":"PROCESSING","processingPhase":"VALIDATING","aiInsightStatus":"PENDING","failReason":null}],"page":1,"size":10,"totalPages":1,"totalCount":1}}` |
| 200 | `{"message":"업로드 이력이 없습니다.","data":{"items":[],"page":1,"size":10,"totalPages":0,"totalCount":0}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## SALES-01 · POST `/internal/v1/ai/forecast/batch`

- **방향**: BE → AI
- **버전**: v1

**요청 값**

```
storeId (필수)
uploadId (필수)
analysisRunId (필수)
forecastStartDate (필수, dailySales 마지막 날짜 + 1일, YYYY-MM-DD)
dailySales (필수, 날짜 오름차순이며 누락 없이 연속된 학습 데이터 배열)
dailySales[].date (필수, YYYY-MM-DD)
dailySales[].amount (필수, 비메뉴를 제외한 menu_net_amount, 무매출 날짜는 0)
dailySales[].orderCnt (필수, 유효 주문 수)
```

**설명**

BE가 검증된 집계 데이터를 구성해 예측 모델을 호출한다. `forecastStartDate`는 `dailySales` 마지막 날짜의 다음 날이어야 하며, 다르면 422를 반환한다. `dailySales`는 날짜 오름차순으로 하루도 빠짐없이 연속되어야 하고 매출 없는 날도 `amount=0`으로 포함한다. `amount`는 주차권·선불카드 충전 등 비메뉴를 제외한 `menu_net_amount`, `orderCnt`는 유효 주문 수다. 원본 파일과 개별 거래 전체는 전달하지 않는다.

예측은 `forecastStartDate`부터 35일이며 월 경계를 넘어갈 수 있다. 예를 들어 마지막 학습 날짜가 2026-08-31이면 2026-09-01부터 2026-10-05까지 반환한다. 다음 업로드의 예측과 최대 7일이 겹칠 수 있으며, 같은 날짜는 최신 업로드 예측으로 교체한다. 업로드 시점보다 앞선 날짜의 예측도 응답·저장할 수 있지만 화면과 솔루션에서는 KST 오늘 이후 날짜만 사용한다.

예측 가능 조건은 예측 시작 달의 직전 두 달이 모두 완전한 월이고 학습 데이터가 60행 이상인 경우다. 조건 미달 시 `INSUFFICIENT_HISTORY`를 반환하며 솔루션 생성과 챗봇 사용을 차단한다. 월 중간에 종료되는 파일도 이 조건을 충족하면 정상 예측한다. 14일 기준 매출 인사이트 생성은 예측 가능 여부와 독립적으로 동작한다.

AI는 일별 예측과 함께 80% 예측구간(`lowerBound`, `upperBound`)을 반환한다. 세 금액은 원 단위 정수이며 `lowerBound` ≤ `predictedSalesAmount` ≤ `upperBound`를 만족한다. 예측구간은 과거 잔차 분위수로 산출하므로 상·하한 폭은 비대칭일 수 있다. 월 합계와 요일 평균은 응답하지 않으며, BE가 저장된 최신 일별 예측에서 매번 다시 집계한다.

`modelVersion`은 최대 50자의 모델 식별자이며 `모델명-YYYY-MM-DD` 형식(예: `ridge-2026-09-16`)을 사용한다. 팀 기능 릴리스(v1/v2/v3)와 무관하다. BE는 이 값을 추적용으로 저장하며 모델 버전에 따른 기능 분기나 최신 업로드 판별에 사용하지 않는다. 같은 매장·날짜의 예측은 모델 버전과 관계없이 최신 업로드 결과로 교체한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"예측을 생성했습니다.","data":{"forecastStartDate":"2026-09-01","forecastEndDate":"2026-10-05","horizonDays":35,"predictions":[{"targetDate":"2026-09-01","predictedSalesAmount":1380000,"lowerBound":1142000,"upperBound":1730000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-02","predictedSalesAmount":1381000,"lowerBound":1146230,"upperBound":1726250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-03","predictedSalesAmount":1382000,"lowerBound":1147060,"upperBound":1727500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-04","predictedSalesAmount":1383000,"lowerBound":1147890,"upperBound":1728750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-05","predictedSalesAmount":1384000,"lowerBound":1148720,"upperBound":1730000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-06","predictedSalesAmount":1385000,"lowerBound":1149550,"upperBound":1731250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-07","predictedSalesAmount":1386000,"lowerBound":1150380,"upperBound":1732500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-08","predictedSalesAmount":1387000,"lowerBound":1151210,"upperBound":1733750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-09","predictedSalesAmount":1388000,"lowerBound":1152040,"upperBound":1735000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-10","predictedSalesAmount":1389000,"lowerBound":1152870,"upperBound":1736250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-11","predictedSalesAmount":1390000,"lowerBound":1153700,"upperBound":1737500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-12","predictedSalesAmount":1391000,"lowerBound":1154530,"upperBound":1738750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-13","predictedSalesAmount":1392000,"lowerBound":1155360,"upperBound":1740000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-14","predictedSalesAmount":1393000,"lowerBound":1156190,"upperBound":1741250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-15","predictedSalesAmount":1394000,"lowerBound":1157020,"upperBound":1742500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-16","predictedSalesAmount":1395000,"lowerBound":1157850,"upperBound":1743750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-17","predictedSalesAmount":1396000,"lowerBound":1158680,"upperBound":1745000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-18","predictedSalesAmount":1397000,"lowerBound":1159510,"upperBound":1746250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-19","predictedSalesAmount":1398000,"lowerBound":1160340,"upperBound":1747500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-20","predictedSalesAmount":1399000,"lowerBound":1161170,"upperBound":1748750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-21","predictedSalesAmount":1400000,"lowerBound":1162000,"upperBound":1750000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-22","predictedSalesAmount":1401000,"lowerBound":1162830,"upperBound":1751250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-23","predictedSalesAmount":1402000,"lowerBound":1163660,"upperBound":1752500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-24","predictedSalesAmount":1403000,"lowerBound":1164490,"upperBound":1753750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-25","predictedSalesAmount":1404000,"lowerBound":1165320,"upperBound":1755000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-26","predictedSalesAmount":1405000,"lowerBound":1166150,"upperBound":1756250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-27","predictedSalesAmount":1406000,"lowerBound":1166980,"upperBound":1757500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-28","predictedSalesAmount":1407000,"lowerBound":1167810,"upperBound":1758750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-29","predictedSalesAmount":1408000,"lowerBound":1168640,"upperBound":1760000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-09-30","predictedSalesAmount":1409000,"lowerBound":1169470,"upperBound":1761250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-10-01","predictedSalesAmount":1410000,"lowerBound":1170300,"upperBound":1762500,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-10-02","predictedSalesAmount":1411000,"lowerBound":1171130,"upperBound":1763750,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-10-03","predictedSalesAmount":1412000,"lowerBound":1171960,"upperBound":1765000,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-10-04","predictedSalesAmount":1413000,"lowerBound":1172790,"upperBound":1766250,"modelVersion":"ridge-2026-09-16"},{"targetDate":"2026-10-05","predictedSalesAmount":1414000,"lowerBound":1173620,"upperBound":1767500,"modelVersion":"ridge-2026-09-16"}]}}` |
| 422 | `{"message":"forecastStartDate는 dailySales 마지막 날짜의 다음 날이어야 합니다.","data":null}` |
| 200 | `{"message":"예측에 필요한 매출 이력이 부족합니다.","status":"INSUFFICIENT_DATA","data":{"missingData":["INSUFFICIENT_HISTORY"]}}` |
| 500 | `{"message":"예측 처리 중 오류가 발생했습니다.","data":null}` |
| 504 | `{"message":"예측 처리 시간이 초과되었습니다.","data":null}` |

---

## SALES-01, SOL-01 · POST `/internal/v1/ai/solutions/generate`

- **방향**: BE → AI
- **버전**: v1

**요청 값**

```
storeId (필수) salesAnalysisId (필수, `sales_analyses.id`) targetDate (필수) triggerType (필수, UPLOAD) metrics (필수 — V1에서 BE가 분석 모듈로 미리 계산한 매출요약·카테고리 비중·시간대 프로파일·오늘 예측 매출(SALES_PREDICTION 조회값) 묶음. 순이익은 V2, 리뷰 요약은 V3부터 포함한다. 원본 salesRecords는 보내지 않음)
```

**설명**

업로드의 기본 매출 집계와 예측이 완료되고 예측 시작 달의 직전 두 달이 완전한 월이며 학습 데이터가 60행 이상이면, 백그라운드 작업이 `triggerType=UPLOAD`으로 호출해 `targetDate` 기준 오늘의 솔루션을 만든다. 예측이 `INSUFFICIENT_HISTORY`이면 이 API를 호출하지 않는다. `salesAnalysisId`는 솔루션 생성 근거인 `sales_analyses.id`이며, AI 응답을 받은 뒤 BE는 이 값을 사용해 `solution_bundles.sales_analysis_id`와 각 `solutions.sales_analysis_id`를 저장한다. AI에는 원본 거래 데이터가 아니라 서버가 계산한 지표 JSON만 전달한다(환각 방지, 입력 토큰 절감) — LLM은 솔루션 카드 3장만 생성한다. 매출 AI 인사이트는 별도 `/internal/v1/ai/sales-insights` API에서 생성한다. 같은 매장·같은 targetDate의 솔루션 묶음이 이미 있으면 새로 생성하지 않고 기존 결과를 사용하며, FE에는 오늘의 솔루션 조회 API로 제공한다.

**설계 근거**

새로운 솔루션 결과를 생성하는 동작이라 POST를 사용했다. AI에는 원본 데이터가 아닌 BE가 미리 계산한 metrics만 전달해 응답 일관성과 보안(환각 방지, 토큰 절감)을 확보했고, 예측 완료 후 같은 백그라운드 작업에서 이어 호출하며, FE는 오늘의 솔루션 조회 API로 준비 상태와 완료 결과를 확인한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"솔루션을 생성했습니다.","data":{"solutionCards":[{"rankNo":1,"title":"점심 시간대 할인","summaryText":"점심 할인 프로모션을 제안합니다.","detailText":"12시부터 14시까지 할인 행사를 진행하세요."}],"modelVersion":"anthropic:claude-sonnet-4-5"}}` |
| 422 | `{"message":"필수 데이터가 누락되었거나 형식이 올바르지 않습니다.","data":null}` |
| 500 | `{"message":"솔루션 생성 중 오류가 발생했습니다.","data":null}` |
| 504 | `{"message":"솔루션 생성 시간이 초과되었습니다.","data":null}` |

---

## (화면 없음 — BE 내부 스케줄러, 매일 00:00) · POST `/internal/v1/ai/solutions/generate`

- **방향**: BE → AI
- **버전**: v1

**요청 값**

```
storeId (필수) targetDate (필수, 오늘 날짜) triggerType (필수, SCHEDULED) metrics (필수 — 위와 동일 구성, 그날 기준으로 재계산된 지표)
```

**설명**

매일 00:00 BE 스케줄러가 사용자 요청과 분리된 백그라운드 배치로 같은 API를 호출해 '오늘' 기준 솔루션을 생성한다. 예측 시작 달의 직전 두 달이 완전한 월이 아니거나 학습 데이터가 60행 미만인 매장은 `INSUFFICIENT_HISTORY`로 처리하고 호출 대상에서 제외한다. 업로드한 당일에는 업로드 직후 생성된 결과를 사용하고, 이후 날짜부터 00:00 배치가 생성한다. 같은 매장·같은 targetDate의 솔루션 묶음이 이미 있으면 생성하지 않는다. 사용자 응답 시간이 없으므로 처리 시간이 다소 걸려도 무방하다. 예측(수치)은 위 forecast/batch가 이미 만들어둔 값을 조회해 metrics에 포함시킬 뿐, 이 호출에서 다시 계산하지 않는다. 날짜·요일이 바뀌면(v2부터는 날씨·공휴일도) 매번 다른 추천이 나올 수 있다. FE의 어떤 요청과도 무관한 배치라 '관련 화면'이 없다. AI 응답을 받은 뒤 BE가 결과를 solutions 테이블에 저장하고, FE에는 오늘의 솔루션 조회 API로 제공한다

**설계 근거**

FE 요청과는 무관한 서버 내부 배치이지만 "새 솔루션을 생성한다"는 의미는 동일해, 엔드포인트를 따로 만들지 않고 `triggerType`(UPLOAD/SCHEDULED) 값으로 호출 맥락만 구분했다 — AI 쪽 처리 로직을 이원화하지 않기 위한 선택이다. 매일 자정 재계산해 날짜·요일(추후 날씨·공휴일) 변화가 반영된 새로운 추천을 제공하는 시나리오다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"솔루션을 생성했습니다.","data":{"targetDate":"2026-09-06","solutionCards":[{"rankNo":1,"title":"점심 시간대 할인","summaryText":"점심 할인 프로모션을 제안합니다.","detailText":"12시부터 14시까지 할인 행사를 진행하세요."}],"modelVersion":"anthropic:claude-sonnet-4-5"}}` |
| 422 | `{"message":"필수 데이터가 누락되었거나 형식이 올바르지 않습니다.","data":null}` |
| 500 | `{"message":"솔루션 생성 중 오류가 발생했습니다.","data":null}` |
| 504 | `{"message":"솔루션 생성 시간이 초과되었습니다.","data":null}` |

---

## SALES-02, SALES-03 · GET `/v1/sales/uploads/{uploadId}/status`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: 없음

**설명**

업로드의 기본 매출 처리 상태와 AI 인사이트 상태를 구분해 조회한다. 기본 상태는 `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`이며 처리 중 세부 단계는 `processingPhase=VALIDATING/NORMALIZING/AGGREGATING/ANALYZING`으로 표시한다. 파일 검증과 주문·집계 저장이 끝나면 기본 매출 상태는 `COMPLETED`가 된다. 이후 AI가 실패해도 기본 매출 상태와 저장 데이터는 유지하고 `aiInsightStatus`만 `FAILED`로 변경한다. FE는 `aiInsightStatus=FAILED`이면서 `retryable=true`인 경우에만 AI 인사이트 영역 또는 업로드 상태 화면에 재시도 버튼을 표시한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"파일을 검증하고 있습니다.","status":"PROCESSING","failReason":null,"data":{"uploadId":12,"analysisRunId":34,"processingPhase":"VALIDATING","analysisId":null,"aiInsightStatus":"PENDING","retryable":false}}` |
| 200 | `{"message":"기본 매출 분석이 완료되었습니다.","status":"COMPLETED","failReason":null,"data":{"uploadId":12,"analysisRunId":34,"processingPhase":null,"analysisId":51,"aiInsightStatus":"GENERATING","retryable":false}}` |
| 200 | `{"message":"기본 매출 분석은 완료되었지만 AI 인사이트 생성에 실패했습니다.","status":"COMPLETED","failReason":"AI_INSIGHT_ERROR","data":{"uploadId":12,"analysisRunId":34,"processingPhase":null,"analysisId":51,"aiInsightStatus":"FAILED","retryable":true}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"업로드 정보를 찾을 수 없습니다.","data":null}` |

---

## SALES-03-01 · POST `/v1/sales/uploads/{uploadId}/analysis-retries`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: 없음

**설명**

검증과 기본 집계가 완료되고 AI 인사이트 생성에 실패한 업로드를 기준으로 새 AI 인사이트 생성 실행을 비동기로 접수한다. 저장된 정상 집계 지표를 재사용하여 내부 `POST /internal/v1/ai/sales-insights`를 `triggerType=RETRY`로 호출하며, 원본 파일 검증·정규화·집계를 다시 수행하지 않는다. 기존 실패 실행과 정상 집계는 보존한다. 원본 파일 검증 실패처럼 집계 지표를 재사용할 수 없는 경우에는 새 파일 업로드를 안내한다.

**응답**

| status | body |
| --- | --- |
| 202 | `{"message":"AI 인사이트 재시도를 접수했습니다.","status":"PENDING","data":{"uploadId":12,"analysisRunId":35}}` |
| 409 | `{"message":"이미 AI 인사이트를 생성하고 있습니다.","data":null}` |
| 422 | `{"message":"이 업로드는 다시 분석할 수 없습니다. 새 파일을 업로드해 주세요.","failReason":"INVALID_SALES_SCHEMA","data":null}` |
| 404 | `{"message":"업로드 정보를 찾을 수 없습니다.","data":null}` |

---

## SALES-03 · GET `/v1/sales/analyses/{analysisId}`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: 없음

**설명**

본인 매장의 특정 매출 분석 결과를 조회한다. 화면 KPI의 `totalSales`는 완료·취소·비메뉴를 모두 합산한 `total_net_amount`다. `menuSales`, 메뉴 순위와 AI 입력은 `item_type=MENU`만 합산한 `menu_net_amount`를 사용한다. AI 인사이트가 준비 중이거나 실패해도 기본 집계는 정상 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"status":"COMPLETED","data":{"period":{"startDate":"2025-12-08","endDate":"2026-06-01"},"kpis":{"totalSales":231750809,"menuSales":228624909,"orderCount":15977,"averageOrderValue":14506},"dailySales":[{"date":"2026-06-01","totalSales":899450,"menuSales":889450,"orderCount":69}],"menuRankings":[{"menuName":"아메리카노","menuSales":800000,"quantity":250}],"aiInsight":{"status":"FAILED","summary":null}}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 403 | `{"message":"해당 분석 결과에 접근할 권한이 없습니다.","data":null}` |
| 404 | `{"message":"분석 결과를 찾을 수 없습니다.","data":null}` |

---

# SALES · 내부 조회 API (챗봇 툴)

## SALES-04 · 매출 요약 · GET `/internal/v1/sales/summary`

- **방향**: AI → BE (툴)
- **버전**: v1

**요청 값**

```
storeId (필수)
period (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간의 전체 실판매 매출(`total_net_amount`), 유효 주문 건수, 객단가와 비교 기간 대비 증감률을 조회한다.

**설계 근거**

챗봇이 매출 현황 질문에 필요한 핵심 지표만 빠르게 조회하도록 사전 집계 결과를 반환한다. 기간은 동일 매출 요약 리소스의 조회 조건이므로 query parameter로 받는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"period":{"type":"THIS_MONTH","startDate":"2026-09-01","endDate":"2026-09-08"},"totalSales":3200000,"orderCount":420,"averageOrderValue":7619,"changeRate":0.125}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

## SALES-04 · 카테고리·메뉴 기여도 · GET `/internal/v1/sales/categories`

- **방향**: AI → BE (툴)
- **버전**: v1

**요청 값**

```
storeId (필수)
period (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간의 MENU 전용 카테고리별 매출 비중과 메뉴별 판매·매출 순위를 `menu_net_amount` 기준으로 조회한다.

**설계 근거**

매출 증감 원인이나 인기 메뉴 질문에 답할 때 필요한 분류별 집계만 반환한다. 원본 주문 목록을 노출하지 않아 응답 크기와 내부 데이터 노출을 줄인다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"categories":[{"categoryName":"커피","menuSales":1800000,"ratio":0.563}],"menuRankings":[{"rank":1,"menuName":"아메리카노","menuSales":800000,"quantity":250}]}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

## SALES-04 · 시간대 매출 분포 · GET `/internal/v1/sales/hourly-profiles`

- **방향**: AI → BE (툴)
- **버전**: v1

**요청 값**

```
storeId (필수)
period (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
dayOfWeek (선택, MONDAY | ... | SUNDAY)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간의 MENU 전용 시간대별 매출(`menu_net_amount`)과 유효 주문 수를 조회한다. `dayOfWeek`를 전달하면 해당 요일로 한정한다.

**설계 근거**

피크 시간대와 요일별 패턴을 별도 도구로 분리해 챗봇이 필요한 경우에만 호출하도록 한다. 시간대별 집계는 사전 계산 결과를 조회한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"hourlyProfiles":[{"hour":12,"menuSales":420000,"orderCount":55},{"hour":13,"menuSales":380000,"orderCount":49}]}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

## SALES-04 · 매출 예측 · GET `/internal/v1/sales/forecasts`

- **방향**: AI → BE (툴)
- **버전**: v1

**요청 값**

```
storeId (필수)
targetDate (선택, YYYY-MM-DD, 기본 다음 영업일)
```

**설명**

저장된 일별 매출 예측 결과와 80% 예측구간(`lowerBound`, `upperBound`), 생성 시각을 조회한다. 세 금액은 원 단위 정수이며 `lowerBound` ≤ `predictedSalesAmount` ≤ `upperBound`를 만족한다. 예측이 겹치는 날짜는 최신 업로드 결과를 사용하며, 화면·솔루션·챗봇에는 KST 오늘 이후 날짜만 반환한다.

**설계 근거**

예측 생성과 조회를 분리한다. 이 API는 이미 저장된 sales_forecasts 결과만 읽으므로 챗봇 호출이 새로운 AI 작업을 중복 실행하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"forecasts":[{"targetDate":"2026-09-09","predictedSalesAmount":420000,"lowerBound":360000,"upperBound":480000}],"generatedAt":"2026-09-08T00:10:00+09:00"}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

## SALES-06 · 순이익 분석 · GET `/internal/v2/sales/profit-analyses`

- **방향**: AI → BE (툴)
- **버전**: v2

**요청 값**

```
storeId (필수)
period (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

V2에서 선택 기간의 순매출, 원가·고정비와 순이익 및 구성 비율을 조회한다.

**설계 근거**

금액 계산은 BE 서버 코드가 수행하고 챗봇은 계산된 결과만 읽는다. 이로써 AI가 비용·순이익을 임의 계산하는 문제를 막는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"netSales":3200000,"ingredientCost":1040000,"fixedCost":1200000,"netProfit":960000,"composition":[{"type":"NET_PROFIT","amount":960000,"ratio":0.3}]}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

## SOL-05 · 리뷰 감성 요약 · GET `/internal/v1/review-summaries`

- **방향**: AI → BE (툴)
- **버전**: v3

**요청 값**

```
storeId (필수)
period (선택, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM, 기본 THIS_MONTH)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간에 저장된 리뷰의 감성 분포, 주요 키워드와 요약을 조회한다.

**설계 근거**

챗봇이 고객 반응을 설명할 때 필요한 비식별 집계·요약만 조회한다. 원문 리뷰 전체를 반환하지 않아 응답 크기와 개인정보 노출을 줄인다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"summary":"커피 맛과 친절한 응대에 대한 긍정 반응이 많습니다.","sentiment":{"positive":0.82,"neutral":0.14,"negative":0.04},"keywords":["커피","친절","대기시간"]}}` |
| 404 | `{"message":"조회할 데이터가 없습니다.","data":null}` |

---

---

# SALES · 매출 분석 (SALES)

## SALES-04 · GET `/v1/sales/analyses`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
periodType (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate (CUSTOM일 때 필수, YYYY-MM-DD)
endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간의 화면 KPI, 일별 추이와 MENU 전용 메뉴·카테고리·시간대 분석을 조회한다. `totalSales`는 `total_net_amount`, `menuSales`는 `menu_net_amount`다. 수치와 증감률은 BE가 결정적으로 계산하며 AI는 화면에 표시할 1~3개의 문장형 인사이트만 생성한다. AI 인사이트가 없거나 실패해도 기본 분석 결과는 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","status":"COMPLETED","data":{"period":{"type":"THIS_MONTH","startDate":"2026-05-01","endDate":"2026-05-31"},"kpis":{"totalSales":40350532,"menuSales":39710632,"orderCount":2799,"changes":{"totalSalesRate":0.125}},"dailySales":[{"date":"2026-05-31","totalSales":1875100,"menuSales":1869100}],"menuRankings":[],"hourlySales":[],"weekdaySales":[],"aiInsight":{"status":"COMPLETED","insights":["최근 화요일 매출이 3주 연속 감소하고 있어요.","오후 3~5시는 다른 시간대보다 매출이 낮아요."]}}}` |
| 200 | `{"message":"선택 기간에 매출 데이터가 없습니다.","status":"EMPTY","data":{"dailySales":[],"menuRankings":[],"aiInsight":null}}` |
| 400 | `{"message":"조회 기간이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## SALES-04 · POST `/internal/v1/ai/sales-insights`

- **방향**: BE → AI
- **버전**: v1

**요청 값**

```
storeId (필수)
salesAnalysisId (필수)
targetMonth (필수, YYYY-MM)
triggerType (필수, UPLOAD | RETRY)
metrics (필수, menu_net_amount와 MENU 전용 일별·요일별·시간대별·카테고리별 지표)
maxInsightCount (필수, 3)
```

**설명**

BE가 DB에서 계산한 MENU 전용 지표만 AI에 전달해 화면에 표시할 1~3개의 문장형 매출 인사이트를 생성한다. AI는 원본 거래에 접근하거나 매출 수치·증감률을 다시 계산하지 않는다. `triggerType=UPLOAD`는 파일 업로드 후 최초 생성, `triggerType=RETRY`는 기존 AI 인사이트 생성 실패 후 재시도를 의미한다. 00:00 정기 갱신은 하지 않으므로 `SCHEDULED`는 사용하지 않는다. AI 응답은 `insights` 문자열 배열로 받고, 결과는 `sales_ai_insights.insights` JSON 배열에 저장하며 같은 매장·대상 월의 레코드를 상태와 함께 갱신한다. 생성 실패 시 기존 정상 인사이트와 기본 매출 집계를 유지한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"매출 AI 인사이트를 생성했습니다.","status":"COMPLETED","data":{"targetMonth":"2026-05","insights":["최근 화요일 매출이 3주 연속 감소하고 있어요.","오후 3~5시는 다른 시간대보다 매출이 낮아요."]}}` |
| 200 | `{"message":"AI 인사이트에 필요한 데이터가 부족합니다.","status":"INSUFFICIENT_DATA","data":{"missingData":["SALES_HISTORY"]}}` |
| 500 | `{"message":"매출 분석 인사이트 생성에 실패했습니다.","data":null}` |

---

# SOL · 솔루션 (SOL)

## SOL-01-01 / SOL-01-02 · GET `/v1/solutions/today`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

본인 매장의 오늘 솔루션 요약을 최대 3개까지 조회한다. 예측 시작 달의 직전 두 달이 완전한 월이 아니거나 학습 데이터가 60행 미만이면 `status=INSUFFICIENT_HISTORY`와 솔루션 생성 불가 안내를 반환한다. 업로드한 당일에는 업로드·분석 완료 직후 생성된 결과를 즉시 조회할 수 있고, 이후 날짜에는 매일 00:00 배치가 생성한 결과를 조회한다. 응답에는 매장명 기반 화면 제목, 솔루션 묶음 ID, 대상 날짜, 생성 상태와 각 카드의 우선순위·제목·요약·제안 근거를 포함한다. 생성 중은 `GENERATING`, 데이터 부족이나 분석 결과 없음은 `EMPTY`, 생성 실패는 `FAILED`로 구분한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","status":"COMPLETED","data":{"storeName":"맴매카페","screenTitle":"맴매카페 맴매 솔루션","solutionBundleId":81,"targetDate":"2026-09-08","solutionCards":[{"id":1,"rankNo":1,"title":"점심 시간대 할인","summaryText":"점심 할인 프로모션을 제안합니다.","detailText":"12시부터 14시까지 할인 행사를 진행하세요.","evidence":"12~14시 주문 수가 전주 대비 감소했습니다."}]}}` |
| 200 | `{"message":"오늘의 솔루션을 생성하고 있습니다.","status":"GENERATING","data":{"solutionBundleId":81,"targetDate":"2026-09-08","solutionCards":[]}}` |
| 200 | `{"message":"솔루션 생성을 위한 매출 이력이 부족합니다.","status":"INSUFFICIENT_HISTORY","data":{"solutionBundleId":null,"targetDate":"2026-09-08","solutionCards":[]}}` |
| 200 | `{"message":"데이터를 추가해 매출 분석을 받아보세요.","status":"EMPTY","data":{"solutionBundleId":null,"targetDate":"2026-09-08","solutionCards":[]}}` |
| 200 | `{"message":"오늘의 솔루션을 불러오지 못했습니다. 다시 시도해주세요.","status":"FAILED","data":{"solutionBundleId":null,"targetDate":"2026-09-08","solutionCards":[]}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## SOL-02 · GET `/v1/solution-bundles/{bundleId}`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

오늘 생성된 솔루션 묶음의 전체 상세 항목을 조회한다. 항목은 최대 3개이며 각각 우선순위, 제목, 구체적인 실행 방법, 기대 효과와 제안 근거를 반환한다. 상세 텍스트는 항목별 최대 1,000자다. 저장하지 않은 오늘의 솔루션은 대상 날짜가 지나면 410을 반환하고 SOL-01-01 이동을 안내한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"solutionBundle":{"id":81,"targetDate":"2026-09-08","expiresAt":"2026-09-09T00:00:00+09:00","expirationNotice":"오늘의 솔루션은 00:00시에 사라져요. 남겨두려면 저장해주세요.","isSaved":false,"items":[{"id":1,"rankNo":1,"title":"점심 시간대 할인","summaryText":"점심 할인 프로모션을 제안합니다.","detailText":"12시부터 14시까지 할인 행사를 진행하세요.","evidence":"해당 시간대 주문 수가 전주 대비 감소했습니다."}]}}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"솔루션을 찾을 수 없습니다.","data":null}` |
| 410 | `{"message":"오늘의 솔루션이 만료되었습니다.","next":"SOL-01-01","data":null}` |

---

## SOL-02 · POST `/v1/solution-bundles/{bundleId}/saves`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

오늘의 솔루션 묶음 전체를 저장한다. 저장 시점의 화면 제목, 대상 날짜와 최대 3개 항목의 제목·요약·실행 방법·기대 효과·근거를 스냅샷으로 보관한다. 이후 원본 매출 데이터, 분석 결과 또는 솔루션 원본이 변경돼도 저장 내용은 변경하지 않는다.

**설계 근거**

동일 사용자·매장·대상 날짜의 솔루션 묶음은 한 번만 저장한다. 네트워크 오류로 같은 요청이 반복되면 새 항목을 만들지 않고 기존 저장 결과를 반환한다.

**응답**

| status | body |
| --- | --- |
| 201 | `{"message":"솔루션이 저장되었습니다.","data":{"savedSolution":{"id":91,"solutionBundleId":81,"targetDate":"2026-09-08","savedAt":"2026-09-08T15:20:00+09:00"},"next":"SOL-03"}}` |
| 200 | `{"message":"이미 저장된 솔루션입니다.","data":{"savedSolution":{"id":91,"solutionBundleId":81,"targetDate":"2026-09-08","savedAt":"2026-09-08T15:20:00+09:00"},"next":"SOL-03"}}` |
| 404 | `{"message":"저장할 솔루션을 찾을 수 없습니다.","data":null}` |
| 410 | `{"message":"저장할 수 있는 시간이 만료되었습니다.","data":null}` |
| 500 | `{"message":"솔루션을 저장하지 못했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

---

## SOL-03 · GET `/v1/saved-solutions`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
cursor (선택)
size (선택, 기본 10, 최대 20)
```

**설명**

본인이 저장한 솔루션 스냅샷을 저장일 최신순, 연도별 그룹으로 조회한다. 카드에는 저장 날짜, 첫 번째 솔루션 제목과 나머지 항목 수를 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","nextCursor":null,"data":{"groups":[{"year":2026,"items":[{"savedId":91,"savedDate":"2026-09-08","displayTitle":"09/08 점심 시간대 할인 외 2개","firstTitle":"점심 시간대 할인","remainingItemCount":2}]}]}}` |
| 200 | `{"message":"아직 저장된 솔루션이 없습니다.","nextCursor":null,"data":{"groups":[]}}` |

---

## SOL-03 · DELETE `/v1/saved-solutions`

- **방향**: FE → BE
- **버전**: v1

**쿼리 파라미터**

```
savedIds (필수, 다중 값 — 편집모드 다중 선택 삭제)
```

**설명**

선택한 저장 솔루션 일괄 삭제. 이미 삭제된 항목이 섞여 있어도 에러 대신 최신 목록 기준으로 처리

**설계 근거**

다중 삭제를 지원하기 위해 단건 리소스 경로가 아니라 컬렉션 경로(`/v1/saved-solutions`)에 DELETE와 `savedIds` 쿼리 파라미터를 사용하는 방식을 택했다(편집모드 다중 선택 삭제 시나리오). 이미 삭제된 id가 섞여 있어도 에러를 내지 않고 최신 목록 기준으로 처리해, 같은 요청을 반복해도 결과가 같은 멱등한 동작으로 유지했다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"삭제되었습니다.","data":{"deletedCount":2}}` |
| 403 | `{"message":"본인이 저장한 솔루션만 삭제할 수 있습니다.","data":null}` |

---

## SOL-04 · GET `/v1/saved-solutions/{savedId}`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

저장한 솔루션을 읽기 전용으로 조회한다. 응답은 원본 솔루션 테이블의 현재값이 아니라 저장 시점에 복사한 스냅샷을 기준으로 한다. 이 화면에서는 추가 저장 기능을 제공하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"savedSolution":{"id":91,"savedDate":"2026-09-08","displayTitle":"09/08 점심 시간대 할인 외 2개","readOnly":true,"items":[{"rankNo":1,"title":"점심 시간대 할인","summaryText":"점심 할인 프로모션을 제안합니다.","detailText":"12시부터 14시까지 할인 행사를 진행하세요.","evidence":"해당 시간대 주문 수가 전주 대비 감소했습니다."}]}}}` |
| 404 | `{"message":"삭제되었거나 존재하지 않는 저장 솔루션입니다.","next":"SOL-03","data":null}` |
| 500 | `{"message":"데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

---

## SOL-05 · GET `/v1/chat/messages`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

인증된 사용자의 KST 오늘 날짜 대화만 생성 시각 오름차순으로 조회한다. 날짜가 바뀌면 새로운 대화를 시작하며, 이전 날짜의 메시지는 DB에 보관하지만 이 API로 반환하지 않는다. 오늘 대화가 없으면 서비스 안내와 고정 추천 질문을 최대 2개 반환한다. 응답의 `chatDate`는 서버가 판정한 KST 대화 기준일이다.

**설계 근거**

별도 채팅방 목록과 과거 대화 조회 기능 없이 날짜별 대화를 제공하는 MVP 정책이다. 클라이언트가 날짜를 임의로 지정하지 못하게 하고 서버가 KST 오늘 날짜를 결정해 사용자별 당일 메시지만 조회한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"chatDate":"2026-09-16","serviceGuide":"매출과 오늘의 솔루션을 바탕으로 운영 질문에 답변해드려요.","messages":[{"id":301,"role":"USER","content":"오늘 어떤 메뉴를 밀어야 해?","status":"COMPLETED","createdAt":"2026-09-16T10:20:00+09:00"}],"recommendedQuestions":[]}}` |
| 200 | `{"message":"오늘 대화가 없습니다.","data":{"chatDate":"2026-09-16","serviceGuide":"매출과 오늘의 솔루션을 바탕으로 운영 질문에 답변해드려요.","messages":[],"recommendedQuestions":["오늘 매출을 높이려면 무엇을 해야 하나요?","어떤 시간대에 프로모션을 진행하면 좋을까요?"]}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

---

## SOL-05 · POST `/v1/chat/messages`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
content (필수, 공백 제외 1자 이상 300자 이하)
retryOfMessageId (선택, 실패한 질문 재시도 시 원본 사용자 메시지 ID)
```

**설명**

본인 매장 데이터와 현재 솔루션, DB에 저장된 전체 누적 대화 이력을 컨텍스트로 질문하고 AI 답변을 스트리밍으로 생성한다. 예측 상태가 `INSUFFICIENT_HISTORY`이면 AI를 호출하지 않고, HTTP 200과 `status=INSUFFICIENT_DATA`로 필요한 데이터 안내를 반환한다. 사용자 질문과 AI 답변은 서버가 판정한 KST 오늘 날짜에 저장한다. 오늘 날짜에 `PENDING` 또는 `STREAMING` 상태의 AI 답변이 있으면 같은 사용자의 추가 질문을 제한한다. 이전 날짜의 처리 상태는 오늘 질문을 차단하지 않지만, 완료된 과거 대화 내용은 AI 문맥에 포함한다. 데이터가 부족하면 원인을 단정하지 않고 부족한 데이터와 추가로 필요한 정보를 안내한다.

**설계 근거**

요구사항의 제한 단위는 토큰이 아니라 사용자 입력 300자이므로 서버도 문자 수 기준으로 검증한다. 재시도는 오늘 날짜의 실패한 질문을 식별해 같은 사용자 질문을 중복 저장하지 않고 새 답변 생성을 다시 시작한다. 날짜가 바뀌어도 과거 메시지는 삭제하지 않고 AI의 누적 대화 문맥으로 계속 사용한다. 다만 외부 조회 API는 화면 정책에 따라 오늘 날짜의 메시지만 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"event":"answerChunk","data":{"messageId":302,"content":"이번 달 매출은 지난달보다 증가했습니다.","evidence":{"metric":"sales_summary","period":"2026-08","value":0.12}}}` |
| 409 | `{"message":"이전 답변을 생성하고 있습니다.","data":null}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"content","message":"질문은 공백을 제외하고 1자 이상 300자 이하로 입력해 주세요."}]}}` |
| 200 | `{"message":"예측에 필요한 매출 이력이 부족해 챗봇 답변을 생성할 수 없습니다.","status":"INSUFFICIENT_DATA","data":{"missingData":["INSUFFICIENT_HISTORY"]}}` |
| 504 | `{"message":"응답 생성이 시간을 초과했습니다. 다시 시도해주세요.","data":null}` |
| 500 | `{"message":"답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

---

## SOL-05 · POST `/internal/v1/ai/chat/messages`

- **방향**: BE → AI
- **버전**: v1

**요청 값**

```
userId (필수) storeId (필수) chatDate (필수, 새 메시지가 속하는 서버 판정 KST 오늘 날짜) question (필수, 사용자 질문 원문) history (선택, DB에 저장된 해당 사용자의 전체 누적 대화 이력 배열: role/content/createdAt) context (필수 — 오늘 생성된 솔루션 상세보기(SOL-02) 전체 내용: 카드별 rank/title/detail)
```

**설명**

FE가 POST /v1/chat/messages로 보낸 질문을 BE가 AI에 전달한다. 별도 채팅 세션은 만들지 않으며, DB에 저장된 해당 사용자의 완료된 전체 누적 대화를 `history`로 전달한다. `chatDate`는 새 질문과 답변을 오늘 화면에 귀속하기 위한 KST 기준일이며, AI가 기억할 대화 범위를 제한하는 값으로 사용하지 않는다. AI는 LangGraph 기반 단일 에이전트로, context(오늘 솔루션 상세보기)만으로 부족하면 위 '분석 모듈 내부 조회 API' 6종을 툴로 호출해 필요한 지표를 직접 조회한 뒤 답변한다. 답변은 토큰 단위로 스트리밍 반환한다(SSE).

**설계 근거**

FE 요청을 BE가 AI에 전달해 답변이라는 새 결과를 생성하므로 POST를 사용했다. 툴 호출(내부 조회 API 6종)이 먼저 끝난 뒤에 스트리밍이 시작되도록 설계해 답변 도중 툴 호출 때문에 스트림이 끊기는 상황을 피했다. `history`는 선택값으로 두어 최초 질문에는 빈 배열을 보내지 않아도 되게 했으며, 이후에는 날짜와 관계없이 저장된 누적 대화를 전달해 이전 대화 내용을 이어서 답변할 수 있게 한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"event":"answerChunk","data":{"content":"이번 달 매출은 지난달보다 증가했습니다."}}` |
| 400 | `{"message":"질문 형식이 올바르지 않습니다.","data":null}` |
| 200 | `{"message":"매출 데이터가 없어 컨텍스트를 구성할 수 없습니다.","status":"INSUFFICIENT_DATA","data":{"missingData":["SALES_DATA"]}}` |
| 504 | `{"message":"응답 생성이 시간을 초과했습니다.","data":null}` |
| 500 | `{"message":"답변 생성에 실패했습니다.","data":null}` |

---

## SOL-05 · 스트리밍 응답 바디 형태

- **방향**: BE → AI
- **버전**: v1
- **요청 값**: (해당 없음 — 응답 형태 설명용 행)

**설명**

위 요청의 스트리밍 응답 바디 형태 — answerChunk(텍스트, 청크 단위) + evidence(답변 근거로 쓴 지표, 구조화된 객체 — 서버 산출값과 반드시 일치해야 함)로 전송한 뒤, 마지막 이벤트는 JSON이 아닌 `data: [DONE]`으로 전송한다. V1의 `answerChunk.content`는 평문으로만 생성하며 Markdown 문법(볼드 `**`, 목록 기호 등)을 포함하지 않는다. 금액은 축약하지 않고 천 단위 쉼표를 사용한 원 단위 표기(예: `3,247,891원`)로 통일한다.

**설계 근거**

별도 엔드포인트가 아니라 위 API의 응답 형태를 설명하기 위한 참고 행이다. `evidence` 필드를 답변 텍스트와 함께 구조화된 객체로 내려받게 해, 챗봇이 근거로 든 수치가 실제 서버 산출값과 항상 일치하는지 검증할 수 있게 만든 것이 이 필드를 둔 이유다.

**응답**

| status | body |
| --- | --- |
| - | `{"event":"answerChunk","data":{"content":"이번 달 매출은 지난달보다","evidence":{"metric":"sales_summary","period":"2026-08","value":-0.12}}}`
`data: [DONE]` |

---

# NOTI · 알림 (NOTI)

알림함과 알림 설정은 로그인한 사용자만 사용할 수 있으며, 사용자는 본인 계정과 본인 매장에 연결된 알림만 조회·변경할 수 있다. 알림 목록은 `notifications`, 수신 설정은 `notification_preferences`를 기준으로 처리한다. 알림 유형은 `SOLUTION_READY`, `SALES_UPLOAD_REMINDER`, `RANKING_CHANGED`를 사용하며, `RANKING_CHANGED`는 V2부터 제공한다.

## NOTI-01 · GET `/v1/notifications`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
readStatus (선택, ALL | UNREAD, 기본 ALL)
cursor (선택, cursor 기반 페이징)
size (선택, 기본 20, 최대 50)
```

**설명**

인증된 사용자의 알림을 실제 발송 시점(`sentAt`) 최신순으로 조회한다. `readStatus=ALL`이면 읽은 알림과 읽지 않은 알림을 모두 반환하고, `readStatus=UNREAD`이면 읽지 않은 알림만 반환한다. 알림이 없는 경우는 오류가 아니므로 200과 빈 배열을 반환한다. 각 알림의 `relatedEntityType`과 `relatedEntityId`는 솔루션·매출 업로드·랭킹 화면으로 이동할 때 사용하며, 연결 대상이 없으면 null이다.

**설계 근거**

시간이 지날수록 알림이 계속 누적되므로 cursor 기반 페이징을 적용한다. GET은 상태를 변경하지 않는 조회로 유지하며, 알림함 진입 후 화면에 표시된 알림의 읽음 처리는 별도 PATCH API로 분리한다. 세션의 사용자 ID로 `notifications.user_id`를 제한해 다른 사용자의 알림 존재 여부와 내용을 노출하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","nextCursor":null,"data":{"items":[{"id":1201,"type":"SOLUTION_READY","title":"오늘의 솔루션이 도착했어요","content":"오늘의 매장 운영 솔루션을 확인해 보세요.","relatedEntityType":"SOLUTION","relatedEntityId":51,"sentAt":"2026-09-08T08:00:00+09:00","readAt":null}]}}` |
| 200 | `{"message":"알림이 없습니다.","nextCursor":null,"data":{"items":[]}}` |
| 400 | `{"message":"알림 조회 조건이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 500 | `{"message":"알림을 불러오지 못했습니다. 다시 시도해주세요.","data":null}` |

---

## NOTI-01 · PATCH `/v1/notifications`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
notificationIds (필수, 화면에 표시된 읽지 않은 알림 ID 배열, 최대 100개)
```

**설명**

알림함에 실제로 표시된 읽지 않은 알림을 일괄 읽음 처리하고 `notifications.read_at`을 기록한다. 이미 읽은 알림 ID가 포함되어 있어도 현재 읽음 상태를 유지하며 성공으로 처리한다. 요청 사용자가 소유하지 않은 ID는 변경하지 않는다.

**설계 근거**

알림 목록 GET 요청에서 읽음 상태까지 변경하면 조회의 멱등성이 깨지고, 네트워크 재시도만으로 읽음 처리되는 문제가 생길 수 있다. 따라서 FE가 화면 렌더링에 성공한 후 실제로 표시한 ID만 PATCH로 전달한다. 동일 요청을 반복해도 결과가 같도록 멱등하게 처리한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"읽음 처리되었습니다.","data":{"updatedCount":3,"readAt":"2026-09-08T14:30:00+09:00"}}` |
| 400 | `{"message":"읽음 처리할 알림을 선택해 주세요.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"읽음 처리할 알림을 찾을 수 없습니다.","data":null}` |

---

## NOTI-02 · GET `/v1/notification-preferences`

- **방향**: FE → BE
- **버전**: v1
- **요청 값**: (없음)

**설명**

인증된 사용자의 유형별 알림 수신 설정을 조회한다. `solutionEnabled`는 솔루션 제공 알림, `salesUploadReminderEnabled`는 매출 데이터 업로드 알림, `rankingChangeEnabled`는 랭킹 순위 변동 알림의 수신 여부다. `rankingChangeEnabled` 설정 UI와 실제 랭킹 알림 발송은 V2부터 제공한다.

**설계 근거**

사용자 1명당 하나의 `notification_preferences` 행을 조회한다. 설정 행이 아직 없다면 ERD 기본값에 따라 각 항목을 true로 생성하거나 동일한 기본값을 응답한다. 다른 사용자의 설정 ID를 요청값으로 받지 않고 세션 사용자 기준으로만 조회한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"preferences":{"solutionEnabled":true,"salesUploadReminderEnabled":true,"rankingChangeEnabled":true}}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 500 | `{"message":"알림 설정을 불러오지 못했습니다.","data":null}` |

---

## NOTI-02 · PATCH `/v1/notification-preferences`

- **방향**: FE → BE
- **버전**: v1

**요청 값**

```
solutionEnabled (선택, boolean)
salesUploadReminderEnabled (선택, boolean)
rankingChangeEnabled (선택, boolean, V2)
```

**설명**

유형별 알림 수신 설정을 부분 수정한다. 변경된 토글 필드만 요청하며, 서버는 전달되지 않은 설정값을 기존 값으로 유지한다. FE는 토글 변경 즉시 이 API를 호출하고, 요청 중에는 변경한 토글만 비활성화한다. 저장에 실패하면 직전 설정값으로 복원한다.

**설계 근거**

설정 리소스 전체 교체가 아니라 선택된 필드만 변경하므로 PATCH를 사용한다. 모든 필드가 누락된 요청은 400으로 거절한다. 사용자 ID는 요청 본문으로 받지 않고 세션에서 식별해 본인 설정만 변경할 수 있게 한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"알림 설정이 변경되었습니다.","data":{"preferences":{"solutionEnabled":true,"salesUploadReminderEnabled":false,"rankingChangeEnabled":true}}}` |
| 400 | `{"message":"변경할 알림 설정이 없습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"preferences","message":"알림 설정값을 확인해 주세요."}]}}` |
| 500 | `{"message":"알림 설정을 저장하지 못했습니다.","data":null}` |

---

## NOTI-03 · GET `/v1/notifications/stream` (SSE, V2)

- **방향**: FE → BE
- **버전**: v2 기능, 알림 리소스의 기존 v1 경로 사용
- **요청 값**: 없음 (로그인 세션 쿠키 필요)

**설명**

접속 중인 로그인 사용자의 알림 이벤트 스트림을 연다. `SOLUTION_READY`, `SALES_UPLOAD_REMINDER`, `RANKING_CHANGED` 알림은 DB 저장이 완료된 뒤 해당 사용자의 활성 SSE 연결로 전달한다. 타 사용자의 이벤트는 전달하지 않는다.

**클라이언트 처리**

SSE는 연결되어 있는 동안에만 새 알림을 전달한다. 연결이 없거나 끊긴 동안 생성된 알림은 DB 알림함에 보존하며, 클라이언트는 재접속 후 기존 `GET /v1/notifications`로 이력을 조회한다. 읽음 처리는 기존 `PATCH /v1/notifications`를 사용한다. 앱·브라우저가 닫힌 상태의 푸시는 V3에서 FCM으로 추가한다.

**응답**

- `200`: `Content-Type: text/event-stream`. 각 알림은 `notification` 이벤트로 전달하며 `data`는 알림 목록 항목과 같은 JSON 구조다.
- 최초 연결 시 로그인 세션이 없으면 기존 인증 규칙에 따라 `401`을 반환한다.

**이벤트 예시**

```
event: notification
data: {"id":1215,"type":"RANKING_CHANGED","title":"성장 랭킹 순위가 올랐어요","content":"지난 집계보다 3단계 오른 5위예요.","relatedEntityType":"RANKING_SNAPSHOT","relatedEntityId":87,"sentAt":"2026-10-06T08:00:00+09:00","readAt":null}
```

---

## 알림 생성·발송 스케줄 정책

- 솔루션 제공 알림은 매일 00:00 솔루션 갱신이 완료된 뒤 오전 08:00에 생성·발송한다. 00:00부터 08:00 사이에는 발송하지 않는다.
- 매출 데이터 업로드 알림은 매월 말일 오전 08:00에 사전 안내를 발송한다.
- 매월 1일부터 3일까지 오전 08:00에는 직전 달 매출 데이터가 모두 등록되지 않은 사용자에게만 업로드 알림을 발송한다.
- 랭킹 순위 변동 알림은 아래 RANK V2 정책에 따라 랭킹 집계 완료 후 생성·발송한다.
- 각 알림은 해당 유형의 수신 설정이 true인 사용자에게만 생성·발송한다.
- 동일 사용자·알림 유형·기준일에 같은 알림이 중복 생성되지 않도록 멱등키를 적용한다.
- 알림 생성과 발송이 같은 BE 애플리케이션의 스케줄러에서 수행된다면 공개 REST API를 추가하지 않고 배치 작업 명세로 관리한다. 별도 알림 서비스와 HTTP로 통신할 경우 내부 발송 API를 별도로 정의한다.

---

# AUTH · 토스 본인인증·회원가입 [V2]

토스 외부 화면의 이름·휴대폰 번호·인증번호는 맴매 서버가 직접 수집하거나 저장하지 않는다. 서버에는 인증 흐름 식별자, 토스가 발급한 결과의 유효성, 만료 시각과 제공자 고유 식별값만 보관하며, 인증 실패·취소만으로 로그인 세션을 만들지 않는다.

## AU-06 · POST `/v2/auth/toss/authentications`

- **방향**: FE → BE → Toss
- **버전**: v2

**요청 값**

```
returnUrl (필수, 사전 허용 목록에 등록된 맴매 복귀 URL)
```

**설명**

토스 본인 인증 흐름을 생성하고 외부 인증 화면으로 이동할 URL을 반환한다. 서버는 요청마다 일회용 `state`와 `authFlowId`를 생성하며 원문 개인정보를 요청하거나 저장하지 않는다.

**응답**

| status | body |
| --- | --- |
| 201 | `{"message":"토스 인증을 시작합니다.","data":{"authFlowId":"toss_auth_abc123","authorizationUrl":"https://toss.example/authorize?...","expiresAt":"2026-09-08T15:10:00+09:00"}}` |
| 400 | `{"message":"복귀 URL이 올바르지 않습니다.","data":null}` |
| 429 | `{"message":"인증 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.","data":null}` |
| 502 | `{"message":"토스 인증을 시작하지 못했습니다.","data":null}` |

---

## AU-06, AU-07 · GET `/v2/auth/toss/callback`

- **방향**: Toss → BE → FE
- **버전**: v2

**요청 값**

```
code (성공 시 필수, query parameter)
state (필수, query parameter)
error (취소·실패 시 선택, query parameter)
```

**설명**

토스가 전달한 `state`를 검증하고 인증 코드를 서버 간 통신으로 교환한다. 서버는 토스 고유 식별값으로 기존 연결을 자동 조회한다. 기존 회원이면 세션 쿠키를 발급해 서비스 홈으로 이동시키고, 연결된 회원이 없으면 인증 흐름을 `VERIFIED`로 변경해 AU-07 가입 확인 화면으로 복귀시킨다. 실패·취소·만료이면 `FAILED` 또는 `CANCELED`로 기록하고 세션을 생성하지 않는다. 이름·휴대폰 번호·인증번호는 응답, 로그 및 DB에 저장하지 않는다.

**응답**

| status | body |
| --- | --- |
| 302 | 신규 회원이면 `/auth/toss/check?authFlowId=toss_auth_abc123`로 이동 |
| 302 | 기존 회원이면 세션 쿠키를 발급하고 서비스 홈으로 이동. 실패·취소 시 `/login?tossAuthResult=failed`로 이동하며 로그인 세션은 생성하지 않음 |

동일 `state` 또는 `code`가 중복 전달돼도 최초 유효 처리만 반영한다.

---

## AU-07 · GET `/v2/auth/toss/authentications/{authFlowId}`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
authFlowId (필수, path variable)
```

**설명**

AU-07 로딩 화면에서 토스 결과의 수신·검증 상태를 조회한다. `VERIFIED`이고 연결된 기존 회원이 없으면 약관 동의 화면으로 이동한다. 기존 회원은 콜백에서 세션 발급 후 서비스 홈으로 바로 이동하므로 이 API를 호출하지 않는다. `FAILED | CANCELED | EXPIRED`이면 로그인 화면으로 이동한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"토스 인증 정보를 확인했습니다.","status":"VERIFIED","data":{"authFlowId":"toss_auth_abc123","expiresAt":"2026-09-08T15:10:00+09:00","next":"SIGN_UP"}}` |
| 200 | `{"message":"토스 인증 정보를 확인하고 있어요.","status":"PROCESSING","data":{"authFlowId":"toss_auth_abc123","next":"WAIT"}}` |
| 404 | `{"message":"토스 인증 정보를 찾을 수 없습니다.","data":null}` |
| 410 | `{"message":"토스 인증 정보가 유효하지 않습니다. 다시 인증해주세요.","data":null}` |

---

## AU-10 · POST `/v2/auth/toss/signups/agreements`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
authFlowId (필수, VERIFIED 상태)
agreements.termsOfService (필수, true)
agreements.termsOfServiceVersion (필수)
agreements.privacyPolicy (필수, true)
agreements.privacyPolicyVersion (필수)
```

**설명**

기존 사용자 연결이 없는 `VERIFIED` 토스 인증 흐름만 이 API를 호출할 수 있다. FE에 고정 노출된 두 필수 약관의 동의 여부·버전과 토스 인증 만료 여부를 검증한다. 이 단계에서는 계정을 만들지 않고 ST-01에서 사용할 만료형 `signupToken`만 발급한다. 뒤로가기는 API를 호출하지 않아 체크 상태를 저장하지 않는다.

**응답**

| status | body |
| --- | --- |
| 201 | `{"message":"필수 약관 동의가 확인되었습니다.","data":{"signupToken":"signup_toss_abc123","expiresAt":"2026-09-08T15:30:00+09:00","next":"BUSINESS_SIGNUP"}}` |
| 409 | `{"message":"이미 연결된 토스 계정입니다. 다시 로그인해주세요.","data":null}` |
| 410 | `{"message":"토스 인증 정보가 유효하지 않습니다. 다시 인증해주세요.","data":null}` |
| 422 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"agreements","message":"필수 약관에 모두 동의해 주세요."}]}}` |

`signupToken`은 토스 제공자 식별값과 동의한 약관 버전을 가입 초안에 연결한다. ST-01 최종 성공 시 `users`, `stores`, `user_auth_providers`, 기본 알림 설정을 하나의 트랜잭션으로 생성한다.

---

# STORE · 메뉴 보기·사진 인식 (ST) [V2, MY-04-01/02]

경로: 마이페이지 → 사업자 정보 확인 및 수정 → 메뉴 보기 → 다시 업로드/사진으로 메뉴 등록. 본인 매장 OWNER 세션을 매 요청마다 확인한다. `items`는 저장된 현재 메뉴, `draftBatch`는 아직 확정되지 않은 AI 결과다. 날짜는 ISO 8601, 화면 표시는 Asia/Seoul이다. 원화 가격은 숫자형 정수로 송수신한다.

## 공통 코드·검증

- 카테고리: `COFFEE`(커피), `NON_COFFEE`(논커피), `BEVERAGE`(음료), `CAKE`(케이크), `BAKERY`(베이커리), `OTHER`(기타).
- 메뉴명은 trim·연속 공백 정리·Unicode NFC로 비교한다. 동일 이름·가격·카테고리 조합만 중복이다. 이름이 같아도 가격 또는 카테고리가 다르면 허용한다.
- 이름 공백, 가격의 빈 값·문자·소수·0 미만·1,000,000 초과, 카테고리 누락·미지원은 `422`와 행별 `fieldErrors`다. `priceReviewRequired` 행은 가격 수정 또는 `priceConfirmed=true` 확인이 필요하다.
- 저장 요청에는 `expectedMenuRevision`과 `Idempotency-Key`를 사용한다. 불일치·이미 교체된 배치는 `409`이며 저장은 전체 원자적이다. `401`은 세션 만료, `403`은 소유권 없음이다.

## ST-03 · GET `/v2/menu-items`

- **방향**: FE → BE; **버전**: v2; **요청 값**: 없음.
- **설명**: 현재 저장 메뉴와 최신 AI 배치 메타데이터를 별도로 반환한다. 저장 메뉴가 없거나 최신 배치가 실패해도 `items`는 독립적으로 반환한다. 최신 배치가 완료되고 미저장이면 FE는 배치 상세 API로 후보를 읽는다.

**응답 예시**

```json
{"message":"조회에 성공했습니다.","data":{"menuRevision":4,"items":[{"id":27,"order":1,"name":"아메리카노","price":4000,"category":"COFFEE","updatedAt":"2026-10-07T13:00:00+09:00"}],"draftBatch":{"batchId":15,"status":"COMPLETED","uploadedAt":"2026-10-07T13:15:00+09:00","failReason":null,"savedAt":null}}}
```

- 최초 저장 전이면 `items=[]`. 배치가 없으면 `draftBatch=null`; `PROCESSING`·`FAILED`여도 기존 `items`는 유지한다. 404는 본인 매장 없음.

## ST-03 · PATCH `/v2/menu-items`

- **방향**: FE → BE; **요청**: `{expectedMenuRevision, items:[{menuId,name,price,category,order,priceConfirmed?}]}`. `items`는 현재 저장 목록 전체이며 변경된 값이 1개 이상 필요하다.
- **설명**: 저장 메뉴 직접 수정. 누락된 ID를 삭제로 해석하지 않는다. 모든 ID가 현재 본인 매장의 목록에 속해야 한다. 변경된 메뉴는 기존 행을 이력으로 보존하고 새 행을 만들며, 수정되지 않은 메뉴 ID는 유지한다. 전체 요청을 검증한 뒤 트랜잭션에서 `menu_revision`을 1 증가시킨다.

**응답 예시**

```json
{"message":"메뉴 정보가 저장되었습니다.","data":{"menuRevision":5,"items":[{"id":31,"order":1,"name":"아메리카노","price":4500,"category":"COFFEE"}]}}
```

- 400: 변경 내용 없음. 403: 다른 매장 메뉴. 409: 개정 충돌 또는 중복 조합(`code=DUPLICATE_MENU`). 422: `fieldErrors:[{menuId,field,code,message}]`. 500: 저장 실패.

## ST-04 · POST `/v2/menu-images`

- **방향**: FE → BE; **형식**: `multipart/form-data`, 반복 필드 `images` 1~10개, 헤더 `Idempotency-Key`.
- **설명**: 각 파일은 jpg/jpeg/png, 5MiB 이하이고 요청 전체는 50MiB 이하이다. 확장자·실제 MIME·시그니처를 검증하고 비공개 객체 스토리지에 저장한다. 접수 시 `menu_upload_batches`와 `menu_images`를 만들고 AI 처리를 비동기로 시작한다. 새 접수 성공 시 이전 **미저장 임시** 배치를 교체 표시하지만 저장 메뉴는 그대로 둔다. 업로드 전에 선택만 한 이미지는 서버에 저장되지 않는다.

**응답 예시**

```json
{"message":"메뉴판 이미지를 접수하고 AI 분석을 시작했습니다.","status":"PENDING","data":{"batchId":15,"imageCount":3,"uploadedAt":"2026-10-07T13:15:00+09:00","next":"MENU_LIST"}}
```

- 400: 이미지 없음/10장 초과(`TOO_MANY_IMAGES`). 401/403: 인증·권한. 409: 같은 멱등 키에 다른 이미지 묶음. 413: 개별 5MiB 또는 전체 50MiB 초과(`FILE_TOO_LARGE`/`TOTAL_TOO_LARGE`). 415: 미지원 형식. 500: 저장 실패. 파일별 오류에는 `fileIndex`를 포함한다.

## ST-03/ST-04 · GET `/v2/menu-image-batches/{batchId}`

- **방향**: FE → BE; **설명**: 본인 배치의 AI 처리 상태·실패 사유·후보를 조회한다. FE는 `PROCESSING` 동안 폴링한다. 원본 이미지의 비공개 저장 키는 노출하지 않는다.

**완료 예시**

```json
{"message":"메뉴 인식이 완료되었습니다.","status":"COMPLETED","data":{"batchId":15,"baseMenuRevision":4,"uploadedAt":"2026-10-07T13:15:00+09:00","savedAt":null,"failReason":null,"detectedItems":[{"itemId":101,"order":1,"name":"아메리카노","price":4000,"category":"COFFEE","priceReviewRequired":false},{"itemId":110,"order":10,"name":"쿠키","price":9000,"category":"OTHER","priceReviewRequired":true}]}}
```

- 분석 중: `200 status=PROCESSING, detectedItems=[]`. 실패: `200 status=FAILED, failReason=LOW_IMAGE_QUALITY|MENU_TEXT_NOT_FOUND|AI_PROCESSING_ERROR, detectedItems=[]`. 빈 결과: `200 status=COMPLETED, detectedItems=[]`. 403/404: 권한·배치 없음.

## ST-03 · POST `/v2/menu-image-batches/{batchId}/confirmations`

- **방향**: FE → BE; **요청**: `{expectedMenuRevision, items:[{itemId,name,price,category,order,priceConfirmed?}]}`, 헤더 `Idempotency-Key`. `items`는 배치에서 표시된 전체 후보이며 1개 이상이다.
- **설명**: `COMPLETED`이고 최신·미저장인 본인 배치만 확정한다. 최초 AI 결과는 편집하지 않아도 저장할 수 있다. 기존 현재 메뉴 전체를 논리 제거하고 검증된 후보를 새 현재 메뉴로 저장한다. 결과에 없는 기존 메뉴도 현재 목록에서 제외하지만 과거 매출 참조는 보존한다. `menu_image_items` 연결, `saved_at`, `menu_revision`을 한 트랜잭션에서 반영한다. `ocr_status`는 분석 결과 상태로 `COMPLETED`를 유지한다.

**응답 예시**

```json
{"message":"메뉴 정보가 저장되었습니다.","data":{"batchId":15,"menuRevision":5,"savedAt":"2026-10-07T13:20:00+09:00","items":[{"itemId":101,"menuId":31,"name":"아메리카노","price":4000,"category":"COFFEE"}]}}
```

- 400: 후보 없음. 401/403/404: 인증·권한·배치 없음. 409: 배치 이미 저장/교체됨, `menu_revision` 충돌 또는 현재 목록과 중복. 422: 행별 입력 검증/가격 확인 미완료. 500: 저장 실패.

## ST-04 · POST `/internal/v2/ai/menu-recognition`

- **방향**: BE → AI; **요청**: `{storeId,batchId,images:[{imageId,imageUrl,order}]}`. `imageUrl`은 접근 제한·단기 서명 URL이다.
- **설명**: 최대 10장을 한 배치로 분석하여 메뉴명·가격·카테고리 후보를 반환한다. BE는 원본 결과를 이미지별로 보관하고 동일 메뉴명·가격·카테고리 후보를 합친 뒤 `menu_image_items`에 저장한다. AI 실패는 배치 `FAILED`로 기록하고 기존 메뉴는 유지한다.

**응답 예시**

```json
{"message":"메뉴가 인식되었습니다.","data":{"detectedItems":[{"sourceImageId":52,"name":"아메리카노","price":4000,"category":"COFFEE","confidence":0.98,"priceReviewRequired":false}]}}
```

- 422: 식별 불가(`LOW_IMAGE_QUALITY`/`MENU_TEXT_NOT_FOUND`). 500: AI 처리 실패. AI는 저장된 `menus`를 직접 변경하지 않는다.

---

# SALES · 순수익 분석 (SALES) [V2]

순수익 API의 저장 기준은 ERD의 `store_cost_items`와 동일한 월 단위다. 금액은 원 단위 정수, **외부 API의 원가율은 0~100의 퍼센트 숫자(소수점 첫째 자리까지)**로 전달한다. 화면의 `40%`는 숫자 `40`으로 전송하며, BE는 이를 100으로 나누어 DB의 0~1 비율로 저장한다. 매출 파일 업로드 자체는 비용 이력 없이 성공할 수 있지만, 검증 완료 파일의 모든 매출 월에 비용을 확인·저장하기 전에는 순이익 분석 단계로 진행하지 않는다.

## SALES-05 · GET `/v2/stores/me/cost-items/{costMonth}`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
costMonth (필수, path variable, YYYY-MM)
```

**설명**

본인 매장의 지정 월 임대료·인건비·원가율을 조회한다. 지정 월은 파일 업로드일이나 화면 진입일이 아니라 매출 발생 월이다. 해당 월에 저장된 행이 없으면 `costItem: null`을 반환한다. 이전 월 제안값은 아래 업로드별 비용 입력 조회 API에서 제공하며, `null`은 세 비용을 모두 0으로 저장한 상태와 다르다. 응답 원가율은 화면과 같은 0~100 퍼센트 숫자다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","data":{"costItem":{"costMonth":"2026-09","rentAmount":1500000,"laborAmount":3000000,"ingredientCostRate":32.5,"updatedAt":"2026-09-08T14:00:00+09:00"}}}` |
| 200 | `{"message":"저장된 순수익 분석 정보가 없습니다.","data":{"costItem":null}}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"매장 정보를 찾을 수 없습니다.","data":null}` |

---

## SALES-05 · PUT `/v2/stores/me/cost-items/{costMonth}`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
costMonth (필수, path variable, YYYY-MM)
rentAmount (필수, 0 이상의 정수)
laborAmount (필수, 0 이상의 정수)
ingredientCostRate (필수, 0 이상 100 이하의 퍼센트 숫자, 소수점 첫째 자리까지)
```

**설명**

지정 월의 세 비용을 전체 저장하거나 교체하는 단일 월 API다. 세 값은 모두 필수이며 본인 매장에만 저장한다. 같은 매장·월은 중복 행을 만들지 않고 갱신한다. 업로드 직후 여러 대상 월을 한 번에 확인·저장하는 화면은 아래 업로드별 일괄 API를 사용하며, 개별 월 PUT을 반복 호출해 부분 저장을 만들지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"순수익 분석 정보가 저장되었습니다.","data":{"costItem":{"costMonth":"2026-09","rentAmount":1500000,"laborAmount":3000000,"ingredientCostRate":32.5,"updatedAt":"2026-09-08T14:05:00+09:00"},"next":"PROFIT_ANALYSIS"}}` |
| 201 | 신규 월 저장 시 위와 같은 `costItem` 반환 |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 400 | `{"message":"입력값을 확인해 주세요.","data":{"fieldErrors":[{"field":"ingredientCostRate","code":"OUT_OF_RANGE","message":"원가율은 0에서 100 사이로 입력해주세요."}]}}` |
| 500 | `{"message":"정보를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

`rentAmount`와 `laborAmount`는 소수·음수·문자·특수문자를 허용하지 않는다. 외부 API의 `ingredientCostRate`는 0 이상 100 이하, 소수점 첫째 자리까지 입력한다. 예: 요청 `32.5` → DB `0.3250`. DB는 기존 `DECIMAL(5,4)`와 `CHECK(ingredient_cost_rate BETWEEN 0 AND 1)`을 유지한다. 허용 자릿수를 넘는 값은 반올림 저장하지 않고 400으로 거절한다. DB의 `UNIQUE(store_id, cost_month)`로 중복 저장을 방지한다.

매출 파일 업로드가 성공해도 이전 월 비용을 DB에 자동 복사하지 않는다. 매출 발생 월의 비용이 없으면 가장 최근 이전 확정값을 **입력 화면의 미저장 제안값**으로만 제공한다. 사용자가 월별로 확인하고 저장해야 해당 월 비용이 확정된다.

---

## SALES-05 · GET `/v2/sales/uploads/{uploadId}/cost-items`

- **방향**: FE → BE
- **버전**: v2
- **목적**: 정상 검증 완료된 본인 매장 파일의 매출 발생 월별 비용 입력 상태를 조회한다. `uploadId`는 기존 `POST /v1/sales/uploads`의 응답 ID다.
- **응답**: `{"message":"조회에 성공했습니다.","data":{"uploadId":123,"months":[{"costMonth":"2026-08","rentAmount":1500000,"laborAmount":3000000,"ingredientCostRate":40,"source":"SAVED"},{"costMonth":"2026-09","rentAmount":1500000,"laborAmount":3000000,"ingredientCostRate":40,"source":"SUGGESTED"}]}}`
- `source`는 `SAVED`(해당 월 확정값), `SUGGESTED`(가장 최근 이전 확정 월의 미저장 제안값), `EMPTY`(이전 값도 없음) 중 하나다. `EMPTY`의 세 값은 `null`이다. 월 목록은 오름차순이며 업로드일이 아닌 파일의 매출 발생 월을 사용한다.
- 미완료·실패 업로드는 409, 존재하지 않거나 다른 매장의 업로드는 404, 세션 만료는 401이다. 조회만으로 새 비용 행을 만들지 않는다.

## SALES-05 · PUT `/v2/sales/uploads/{uploadId}/cost-items`

- **방향**: FE → BE
- **버전**: v2
- **요청**: `{"items":[{"costMonth":"2026-08","rentAmount":1500000,"laborAmount":3000000,"ingredientCostRate":40},{"costMonth":"2026-09","rentAmount":1600000,"laborAmount":3000000,"ingredientCostRate":35.5}]}`
- **검증**: 제출 월의 집합은 파일의 매출 발생 월 집합과 정확히 일치해야 하며 누락·중복·추가 월은 400이다. 각 월의 세 값은 필수다. 금액은 0 이상 원 단위 정수, 원가율은 0~100의 퍼센트 숫자·소수점 첫째 자리까지 허용한다. 필드 오류는 해당 `costMonth`와 `field`를 함께 반환한다.
- **저장**: 본인 매장 확인 후 전체 월의 비용을 **하나의 DB 트랜잭션**에서 저장·갱신한다. 실패 시 전체 롤백한다. 업로드에 없는 다른 월의 비용은 변경하지 않는다.
- **성공 응답**: `{"message":"순수익 분석 정보가 저장되었습니다.","data":{"uploadId":123,"costMonths":["2026-08","2026-09"],"next":"PROFIT_ANALYSIS"}}` (200).
- 미완료·실패 업로드는 409, 존재하지 않거나 다른 매장의 업로드는 404, 세션 만료는 401이다. 서버 저장 실패는 500이며 FE는 입력값을 유지한다.

## SALES-04 · GET `/v2/sales/analyses/month-options`

- **방향**: FE → BE
- **버전**: v2
- **요청 값**: 없음(세션 쿠키 필요)
- **설명**: 본인 매장의 정상 처리 완료된 업로드에서 매출 발생 월을 추출한다. 같은 월에 여러 완료 파일이 연결되면 업로드 시각이 가장 늦은 파일 한 건을 고르고, 동시각이면 업로드 ID가 큰 파일을 고른다. 처리 중·실패 파일은 제외한다. 한 파일이 여러 달의 매출을 포함하면 각 월의 선택지에 연결될 수 있다. 선택지는 월 오름차순으로 반환한다. 파일명은 UI 표시용이고 분석 수치는 해당 월의 현재 반영된 매출 집계를 사용한다. 주문이 0건인 정상 파일은 파일 기간에 포함된 월을 사용한다.
- **성공 응답**: `{"message":"조회에 성공했습니다.","data":{"months":[{"targetMonth":"2026-08","uploadId":123,"fileName":"매출.xlsx","uploadedAt":"2026-09-01T12:00:00+09:00"}]}}` (200). 선택지가 없으면 `months:[]`다.
- **오류**: 세션이 없으면 401. 다른 매장의 파일 정보는 반환하지 않는다.

## SALES-06 · GET `/v2/sales/profit-analyses`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
periodType (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate (CUSTOM일 때 필수, YYYY-MM-DD)
endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

선택 기간의 순수익 요약과 이전 기간 대비 증감률을 반환한다. 매출 기준은 완료·취소·비메뉴를 모두 합산한 `sales_daily_summaries.total_net_amount`다. 토스 POS 취소 행의 음수 금액은 해당 주문기준일자에 그대로 반영한다.

**계산 기준**

```
월별 재료비 = roundWon(해당 월의 선택 기간 순매출 × 해당 월 원가율)
월별 배분 고정비 = roundWon((월 임대료 + 월 인건비) × 선택 기간에 포함된 그 월의 일수 ÷ 그 월의 전체 일수)
순이익 = 선택 기간 순매출 − Σ(월별 재료비) − Σ(월별 배분 고정비)
순이익률 = 순이익 ÷ 순매출 (순매출이 0이면 null)
전기 대비 순이익 증감률 = (당기 순이익 − 전기 순이익) ÷ |전기 순이익| (전기 순이익이 0이거나 계산 불가하면 null)
```

`roundWon`은 `BigDecimal`의 원 단위 `HALF_UP` 반올림이며, 월별 재료비와 배분 고정비를 각각 한 번 반올림한 뒤 합산한다. 날짜 양끝을 모두 포함하고 윤년을 반영한다. 음수 취소 매출은 그대로 합산한다. 비율 응답은 백분율 숫자가 아닌 소수로 표현하고 소수점 넷째 자리까지 `HALF_UP` 반올림한다.

선택 기간에 포함된 월의 비용 행이 없으면 기존 `COST_INPUT_REQUIRED`와 `missingCostMonths`를 반환하고 순이익 금액·일별 그래프·인사이트를 계산하지 않는다. 전기 비용만 부족하면 당기 순이익은 반환하고 전기 대비 증감률은 `null`이다. 비용이 모두 있으나 매출 집계 행이 전혀 없는 기간은 `EMPTY`다. 0원으로 저장한 비용은 입력 완료로 간주하며, 매출 합계 0원은 매출 집계 행 없음과 구분한다. 공과금과 카드·배달 수수료는 V2 계산에 포함하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","status":"COMPLETED","data":{"summary":{"totalNetAmount":40350532,"ingredientCost":13113923,"fixedCost":4500000,"netProfit":22736609}}}` |
| 200 | `{"message":"순수익 분석 정보를 입력해주세요.","status":"COST_INPUT_REQUIRED","data":{"missingCostMonths":["2026-05"]}}` |
| 200 | `{"message":"선택 기간에 매출 데이터가 없습니다.","status":"EMPTY","data":null}` |
| 400 | `{"message":"조회 기간이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |

`COMPLETED`의 `data.summary`에는 `totalNetAmount`, `ingredientCost`, `fixedCost`, `totalCost`(재료비+고정비), `netProfit`, `netProfitRate`를 포함한다. 전월 비교값은 `previousNetProfit`, `netProfitChangeRate`, `previousTotalCost`, `totalCostChangeRate`, `previousNetProfitRate`, `netProfitRateDifference`다. 금액 증감률은 `(당월 값−전월 값)÷|전월 값|`이며 전월 값이 없거나 0원이면 `null`이다. `netProfitRateDifference`는 당월 순이익률과 전월 순이익률의 차이인 소수 비율로 반환하며 FE가 100을 곱해 `%p`로 표시한다. 총매출 0원이면 해당 월 순이익률은 `null`이다. 비율은 0~1로 제한하지 않고 소수점 넷째 자리까지 `HALF_UP`으로 표현한다. 전월 매출·비용이 부족하면 전월 비교값 전체를 `null`로 제공한다.

`data.dailyProfits`는 선택 기간의 날짜별 `{date, netProfit}` 배열이다. 매출이 없는 날도 포함하며 비용을 배분해 음수 순이익이 될 수 있다. 일별 순이익 합계는 같은 응답의 `summary.netProfit`과 원 단위까지 일치해야 한다.

`data.weekdayProfits`는 `{dayOfWeek, netProfit}` 배열이며 `MONDAY`부터 `SUNDAY`까지 7개를 고정 순서로 제공한다. 해당 요일의 일별 순이익을 합산하며 전체 합계는 `summary.netProfit`과 원 단위까지 일치한다.

`data.aiInsight`는 `{status, insights}` 형식의 문장형 인사이트이며 계산 완료된 지표만 해석한다. 인사이트가 아직 없거나 생성에 실패해도 금액·그래프 응답은 유지한다. `COST_INPUT_REQUIRED`·`EMPTY`에서는 일별·요일별 순이익과 인사이트를 제공하지 않는다. 메뉴별·시간대별 순이익은 근거 데이터와 배분 정책이 마련되기 전까지 응답에 숫자를 제공하지 않고 FE에서 미지원 상태로 표시한다.

---

## SALES-06 · POST `/internal/v2/profit-analysis-jobs`

- **방향**: BE → 분석 모듈
- **버전**: v2

**요청 값**

```
storeId (필수)
startDate, endDate (필수)
totalNetSalesByDate (필수, 음수 취소 행을 포함한 일별 total_net_amount)
monthlyCostItems (필수, 기간에 포함된 월별 비용)
```

**설명**

BE 서버 코드가 순수익·구성 비율·일별 추이를 계산한다. 금액 계산은 생성형 AI에 맡기지 않으며 AI에는 계산 완료 지표만 전달한다. 이 내부 작업 API는 분석 모듈 분리 시 사용하는 계약으로 남기며, 같은 BE 프로세스에서 계산할 때는 별도 HTTP 호출을 요구하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"status":"COMPLETED","data":{"summary":{"totalNetAmount":40350532,"ingredientCost":13113923,"fixedCost":4500000,"netProfit":22736609}}}` |
| 422 | `{"message":"비용 정보 또는 매출 집계값이 올바르지 않습니다.","data":null}` |

---

## SALES-06 · POST `/internal/v2/ai/profit-insights`

- **방향**: BE → AI
- **버전**: v2
- **인증**: 기존 BE→AI 내부 Bearer 토큰

**요청 값**

```json
{
  "storeId": 1,
  "period": {"startDate": "2026-01-01", "endDate": "2026-01-01"},
  "summary": {
    "totalNetAmount": 1000000,
    "ingredientCost": 300000,
    "fixedCost": 100000,
    "netProfit": 600000,
    "netProfitRate": 0.6,
    "previousNetProfit": 500000,
    "netProfitChangeRate": 0.2
  },
  "dailyProfits": [{"date": "2026-01-01", "netProfit": 600000}],
  "maxInsightCount": 3
}
```

`storeId`, `period.startDate`, `period.endDate`, `summary`, `dailyProfits`, `maxInsightCount`는 필수다. 날짜는 `YYYY-MM-DD`이며 시작일과 종료일을 모두 포함한다. `dailyProfits`는 기간 내 날짜 오름차순이고 매출이 없는 날짜도 포함한다. 금액은 BE가 계산한 원 단위 정수로 음수를 허용하며, 비율은 백분율이 아닌 소수다. `previousNetProfit`와 `netProfitChangeRate`는 비교 기간을 계산할 수 없으면 `null`이다. `maxInsightCount`는 3으로 전달한다.

**설명**

BE가 업로드 파일을 파싱하고 매출을 집계한 뒤, 월 비용을 반영해 순이익과 비교 지표를 계산한다. AI에는 위 계산 완료 지표만 전송한다. 원본 파일·주문별 거래·월 임대료·인건비·원가율 입력값은 보내지 않는다. AI는 전달받은 값만 근거로 한국어 존댓말 인사이트 문장 1~3개를 작성하며 금액·비율을 재계산하거나 확인되지 않은 원인을 추정하지 않는다. 각 문장은 100자 이하다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"status":"COMPLETED","data":{"insights":["선택 기간의 예상 순이익은 600,000원이에요."]}}` |
| 200 | `{"status":"INSUFFICIENT_DATA","data":{"insights":[]}}` |
| 401 | `{"message":"내부 인증에 실패했습니다.","data":null}` |
| 422 | `{"message":"순이익 인사이트 입력값이 올바르지 않습니다.","data":null}` |
| 500 | `{"message":"순이익 인사이트 생성에 실패했습니다.","data":null}` |

BE는 `COST_INPUT_REQUIRED` 또는 `EMPTY`이면 AI를 호출하지 않는다. AI 호출 실패·타임아웃은 `GET /v2/sales/profit-analyses`의 `data.aiInsight={"status":"FAILED","insights":[]}`로 격리하고, 순이익 KPI·그래프는 그대로 반환한다. AI가 `INSUFFICIENT_DATA`를 반환하면 같은 상태와 빈 `insights`를 전달한다. 기존 매출 인사이트 `/internal/v1/ai/sales-insights`와 분리한다.

---

# SOL · 솔루션 생성 입력 확장 [V2]

> 🚧 **V2 상세 계약 확정 대기:** 날씨 연동, 공휴일 반영, 요일·시간대 패턴 심화, 주변 상권 데이터 분석은 요구사항에 V2 후보로 있으나 데이터 제공처·수집 주기·필드·실패 대체 규칙이 미정이다. 아래 내부 API의 `weatherContext`, `holidayContext`, `districtBenchmark`는 확장 자리만 예약하며 확정 계약으로 간주하지 않는다. 요일·시간대 심화 패턴은 상세 사양 확정 후 별도 필드를 추가한다. 외부 데이터가 없더라도 V1 매출 분석과 솔루션 조회는 실패시키지 않는다.
> 

## SALES-01, SALES-04, SOL-01, SOL-02 · POST `/internal/v2/ai/solutions/generate`

- **방향**: BE → AI
- **버전**: v2

**요청 값**

```
v1의 공통 필수값(`storeId`, `salesAnalysisId`, `targetDate`, `triggerType`, `metrics`)에 아래 항목을 추가한다. weatherContext (선택, targetDate 기준 당일 날씨/강수 데이터) holidayContext (선택, targetDate가 공휴일인지 여부) districtBenchmark (선택, 동일 상권·동종업종 평균 대비 지표)
```

**설명**

매일 바뀌는 날씨·공휴일과 상권 벤치마크를 지표에 추가해 솔루션 카드의 근거를 보강한다. `salesAnalysisId`는 v1과 동일하게 `sales_analyses.id`를 의미하며, BE가 솔루션 묶음·카드를 해당 분석 결과에 연결해 저장한다. costInputs(임대료/인건비/원가율)는 AI로 보내지 않고 BE 분석 모듈의 순이익 계산(/internal/v1/profit)에만 쓰인다 — 계산은 코드가, 해석은 모델이 담당한다는 원칙 유지. 외부 데이터를 BE가 수집해 전달할지, AI가 직접 호출할지는 팀 확정 필요

**설계 근거**

v1과 동일한 엔드포인트를 유지하고 요청 metrics에 필드를 선택값으로 추가하는 방식으로 확장해(무버전 경로에 필드만 늘리는 하위호환 확장) 클라이언트 변경을 최소화했다. costInputs처럼 계산이 필요한 값은 AI로 보내지 않고 BE 계산 결과만 전달해 "계산은 코드, 해석은 모델" 원칙을 v2에서도 그대로 유지했다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"솔루션을 생성했습니다.","data":{"solutionCards":[{"rank":1,"title":"점심 시간대 할인"}],"aiInsight":"날씨와 공휴일 정보를 반영했습니다."}}` |
| 422 | `{"message":"확장 필드 형식이 올바르지 않습니다.","data":null}` |

---

# RANK · 성장 랭킹 [V2]

성장 랭킹은 선택 기간과 비교 기간의 매출 성장률로 산정한다. 로그인 사용자는 익명 랭킹 상위 20위와 본인 매장의 순위를 조회할 수 있다. 다른 매장의 실제 매장명, 사용자 이름, 이메일, 사업자 정보, 주소, 매출액 및 상세 운영 정보는 외부 응답에 포함하지 않는다.

## 성장 랭킹 정책

- **목록·페이지네이션:** 상위 20개를 한 번에 반환하고 `myRanking`은 별도 제공한다. 현재는 페이지네이션을 사용하지 않는다.
- **성장률:** `(선택 기간 매출-비교 기간 매출)÷비교 기간 매출×100`으로 계산한다. API는 소수 첫째 자리의 퍼센트 숫자(예: `28.5`)를 반환하고 FE는 그대로 `28.5%`로 표시한다.
- **기간:** 한국 시간(`Asia/Seoul`) 기준 지난달 전체와 지지난달 전체만 비교한다. 이번 달 진행 중 랭킹과 기간 선택은 제공하지 않는다.
- **참여:** 날짜별 상태는 `COMPLETE`(매출 0원 포함), `CLOSED`, `MISSING`, `UNKNOWN`으로 관리한다. `CLOSED`는 영업일 검사에서 제외한다. 두 기간 분석 미완료 매장은 `ANALYSIS_NOT_COMPLETED`, 필요한 영업일에 `MISSING`/`UNKNOWN`이 있으면 `DATA_INCOMPLETE`로 제외한다. 비교 매출 0원은 `COMPARISON_SALES_ZERO`로 제외하며 취소·환불은 매출에서 뺀다.
- **재계산:** 관련 월의 매출 업로드·분석 완료 또는 월 전환 시 전체 랭킹을 새 revision으로 계산한다. 날짜가 매일 바뀐다는 이유만으로 재계산하지 않으며, 완료 전에는 이전 완료 결과를 유지한다.
- **순위·알림:** 성장률·선택 기간 매출 내림차순, 완전 동률은 `RANK`(`1,1,3`). 완료 스냅샷 간 `ENTERED`·`UP`·`DOWN`을 비교하고 사용자·기간·기준일별로 멱등 처리한다.

---

## RANK-01, RANK-02 · GET `/v2/rankings/growth`

- **방향**: FE → BE
- **버전**: v2

**요청 값**

```
없음 (지난달 랭킹 고정; 페이지네이션 없음)
```

**설명**

지난달 전체와 지지난달 전체의 성장 랭킹을 조회한다. 상위 20위와 본인 순위를 한 번에 반환하며 기간 선택과 페이지네이션 파라미터는 사용하지 않는다.

응답 period.type은 `LAST_MONTH`이고 실제 선택·비교 기간 및 마지막 완료 스냅샷의 `calculatedAt`을 포함한다. 월이 바뀌면 조회 기간을 전환하고, 늦은 업로드·재분석으로 순위가 바뀌면 새 revision을 공개한다. 새 스냅샷 계산 중에는 이전 완료 결과를 유지한다.

**성장률 계산식과 반환 단위**

```
growthRate = (selectedPeriodSales - comparisonPeriodSales) / comparisonPeriodSales * 100
```

순위는 반올림 전 성장률로 계산한다. API의 `growthRate`는 소수 첫째 자리까지 반올림한 퍼센트 숫자로 반환한다. 예: `28.45`는 `28.5`로 반환하고, FE는 추가 변환 없이 `28.5%`로 표시한다.

**집계 및 공개 기준**

- 일별 상태는 ERD의 `sales_daily_summaries.day_status`에서 관리한다: `COMPLETE`(해당 일자 데이터 처리 완료, 매출 0원 포함), `CLOSED`(휴무 확인), `MISSING`(영업일 데이터 누락), `UNKNOWN`(상태 판정 근거 부족). 이 내부 필드는 API 응답에 노출하지 않는다.
- 두 기간의 분석이 완료된 매장만 집계한다. `CLOSED`는 영업일 완전성 검사에서 제외하며, 필요한 영업일에 `MISSING`/`UNKNOWN`이 하나라도 있으면 제외하고 myEligibility.reason=DATA_INCOMPLETE로 반환한다. 근거 없는 과거 이력은 `UNKNOWN`으로 두고 참여시키지 않는다. 분석 미완료는 ANALYSIS_NOT_COMPLETED, 비교 기간 매출 0원은 COMPARISON_SALES_ZERO로 제외한다.
- 취소·환불 주문은 매출 합계에서 제외한다.
- 성장률 내림차순, 선택 기간 매출 내림차순으로 정렬하고, 두 값이 같으면 경쟁 순위(RANK)를 적용한다.
- 다른 매장은 익명 닉네임, 순위, 성장률만 반환한다. 본인 항목은 displayName=내 매장으로 표시한다. 매출액은 응답에 포함하지 않는다.

**설계 근거**

랭킹 스냅샷은 ranking_snapshots와 ranking_entries에 보존하고, 익명 닉네임과 참여 상태는 ranking_profiles를 사용한다. 각 재계산은 새 revision으로 저장하며 완료된 최신 스냅샷만 공개한다. 목록과 본인 순위를 한 번의 응답으로 제공한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","status":"COMPLETED","data":{"isFinal":true,"period":{"type":"LAST_MONTH","startDate":"2026-09-01","endDate":"2026-09-30","comparisonStartDate":"2026-08-01","comparisonEndDate":"2026-08-31","calculatedAt":"2026-10-06T00:10:00+09:00"},"rankings":[{"rank":1,"displayName":"사장님 184","growthRate":28.5,"isMine":false},{"rank":2,"displayName":"내 매장","growthRate":24.1,"isMine":true}],"myRanking":{"rank":2,"growthRate":24.1,"includedInTop20":true},"myEligibility":{"status":"ELIGIBLE","reason":null}}}` |
| 200 | `{"message":"아직 순위 정보가 없어요. 매출 데이터를 등록하면 랭킹에 참여할 수 있어요.","status":"COMPLETED","data":{"isFinal":true,"period":{"type":"LAST_MONTH","startDate":"2026-09-01","endDate":"2026-09-30","comparisonStartDate":"2026-08-01","comparisonEndDate":"2026-08-31","calculatedAt":"2026-10-06T00:10:00+09:00"},"rankings":[],"myRanking":null,"myEligibility":{"status":"DATA_INSUFFICIENT","reason":"DATA_INCOMPLETE"}}}` |
| 200 | `{"message":"아직 성장 랭킹이 집계되지 않았어요.","status":"NOT_CALCULATED","data":{"isFinal":true,"period":{"type":"LAST_MONTH","startDate":"2026-09-01","endDate":"2026-09-30","comparisonStartDate":"2026-08-01","comparisonEndDate":"2026-08-31","calculatedAt":null},"rankings":[],"myRanking":null,"myEligibility":{"status":"UNKNOWN","reason":null}}}` |
| 200 | `{"message":"성장 랭킹을 집계하고 있습니다.","status":"PROCESSING","data":{"isFinal":true,"period":{"type":"LAST_MONTH","startDate":"2026-09-01","endDate":"2026-09-30","comparisonStartDate":"2026-08-01","comparisonEndDate":"2026-08-31","calculatedAt":null},"rankings":[],"myRanking":null,"myEligibility":{"status":"UNKNOWN","reason":null}}}` |
| 200 | `{"message":"성장 랭킹을 집계하지 못했습니다. 잠시 후 다시 시도해주세요.","status":"FAILED","data":{"isFinal":true,"period":{"type":"LAST_MONTH","startDate":"2026-09-01","endDate":"2026-09-30","comparisonStartDate":"2026-08-01","comparisonEndDate":"2026-08-31","calculatedAt":null},"rankings":[],"myRanking":null,"myEligibility":{"status":"UNKNOWN","reason":null}}}` |
| 400 | `{"message":"지원하지 않는 조회 조건입니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 500 | `{"message":"성장 랭킹을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.","data":null}` |

isFinal은 비교하는 월이 모두 종료되었음을 뜻하는 true다. 늦은 매출 업로드로 순위가 바뀌지 않는다는 의미는 아니다. 상위 20위 밖이어도 myRanking을 반환하고 includedInTop20=false로 표시한다. myEligibility.reason은 SELECTED_PERIOD_MISSING, COMPARISON_PERIOD_MISSING, DATA_INCOMPLETE, COMPARISON_SALES_ZERO, ANALYSIS_NOT_COMPLETED 중 하나다.

---

## 랭킹 집계·갱신 정책

- 매출 업로드와 분석 완료 후 해당 기간의 전체 매장 랭킹을 다시 계산한다. 한 매장의 데이터 변경도 다른 매장의 상대 순위에 영향을 준다.
- 매월 1일 한국 시간 기준으로 조회 대상을 새로운 지난달·지지난달로 전환한다. 해당 기간의 업로드·분석 완료 시 재계산하며, 매일 날짜 변경만으로는 재계산하지 않는다.
- 집계 시작 시 ranking_snapshots.status=PROCESSING으로 기록하고, 새 ranking_entries 저장과 함께 COMPLETED로 전환한다. 이전 완료 스냅샷은 새 계산 완료 전까지 유지한다.
- 새 계산마다 별도 revision 스냅샷을 보존한다. 집계 실패는 FAILED로 기록하고 임의 결과를 생성하지 않는다.
- 랭킹 프로필이 없는 참여 매장에는 중복되지 않는 사장님 {번호} 익명 닉네임을 생성한다.

---

# RANK · 랭킹 순위 변동 알림 [V2]

별도 외부 알림 API를 추가하지 않고 NOTI 목록·읽음 처리·수신 설정 API를 사용한다.

- 알림 조회: GET `/v1/notifications`; 읽음 처리: PATCH `/v1/notifications`; 수신 설정: GET/PATCH `/v1/notification-preferences`의 rankingChangeEnabled
- 알림 유형은 RANKING_CHANGED, 연결 대상은 RANKING_SNAPSHOT이다.

## 발생 조건

- 매일 08:00(KST)에 전날의 마지막 COMPLETED 스냅샷과 그 전날의 마지막 COMPLETED 스냅샷을 비교한다. 두 스냅샷은 period_start, period_end, comparison_start, comparison_end가 모두 같은 랭킹 기간이어야 한다.
- 월초 새 랭킹 기간의 첫 COMPLETED 스냅샷처럼 비교 가능한 이전 스냅샷이 없으면 알림을 생성하지 않는다.
- 두 스냅샷 모두 포함된 매장의 rank_no가 바뀌면 상승은 UP, 하락은 DOWN으로 알림함에 생성한다. 이전 스냅샷에는 없고 현재 스냅샷에는 처음 포함된 매장은 ENTERED다. 순위가 같으면 성장률이 달라져도 알림을 만들지 않으며, 현재 스냅샷에서 제외된 매장도 알림 대상이 아니다.
- ranking_change_enabled=true인 사용자에게만 생성한다. PENDING, PROCESSING, FAILED 스냅샷은 비교하지 않는다.
- 같은 사용자·랭킹 기간·기준일 조합당 알림을 한 건만 생성한다. 기준일은 비교 대상인 전날이며 멱등 키는 RANKING_CHANGED:{userId}:{period}:{baseDate} 형식을 사용한다.
- V2에서는 세 알림 유형 모두 DB에 저장한 뒤 NOTI-03 SSE 연결로 접속 중인 사용자에게 전달한다. 알림 이력 조회와 읽음 처리는 기존 GET/PATCH REST API를 사용한다. FCM 푸시는 V3에서 앱·브라우저가 닫힌 상태의 전달을 위해 추가한다.
- 랭킹 조회 API는 요청 시점의 최신 COMPLETED 스냅샷을 반환하므로, 재계산 완료 뒤 다음 API 조회에서 새 순위를 확인할 수 있다.

## 변동 유형

<table fit-page-width="true" header-row="true"><tr><td>changeType</td><td>조건</td><td>문구 예시</td></tr><tr><td>UP</td><td>현재 순위가 이전보다 높음</td><td>지난 집계보다 3단계 오른 5위예요.</td></tr><tr><td>DOWN</td><td>현재 순위가 이전보다 낮음</td><td>지난 집계보다 2단계 내려갔어요.</td></tr><tr><td>ENTERED</td><td>직전 미포함, 신규 집계 포함</td><td>성장 랭킹에 처음 진입했어요.</td></tr></table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

</table>

## 알림 응답 예시

GET `/v1/notifications` 항목에 포함한다.

```json
{"id":1215,"type":"RANKING_CHANGED","title":"성장 랭킹 순위가 올랐어요","content":"지난 집계보다 3단계 오른 5위예요.","relatedEntityType":"RANKING_SNAPSHOT","relatedEntityId":87,"sentAt":"2026-10-06T08:00:00+09:00","readAt":null}
```

## 중복 방지 및 재처리

- 멱등키는 RANKING_CHANGED:{userId}:{period}:{baseDate} 형식으로 한다.
- 같은 사용자·기간·기준일의 재계산·재시도에도 알림은 한 건만 유지한다.
- 알림 생성과 멱등키 저장을 트랜잭션 또는 유니크 제약으로 원자적으로 처리한다.
- 집계 실패 시 알림을 만들지 않고 재처리 성공 후 동일 멱등키로 생성한다.

## 랭킹 화면 연결

- 알림을 선택하면 RANK-01 성장 랭킹으로 이동한다.
- 연결된 랭킹은 지난달 전체와 지지난달 전체를 비교하는 화면으로 이동한다.
- 이동 후 랭킹 데이터는 RANK-01 API에서 새로 조회한다.
- 다른 사용자의 알림 ID를 이용해도 본인에게 허용된 익명 랭킹 정보 외에는 반환하지 않는다.

---

# V3 API

# SALES · 리뷰 분석 (SALES) [V3]

<aside>
⚠️

네이버 리뷰 수집은 이용약관·robots 정책·저작권·개인정보 처리 기준을 검토하고 허용된 방식으로만 운영한다. 수집이 허용되지 않거나 실패하더라도 기존 SALES·SOL 기능은 중단하지 않는다. 요구사항에는 리뷰 이미지 수집이 포함되어 있으나 현재 ERD의 reviews에는 이미지 저장 구조가 없으므로 구현 전 review_images 관계 테이블 또는 동등한 저장 구조를 추가해야 한다.

</aside>

## SALES-07 · GET `/v3/sales/review-analyses/latest`

- **방향**: FE → BE
- **버전**: v3

**요청 값**

```
(없음, 세션 사용자 매장 기준)
```

**설명**

가장 최근 리뷰 수집·분석 결과를 조회한다. 분석 상태는 `PROCESSING`, `COMPLETED`, `EMPTY`, `FAILED` 중 하나다. 별점 4~5점은 긍정, 3점은 중립, 2점 이하는 부정으로 분류한다. 비율은 0~1 범위의 소수로 표현하고 소수점 넷째 자리까지 반올림한다. 별점 없는 리뷰는 AI 요약에는 포함하지만 비율의 분모에서는 제외하고 `ratedReviewCount`로 별도 공개한다. AI 요약은 300자 미만, 관련 리뷰는 최대 3개를 반환한다.

**설계 근거**

리뷰 수집·분석은 비동기 작업이므로 최신 결과를 상태값과 함께 조회한다. 수집 실패를 기존 매출·솔루션 기능의 실패로 전파하지 않고, 상태와 실패 단계를 명시해 FE가 재시도 안내 또는 이전 화면을 유지할 수 있게 한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"리뷰 분석 결과를 조회했습니다.","status":"COMPLETED","data":{"analysisRunId":81,"collectedAt":"2026-09-08T03:00:00+09:00","reviewCount":42,"ratedReviewCount":39,"sentiment":{"positiveRate":0.6154,"neutralRate":0.2051,"negativeRate":0.1795},"summary":"친절한 응대와 커피 맛에 대한 긍정 리뷰가 많습니다.","relatedReviews":[{"reviewId":301,"rating":5,"content":"커피가 맛있고 직원분이 친절해요.","createdAt":"2026-09-07T14:20:00+09:00"}]}}`  |
| 200 | `{"message":"리뷰를 수집·분석하고 있습니다.","status":"PROCESSING","data":null}` |
| 200 | `{"message":"분석할 리뷰 데이터가 없습니다.","status":"EMPTY","data":null}` |
| 200 | `{"message":"리뷰 수집 또는 분석에 실패했습니다.","status":"FAILED","failStage":"COLLECTION","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 404 | `{"message":"매장 정보를 찾을 수 없습니다.","data":null}` |
| 500 | `{"message":"리뷰 분석 결과를 불러오지 못했습니다.","data":null}` |

---

## SALES-07 · POST `/internal/v3/review-collection-jobs`

- **방향**: Scheduler → BE/수집 모듈
- **버전**: v3

**요청 값**

```
targetDate (필수, YYYY-MM-DD)
triggerType (필수, DAILY | RETRY)
storeId (선택, RETRY 시 특정 매장 재처리)
```

**설명**

일일 리뷰 수집·분석 작업을 접수한다. `DAILY`는 대상 매장 전체, `RETRY`는 실패한 특정 매장을 재처리한다.

**설계 근거**

수집은 장시간 실행될 수 있으므로 작업 리소스를 생성하고 202로 즉시 응답한다. 같은 대상·날짜의 중복 작업은 409로 차단해 수집 중복과 외부 서비스 요청 폭주를 방지한다.

**응답**

| status | body |
| --- | --- |
| 202 | `{"message":"리뷰 수집 작업을 시작했습니다.","jobId":"review_job_20260908_01","status":"QUEUED","data":{"targetDate":"2026-09-08","triggerType":"DAILY"}}` |
| 409 | `{"message":"동일한 리뷰 수집 작업이 이미 진행 중입니다.","jobId":"review_job_20260908_01","data":null}` |
| 422 | `{"message":"재처리할 매장 정보가 올바르지 않습니다.","data":null}` |

---

## SALES-07 · GET `/internal/v3/review-collection-jobs/{jobId}`

- **방향**: 관리자 도구·Scheduler → BE
- **버전**: v3

**요청 값**

```
jobId (필수, path parameter)
```

**설명**

리뷰 수집 작업의 진행 상태와 집계 결과를 조회한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"리뷰 수집 작업을 조회했습니다.","data":{"jobId":"review_job_20260908_01","status":"COMPLETED","targetDate":"2026-09-08","totalStoreCount":120,"successStoreCount":116,"failedStoreCount":4,"startedAt":"2026-09-08T03:00:00+09:00","completedAt":"2026-09-08T03:20:00+09:00"}}` |
| 404 | `{"message":"리뷰 수집 작업을 찾을 수 없습니다.","data":null}` |

---

## SALES-07 · POST `/internal/v3/ai/reviews/summarize`

- **방향**: BE → AI
- **버전**: v3

**요청 값**

```
storeId (필수)
analysisRunId (필수)
reviews (필수, reviewId·rating·content·createdAt 배열)
maxSummaryCharacters (필수, 299)
relatedReviewTopK (필수, 3)
```

**설명**

수집한 리뷰를 기반으로 감성 비율 설명, 300자 미만 요약, 관련 리뷰 최대 3개를 생성한다. 리뷰 원문과 응답은 개인정보·민감정보를 포함하지 않도록 정제한다.

**설계 근거**

AI는 서술형 해석만 담당하고, 상태 관리·저장·비율 계산은 BE가 수행한다. 요약 길이와 관련 리뷰 수를 요청값으로 제한해 화면 계약과 비용을 안정화한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"status":"COMPLETED","data":{"summary":"친절한 응대와 커피 맛에 대한 긍정 리뷰가 많습니다.","sentimentHighlights":["친절한 응대","커피 맛"],"relatedReviewIds":[301,304,318]}}` |
| 422 | `{"message":"리뷰 분석 입력값이 올바르지 않습니다.","data":null}` |
| 500 | `{"message":"AI 리뷰 요약 생성에 실패했습니다.","data":null}` |
| 504 | `{"message":"AI 리뷰 요약 생성 시간이 초과되었습니다.","data":null}` |

---

## SALES-04, SALES-07 · GET `/v3/sales/analyses`

- **방향**: FE → BE
- **버전**: v3

**요청 값**

```
periodType (필수, TODAY | THIS_WEEK | THIS_MONTH | CUSTOM)
startDate, endDate (CUSTOM일 때 필수, YYYY-MM-DD)
```

**설명**

V1 매출 분석 응답에 `reviewInsight`을 확장해 조회한다. 매출 분석 결과와 리뷰 분석의 최신 완료 결과를 함께 제공하되, 리뷰 수집·분석이 없거나 실패했어도 매출 분석 결과는 정상 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"조회에 성공했습니다.","status":"COMPLETED","data":{"salesAnalysis":{"summary":{"salesAmount":3200000}},"reviewInsight":{"status":"COMPLETED","summary":"친절한 응대와 커피 맛에 대한 긍정 리뷰가 많습니다.","positiveRate":0.6154,"negativeRate":0.1795,"relatedReviewCount":3}}}` |
| 200 | `{"message":"매출 분석 결과를 조회했습니다.","status":"COMPLETED","data":{"salesAnalysis":{"summary":{"salesAmount":3200000}},"reviewInsight":{"status":"EMPTY","summary":null,"positiveRate":null,"negativeRate":null,"relatedReviewCount":0}}}` |
| 400 | `{"message":"조회 기간이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 500 | `{"message":"매출 분석 결과를 불러오지 못했습니다.","data":null}` |

# SOL · 리뷰 기반 솔루션 입력 확장 [V3]

## SALES-07, SOL-01, SOL-02 · POST `/internal/v3/ai/solutions/generate`

- **방향**: BE → AI
- **버전**: v3

**요청 값**

```
V2 공통 필수값(storeId, salesAnalysisId, targetDate, triggerType, metrics)
reviewContext (선택, reviewAnalysisId·status·summary·sentiment·relatedReviews)
```

**설명**

V2 솔루션 생성 입력에 최신 리뷰 분석 결과를 선택적으로 추가한다. `reviewContext.status=COMPLETED`일 때만 감성 요약·관련 리뷰를 전달하며, `EMPTY`·`FAILED`이면 리뷰 맥락 없이 V2 수준의 솔루션을 생성한다.

**설계 근거**

리뷰 수집 상태가 SOL 기능 전체 실패로 이어지지 않도록 선택 필드로 확장한다. AI에는 필요한 최소 리뷰 정보만 전달하고, 수집 원문·개인정보는 전달하지 않는다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"리뷰 분석을 반영한 솔루션을 생성했습니다.","data":{"solutionCards":[{"rank":1,"title":"친절 응대 강점 홍보","reason":"긍정 리뷰에서 친절한 응대가 반복 언급되었습니다."}],"reviewContextApplied":true}}` |
| 422 | `{"message":"리뷰 기반 솔루션 입력값이 올바르지 않습니다.","data":null}` |

# SALES · 매출 달력 (SALES) [V3]

## SALES-08 · GET `/v3/sales/calendar`

- **방향**: FE → BE
- **버전**: v3

**요청 값**

```
month (필수, YYYY-MM)
```

**설명**

선택한 월의 일자별 매출 달력을 조회한다. `salesAmount`는 완료·취소·비메뉴를 모두 합산한 `sales_daily_summaries.total_net_amount`다. 취소 행의 음수 금액은 주문기준일자에 반영한다. 커버리지 안의 매출 없는 날은 0원·0건으로 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"매출 달력을 조회했습니다.","status":"COMPLETED","data":{"month":"2026-05","days":[{"date":"2026-05-31","salesAmount":1875100,"orderCount":133,"analysisStatus":"COMPLETED"}],"monthlySalesAmount":40350532,"monthlyOrderCount":2799}}` |
| 200 | `{"message":"해당 월의 매출 데이터가 없습니다.","status":"EMPTY","data":{"month":"2026-05","days":[],"monthlySalesAmount":0,"monthlyOrderCount":0}}` |
| 400 | `{"message":"조회 월 형식이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 416 | `{"message":"조회 가능한 매출 기간을 벗어났습니다.","data":null}` |

---

## SALES-08 · GET `/v3/sales/calendar/days/{date}`

- **방향**: FE → BE
- **버전**: v3

**요청 값**

```
date (필수, path parameter, YYYY-MM-DD)
```

**설명**

선택한 하루의 `total_net_amount`, 유효 주문 수와 분석 요약을 조회한다. 데이터가 없으면 0원·0건과 `EMPTY`를 반환한다.

**응답**

| status | body |
| --- | --- |
| 200 | `{"message":"일별 매출 정보를 조회했습니다.","status":"COMPLETED","data":{"date":"2026-05-31","salesAmount":1875100,"orderCount":133,"analysis":{"summary":"점심 시간대 메뉴 매출이 높았습니다."}}}` |
| 200 | `{"message":"해당 날짜의 매출 데이터가 없습니다.","status":"EMPTY","data":{"date":"2026-05-31","salesAmount":0,"orderCount":0,"analysis":null}}` |
| 400 | `{"message":"조회 날짜 형식이 올바르지 않습니다.","data":null}` |
| 401 | `{"message":"로그인이 필요합니다.","data":null}` |
| 416 | `{"message":"조회 가능한 매출 기간을 벗어났습니다.","data":null}` |

## 매출 달력 날씨·집계 정책

- 매출은 `total_net_amount`를 사용하고 취소 행의 음수 금액을 제외하지 않는다.
- 달력의 데이터 없음은 오류가 아니며 금액 0·주문 0과 `EMPTY`로 구분한다.
- 날짜별 분석이 처리 중이면 `analysisStatus=PROCESSING`으로 반환한다.
- 날씨·공휴일 데이터가 없거나 실패해도 기본 달력 매출 조회는 실패시키지 않는다.