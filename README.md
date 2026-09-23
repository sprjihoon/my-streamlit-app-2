# my-streamlit-app (tillion.io.kr)

## 배포 정책 ⚠️

### ✅ 허용: Vercel + Railway 배포

```bash
# main 브랜치에 push하면 자동 배포
git push origin main
```

- **Vercel** (프론트엔드): main 브랜치 push → 자동 빌드·배포
- **Railway** (백엔드): main 브랜치 push → Docker 빌드·자동 배포

### ❌ 금지: 로컬 배포

```bash
# 아래 명령어는 로컬 개발용이며 배포에 사용하지 않는다
npm run build   # ❌ 로컬 빌드 금지
npm run start   # ❌ 로컬 서버 실행은 개발용으로만
```

로컬에서 빌드하거나 `.next` 빌드 결과를 직접 배포하지 않는다.  
모든 배포는 **GitHub main 브랜치 push → Vercel/Railway 자동 CI/CD**로만 진행한다.

---

## ⚠️ Railway 네트워크 제약 — 우체국 API 호출 아키텍처

> **차후 개발 필독**: Railway 서버에서 직접 우체국 API를 호출하면 차단됩니다.

### 차단되는 경로

| 호출 대상 | 도메인 | 상태 |
|-----------|--------|------|
| 우체국 계약소포 API | `ship.epost.go.kr` | ❌ Railway(싱가포르)에서 직접 호출 차단 |
| 우체국 EMS / K-Packet | `eship.epost.go.kr` | ❌ Railway에서 직접 호출 차단 → ICN 릴레이 사용 |
| 우체국 공개 종적조회 | `service.epost.go.kr` | ❌ Railway에서 timeout (IP 차단 추정) |
| 우체국 신형 추적 | `ntrack.epost.go.kr` | ❓ 미확인 (동일 차단 가능성 높음) |

### 현재 우회 방법

#### 1. 계약소포 API (`ship.epost.go.kr`) — ✅ 해결됨
- **경로**: Railway → `EPOST_RELAY_URL`(`tillion.io.kr`) → `ship.epost.go.kr`
- `tillion.io.kr`은 국내 서버이므로 우체국 API 직접 호출 가능
- `backend/app/services/epost/client.py` `call_epost()` 함수가 이 경로를 사용
- 관련 env var: `EPOST_RELAY_URL`, `EPOST_RELAY_SECRET`

#### 2. Vercel Seoul(ICN) API Route — ✅ 구현됨
- `frontend/src/app/api/epost-relay/route.ts` — `preferredRegion = 'icn1'`
- 허용 호스트: `ship.epost.go.kr`(계약소포), `eship.epost.go.kr`(해외배송 EMS), `service.epost.go.kr`(종적조회 GET)
- 해외배송 경로: Railway → `EPOST_RELAY_URL` → `/api/epost-relay` → `eship.epost.go.kr`
- 관련 env var: `EPOST_RELAY_SECRET` (Railway·Vercel 양쪽 동일 값 설정 필요)

#### 3. 공개 종적조회 (`service.epost.go.kr`) — ✅ 해결됨 (2026-09-10)
- **경로**: Railway → `VERCEL_APP_URL`(`tillion.io.kr`) `/api/epost-relay` → `service.epost.go.kr`
- `route.ts`: `isAllowedUrl()` 로직으로 `service.epost.go.kr` GET 허용, `arrayBuffer()` 바이너리 전달
- `client.py`: `_track_via_vercel_relay()` 함수가 EUC-KR 디코딩 후 `treat_status_from_tracking_text()` 호출
- **Railway env**: `VERCEL_APP_URL=https://tillion.io.kr` ✅ 설정 완료

> **tracker.delivery GraphQL (방안 A)**도 사용 가능:  
> `TRACKER_DELIVERY_CLIENT_ID` / `TRACKER_DELIVERY_CLIENT_SECRET` Railway env 등록 시 1순위로 사용됨

### 상태 조회 현재 동작 (2026-09-10 기준)

```
송장조회 버튼 클릭
  └─ GetResInfo (계약 API, tillion.io.kr 릴레이) → 수거완료(01)까지 정상 갱신
  └─ _track_via_vercel_relay() (Vercel ICN → service.epost.go.kr)
      └─ EUC-KR 디코딩 → treat_status_from_tracking_text() → 최신 상태 추출
      └─ 이동중(02) / 배달준비(06) / 배달중(07) / 배달완료(03) 갱신 가능
  └─ _track_via_epost_trace() (Railway 직접 → 차단, fallback 유지)
```

> ⚠️ **HTML 파싱 주의**: `service.epost.go.kr` 페이지에는 진행 단계 레이블로 '배달완료' 텍스트가
> 항상 포함됨. `treat_status_from_tracking_text()`는 실제 이력 `<td>` 행만 역순 파싱해 오탐 방지.
> 날짜/시간이 **별도 TD로 분리**되며 이력은 **오름차순** (마지막 행 = 최신).
>
> **상태코드 전체 10단계**: `신청접수(00)→운송장출력(04)→접수확인(08)→수거준비(05)→배차신청(09)→수거완료(01)→이동중(02)→배달준비(06)→배달중(07)→배달완료(03)`

### 유지보수 엔드포인트

```
POST /kpost-pickup/maintenance/reset-status?secret=<EPOST_RELAY_SECRET>
Body: {"tracking_nos": ["78901..."], "treat_status": "05"}
```
- DB 상태를 직접 수정 (인증: `EPOST_RELAY_SECRET` 값 사용)
- 잘못 변경된 상태 복구 또는 테스트 목적으로 사용

---

## 📦 회수접수(kpost-pickup) 배송추적 API

### 추적 흐름

```
접수 후 상태 갱신 요청
        ↓
_sync_pickup_like_infront()   [backend/app/api/kpost_pickup.py]
  ├─ [1] GetResInfo (계약 API, ship.epost.go.kr)
  │        order_no + req_ymd → 신청접수~수거완료 단계 갱신
  │
  └─ [2] track_regi_no (공개 종적조회)
           → 수거완료(01) 이후 이동중·배달중·배달완료 단계 추적
           ├─ 1순위: tracker.delivery GraphQL   (자격증명 있을 때)
           ├─ 2순위: Vercel ICN 릴레이           (VERCEL_APP_URL 설정 시)
           └─ 3순위: service.epost.go.kr 직접   (Railway 차단 fallback)
```

> **상태는 앞으로만 진행** — `_apply_tracking_info()`에서 `TREAT_STATUS_ORDER` 기준으로
> 이미 더 진행된 상태를 이전 상태로 되돌리지 않음.

---

### 추적 방법 3가지

#### 1순위 — tracker.delivery GraphQL
- 함수: `_track_via_tracker_delivery()` (`backend/app/services/epost/client.py`)
- 필요 env: `TRACKER_DELIVERY_CLIENT_ID`, `TRACKER_DELIVERY_CLIENT_SECRET`
- 대상 URL: `https://apis.tracker.delivery/graphql` (`carrierId: "kr.epost"`)
- 상태 코드 매핑:

| tracker.delivery 코드 | → Korean text |
|---|---|
| `PICKUP_PENDING` / `PICKING_UP` | 수거준비 |
| `AT_PICKUP` | 수거완료 |
| `IN_TRANSIT` | 이동중 |
| `OUT_FOR_DELIVERY` | 배달중 |
| `DELIVERED` | 배달완료 |
| `ATTEMPT_FAILED` | 배달중 |

#### 2순위 — Vercel Seoul(ICN) 릴레이
- 함수: `_track_via_vercel_relay()` (`backend/app/services/epost/client.py`)
- 필요 env: `VERCEL_APP_URL`, `EPOST_RELAY_SECRET`
- 경로: Railway → `{VERCEL_APP_URL}/api/epost-relay` (ICN 리전, `preferredRegion='icn1'`) → `service.epost.go.kr`
- 릴레이 route: `frontend/src/app/api/epost-relay/route.ts`
  - `service.epost.go.kr` GET만 허용, 응답을 `arrayBuffer()` 바이너리 그대로 전달
  - Python 측에서 EUC-KR 디코딩 후 `treat_status_from_tracking_text()` 호출

#### 3순위 — service.epost.go.kr 직접 (fallback)
- 함수: `_track_via_epost_trace()` (`backend/app/services/epost/client.py`)
- 환경변수 불필요 (네트워크 직접 연결)
- Railway 싱가포르에서 timeout 차단 가능성 높음 → fallback 용도
- EUC-KR / UTF-8 자동 감지 디코딩

---

### 계약 API 상태조회 — GetResInfo

```python
# backend/app/services/epost/client.py
get_res_info(order_no, req_ymd, req_type="2")
# → call_epost("api.GetResInfo.jparcel", ...)
# → ship.epost.go.kr (EPOST_RELAY_URL 중계 경유)
```

- `req_ymd` 후보: `res_date` → `created_at` → `pickup_date` 순서로 시도 (`lookup_req_ymds()`)
- `get_res_info_with_dates(order_no, ymds)`: 날짜 목록을 순차 시도해 유효 응답 반환

---

### 처리상태(treatStatus) 전체 10단계

| 코드 | Korean text | 순서 | 칩 색상 |
|---|---|---|---|
| `00` | 신청접수 | 0 | 회색 |
| `04` | 운송장출력 | 1 | 노랑 |
| `08` | 접수확인 | 2 | 연노랑 |
| `05` | 수거준비 | 3 | 주황 |
| `09` | 배차신청 | 4 | 진주황 |
| `01` | 수거완료 | 5 | 초록 |
| `02` | 이동중 | 6 | 파랑 |
| `06` | 배달준비 | 7 | 보라 |
| `07` | 배달중 | 8 | 핑크 |
| `03` | 배달완료 | 9 | 민트 |
| — | 취소 | — | 빨강 |

- **최종 상태** (`FINAL_TREAT_STATUSES`): `배달완료`, `신청취소` → 이후 조회 중단
- DB에는 숫자 코드가 아닌 **Korean text**로 저장 (`treat_status` 컬럼)

---

### 배송추적 관련 API 엔드포인트

| 메서드 | 경로 | 동작 | 권한 |
|---|---|---|---|
| `POST` | `/kpost-pickup/refresh-status` | 미완료 접수 전체 상태 일괄 갱신 (최대 200건, 8 스레드 병렬) | 로그인 |
| `GET` | `/kpost-pickup/{id}?refresh=true` | 특정 1건 상태 즉시 갱신 | 로그인 |
| `GET` | `/kpost-pickup/debug-track/{regi_no}` | 4가지 추적 경로 모두 테스트 결과 반환 | 관리자 |
| `PATCH` | `/kpost-pickup/{id}/treat-status` | 특정 건 처리상태 수동 강제 변경 | 관리자 |
| `POST` | `/kpost-pickup/maintenance/reset-status` | 송장 목록 상태 직접 수정 (EPOST_RELAY_SECRET 인증) | 유지보수 |
| `GET` | `/kpost-pickup/maintenance/inspect` | DB 레코드 + insert_snapshot 조회 | 유지보수 |

---

### 관련 환경변수 (Railway)

| 환경변수 | 용도 | 필수 |
|---|---|---|
| `EPOST_API_KEY` | 우체국 계약소포 API 키 | ✅ |
| `EPOST_SECURITY_KEY` | SEED-128 암호화 보안키 | ✅ |
| `EPOST_CUSTOMER_ID` | 우체국 고객번호 | ✅ |
| `EPOST_APPROVAL_NO` | 우체국 승인번호 | ✅ |
| `EPOST_RELAY_URL` | 계약 API 중계 서버 URL (tillion.io.kr) | ✅ |
| `EPOST_RELAY_SECRET` | 중계 인증 시크릿 (Vercel·Railway 동일 값) | ✅ |
| `VERCEL_APP_URL` | 공개 종적조회 Vercel 릴레이 URL | ✅ |
| `TRACKER_DELIVERY_CLIENT_ID` | tracker.delivery GraphQL 클라이언트 ID | 선택 |
| `TRACKER_DELIVERY_CLIENT_SECRET` | tracker.delivery GraphQL 시크릿 | 선택 |

---

## 해외배송 접수 (EMS / EMS 프리미엄 / K-Packet)

창고 직원이 tillion에서 **결제 없이** 우체국 해외발송을 바로 접수한다. 고객 앱(Infront)의 결제·보관료 게이트는 없다.

화면: `/overseas-shipping` (접수), `/overseas-shipping-list` (목록·취소), `/overseas-senders`, `/overseas-recipients`, `/overseas-hs-codes`

### 접수 흐름

```
로그인
  → GET /overseas-shipping/meta          발송인 기본값, 배송방법, HS 카탈로그
  → GET /overseas-shipping/nations       배송방법별 우체국 발송 가능 국가
  → GET /overseas-shipping/quote         우체국 예상요금 (후납, 화면 표시)
  → GET /overseas-shipping/saved-addresses  기본 주소 자동입력
  → 발송인 이름 수정 (화면 기본값은 EMS_SENDER_NAME, 없으면 스프링풀필먼트)
  → 구글 Places 자동완성 + Address Validation 추천
  → 화물/서류 선택. 서류는 박스 크기를 넣지 않는다
  → 품목 한글/영문/HS 검색으로 인보이스·HS코드 완성
  → POST /overseas-shipping/preview      확인 전 DB·우체국 미기록
  → 확인 후 POST /overseas-shipping      eship.epost.go.kr 즉시 접수
  → GET /overseas-shipping/{id}/label    CN22 출력서류 (JSON/HTML)
  → 화면 /overseas-print/{id} 에서 인쇄
  → 접수목록에서 같은 서류를 다시 연다 (취소 후에도 가능)
  → 목록에서 확인 후 취소
```

- 확인(`confirm=true`) 전에는 접수·취소를 쓰지 않는다.
- 같은 직원 + 같은 전화번호 + 같은 국가 + 당일 접수는 중복 가드.
- EMS 키가 없으면 `live_ready=false` 이고 테스트 접수(등기번호 `EG`/`FX`/`LK` 접두어)만 저장한다.
- 실접수는 Railway `EMS_*` + `EPOST_RELAY_URL` 이 있을 때만 `eship.epost.go.kr` 로 나간다. 접수 `regData`는 SEED128, EUC-KR이다.
- 요금은 우체국 후납. 접수 화면에서 `GET /overseas-shipping/quote` 로 화물·서류 예상요금을 나눠 보여 준다.
- 미국·영국 DDP 예상액은 세율·운송사 수수료에 버퍼 10%와 환율 2%를 얹은 내부 참고값이다. 최저 금액으로 올리지 않고, 1,000원 단위로만 올린다. 배송요금 칸에는 DDP 합계와 그 안에 포함된 버퍼 원화를 같이 보여 준다. 미국 신고가액 USD 800 초과는 EMS 프리미엄(FedEx DDP)만 선납 가능하다.
- 국가 목록은 배송방법(`premiumcd` 31/32/14)마다 `api.RetrieveNationListRequest.ems` 값을 받는다. K-Packet은 EMS보다 발송국이 적다.
- EMS·프리미엄(`premiumcd` 31/32)은 `EMS_APPROVAL_NO`, K-Packet(`14`)은 `EMS_KPACKET_APPROVAL_NO` 를 쓴다.

### 우체국에 보내는 값

계약 OpenAPI 항목명 그대로 보낸다. 한 칸짜리 `sendermobile` 은 없다.

- 발송인 이름(`sender`)은 영문 35자 이하다. 화면의 `틸리언`은 `Tillion`, `스프링풀필먼트`는 `Spring Fulfillment`로 바꿔 접수한다. 그 외 한글 이름은 접수 전에 거절한다.
- 발송인 전화·휴대전화는 4칸이다. 첫 칸은 국가번호 `82`, 나머지는 국내번호에서 앞 `0`을 뺀 값이다. 예: `010-1234-4567` → `82` / `10` / `1234` / `4567`.
- 수취인 전화도 4칸(`receivetelno1`~`4`)과 전체번호(`receivetelno`)를 같이 보낸다. 첫 칸은 도착국 국가번호이고, 전체번호는 `+` 없이 `010-1234-1234`처럼 하이픈이 있는 국내번호다.
- 서류(`em_ee=ee`)는 가로·세로·높이를 보내지 않는다. HS는 `49`로 시작하는 10자리다. 화면의 `490199`는 `4901999000`으로 보내고, 49가 아닌 서류 HS도 같은 세번으로 바꾼다.

### 구글 주소 · 주소록 · HS코드

- Places Autocomplete: 상세주소 입력 시 국가 제한 검색, 주/시/우편번호 자동 채움
- Address Validation: 지원 국가에서 blur 시 추천 주소 다이얼로그
- 주소록: 직원별 수취인 저장/기본주소/접수와 함께 저장 (`overseas_saved_addresses`), 화면 `/overseas-recipients`
- 발송인: 이름·주소·전화 수정 후 목록 저장 (`overseas_saved_senders`), 화면 `/overseas-senders`
- HS 검색: 접수 화면에서 한글·영문·HS 6자리 검색. 저장 품목 + 창고 카탈로그 + WCO HS 6자리 목록(`hs6.json`, 약 5,600건)을 API로 합쳐 보여 준다. 고른 품목은 저장해 재사용 (`overseas_saved_hs_codes`)

프론트 키 `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` 는 Vercel에만 넣고 git에 커밋하지 않는다. Google Cloud 키 제한에 `tillion.io.kr` 과 로컬 개발 origin을 허용해야 화면 검색이 된다.

### API

| 메서드 | 경로 | 동작 |
|---|---|---|
| `GET` | `/overseas-shipping/meta` | 실접수 가능 여부, 발송인 기본값, 배송방법, HS 카탈로그 |
| `GET` | `/overseas-shipping/nations` | 배송방법별 발송 국가 (우체국 API, `premiumcd`) |
| `GET` | `/overseas-shipping/quote` | 우체국 예상요금 + 미국/영국 DDP (후납 참고, 결제 아님) |
| `GET` | `/overseas-shipping/item-categories` | HS/품목 검색 (저장 + 카탈로그 + HS 6자리 목록) |
| `GET/POST/PUT/DELETE` | `/overseas-shipping/saved-addresses` | 해외 수취인 목록 |
| `GET/POST/PUT/DELETE` | `/overseas-shipping/saved-senders` | 발송인 목록 |
| `GET/POST/PUT/DELETE` | `/overseas-shipping/saved-hs` | 저장 HS코드 목록 |
| `POST` | `/overseas-shipping/preview` | 확인용 미리보기 (미기록) |
| `GET` | `/overseas-shipping` | 접수 목록 |
| `POST` | `/overseas-shipping` | 확인 후 접수 |
| `GET` | `/overseas-shipping/{id}/label` | 출력서류 CN22 (JSON, `format=html` 이면 인쇄 HTML) |
| `POST` | `/overseas-shipping/{id}/cancel` | 확인 후 취소 |

우체국 `eship.epost.go.kr` 계약 OpenAPI에는 라벨 PDF를 내려주는 엔드포인트가 없다. 접수한 등기번호·발송인·수취인·인보이스를 저장해 두고, tillion이 CN22 형식 출력서류를 만들어 인쇄한다. 화면은 `/overseas-print/{id}` 이다. 접수 직후의 **출력서류 인쇄**와 접수목록 각 행의 **출력서류**가 같은 페이지를 연다. 취소된 건도 출력서류 버튼은 남고, 서류 위에 취소된 접수라고 표시한다.

### 환경변수

Railway (git에 넣지 않음):

| 환경변수 | 용도 |
|---|---|
| `EMS_API_KEY` | EMS OpenAPI 인증키 |
| `EMS_SECURITY_KEY` | EMS 보안키 (SEED128) |
| `EMS_CUSTOMER_NO` | 고객번호 |
| `EMS_APPROVAL_NO` | EMS·프리미엄 계약승인번호 (`premiumcd` 31/32) |
| `EMS_KPACKET_APPROVAL_NO` | K-Packet 계약승인번호 (`premiumcd` 14) |
| `EMS_SENDER_NAME` | 화면 기본 발송인. 우체국에는 영문 35자로 전달 |
| `EMS_USD_KRW_RATE` | DDP 환산 환율. 없으면 1400 |
| `EPOST_RELAY_URL` / `EPOST_RELAY_SECRET` | Seoul ICN 중계 (`eship.epost.go.kr`) |

Vercel:

| 환경변수 | 용도 |
|---|---|
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Places + Address Validation (브라우저 공개키) |

### 테스트

```bash
python -m pytest tests/test_overseas_shipping.py tests/test_overseas_intake_flow.py tests/test_google_places.py -v
```

화면 접수 순서 전체 플로우, 확인 전 쓰기 거부, 발송인 영문 변환, 휴대전화 4칸, 서류 HS·박스 생략, 주소록, HS 완성, 출력서류 재출력, 구글 주소 파싱·Address Validation을 검증한다.

---

## 개발 환경

| 항목 | 값 |
|------|-----|
| 프론트엔드 | Next.js 14 (Vercel 배포) |
| 백엔드 | FastAPI (Railway 배포, Dockerfile.backend) |
| DB | SQLite (Railway Volume) |
| 도메인 | https://tillion.io.kr |

## 로컬 개발

```bash
# 백엔드
cd backend && uvicorn app.main:app --reload --port 8000

# 프론트엔드 (개발 서버만 — 빌드 아님)
cd frontend && npm run dev
```

---

## 변경 이력

### 2026-09-23
- **fix(overseas-shipping): DDP 버퍼 10% 통일, 최저 금액 제거**
  - 미국 EMS·프리미엄·영국 버퍼를 추정액의 10%로 맞춘다
  - 15,000 / 25,000 / 10,000원 바닥값은 쓰지 않고, 환율 2%와 1,000원 올림만 적용한다
  - 배송요금 칸과 접수 확인창에 버퍼 원화를 표시한다 (DDP 합계에 포함)

### 2026-09-22
- **fix(overseas-shipping): 우체국 실접수 항목을 계약 매뉴얼에 맞춘다**
  - 발송인 휴대전화를 `sendermobile1`~`4`(국가번호 82)로 보내고, 한글 발송인명은 영문 35자로 바꾼다
  - 수취인 전화는 도착국 국가번호와 하이픈 국내번호로 나눈다
  - 서류는 박스 크기를 빼고, HS `490199`는 `4901999000`으로 접수한다
  - K-Packet은 `EMS_KPACKET_APPROVAL_NO` 를 쓴다
  - 접수목록 **출력서류**로 취소 후에도 CN22를 다시 연다

### 2026-09-17
- **feat(overseas-shipping): 창고 직원 EMS/K-Packet 즉시 접수**
  - 결제 없이 미리보기 확인 후 `eship.epost.go.kr` 로 바로 접수 (Vercel ICN 릴레이)
  - 발송인 이름 건별 수정, 해외 주소록 저장/기본주소, 품목·HS코드 검색 완성
  - 구글 Places 자동완성 + Address Validation 추천 주소
  - 확인 전 미기록, 당일 중복 가드, 테스트 접수(`EG`/`FX`/`LK`)
  - 검증: `tests/test_overseas_shipping.py`, `tests/test_overseas_intake_flow.py`, `tests/test_google_places.py`

### 2026-09-11 (5차)
- **fix(inbound): inbox 사진 연결 오류 + 아코디언 기본 열림**
  - `linkInboxPhotoToItem` — `Content-Type: application/json` 누락으로 Pydantic 422 에러 발생 수정
    - `fetchApi` 스프레드 순서 버그: `...options`가 기본 헤더를 덮어쓰는 문제 해결
  - 봇 inbox 사진 섹션 기본값 열림 (`showInboxPicker`, `showInbox`: `false → true`)
    - 링크 진입 즉시 사진 선택 영역이 보여 작업자 혼선 방지

### 2026-09-11 (4차)
- **feat(inbound): 입고완료 시 미매칭 inbox 사진 자동 삭제**
  - `am close` (입고 확인 완료, `confirming → inbound_done`) 시 자동 실행
  - 어떤 품목에도 연결되지 않은 inbox 사진(`item_id IS NULL`) 일괄 정리
  - 파일 디스크 삭제 + DB `is_deleted=1` soft-delete
  - 삭제 실패(디스크 오류 등)는 warning 로그만 남기고 마감은 정상 진행
  - close 응답에 `deleted_inbox_photos` 카운트 포함

### 2026-09-11 (3차)
- **fix(inbound-bot): 링크 전송 순서 수정 — 사진 끝 이후에만 링크 발송**
  - 장끼 OCR 완료 응답에서 작업 링크 제거 (조기 링크 제거)
  - `사진 끝` 입력 시에만 링크 발송 → 제품사진 업로드 완료 확인 후 링크 도착
  - 봇 대화 순서: 입고 → 업체명 → 장끼 → 제품사진(여러장) → `사진 끝` → **링크 수신** → 매칭 작업

### 2026-09-11 (2차)
- **fix(inbound): 봇 inbox 사진 중복 매칭 방지 강화**
  - 다른 품목에 이미 연결된 사진(`linkedToOther`) 클릭 완전 차단
  - `onClick` 조건에 `!linkedToOther` 추가
  - `cursor` 스타일: `linkedToOther`일 때 `'not-allowed'`로 변경
  - `opacity`: `linkedToOther` 사진을 `0.45`로 흐리게 처리해 시각적 비활성 표시
  - 기존 "이 품목에 연결됨(초록)" · "다른 품목에 연결됨(주황)" 색상 구분은 유지

### 2026-09-11
- **feat(kpost-pickup): 관리자 회수신청 목록 삭제 기능** (`ccc94eee`)
  - `isAdmin` localStorage 키 불일치 버그 수정 (`is_admin` → `isAdmin`) — 삭제 버튼이 관리자에게도 안 보이던 문제
  - 체크박스 다중 선택 + 일괄 삭제/취소 기능 추가
    - 헤더 체크박스: 현재 페이지 전체 선택/해제
    - 선택 취소 버튼: 취소 가능한 건만 일괄 취소 (모든 사용자)
    - 선택 삭제 버튼: 삭제 가능한 건만 일괄 삭제 (관리자 전용)
  - **삭제 가능 조건**: `status=canceled` 또는 `배달완료`·`신청취소` 상태만 허용
    - 진행 중인 건(신청접수·수거준비·이동중 등)은 삭제 불가
    - 행별 삭제 버튼도 동일 조건 적용
- **feat(kpost-pickup): 회수신청 목록 수거 메모 칼럼 + 박스 규격 표시 개선** (`e1e9be72`)
  - 박스 규격: 코드(`LARGE`) 대신 폼과 동일한 표시(`대형 · 20kg · 120cm`)
  - 수거 메모 칼럼 신규 추가
- **feat(kpost-pickup): 저장된 주소지 다음 주소검색 API 동적 로드** (`82ff6a34`)
  - `saved-recipients` 페이지에서 "다음 주소 검색 API를 로드하지 못했습니다" 에러 수정
  - `return-request`와 동일하게 `<script>` 태그 동적 삽입 후 실행
- **fix(kpost-pickup): 주소지 저장 중복 시 에러 대신 기존 레코드 반환** (`69bc2e77`)
  - 동일 라벨 이미 존재 시 400 에러 대신 기존 레코드 `success=true` 반환
  - 프론트 별칭 중복 사전 차단 제거

### 2026-09-10 (3차)
- **feat(kpost-pickup): 송장 갯수만큼 InsertOrder 반복 — 박스당 송장번호 1개 발급** (`0364f399`)
  - 기존: InsertOrder 1회 호출(qty=N 전송) → 송장번호 1개
  - 변경: InsertOrder N회 반복(qty=1 고정) → 송장번호 N개
  - DB도 박스별 row 1개씩 저장 (box_quantity=1)
  - 중복 방지 로직 개선: 기존 접수 수 < 요청 수량이면 남은 개수만 추가 접수 허용 (부분 실패 재시도 가능)
  - 타임아웃: qty × 7초 동적 계산 (최소 20초)
  - 성공 메시지: 발급된 송장번호 전체 목록 표시 (`송장 A, B, C, D, E`)
  - 폼 라벨: **"박스 수량" → "송장 갯수"** (직관적 표현)
- **feat(kpost-pickup): 상태코드 Korean text 통합 + 신청취소 처리** (`b0d4a462`)
  - `treat_status` DB 컬럼: 숫자코드(`05`) → Korean text(`수거준비`) 직접 저장
  - `_STATUS_CANONICAL` / `TREAT_STATUS_ORDER` / `FINAL_TREAT_STATUSES` 모두 Korean text 기준
  - `신청취소` 종단 상태(order=10) 추가 → 수거준비에서 신청취소로 정상 전이
  - DB 마이그레이션: 앱 시작 시 기존 숫자코드 rows 일괄 Korean text 변환
  - 프론트 `TREAT_STATUS_OPTIONS` / `statusLabel()` / `canCancel()` Korean text 기준으로 통합
  - `GET /kpost-pickup/maintenance/inspect` 엔드포인트 추가 (DB 레코드 + insert_snapshot 조회)
  - 단위 테스트 11/11 PASS (`test_tracking_fix.py`)

### 2026-09-10 (2차)
- **fix(kpost-pickup): treat_status_from_tracking_text 오탐 수정** (`763db40f` → `76886603`)
  - **버그**: `service.epost.go.kr` HTML에 진행 단계 레이블로 '배달완료'가 항상 포함 → 수거준비 건도 `03`으로 오탐
  - **원인 분석**: 실제 HTML 구조 확인 — 날짜/시간이 별도 TD(`<td>2026.09.10</td><td>07:55</td>`), 이력 오름차순
  - **수정**: 3단계 파싱으로 변경
    1. 날짜 TD 패턴(`^\d{4}.\d{2}.\d{2}$`) 포함 이력 `<tr>` 역순 탐색 → 최신 상태 추출
    2. 전체 `<td>` 역순 검색 (배달완료 제외)
    3. 텍스트 fallback
  - **신규 상태**: `배차신청`(수거 차량 배정) → `05(수거준비)` 매핑 추가
  - **단위 테스트**: 8/8 PASS (`test_tracking_fix.py`)
- **feat(kpost-pickup): 수거 전 단계 세분화 — 접수확인(08)·배차신청(09) 추가** (`33439ed7`)
  - 총 10단계: `00→04→08→05→09→01→02→06→07→03`
  - `접수확인(08)`: 연노랑 칩 / `배차신청(09)`: 진주황 칩
  - `treat_status_from_tracking_text`: 접수확인→08, 수거준비→05, 배차신청→09 각각 분리 매핑
  - `TREAT_STATUS_ORDER` 업데이트, 필터 드롭다운·관리자 드롭다운에도 반영
- **feat(kpost-pickup): 회수신청 목록 배송상태 필터 추가** (`5e8964cb`)
  - 필터 바에 **배송상태 드롭다운** 추가 (전체 / 신청접수~배달완료 / 취소)
  - 백엔드 `GET /kpost-pickup`에 `treat_status` 쿼리 파라미터 추가
  - `canceled` 값이면 `status='canceled'` 필터 처리
  - 전체목록 버튼 클릭 시 상태 필터도 초기화
- **feat(kpost-pickup): 유지보수 엔드포인트 추가** (`76886603`)
  - `POST /kpost-pickup/maintenance/reset-status?secret=<EPOST_RELAY_SECRET>`
  - 특정 송장 번호의 treat_status를 직접 수정 (잘못 변경된 상태 복구용)
- **feat: Vercel 릴레이 공개 종적조회 활성화** (`4ade0014` + Railway env)
  - `VERCEL_APP_URL=https://tillion.io.kr` Railway 환경변수 설정 완료
  - `_track_via_vercel_relay()` 활성화 → 배달완료까지 자동 추적 가능

### 2026-09-10 (1차)
- **feat(kpost-pickup): 송장조회 상태 세분화 + 배달완료까지 추적** (`d8d99c89` → `현재`)
  - 처리상태코드 8단계 추가: `신청접수(00) → 운송장출력(04) → 수거준비(05) → 수거완료(01) → 이동중(02) → 배달준비(06) → 배달중(07) → 배달완료(03)`
  - `TRACKER_STATUS_TO_TREAT` 확장: `PICKUP_PENDING→05`, `OUT_FOR_DELIVERY→07`, `ATTEMPT_FAILED→07`
  - `treat_status_from_tracking_text` 확장: 운송장출력·수거준비·이동중·배달준비·배달중 텍스트 인식
  - `_sync_pickup_like_infront`: 수거완료(01) 이후에도 `track_regi_no` 계속 호출 → 배달완료(03)까지 추적
  - DB 쿼리: 배달완료(`03`)만 LIMIT 200 제외 → 수거완료 건도 배달완료까지 지속 조회
  - StatusChip 10가지 색상 칩: 운송장출력(노랑), 수거준비(주황), 수거완료(초록), 이동중(파랑), 배달준비(보라), 배달중(핑크), 배달완료(민트), 취소(빨강)
  - 신규 테스트: `test_treat_status_from_tracking_text_granular`, `test_refresh_status_skips_only_delivered` — 15/15 통과
- **feat(kpost-pickup): 회수신청 목록 컬럼별 정렬** (`80227823`)
  - 모든 컬럼 헤더 클릭 → 오름/내림차순 전환, 활성 컬럼 ▲▼ 표시
- **fix(kpost-pickup): 송장조회 수거완료·배달완료 건 DB 단 제외** (`7a98aa1e`)
  - `treat_status NOT IN ('01','03')` 조건 추가 → LIMIT 200을 실조회 대상에만 사용
  - 취소 건은 기존 `status='requested'` 조건으로 이미 제외
  - 검증 테스트 추가 (`test_refresh_status_skips_completed_and_delivered`) — 14/14 통과
- **feat(kpost-pickup): 회수신청 목록 상태 컬럼 색상 칩 표시** (`c868604e`)
  - 신청접수(회색) / 수거중(파랑) / 수거완료(초록) / 배달완료(청록) / 취소(빨강) 칩
  - React import 누락 수정
- **feat(kpost-pickup): 회수신청 목록 페이징 추가** (`31827bc8`)
  - 페이지당 10/30/50/100건 선택, 페이지 네비게이션, 필터 조회 시 1페이지 리셋
- **feat(kpost-pickup): 관리자 송장번호 일괄 삭제 API** (`70acbd2d`)
  - `POST /kpost-pickup/bulk-delete` 엔드포인트 추가 (관리자 전용)
- **feat(kpost-pickup): 회수신청 목록 수취인·접수자 콤보박스 필터 추가** (`5dcaaa10`)
  - `GET /kpost-pickup/filter-options` 엔드포인트 추가 (접수자 전체·수취인 최근 200명 고유값 반환)
  - 수취인·접수자 입력 필드에 `<datalist>` 연결 — 드롭다운 선택 + 직접 입력 모두 가능
  - 백엔드 `GET /kpost-pickup` 에 `created_by` 쿼리 파라미터 추가 (부분 일치 LIKE 검색)
  - 회수신청 목록 필터 바 4열 그리드 (수거일 시작·종료·수취인·접수자)

### 2026-09-07
- **fix: MICRO 박스 접수 시 microYn=Y 누락 수정** (`d267a6d5`)
  - `PICKUP_BOX_SIZES` MICRO 항목에 `"micro": True` 플래그 추가
  - 누락 시 `microYn=N` 으로 전송되어 우체국이 표준 5kg(5,500원)으로 처리하던 버그 수정
- **fix: 극소(MICRO) 사이즈 기본 선택으로 변경** (`e50c5c69`)
