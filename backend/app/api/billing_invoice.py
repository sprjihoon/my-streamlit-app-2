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

[파싱 규칙 - 반드시 준수]
1. PDF 텍스트는 멀티컬럼 레이아웃 때문에 순서가 뒤섞여 있을 수 있어. No 순서대로 품명을 매핑해.
2. 금액이 음수(차감)인 경우 그대로 음수로 반환해.
3. 숫자 앞의 행번호(1, 2, 3...)를 금액에 포함시키지 마. 예: 행번호 1, 금액 4,104,420 → amount: 4104420 (14104420 아님).
4. 모든 items의 amount 합계(양수)가 supply_amount(공급가액)와 일치하는지 반드시 확인해. 일치하지 않으면 누락된 항목이 있는지 다시 점검해.
5. 소계/합계 행은 items에 포함하지 마. 개별 항목만 포함해.
6. 텍스트가 잘려 있거나 불명확한 금액은 주변 맥락(단가×수량)으로 검증해.

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


def _fix_pdf_number_spaces(text: str) -> str:
    """pdfplumber가 큰 숫자 안에 삽입하는 공백을 제거합니다.
    예: '1 4,344,660' → '14,344,660'
    패턴: 숫자(1-2자리) + 공백 + 숫자·쉼표 연속
    """
    import re
    # 반복 적용 (여러 번 삽입된 경우 처리)
    for _ in range(5):
        fixed = re.sub(r'(\d{1,2}) (\d{3}[,\d]*)', r'\1\2', text)
        if fixed == text:
            break
        text = fixed
    return text


def _regex_extract_totals(text: str) -> dict:
    """regex로 공급가액·부가세·청구합계를 직접 추출 (pdfplumber 공백 처리 포함)."""
    import re

    def _clean(raw: str) -> int | None:
        val = re.sub(r'[\s,]', '', raw)
        return int(val) if val.isdigit() and int(val) > 0 else None

    result = {}
    patterns = {
        "total_amount": [
            r'청구금액\s*[₩￦]\s*([\d ,]+)',
            r'청\s*구\s*금\s*액\s*[₩￦]\s*([\d ,]+)',
        ],
        "supply_amount": [
            r'공급가액\s*[₩￦]?\s*([\d ,]+)',
            r'합계\s*금\s*액\s*[₩￦]\s*([\d ,]+)',
        ],
        "vat_amount": [
            r'부가세\s*[₩￦]?\s*([\d ,]+)',
            r'세\s*액\s*[₩￦]?\s*([\d ,]+)',
        ],
    }
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text)
            if m:
                val = _clean(m.group(1))
                if val:
                    result[key] = val
                    break
    return result


def _gpt_parse(client, text: str, extra_messages: list | None = None) -> dict:
    """GPT 호출 + JSON 추출 헬퍼."""
    messages = [
        {"role": "system", "content": GPT_SYSTEM_PROMPT},
        {"role": "user", "content": f"아래 PDF 텍스트를 분석해:\n\n{text}"},
    ]
    if extra_messages:
        messages.extend(extra_messages)
    resp = client.chat.completions.create(
        model="gpt-4o", messages=messages, temperature=0, max_tokens=4000,
    )
    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw), resp.choices[0].message.content


def _parse_pdf_text(text: str) -> dict:
    """
    2중 파싱 검증:
      1단계) regex (윈도우 프로그램 동일 로직) → 업체명·합계금액 추출 (신뢰도 최고)
      2단계) GPT → 전체 구조 파싱 (items 상세 포함)
      3단계) 비교 교정 → GPT 금액이 regex와 다르면 regex 값으로 덮어씀
             items 합계가 supply_amount와 1% 이상 차이 → GPT 재검토 요청
    """
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # ── 1단계: regex 파싱 (pdfplumber 공백 정규화 포함) ──────────
    cleaned_text = _fix_pdf_number_spaces(text)
    regex_result = _regex_extract_totals(cleaned_text)
    r_total   = regex_result.get("total_amount")
    r_supply  = regex_result.get("supply_amount")
    r_vat     = regex_result.get("vat_amount")

    # ── 2단계: GPT 파싱 (정규화된 텍스트 전달) ───────────────────
    parsed, gpt_raw = _gpt_parse(client, cleaned_text)

    # ── 3단계-A: GPT 합계 vs regex 합계 비교 교정 ─────────────────
    corrections = []
    if r_total and parsed.get("total_amount") and abs(parsed["total_amount"] - r_total) > 100:
        corrections.append(
            f"total_amount: GPT={parsed['total_amount']:,.0f} → regex={r_total:,.0f}"
        )
        parsed["total_amount"] = r_total
    elif r_total and not parsed.get("total_amount"):
        parsed["total_amount"] = r_total

    if r_supply and parsed.get("supply_amount") and abs(parsed["supply_amount"] - r_supply) > 100:
        corrections.append(
            f"supply_amount: GPT={parsed['supply_amount']:,.0f} → regex={r_supply:,.0f}"
        )
        parsed["supply_amount"] = r_supply
    elif r_supply and not parsed.get("supply_amount"):
        parsed["supply_amount"] = r_supply

    if r_vat and parsed.get("vat_amount") and abs(parsed["vat_amount"] - r_vat) > 100:
        parsed["vat_amount"] = r_vat
    elif r_vat and not parsed.get("vat_amount"):
        parsed["vat_amount"] = r_vat

    if corrections:
        parsed["_regex_corrections"] = corrections

    # ── 3단계-B: items 합계 vs supply_amount 검증 → 차이 시 재파싱 ─
    supply = parsed.get("supply_amount") or 0
    items = parsed.get("items", [])
    items_sum = sum(it.get("amount", 0) or 0 for it in items if (it.get("amount") or 0) > 0)

    if supply > 0 and abs(items_sum - supply) / supply > 0.01:
        verify_prompt = (
            f"[regex 검증 결과]\n"
            f"  청구합계(regex): {r_total:,.0f}원\n"
            f"  공급가액(regex): {r_supply:,.0f}원\n\n"
            f"[GPT 파싱 결과]\n"
            f"  items 합계: {items_sum:,.0f}원\n"
            f"  공급가액: {supply:,.0f}원\n"
            f"  차이: {items_sum - supply:,.0f}원\n\n"
            f"items 합계가 공급가액과 일치하지 않습니다. "
            f"PDF를 다시 꼼꼼히 확인해 누락된 항목을 추가하거나 잘못된 금액을 수정해주세요. "
            f"특히 행번호(1, 2, 3...)가 금액 앞에 붙어 있는지 확인하세요. "
            f"수정된 전체 JSON을 반환하세요."
        )
        try:
            parsed2, _ = _gpt_parse(client, cleaned_text, extra_messages=[
                {"role": "assistant", "content": gpt_raw},
                {"role": "user", "content": verify_prompt},
            ])
            items2 = parsed2.get("items", [])
            items_sum2 = sum(it.get("amount", 0) or 0 for it in items2 if (it.get("amount") or 0) > 0)
            if abs(items_sum2 - supply) < abs(items_sum - supply):
                # 재파싱이 더 정확 → items만 교체 (합계는 이미 regex로 고정됨)
                parsed["items"] = items2
                parsed["_reparse_applied"] = True
        except Exception:
            pass

    # ── 최종 경고 (재파싱 후에도 차이 남은 경우) ──────────────────
    final_items = parsed.get("items", [])
    final_sum = sum(it.get("amount", 0) or 0 for it in final_items if (it.get("amount") or 0) > 0)
    final_supply = parsed.get("supply_amount") or 0
    if final_supply > 0 and abs(final_sum - final_supply) > 100:
        parsed["_parse_warning"] = (
            f"항목합계({final_sum:,.0f})와 공급가액({final_supply:,.0f}) 차이: "
            f"{abs(final_sum - final_supply):,.0f}원 — 항목을 직접 확인하세요"
        )

    return parsed


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

    # GPT 파싱 완료 후 즉시 파일 삭제 (정보만 DB에 저장)
    pdf_path.unlink(missing_ok=True)

    # 중복 방지: 같은 (거래처, 서비스월, 청구합계) 이미 존재하면 차단
    client_name_parsed = parsed.get("client_name", "미상")
    service_month_parsed = parsed.get("service_month")
    total_amount_parsed = parsed.get("total_amount", 0)
    with get_connection() as con:
        existing = con.execute("""
            SELECT id FROM billing_invoices
            WHERE client_name = ? AND service_month = ? AND total_amount = ?
            LIMIT 1
        """, (client_name_parsed, service_month_parsed, total_amount_parsed)).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"이미 동일한 인보이스가 존재합니다: {client_name_parsed} / {service_month_parsed} / {total_amount_parsed:,.0f}원 (ID: {existing[0][:8]}...)"
        )

    # DB 저장
    items = parsed.pop("items", [])
    invoice_id = pdf_id

    with get_connection() as con:
        con.execute("""
            INSERT INTO billing_invoices
              (id, invoice_no, client_name, invoice_date, due_date, service_month,
               subject, supply_amount, vat_amount, total_amount,
               paid_amount, status,
               bank_name, account_holder, account_number,
               pdf_filename, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            parsed.get("total_amount", 0),  # 기본값: 완납 (paid_amount = total_amount)
            "완납",
            parsed.get("bank_name"),
            parsed.get("account_holder"),
            parsed.get("account_number"),
            None,
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
    if year and month:
        service_m = f"{year}-{str(month).zfill(2)}"
        query += " AND (service_month = ? OR (service_month IS NULL AND strftime('%Y-%m', COALESCE(invoice_date, created_at)) = ?))"
        params.extend([service_m, service_m])
    elif year:
        query += " AND (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', COALESCE(invoice_date, created_at)) = ?))"
        params.extend([f"{year}-%", str(year)])
    if client_name:
        query += " AND client_name LIKE ?"
        params.append(f"%{client_name}%")
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY invoice_date DESC"

    with get_connection() as con:
        rows = con.execute(query, params).fetchall()
        cols = [d[1] for d in con.execute("PRAGMA table_info(billing_invoices)").fetchall()]

    return [dict(zip(cols, r)) for r in rows]


# ─────────────────────────────────────
# API: 분석 (반드시 /{invoice_id} GET 앞에 정의해야 라우팅 충돌 방지)
# ─────────────────────────────────────

def _build_client_category(rows: list) -> list:
    """업체별 카테고리 합산 → {client_name, categories: [{category, total, ratio}]}"""
    from collections import defaultdict
    data: dict = defaultdict(lambda: defaultdict(float))
    for client, cat, total in rows:
        data[client][cat or "기타"] += total or 0
    result = []
    for client, cats in data.items():
        client_total = sum(cats.values())
        result.append({
            "client_name": client,
            "total": client_total,
            "categories": [
                {"category": c, "total": v,
                 "ratio": round(v / client_total * 100, 1) if client_total else 0}
                for c, v in sorted(cats.items(), key=lambda x: -x[1])
            ],
        })
    return sorted(result, key=lambda x: -x["total"])


def _build_monthly_category(rows: list) -> list:
    """월별 카테고리 합산 → [{month, categories: {cat: total}, total}]"""
    from collections import defaultdict, OrderedDict
    data: dict = defaultdict(lambda: defaultdict(float))
    for ym, cat, total in rows:
        data[ym][cat or "기타"] += total or 0
    result = []
    for ym in sorted(data.keys()):
        cats = data[ym]
        month_total = sum(cats.values())
        result.append({
            "month": ym,
            "total": month_total,
            "categories": {c: v for c, v in cats.items()},
        })
    return result


@router.get("/analytics/summary")
def analytics_summary(token: str, year: Optional[int] = None):
    ensure_tables()
    _require_admin(token)

    y = str(year) if year else str(date.today().year)
    today = date.today().isoformat()

    with get_connection() as con:
        # ── 월별 청구 추이 (service_month 기준) ──────────────────
        monthly = con.execute("""
            SELECT COALESCE(service_month, strftime('%Y-%m', invoice_date)) as ym,
                   COUNT(*) as cnt,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid
            FROM billing_invoices
            WHERE (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
            GROUP BY ym ORDER BY ym
        """, (f"{y}-%", y)).fetchall()

        # ── 거래처별 현황 + 납부율 ────────────────────────────────
        by_client = con.execute("""
            SELECT client_name,
                   COUNT(*) as cnt,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid,
                   SUM(total_amount - paid_amount) as unpaid,
                   MIN(invoice_date) as first_inv,
                   MAX(invoice_date) as last_inv
            FROM billing_invoices
            WHERE (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
            GROUP BY client_name ORDER BY total DESC
        """, (f"{y}-%", y)).fetchall()

        # ── 카테고리별 비중 (양수 항목만) ────────────────────────
        by_category = con.execute("""
            SELECT ii.category, SUM(ii.amount) as total, COUNT(*) as cnt
            FROM billing_invoice_items ii
            JOIN billing_invoices inv ON ii.invoice_id = inv.id
            WHERE (inv.service_month LIKE ? OR (inv.service_month IS NULL AND strftime('%Y', inv.invoice_date) = ?))
              AND ii.amount > 0
            GROUP BY ii.category ORDER BY total DESC
        """, (f"{y}-%", y)).fetchall()

        # ── 업체별 카테고리 비용 분해 ─────────────────────────────
        by_client_category = con.execute("""
            SELECT inv.client_name, ii.category, SUM(ii.amount) as total
            FROM billing_invoice_items ii
            JOIN billing_invoices inv ON ii.invoice_id = inv.id
            WHERE (inv.service_month LIKE ? OR (inv.service_month IS NULL AND strftime('%Y', inv.invoice_date) = ?))
              AND ii.amount > 0
            GROUP BY inv.client_name, ii.category
            ORDER BY inv.client_name, total DESC
        """, (f"{y}-%", y)).fetchall()

        # ── 월별 카테고리 추이 ────────────────────────────────────
        monthly_category = con.execute("""
            SELECT COALESCE(inv.service_month, strftime('%Y-%m', inv.invoice_date)) as ym,
                   ii.category, SUM(ii.amount) as total
            FROM billing_invoice_items ii
            JOIN billing_invoices inv ON ii.invoice_id = inv.id
            WHERE (inv.service_month LIKE ? OR (inv.service_month IS NULL AND strftime('%Y', inv.invoice_date) = ?))
              AND ii.amount > 0
            GROUP BY ym, ii.category
            ORDER BY ym, total DESC
        """, (f"{y}-%", y)).fetchall()

        # ── 차감 항목 (음수) ──────────────────────────────────────
        deductions = con.execute("""
            SELECT ii.category, SUM(ii.amount) as total, COUNT(*) as cnt
            FROM billing_invoice_items ii
            JOIN billing_invoices inv ON ii.invoice_id = inv.id
            WHERE (inv.service_month LIKE ? OR (inv.service_month IS NULL AND strftime('%Y', inv.invoice_date) = ?))
              AND ii.amount < 0
            GROUP BY ii.category ORDER BY total ASC
        """, (f"{y}-%", y)).fetchall()

        # ── 미수금 / 연체 현황 ────────────────────────────────────
        unpaid = con.execute("""
            SELECT id, client_name, service_month, invoice_date, due_date,
                   total_amount, paid_amount,
                   (total_amount - paid_amount) as unpaid_amount,
                   status
            FROM billing_invoices
            WHERE status IN ('미납', '부분납')
              AND (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
            ORDER BY due_date ASC
        """, (f"{y}-%", y)).fetchall()

        # ── 납부 소요일 (완납 건만) ───────────────────────────────
        paid_days = con.execute("""
            SELECT client_name,
                   AVG(julianday(paid_date) - julianday(invoice_date)) as avg_days,
                   COUNT(*) as cnt
            FROM billing_invoices
            WHERE status = '완납'
              AND paid_date IS NOT NULL AND invoice_date IS NOT NULL
              AND (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
            GROUP BY client_name ORDER BY avg_days ASC
        """, (f"{y}-%", y)).fetchall()

        # ── 연간 합계 ─────────────────────────────────────────────
        total_row = con.execute("""
            SELECT COUNT(*), SUM(total_amount), SUM(paid_amount),
                   COUNT(CASE WHEN status='완납' THEN 1 END),
                   COUNT(CASE WHEN status='미납' THEN 1 END),
                   COUNT(CASE WHEN status='부분납' THEN 1 END)
            FROM billing_invoices
            WHERE (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
        """, (f"{y}-%", y)).fetchone()

    total_billed = total_row[1] or 0
    total_paid = total_row[2] or 0
    total_cnt = total_row[0] or 0
    payment_rate = round(total_paid / total_billed * 100, 1) if total_billed else 0

    # 월별 전월 대비 증감
    monthly_list = []
    for i, r in enumerate(monthly):
        prev_total = monthly[i - 1][2] or 0 if i > 0 else 0
        cur_total = r[2] or 0
        mom = round((cur_total - prev_total) / prev_total * 100, 1) if prev_total else None
        monthly_list.append({
            "month": r[0], "invoice_count": r[1],
            "total": cur_total, "paid": r[3] or 0,
            "unpaid": cur_total - (r[3] or 0),
            "payment_rate": round((r[3] or 0) / cur_total * 100, 1) if cur_total else 0,
            "mom_change": mom,
        })

    # 카테고리 비중
    cat_total = sum(r[1] or 0 for r in by_category)
    by_category_list = [
        {
            "category": r[0] or "기타",
            "total": r[1] or 0,
            "count": r[2],
            "ratio": round((r[1] or 0) / cat_total * 100, 1) if cat_total else 0,
        }
        for r in by_category
    ]

    # 연체 일수 계산
    unpaid_list = []
    for r in unpaid:
        overdue_days = None
        if r[4] and r[4] < today:
            try:
                from datetime import datetime
                overdue_days = (datetime.fromisoformat(today) - datetime.fromisoformat(r[4])).days
            except Exception:
                pass
        unpaid_list.append({
            "id": r[0], "client_name": r[1],
            "service_month": r[2], "invoice_date": r[3], "due_date": r[4],
            "total_amount": r[5] or 0, "paid_amount": r[6] or 0,
            "unpaid_amount": r[7] or 0, "status": r[8],
            "overdue": bool(r[4] and r[4] < today),
            "overdue_days": overdue_days,
        })

    return {
        "year": y,
        "summary": {
            "invoice_count": total_cnt,
            "total_billed": total_billed,
            "total_paid": total_paid,
            "total_unpaid": total_billed - total_paid,
            "payment_rate": payment_rate,
            "status_breakdown": {
                "완납": total_row[3] or 0,
                "미납": total_row[4] or 0,
                "부분납": total_row[5] or 0,
            },
        },
        "monthly": monthly_list,
        "by_client": [
            {
                "client_name": r[0], "invoice_count": r[1],
                "total": r[2] or 0, "paid": r[3] or 0, "unpaid": r[4] or 0,
                "payment_rate": round((r[3] or 0) / (r[2] or 1) * 100, 1) if r[2] else 0,
                "first_invoice": r[5], "last_invoice": r[6],
            }
            for r in by_client
        ],
        "by_category": by_category_list,
        "deductions": [
            {"category": r[0] or "차감", "total": r[1] or 0, "count": r[2]}
            for r in deductions
        ],
        "unpaid_list": unpaid_list,
        "payment_speed": [
            {"client_name": r[0], "avg_days": round(r[1], 1) if r[1] else None, "count": r[2]}
            for r in paid_days
        ],
        "by_client_category": _build_client_category(by_client_category),
        "monthly_category": _build_monthly_category(monthly_category),
    }


@router.get("/analytics/client-trend")
def analytics_client_trend(token: str, client_name: str, year: Optional[int] = None):
    """특정 거래처의 월별 청구 추이"""
    ensure_tables()
    _require_admin(token)

    y = str(year) if year else str(date.today().year)
    with get_connection() as con:
        rows = con.execute("""
            SELECT COALESCE(service_month, strftime('%Y-%m', invoice_date)) as ym,
                   SUM(total_amount) as total,
                   SUM(paid_amount) as paid
            FROM billing_invoices
            WHERE client_name LIKE ?
              AND (service_month LIKE ? OR (service_month IS NULL AND strftime('%Y', invoice_date) = ?))
            GROUP BY ym ORDER BY ym
        """, (f"%{client_name}%", f"{y}-%", y)).fetchall()

    return [{"month": r[0], "total": r[1] or 0, "paid": r[2] or 0,
             "unpaid": (r[1] or 0) - (r[2] or 0)} for r in rows]


@router.get("/diagnostics")
def diagnostics(token: str):
    """중복 인보이스 진단 (같은 client_name + service_month + total_amount)"""
    ensure_tables()
    _require_admin(token)
    with get_connection() as con:
        total = con.execute("SELECT COUNT(*), SUM(total_amount) FROM billing_invoices").fetchone()
        dups = con.execute("""
            SELECT client_name, service_month, total_amount, COUNT(*) as cnt,
                   GROUP_CONCAT(id, ',') as ids,
                   GROUP_CONCAT(created_at, ',') as dates
            FROM billing_invoices
            GROUP BY client_name, service_month, total_amount
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """).fetchall()
        monthly = con.execute("""
            SELECT COALESCE(service_month, strftime('%Y-%m', invoice_date)) as ym,
                   COUNT(*) as cnt, SUM(total_amount) as total
            FROM billing_invoices
            GROUP BY ym ORDER BY ym DESC LIMIT 12
        """).fetchall()
    return {
        "total_invoices": total[0] or 0,
        "total_amount": total[1] or 0,
        "duplicate_groups": [
            {"client_name": r[0], "service_month": r[1], "total_amount": r[2],
             "count": r[3], "ids": r[4].split(","), "dates": r[5].split(",")}
            for r in dups
        ],
        "monthly_summary": [
            {"month": r[0], "count": r[1], "total": r[2] or 0}
            for r in monthly
        ],
    }


# ─────────────────────────────────────
# API: 상세 조회 (항목 포함)
# ─────────────────────────────────────

@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, token: str):
    ensure_tables()
    _require_admin(token)

    with get_connection() as con:
        inv_cols = [d[1] for d in con.execute("PRAGMA table_info(billing_invoices)").fetchall()]
        inv_row = con.execute("SELECT * FROM billing_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv_row:
            raise HTTPException(status_code=404, detail="인보이스를 찾을 수 없습니다.")

        item_cols = [d[1] for d in con.execute("PRAGMA table_info(billing_invoice_items)").fetchall()]
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

@router.put("/bulk-status")
def bulk_status_update(token: str, status: str = "완납"):
    """전체 인보이스 상태 일괄 변경 (완납 시 paid_amount = total_amount)"""
    ensure_tables()
    user = _require_admin(token)
    with get_connection() as con:
        if status == "완납":
            con.execute("UPDATE billing_invoices SET status='완납', paid_amount=total_amount WHERE status != '완납'")
        else:
            con.execute("UPDATE billing_invoices SET status=? WHERE 1=1", (status,))
        cnt = con.execute("SELECT changes()").fetchone()[0]
        con.commit()
    add_log("상태 일괄변경", "billing_invoice", None, None, user["nickname"], f"{status}으로 {cnt}건 변경")
    return {"success": True, "updated": cnt}


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
            "SELECT id FROM billing_invoices WHERE total_amount = 0 OR total_amount IS NULL"
        ).fetchall()
        deleted = 0
        for row in rows:
            inv_id = row[0]
            con.execute("DELETE FROM billing_invoice_items WHERE invoice_id=?", (inv_id,))
            con.execute("DELETE FROM billing_invoices WHERE id=?", (inv_id,))
            deleted += 1
        con.commit()
    add_log("빈 항목 일괄 삭제", "billing_invoice", None, None, user["nickname"],
            f"{deleted}개 삭제")
    return {"success": True, "deleted": deleted}


@router.delete("/dedup")
def dedup_invoices(token: str):
    """중복 인보이스 제거: 같은 (client_name, service_month, total_amount) 중 최신 1개만 보존"""
    ensure_tables()
    user = _require_admin(token)
    with get_connection() as con:
        dups = con.execute("""
            SELECT client_name, service_month, total_amount, COUNT(*) as cnt
            FROM billing_invoices
            GROUP BY client_name, service_month, total_amount
            HAVING COUNT(*) > 1
        """).fetchall()
        deleted = 0
        for client, smonth, amount, cnt in dups:
            old_rows = con.execute("""
                SELECT id FROM billing_invoices
                WHERE client_name=? AND service_month=? AND total_amount=?
                ORDER BY created_at DESC LIMIT -1 OFFSET 1
            """, (client, smonth, amount)).fetchall()
            for (inv_id,) in old_rows:
                con.execute("DELETE FROM billing_invoice_items WHERE invoice_id=?", (inv_id,))
                con.execute("DELETE FROM billing_invoices WHERE id=?", (inv_id,))
                deleted += 1
        con.commit()
    add_log("중복 인보이스 제거", "billing_invoice", None, None, user["nickname"], f"{deleted}개 삭제")
    return {"success": True, "deleted": deleted}


# ─────────────────────────────────────
# API: 삭제
# ─────────────────────────────────────

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: str, token: str):
    ensure_tables()
    user = _require_admin(token)

    with get_connection() as con:
        row = con.execute("SELECT client_name FROM billing_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="인보이스를 찾을 수 없습니다.")
        con.execute("DELETE FROM billing_invoice_items WHERE invoice_id=?", (invoice_id,))
        con.execute("DELETE FROM billing_invoices WHERE id=?", (invoice_id,))
        con.commit()

    add_log("인보이스 삭제", "billing_invoice", invoice_id, row[0], user["nickname"], "")
    return {"success": True}
