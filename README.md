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
| 우체국 공개 종적조회 | `service.epost.go.kr` | ❌ Railway에서 timeout (IP 차단 추정) |
| 우체국 신형 추적 | `ntrack.epost.go.kr` | ❓ 미확인 (동일 차단 가능성 높음) |

### 현재 우회 방법

#### 1. 계약소포 API (`ship.epost.go.kr`) — ✅ 해결됨
- **경로**: Railway → `EPOST_RELAY_URL`(`tillion.io.kr`) → `ship.epost.go.kr`
- `tillion.io.kr`은 국내 서버이므로 우체국 API 직접 호출 가능
- `backend/app/services/epost/client.py` `call_epost()` 함수가 이 경로를 사용
- 관련 env var: `EPOST_RELAY_URL`, `EPOST_RELAY_SECRET`

#### 2. Vercel Seoul(ICN) API Route — ✅ 구현됨, 계약 API용
- `frontend/src/app/api/epost-relay/route.ts` — `preferredRegion = 'icn1'`
- 현재는 `ship.epost.go.kr` 전용. 공개 종적조회(`service.epost.go.kr`) 릴레이는 미구현
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
