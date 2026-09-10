# Railway 배포 운영 절차

## ⚠️ 배포 차단사항 — Volume 마운트 전 DB 백업 필수

> **위험**: `DATABASE_PATH=/app/data/billing.db` 설정 상태에서 Railway Volume을
> `/app/data`에 마운트하면, **빈 볼륨이 기존 파일시스템을 덮어써 DB가 즉시 삭제**됩니다.
> 반드시 아래 백업 절차를 완료한 후 Volume을 추가하십시오.

---

## 0. Volume 추가 전 DB 백업 절차 (필수)

> Volume 마운트는 기존 `/app/data` 내용을 **완전히 대체**합니다.  
> 서비스에 이미 데이터가 있다면 다음 순서를 반드시 따르십시오.

### 0-1. 현재 DB 다운로드

1. Railway Dashboard → **Shell** 탭 열기 (또는 `railway run bash`)
2. 다음 명령으로 DB 내용 확인:
   ```bash
   ls -lh /app/data/billing.db 2>/dev/null || echo "DB없음 — 볼륨 추가 안전"
   ```
3. DB가 존재하면 로컬로 복사:
   ```bash
   # 로컬 터미널에서:
   railway run --service <service-name> -- cat /app/data/billing.db > billing_backup_$(date +%Y%m%d).db
   ```
   또는 Railway Dashboard > Volumes 탭 > 파일 브라우저에서 직접 다운로드.

### 0-2. Volume 추가 후 DB 복원

1. Railway Dashboard → **Volumes** 탭 → **Add Volume** → Mount Path: `/app/data`
2. 배포 완료 후 Shell에서 DB 업로드:
   ```bash
   railway run -- sh -c "cat > /app/data/billing.db" < billing_backup_<날짜>.db
   ```
3. 앱 재시작: `railway service restart`
4. 사진·DB 이상 없는지 확인

> 운영 DB 백업 수단이 없다면 Volume 마운트를 중단하고 운영팀에 문의하십시오.

---

## 환경변수

| 변수 | 권장값 | 설명 |
|---|---|---|
| `UPLOAD_DIR` | `/app/data/uploads` | 사진 저장 디렉터리 |
| `DATABASE_PATH` | `/app/data/billing.db` | SQLite DB 경로 (Volume 마운트 후) |

## 1. 사진 영구 저장 설정 (필수)

기본 컨테이너 파일시스템(`/app/data/uploads`)은 **재시작마다 초기화**됩니다.  
사진을 영구 보존하려면 Railway Volume을 반드시 설정해야 합니다.

### 설정 절차

> ⚠️ 반드시 **섹션 0 (DB 백업)** 완료 후 진행하십시오.

1. Railway Dashboard → 해당 서비스 선택
2. **Volumes** 탭 → **Add Volume**
3. Mount Path: `/app/data`
4. 환경변수 확인: `UPLOAD_DIR=/app/data/uploads`, `DATABASE_PATH=/app/data/billing.db`
5. 섹션 0-2 절차로 DB 복원
6. 테스트 사진 업로드
7. 서비스 **Restart** (강제 재시작)
8. 사진이 유지되는지 확인

### 확인 방법

앱 기동 로그에서 다음 메시지 확인:

```
[UPLOAD_DIR] OK — 쓰기 가능: /app/data/uploads
[UPLOAD_DIR] 영구 볼륨 마운트 감지: /app/data
```

볼륨 미설정 시:

```
[UPLOAD_DIR] 경고: /app/data 가 마운트된 영구 볼륨이 아닌 것으로 보입니다.
```

## 주의사항

- `DATABASE_PATH`가 이미 영구 볼륨을 사용 중이면 Volume 추가 시 **DB 백업 필수**.
- Railway Volume은 코드에서 자동 생성되지 않습니다. Dashboard에서 수동 추가해야 합니다.
- 개발/테스트 환경에서는 `data/uploads` (로컬 임시 경로)를 사용합니다.
- Volume 마운트 전에 `billing.db`가 없으면 앱이 자동 생성하므로 안전합니다 (신규 배포).
- **빈 Volume + 기존 DB**: 기존 데이터 전부 유실 위험. 반드시 백업 후 복원하십시오.

---

## 변경 이력

### 2026-09-10 — 실 인보이스 관리: PDF→엑셀 전환

**제거**
- PDF 업로드 엔드포인트 `POST /billing-invoice/upload`
- pdfplumber 텍스트 추출 로직
- GPT-4o OCR 파싱 (`_parse_pdf_text`, `_gpt_parse`, `_regex_extract_totals` 등)
- 프론트엔드 다중 PDF 업로드 UI·진행바·AI 파싱 결과 표시

**추가**
- Excel 업로드 엔드포인트 `POST /billing-invoice/upload-excel`
  - 형식: `No | 파일명 | 업체명 | 청구금액(원)` (첫 행 헤더, 합계 행 자동 스킵)
  - 파일명에서 서비스월 자동 추출 (`2026_08월_...xlsx` → `2026-08`)
  - 중복 체크 (업체명+서비스월+청구금액) 유지
- 프론트엔드 엑셀 드래그 앤 드롭 업로드 존 (`.xlsx`/`.xls`)
- 업로드 결과: 등록 N건 / 중복 N건 / 오류 N건 표시

**DB 초기화**
- `billing_invoices`, `billing_invoice_items` 전체 데이터 삭제 후 재시작
