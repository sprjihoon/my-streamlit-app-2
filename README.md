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
