# 프로덕션 배포 가이드

## 목차
1. [로컬 개발 환경](#1-로컬-개발-환경)
2. [환경변수 설정](#2-환경변수-설정)
3. [실행 명령어](#3-실행-명령어)
4. [배포 플랫폼 가이드](#4-배포-플랫폼-가이드)
5. [보안 체크리스트](#5-보안-체크리스트)

---

## 1. 로컬 개발 환경

### 요구사항
- Python 3.11+
- Node.js 18+
- npm 9+

### 빠른 시작
```bash
# 1. 환경변수 설정
cp env.example .env
# .env 파일 편집

# 2. 백엔드 실행
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# 3. 프론트엔드 실행 (새 터미널)
cd frontend
npm install
npm run dev

# 4. 접속
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

---

## 2. 환경변수 설정

### 백엔드 (.env)
```bash
# 앱 설정
APP_NAME=Billing API
APP_VERSION=1.0.0
DEBUG=false                    # 프로덕션: false

# 서버
HOST=0.0.0.0
PORT=8000

# 데이터베이스
DATABASE_PATH=billing.db

# CORS (중요!)
CORS_ORIGINS=https://your-frontend-domain.com
CORS_ALLOW_CREDENTIALS=true

# 보안 (반드시 변경!)
SECRET_KEY=your-32-char-random-string
```

### 프론트엔드
```bash
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
```

---

## 3. 실행 명령어

### 개발 환경
```bash
# 백엔드
uvicorn backend.app.main:app --reload --port 8000

# 프론트엔드
cd frontend && npm run dev
```

### 프로덕션 환경
```bash
# 백엔드 (Gunicorn)
gunicorn backend.app.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000

# 프론트엔드 (빌드 후 실행)
cd frontend
npm run build
npm start
```

### Docker
```bash
# 전체 스택
docker-compose up -d

# 개별 빌드
docker build -f Dockerfile.backend -t billing-backend .
docker build -f Dockerfile.frontend -t billing-frontend .
```

---

## 4. 배포 플랫폼 가이드

### 권장 플랫폼

| 구성요소 | 플랫폼 | 특징 | 비용 |
|---------|--------|------|------|
| **백엔드** | Railway | 간편, Python 지원 | $5~/월 |
| | Render | 무료 티어 있음 | 무료~ |
| | Fly.io | 글로벌 엣지 | $5~/월 |
| | AWS Lambda | 서버리스 | 사용량 기반 |
| **프론트엔드** | Vercel | Next.js 최적화 | 무료~ |
| | Netlify | 정적 호스팅 | 무료~ |
| | Cloudflare Pages | 빠른 CDN | 무료~ |
| **통합** | Docker + VPS | 완전 제어 | $5~/월 |
| | Kubernetes | 대규모 운영 | 가변 |

---

### A. Railway (백엔드 권장)

```bash
# 1. Railway CLI 설치
npm install -g @railway/cli

# 2. 로그인 & 프로젝트 생성
railway login
railway init

# 3. 환경변수 설정
railway variables set DEBUG=false
railway variables set CORS_ORIGINS=https://your-frontend.vercel.app
railway variables set SECRET_KEY=your-secret-key

# 4. 배포
railway up
```

**railway.json:**
```json
{
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile.backend"
  },
  "deploy": {
    "startCommand": "gunicorn backend.app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT"
  }
}
```

---

### B. Vercel (프론트엔드 권장)

```bash
# 1. Vercel CLI 설치
npm install -g vercel

# 2. 프론트엔드 폴더로 이동
cd frontend

# 3. 배포
vercel

# 4. 환경변수 설정 (Vercel 대시보드)
# NEXT_PUBLIC_API_URL = https://your-backend.railway.app
```

**vercel.json:**
```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": ".next"
}
```

---

### C. Render (백엔드 무료 티어)

**render.yaml:**
```yaml
services:
  - type: web
    name: billing-api
    env: python
    buildCommand: pip install -r backend/requirements.txt
    startCommand: gunicorn backend.app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT
    envVars:
      - key: DEBUG
        value: false
      - key: CORS_ORIGINS
        value: https://your-frontend.vercel.app
      - key: SECRET_KEY
        generateValue: true
```

---

### D. Docker + VPS (완전 제어)

```bash
# 1. VPS에 Docker 설치 (Ubuntu)
curl -fsSL https://get.docker.com | sh

# 2. 프로젝트 클론
git clone your-repo
cd your-repo

# 3. 환경변수 설정
cp env.example .env
nano .env

# 4. 실행
docker-compose up -d

# 5. Nginx 리버스 프록시 (선택)
sudo apt install nginx
# /etc/nginx/sites-available/billing 설정
```

**Nginx 설정:**
```nginx
server {
    listen 80;
    server_name api.your-domain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 5. 보안 체크리스트

### 필수
- [ ] `DEBUG=false` 설정
- [ ] `SECRET_KEY` 변경 (32자 이상 랜덤 문자열)
- [ ] `CORS_ORIGINS`에 정확한 프론트엔드 도메인만 허용
- [ ] HTTPS 적용 (SSL 인증서)
- [ ] `.env` 파일 Git 제외 확인

### 권장
- [ ] Rate limiting 설정
- [ ] 요청 로깅 활성화
- [ ] 데이터베이스 백업 자동화
- [ ] 모니터링 설정 (Sentry, LogRocket 등)
- [ ] WAF(Web Application Firewall) 적용

### CORS 설정 예시

```python
# 개발
CORS_ORIGINS=http://localhost:3000

# 프로덕션 (단일 도메인)
CORS_ORIGINS=https://app.your-domain.com

# 프로덕션 (다중 도메인)
CORS_ORIGINS=https://app.your-domain.com,https://admin.your-domain.com
```

---

## 문제 해결

### 연결 테스트
```bash
python test_connection.py
```

### 로그 확인
```bash
# Docker
docker-compose logs -f backend

# 직접 실행
uvicorn backend.app.main:app --log-level debug
```

### 일반적인 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| CORS 에러 | Origin 불일치 | `CORS_ORIGINS` 확인 |
| 500 에러 | DB 없음 | `billing.db` 파일 확인 |
| 연결 거부 | 서버 미실행 | 백엔드 실행 상태 확인 |
| 빌드 실패 | 의존성 누락 | `requirements.txt` 확인 |

