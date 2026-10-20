"""
backend/app/api/receipt.py - 동대문 장끼/영수증 AI 분석 API
──────────────────────────────────────────────────────────
업로드 판독은 업무봇 장끼 OCR(inbound.ocr)과 같은 프롬프트·스키마·
이미지 정규화를 사용한다. 금액 검산과 영수증 저장·엑셀은 이 모듈이 담당한다.

기능:
- 이미지 업로드 → 업무봇과 같은 장끼 판독
- 거래처명, 날짜, 품목(품명/옵션/단가/수량/금액) 자동 추출
- 금액 검산 (단가×수량=금액, 품목합계=영수증합계)
- 확인 필요 항목 자동 표시
- 엑셀 다운로드 (거래일/거래처명/품명/옵션/단가/수량/금액 등)
"""

import copy
import json
import re
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from logic.db import get_connection
from backend.app.api.inbound.ocr import (
    JANGGI_SCHEMA,
    OcrError,
    SYSTEM_PROMPT,
    _normalize_image,
    _ocr_error_to_http,
    _run_ocr,
)
from backend.app.api.logs import add_log
from backend.app.config import settings

router = APIRouter(prefix="/receipt", tags=["receipt"])


def _receipt_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / "receipts"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────

def ensure_receipt_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                image_filename TEXT,
                store_name TEXT,
                receipt_type TEXT DEFAULT '장끼',
                receipt_no TEXT,
                order_date TEXT,
                phone TEXT,
                total_amount REAL,
                paid_amount REAL,
                balance_amount REAL,
                bank_info TEXT,
                memo TEXT,
                raw_text TEXT,
                image_quality TEXT DEFAULT 'good',
                is_handwritten INTEGER DEFAULT 0,
                confidence REAL DEFAULT 1.0,
                needs_review INTEGER DEFAULT 0,
                warnings TEXT,
                address TEXT,
                business_number TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = {row[1] for row in con.execute("PRAGMA table_info(receipts)")}
        for column in ("address", "business_number"):
            if column not in existing:
                con.execute(f"ALTER TABLE receipts ADD COLUMN {column} TEXT")
        con.execute("""
            CREATE TABLE IF NOT EXISTS receipt_items (
                id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL,
                line_no INTEGER,
                raw_text TEXT,
                item_name TEXT,
                color TEXT,
                size TEXT,
                option_text TEXT,
                unit_price REAL,
                quantity REAL,
                amount REAL,
                confidence REAL DEFAULT 1.0,
                needs_review INTEGER DEFAULT 0,
                warnings TEXT,
                FOREIGN KEY (receipt_id) REFERENCES receipts(id)
            )
        """)
        con.commit()


# ─────────────────────────────────────
# 인증 헬퍼
# ─────────────────────────────────────

def get_user_from_token(token: str) -> dict:
    """로그인 세션 토큰으로 사용자를 확인한다. 다른 API와 같은 sessions 테이블을 본다."""
    with get_connection() as con:
        row = con.execute(
            """SELECT u.user_id, u.nickname, u.is_admin
               FROM sessions s JOIN users u ON s.user_id = u.user_id
               WHERE s.token = ?""",
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return {"user_id": row[0], "nickname": row[1], "is_admin": bool(row[2])}


# ─────────────────────────────────────
# 장끼 판독 (업무봇 OCR 재사용)
# ─────────────────────────────────────

def _receipt_ocr_schema() -> dict:
    """입고 장끼 스키마에 주소·사업자등록번호만 더한다. 원본 스키마는 바꾸지 않는다."""
    schema = copy.deepcopy(JANGGI_SCHEMA)
    receipt = schema["properties"]["receipt"]
    receipt["properties"]["address"] = {"type": ["string", "null"]}
    receipt["properties"]["businessNumber"] = {"type": ["string", "null"]}
    receipt["required"] = [*receipt["required"], "address", "businessNumber"]
    return schema


RECEIPT_OCR_SCHEMA = _receipt_ocr_schema()
RECEIPT_OCR_PROMPT = SYSTEM_PROMPT.replace(
    "반드시 위 JSON Schema를 정확히 따른다.",
    "8. 판매처 주소가 보이면 address에 적는다. 없으면 null이다. 추측하지 않는다.\n"
    "9. 사업자등록번호가 보이면 businessNumber에 적는다. 숫자 10자리면 000-00-00000으로 적는다. "
    "없거나 불명확하면 null이다. 추측하지 않는다.\n"
    "반드시 위 JSON Schema를 정확히 따른다.",
    1,
)


def _clean_optional_text(value) -> Optional[str]:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _normalize_business_number(value, receipt: dict) -> Optional[str]:
    """10자리 사업자등록번호는 000-00-00000으로 맞춘다. 다른 값은 확인 필요로 남긴다."""
    text = _clean_optional_text(value)
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    receipt["needsReview"] = True
    receipt.setdefault("warnings", [])
    if "사업자등록번호 형식 확인" not in receipt["warnings"]:
        receipt["warnings"].append("사업자등록번호 형식 확인")
    return text


def _receipt_column_names(con) -> list[str]:
    names = [row[1] for row in con.execute("PRAGMA table_info(receipts)")]
    return names + ["processor_name"]


def _as_receipt(row, names: list[str]) -> dict:
    receipt = dict(zip(names, row))
    receipt["is_handwritten"] = bool(receipt.get("is_handwritten"))
    receipt["needs_review"] = bool(receipt.get("needs_review"))
    try:
        receipt["warnings"] = json.loads(receipt.get("warnings") or "[]")
    except Exception:
        receipt["warnings"] = []
    return receipt

def _validate_amounts(receipt: dict, items: list) -> None:
    """단가×수량=금액 검산, 품목합계=영수증합계 검산"""
    for item in items:
        u = item.get("unitPrice")
        q = item.get("quantity")
        a = item.get("amount")
        if u is not None and q is not None and a is not None:
            calc = u * q
            if abs(calc - a) > 1:
                item["needsReview"] = True
                item.setdefault("warnings", [])
                item["warnings"].append(f"금액 불일치: {u}×{q}={calc} ≠ {a}")
        if item.get("confidence", 1.0) < 0.8:
            item["needsReview"] = True
        if not item.get("itemName") or item.get("quantity") is None or item.get("amount") is None:
            item["needsReview"] = True
            item.setdefault("warnings", [])
            item["warnings"].append("필수 정보 누락")

    total = receipt.get("totalAmount")
    if total is not None and items:
        items_total = sum(item.get("amount") or 0 for item in items)
        if abs(items_total - total) > 1:
            receipt["needsReview"] = True
            receipt.setdefault("warnings", [])
            receipt["warnings"].append(f"합계 불일치: 품목합계 {items_total} ≠ 영수증합계 {total}")

    if receipt.get("isHandwritten"):
        receipt["needsReview"] = True
        for item in items:
            item["needsReview"] = True

    if receipt.get("confidence", 1.0) < 0.8:
        receipt["needsReview"] = True


async def _analyze_janggi(image_bytes: bytes) -> tuple[bytes, dict]:
    """업무봇 장끼 판독으로 이미지를 읽고, 영수증 저장용 필드를 채운다.

    반환: (정규화된 JPEG bytes, 판독 dict)
    판독 실패 시 영수증 행을 만들지 않도록 호출 전에 예외를 던진다.
    """
    try:
        norm_bytes, mime = _normalize_image(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        parsed = await _run_ocr(
            norm_bytes,
            mime,
            schema=RECEIPT_OCR_SCHEMA,
            system_prompt=RECEIPT_OCR_PROMPT,
            schema_name="receipt_ocr",
        )
    except OcrError as exc:
        raise _ocr_error_to_http(exc) from exc

    receipt = parsed.setdefault("receipt", {})
    items = parsed.get("items") or []
    receipt["address"] = _clean_optional_text(receipt.get("address"))
    receipt["businessNumber"] = _normalize_business_number(receipt.get("businessNumber"), receipt)
    receipt.setdefault("receiptType", "장끼")
    receipt.setdefault(
        "imageQuality",
        "handwritten" if receipt.get("isHandwritten") else "good",
    )
    if not parsed.get("rawText"):
        parsed["rawText"] = "\n".join(
            str(item.get("rawText")) for item in items if item.get("rawText")
        )
    _validate_amounts(receipt, items)
    return norm_bytes, parsed


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class ReceiptItemUpdate(BaseModel):
    item_name: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    option_text: Optional[str] = None
    unit_price: Optional[float] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None


class ReceiptUpdate(BaseModel):
    store_name: Optional[str] = None
    order_date: Optional[str] = None
    phone: Optional[str] = None
    total_amount: Optional[float] = None
    bank_info: Optional[str] = None
    memo: Optional[str] = None
    address: Optional[str] = None
    business_number: Optional[str] = None


# ─────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────

@router.post("/upload")
async def upload_and_analyze(
    token: str,
    file: UploadFile = File(...),
):
    """장끼/영수증 이미지 업로드 → 업무봇과 같은 판독 → DB 저장"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    content = await file.read()
    norm_bytes, analysis = await _analyze_janggi(content)

    filename = f"{uuid.uuid4()}.jpg"
    file_path = _receipt_dir() / filename
    file_path.write_bytes(norm_bytes)

    receipt_data = analysis.get("receipt", {})
    items_data = analysis.get("items", [])

    receipt_id = str(uuid.uuid4())

    with get_connection() as con:
        con.execute("""
            INSERT INTO receipts
            (id, user_id, image_filename, store_name, receipt_type, receipt_no,
             order_date, phone, total_amount, paid_amount, balance_amount,
             bank_info, memo, raw_text, image_quality, is_handwritten,
             confidence, needs_review, warnings, address, business_number)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            receipt_id,
            user["user_id"],
            filename,
            receipt_data.get("storeName"),
            receipt_data.get("receiptType", "장끼"),
            receipt_data.get("receiptNo"),
            receipt_data.get("orderDate"),
            receipt_data.get("phone"),
            receipt_data.get("totalAmount"),
            receipt_data.get("paidAmount"),
            receipt_data.get("balanceAmount"),
            receipt_data.get("bankInfo"),
            receipt_data.get("memo"),
            analysis.get("rawText"),
            receipt_data.get("imageQuality", "good"),
            1 if receipt_data.get("isHandwritten") else 0,
            receipt_data.get("confidence", 1.0),
            1 if receipt_data.get("needsReview") else 0,
            json.dumps(receipt_data.get("warnings", []), ensure_ascii=False),
            receipt_data.get("address"),
            receipt_data.get("businessNumber"),
        ))

        for item in items_data:
            item_id = str(uuid.uuid4())
            con.execute("""
                INSERT INTO receipt_items
                (id, receipt_id, line_no, raw_text, item_name, color, size,
                 option_text, unit_price, quantity, amount,
                 confidence, needs_review, warnings)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                item_id, receipt_id,
                item.get("lineNo"),
                item.get("rawText"),
                item.get("itemName"),
                item.get("color"),
                item.get("size"),
                item.get("optionText"),
                item.get("unitPrice"),
                item.get("quantity"),
                item.get("amount"),
                item.get("confidence", 1.0),
                1 if item.get("needsReview") else 0,
                json.dumps(item.get("warnings", []), ensure_ascii=False),
            ))

        con.commit()

    store = receipt_data.get("storeName") or "미추출"
    item_count = len(items_data)
    add_log(
        action_type="영수증 업로드",
        target_type="receipt",
        target_id=receipt_id,
        target_name=store,
        user_nickname=user["nickname"],
        details=f"거래처:{store} / 품목 {item_count}개 / AI분석{'(확인필요)' if receipt_data.get('needsReview') else '완료'}",
    )

    return {"receipt_id": receipt_id, "needs_review": bool(receipt_data.get("needsReview"))}


@router.get("/list")
def list_receipts(token: str, year: Optional[int] = None, month: Optional[int] = None):
    """영수증 목록 조회 (관리자=전체, 일반=본인)"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    with get_connection() as con:
        # 처리자 닉네임 포함 JOIN
        base = """
            SELECT r.*, u.nickname AS processor_name
            FROM receipts r
            LEFT JOIN users u ON r.user_id = u.user_id
        """
        params: list = []
        if user["is_admin"]:
            query = base + " WHERE 1=1"
        else:
            query = base + " WHERE r.user_id = ?"
            params.append(user["user_id"])

        if year:
            query += " AND strftime('%Y', r.created_at) = ?"
            params.append(str(year))
        if month:
            query += " AND strftime('%m', r.created_at) = ?"
            params.append(f"{month:02d}")
        query += " ORDER BY r.created_at DESC"

        rows = con.execute(query, params).fetchall()
        cols = _receipt_column_names(con)

    return [_as_receipt(row, cols) for row in rows]


@router.get("/{receipt_id}")
def get_receipt(receipt_id: str, token: str):
    """영수증 단건 + 품목 조회 (처리자 정보 포함)"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    with get_connection() as con:
        # 관리자는 타인 영수증도 조회 가능
        if user["is_admin"]:
            row = con.execute(
                """SELECT r.*, u.nickname AS processor_name
                   FROM receipts r LEFT JOIN users u ON r.user_id = u.user_id
                   WHERE r.id = ?""",
                (receipt_id,)
            ).fetchone()
        else:
            row = con.execute(
                """SELECT r.*, u.nickname AS processor_name
                   FROM receipts r LEFT JOIN users u ON r.user_id = u.user_id
                   WHERE r.id = ? AND r.user_id = ?""",
                (receipt_id, user["user_id"])
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="영수증을 찾을 수 없습니다.")

        receipt = _as_receipt(row, _receipt_column_names(con))

        item_rows = con.execute(
            "SELECT * FROM receipt_items WHERE receipt_id = ? ORDER BY line_no",
            (receipt_id,)
        ).fetchall()
        item_cols = [
            "id", "receipt_id", "line_no", "raw_text", "item_name", "color", "size",
            "option_text", "unit_price", "quantity", "amount",
            "confidence", "needs_review", "warnings"
        ]
        items = []
        for ir in item_rows:
            d = dict(zip(item_cols, ir))
            d["needs_review"] = bool(d["needs_review"])
            try:
                d["warnings"] = json.loads(d["warnings"] or "[]")
            except Exception:
                d["warnings"] = []
            items.append(d)

        receipt["items"] = items
    return receipt


@router.put("/{receipt_id}")
def update_receipt(receipt_id: str, token: str, data: ReceiptUpdate):
    """영수증 헤더 수정"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    fields = {k: v for k, v in data.dict().items() if v is not None}
    if not fields:
        return {"success": True}

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with get_connection() as con:
        row = con.execute("SELECT store_name FROM receipts WHERE id = ?", (receipt_id,)).fetchone()
        store = row[0] if row else receipt_id
        con.execute(
            f"UPDATE receipts SET {set_clause} WHERE id = ? AND user_id = ?",
            list(fields.values()) + [receipt_id, user["user_id"]]
        )
        con.commit()
    add_log(
        action_type="영수증 수정",
        target_type="receipt",
        target_id=receipt_id,
        target_name=store,
        user_nickname=user["nickname"],
        details=f"수정 항목: {', '.join(fields.keys())}",
    )
    return {"success": True}


@router.put("/items/{item_id}")
def update_receipt_item(item_id: str, token: str, data: ReceiptItemUpdate):
    """품목 수정"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    fields = {k: v for k, v in data.dict().items() if v is not None}
    if not fields:
        return {"success": True}

    col_map = {
        "item_name": "item_name", "color": "color", "size": "size",
        "option_text": "option_text", "unit_price": "unit_price",
        "quantity": "quantity", "amount": "amount",
    }
    db_fields = {col_map[k]: v for k, v in fields.items() if k in col_map}

    # 금액 재검산
    if "unit_price" in db_fields or "quantity" in db_fields or "amount" in db_fields:
        with get_connection() as con:
            row = con.execute(
                "SELECT unit_price, quantity, amount FROM receipt_items WHERE id = ?",
                (item_id,)
            ).fetchone()
        if row:
            u = db_fields.get("unit_price", row[0])
            q = db_fields.get("quantity", row[1])
            a = db_fields.get("amount", row[2])
            if u is not None and q is not None and a is not None:
                calc = u * q
                nr = 1 if abs(calc - a) > 1 else 0
                db_fields["needs_review"] = nr

    set_clause = ", ".join(f"{k} = ?" for k in db_fields)
    with get_connection() as con:
        # 품목 소속 영수증 조회 (로그용)
        r_row = con.execute(
            "SELECT r.store_name FROM receipt_items ri JOIN receipts r ON ri.receipt_id = r.id WHERE ri.id = ?",
            (item_id,)
        ).fetchone()
        store = r_row[0] if r_row else item_id
        con.execute(
            f"UPDATE receipt_items SET {set_clause} WHERE id = ?",
            list(db_fields.values()) + [item_id]
        )
        con.commit()
    add_log(
        action_type="영수증 품목 수정",
        target_type="receipt",
        target_id=item_id,
        target_name=store,
        user_nickname=user["nickname"],
        details=f"수정 항목: {', '.join(fields.keys())}",
    )
    return {"success": True}


class ReceiptDeleteRequest(BaseModel):
    ids: List[str]


def _delete_receipts(con, user: dict, ids: list[str]) -> list[tuple]:
    """권한 있는 영수증만 지운다. 반환은 (id, store_name)."""
    unique = list(dict.fromkeys(i for i in ids if i))
    if not unique:
        return []
    placeholders = ",".join("?" * len(unique))
    if user["is_admin"]:
        rows = con.execute(
            f"SELECT id, image_filename, store_name FROM receipts WHERE id IN ({placeholders})",
            unique,
        ).fetchall()
    else:
        rows = con.execute(
            f"""SELECT id, image_filename, store_name FROM receipts
                WHERE user_id = ? AND id IN ({placeholders})""",
            [user["user_id"], *unique],
        ).fetchall()
    found_ids = [row[0] for row in rows]
    if not found_ids:
        return []
    for _, filename, _store in rows:
        if not filename:
            continue
        img_path = _receipt_dir() / filename
        try:
            if img_path.is_file():
                img_path.unlink()
        except OSError:
            pass
    found_placeholders = ",".join("?" * len(found_ids))
    con.execute(
        f"DELETE FROM receipt_items WHERE receipt_id IN ({found_placeholders})",
        found_ids,
    )
    con.execute(
        f"DELETE FROM receipts WHERE id IN ({found_placeholders})",
        found_ids,
    )
    return [(row[0], row[2]) for row in rows]


@router.post("/delete")
def delete_selected_receipts(token: str, data: ReceiptDeleteRequest):
    """체크한 영수증만 삭제한다. 관리자는 고른 영수증을 누구 것이든 지운다."""
    ensure_receipt_tables()
    user = get_user_from_token(token)
    if not data.ids:
        raise HTTPException(status_code=400, detail="삭제할 영수증을 선택해 주세요.")
    if len(data.ids) > 500:
        raise HTTPException(status_code=400, detail="한 번에 500건까지만 삭제할 수 있습니다.")

    with get_connection() as con:
        removed = _delete_receipts(con, user, data.ids)
        con.commit()
    if not removed:
        raise HTTPException(status_code=404, detail="삭제할 수 있는 영수증이 없습니다.")

    add_log(
        action_type="영수증 선택 삭제",
        target_type="receipt",
        target_id=removed[0][0],
        target_name=removed[0][1] or removed[0][0],
        user_nickname=user["nickname"],
        details=f"영수증 {len(removed)}건 삭제",
    )
    return {"success": True, "deleted": len(removed)}


@router.delete("/{receipt_id}")
def delete_receipt(receipt_id: str, token: str):
    """영수증 삭제"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    with get_connection() as con:
        removed = _delete_receipts(con, user, [receipt_id])
        if not removed:
            raise HTTPException(status_code=404, detail="영수증을 찾을 수 없습니다.")
        con.commit()
    row = removed[0]

    add_log(
        action_type="영수증 삭제",
        target_type="receipt",
        target_id=receipt_id,
        target_name=row[1] or receipt_id,
        user_nickname=user["nickname"],
        details="영수증 및 품목 전체 삭제",
    )
    return {"success": True}


@router.get("/bulk-excel")
def download_bulk_excel(token: str, year: Optional[int] = None, month: Optional[int] = None):
    """필터 조건에 맞는 영수증 전체를 엑셀로 다운로드"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        import io

        # 영수증 목록 조회 (기존 list 로직 재활용)
        with get_connection() as con:
            base = """
                SELECT r.id, r.store_name, r.receipt_type, r.receipt_no,
                       r.order_date, r.phone, r.total_amount, r.bank_info,
                       r.is_handwritten, r.needs_review, r.created_at,
                       u.nickname AS processor_name,
                       r.address, r.business_number
                FROM receipts r
                LEFT JOIN users u ON r.user_id = u.user_id
            """
            params: list = []
            if user["is_admin"]:
                query = base + " WHERE 1=1"
            else:
                query = base + " WHERE r.user_id = ?"
                params.append(user["user_id"])
            if year:
                query += " AND strftime('%Y', r.created_at) = ?"
                params.append(str(year))
            if month:
                query += " AND strftime('%m', r.created_at) = ?"
                params.append(str(month).zfill(2))
            query += " ORDER BY r.created_at DESC"

            receipts_rows = con.execute(query, params).fetchall()
            receipt_ids = [r[0] for r in receipts_rows]
            receipt_map = {r[0]: r for r in receipts_rows}

            # 품목 한 번에 조회
            if receipt_ids:
                placeholders = ",".join("?" * len(receipt_ids))
                items_rows = con.execute(
                    f"""SELECT receipt_id, item_name, color, size, option_text,
                               unit_price, quantity, amount, needs_review, warnings
                        FROM receipt_items WHERE receipt_id IN ({placeholders})
                        ORDER BY receipt_id, line_no""",
                    receipt_ids
                ).fetchall()
            else:
                items_rows = []

        # 품목을 receipt_id 별로 그룹화
        from collections import defaultdict
        import json as _json
        items_by_receipt: dict = defaultdict(list)
        for it in items_rows:
            items_by_receipt[it[0]].append(it)

        # 엑셀 작성
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "영수증목록"

        headers = ["처리일시", "처리자", "거래일", "거래처명", "영수증번호", "종류",
                   "품명", "색상", "사이즈", "옵션", "단가", "수량", "금액",
                   "합계", "연락처", "계좌정보", "수기여부", "확인필요",
                   "주소", "사업자등록번호"]
        header_fill = PatternFill("solid", fgColor="1F4E79")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        review_fill = PatternFill("solid", fgColor="FFF2CC")
        alt_fill = PatternFill("solid", fgColor="EBF3FB")

        row_idx = 2
        for rid in receipt_ids:
            r = receipt_map[rid]
            (r_id, store, r_type, r_no, order_date, phone,
             total_amount, bank_info, is_hw, needs_review,
             created_at, processor, address, business_number) = r

            items = items_by_receipt.get(rid, [])
            if not items:
                # 품목 없는 영수증도 한 줄 출력
                row_data = [
                    created_at, processor or "", order_date or "",
                    store or "", r_no or "", r_type,
                    "", "", "", "", None, None, None,
                    total_amount, phone or "", bank_info or "",
                    "O" if is_hw else "", "O" if needs_review else "",
                    address or "", business_number or "",
                ]
                ws.append(row_data)
                if needs_review:
                    for ci in range(1, len(headers) + 1):
                        ws.cell(row=row_idx, column=ci).fill = review_fill
                elif row_idx % 2 == 0:
                    for ci in range(1, len(headers) + 1):
                        ws.cell(row=row_idx, column=ci).fill = alt_fill
                row_idx += 1
            else:
                for it in items:
                    (_, item_name, color, size, option_text,
                     unit_price, quantity, amount, it_review, warnings_json) = it
                    try:
                        warnings = _json.loads(warnings_json) if warnings_json else []
                    except Exception:
                        warnings = []
                    row_data = [
                        created_at, processor or "", order_date or "",
                        store or "", r_no or "", r_type,
                        item_name or "", color or "", size or "", option_text or "",
                        unit_price, quantity, amount,
                        total_amount, phone or "", bank_info or "",
                        "O" if is_hw else "",
                        "O" if it_review else ("△" if warnings else ""),
                        address or "", business_number or "",
                    ]
                    ws.append(row_data)
                    if it_review:
                        for ci in range(1, len(headers) + 1):
                            ws.cell(row=row_idx, column=ci).fill = review_fill
                    elif row_idx % 2 == 0:
                        for ci in range(1, len(headers) + 1):
                            ws.cell(row=row_idx, column=ci).fill = alt_fill
                    row_idx += 1

        # 컬럼 너비 설정
        col_widths = [18, 10, 12, 20, 14, 10, 28, 10, 8, 18, 10, 8, 12, 12, 15, 30, 8, 8, 36, 16]
        for ci, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

        # 금액 컬럼 숫자 서식
        for col in [11, 12, 13, 14]:
            for row in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                for cell in row:
                    if cell.value is not None:
                        cell.number_format = '#,##0'

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        year_str = str(year) if year else "전체"
        month_str = f"{month}월" if month else "전체"
        filename = f"영수증_{year_str}_{month_str}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl이 설치되지 않았습니다.")


@router.get("/{receipt_id}/excel")
def download_excel(receipt_id: str, token: str):
    """영수증 엑셀 다운로드"""
    ensure_receipt_tables()
    user = get_user_from_token(token)

    receipt_full = get_receipt(receipt_id, token)

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        import io

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "영수증정리"

        # 헤더
        headers = ["거래일", "거래처명", "영수증번호", "품명", "색상", "사이즈", "옵션",
                   "단가", "수량", "금액", "합계", "연락처", "계좌정보", "확인필요", "비고",
                   "주소", "사업자등록번호"]
        header_fill = PatternFill("solid", fgColor="366092")
        header_font = Font(color="FFFFFF", bold=True)
        for ci, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # 데이터 행
        review_fill = PatternFill("solid", fgColor="FFF2CC")
        for item in receipt_full["items"]:
            row_data = [
                receipt_full.get("order_date", ""),
                receipt_full.get("store_name", ""),
                receipt_full.get("receipt_no", ""),
                item.get("item_name", ""),
                item.get("color", ""),
                item.get("size", ""),
                item.get("option_text", ""),
                item.get("unit_price"),
                item.get("quantity"),
                item.get("amount"),
                receipt_full.get("total_amount"),
                receipt_full.get("phone", ""),
                receipt_full.get("bank_info", ""),
                "O" if item.get("needs_review") else "",
                ", ".join(item.get("warnings", [])),
                receipt_full.get("address") or "",
                receipt_full.get("business_number") or "",
            ]
            ws.append(row_data)
            if item.get("needs_review"):
                for ci in range(1, len(headers) + 1):
                    ws.cell(row=ws.max_row, column=ci).fill = review_fill

        # 컬럼 너비
        col_widths = [12, 20, 15, 28, 10, 8, 18, 10, 8, 12, 12, 15, 30, 10, 30, 36, 16]
        for ci, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        store = receipt_full.get("store_name") or "영수증"
        dt = (receipt_full.get("order_date") or datetime.now().strftime("%Y%m%d")).replace("-", "")
        filename = f"영수증정리_{store}_{dt}.xlsx"

        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"}
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl이 설치되지 않았습니다.")


@router.get("/image/{filename}")
def get_image(filename: str, token: str):
    """영수증 이미지 반환"""
    get_user_from_token(token)
    img_path = _receipt_dir() / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")

    from fastapi.responses import FileResponse
    return FileResponse(img_path)
