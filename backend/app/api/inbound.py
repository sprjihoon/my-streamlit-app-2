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
import io
import json
import logging
import os
import secrets
import time
import uuid
import datetime as _dt
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, Form, Header
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.config import settings
from logic.db import get_connection

logger = logging.getLogger(__name__)

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
    item_name: Optional[str] = None        # 상품명 직접 수정
    option_text: Optional[str] = None      # 옵션 직접 수정
    item_wholesale: Optional[str] = None   # 도매처 직접 수정 (배치 wholesale 오버라이드)
    matched_barcode: Optional[str] = None
    matched_vendor: Optional[str] = None
    matched_product: Optional[str] = None
    matched_option: Optional[str] = None
    supplier_location: Optional[str] = None
    supplier_contact: Optional[str] = None
    confirmed_by: Optional[str] = None  # 로그인 없이 접근하는 작업자 이름


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
            "confirmed_by TEXT",    # 로그인 없이 접근하는 작업자 이름
            "item_wholesale TEXT",  # 도매처 항목별 오버라이드
            "normal_qty INTEGER DEFAULT 0",  # 정상처리 수량 (직원 직접 입력)
        ]:
            try:
                con.execute(f"ALTER TABLE inbound_items ADD COLUMN {col_def}")
            except Exception:
                pass
        # inbound_share_links 에 폐기 컬럼 추가
        try:
            con.execute("ALTER TABLE inbound_share_links ADD COLUMN revoked_at DATETIME")
        except Exception:
            pass
        # repair_barcode 에 도매처주소·도매처연락처 컬럼 추가 (없으면)
        for _col in ("도매처주소 TEXT", "도매처연락처 TEXT"):
            try:
                con.execute(f"ALTER TABLE repair_barcode ADD COLUMN {_col}")
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


_KST = _dt.timezone(_dt.timedelta(hours=9))


def _update_barcode_master(
    con,
    barcode: str,
    wholesale: str = "",
    supplier_location: str = "",
    supplier_contact: str = "",
    matched_product: str = "",   # 도매처상품명 → repair_barcode.제품명
    matched_option: str = "",    # 도매처옵션   → repair_barcode.옵션
) -> None:
    """매칭 확정 시 repair_barcode 마스터의 도매처·위치·연락처·상품명·옵션을 갱신한다.

    - 해당 바코드 레코드가 없으면 아무 작업도 하지 않는다.
    - 빈 문자열은 기존 값을 덮어쓰지 않는다.
    """
    # 신규 컬럼 마이그레이션
    for col in ("도매처주소 TEXT", "도매처연락처 TEXT"):
        try:
            con.execute(f"ALTER TABLE repair_barcode ADD COLUMN {col}")
        except Exception:
            pass

    # 업데이트할 필드 수집 (값이 있는 것만)
    col_map = [
        (wholesale,          "도매처"),
        (supplier_location,  "도매처주소"),
        (supplier_contact,   "도매처연락처"),
        (matched_product,    "제품명"),
        (matched_option,     "옵션"),
    ]
    sets, vals = [], []
    for val, col in col_map:
        if val:
            sets.append(f"{col}=?"); vals.append(val)

    if not sets:
        return

    vals.append(barcode)
    try:
        con.execute(f"UPDATE repair_barcode SET {', '.join(sets)} WHERE 바코드=?", vals)
        updated = {col_map[i][1]: vals[i] for i in range(len(sets))}
        logger.info(f"바코드 마스터 업데이트: {barcode} → {updated}")
    except Exception as e:
        logger.warning(f"바코드 마스터 업데이트 실패 ({barcode}): {e}")


def _check_link_expiry(inbound_date_str: str) -> None:
    """비로그인 공개 링크 만료 확인 — 당일(KST) 자정 이후이면 410 반환."""
    try:
        batch_date = _dt.date.fromisoformat(inbound_date_str)
        today_kst  = _dt.datetime.now(_KST).date()
        if today_kst > batch_date:
            raise HTTPException(
                status_code=410,
                detail=f"링크가 만료되었습니다. (유효일: {inbound_date_str})"
            )
    except HTTPException:
        raise
    except Exception:
        pass  # 날짜 파싱 실패 시 허용


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
        "confirmed_by": row[21] if len(row) > 21 else None,
        "item_wholesale": row[22] if len(row) > 22 else None,
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
        "supplier_location": None,   # 도매처주소
        "supplier_contact": None,    # 도매처연락처
        "match_confidence": 0.0,
        "needs_matching": True,
    }
    if not item_name:
        return result

    vendor_names = _resolve_vendor_names(vendor)  # 별칭 포함 후보 업체명 목록
    vendor_ph = ",".join("?" * len(vendor_names))  # IN (?,?,...) 플레이스홀더

    def _row_to_result(row, confidence: float, needs: bool) -> dict:
        return {
            **result,
            "matched_barcode": row[0],
            "matched_vendor": row[1],
            "matched_product": row[2] or item_name,
            "matched_option": row[3],
            "supplier_location": row[4] if len(row) > 4 else None,
            "supplier_contact": row[5] if len(row) > 5 else None,
            "match_confidence": confidence,
            "needs_matching": needs,
        }

    _sel = "SELECT 바코드, 업체명, 제품명, 옵션, 도매처주소, 도매처연락처"

    with get_connection() as con:
        # 1순위: 화주사(별칭 포함) + 도매처 + 제품명/상품명 + 옵션 정확 매칭
        if wholesale and option_text:
            row = con.execute(f"""
                {_sel}
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (제품명=? OR 상품명=?)
                  AND 옵션=?
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name, option_text)).fetchone()
            if row:
                return _row_to_result(row, 1.0, False)

        # 2순위: 화주사(별칭 포함) + 도매처 + 제품명/상품명 (옵션 무시)
        if wholesale:
            row = con.execute(f"""
                {_sel}
                FROM repair_barcode
                WHERE 업체명 IN ({vendor_ph}) AND 도매처=?
                  AND (제품명=? OR 상품명=?)
                LIMIT 1
            """, (*vendor_names, wholesale, item_name, item_name)).fetchone()
            if row:
                return _row_to_result(row, 0.85, False)

        # 3순위: 화주사(별칭 포함) + 제품명/상품명
        row = con.execute(f"""
            {_sel}
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (제품명=? OR 상품명=?)
            LIMIT 1
        """, (*vendor_names, item_name, item_name)).fetchone()
        if row:
            return _row_to_result(row, 0.7, False)

        # 4순위: 부분 일치 (LIKE) — 화주사 별칭 포함
        keyword = f"%{item_name}%"
        row = con.execute(f"""
            {_sel}
            FROM repair_barcode
            WHERE 업체명 IN ({vendor_ph}) AND (제품명 LIKE ? OR 상품명 LIKE ?)
            LIMIT 1
        """, (*vendor_names, keyword, keyword)).fetchone()
        if row:
            return _row_to_result(row, 0.5, True)

    return result


# ─────────────────────────────────────
# OCR (장끼 이미지 분석)
# ─────────────────────────────────────

OCR_MODEL: str = os.getenv("BOT_OCR_MODEL", "gpt-4o")

JANGGI_SCHEMA: dict = {
    "type": "object",
    "required": ["receipt", "items"],
    "additionalProperties": False,
    "properties": {
        "receipt": {
            "type": "object",
            "required": [
                "storeName", "receiptNo", "orderDate", "totalAmount",
                "isHandwritten", "confidence", "needsReview", "warnings",
            ],
            "additionalProperties": False,
            "properties": {
                "storeName":     {"type": ["string", "null"]},
                "receiptNo":     {"type": ["string", "null"]},
                "orderDate":     {"type": ["string", "null"]},
                "totalAmount":   {"type": ["number", "null"]},
                "isHandwritten": {"type": "boolean"},
                "confidence":    {"type": "number"},
                "needsReview":   {"type": "boolean"},
                "warnings":      {"type": "array", "items": {"type": "string"}},
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "lineNo", "rawText", "itemName", "color", "size", "optionText",
                    "unitPrice", "quantity", "amount", "confidence", "needsReview", "warnings",
                ],
                "additionalProperties": False,
                "properties": {
                    "lineNo":     {"type": "integer"},
                    "rawText":    {"type": ["string", "null"]},
                    "itemName":   {"type": ["string", "null"]},
                    "color":      {"type": ["string", "null"]},
                    "size":       {"type": ["string", "null"]},
                    "optionText": {"type": ["string", "null"]},
                    "unitPrice":  {"type": ["number", "null"]},
                    "quantity":   {"type": ["number", "null"]},
                    "amount":     {"type": ["number", "null"]},
                    "confidence": {"type": "number"},
                    "needsReview":{"type": "boolean"},
                    "warnings":   {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

SYSTEM_PROMPT: str = (
    "너는 동대문 장끼(도매 영수증)를 판독하는 전문가다.\n"
    "규칙:\n"
    "1. 상호·도매처는 장끼를 발행한 판매처다. 상단에 별도로 손글씨로 쓰인 화주사명·구매자명은 도매처로 오인하지 않는다.\n"
    "2. 출력일시와 거래일이 함께 있으면 품목 가까이에 표시된 거래일을 orderDate로 사용한다.\n"
    "3. 품명·색상·사이즈·옵션을 가능한 범위에서 분리한다.\n"
    "4. 읽을 수 없는 글자를 추측해 확정하지 않는다. 불명확한 값은 rawText에 원문을 남기고 needsReview=true와 경고를 반환한다.\n"
    "5. unitPrice × quantity = amount 검산. 불일치 시 needsReview=true와 경고.\n"
    '6. 동대문 수기 장끼에서 "9", "18"처럼 천원 단위가 생략된 경우 수량·금액·총액 문맥이 일치하면 9000, 18000으로 정규화하되 '
    'needsReview=true와 "천원 단위 추정" 경고를 남긴다.\n'
    "7. 품목이 보이는데도 빈 배열을 반환하지 않는다. 한 개도 판독하지 못하면 정상 성공으로 처리하지 않는다.\n"
    "반드시 위 JSON Schema를 정확히 따른다."
)


class OcrError(Exception):
    """OCR 파이프라인 분류 오류.

    kind: "no_api_key" | "auth" | "model" | "quota" | "image"
          | "timeout" | "server" | "schema" | "no_items"
    """

    def __init__(self, kind: str, user_msg: str, log_detail: str = ""):
        self.kind = kind
        self.user_msg = user_msg
        self.log_detail = log_detail
        super().__init__(user_msg)


def _normalize_image(raw: bytes) -> tuple:
    """Pillow로 이미지를 디코딩·EXIF 회전·RGB JPEG 변환·2048px 리사이즈.

    반환: (정규화된 JPEG bytes, "image/jpeg")
    실패 시 ValueError 발생 (400으로 매핑됨).
    base64 내용·원본 bytes는 절대 로그에 남기지 않는다.
    """
    _ERR = "이미지를 읽지 못했어요. 사진 방향과 선명도를 확인해 다시 촬영해주세요."
    if not raw:
        raise ValueError(_ERR)
    try:
        buf = io.BytesIO(raw)
        img = Image.open(buf)
        img.verify()          # 포맷 유효성 검사
        buf.seek(0)
        img = Image.open(buf)  # verify() 후 재열기
    except Exception:
        raise ValueError(_ERR)
    try:
        img = ImageOps.exif_transpose(img)  # EXIF 회전 적용
        img = img.convert("RGB")
        w, h = img.size
        max_px = 2048
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf_out = io.BytesIO()
        img.save(buf_out, format="JPEG", quality=90)
        return buf_out.getvalue(), "image/jpeg"
    except Exception:
        raise ValueError(_ERR)


async def _run_ocr(image_bytes: bytes, mime: str) -> dict:
    """GPT Vision Structured Outputs로 장끼 분석.

    성공 시 OCR 결과 dict 반환.
    실패 시 OcrError 발생.
    API 키·Authorization·base64·장끼 전문·개인정보는 절대 로그에 남기지 않는다.
    """
    import httpx  # 지연 import (테스트 패치 용이)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OcrError("no_api_key", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

    b64 = base64.b64encode(image_bytes).decode()
    img_size = len(image_bytes)

    request_payload = {
        "model": OCR_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                }
            ]},
        ],
        "max_tokens": 2000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "janggi_ocr",
                "strict": True,
                "schema": JANGGI_SCHEMA,
            },
        },
    }
    # Authorization 헤더는 로그에 남기지 않음
    req_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_attempts = 2
    t_start = time.monotonic()

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=req_headers,
                    json=request_payload,
                )
        except httpx.TimeoutException:
            elapsed = time.monotonic() - t_start
            if attempt < max_attempts - 1:
                continue  # 1회 재시도
            logger.info(
                "OCR err kind=timeout status=None req_id=None model=%s elapsed=%.1fs img_size=%d",
                OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("timeout", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        elapsed = time.monotonic() - t_start
        status_code = resp.status_code
        req_id = resp.headers.get("x-request-id", "None")

        if status_code in (401, 403):
            logger.info(
                "OCR err kind=auth status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("auth", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

        if status_code == 404:
            logger.info(
                "OCR err kind=model status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("model", "AI 설정을 확인해야 합니다. 관리자에게 알려주세요.")

        if status_code == 429:
            logger.info(
                "OCR err kind=quota status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("quota", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        if status_code >= 500:
            if attempt < max_attempts - 1:
                continue  # 1회 재시도
            logger.info(
                "OCR err kind=server status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("server", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")

        # Structured Output 파싱
        try:
            resp_json = resp.json()
            content = resp_json["choices"][0]["message"]["content"]
            result = json.loads(content)
            if "receipt" not in result or "items" not in result:
                raise ValueError("required keys missing")
        except Exception:
            logger.info(
                "OCR err kind=schema status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("schema", "이미지를 읽지 못했어요. 사진 방향과 선명도를 확인해 다시 촬영해주세요.")

        items = result.get("items", [])
        if len(items) == 0:
            logger.info(
                "OCR err kind=no_items status=%d req_id=%s model=%s elapsed=%.1fs img_size=%d",
                status_code, req_id, OCR_MODEL, elapsed, img_size,
            )
            raise OcrError("no_items", "품목을 찾지 못했어요. 다시 촬영하거나 직접 입력해주세요.")

        # 정상 성공 로그 (img_size만, base64·원문 제외)
        try:
            norm_img = Image.open(io.BytesIO(image_bytes))
            nw, nh = norm_img.size
            norm_str = f"{nw}x{nh}"
        except Exception:
            norm_str = "?"
        logger.info(
            "OCR ok  model=%s elapsed=%.1fs items=%d norm=%s",
            OCR_MODEL, elapsed, len(items), norm_str,
        )
        return result

    # 도달 불가 (안전망)
    raise OcrError("server", "AI 판독 요청이 지연되고 있어요. 잠시 후 다시 시도해주세요.")


# ─────────────────────────────────────
# 라우터
# ─────────────────────────────────────

# ── 통합현황: 화주사+날짜 단위 목록 및 상세 ──────

@router.get("/vendor-overview")
def list_vendor_overviews(
    vendor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),   # "closed" | "open"
    authorization: Optional[str] = Header(None),
):
    """
    화주사+입고일 단위로 묶어 반환한다.
    vendor_canonical 이 있으면 canonical 기준으로 묶고, 없으면 vendor 사용.
    status="closed" → 해당 날짜 모든 배치가 마감인 그룹만 반환
    status="open"   → 하나라도 진행중인 그룹만 반환
    """
    _get_user(authorization)
    where = ["1=1"]
    params: list = []
    if vendor:
        # canonical 또는 raw vendor 어느 쪽이든 일치
        where.append("COALESCE(vendor_canonical, vendor)=?"); params.append(vendor)
    if date_from:
        where.append("inbound_date>=?"); params.append(date_from)
    if date_to:
        where.append("inbound_date<=?"); params.append(date_to)

    sql = f"""
        SELECT COALESCE(vendor_canonical, vendor) AS canonical_vendor,
               inbound_date,
               COUNT(*) AS batches_count,
               GROUP_CONCAT(COALESCE(wholesale,''), '|') AS wholesales,
               SUM(total_janggi_qty) AS total_janggi,
               SUM(total_actual_qty) AS total_actual,
               SUM(total_missing_qty) AS total_missing,
               GROUP_CONCAT(status, '|') AS statuses
        FROM inbound_batches
        WHERE {' AND '.join(where)}
        GROUP BY canonical_vendor, inbound_date
        ORDER BY inbound_date DESC, canonical_vendor
    """
    with get_connection() as con:
        rows = con.execute(sql, params).fetchall()

        # 각 (vendor, date) 별 수선건수 집계: inbound_item_id 연결 + 바코드 fallback
        repair_count_map: dict = {}
        for r in rows:
            cvendor, idate = r[0], r[1]
            # ① inbound_item_id 기준
            cnt_a = con.execute(
                """SELECT COUNT(*) FROM repair_work_log rw
                   JOIN inbound_items ii ON rw.inbound_item_id = ii.id
                   JOIN inbound_batches ib ON ii.batch_id = ib.id
                   WHERE COALESCE(ib.vendor_canonical, ib.vendor)=? AND ib.inbound_date=?""",
                (cvendor, idate),
            ).fetchone()[0] or 0
            # ② 바코드+날짜 fallback (inbound_item_id 없는 봇 기록)
            cnt_b = con.execute(
                """SELECT COUNT(*) FROM repair_work_log rw
                   JOIN inbound_items ii ON rw.바코드 = ii.matched_barcode
                   JOIN inbound_batches ib ON ii.batch_id = ib.id
                   WHERE COALESCE(ib.vendor_canonical, ib.vendor)=? AND ib.inbound_date=?
                     AND (rw.inbound_item_id IS NULL OR rw.inbound_item_id='')
                     AND rw.날짜=?""",
                (cvendor, idate, idate),
            ).fetchone()[0] or 0
            repair_count_map[(cvendor, idate)] = cnt_a + cnt_b

    items = []
    for r in rows:
        wholesales = list(dict.fromkeys(w for w in (r[3] or "").split("|") if w))  # 중복 제거
        statuses = (r[7] or "").split("|")
        all_closed = all(s == "closed" for s in statuses if s)
        # status 필터 적용
        if status == "closed" and not all_closed:
            continue
        if status == "open" and all_closed:
            continue
        items.append({
            "vendor": r[0],          # canonical 기준 표시명
            "inbound_date": r[1],
            "batches_count": r[2],
            "wholesales": wholesales,
            "total_janggi_qty": r[4] or 0,
            "total_actual_qty": r[5] or 0,
            "total_missing_qty": r[6] or 0,
            "all_closed": all_closed,
            "statuses": statuses,
            "repair_count": repair_count_map.get((r[0], r[1]), 0),
        })
    return {"items": items, "total": len(items)}


@router.get("/vendor-overview/{vendor}/{inbound_date}")
def get_vendor_overview_detail(
    vendor: str,
    inbound_date: str,
    authorization: Optional[str] = Header(None),
):
    """
    특정 화주사+입고일의 전체 배치·품목·사진·불량/수선 로그를 반환한다.
    """
    _get_user(authorization)
    with get_connection() as con:
        batch_rows = con.execute(
            """SELECT id, vendor, inbound_date, status, memo, wholesale,
                      total_janggi_qty, total_actual_qty, total_missing_qty,
                      created_by, closed_by, closed_at, created_at, janggi_filename
               FROM inbound_batches
               WHERE COALESCE(vendor_canonical, vendor)=? AND inbound_date=?
               ORDER BY wholesale""",
            (vendor, inbound_date),
        ).fetchall()

        if not batch_rows:
            raise HTTPException(status_code=404, detail="해당 화주사/날짜 데이터 없음")

        batch_ids = [r[0] for r in batch_rows]
        ph = ",".join("?" * len(batch_ids))

        # 전체 품목 조회
        item_rows = con.execute(
            f"""SELECT id, batch_id, line_no, item_name, option_text, unit_price,
                       janggi_qty, actual_qty, missing_qty, status,
                       matched_barcode, matched_vendor, matched_product, matched_option,
                       supplier_location, supplier_contact, needs_matching, normal_qty,
                       confirmed_by, item_wholesale, memo
                FROM inbound_items
                WHERE batch_id IN ({ph})
                ORDER BY batch_id, line_no""",
            batch_ids,
        ).fetchall()

        item_ids = [r[0] for r in item_rows]
        idph = ",".join("?" * len(item_ids)) if item_ids else "NULL"

        # 품목별 사진
        photo_map: dict = {}
        if item_ids:
            for row in con.execute(
                f"SELECT item_id, id, filename FROM inbound_item_photos WHERE item_id IN ({idph}) ORDER BY created_at",
                item_ids,
            ).fetchall():
                photo_map.setdefault(row[0], []).append({"id": row[1], "url": _image_url(row[2])})

        # 바코드 → item_id 매핑 (fallback용, matched_barcode 기준)
        barcode_to_item_id: dict = {}
        for r in item_rows:
            bc = r[10]  # matched_barcode
            if bc and bc not in barcode_to_item_id:
                barcode_to_item_id[bc] = r[0]

        # 불량 로그 전체 ① inbound_item_id 직접 연결
        defect_map: dict = {}
        defect_seen: set = set()
        if item_ids:
            for row in con.execute(
                f"""SELECT inbound_item_id, id, 날짜, 불량명, 수량, 비고, 처리결과,
                           before_image, after_image, 작성자
                    FROM defect_log WHERE inbound_item_id IN ({idph})
                    ORDER BY inbound_item_id, id""",
                item_ids,
            ).fetchall():
                defect_map.setdefault(row[0], []).append({
                    "id": row[1], "날짜": row[2], "불량명": row[3],
                    "수량": row[4], "비고": row[5], "처리결과": row[6],
                    "before_image": _image_url_defect(row[7]),
                    "after_image": _image_url_defect(row[8]),
                    "작성자": row[9],
                })
                defect_seen.add(row[1])

        # 불량 로그 ② 바코드+날짜 fallback (봇 기록 등 inbound_item_id 없는 경우)
        if barcode_to_item_id:
            bcph = ",".join("?" * len(barcode_to_item_id))
            for row in con.execute(
                f"""SELECT 바코드, id, 날짜, 불량명, 수량, 비고, 처리결과,
                           before_image, after_image, 작성자
                    FROM defect_log
                    WHERE 바코드 IN ({bcph}) AND 날짜=?
                      AND (inbound_item_id IS NULL OR inbound_item_id='')
                    ORDER BY 바코드, id""",
                list(barcode_to_item_id.keys()) + [inbound_date],
            ).fetchall():
                if row[1] in defect_seen:
                    continue
                item_id = barcode_to_item_id.get(row[0])
                if item_id:
                    defect_map.setdefault(item_id, []).append({
                        "id": row[1], "날짜": row[2], "불량명": row[3],
                        "수량": row[4], "비고": row[5], "처리결과": row[6],
                        "before_image": _image_url_defect(row[7]),
                        "after_image": _image_url_defect(row[8]),
                        "작성자": row[9],
                    })
                    defect_seen.add(row[1])

        # 수선 로그 전체 ① inbound_item_id 직접 연결
        repair_map: dict = {}
        repair_seen: set = set()
        if item_ids:
            for row in con.execute(
                f"""SELECT inbound_item_id, id, 날짜, 작업, 불량명, 수량, 비용, 비고,
                           before_image, after_image, 작성자
                    FROM repair_work_log WHERE inbound_item_id IN ({idph})
                    ORDER BY inbound_item_id, id""",
                item_ids,
            ).fetchall():
                repair_map.setdefault(row[0], []).append({
                    "id": row[1], "날짜": row[2], "작업": row[3], "불량명": row[4],
                    "수량": row[5], "비용": row[6], "비고": row[7],
                    "before_image": _image_url_repair(row[8]),
                    "after_image": _image_url_repair(row[9]),
                    "작성자": row[10],
                })
                repair_seen.add(row[1])

        # 수선 로그 ② 바코드+날짜 fallback (봇 기록 등 inbound_item_id 없는 경우)
        if barcode_to_item_id:
            bcph = ",".join("?" * len(barcode_to_item_id))
            for row in con.execute(
                f"""SELECT 바코드, id, 날짜, 작업, 불량명, 수량, 비용, 비고,
                           before_image, after_image, 작성자
                    FROM repair_work_log
                    WHERE 바코드 IN ({bcph}) AND 날짜=?
                      AND (inbound_item_id IS NULL OR inbound_item_id='')
                    ORDER BY 바코드, id""",
                list(barcode_to_item_id.keys()) + [inbound_date],
            ).fetchall():
                if row[1] in repair_seen:
                    continue
                item_id = barcode_to_item_id.get(row[0])
                if item_id:
                    repair_map.setdefault(item_id, []).append({
                        "id": row[1], "날짜": row[2], "작업": row[3], "불량명": row[4],
                        "수량": row[5], "비용": row[6], "비고": row[7],
                        "before_image": _image_url_repair(row[8]),
                        "after_image": _image_url_repair(row[9]),
                        "작성자": row[10],
                    })
                    repair_seen.add(row[1])

    # 도매처별 그룹핑
    batch_map = {}
    for r in batch_rows:
        batch_map[r[0]] = {
            "id": r[0], "vendor": r[1], "inbound_date": r[2], "status": r[3],
            "memo": r[4], "wholesale": r[5] or "-",
            "total_janggi_qty": r[6] or 0, "total_actual_qty": r[7] or 0,
            "total_missing_qty": r[8] or 0,
            "created_by": r[9], "closed_by": r[10], "closed_at": r[11],
            "created_at": r[12],
            "janggi_url": _image_url(r[13]) if r[13] else None,  # 장끼 사진
            "items": [],
        }

    for r in item_rows:
        iid = r[0]
        item = {
            "id": iid, "batch_id": r[1], "line_no": r[2],
            "item_name": r[3], "option_text": r[4], "unit_price": r[5],
            "janggi_qty": r[6] or 0, "actual_qty": r[7] or 0, "missing_qty": r[8] or 0,
            "status": r[9], "matched_barcode": r[10],
            "matched_vendor": r[11], "matched_product": r[12], "matched_option": r[13],
            "supplier_location": r[14], "supplier_contact": r[15],
            "needs_matching": bool(r[16]), "normal_qty": r[17] or 0,
            "confirmed_by": r[18], "item_wholesale": r[19], "memo": r[20],
            "photos": photo_map.get(iid, []),
            "defect_logs": defect_map.get(iid, []),
            "repair_logs": repair_map.get(iid, []),
        }
        if r[1] in batch_map:
            batch_map[r[1]]["items"].append(item)

    batches = list(batch_map.values())

    total_janggi = sum(b["total_janggi_qty"] for b in batches)
    total_actual = sum(b["total_actual_qty"] for b in batches)
    total_missing = sum(b["total_missing_qty"] for b in batches)
    all_items = [i for b in batches for i in b["items"]]
    needs_matching_count = sum(1 for i in all_items if i["needs_matching"])
    defect_total = sum(len(i["defect_logs"]) for i in all_items)
    repair_total = sum(len(i["repair_logs"]) for i in all_items)

    return {
        "vendor": vendor,
        "inbound_date": inbound_date,
        "summary": {
            "batches_count": len(batches),
            "total_janggi_qty": total_janggi,
            "total_actual_qty": total_actual,
            "total_missing_qty": total_missing,
            "items_count": len(all_items),
            "needs_matching_count": needs_matching_count,
            "defect_total": defect_total,
            "repair_total": repair_total,
        },
        "batches": batches,
    }


# ── 입고 필터 옵션 (화주사·도매처 목록) ──────

@router.get("/filter-options")
def get_filter_options(authorization: Optional[str] = Header(None)):
    """
    입고일지 필터용 드롭다운 옵션 반환.
    - vendors      : inbound_batches 에 실제 등록된 고유 화주사명
    - wholesales   : inbound_batches.wholesale 의 고유 값
    - alias_groups : inbound_vendor_aliases 의 canonical → aliases 매핑
                     (입고 이력이 있는 canonical 만 포함)
    """
    _get_user(authorization)
    with get_connection() as con:
        vendor_rows = con.execute(
            "SELECT DISTINCT vendor FROM inbound_batches WHERE vendor IS NOT NULL AND vendor != '' ORDER BY vendor"
        ).fetchall()
        wholesale_rows = con.execute(
            "SELECT DISTINCT wholesale FROM inbound_batches WHERE wholesale IS NOT NULL AND wholesale != '' ORDER BY wholesale"
        ).fetchall()
        # 별칭: 입고 이력이 있는 canonical 만
        batch_vendors = {r[0] for r in vendor_rows}
        alias_rows = con.execute(
            "SELECT canonical, aliases FROM inbound_vendor_aliases WHERE aliases IS NOT NULL AND aliases != '' ORDER BY canonical"
        ).fetchall()
        alias_groups = []
        for canonical, aliases_str in alias_rows:
            alias_list = [a.strip() for a in aliases_str.split(",") if a.strip()]
            if not alias_list:
                continue
            # canonical 이 입고 이력에 있는 경우만 포함
            # (별칭으로 저장된 경우도 포함하기 위해 _resolve_vendor_names 없이 단순 체크)
            alias_groups.append({"canonical": canonical, "aliases": alias_list})
    return {
        "vendors": [r[0] for r in vendor_rows],
        "wholesales": [r[0] for r in wholesale_rows],
        "alias_groups": alias_groups,
    }


# ── 입고 배치 목록 ──────────────────────

@router.get("/batches")
def list_batches(
    vendor: Optional[str] = Query(None),
    wholesale: Optional[str] = Query(None),
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
        # 별칭 포함 업체명 목록으로 확장 (alias → canonical 포함) + 부분일치
        vendor_names = _resolve_vendor_names(vendor)
        ph = ",".join("?" * len(vendor_names))
        where.append(f"(vendor IN ({ph}) OR vendor LIKE ? OR vendor_canonical IN ({ph}) OR vendor_canonical LIKE ?)")
        params += vendor_names + [f"%{vendor}%"] + vendor_names + [f"%{vendor}%"]
    if wholesale:
        where.append("wholesale LIKE ?"); params.append(f"%{wholesale}%")
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
    # 실수량 입력 링크는 로그인 없이 접근 가능 (배치 ID가 비밀 토큰 역할)
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
        # 비로그인 공개 접근: 당일 자정 이후 만료
        if not authorization:
            _check_link_expiry(row[2])  # row[2] = inbound_date
        batch = _serialize_batch(row)

        items = con.execute("""
            SELECT id, batch_id, line_no, item_name, option_text, unit_price,
                   janggi_qty, actual_qty, missing_qty, status,
                   matched_barcode, matched_vendor, matched_product, matched_option,
                   match_confidence, needs_matching, memo,
                   supplier_location, supplier_contact, created_at, updated_at,
                   confirmed_by, item_wholesale
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

def _ocr_error_to_http(e: OcrError) -> HTTPException:
    """OcrError → HTTPException 매핑."""
    if e.kind in ("no_api_key", "auth", "model", "quota"):
        return HTTPException(status_code=503, detail=e.user_msg)
    if e.kind == "image":
        return HTTPException(status_code=400, detail=e.user_msg)
    if e.kind in ("timeout", "server"):
        return HTTPException(status_code=504, detail=e.user_msg)
    # schema, no_items
    return HTTPException(status_code=422, detail=e.user_msg)


@router.post("/batches/{batch_id}/ocr")
async def run_ocr(
    batch_id: str,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    """장끼 이미지 업로드 → OCR → repair_barcode 자동 매칭 → inbound_items 생성.

    실패 시 기존 items, 배치 상태, 장끼 파일을 변경하지 않는다.
    """
    user = _get_user(authorization)

    # 1. 배치 조회
    with get_connection() as con:
        batch_row = con.execute(
            "SELECT id, vendor, status, vendor_canonical FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
    if not batch_row:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
    vendor = batch_row[3] or batch_row[1]  # vendor_canonical 우선

    # 2. 파일 읽기 (임시 — OCR 성공 후에만 저장)
    raw = await file.read()

    # 3. 이미지 정규화 (실패 → 400)
    try:
        norm_bytes, mime = _normalize_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4. OCR 실행 (실패 → 적절한 HTTP 오류, DB 변경 없음)
    try:
        ocr_result = await _run_ocr(norm_bytes, mime)
    except OcrError as e:
        raise _ocr_error_to_http(e)

    # 5. 성공 → 파일 저장 후 트랜잭션 내 기존 OCR 품목 교체
    janggi_filename = f"{uuid.uuid4().hex}.jpg"
    (UPLOAD_DIR / janggi_filename).write_bytes(norm_bytes)

    receipt_data = ocr_result.get("receipt", {})
    items_data = ocr_result.get("items", [])

    wholesale = receipt_data.get("storeName")
    janggi_date = receipt_data.get("orderDate")
    janggi_no = receipt_data.get("receiptNo")

    now = datetime.utcnow().isoformat()
    created_items = []

    with get_connection() as con:
        # 기존 OCR 생성 품목 삭제 (재시도 시 교체)
        con.execute(
            "DELETE FROM inbound_items WHERE batch_id=? AND (memo LIKE '%OCR%' OR memo IS NULL)",
            (batch_id,),
        )

        for i, item in enumerate(items_data):
            item_id = uuid.uuid4().hex
            item_name = item.get("itemName") or ""
            color = item.get("color") or ""
            size_str = item.get("size") or ""
            option_text = item.get("optionText") or ""
            # color / size / optionText 합산
            combined_option = " ".join(filter(None, [color, size_str, option_text])) or None
            unit_price = item.get("unitPrice")
            janggi_qty = int(item.get("quantity") or 0)

            match = _match_barcode(vendor, item_name, combined_option, wholesale)
            needs_review = bool(item.get("needsReview", False))
            needs_matching = match["needs_matching"] or needs_review

            con.execute("""
                INSERT INTO inbound_items
                    (id, batch_id, line_no, item_name, option_text, unit_price,
                     janggi_qty, actual_qty, missing_qty, status,
                     matched_barcode, matched_vendor, matched_product, matched_option,
                     match_confidence, needs_matching, supplier_location, supplier_contact,
                     memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id, batch_id, i + 1, item_name, combined_option, unit_price,
                janggi_qty,
                match["matched_barcode"], match["matched_vendor"],
                match["matched_product"], match["matched_option"],
                match["match_confidence"], int(needs_matching),
                match.get("supplier_location") or "",
                match.get("supplier_contact") or "",
                "OCR", now,
            ))
            # OCR 자동매칭 성공 시 바코드 마스터에 도매처 정보 갱신
            if match.get("matched_barcode") and wholesale:
                _update_barcode_master(
                    con,
                    barcode=match["matched_barcode"],
                    wholesale=wholesale or "",
                    supplier_location=match.get("supplier_location") or "",
                    supplier_contact=match.get("supplier_contact") or "",
                    matched_product=match.get("matched_product") or "",
                    matched_option=match.get("matched_option") or "",
                )
            created_items.append({
                "id": item_id,
                "line_no": i + 1,
                "item_name": item_name,
                "option_text": combined_option,
                "janggi_qty": janggi_qty,
                **match,
            })

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

    add_log(
        "inbound", "ocr",
        f"OCR: {vendor} {len(created_items)}개 ({matched_count}매칭/{needs_count}확인필요)",
        user["user_id"],
    )
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
    # 실수량 입력은 로그인 없이도 가능 — confirmed_by로 입력자 이름 기록
    # 비로그인 공개 접근: 당일 자정 이후 만료
    if not authorization:
        with get_connection() as con:
            batch_info = con.execute(
                """SELECT b.inbound_date FROM inbound_items i
                   JOIN inbound_batches b ON i.batch_id = b.id
                   WHERE i.id=?""",
                (item_id,)
            ).fetchone()
        if batch_info:
            _check_link_expiry(batch_info[0])

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
    if body.item_name is not None:
        name_val = body.item_name.strip()
        fields.append("item_name=?"); params.append(name_val if name_val else None)
    if body.option_text is not None:
        opt_val = body.option_text.strip()
        fields.append("option_text=?"); params.append(opt_val if opt_val else None)
    if body.item_wholesale is not None:
        ws_val = body.item_wholesale.strip()
        fields.append("item_wholesale=?"); params.append(ws_val if ws_val else None)
    if body.confirmed_by is not None:
        name = body.confirmed_by.strip()[:50]  # 최대 50자, 앞뒤 공백 제거
        fields.append("confirmed_by=?"); params.append(name if name else None)
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

        # ── 바코드 마스터 자동 갱신 ──────────────────────────────────────
        # matched_barcode / supplier / 상품명·옵션 중 하나라도 변경될 때
        # repair_barcode 의 해당 바코드 레코드를 최신 상태로 갱신한다.
        should_update_master = any([
            body.matched_barcode, body.supplier_location, body.supplier_contact,
            body.matched_product, body.matched_option,
        ])
        if should_update_master:
            # 업데이트 후 품목 전체 상태 조회
            item_state = con.execute(
                """SELECT i.matched_barcode,
                          COALESCE(i.item_wholesale, b.wholesale) AS wholesale,
                          i.supplier_location,
                          i.supplier_contact,
                          i.matched_product,
                          i.matched_option
                   FROM inbound_items i
                   JOIN inbound_batches b ON i.batch_id = b.id
                   WHERE i.id=?""",
                (item_id,)
            ).fetchone()
            if item_state and item_state[0]:  # matched_barcode 있을 때만
                _update_barcode_master(
                    con,
                    barcode=item_state[0],
                    wholesale=item_state[1] or "",
                    supplier_location=item_state[2] or "",
                    supplier_contact=item_state[3] or "",
                    matched_product=item_state[4] or "",
                    matched_option=item_state[5] or "",
                )

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
    # 작업자도 사진 업로드 가능 (인증 불필요)
    # 비로그인 공개 접근: 당일 자정 이후 만료
    with get_connection() as con:
        item_row = con.execute("SELECT batch_id FROM inbound_items WHERE id=?", (item_id,)).fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
        batch_id = item_row[0]
        if not authorization:
            date_row = con.execute(
                "SELECT inbound_date FROM inbound_batches WHERE id=?", (batch_id,)
            ).fetchone()
            if date_row:
                _check_link_expiry(date_row[0])

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
    # 작업자도 사진 조회 가능 (인증 불필요)
    # 경로 탈출 방지
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다.")
    return FileResponse(path)


# ── 입고전표 엑셀 다운로드 ────────────────────

@router.get("/batches/{batch_id}/export-xls")
def export_inbound_xls(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    입고전표 형식 엑셀 다운로드.
    파일명: {vendor_alias}_{YYYYMMDD}.xls → 중복 시 _01, _02 넘버링.
    포맷:
      A: 바코드/상품코드   B: 작업수량(실입고)  C: 요청수량(장끼)
      D: 로케이션         E: 유통기한         F: 로트번호
      G: 제조번호         H: 재고메모(품명/옵션)
    """
    import re as _re
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from fastapi.responses import StreamingResponse

    _get_user(authorization)

    with get_connection() as con:
        batch_row = con.execute(
            """SELECT vendor, vendor_canonical, inbound_date, wholesale
               FROM inbound_batches WHERE id=?""",
            (batch_id,)
        ).fetchone()
        if not batch_row:
            raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")

        vendor        = batch_row[0]
        vendor_canon  = batch_row[1] or batch_row[0]
        inbound_date  = batch_row[2]          # YYYY-MM-DD
        date_str      = inbound_date.replace("-", "")  # YYYYMMDD

        # 별칭: vendor_canonical 우선, 없으면 vendor
        alias = vendor_canon or vendor
        # 파일명에 안전한 문자로 변환 (공백·슬래시 제거)
        safe_alias = _re.sub(r'[\\/:*?"<>|]', '_', alias).strip()
        base_name  = f"{safe_alias}_{date_str}"

        # 중복 넘버링: inbound_batch_exports 테이블 사용
        try:
            con.execute("""
                CREATE TABLE IF NOT EXISTS inbound_batch_exports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            con.commit()
        except Exception:
            pass

        existing = con.execute(
            "SELECT COUNT(*) FROM inbound_batch_exports WHERE batch_id=?",
            (batch_id,)
        ).fetchone()[0]

        if existing == 0:
            final_name = f"{base_name}.xls"
        else:
            final_name = f"{base_name}_{existing:02d}.xls"

        con.execute(
            "INSERT INTO inbound_batch_exports (batch_id, filename) VALUES (?, ?)",
            (batch_id, final_name)
        )
        con.commit()

        # 품목 목록 + 로케이션 조회
        items = con.execute(
            """SELECT ii.line_no, ii.item_name, ii.option_text,
                      ii.janggi_qty, ii.actual_qty, ii.missing_qty,
                      ii.matched_barcode, ii.matched_product, ii.matched_option,
                      ii.memo,
                      COALESCE(rb.로케이션, '') AS location
               FROM inbound_items ii
               LEFT JOIN repair_barcode rb ON rb.바코드 = ii.matched_barcode
               WHERE ii.batch_id = ?
               ORDER BY ii.line_no""",
            (batch_id,)
        ).fetchall()

    # ── 엑셀 생성 ──
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "입고전표"

    # 스타일
    hdr_font  = Font(name="굴림", bold=True, size=10)
    hdr_fill  = PatternFill("solid", fgColor="CCFFCC")
    hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_font = Font(name="굴림", size=10)
    thin      = Side(style="thin")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)

    HEADERS = [
        "상품코드/바코드(택1)", "작업수량", "요청수량",
        "로케이션", "유통기한", "로트번호", "제조번호", "재고메모",
    ]

    # 헤더 행
    for col_idx, h in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font      = hdr_font
        cell.fill      = hdr_fill
        cell.alignment = hdr_align
        cell.border    = border

    # 컬럼 너비
    col_widths = [22, 10, 10, 14, 12, 12, 12, 30]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 28

    # 데이터 행
    for row_idx, it in enumerate(items, 2):
        (line_no, item_name, option_text, janggi_qty, actual_qty,
         missing_qty, matched_barcode, matched_product, matched_option,
         memo, location) = it

        barcode  = matched_barcode or ""
        memo_val = ""
        if item_name:
            memo_val = item_name
        if option_text:
            memo_val += f" [{option_text}]" if memo_val else option_text
        if memo:
            memo_val += f" / {memo}" if memo_val else memo

        row_data = [
            barcode,
            actual_qty or 0,
            janggi_qty or 0,
            location,
            "",   # 유통기한
            "",   # 로트번호
            "",   # 제조번호
            memo_val,
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font   = cell_font
            cell.border = border
            if col_idx in (2, 3):
                cell.alignment = Alignment(horizontal="center")

    # 스트리밍 응답
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from urllib.parse import quote
    encoded = quote(final_name, safe="")

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


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

        # ── 오전 마감: confirming / ocr_pending → inbound_done ──────────────
        if close_type == "am":
            if current_status not in ("confirming", "ocr_pending"):
                return {"ok": False, "warning": f"입고처리 완료는 '수량 확인 중' 또는 '장끼 등록 완료' 상태에서만 가능합니다. (현재: {STATUS_LABELS.get(current_status, current_status)})"}

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
            "SELECT batch_id, password, expires_at, allow_excel, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")
        batch_id, stored_pw, expires_at, allow_excel, revoked_at = row

        # 폐기 확인
        if revoked_at:
            raise HTTPException(status_code=410, detail="폐기된 링크입니다.")

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
    """장끼 이미지를 GPT Vision으로 분석해 품목 목록을 반환. DB·업로드 폴더에 저장하지 않음."""
    _get_user(authorization)

    raw = await file.read()

    try:
        norm_bytes, mime = _normalize_image(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await _run_ocr(norm_bytes, mime)
    except OcrError as e:
        raise _ocr_error_to_http(e)

    return {
        "ok": True,
        "receipt": result.get("receipt", {}),
        "items": result.get("items", []),
        "raw": result,
    }


# ═══════════════════════════════════════════════════════════════
#  입고 건별 통합 처리현황 (feat/inbound-unified-overview)
# ═══════════════════════════════════════════════════════════════

# ── 이미지 URL 헬퍼 (수선/불량일지용) ──────────────────────────

def _image_url_repair(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/repair-log/image/{filename}"


def _image_url_defect(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/defect-log/image/{filename}"


# ── 처리 단계 추론 ──────────────────────────────────────────────

def _infer_phase(
    *,
    status: str,
    pending_qty: int,
    defect_qty: int,
    repairing_qty: int,
    received_qty: int,
) -> str:
    """batch 상태 + 수량 현황 → 한국어 처리 단계."""
    if status in ("ocr_pending", "confirming"):
        return "입고 확인 중"
    if status == "done":
        return "최종 마감 완료"
    if status == "cancelled":
        return "취소"
    # 진행 중
    if repairing_qty > 0:
        return "수선 진행 중"
    if defect_qty > 0:
        return "불량 확인 중"
    if pending_qty > 0:
        return "양품화 진행 중"
    if received_qty > 0:
        return "양품화 진행 중"
    return "입고 확인 중"


# ── 배치 통합현황 계산 헬퍼 ─────────────────────────────────────

def _compute_batch_overview(batch_id: str, con, *, public: bool = False) -> Optional[dict]:
    """
    batch_id 기준 통합현황 dict 반환.

    public=True 이면 내부 전용 필드(원가, 직원명, 인증정보)를 제외한 공유 DTO 반환.
    반환값이 None 이면 배치가 존재하지 않음.

    수량 계산 원칙
    ─────────────
    장끼수량 = 실입고수량 + 미입고수량
    실입고수량 = 미처리 + 정상처리 + 불량판정중 + 수선중 + 수선후정상 + 회생불가
    최종정상수량 = 정상처리 + 수선후정상

    상태 매핑 (inbound_items.status → 카테고리)
    ─────────────────────────────────────────
    pending       → 미처리 (actual_qty - normal_qty)
    confirmed     → 정상처리 (actual_qty)
    defect        → 불량판정중 (actual_qty)
    repair        → 수선중 (actual_qty)
    done          → 수선후정상 (actual_qty)
    unrecoverable → 회생불가 (actual_qty)
    missing       → (missing_qty 컬럼 사용)

    pending 상태 품목의 경우 normal_qty(직원 입력)만큼 정상처리로 먼저 차감한다.
    중복 집계 방지: status는 해당 품목의 현재 최종 상태 → 이력 기록은 defect/repair_log에만
    """
    batch_row = con.execute("""
        SELECT id, vendor, inbound_date, status, memo,
               janggi_filename, janggi_date, janggi_no, wholesale,
               total_janggi_qty, total_actual_qty, total_missing_qty,
               created_by, closed_by, closed_at, created_at, updated_at, vendor_canonical
        FROM inbound_batches WHERE id=?
    """, (batch_id,)).fetchone()

    if not batch_row:
        return None

    # 품목 조회 (normal_qty 포함)
    items_raw = con.execute("""
        SELECT id, batch_id, line_no, item_name, option_text, unit_price,
               janggi_qty, actual_qty, missing_qty, status,
               matched_barcode, matched_vendor, matched_product, matched_option,
               match_confidence, needs_matching, memo,
               supplier_location, supplier_contact, created_at, updated_at,
               confirmed_by, item_wholesale,
               COALESCE(normal_qty, 0) AS normal_qty,
               inbound_item_id, defect_case_id
        FROM inbound_items WHERE batch_id=? ORDER BY line_no, created_at
    """, (batch_id,)).fetchall()

    item_ids = [r[0] for r in items_raw]

    # 품목 사진
    photos_map: dict = {}
    if item_ids:
        ph_rows = con.execute(
            f"SELECT item_id, id, filename FROM inbound_item_photos "
            f"WHERE item_id IN ({','.join('?'*len(item_ids))})",
            item_ids
        ).fetchall()
        for ph in ph_rows:
            photos_map.setdefault(ph[0], []).append({
                "id": ph[1],
                "url": _image_url(ph[2]),
                "filename": ph[2],
            })

    # 불량일지 (inbound_item_id 연결)
    defect_map: dict = {}
    if item_ids:
        try:
            d_rows = con.execute(
                f"SELECT inbound_item_id, id, 날짜, 불량명, 수량, 비고, 처리결과, "
                f"before_image, after_image, extra_images "
                f"FROM defect_log WHERE inbound_item_id IN ({','.join('?'*len(item_ids))})"
                f" ORDER BY COALESCE(저장시간, 날짜) ASC",
                item_ids
            ).fetchall()
            for dr in d_rows:
                entry = {
                    "id": dr[1], "날짜": dr[2], "불량명": dr[3],
                    "수량": dr[4], "비고": dr[5], "처리결과": dr[6],
                    "before_image": _image_url_defect(dr[7]),
                    "after_image": _image_url_defect(dr[8]),
                }
                if not public:
                    entry["extra_images"] = dr[9]
                defect_map.setdefault(dr[0], []).append(entry)
        except Exception:
            pass  # 테이블 없으면 빈 맵

    # 수선일지 (inbound_item_id 연결)
    repair_map: dict = {}
    if item_ids:
        try:
            r_rows = con.execute(
                f"SELECT inbound_item_id, id, 날짜, 작업, 불량명, 수량, 비용, 비고, "
                f"before_image, after_image "
                f"FROM repair_work_log WHERE inbound_item_id IN ({','.join('?'*len(item_ids))})"
                f" ORDER BY COALESCE(저장시간, 날짜) ASC",
                item_ids
            ).fetchall()
            for rr in r_rows:
                entry = {
                    "id": rr[1], "날짜": rr[2], "작업": rr[3], "불량명": rr[4],
                    "수량": rr[5], "비고": rr[7],
                    "before_image": _image_url_repair(rr[8]),
                    "after_image": _image_url_repair(rr[9]),
                }
                if not public:
                    entry["비용"] = rr[6]
                repair_map.setdefault(rr[0], []).append(entry)
        except Exception:
            pass

    # ── 수량 집계 ──────────────────────────────────────────
    total_janggi = 0
    total_actual = 0
    total_missing = 0
    agg_pending = 0
    agg_normal = 0
    agg_defect = 0
    agg_repairing = 0
    agg_repaired_good = 0
    agg_unrecoverable = 0

    item_list = []
    for r in items_raw:
        item_id   = r[0]
        janggi_qty  = r[6] or 0
        actual_qty  = r[7] or 0
        missing_qty = r[8] or 0
        status      = r[9] or "pending"
        normal_qty_col = r[23] or 0  # 직원 입력 정상처리 수량

        # 상태별 수량 계산 (중복 집계 없음: 현재 최종 상태만 한 번 반영)
        if status == "confirmed":
            i_normal   = actual_qty
            i_pending  = 0
        elif status == "pending":
            i_normal   = min(normal_qty_col, actual_qty)
            i_pending  = max(actual_qty - i_normal, 0)
        else:
            i_normal  = 0
            i_pending = 0

        i_defect      = actual_qty if status == "defect"        else 0
        i_repairing   = actual_qty if status == "repair"        else 0
        i_repaired    = actual_qty if status == "done"          else 0
        i_unrecov     = actual_qty if status == "unrecoverable" else 0

        total_janggi    += janggi_qty
        total_actual    += actual_qty
        total_missing   += missing_qty
        agg_pending     += i_pending
        agg_normal      += i_normal
        agg_defect      += i_defect
        agg_repairing   += i_repairing
        agg_repaired_good += i_repaired
        agg_unrecoverable += i_unrecov

        item_data: dict = {
            "id":          item_id,
            "line_no":     r[2],
            "item_name":   r[3],
            "option_text": r[4],
            "janggi_qty":  janggi_qty,
            "actual_qty":  actual_qty,
            "missing_qty": missing_qty,
            "status":      status,
            "status_label": ITEM_STATUS_LABELS.get(status, status),
            "matched_barcode": r[10],
            "matched_vendor":  r[11],
            "matched_product": r[12],
            "matched_option":  r[13],
            "breakdown": {
                "normal":       i_normal,
                "pending":      i_pending,
                "defect":       i_defect,
                "repairing":    i_repairing,
                "repaired_good": i_repaired,
                "unrecoverable": i_unrecov,
            },
            "photos":      photos_map.get(item_id, []),
            "defect_logs": defect_map.get(item_id, []),
            "repair_logs": repair_map.get(item_id, []),
        }

        if not public:
            item_data["unit_price"]       = r[5]
            item_data["item_wholesale"]   = r[22]
            item_data["normal_qty_input"] = normal_qty_col
            item_data["needs_matching"]   = bool(r[15])
            item_data["match_confidence"] = r[14]
            item_data["supplier_location"] = r[17]
            item_data["supplier_contact"]  = r[18]
            item_data["confirmed_by"]      = r[21]
            item_data["memo"]              = r[16]
            item_data["defect_case_id"]    = r[25]
            item_data["inbound_item_id"]   = r[24]

        item_list.append(item_data)

    # ── 진행률 (0 나누기 안전 처리) ─────────────────────────
    final_good_qty   = agg_normal + agg_repaired_good
    received_qty     = total_actual
    expected_qty     = total_janggi

    inbound_progress = (
        round((received_qty + total_missing) / expected_qty * 100, 1)
        if expected_qty > 0 else 0.0
    )
    processing_progress = (
        round((agg_normal + agg_repaired_good + agg_unrecoverable) / received_qty * 100, 1)
        if received_qty > 0 else 0.0
    )

    phase = _infer_phase(
        status=batch_row[3],
        pending_qty=agg_pending,
        defect_qty=agg_defect,
        repairing_qty=agg_repairing,
        received_qty=received_qty,
    )

    # ── 처리 이력 타임라인 ─────────────────────────────────
    timeline: list = []
    for item_data in item_list:
        for d in item_data["defect_logs"]:
            timeline.append({
                "type": "defect",
                "date": d.get("날짜"),
                "item_name": item_data["item_name"],
                "detail": d.get("불량명"),
                "qty": d.get("수량"),
                "result": d.get("처리결과"),
                "id": d.get("id"),
            })
        for rr in item_data["repair_logs"]:
            timeline.append({
                "type": "repair",
                "date": rr.get("날짜"),
                "item_name": item_data["item_name"],
                "detail": rr.get("작업"),
                "qty": rr.get("수량"),
                "id": rr.get("id"),
            })
    timeline.sort(key=lambda e: (e.get("date") or ""), reverse=True)

    janggi_url = _image_url(batch_row[5]) if batch_row[5] else None

    batch_info: dict = {
        "id":            batch_row[0],
        "vendor":        batch_row[1],
        "inbound_date":  batch_row[2],
        "status":        batch_row[3],
        "status_label":  STATUS_LABELS.get(batch_row[3], batch_row[3]),
        "wholesale":     batch_row[8],
        "janggi_date":   batch_row[6],
        "janggi_no":     batch_row[7],
        "janggi_url":    janggi_url,
        "phase":         phase,
        "closed_at":     batch_row[14],
    }
    if not public:
        batch_info["memo"]       = batch_row[4]
        batch_info["created_by"] = batch_row[12]
        batch_info["closed_by"]  = batch_row[13]

    return {
        "batch": batch_info,
        "summary": {
            "expected_qty":      expected_qty,
            "received_qty":      received_qty,
            "missing_qty":       total_missing,
            "pending_qty":       agg_pending,
            "normal_qty":        agg_normal,
            "defect_pending_qty": agg_defect,
            "repairing_qty":     agg_repairing,
            "repaired_good_qty": agg_repaired_good,
            "unrecoverable_qty": agg_unrecoverable,
            "final_good_qty":    final_good_qty,
            "inbound_progress":  inbound_progress,
            "processing_progress": processing_progress,
        },
        "items":    item_list,
        "timeline": timeline[:50],
        "photos":   {"janggi": janggi_url},
    }


# ── 통합현황 조회 (내부, 인증 필요) ────────────────────────────

@router.get("/batches/{batch_id}/overview")
def get_batch_overview(
    batch_id: str,
    authorization: Optional[str] = Header(None),
):
    """입고 건별 통합 처리현황 (내부 직원용, 로그인 필요)."""
    _get_user(authorization)
    with get_connection() as con:
        overview = _compute_batch_overview(batch_id, con, public=False)
    if overview is None:
        raise HTTPException(status_code=404, detail="입고 배치를 찾을 수 없습니다.")
    return overview


# ── 정상처리 수량 입력·정정 ────────────────────────────────────

class NormalQtyUpdate(BaseModel):
    normal_qty: int
    confirmed_by: Optional[str] = None


@router.patch("/items/{item_id}/normal-qty")
def update_normal_qty(
    item_id: str,
    body: NormalQtyUpdate,
    authorization: Optional[str] = Header(None),
):
    """
    정상처리 수량 입력·정정 (인증 불필요 — 작업자 직접 입력).

    - normal_qty < 0  → 거부
    - normal_qty > actual_qty  → 거부 (실입고수량 초과 불가)
    - normal_qty == actual_qty → status 자동 'confirmed'
    - normal_qty < actual_qty, 현재 confirmed → status 'pending' 으로 복귀
    """
    if body.normal_qty < 0:
        raise HTTPException(status_code=400, detail="수량은 0 이상이어야 합니다.")

    with get_connection() as con:
        item_row = con.execute(
            "SELECT id, batch_id, actual_qty, status FROM inbound_items WHERE id=?",
            (item_id,)
        ).fetchone()
        if not item_row:
            raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")

        actual_qty = item_row[2] or 0
        current_status = item_row[3] or "pending"

        if body.normal_qty > actual_qty:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"정상처리 수량({body.normal_qty})이 "
                    f"실입고수량({actual_qty})을 초과할 수 없습니다."
                ),
            )

        # 자동 상태 전환 (중복 집계 방지: pending/confirmed 사이만 자동 전환)
        if body.normal_qty == actual_qty and actual_qty > 0:
            new_status = "confirmed"
        elif body.normal_qty < actual_qty and current_status == "confirmed":
            new_status = "pending"
        else:
            new_status = current_status  # 다른 상태(defect/repair 등)는 유지

        fields = ["normal_qty=?", "status=?", "updated_at=CURRENT_TIMESTAMP"]
        params: list = [body.normal_qty, new_status]
        if body.confirmed_by is not None:
            name = body.confirmed_by.strip()[:50]
            fields.append("confirmed_by=?")
            params.append(name if name else None)
        params.append(item_id)

        con.execute(f"UPDATE inbound_items SET {', '.join(fields)} WHERE id=?", params)
        _recalc_batch_totals(con, item_row[1])
        con.commit()

    return {"ok": True, "normal_qty": body.normal_qty, "status": new_status}


# ── 공유 링크 폐기 ──────────────────────────────────────────────

@router.delete("/share/{token}")
def revoke_share_link(
    token: str,
    authorization: Optional[str] = Header(None),
):
    """공유 링크 폐기 (인증 필요). 이후 해당 링크 접근 불가."""
    _get_user(authorization)

    with get_connection() as con:
        row = con.execute(
            "SELECT token, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")
        if row[1]:
            return {"ok": True, "already_revoked": True, "revoked_at": row[1]}

        con.execute(
            "UPDATE inbound_share_links SET revoked_at=CURRENT_TIMESTAMP WHERE token=?",
            (token,)
        )
        con.commit()

    return {"ok": True, "revoked": True}


# ── 공유 통합현황 (화주사용, 인증 불필요) ──────────────────────

@router.get("/share/{token}/overview")
def get_share_overview(
    token: str,
    password: Optional[str] = None,
):
    """
    공유 링크 토큰으로 통합현황 조회 (화주사용, 인증 불필요).

    보안:
    - 토큰에 연결된 화주사·batch만 조회 가능
    - 비밀번호, 만료, 폐기 검증
    - 다른 batch·화주사 접근 불가
    - 내부 필드(원가·직원명·인증정보) 제외한 공유 전용 DTO 반환
    """
    with get_connection() as con:
        link_row = con.execute(
            "SELECT batch_id, password, expires_at, revoked_at FROM inbound_share_links WHERE token=?",
            (token,)
        ).fetchone()
        if not link_row:
            raise HTTPException(status_code=404, detail="링크를 찾을 수 없습니다.")

        batch_id, stored_pw, expires_at, revoked_at = link_row

        # 폐기 확인
        if revoked_at:
            raise HTTPException(status_code=410, detail="폐기된 링크입니다.")

        # 만료 확인
        if expires_at and datetime.utcnow().strftime("%Y-%m-%d") > expires_at:
            raise HTTPException(status_code=410, detail="링크가 만료되었습니다.")

        # 비밀번호 확인
        if stored_pw:
            if not password:
                return {"needs_password": True}
            if not _verify_password(password, stored_pw):
                raise HTTPException(status_code=403, detail="비밀번호가 틀렸습니다.")

        # 공유 DTO 생성 (public=True → 내부 필드 제외)
        overview = _compute_batch_overview(batch_id, con, public=True)

    if overview is None:
        raise HTTPException(status_code=404, detail="입고 데이터를 찾을 수 없습니다.")

    overview["expires_at"] = expires_at
    overview["updated_at"] = overview["batch"].get("closed_at") or overview["batch"].get("inbound_date")
    return overview
