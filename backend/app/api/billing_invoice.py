"""
backend/app/api/billing_invoice.py - 실 인보이스 업로드 / 파싱 / 분석 API

PDF (엑셀 기반) → pdfplumber 텍스트 추출 → GPT-4o 구조화 파싱 → DB 저장
"""
import os
import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from logic.db import get_connection
from backend.app.api.logs import add_log
from backend.app.config import settings

router = APIRouter(prefix="/billing-invoice", tags=["billing-invoice"])

UPLOAD_DIR = Path("/app/billing_invoice_uploads") if Path("/app").exists() else Path("billing_invoice_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_MAP = {
    "우체국택배": "택배비",
    "택배": "택배비",
    "반품택배": "택배비",
    "기본포장": "포장비",
    "합포장": "포장비",
    "pp봉투": "포장비",
    "pp 봉투": "포장비",
    "택배봉투": "포장비",
    "봉투": "포장비",
    "입고": "입출고비",
    "양품화": "입출고비",
    "반품 회수": "입출고비",
    "반품회수": "입출고비",
    "보관료": "보관료",
    "바코드": "바코드",
    "도서산간": "도서산간",
    "영상": "부대비용",
    "사입": "부대비용",
    "차감": "차감",
}

GPT_SYSTEM_PROMPT = """
너는 물류 풀필먼트 청구서 PDF 텍스트를 분석해서 구조화된 JSON으로 반환하는 AI야.

PDF 텍스트는 멀티컬럼 레이아웃 때문에 순서가 뒤섞여 있을 수 있어.
항목 행(No, 수량, 단가, 금액)과 품명이 분리되어 나타날 수 있으니 No 순서대로 품명을 매핑해.
금액이 음수(차감)인 경우 그대로 음수로 반환해.

반드시 아래 JSON 형식만 반환하고 다른 설명은 하지 마:

{
  "invoice_no": "문서번호",
  "client_name": "수신 거래처명 (회사명만, '대표님 귀하' 제외)",
  "invoice_date": "청구일자 YYYY-MM-DD",
  "due_date": "지급기한 YYYY-MM-DD (없으면 null)",
  "service_month": "서비스 월 YYYY-MM (건명에서 추출, 예: 2026-05)",
  "subject": "건명",
  "supply_amount": 공급가액(숫자),
  "vat_amount": 부가세(숫자),
  "total_amount": 청구합계(숫자),
  "bank_name": "은행명",
  "account_holder": "예금주",
  "account_number": "계좌번호",
  "items": [
    {
      "line_no": 행번호(숫자),
      "item_name": "품명",
      "quantity": 수량(숫자 또는 null),
      "unit_price": 단가(숫자 또는 null),
      "amount": 금액(숫자, 차감은 음수),
      "memo": "비고 (없으면 null)"
    }
  ]
}
"""


# ─────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────

def ensure_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS billing_invoices (
                id              TEXT PRIMARY KEY,
                invoice_no      TEXT,
                client_name     TEXT NOT NULL,
                invoice_date    TEXT,
                due_date        TEXT,
                service_month   TEXT,
                subject         TEXT,
                supply_amount   REAL DEFAULT 0,
                vat_amount      REAL DEFAULT 0,
                total_amount    REAL NOT NULL DEFAULT 0,
                paid_amount     REAL DEFAULT 0,
                paid_date       TEXT,
                status          TEXT DEFAULT '미납',
                bank_name       TEXT,
                account_holder  TEXT,
                account_number  TEXT,
                memo            TEXT,
                pdf_filename    TEXT,
                created_by      TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                confirmed       INTEGER DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS billing_invoice_items (
                id          TEXT PRIMARY KEY,
                invoice_id  TEXT NOT NULL,
                line_no     INTEGER,
                item_name   TEXT,
                category    TEXT,
                quantity    REAL,
                unit_price  REAL,
                amount      REAL,
                memo        TEXT,
                FOREIGN KEY (invoice_id) REFERENCES billing_invoices(id)
            )
        """)
        con.commit()


def _get_user(token: str) -> dict:
    with get_connection() as con:
        row = con.execute(
            "SELECT u.user_id, u.nickname, u.is_admin FROM sessions s JOIN users u USING(user_id) WHERE s.token=?",
            (token,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {"user_id": row[0], "nickname": row[1], "is_admin": bool(row[2])}


def _require_admin(token: str) -> dict:
    user = _get_user(token)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


def _guess_category(item_name: str) -> str:
    if not item_name:
        return "기타"
    for keyword, category in CATEGORY_MAP.items():
        if keyword in item_name:
            return category
    return "기타"


def _parse_pdf_text(text: str) -> dict:
    """GPT-4o로 PDF 텍스트 파싱"""
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": GPT_SYSTEM_PROMPT},
            {"role": "user", "content": f"아래 PDF 텍스트를 분석해:\n\n{text}"},
        ],
        temperature=0,
        max_tokens=4000,
    )
    raw = resp.choices[0].message.content.strip()
    # JSON 블록 추출
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ─────────────────────────────────────
# API: PDF 업로드 & 파싱
# ─────────────────────────────────────

@router.post("/upload")
async def upload_invoice(token: str = Form(...), file: UploadFile = File(...)):
    """PDF 업로드 → 텍스트 추출 → GPT 파싱 → DB 저장"""
    ensure_tables()
    user = _require_admin(token)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    try:
        import pdfplumber
    except ImportError:
        raise HTTPException(status_code=500, detail="pdfplumber가 설치되지 않았습니다.")

    # 파일 저장
    pdf_id = str(uuid.uuid4())
    safe_name = f"{pdf_id}.pdf"
    pdf_path = UPLOAD_DIR / safe_name
    content = await file.read()
    pdf_path.write_bytes(content)

    # 텍스트 추출
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"PDF 읽기 실패: {e}")

    if not text.strip():
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="PDF에서 텍스트를 추출할 수 없습니다. (스캔 PDF는 미지원)")

    # GPT 파싱
    try:
        parsed = _parse_pdf_text(text)
    except Exception as e:
        pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"AI 파싱 실패: {e}")

    # DB 저장
    items = parsed.pop("items", [])
    invoice_id = pdf_id

    with get_connection() as con:
        con.execute("""
            INSERT INTO billing_invoices
              (id, invoice_no, client_name, invoice_date, due_date, service_month,
               subject, supply_amount, vat_amount, total_amount,
               bank_name, account_holder, account_number,
               pdf_filename, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            invoice_id,
            parsed.get("invoice_no"),
            parsed.get("client_name", "미상"),
            parsed.get("invoice_date"),
            parsed.get("due_date"),
            parsed.get("service_month"),
            parsed.get("subject"),
            parsed.get("supply_amount", 0),
            parsed.get("vat_amount", 0),
            parsed.get("total_amount", 0),
            parsed.get("bank_name"),
            parsed.get("account_holder"),
            parsed.get("account_number"),
            safe_name,
            user["nickname"],
        ))

        for it in items:
            item_id = str(uuid.uuid4())
            category = _guess_category(it.get("item_name", ""))
            con.execute("""
                INSERT INTO billing_invoice_items
                  (id, invoice_id, line_no, item_name, category, quantity, unit_price, amount, memo)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                item_id, invoice_id,
                it.get("line_no"),
                it.get("item_name"),
                category,
                it.get("quantity"),
                it.get("unit_price"),
                it.get("amount"),
                it.get("memo"),
            ))
        con.commit()

    add_log(
        action_type="인보이스 업로드",
        target_type="billing_invoice",
        target_id=invoice_id,
        target_name=parsed.get("client_name", "미상"),
        user_nickname=user["nickname"],
        details=f"{parsed.get('client_name')} / {parsed.get('service_month')} / {parsed.get('total_amount'):,}원",
    )

    return {
        "invoice_id": invoice_id,
        "parsed": {**parsed, "items": items},
        "item_count": len(items),
    }


# ─────────────────────────────────────
# API: 목록 조회
# ─────────────────────────────────────

@router.get("/list")
def list_invoices(
    token: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    client_name: Optional[str] = None,
    status: Optional[str] = None,
):
    ensure_tables()
    _require_admin(token)

    query = "SELECT * FROM billing_invoices WHERE 1=1"
    params: list = []
    if year:
        query += " AND strftime('%Y', COALESCE(invoice_date, created_at)) = ?"
        params.append(str(year))
    if month:
        query += " AND strftime('%m', COALESCE(invoice_date, created_at)) = ?"
        params.append(str(month).zfill(2))
    if client_name:
        query += " AND client_name LIKE ?"
        params.append(f"%{client_name}%")
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY invoice_date DESC"

    with get_connection() as con:
        rows = con.execute(query, params).fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(billing_invoices)").fetchall()]

    return [dict(zip(cols, r)) for r in rows]


# ─────────────────────────────────────
# API: 분석 (반드시 /{invoice_id} GET 앞에 정의해야 라우팅 충돌 방지)
# ─────────────────────────────────────

@router.get("/analytics/summary")
def analytics_summary(token: str, year: Optional[int] = None):
    ensure_tables()
    _require_admin(token)

    y = str(year) if year else str(date.today().year)
    with get_connection() as con:
        monthly = con.execute("""
            SELECT strftime('%Y-%m', invoice_date) as ym,
                   COUNT(*) as invoice_count,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid
            FROM billing_invoices
            WHERE strftime('%Y', invoice_date) = ?
            GROUP BY ym ORDER BY ym
        """, (y,)).fetchall()

        by_client = con.execute("""
            SELECT client_name,
                   COUNT(*) as invoice_count,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid,
                   SUM(total_amount - paid_amount) as unpaid
            FROM billing_invoices
            WHERE strftime('%Y', invoice_date) = ?
            GROUP BY client_name ORDER BY total DESC
        """, (y,)).fetchall()

        by_category = con.execute("""
            SELECT ii.category,
                   SUM(ii.amount) as total
            FROM billing_invoice_items ii
            JOIN billing_invoices inv ON ii.invoice_id = inv.id
            WHERE strftime('%Y', inv.invoice_date) = ?
              AND ii.amount > 0
            GROUP BY ii.category ORDER BY total DESC
        """, (y,)).fetchall()

        unpaid = con.execute("""
            SELECT id, client_name, invoice_date, due_date,
                   total_amount, paid_amount,
                   (total_amount - paid_amount) as unpaid_amount,
                   status
            FROM billing_invoices
            WHERE status IN ('미납', '부분납')
              AND strftime('%Y', invoice_date) = ?
            ORDER BY due_date ASC NULLS LAST
        """, (y,)).fetchall()

        total_row = con.execute("""
            SELECT COUNT(*), SUM(total_amount), SUM(paid_amount)
            FROM billing_invoices WHERE strftime('%Y', invoice_date) = ?
        """, (y,)).fetchone()

    today = date.today().isoformat()

    return {
        "year": y,
        "summary": {
            "invoice_count": total_row[0] or 0,
            "total_billed": total_row[1] or 0,
            "total_paid": total_row[2] or 0,
            "total_unpaid": (total_row[1] or 0) - (total_row[2] or 0),
        },
        "monthly": [
            {"month": r[0], "invoice_count": r[1], "total": r[2] or 0, "paid": r[3] or 0,
             "unpaid": (r[2] or 0) - (r[3] or 0)}
            for r in monthly
        ],
        "by_client": [
            {"client_name": r[0], "invoice_count": r[1],
             "total": r[2] or 0, "paid": r[3] or 0, "unpaid": r[4] or 0}
            for r in by_client
        ],
        "by_category": [
            {"category": r[0] or "기타", "total": r[1] or 0}
            for r in by_category
        ],
        "unpaid_list": [
            {
                "id": r[0], "client_name": r[1],
                "invoice_date": r[2], "due_date": r[3],
                "total_amount": r[4] or 0, "paid_amount": r[5] or 0,
                "unpaid_amount": r[6] or 0, "status": r[7],
                "overdue": bool(r[3] and r[3] < today),
            }
            for r in unpaid
        ],
    }


@router.get("/analytics/client-trend")
def analytics_client_trend(token: str, client_name: str, year: Optional[int] = None):
    """특정 거래처의 월별 청구 추이"""
    ensure_tables()
    _require_admin(token)

    y = str(year) if year else str(date.today().year)
    with get_connection() as con:
        rows = con.execute("""
            SELECT strftime('%Y-%m', invoice_date) as ym,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid
            FROM billing_invoices
            WHERE client_name LIKE ? AND strftime('%Y', invoice_date) = ?
            GROUP BY ym ORDER BY ym
        """, (f"%{client_name}%", y)).fetchall()

    return [{"month": r[0], "total": r[1] or 0, "paid": r[2] or 0,
             "unpaid": (r[1] or 0) - (r[2] or 0)} for r in rows]


# ─────────────────────────────────────
# API: 상세 조회 (항목 포함)
# ─────────────────────────────────────

@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, token: str):
    ensure_tables()
    _require_admin(token)

    with get_connection() as con:
        inv_cols = [d[0] for d in con.execute("PRAGMA table_info(billing_invoices)").fetchall()]
        inv_row = con.execute("SELECT * FROM billing_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv_row:
            raise HTTPException(status_code=404, detail="인보이스를 찾을 수 없습니다.")

        item_cols = [d[0] for d in con.execute("PRAGMA table_info(billing_invoice_items)").fetchall()]
        item_rows = con.execute(
            "SELECT * FROM billing_invoice_items WHERE invoice_id=? ORDER BY line_no",
            (invoice_id,)
        ).fetchall()

    inv = dict(zip(inv_cols, inv_row))
    inv["items"] = [dict(zip(item_cols, r)) for r in item_rows]
    return inv


# ─────────────────────────────────────
# API: 수정 (납부 처리 / 메모 등)
# ─────────────────────────────────────

class InvoiceUpdate(BaseModel):
    paid_amount: Optional[float] = None
    paid_date: Optional[str] = None
    status: Optional[str] = None
    memo: Optional[str] = None
    confirmed: Optional[bool] = None


@router.put("/{invoice_id}")
def update_invoice(invoice_id: str, token: str, data: InvoiceUpdate):
    ensure_tables()
    user = _require_admin(token)

    fields = {k: v for k, v in data.dict().items() if v is not None}
    if "confirmed" in fields:
        fields["confirmed"] = 1 if fields["confirmed"] else 0

    # 납부액 기반 status 자동 계산
    if "paid_amount" in fields:
        with get_connection() as con:
            row = con.execute("SELECT total_amount FROM billing_invoices WHERE id=?", (invoice_id,)).fetchone()
        if row:
            total = row[0]
            paid = fields["paid_amount"]
            if paid <= 0:
                fields["status"] = "미납"
            elif paid < total:
                fields["status"] = "부분납"
            else:
                fields["status"] = "완납"

    set_clause = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as con:
        con.execute(f"UPDATE billing_invoices SET {set_clause} WHERE id=?", list(fields.values()) + [invoice_id])
        con.commit()

    add_log("인보이스 수정", "billing_invoice", invoice_id, None, user["nickname"],
            f"수정항목: {', '.join(fields.keys())}")
    return {"success": True}


# ─────────────────────────────────────
# API: 빈 항목 일괄 삭제 (total_amount=0, client_name 미상/빈값)
# ─────────────────────────────────────

@router.delete("/cleanup-empty")
def cleanup_empty_invoices(token: str):
    ensure_tables()
    user = _require_admin(token)
    with get_connection() as con:
        rows = con.execute(
            "SELECT id, pdf_filename FROM billing_invoices WHERE total_amount = 0 OR total_amount IS NULL"
        ).fetchall()
        deleted = 0
        for row in rows:
            inv_id, pdf_name = row
            if pdf_name:
                p = UPLOAD_DIR / pdf_name
                p.unlink(missing_ok=True)
            con.execute("DELETE FROM billing_invoice_items WHERE invoice_id=?", (inv_id,))
            con.execute("DELETE FROM billing_invoices WHERE id=?", (inv_id,))
            deleted += 1
        con.commit()
    add_log("빈 항목 일괄 삭제", "billing_invoice", None, None, user["nickname"],
            f"{deleted}개 삭제")
    return {"success": True, "deleted": deleted}


# ─────────────────────────────────────
# API: 삭제
# ─────────────────────────────────────

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: str, token: str):
    ensure_tables()
    user = _require_admin(token)

    with get_connection() as con:
        row = con.execute("SELECT pdf_filename, client_name FROM billing_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="인보이스를 찾을 수 없습니다.")
        if row[0]:
            p = UPLOAD_DIR / row[0]
            p.unlink(missing_ok=True)
        con.execute("DELETE FROM billing_invoice_items WHERE invoice_id=?", (invoice_id,))
        con.execute("DELETE FROM billing_invoices WHERE id=?", (invoice_id,))
        con.commit()

    add_log("인보이스 삭제", "billing_invoice", invoice_id, row[1], user["nickname"], "")
    return {"success": True}
