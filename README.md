# 통합 물류 정산 관리 시스템

React (Next.js) + FastAPI 기반의 물류 풀필먼트 업무 통합 관리 플랫폼입니다.

---

## 📁 프로젝트 구조

```
my-streamlit-app/
├── backend/
│   └── app/
│       ├── api/            # API 라우터
│       ├── models/         # Pydantic 스키마
│       ├── services/       # AI 파서, 네이버웍스 봇, 스케줄러
│       └── main.py
├── frontend/               # Next.js 14 App Router
│   └── src/app/
│       ├── billing-invoice/   # 실인보이스 관리
│       ├── receipts/          # 영수증(장끼) 관리
│       ├── invoice/           # 인보이스 계산서 생성
│       ├── invoice-list/      # 인보이스 목록
│       ├── invoice-analytics/ # 인보이스 통계
│       ├── estimate/          # 견적서 작성
│       ├── estimate-list/     # 견적서 목록
│       ├── estimate-analytics/# 견적 통계
│       ├── work-log/          # 작업일지 (AI 봇 연동)
│       ├── leave/             # 연차 신청/관리
│       ├── vendors/           # 업체 관리
│       ├── vendor-charges/    # 업체별 청구 관리
│       ├── rates/             # 요금표 관리
│       ├── mapping/           # 매핑 관리
│       ├── upload/            # 엑셀 업로드
│       ├── insights/          # 배송 인사이트
│       ├── wp-analytics/      # WP 분석
│       ├── certificates/      # 알림장 관리
│       ├── storage/           # 창고 보관 관리
│       ├── settings/          # 시스템 설정
│       ├── users/             # 사용자 관리
│       └── logs/              # 시스템 로그
├── logic/                  # 인보이스 계산 핵심 로직
├── scripts/                # 유틸리티 스크립트
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── railway.json            # Railway 배포 설정
└── requirements.txt
```

---

## 🚀 주요 기능

### 💰 실인보이스 관리 (Billing Invoice)
- PDF 업로드 → **GPT-4o AI 자동 파싱** → 구조화된 데이터 저장
- 다중 파일 드래그 앤 드롭 업로드 지원
- 인보이스 항목별 카테고리 자동 분류 (택배비, 포장비, 입출고비 등)
- 납부 현황 추적 (미납/완납), 통계 분석 페이지

### 🧾 영수증(장끼) 관리 (Receipt)
- 이미지 업로드 → **GPT-4o Vision AI OCR** → 거래처/품목 자동 추출
- 수기 영수증 포함, 금액 검산 (단가×수량=금액) 자동 확인
- 확인 필요 항목 자동 표시, 엑셀 일괄 다운로드

### 📋 인보이스 계산서 (Invoice)
- 업체별 물류비 자동 계산 (배송비, 포장비, 출고비, 보관료 등)
- 엑셀 업로드 기반 청구서 자동 생성 및 PDF 출력

### 📝 작업일지 (Work Log)
- **네이버웍스 봇 AI** (GPT Function Calling) 연동 자연어 입력
- "틸리언 하차 3만원" → 자동 파싱 & 저장
- 이전 단가 자동 조회 및 확인, 멀티턴 대화 지원
- 연차 신청/조회/승인 챗봇 연동

### 🗓️ 연차 관리 (Leave)
- 연차/반차 신청 및 결재 워크플로우 (팀원 → 팀장 → 인사과장)
- 캘린더 뷰, 잔여 연차 자동 계산
- 연차 승인/반려, 네이버웍스 봇 연동

### 📦 업체/요금표/매핑 관리
- 업체 등록·별칭 관리, 요금표 CRUD
- 엑셀 업로드 매핑 설정

### 📊 분석 및 통계
- 인보이스 월별/업체별 통계, 배송 인사이트
- WP(워드프레스) 주문 분석

---

## 🛠 기술 스택

| 영역 | 기술 |
|---|---|
| 프론트엔드 | Next.js 14 (App Router), TypeScript, TailwindCSS, Recharts |
| 백엔드 | FastAPI, Python 3.12, SQLite |
| AI | OpenAI GPT-4o / GPT-4o-mini (Function Calling, Vision) |
| 봇 | 네이버웍스 Webhook Bot |
| 배포 | Railway (Docker), Vercel (프론트엔드 옵션) |

---

## ⚙️ 로컬 실행

### 환경변수 설정

```bash
cp env.example .env
# .env 파일에서 아래 값 설정
```

| 변수 | 설명 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 (AI 파싱 기능 필수) |
| `NAVER_WORKS_*` | 네이버웍스 봇 설정 |
| `SECRET_KEY` | JWT 시크릿 키 |
| `DATABASE_PATH` | SQLite DB 경로 |

### 백엔드

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt

uvicorn backend.app.main:app --reload --port 8000
```

API 문서: http://localhost:8000/docs

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

프론트엔드: http://localhost:3000

---

## 🐳 Docker 실행

```bash
docker-compose up --build
```

---

## 🚂 Railway 배포

```bash
# railway.json 설정 후
railway up
```

- 백엔드: `Dockerfile.backend`
- 프론트엔드: `Dockerfile.frontend`
- 데이터 볼륨: `/app/data` (DB, 업로드 파일)

---

## 📌 현재 개발 현황 (2026-07)

| 기능 | 상태 |
|---|---|
| 실인보이스 AI PDF 파싱 | ✅ 완료 |
| 영수증 AI Vision OCR | ✅ 완료 |
| 인보이스 계산서 생성 | ✅ 완료 |
| 작업일지 AI 봇 (네이버웍스) | ✅ 완료 |
| 연차 관리 / 결재 워크플로우 | ✅ 완료 |
| 연차 캘린더 뷰 | ✅ 완료 |
| 업체/요금표/매핑 관리 | ✅ 완료 |
| 인보이스·견적 통계 분석 | ✅ 완료 |
| 배송 인사이트 | ✅ 완료 |
| WP 분석 | ✅ 완료 |
| 창고 보관 관리 | ✅ 완료 |
| 알림장 관리 | ✅ 완료 |
| 사용자/권한 관리 | ✅ 완료 |
| 시스템 로그 | ✅ 완료 |

---

## 📝 라이선스

Private — All rights reserved.
