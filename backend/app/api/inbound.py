"""
backend/app/api/inbound.py - 입고모드 API
────────────────────────────────────────────
장끼 사진 OCR → 상품 자동 매칭 → 실수량 확인 → 양품화 → 마감

상태 흐름:
  ocr_pending   장끼 확인 중
  confirming    수량 확인 중 (OCR 완료, 직원 실수량 입력 전)
  inbound_done  입고접수 완료 (실수량 확정)
  grading       양품화 중
  repairing     수선 중
  done          최종완료
  cancelled     취소
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Form, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.config import settings
from logic.db import get_connection

router = APIRouter(prefix="/inbound", tags=["inbound"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "inbound"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────
# 비밀번호 해시 헬퍼
# ─────────────────────────────────────

def _hash_password(plain: str) -> str:
    """SHA-256 + random 16-byte hex salt.
    저장 형식: sha256:{salt}:{hex_digest}
    원문 비밀번호는 이 함수 호출 후 즉시 폐기해야 합니다.
    """
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{plain}".encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{digest}"


def _verify_password(plain: str, stored: str) -> bool:
    """해시 비교 (타이밍 공격 방지 compare_digest 사용).
    stored 가 sha256:… 형식이 아닌 경우(레거시 플레인텍스트) 도 처리.
    """
    if not stored:
        return not plain  # 저장 비번 없음 → 빈 값만 통과
    if stored.startswith("sha256:"):
        parts = stored.split(":", 2)
        if len(parts) != 3:
            return False
        _, salt, h = parts
        candidate = hashlib.sha256(f"{salt}:{plain}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, h)
    # 레거시: 플레인텍스트로 저장된 경우 (해시 마이그레이션 전 데이터)
    return hmac.compare_digest(plain, stored)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}

# ─────────────────────────────────────
# 상태 정의
# ─────────────────────────────────────

STATUS_VALUES = ("ocr_pending", "confirming", "inbound_done", "grading", "repairing", "done", "cancelled")
STATUS_LABELS = {
    "ocr_pending": "장끼 확인 중",
    "confirming":  "수량 확인 중",
    "inbound_done": "양품화 중",          # 오전 입고접수 완료 후 상태
    "grading":     "양품화 중(수선처리)",  # 수선 품목 있을 때
    "repairing":   "수선 중",
    "done":        "최종완료",
    "cancelled":   "취소",
}

ITEM_STATUS_VALUES = ("pending", "confirmed", "missing", "defect", "repair", "unrecoverable", "done", "etc")
ITEM_STATUS_LABELS = {
    "pending": "확인 전",
    "confirmed": "정상",
    "missing": "미입고",
    "defect": "불량",
    "repair": "수선대기",
    "unrecoverable": "회생불가",
    "done": "완료",
    "etc": "기타",
}


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class InboundBatchCreate(BaseModel):
    vendor: str                           # 화주사 (표시명 / 직접입력)
    vendor_canonical: Optional[str] = None  # repair_barcode.업체명 정식명 (선택 시)
    inbound_date: str                     # YYYY-MM-DD
    memo: Optional[str] = None
    created_by: Optional[str] = None


class InboundBatchUpdate(BaseModel):
    status: Optional[str] = None
    memo: Optional[str] = None
    vendor: Optional[str] = None
    inbound_date: Optional[str] = None


class InboundItemUpdate(BaseModel):
    actual_qty: Optional[int] = None
    missing_qty: Optional[int] = None
    status: Optional[str] = None
    memo: Optional[str] = None
    matched_barcode: Optional[str] = None
    matched_vendor: Optional[str] = None
    matched_product: Optional[str] = None
    matched_option: Optional[str] = None
    supplier_location: Optional[str] = None
    supplier_contact: Optional[str] = None


class InboundItemCreate(BaseModel):
    """수동 품목 추가"""
    item_name: str
    option_text: Optional[str] = None
    unit_price: Optional[float] = None
    janggi_qty: int = 0
    actual_qty: int = 0
    missing_qty: int = 0
    matched_barcode: Optional[str] = None
    matched_vendor: Optional[str] = None
    matched_product: Optional[str] = None
    matched_option: Optional[str] = None
    supplier_location: Optional[str] = None
    supplier_contact: Optional[str] = None
    memo: Optional[str] = None


# ─────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────

def ensure_inbound_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_batches (
                id TEXT PRIMARY KEY,
                vendor TEXT NOT NULL,
                inbound_date TEXT NOT NULL,
                status TEXT DEFAULT 'ocr_pending',
                memo TEXT,
                receipt_id TEXT,
                janggi_filename TEXT,
                janggi_date TEXT,
                janggi_no TEXT,
                wholesale TEXT,
                total_janggi_qty INTEGER DEFAULT 0,
                total_actual_qty INTEGER DEFAULT 0,
                total_missing_qty INTEGER DEFAULT 0,
                created_by TEXT,
                closed_by TEXT,
                closed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_items (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                line_no INTEGER DEFAULT 0,
                item_name TEXT,
                option_text TEXT,
                unit_price REAL,
                janggi_qty INTEGER DEFAULT 0,
                actual_qty INTEGER DEFAULT 0,
                missing_qty INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                matched_barcode TEXT,
                matched_vendor TEXT,
                matched_product TEXT,
                matched_option TEXT,
                match_confidence REAL DEFAULT 0.0,
                needs_matching INTEGER DEFAULT 0,
                supplier_location TEXT,
                supplier_contact TEXT,
                memo TEXT,
                defect_case_id TEXT,
                inbound_item_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_item_photos (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES inbound_items(id)
            )
        """)
    # inbound_share_links 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_share_links (
                token TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                password TEXT,
                expires_at TEXT,
                allow_excel INTEGER DEFAULT 0,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        # barcode_print_jobs 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS barcode_print_jobs (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                item_id TEXT,
                barcode TEXT,
                product TEXT,
                option_text TEXT,
                vendor TEXT,
                wholesale TEXT,
                qty INTEGER DEFAULT 1,
                pdf_filename TEXT,
                printed_by TEXT,
                printed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        # 벤더 별칭 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_vendor_aliases (
                canonical TEXT PRIMARY KEY,
                aliases TEXT DEFAULT '',
                memo TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 기존 테이블에 inbound 연결 컬럼 추가
        for table, col in [
            ("defect_log",      "inbound_item_id TEXT"),
            ("defect_log",      "defect_case_id TEXT"),
            ("repair_work_log", "inbound_item_id TEXT"),
            ("repair_work_log", "defect_case_id TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except Exception:
                pass  # 이미 존재하면 무시
        # inbound_batches 에 vendor_canonical 컬럼 추가
        try:
            con.execute("ALTER TABLE inbound_batches ADD COLUMN vendor_canonical TEXT")
        except Exception:
            pass
        # inbound_items 에 신규 컬럼 추가 (기존 DB 마이그레이션)
        for col_def in [
            "supplier_location TEXT",
            "supplier_contact TEXT",
            "updated_at DATETIME",
        ]:
            try:
                con.execute(f"ALTER TABLE inbound_items ADD COLUMN {col_def}")
            except Exception:
                pass
        con.commit()


# ─────────────────────────────────────
# 인증 헬퍼
# ─────────────────────────────────────

def _get_user(token: Optional[str]) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    tok = token.replace("Bearer ", "").strip()
    with get_connection() as con:
        row = con.execute(
            """SELECT u.user_id, u.nickname, u.is_admin
               FROM sessions s JOIN users u ON s.user_id = u.user_id
               WHERE s.token = ?""",
            (tok,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return {"user_id": row[0], "nickname": row[1], "is_admin": bool(row[2])}


# ─────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────

async def _save_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(await file.read())
    return filename


def _image_url(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/inbound/photos/{filename}"


def _recalc_batch_totals(con, batch_id: str):
    """품목 수량 집계를 배치에 반영"""
    row = con.execute("""
        SELECT
            COALESCE(SUM(janggi_qty), 0),
            COALESCE(SUM(actual_qty), 0),
            COALESCE(SUM(missing_qty), 0)
        FROM inbound_items WHERE batch_id = ?
    """, (batch_id,)).fetchone()
    if row:
        con.execute("""
            UPDATE inbound_batches
            SET total_janggi_qty=?, total_actual_qty=?, total_missing_qty=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (row[0], row[1], row[2], batch_id))


def _serialize_batch(row) -> dict:
    return {
        "id": row[0],
        "vendor": row[1],
        "inbound_date": row[2],
        "status": row[3],
        "status_label": STATUS_LABELS.get(row[3], row[3]),
        "memo": row[4],
        "receipt_id": row[5],
        "janggi_filename": row[6],
        "janggi_date": row[7],
        "janggi_no": row[8],
        "wholesale": row[9],
        "total_janggi_qty": row[10],
        "total_actual_qty": row[11],
        "total_missing_qty": row[12],
        "created_by": row[13],
        "closed_by": row[14],
        "closed_at": row[15],
        "created_at": row[16],
        "updated_at": row[17],
    }


def _serialize_item(row) -> dict:
    return {
        "id": row[0],
        "batch_id": row[1],
        "line_no": row[2],
        "item_name": row[3],
        "option_text": row[4],
        "unit_price": row[5],
        "janggi_qty": row[6],
        "actual_qty": row[7],
        "missing_qty": row[8],
        "status": row[9],
        "status_label": ITEM_STATUS_LABELS.get(row[9], row[9]),
        "matched_barcode": row[10],
        "matched_vendor": row[11],
        "matched_product": row[12],
        "matched_option": row[13],
        "match_confidence": row[14],
        "needs_matching": bool(row[15]),
        "memo": row[16],
        "supplier_location": row[17],
        "supplier_contact": row[18],
        "created_at": row[19],
        "updated_at": row[20],
    }


def _get_item_photos(con, item_id: str) -> list:
    rows = con.execute(
        "SELECT id, filename, created_at FROM inbound_item_photos WHERE item_id=? ORDER BY created_at",
        (item_id,)
    ).fetchall()
    return [{"id": r[0], "url": _image_url(r[1]), "filename": r[1], "created_at": r[2]} for r in rows]


# ─────────────────────────────────────
# 상품 자동 매칭
# ─────────────────────────────────────

def _resolve_vendor_names(vendor: str) -> List[str]:
    """
    주어진 vendor 문자열에 대해 매칭 가능한 모든 업체명 반환.
    1) repair_barcode 에 vendor 그대로 있으면 우선
    2) inbound_vendor_aliases 에서 canonical 또는 alias 로 등록된 업체 포함
    3) 없으면 [vendor] 그대로
    """
    names = [vendor]
    with get_connection() as con:
        # canonical 로 등록된 경우 → 별칭들도 추가 (역방향: 별칭 포함 바코드 검색 위해)
        row = con.execute(
            "SELECT aliases FROM inbound_vendor_aliases WHERE canonical=?", (vendor,)
        ).fetchone()
        if row and row[0]:
            names += [a.strip() for a in row[0].split(",") if a.strip()]
        # 혹시 vendor 가 별칭으로 등록된 경우 → canonical 추가
        rows = con.execute(
            "SELECT canonical FROM inbound_vendor_aliases WHERE aliases LIKE ?",
            (f"%{vendor}%",)
        ).fetchall()
        for r in rows:
            if r[0] not in names:
                names.append(r[0])
    return list(dict.fromkeys(names))  # 중복 제거, 순서 유지


def _match_barcode(vendor: str, item_name: str, option_text: Optional[str], wholesale: Optional[str]) -> dict:
    """
    repair_barcode DB에서 품목을 매칭한다.
    반환: {matched_barcode, matched_vendor, matched_product, matched_option, match_confidence, needs_matching}
    """
    result = {
        "matched_barcode": None,
        "matched_vendor": None,
        "matched_product": None,
        "matched_option": None,
        "match_confidence": 0.0,
        "needs_matching": True,
    }
    if not item_name:
        return result

    vendor_names = _resolve_vendor_names(vendor)  # 별칭 포함 후보 업체명 목록
    vendor_ph = ",".join("?" * len(vendor_names))  # IN (?,?,...) 플레이스홀더

    with get_connection() as con:
        # 1순위: 화주사(별칭 포함) + 도매처 + 공급처상품명/상품명 + 옵션 정확 매칭
        if wholesale and option_text:
            row = con.execute(f"""
                SELECT 바코드, 업체명, 공급처상품명, 옵션
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (공급처상품명=? OR 상품명=?)
                  AND 옵션=?
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name, option_text)).fetchone()
            if row:
                return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                        "matched_product": row[2] or item_name, "matched_option": row[3],
                        "match_confidence": 1.0, "needs_matching": False}

        # 2순위: 화주사(별칭 포함) + 도매처 + 상품명 (옵션 무시)
        if wholesale:
            row = con.execute(f"""
                SELECT 바코드, 업체명, 공급처상품명, 옵션
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (공급처상품명=? OR 상품명=?)
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name)).fetchone()
            if row:
                return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                        "matched_product": row[2] or item_name, "matched_option": row[3],
                        "match_confidence": 0.85, "needs_matching": False}

        # 3순위: 화주사(별칭 포함) + 상품명
        row = con.execute(f"""
            SELECT 바코드, 업체명, 공급처상품명, 옵션
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (공급처상품명=? OR 상품명=?)
            LIMIT 1
        """, (*vendor_names, item_name, item_name)).fetchone()
        if row:
            return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                    "matched_product": row[2] or item_name, "matched_option": row[3],
                    "match_confidence": 0.7, "needs_matching": False}

        # 4순위: 부분 일치 (LIKE) — 화주사 별칭 포함
        keyword = f"%{item_name}%"
        row = con.execute(f"""
            SELECT 바코드, 업체명, 공급처상품명, 옵션
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (공급처상품명 LIKE ? OR 상품명 LIKE ?)
            LIMIT 1
        """, (*vendor_names, keyword, keyword)).fetchone()
        if row:
            return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                    "matched_product": row[2] or item_name, "matched_option": row[3],
                    "match_confidence": 0.5, "needs_matching": True}

    return result


# ─────────────────────────────────────
# OCR (장끼 이미지 분석)
# ─────────────────────────────────────

async def _run_ocr(image_path: Path) -> Optional[dict]:
    """GPT-4o Vision으로 장끼 분석 (receipt.py 동일 로직)"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import httpx
        data = image_path.read_bytes()
        b64 = base64.b64encode(data).decode()
        ext = image_path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")

        system_prompt = """너는 동대문 장끼/영수증을 분석하는 AI다. 이미지에서 다음을 추출하라.

반드시 아래 JSON 형식만 반환하라:
{
  "receipt": {
    "storeName": "거래처명(발신인/공급자) 또는 null",
    "receiptNo": "영수증번호 또는 null",
    "orderDate": "YYYY-MM-DD 또는 null",
    "totalAmount": 숫자 또는 null,
    "isHandwritten": true|false,
    "confidence": 0.0~1.0,
    "needsReview": true|false,
    "warnings": []
  },
  "items": [
    {
      "lineNo": 1,
      "itemName": "품명(색상/사이즈/옵션 제외)",
      "color": "색상 또는 null",
      "optionText": "기타 옵션 또는 null",
      "unitPrice": 단가 숫자 또는 null,
      "quantity": 수량 숫자 또는 null,
      "amount": 금액 숫자 또는 null,
      "confidence": 0.0~1.0,
      "needsReview": true|false,
      "warnings": []
    }
  ]
}

규칙:
- 품명과 색상/옵션을 분리한다
- 수기 글씨는 isHandwritten=true, needsReview=true
- confidence < 0.8 이면 needsReview=true
- 필수값 누락 시 warnings에 기록
- 숫자는 콤마/원 제거 후 숫자만 반환"""

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "auto"}}
                ]}
            ],
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None


# ─────────────────────────────────────
# 라우터
# ─────────────────────────────────────

# ── 입고 배치 목록 ──────────────────────

@router.get("/batches")
def list_batches(
    vendor: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    where = ["1=1"]
    params: list = []
    if vendor:
        where.append("vendor=?"); params.append(vendor)
    if status:
        where.append("status=?"); params.append(status)
    if date_from:
        where.append("inbound_date>=?"); params.append(date_from)
    if date_to:
        where.append("inbound_date<=?"); params.append(date_to)

    sql = f"""
        SELECT id, vendor, inbound_date, status, memo, receipt_id,
               janggi_filename, janggi_date, janggi_no, wholesale,
               total_janggi_qty, total_actual_qty, total_missing_qty,
               created_by, closed_by, closed_at, created_at, updated_at
        FROM inbound_batches
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    with get_connection() as con:
        rows = con.execute(sql, params).fetchall()
        total = con.execute(
            f"SELECT COUNT(*) FROM inbound_batches WHERE {' AND '.join(where)}",
            params[:-2]
        ).fetchone()[0]
    return {"items": [_serialize_batch(r) for r in rows], "total": total}


# ── 입고 배치 생성 ──────────────────────

@router.post("/batches", status_code=201)
def create_batch(
    body: InboundBatchCreate,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    batch_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, vendor_canonical, inbound_date, status, memo, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'ocr_pending', ?, ?, ?, ?)
        """, (batch_id, body.vendor, body.vendor_canonical or body.vendor,
              body.inbound_date, body.memo,
              body.created_by or user["nickname"], now, now))
        con.commit()
    add_log("inbound", "create_batch", f"입고 배치 생성: {body.vendor} {body.inbound_date}", user["user_id"])
    return {"id": batch_id, "status": "ocr_pending"}


# ── 입고 배치 상세 ──────────────────────

@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        row = con.execute("""
            SELECT id, vendor, inbound_date, status, memo, receipt_id,
                   janggi_filename, janggi_date, janggi_no, wholesale,
                   total_janggi_qty, total_actual_qty, total_missing_qty,
                   created_by, closed_by, closed_at, created_at, updated_at
            FROM inbound_batches WHERE id=?
        """, (batch_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        batch = _serialize_batch(row)

        items = con.execute("""
            SELECT id, batch_id, line_no, item_name, option_text, unit_price,
                   janggi_qty, actual_qty, missing_qty, status,
                   matched_barcode, matched_vendor, matched_product, matched_option,
                   match_confidence, needs_matching, memo,
                   supplier_location, supplier_contact, created_at, updated_at
            FROM inbound_items WHERE batch_id=? ORDER BY line_no, created_at
        """, (batch_id,)).fetchall()
        item_list = []
        for item_row in items:
            item = _serialize_item(item_row)
            item["photos"] = _get_item_photos(con, item_row[0])
            item_list.append(item)

    batch["items"] = item_list
    return batch


# ── 입고 배치 수정 ──────────────────────

@router.patch("/batches/{batch_id}")
def update_batch(
    batch_id: str,
    body: InboundBatchUpdate,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    fields, params = [], []
    if body.status is not None:
        if body.status not in STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {body.status}")
        fields.append("status=?"); params.append(body.status)
    if body.memo is not None:
        fields.append("memo=?"); params.append(body.memo)
    if body.vendor is not None:
        fields.append("vendor=?"); params.append(body.vendor)
    if body.inbound_date is not None:
        fields.append("inbound_date=?"); params.append(body.inbound_date)
    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    fields.append("updated_at=CURRENT_TIMESTAMP")
    params.append(batch_id)
    with get_connection() as con:
        con.execute(f"UPDATE inbound_batches SET {', '.join(fields)} WHERE id=?", params)
        con.commit()
    return {"ok": True}


# ── 장끼 OCR + 자동 매칭 ─────────────────

@router.post("/batches/{batch_id}/ocr")
async def run_ocr(
    batch_id: str,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지 업로드 → OCR → repair_barcode 자동 매칭 → inbound_items 생성"""
    user = _get_user(authorization)

    # 배치 조회
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT id, vendor, status, vendor_canonical FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
    if not batch_row:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

    # vendor_canonical 우선 사용 (없으면 vendor 그대로)
    vendor = batch_row[3] or batch_row[1]

    # 이미지 저장
    janggi_filename = await _save_upload(file)
    image_path = UPLOAD_DIR / janggi_filename

    # OCR 실행
    ocr_result = await _run_ocr(image_path)

    receipt_data = ocr_result.get("receipt", {}) if ocr_result else {}
    items_data = ocr_result.get("items", []) if ocr_result else []

    wholesale = receipt_data.get("storeName")  # 장끼의 발신인 = 도매처
    janggi_date = receipt_data.get("orderDate")
    janggi_no = receipt_data.get("receiptNo")

    now = datetime.utcnow().isoformat()
    created_items = []

    with get_connection() as con:
        # 기존 OCR 생성 품목 삭제 (재시도 시)
        con.execute("DELETE FROM inbound_items WHERE batch_id=? AND (memo LIKE '%OCR%' OR memo IS NULL)",
                    (batch_id,))

        for i, item in enumerate(items_data):
            item_id = uuid.uuid4().hex
            item_name = item.get("itemName") or ""
            option_text = item.get("color") or item.get("optionText") or ""
            unit_price = item.get("unitPrice")
            janggi_qty = int(item.get("quantity") or 0)

            # 자동 매칭
            match = _match_barcode(vendor, item_name, option_text or None, wholesale)

            needs_review = bool(item.get("needsReview", False))
            needs_matching = match["needs_matching"] or needs_review

            con.execute("""
                INSERT INTO inbound_items
                    (id, batch_id, line_no, item_name, option_text, unit_price,
                     janggi_qty, actual_qty, missing_qty, status,
                     matched_barcode, matched_vendor, matched_product, matched_option,
                     match_confidence, needs_matching, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id, batch_id, i + 1, item_name, option_text or None, unit_price,
                janggi_qty,
                match["matched_barcode"], match["matched_vendor"],
                match["matched_product"], match["matched_option"],
                match["match_confidence"], int(needs_matching),
                "OCR", now,
            ))
            created_items.append({
                "id": item_id,
                "line_no": i + 1,
                "item_name": item_name,
                "option_text": option_text,
                "janggi_qty": janggi_qty,
                **match,
            })

        # 배치 업데이트
        _recalc_batch_totals(con, batch_id)
        con.execute("""
            UPDATE inbound_batches
            SET janggi_filename=?, janggi_date=?, janggi_no=?,
                wholesale=?, status='confirming', updated_at=?
            WHERE id=?
        """, (janggi_filename, janggi_date, janggi_no, wholesale, now, batch_id))
        con.commit()

    matched_count = sum(1 for it in created_items if not it["needs_matching"])
    needs_count = len(created_items) - matched_count

    add_log("inbound", "ocr", f"OCR: {vendor} {len(created_items)}개 ({matched_count}매칭/{needs_count}확인필요)", user["user_id"])
    return {
        "ok": True,
        "item_count": len(created_items),
        "matched_count": matched_count,
        "needs_matching_count": needs_count,
        "wholesale": wholesale,
        "janggi_date": janggi_date,
        "items": created_items,
    }


# ── 품목 수동 추가 ──────────────────────

@router.post("/batches/{batch_id}/items", status_code=201)
def add_item(
    batch_id: str,
    body: InboundItemCreate,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        if not con.execute("SELECT 1 FROM inbound_batches WHERE id=?", (batch_id,)).fetchone():
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        item_id = uuid.uuid4().hex
        max_line = con.execute(
            "SELECT COALESCE(MAX(line_no),0) FROM inbound_items WHERE batch_id=?", (batch_id,)
        ).fetchone()[0]
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, option_text, unit_price,
                 janggi_qty, actual_qty, missing_qty, status,
                 matched_barcode, matched_vendor, matched_product, matched_option,
                 match_confidence, needs_matching, memo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, batch_id, max_line + 1, body.item_name, body.option_text, body.unit_price,
            body.janggi_qty, body.actual_qty, body.missing_qty,
            body.matched_barcode, body.matched_vendor, body.matched_product, body.matched_option,
            1.0 if body.matched_barcode else 0.0,
            0 if body.matched_barcode else 1,
            body.memo,
        ))
        _recalc_batch_totals(con, batch_id)
        con.commit()
    return {"id": item_id}


# ── 품목 수정 ───────────────────────────

@router.patch("/items/{item_id}")
def update_item(
    item_id: str,
    body: InboundItemUpdate,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    fields, params = [], []

    if body.actual_qty is not None:
        fields.append("actual_qty=?"); params.append(body.actual_qty)
    if body.missing_qty is not None:
        fields.append("missing_qty=?"); params.append(body.missing_qty)
    if body.status is not None:
        if body.status not in ITEM_STATUS_VALUES:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 품목 상태: {body.status}")
        fields.append("status=?"); params.append(body.status)
    if body.memo is not None:
        fields.append("memo=?"); params.append(body.memo)
    if body.matched_barcode is not None:
        fields.append("matched_barcode=?"); params.append(body.matched_barcode)
        fields.append("needs_matching=0")
    if body.matched_vendor is not None:
        fields.append("matched_vendor=?"); params.append(body.matched_vendor)
    if body.matched_product is not None:
        fields.append("matched_product=?"); params.append(body.matched_product)
    if body.matched_option is not None:
        fields.append("matched_option=?"); params.append(body.matched_option)
    if body.supplier_location is not None:
        fields.append("supplier_location=?"); params.append(body.supplier_location)
    if body.supplier_contact is not None:
        fields.append("supplier_contact=?"); params.append(body.supplier_contact)

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

    fields.append("updated_at=CURRENT_TIMESTAMP")
    params.append(item_id)
    with get_connection() as con:
        con.execute(f"UPDATE inbound_items SET {', '.join(fields)} WHERE id=?", params)
        batch_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if batch_row:
            _recalc_batch_totals(con, batch_row[0])
        con.commit()
    return {"ok": True}


# ── 품목 삭제 ───────────────────────────

@router.delete("/items/{item_id}")
def delete_item(
    item_id: str,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    with get_connection() as con:
        batch_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        # 사진 파일 삭제
        photos = con.execute("SELECT filename FROM inbound_item_photos WHERE item_id=?", (item_id,)).fetchall()
        for p in photos:
            try: (UPLOAD_DIR / p[0]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE item_id=?", (item_id,))
        con.execute("DELETE FROM inbound_items WHERE id=?", (item_id,))
        if batch_row:
            _recalc_batch_totals(con, batch_row[0])
        con.commit()
    return {"ok": True}


# ── 제품 사진 업로드 ──────────────────

@router.post("/items/{item_id}/photos", status_code=201)
async def upload_item_photo(
    item_id: str,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        item_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
        batch_id = item_row[0]

    filename = await _save_upload(file)
    photo_id = uuid.uuid4().hex
    with get_connection() as con:
        con.execute(
            "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename) VALUES (?, ?, ?, ?)",
            (photo_id, item_id, batch_id, filename)
        )
        con.commit()
    return {"id": photo_id, "url": _image_url(filename)}


# ── 제품 사진 삭제 ─────────────────────

@router.delete("/items/{item_id}/photos/{photo_id}")
def delete_item_photo(
    item_id: str,
    photo_id: str,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    with get_connection() as con:
        row = con.execute(
            "SELECT filename FROM inbound_item_photos WHERE id=? AND item_id=?",
            (photo_id, item_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
        try: (UPLOAD_DIR / row[0]).unlink(missing_ok=True)
        except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE id=?", (photo_id,))
        con.commit()
    return {"ok": True}


# ── 사진 파일 서빙 ─────────────────────

@router.get("/photos/{filename}")
def serve_photo(
    filename: str,
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    # 경로 탈출 방지
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
    return FileResponse(path)


# ── 마감 (AM/PM 분리) ────────────────────

class CloseRequest(BaseModel):
    """
    close_type:
      'am'  오전 입고접수 완료  confirming → inbound_done (양품화 중)
      'pm'  오후 최종 마감      inbound_done / grading / repairing → done (수량 확정)
    """
    close_type: str = "am"  # "am" | "pm"


@router.post("/batches/{batch_id}/close")
def close_batch(
    batch_id: str,
    body: CloseRequest = CloseRequest(),
    authorization: Optional[str] = Header(None),
):
    """
    오전(am): confirming → inbound_done (양품화 중 시작, 확인 전 품목 없어야 함)
    오후(pm): inbound_done / grading / repairing → done
              장끼수량 = 미입고 + 일반정상 + 수선중 + 수선후정상 + 회생불가 검증 포함
    """
    close_type = body.close_type.lower().strip()
    if close_type not in ("am", "pm"):
        raise HTTPException(status_code=400, detail="close_type은 'am' 또는 'pm'이어야 합니다.")

    user = _get_user(authorization)
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT status, total_janggi_qty, total_actual_qty, total_missing_qty FROM inbound_batches WHERE id=?",
            (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        current_status = batch_row[0]
        total_janggi = batch_row[1] or 0

        # ── 오전 마감: confirming → inbound_done ──────────────
        if close_type == "am":
            if current_status != "confirming":
                return {"ok": False, "warning": f"오전 입고접수 완료는 '수량 확인 중' 상태에서만 가능합니다. (현재: {STATUS_LABELS.get(current_status, current_status)})"}

            pending_count = con.execute(
                "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'",
                (batch_id,)
            ).fetchone()[0]
            if pending_count > 0:
                return {
                    "ok": False,
                    "warning": f"확인 전 품목이 {pending_count}개 남아 있습니다. 모두 확인 후 오전 완료해주세요.",
                    "pending_count": pending_count,
                }

            next_status = "inbound_done"
            now = datetime.utcnow().isoformat()
            con.execute(
                "UPDATE inbound_batches SET status=?, updated_at=? WHERE id=?",
                (next_status, now, batch_id)
            )
            con.commit()
            add_log("inbound", "am_close", f"오전 입고접수 완료: {batch_id}", user["user_id"])
            return {
                "ok": True,
                "close_type": "am",
                "status": next_status,
                "status_label": STATUS_LABELS[next_status],
                "message": "오전 입고접수 완료 — 양품화를 진행해주세요",
            }

        # ── 오후 마감: inbound_done / grading / repairing → done ──
        # close_type == "pm"
        if current_status == "done":
            return {"ok": False, "warning": "이미 최종 마감된 입고건입니다."}
        if current_status not in ("inbound_done", "grading", "repairing"):
            return {"ok": False, "warning": f"오후 최종 마감은 '양품화 중' 또는 '수선 중' 상태에서만 가능합니다. (현재: {STATUS_LABELS.get(current_status, current_status)})"}

        # 미처리 품목 경고 (pending 또는 defect)
        unresolved = con.execute(
            "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status IN ('pending', 'defect')",
            (batch_id,)
        ).fetchone()[0]
        if unresolved > 0:
            return {
                "ok": False,
                "warning": f"미처리(확인전/불량) 품목이 {unresolved}개 있습니다. 처리 후 오후 마감해주세요.",
                "unresolved_count": unresolved,
            }

        # ── 수량 정산 ──
        # 공식: 장끼수량 = 미입고 + 일반정상 + 수선중 + 수선후정상 + 회생불가
        rows = con.execute("""
            SELECT status,
                   COALESCE(SUM(actual_qty),  0) AS actual_sum,
                   COALESCE(SUM(missing_qty), 0) AS missing_sum,
                   COALESCE(SUM(janggi_qty),  0) AS janggi_sum
            FROM inbound_items WHERE batch_id=? GROUP BY status
        """, (batch_id,)).fetchall()
        sd: dict[str, dict] = {r[0]: {"actual": r[1], "missing": r[2], "janggi": r[3]} for r in rows}

        # 각 카테고리 수량 (개수 기준)
        정상_qty     = sd.get("confirmed",     {}).get("actual", 0)
        수선중_qty    = sd.get("repair",        {}).get("actual", 0)
        수선후정상_qty = sd.get("done",          {}).get("actual", 0)
        회생불가_qty  = sd.get("unrecoverable", {}).get("actual", 0)
        # 미입고: 전체 품목의 missing_qty 합계 (어떤 status든 missing_qty가 있으면 미입고)
        미입고_qty = sum(v["missing"] for v in sd.values())

        formula_total = 미입고_qty + 정상_qty + 수선중_qty + 수선후정상_qty + 회생불가_qty
        discrepancy = total_janggi - formula_total  # 0이면 정상

        now = datetime.utcnow().isoformat()
        con.execute("""
            UPDATE inbound_batches
            SET status='done', closed_by=?, closed_at=?, updated_at=?
            WHERE id=?
        """, (user["nickname"], now, now, batch_id))
        con.commit()

    add_log("inbound", "pm_close",
            f"오후 최종 마감: {batch_id} | 정상{정상_qty}/수선중{수선중_qty}/수선후{수선후정상_qty}/회생불가{회생불가_qty}/미입고{미입고_qty}",
            user["user_id"])

    result = {
        "ok": True,
        "close_type": "pm",
        "status": "done",
        "status_label": STATUS_LABELS["done"],
        "message": "오후 최종 마감 완료",
        # ── 수량 정산 (공식 기준) ──
        "total_janggi_qty":    total_janggi,
        "정상_qty":            정상_qty,
        "수선중_qty":           수선중_qty,
        "수선후정상_qty":       수선후정상_qty,
        "회생불가_qty":         회생불가_qty,
        "미입고_qty":           미입고_qty,
        "formula_total":       formula_total,
        "discrepancy":         discrepancy,
        "formula_ok":          discrepancy == 0,
        "formula_str": (
            f"장끼{total_janggi} = 미입고{미입고_qty} + 정상{정상_qty} "
            f"+ 수선중{수선중_qty} + 수선후정상{수선후정상_qty} + 회생불가{회생불가_qty}"
            f" ({'✓ 일치' if discrepancy == 0 else f'⚠️ 차이 {discrepancy:+d}'})"
        ),
    }
    return result


# ── 배치 삭제 (관리자) ──────────────────

@router.delete("/batches/{batch_id}")
def delete_batch(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    user = _get_user(authorization)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 삭제할 수 있습니다.")
    with get_connection() as con:
        # 사진 파일 삭제
        photos = con.execute(
            "SELECT filename FROM inbound_item_photos WHERE batch_id=?", (batch_id,)
        ).fetchall()
        for p in photos:
            try: (UPLOAD_DIR / p[0]).unlink(missing_ok=True)
            except Exception: pass
        # 장끼 이미지 삭제
        janggi = con.execute("SELECT janggi_filename FROM inbound_batches WHERE id=?", (batch_id,)).fetchone()
        if janggi and janggi[0]:
            try: (UPLOAD_DIR / janggi[0]).unlink(missing_ok=True)
            except Exception: pass
        con.execute("DELETE FROM inbound_item_photos WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM inbound_items WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM inbound_batches WHERE id=?", (batch_id,))
        con.commit()
    return {"ok": True}


# ── 화주사 목록 (자동완성용) ────────────

@router.get("/vendors")
def list_inbound_vendors(
    authorization: Optional[str] = Header(None),
):
    """
    repair_barcode 등록 업체명 (registered) +
    최근 입고 실적 업체 (recent) 를 분리 반환.
    각 등록 업체에 별칭(aliases) 포함.
    """
    _get_user(authorization)
    with get_connection() as con:
        # repair_barcode 등록 업체 + 별칭
        barcode_vendors = [r[0] for r in con.execute(
            "SELECT DISTINCT \uc5c5\uccb4\uba85 FROM repair_barcode WHERE \uc5c5\uccb4\uba85 IS NOT NULL ORDER BY \uc5c5\uccb4\uba85"
        ).fetchall() if r[0]]
        alias_rows = {r[0]: r[1] for r in con.execute(
            "SELECT canonical, aliases FROM inbound_vendor_aliases"
        ).fetchall()}
        registered = [
            {
                "name": v,
                "aliases": [a.strip() for a in (alias_rows.get(v) or "").split(",") if a.strip()],
            }
            for v in barcode_vendors
        ]
        # 최근 입고 실적 업체 (등록 업체 제외)
        registered_names = set(barcode_vendors)
        recent_raw = [r[0] for r in con.execute(
            "SELECT DISTINCT vendor FROM inbound_batches ORDER BY created_at DESC LIMIT 20"
        ).fetchall() if r[0]]
        recent = [v for v in recent_raw if v not in registered_names]
    return {"registered": registered, "recent": recent}


# ── 벤더 별칭 관리 ──────────────────────

class VendorAliasUpdate(BaseModel):
    aliases: List[str]     # 새 별칭 목록 (덮어쓰기)
    memo: Optional[str] = None


@router.get("/vendor-aliases")
def get_vendor_aliases(authorization: Optional[str] = Header(None)):
    """등록된 벤더 별칭 전체 조회"""
    _get_user(authorization)
    with get_connection() as con:
        rows = con.execute(
            "SELECT canonical, aliases, memo FROM inbound_vendor_aliases ORDER BY canonical"
        ).fetchall()
    return {"aliases": [{"canonical": r[0], "aliases": [a.strip() for a in (r[1] or "").split(",") if a.strip()], "memo": r[2]} for r in rows]}


@router.put("/vendor-aliases/{canonical}")
def upsert_vendor_alias(
    canonical: str,
    body: VendorAliasUpdate,
    authorization: Optional[str] = Header(None),
):
    """특정 업체의 별칭 저장 (없으면 생성, 있으면 덮어쓰기)"""
    _get_user(authorization)
    aliases_str = ", ".join(a.strip() for a in body.aliases if a.strip())
    now = datetime.utcnow().isoformat()
    with get_connection() as con:
        con.execute("""
            INSERT INTO inbound_vendor_aliases (canonical, aliases, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(canonical) DO UPDATE SET
                aliases = excluded.aliases,
                memo = excluded.memo,
                updated_at = excluded.updated_at
        """, (canonical, aliases_str, body.memo, now, now))
        con.commit()
    return {"ok": True, "canonical": canonical, "aliases": body.aliases}


@router.delete("/vendor-aliases/{canonical}")
def delete_vendor_alias(
    canonical: str,
    authorization: Optional[str] = Header(None),
):
    """특정 업체 별칭 삭제"""
    _get_user(authorization)
    with get_connection() as con:
        con.execute("DELETE FROM inbound_vendor_aliases WHERE canonical=?", (canonical,))
        con.commit()
    return {"ok": True}


# ── 입고 통계 ───────────────────────────

@router.get("/stats")
def get_stats(
    year_month: Optional[str] = Query(None, description="YYYY-MM"),
    authorization: Optional[str] = Header(None),
):
    _get_user(authorization)
    where = "1=1"
    params: list = []
    if year_month:
        where = "inbound_date LIKE ?"
        params.append(f"{year_month}%")
    with get_connection() as con:
        rows = con.execute(f"""
            SELECT status, COUNT(*), SUM(total_janggi_qty), SUM(total_actual_qty), SUM(total_missing_qty)
            FROM inbound_batches WHERE {where}
            GROUP BY status
        """, params).fetchall()
    return {
        "by_status": [
            {"status": r[0], "status_label": STATUS_LABELS.get(r[0], r[0]),
             "count": r[1], "janggi_qty": r[2] or 0,
             "actual_qty": r[3] or 0, "missing_qty": r[4] or 0}
            for r in rows
        ]
    }


# ── 바코드 라벨 PDF ────────────────────

@router.post("/batches/{batch_id}/barcode-pdf")
def generate_barcode_pdf(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    실입고 확정 품목의 바코드 라벨 PDF 생성.
    품목별 actual_qty 수량만큼 라벨 생성.
    """
    from fastapi.responses import StreamingResponse as SR
    import io

    user = _get_user(authorization)

    with get_connection() as con:
        batch_row = con.execute(
            "SELECT vendor, inbound_date, wholesale FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        items = con.execute("""
            SELECT id, line_no, item_name, option_text, actual_qty,
                   matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items
            WHERE batch_id=? AND actual_qty > 0 AND matched_barcode IS NOT NULL
            ORDER BY line_no
        """, (batch_id,)).fetchall()

    if not items:
        raise HTTPException(status_code=400, detail="실입고 확정 및 바코드 매칭된 품목이 없습니다.")

    vendor = batch_row[0]
    inbound_date = batch_row[1]
    wholesale = batch_row[2] or ""

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.graphics.barcode import code128
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab 라이브러리가 없습니다. pip install reportlab")

    # 라벨 크기: 62mm × 38mm (열 4개 × 페이지)
    LABEL_W = 62 * mm
    LABEL_H = 38 * mm
    COLS = 3
    PAGE_W, PAGE_H = A4

    buf = io.BytesIO()

    from reportlab.pdfgen import canvas as rl_canvas
    c = rl_canvas.Canvas(buf, pagesize=A4)

    # 폰트 (한글 지원 - Noto Sans CJK 없으면 기본 폰트 사용)
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os as _os
        font_paths = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        font_loaded = False
        for fp in font_paths:
            if _os.path.exists(fp):
                pdfmetrics.registerFont(TTFont("NotoKR", fp))
                FONT = "NotoKR"
                font_loaded = True
                break
        if not font_loaded:
            FONT = "Helvetica"
    except Exception:
        FONT = "Helvetica"

    margin_x = 10 * mm
    margin_y = 10 * mm
    col_gap = 3 * mm
    row_gap = 3 * mm

    label_list = []
    for item in items:
        item_id, line_no, item_name, option_text, actual_qty, barcode, m_vendor, m_product, m_option = item
        for _ in range(actual_qty):
            label_list.append({
                "barcode": barcode or "",
                "product": m_product or item_name or "",
                "option": m_option or option_text or "",
                "vendor": m_vendor or vendor,
                "wholesale": wholesale,
            })

    idx = 0
    total_labels = len(label_list)
    while idx < total_labels:
        # 페이지당 몇 행 들어가는지 계산
        rows_per_page = int((PAGE_H - 2 * margin_y) / (LABEL_H + row_gap))
        labels_per_page = COLS * rows_per_page

        for row_i in range(rows_per_page):
            for col_i in range(COLS):
                if idx >= total_labels:
                    break
                lbl = label_list[idx]
                idx += 1

                x = margin_x + col_i * (LABEL_W + col_gap)
                y = PAGE_H - margin_y - (row_i + 1) * (LABEL_H + row_gap) + row_gap

                # 라벨 테두리
                c.setStrokeColorRGB(0.8, 0.8, 0.8)
                c.setLineWidth(0.5)
                c.rect(x, y, LABEL_W, LABEL_H)

                # 바코드
                if lbl["barcode"]:
                    try:
                        bc = code128.Code128(lbl["barcode"], barHeight=12 * mm, barWidth=0.6)
                        bc_w = bc.width
                        bc_x = x + (LABEL_W - bc_w) / 2
                        bc_y = y + LABEL_H - 14 * mm
                        bc.drawOn(c, bc_x, bc_y)
                        # 바코드 텍스트
                        c.setFont(FONT, 7)
                        c.drawCentredString(x + LABEL_W / 2, y + LABEL_H - 15.5 * mm, lbl["barcode"])
                    except Exception:
                        pass

                # 상품명
                c.setFont(FONT, 8)
                product_text = lbl["product"][:20]
                c.drawCentredString(x + LABEL_W / 2, y + 7 * mm, product_text)

                # 옵션
                if lbl["option"]:
                    c.setFont(FONT, 7)
                    c.setFillColorRGB(0.4, 0.4, 0.4)
                    c.drawCentredString(x + LABEL_W / 2, y + 4.5 * mm, lbl["option"][:20])
                    c.setFillColorRGB(0, 0, 0)

                # 업체명 (좌하단)
                c.setFont(FONT, 6)
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.drawString(x + 1.5 * mm, y + 2 * mm, lbl["vendor"][:15])
                c.setFillColorRGB(0, 0, 0)

            if idx >= total_labels:
                break

        if idx < total_labels:
            c.showPage()

    c.showPage()
    c.save()
    buf.seek(0)

    # 출력 이력 저장
    now = datetime.utcnow().isoformat()
    job_id = uuid.uuid4().hex
    with get_connection() as con:
        con.execute(
            "INSERT INTO barcode_print_jobs (id, batch_id, qty, printed_by, printed_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, batch_id, total_labels, user["nickname"], now)
        )
        con.commit()

    filename = f"barcode_{vendor}_{inbound_date}.pdf"
    return SR(
        content=buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
    )


# ── 화주사 공유 링크 생성 ────────────────

class ShareLinkCreate(BaseModel):
    password: Optional[str] = None
    expires_days: int = 7
    allow_excel: bool = False


@router.post("/batches/{batch_id}/share")
def create_share_link(
    batch_id: str,
    body: ShareLinkCreate,
    authorization: Optional[str] = Header(None),
):
    """
    공유 링크 생성.
    비밀번호가 있으면 SHA-256+salt 해시로 변환해 저장.
    원문 비밀번호는 응답에 한 번만 포함 — 이후 API·로그·DB 어디에도 원문 없음.
    """
    user = _get_user(authorization)
    plain_password = (body.password or "").strip() or None  # None = 비번 없는 링크

    # 해시 변환 (원문 즉시 폐기)
    stored_password = _hash_password(plain_password) if plain_password else None

    with get_connection() as con:
        if not con.execute("SELECT 1 FROM inbound_batches WHERE id=?", (batch_id,)).fetchone():
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
        from datetime import timedelta
        token = uuid.uuid4().hex
        expires_at = (datetime.utcnow() + timedelta(days=body.expires_days)).strftime("%Y-%m-%d")
        con.execute("""
            INSERT INTO inbound_share_links (token, batch_id, password, expires_at, allow_excel, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token, batch_id, stored_password, expires_at, int(body.allow_excel), user["nickname"]))
        con.commit()

    link = f"{settings.FRONTEND_URL}/share/{token}"
    # plain_password 는 생성 응답에만 포함. 이 이후로는 서버 어디에도 원문이 없음.
    return {
        "token": token,
        "link": link,
        "expires_at": expires_at,
        "has_password": plain_password is not None,
        "password_once": plain_password,  # 프론트가 1회 표시 후 즉시 소멸해야 함
    }


@router.get("/share/{token}")
def get_share_data(
    token: str,
    password: Optional[str] = None,
):
    """공유 링크 데이터 (인증 불필요, 비밀번호 확인만)"""
    with get_connection() as con:
        row = con.execute(
            "SELECT batch_id, password, expires_at, allow_excel FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")
        batch_id, stored_pw, expires_at, allow_excel = row

        # 만료 확인
        if expires_at and datetime.utcnow().strftime("%Y-%m-%d") > expires_at:
            raise HTTPException(status_code=410, detail="링크가 만료되었습니다.")

        # 비밀번호 확인 (해시 비교 — 원문 절대 반환하지 않음)
        if stored_pw:
            if not password:
                return {"needs_password": True}
            if not _verify_password(password, stored_pw):
                raise HTTPException(status_code=403, detail="비밀번호가 틀렸습니다.")

        # 배치 + 품목 조회
        batch_row = con.execute("""
            SELECT id, vendor, inbound_date, status, wholesale, janggi_date, janggi_no,
                   total_janggi_qty, total_actual_qty, total_missing_qty, created_by, closed_at
            FROM inbound_batches WHERE id=?
        """, (batch_id,)).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 데이터를 찾을 수 없습니다.")

        items = con.execute("""
            SELECT id, line_no, item_name, option_text, janggi_qty, actual_qty, missing_qty,
                   status, matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items WHERE batch_id=? ORDER BY line_no
        """, (batch_id,)).fetchall()

        photos_map: dict = {}
        if items:
            ids_ph = [r[0] for r in items]
            ph_rows = con.execute(
                f"SELECT item_id, id, filename FROM inbound_item_photos WHERE item_id IN ({','.join('?' for _ in ids_ph)})",
                ids_ph
            ).fetchall()
            for ph in ph_rows:
                photos_map.setdefault(ph[0], []).append({"id": ph[1], "filename": ph[2]})

    STATUS_LABEL_MAP = {
        "ocr_pending": "장끼 확인 중", "confirming": "수량 확인 중",
        "inbound_done": "입고접수 완료", "grading": "양품화 중",
        "repairing": "수선 중", "done": "최종완료", "cancelled": "취소",
    }
    ITEM_LABEL_MAP = {
        "pending": "확인 전", "confirmed": "정상", "missing": "미입고",
        "defect": "불량", "repair": "수선대기", "unrecoverable": "회생불가", "done": "완료",
    }

    return {
        "batch": {
            "id": batch_row[0], "vendor": batch_row[1], "inbound_date": batch_row[2],
            "status": batch_row[3], "status_label": STATUS_LABEL_MAP.get(batch_row[3], batch_row[3]),
            "wholesale": batch_row[4], "janggi_date": batch_row[5], "janggi_no": batch_row[6],
            "total_janggi_qty": batch_row[7], "total_actual_qty": batch_row[8],
            "total_missing_qty": batch_row[9], "created_by": batch_row[10], "closed_at": batch_row[11],
        },
        "items": [{
            "id": r[0], "line_no": r[1], "item_name": r[2], "option_text": r[3],
            "janggi_qty": r[4], "actual_qty": r[5], "missing_qty": r[6],
            "status": r[7], "status_label": ITEM_LABEL_MAP.get(r[7], r[7]),
            "matched_barcode": r[8], "matched_vendor": r[9],
            "matched_product": r[10], "matched_option": r[11],
            "photos": [
                {"id": p["id"], "url": f"/inbound/share-photo/{p['filename']}"}
                for p in photos_map.get(r[0], [])
            ],
        } for r in items],
        "allow_excel": bool(allow_excel),
        "expires_at": expires_at,
    }


@router.get("/share-photo/{filename}")
def serve_share_photo(filename: str):
    """공유 링크용 사진 (인증 불필요)"""
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
    return FileResponse(path)


# ── 불량일지·수선일지 inbound_item 연결 ─────────────────

class DefectLogLink(BaseModel):
    불량명: str
    수량: int = 1
    비고: Optional[str] = None
    작성자: Optional[str] = None


class RepairLogLink(BaseModel):
    불량명: Optional[str] = None
    작업: str
    수량: int = 1
    비용: int = 0
    비고: Optional[str] = None
    작성자: Optional[str] = None


@router.post("/items/{item_id}/defect-log", status_code=201)
def link_defect_log(
    item_id: str,
    body: DefectLogLink,
    authorization: Optional[str] = Header(None),
):
    """
    입고 품목에서 불량일지 생성 + inbound_items.defect_case_id 연결.
    item의 matched_barcode / matched_vendor / matched_product 를 자동 사용.
    """
    from backend.app.api.defect_log import insert_defect_log_record, ensure_defect_tables
    ensure_defect_tables()
    user = _get_user(authorization)

    with get_connection() as con:
        item = con.execute("""
            SELECT id, batch_id, item_name, option_text,
                   matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items WHERE id=?
        """, (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
        batch = con.execute(
            "SELECT inbound_date, vendor FROM inbound_batches WHERE id=?", (item[1],)
        ).fetchone()

    inbound_date = batch[0] if batch else datetime.utcnow().strftime("%Y-%m-%d")
    vendor = item[5] or (batch[1] if batch else None)
    product = item[6] or item[2]
    option = item[7] or item[3]
    barcode = item[4]

    result = insert_defect_log_record(
        날짜=inbound_date,
        업체명=vendor,
        제품명=product,
        옵션=option,
        바코드=barcode,
        불량명=body.불량명,
        수량=body.수량,
        비고=body.비고,
        작성자=body.작성자 or user["nickname"],
        출처="inbound",
        inbound_item_id=item_id,
    )

    defect_log_id = result["id"]

    # inbound_items에 defect_case_id 기록
    with get_connection() as con:
        con.execute(
            "UPDATE inbound_items SET defect_case_id=? WHERE id=?",
            (str(defect_log_id), item_id)
        )
        con.commit()

    return {**result, "defect_log_id": defect_log_id, "inbound_item_id": item_id}


@router.post("/items/{item_id}/repair-log", status_code=201)
def link_repair_log(
    item_id: str,
    body: RepairLogLink,
    authorization: Optional[str] = Header(None),
):
    """
    입고 품목에서 수선일지 생성 + inbound_items.defect_case_id 연결.
    """
    from backend.app.api.repair_log import insert_repair_log_record, ensure_repair_tables
    ensure_repair_tables()
    user = _get_user(authorization)

    with get_connection() as con:
        item = con.execute("""
            SELECT id, batch_id, item_name, option_text,
                   matched_barcode, matched_vendor, matched_product, matched_option
            FROM inbound_items WHERE id=?
        """, (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
        batch = con.execute(
            "SELECT inbound_date, vendor FROM inbound_batches WHERE id=?", (item[1],)
        ).fetchone()

    inbound_date = batch[0] if batch else datetime.utcnow().strftime("%Y-%m-%d")
    vendor = item[5] or (batch[1] if batch else None)
    product = item[6] or item[2]
    option = item[7] or item[3]
    barcode = item[4]

    result = insert_repair_log_record(
        날짜=inbound_date,
        업체명=vendor,
        제품명=product,
        옵션=option,
        바코드=barcode,
        불량명=body.불량명,
        작업=body.작업,
        수량=body.수량,
        비용=body.비용,
        비고=body.비고,
        작성자=body.작성자 or user["nickname"],
        출처="inbound",
        inbound_item_id=item_id,
    )

    repair_log_id = result["id"]

    # inbound_items에 defect_case_id 기록 (수선일지 ID)
    with get_connection() as con:
        con.execute(
            "UPDATE inbound_items SET defect_case_id=? WHERE id=?",
            (f"repair:{repair_log_id}", item_id)
        )
        con.commit()

    return {**result, "repair_log_id": repair_log_id, "inbound_item_id": item_id}

# ── OCR 미리보기 (DB 저장 없이 GPT 결과만 반환) ─────────────────

@router.post("/ocr-preview")
async def ocr_preview(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지를 GPT-4o로 분석해 품목 목록을 반환. DB에 저장하지 않음."""
    _get_user(authorization)

    suffix = Path(file.filename or "img.jpg").suffix or ".jpg"
    tmp_path = UPLOAD_DIR / ("preview_" + uuid.uuid4().hex + suffix)
    try:
        tmp_path.write_bytes(await file.read())
        result = await _run_ocr(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="GPT OCR를 실행할 수 없습니다. OPENAI_API_KEY를 확인하세요.",
        )

    return {
        "ok": True,
        "receipt": result.get("receipt", {}),
        "items": result.get("items", []),
        "raw": result,
    }
