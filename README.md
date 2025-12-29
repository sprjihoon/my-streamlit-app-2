# 통합 정산 관리 시스템

기존 Streamlit 기반 앱을 **React + FastAPI** 구조로 마이그레이션한 프로젝트입니다.

## 📁 프로젝트 구조

```
my-streamlit-app-2/
├── backend/                 # FastAPI 백엔드
│   ├── app/
│   │   ├── api/            # API 라우터 (endpoints)
│   │   ├── core/           # 설정, 데이터베이스
│   │   ├── models/         # Pydantic 스키마
│   │   ├── services/       # 비즈니스 로직
│   │   └── main.py         # FastAPI 앱 진입점
│   └── requirements.txt
│
├── frontend/                # React 프론트엔드
│   ├── src/
│   │   ├── api/            # API 클라이언트
│   │   ├── components/     # 재사용 컴포넌트
│   │   ├── pages/          # 페이지 컴포넌트
│   │   └── App.tsx
│   └── package.json
│
├── billing.db               # SQLite 데이터베이스
└── README.md
```

## 🚀 빠른 시작

### 백엔드 실행

```bash
# 가상환경 생성 (선택사항)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r backend/requirements.txt

# 서버 실행
cd backend
uvicorn app.main:app --reload --port 8000
```

백엔드 API 문서: http://localhost:8000/docs

### 프론트엔드 실행

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

프론트엔드: http://localhost:5173

## 📚 API 엔드포인트

### 공급처 (Vendors)
- `GET /api/v1/vendors` - 목록 조회
- `GET /api/v1/vendors/{vendor}` - 상세 조회
- `POST /api/v1/vendors` - 등록
- `PUT /api/v1/vendors/{vendor}` - 수정
- `DELETE /api/v1/vendors/{vendor}` - 삭제

### 인보이스 (Invoices)
- `GET /api/v1/invoices` - 목록 조회
- `GET /api/v1/invoices/{id}` - 상세 조회
- `POST /api/v1/invoices/batch` - 일괄 생성
- `DELETE /api/v1/invoices/{id}` - 삭제

### 요금표 (Rates)
- `GET /api/v1/rates/shipping-zone` - 배송요금 조회
- `GET /api/v1/rates/out-basic` - 출고비 조회
- `GET /api/v1/rates/out-extra` - 추가작업비 조회

### 업로드 (Upload)
- `POST /api/v1/upload/{table}` - Excel 업로드
- `GET /api/v1/upload/tables/status` - 테이블 상태 조회
- `DELETE /api/v1/upload/{table}` - 테이블 삭제

### 대시보드 (Dashboard)
- `GET /api/v1/dashboard/metrics` - 핵심 지표
- `GET /api/v1/dashboard/top-products` - 인기 상품
- `GET /api/v1/dashboard/top-vendors` - 출고량 TOP 거래처
- `GET /api/v1/dashboard/revenue-vendors` - 매출 TOP 거래처

## 🛠 기술 스택

### 백엔드
- **FastAPI** - 고성능 API 프레임워크
- **SQLite** - 경량 데이터베이스
- **Pandas** - 데이터 처리
- **Pydantic** - 데이터 검증

### 프론트엔드
- **React 18** - UI 라이브러리
- **TypeScript** - 타입 안정성
- **Vite** - 빌드 도구
- **TailwindCSS** - 스타일링
- **React Query** - 서버 상태 관리
- **Recharts** - 차트 라이브러리

## 🔄 마이그레이션 상세

### 유지된 로직
- 모든 비즈니스 계산 로직 (100% 보존)
- 데이터베이스 스키마 및 쿼리
- 인보이스 생성 알고리즘
- 요금 계산 로직

### 변경된 부분
- **UI**: Streamlit → React + TailwindCSS
- **API**: 동기 호출 → RESTful API
- **상태 관리**: st.session_state → React Query

## 📦 프로덕션 배포

### 백엔드
```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
```

### 프론트엔드
```bash
cd frontend
npm run build
# dist/ 폴더를 정적 파일 서버로 제공
```

## 📝 라이선스

MIT License

