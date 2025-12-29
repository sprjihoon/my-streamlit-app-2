# 🚀 Railway 배포 가이드

## 📋 준비 사항

- Railway 계정 (https://railway.app)
- GitHub 계정 (코드 연동용)

---

## 🔧 1단계: Railway 프로젝트 생성

1. **Railway 가입/로그인**
   - https://railway.app 접속
   - GitHub로 가입 (추천)

2. **새 프로젝트 생성**
   - Dashboard → "New Project" 클릭
   - "Deploy from GitHub repo" 선택
   - 이 저장소 선택

---

## ⚙️ 2단계: Backend 서비스 설정

### 환경변수 설정

Railway 대시보드 → Backend 서비스 → Variables 탭:

```
DEBUG=false
DATABASE_PATH=/app/data/billing.db
BILLING_DB=/app/data/billing.db
SECRET_KEY=your-random-secret-key-here
CORS_ORIGINS=https://your-frontend.up.railway.app
PORT=8000
```

### Volume 추가 (중요!)

1. Backend 서비스 클릭
2. "Add Volume" 클릭
3. 설정:
   - **Mount Path**: `/app/data`
   - **Name**: `billing-data`
4. 저장

> ⚠️ **Volume 없으면 서버 재시작 시 DB 데이터가 삭제됩니다!**

---

## 🎨 3단계: Frontend 서비스 설정

### 새 서비스 추가

1. 프로젝트에서 "New Service" → "GitHub Repo" 선택
2. 같은 저장소 선택
3. Settings → Build:
   - **Root Directory**: `frontend`
   - **Dockerfile Path**: (비워두기 - nixpack 사용)

또는 Dockerfile 사용 시:
   - **Dockerfile Path**: `Dockerfile.frontend`

### 환경변수 설정

```
NEXT_PUBLIC_API_URL=https://your-backend.up.railway.app
PORT=3000
```

> 💡 Backend의 실제 도메인으로 변경하세요!

---

## 🌐 4단계: 도메인 설정

### Backend 도메인

1. Backend 서비스 → Settings → Domains
2. "Generate Domain" 클릭
3. 생성된 도메인 복사 (예: `billing-backend-xxx.up.railway.app`)

### Frontend 도메인

1. Frontend 서비스 → Settings → Domains
2. "Generate Domain" 클릭
3. 생성된 도메인이 메인 접속 URL

### CORS 설정 업데이트

Backend의 `CORS_ORIGINS` 환경변수를 Frontend 도메인으로 업데이트:

```
CORS_ORIGINS=https://billing-frontend-xxx.up.railway.app
```

---

## 📦 5단계: 기존 DB 마이그레이션 (선택사항)

로컬의 `billing.db` 데이터를 Railway로 옮기려면:

### 방법 1: Railway CLI 사용

```bash
# Railway CLI 설치
npm install -g @railway/cli

# 로그인
railway login

# 프로젝트 연결
railway link

# 볼륨에 파일 복사
railway run cp billing.db /app/data/billing.db
```

### 방법 2: 앱 내 업로드 기능 사용

배포 후 웹 앱에서 Excel 파일 업로드로 데이터 재구성

---

## ✅ 배포 확인

1. **Backend 헬스체크**
   ```
   https://your-backend.up.railway.app/health
   ```

2. **Frontend 접속**
   ```
   https://your-frontend.up.railway.app
   ```

---

## 💰 예상 비용

| 플랜 | 비용 | Volume |
|------|------|--------|
| Trial | 무료 ($5 크레딧) | ❌ |
| Hobby | $5/월 | ✅ 5GB |
| Pro | $20/월 | ✅ 50GB |

> SQLite + Volume 사용 시 **Hobby 플랜($5/월)** 이상 필요

---

## 🔧 트러블슈팅

### DB 파일을 찾을 수 없음

- Volume이 `/app/data`에 마운트되었는지 확인
- `DATABASE_PATH` 환경변수가 `/app/data/billing.db`인지 확인

### CORS 에러

- Backend의 `CORS_ORIGINS`에 Frontend 도메인 추가
- `https://` 포함 확인

### 빌드 실패

- Dockerfile 경로 확인
- 의존성 버전 확인

---

## 📞 지원

문제가 있으면 Railway Discord 또는 문서 참조:
- https://docs.railway.app
- https://discord.gg/railway

