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
