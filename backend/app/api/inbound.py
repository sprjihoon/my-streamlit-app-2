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
import json
import os
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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}

# ─────────────────────────────────────
# 상태 정의
# ─────────────────────────────────────

STATUS_VALUES = ("ocr_pending", "confirming", "inbound_done", "grading", "repairing", "done", "cancelled")
STATUS_LABELS = {
    "ocr_pending": "장끼 확인 중",
    "confirming": "수량 확인 중",
    "inbound_done": "입고접수 완료",
    "grading": "양품화 중",
    "repairing": "수선 중",
    "done": "최종완료",
    "cancelled": "취소",
}

ITEM_STATUS_VALUES = ("pending", "confirmed", "missing", "defect", "repair", "unrecoverable", "done")
ITEM_STATUS_LABELS = {
    "pending": "확인 전",
    "confirmed": "정상",
    "missing": "미입고",
    "defect": "불량",
    "repair": "수선대기",
    "unrecoverable": "회생불가",
    "done": "완료",
}


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class InboundBatchCreate(BaseModel):
    vendor: str                  # 화주사
    inbound_date: str            # YYYY-MM-DD
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
                memo TEXT,
                defect_case_id TEXT,
                inbound_item_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
            "SELECT user_id, nickname, is_admin FROM users WHERE session_token = ?",
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
        "created_at": row[17],
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

    with get_connection() as con:
        # 1순위: 화주사 + 도매처 + 공급처상품명/상품명 + 옵션 정확 매칭
        if wholesale and option_text:
            row = con.execute("""
                SELECT 바코드, 업체명, 공급처상품명, 옵션
                FROM repair_barcode
                WHERE 업체명=? AND 도매처=?
                  AND (공급처상품명=? OR 상품명=?)
                  AND 옵션=?
                LIMIT 1
            """, (vendor, wholesale, item_name, item_name, option_text)).fetchone()
            if row:
                return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                        "matched_product": row[2] or item_name, "matched_option": row[3],
                        "match_confidence": 1.0, "needs_matching": False}

        # 2순위: 화주사 + 도매처 + 상품명 (옵션 무시)
        if wholesale:
            row = con.execute("""
                SELECT 바코드, 업체명, 공급처상품명, 옵션
                FROM repair_barcode
                WHERE 업체명=? AND 도매처=?
                  AND (공급처상품명=? OR 상품명=?)
                LIMIT 1
            """, (vendor, wholesale, item_name, item_name)).fetchone()
            if row:
                return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                        "matched_product": row[2] or item_name, "matched_option": row[3],
                        "match_confidence": 0.85, "needs_matching": False}

        # 3순위: 화주사 + 상품명
        row = con.execute("""
            SELECT 바코드, 업체명, 공급처상품명, 옵션
            FROM repair_barcode
            WHERE 업체명=? AND (공급처상품명=? OR 상품명=?)
            LIMIT 1
        """, (vendor, item_name, item_name)).fetchone()
        if row:
            return {**result, "matched_barcode": row[0], "matched_vendor": row[1],
                    "matched_product": row[2] or item_name, "matched_option": row[3],
                    "match_confidence": 0.7, "needs_matching": False}

        # 4순위: 부분 일치 (LIKE)
        keyword = f"%{item_name}%"
        row = con.execute("""
            SELECT 바코드, 업체명, 공급처상품명, 옵션
            FROM repair_barcode
            WHERE 업체명=? AND (공급처상품명 LIKE ? OR 상품명 LIKE ?)
            LIMIT 1
        """, (vendor, keyword, keyword)).fetchone()
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
                     "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}}
                ]}
            ],
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60) as client:
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
                (id, vendor, inbound_date, status, memo, created_by, created_at, updated_at)
            VALUES (?, ?, ?, 'ocr_pending', ?, ?, ?, ?)
        """, (batch_id, body.vendor, body.inbound_date, body.memo,
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
                   match_confidence, needs_matching, memo, created_at
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
            "SELECT id, vendor, status FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
    if not batch_row:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

    vendor = batch_row[1]

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

    if not fields:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")

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


# ── 마감 ───────────────────────────────

@router.post("/batches/{batch_id}/close")
def close_batch(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    마감 요청:
    - inbound_done → grading (수선 대상 없으면 바로 done)
    - grading/repairing → done
    수량 미확인 품목이 있으면 경고 반환 (강제 마감 불가)
    """
    user = _get_user(authorization)
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT status, total_janggi_qty, total_actual_qty, total_missing_qty FROM inbound_batches WHERE id=?",
            (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        current_status = batch_row[0]
        janggi_qty = batch_row[1]
        actual_qty = batch_row[2]
        missing_qty = batch_row[3]

        # 수량 검증
        if current_status == "confirming":
            pending_count = con.execute(
                "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'",
                (batch_id,)
            ).fetchone()[0]
            if pending_count > 0:
                return {
                    "ok": False,
                    "warning": f"아직 확인 전 품목이 {pending_count}개 있습니다. 모든 품목 확인 후 마감해주세요.",
                    "pending_count": pending_count,
                }
            # confirming → inbound_done
            next_status = "inbound_done"
            msg = "입고접수 완료"
        elif current_status == "inbound_done":
            next_status = "grading"
            msg = "양품화 중"
        elif current_status in ("grading", "repairing"):
            # 수선 대기 품목 확인
            repair_count = con.execute(
                "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status IN ('repair', 'defect')",
                (batch_id,)
            ).fetchone()[0]
            if repair_count > 0:
                return {
                    "ok": False,
                    "warning": f"수선/불량 처리 중인 품목이 {repair_count}개 있습니다.",
                    "repair_count": repair_count,
                }
            next_status = "done"
            msg = "최종완료"
        elif current_status == "done":
            return {"ok": False, "warning": "이미 완료된 입고건입니다."}
        else:
            raise HTTPException(status_code=400, detail=f"현재 상태({current_status})에서는 마감할 수 없습니다.")

        now = datetime.utcnow().isoformat()
        con.execute("""
            UPDATE inbound_batches
            SET status=?, closed_by=?, closed_at=?, updated_at=?
            WHERE id=?
        """, (next_status, user["nickname"], now if next_status == "done" else None, now, batch_id))
        con.commit()

    add_log("inbound", "close", f"입고 마감: {batch_id} → {next_status}", user["user_id"])
    return {
        "ok": True,
        "status": next_status,
        "status_label": STATUS_LABELS[next_status],
        "message": msg,
        "total_janggi_qty": janggi_qty,
        "total_actual_qty": actual_qty,
        "total_missing_qty": missing_qty,
    }


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
    """입고 실적이 있는 화주사 + repair_barcode 등록 업체명 합집합"""
    _get_user(authorization)
    with get_connection() as con:
        vendors_from_batches = {r[0] for r in con.execute(
            "SELECT DISTINCT vendor FROM inbound_batches ORDER BY vendor"
        ).fetchall() if r[0]}
        vendors_from_barcodes = {r[0] for r in con.execute(
            "SELECT DISTINCT 업체명 FROM repair_barcode ORDER BY 업체명"
        ).fetchall() if r[0]}
    all_vendors = sorted(vendors_from_batches | vendors_from_barcodes)
    return {"vendors": all_vendors}


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
