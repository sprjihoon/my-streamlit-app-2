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

#### 3. 공개 종적조회 (`service.epost.go.kr`) — ❌ 미해결
- Railway → `service.epost.go.kr` 직접 호출 → **15초 timeout**
- `_track_via_epost_trace()` 함수가 항상 실패함
- **향후 해결 방안**:
  - **A (권장)**: [tracker.delivery](https://tracker.delivery) GraphQL API 사용
    - `TRACKER_DELIVERY_CLIENT_ID` / `TRACKER_DELIVERY_CLIENT_SECRET` Railway env 등록 필요
    - 글로벌 접근 가능, `kr.epost` 지원
  - **B**: Vercel `/api/epost-relay` 라우트를 `service.epost.go.kr` GET 요청도 허용하도록 확장
    - `route.ts`의 `ALLOWED_HOST`에 `service.epost.go.kr` 추가
    - `client.py`에 `_track_via_vercel_relay()` 함수 추가

### 상태 조회 현재 동작 (2026-09-10 기준)

```
송장조회 버튼 클릭
  └─ GetResInfo (계약 API, tillion.io.kr 릴레이) → 수거완료(01)까지는 정상 갱신
  └─ track_regi_no (공개 종적조회) → Railway에서 항상 timeout → 예외 무시
      └─ 결과: 수거완료(01) 이후 단계(이동중·배달준비·배달중·배달완료)는
               GetResInfo가 해당 코드를 반환할 때만 갱신됨
```

> **임시 해결**: 관리자는 회수신청 목록의 상태 칩 하단 드롭다운으로 수동 수정 가능

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

### 2026-09-10
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
