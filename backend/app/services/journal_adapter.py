"""일지 저장·조회 어댑터. 기존 bot_tools 본체를 호출만 한다."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend.app.services.bot_intent import AMOUNT_TYPES, extract_korean_amount, journal_fields_only
from logic.db import get_connection

logger = logging.getLogger(__name__)

SEOUL = ZoneInfo("Asia/Seoul")
SAFE_ERROR = "처리하지 못했어요. 업체, 작업, 단가를 다시 알려주세요."
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATH_RE = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s]{2,}")
SQL_MARKERS = (
    "select ", "insert ", "update ", "delete from", "sqlite", "traceback",
    "operationalerror", "integrityerror", "no such table", "billing.db",
)
KOREAN_QTY = {
    "하나": 1, "한개": 1, "한건": 1, "한": 1,
    "둘": 2, "두개": 2, "두건": 2, "두": 2,
    "셋": 3, "세개": 3, "세건": 3, "세": 3,
    "넷": 4, "네개": 4, "네건": 4, "네": 4,
    "다섯": 5, "다섯개": 5, "다섯건": 5,
}
QTY_DIGIT_RE = re.compile(r"(\d+)\s*(?:건|개|장|박스)?")
TOTAL_HINT_RE = re.compile(r"총\s*(?:액|합|합계)?")


def seoul_today() -> str:
    return datetime.now(SEOUL).strftime("%Y-%m-%d")


def seoul_yesterday() -> str:
    return (datetime.now(SEOUL) - timedelta(days=1)).strftime("%Y-%m-%d")


def sanitize_user_error(err: Any, fallback: str = SAFE_ERROR) -> str:
    text = str(err or "").strip()
    if not text:
        return fallback
    lowered = text.lower()
    if any(marker in lowered for marker in SQL_MARKERS):
        return fallback
    if PATH_RE.search(text):
        return fallback
    if len(text) > 120:
        return fallback
    return text


def parse_iso_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not DATE_RE.fullmatch(raw):
        return None
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None
    return raw


def resolve_vendor(name: str) -> Tuple[Optional[str], List[str]]:
    vendor = (name or "").strip()
    if not vendor:
        return None, []
    vendor_normalized = vendor.replace(" ", "").replace("　", "")
    with get_connection() as con:
        row = con.execute(
            """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
               UNION
               SELECT vendor FROM aliases WHERE LOWER(alias) = LOWER(?)""",
            (vendor, vendor),
        ).fetchone()
        if not row:
            row = con.execute(
                """SELECT vendor FROM vendors
                   WHERE REPLACE(LOWER(vendor), ' ', '') = LOWER(?)
                   UNION
                   SELECT vendor FROM aliases
                   WHERE REPLACE(LOWER(alias), ' ', '') = LOWER(?)""",
                (vendor_normalized, vendor_normalized),
            ).fetchone()
        if not row:
            partial = con.execute(
                """SELECT DISTINCT vendor FROM vendors
                   WHERE vendor LIKE ? OR vendor LIKE ?
                   UNION
                   SELECT DISTINCT vendor FROM aliases
                   WHERE alias LIKE ? OR alias LIKE ?""",
                (f"%{vendor}%", f"%{vendor_normalized}%", f"%{vendor}%", f"%{vendor_normalized}%"),
            ).fetchall()
            if len(partial) == 1:
                row = partial[0]
            elif len(partial) > 1:
                return None, [r[0] for r in partial[:5] if r and r[0]]
        if row:
            return row[0], []
        similar = con.execute(
            """SELECT vendor FROM vendors
               WHERE vendor LIKE ? OR vendor LIKE ?
               LIMIT 5""",
            (f"%{vendor}%", f"%{vendor[:2]}%"),
        ).fetchall()
    return None, [r[0] for r in similar if r and r[0]]


def apply_amount_type(entry: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """총액이면 수량으로 나눠 단가를 만든다. 나누어떨어지지 않으면 질문한다."""
    out = dict(entry)
    amount_type = out.get("amount_type") or "unknown"
    if amount_type not in AMOUNT_TYPES:
        amount_type = "unknown"
        out["amount_type"] = amount_type
    total = out.get("total_amount")
    qty = out.get("qty") or 1
    unit = out.get("unit_price")
    if amount_type == "total" and total:
        try:
            total_i = int(total)
            qty_i = int(qty)
        except (TypeError, ValueError):
            return None, "수량과 총액을 숫자로 알려주세요."
        if qty_i <= 0 or total_i <= 0:
            return None, "수량과 총액은 0보다 커야 해요."
        if total_i % qty_i != 0:
            return None, "ask_unit_from_total"
        out["unit_price"] = total_i // qty_i
        return out, None
    if amount_type == "unknown" and total and not unit:
        return out, "ask_amount_type"
    if amount_type == "unit" and unit:
        return out, None
    if unit:
        out["amount_type"] = "unit"
    return out, None


def validate_journal_entry(entry: Dict[str, Any], *, require_complete: bool = True) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    cleaned = journal_fields_only(entry)
    if "qty" in cleaned:
        try:
            qty = int(cleaned["qty"])
        except (TypeError, ValueError):
            return False, cleaned, "수량은 0보다 큰 숫자여야 해요."
        if qty <= 0:
            return False, cleaned, "수량은 0보다 커야 해요."
        cleaned["qty"] = qty
    if "unit_price" in cleaned:
        try:
            price = int(cleaned["unit_price"])
        except (TypeError, ValueError):
            return False, cleaned, "단가는 0보다 큰 숫자여야 해요."
        if price <= 0:
            return False, cleaned, "단가는 0보다 커야 해요."
        cleaned["unit_price"] = price
    if "total_amount" in cleaned:
        try:
            total = int(cleaned["total_amount"])
        except (TypeError, ValueError):
            return False, cleaned, "총액은 0보다 큰 숫자여야 해요."
        if total <= 0:
            return False, cleaned, "총액은 0보다 커야 해요."
        cleaned["total_amount"] = total
    if cleaned.get("date"):
        parsed = parse_iso_date(cleaned["date"])
        if not parsed:
            return False, cleaned, "날짜는 실제 있는 YYYY-MM-DD 형식으로 알려주세요."
        cleaned["date"] = parsed
    if cleaned.get("vendor"):
        resolved, similar = resolve_vendor(str(cleaned["vendor"]))
        if not resolved:
            hint = f" 비슷한 업체: {', '.join(similar)}" if similar else ""
            return False, {**cleaned, "similar_vendors": similar}, f"'{cleaned['vendor']}'은(는) 등록되지 않은 업체입니다.{hint}"
        cleaned["vendor"] = resolved
    priced, amount_err = apply_amount_type(cleaned)
    if amount_err == "ask_unit_from_total":
        return False, cleaned, "ask_unit_from_total"
    if amount_err == "ask_amount_type":
        return False, cleaned, "ask_amount_type"
    if amount_err:
        return False, cleaned, amount_err
    if priced:
        cleaned = priced
    if require_complete:
        missing = [k for k in ("vendor", "work_type", "unit_price") if cleaned.get(k) in (None, "")]
        if missing:
            return False, cleaned, "missing:" + ",".join(missing)
    return True, cleaned, None


def missing_required(entry: Dict[str, Any]) -> List[str]:
    return [k for k in ("vendor", "work_type", "unit_price") if entry.get(k) in (None, "")]


def lookup_price_history(vendor: str, work_type: str) -> Dict[str, Any]:
    """기존 조회 본체를 호출한 뒤, 작업명이 정확히 하나일 때만 제안한다."""
    from backend.app.services.bot_tools import _lookup_price_from_history

    work = (work_type or "").strip()
    vend = (vendor or "").strip()
    if not work:
        return {"success": False, "found": False, "ambiguous": False, "message": "작업종류가 필요합니다."}
    resolved, _ = resolve_vendor(vend) if vend else (vend, [])
    resolved = resolved or vend
    with get_connection() as con:
        names = con.execute(
            """
            SELECT DISTINCT 분류 FROM work_log
            WHERE 분류 IS NOT NULL AND TRIM(분류) != ''
              AND (분류 = ? OR 분류 LIKE ?)
            ORDER BY 분류
            LIMIT 8
            """,
            (work, f"%{work}%"),
        ).fetchall()
    work_names = [r[0] for r in names if r and r[0]]
    exact = [n for n in work_names if n == work]
    if len(exact) == 1 and len([n for n in work_names if n != work]) == 0:
        result = _lookup_price_from_history(
            {"vendor": resolved, "work_type": work}, "", ""
        )
        result["ambiguous"] = False
        result["work_candidates"] = exact
        return result
    if len(work_names) > 1:
        return {
            "success": True,
            "found": False,
            "ambiguous": True,
            "work_candidates": work_names[:5],
            "vendor": resolved,
            "work_type": work,
            "message": "작업명이 여러 개라 하나를 골라주세요.",
        }
    if len(work_names) == 1 and work_names[0] != work:
        return {
            "success": True,
            "found": False,
            "ambiguous": True,
            "work_candidates": work_names[:5],
            "vendor": resolved,
            "work_type": work,
            "message": "작업명이 여러 개라 하나를 골라주세요.",
        }
    result = _lookup_price_from_history({"vendor": resolved, "work_type": work}, "", "")
    if result.get("exact_match") and result.get("found"):
        result["ambiguous"] = False
        return result
    result["ambiguous"] = False
    return result


def save_journal_entries(
    entries: List[Dict[str, Any]],
    user_id: str,
    user_name: Optional[str],
    channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    from backend.app.services.bot_tools import _save_work_log
    from backend.app.services.journal_edit import remember_last_saved

    prepared: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for idx, raw in enumerate(entries):
        payload = dict(raw)
        if not payload.get("date"):
            payload["date"] = seoul_today()
        if payload.get("qty") in (None, ""):
            payload["qty"] = 1
        ok, cleaned, err = validate_journal_entry(payload, require_complete=True)
        if not ok:
            failures.append({"index": idx, "error": sanitize_user_error(err), "entry": raw})
            continue
        prepared.append(cleaned)

    if not prepared:
        return {
            "success": False,
            "partial": False,
            "saved_count": 0,
            "failed_count": len(failures),
            "failures": failures,
            "results": [],
            "message": _fail_message(failures),
        }

    saved: List[Dict[str, Any]] = []
    last_id = None
    for idx, item in enumerate(prepared):
        try:
            result = _save_work_log(item, user_id, user_name)
        except Exception as exc:
            logger.exception("journal_save_failed")
            failures.append({"index": idx, "error": SAFE_ERROR, "entry": item})
            continue
        if result.get("success"):
            saved.append(result)
            last_id = result.get("record_id")
        else:
            failures.append({
                "index": idx,
                "error": sanitize_user_error(result.get("error")),
                "entry": item,
                "similar_vendors": result.get("similar_vendors") or [],
            })

    if last_id is not None:
        try:
            remember_last_saved(user_id, channel_id, int(last_id))
        except Exception:
            logger.exception("journal_last_saved_pointer_failed")

    if not saved:
        return {
            "success": False,
            "partial": False,
            "saved_count": 0,
            "failed_count": len(failures),
            "failures": failures,
            "results": [],
            "message": _fail_message(failures),
        }
    if failures:
        return {
            "success": False,
            "partial": True,
            "saved_count": len(saved),
            "failed_count": len(failures),
            "failures": failures,
            "results": saved,
            "record_id": last_id,
            "message": (
                f"{len(saved)}건 저장, {len(failures)}건 실패. "
                + _fail_message(failures)
            ),
        }
    total = sum(int((r.get("data") or {}).get("total") or 0) for r in saved)
    if len(saved) == 1:
        message = saved[0].get("message") or "저장했어요."
    else:
        message = f"{len(saved)}건 저장했어요. 총 {total:,}원"
    return {
        "success": True,
        "partial": False,
        "saved_count": len(saved),
        "failed_count": 0,
        "failures": [],
        "results": saved,
        "record_id": last_id,
        "message": message,
    }


def _fail_message(failures: List[Dict[str, Any]]) -> str:
    if not failures:
        return SAFE_ERROR
    parts = []
    for item in failures[:5]:
        err = sanitize_user_error(item.get("error"))
        parts.append(err)
    return " / ".join(parts) if parts else SAFE_ERROR


def extract_journal_qty(text: str) -> Optional[int]:
    raw = (text or "").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw)
    for word, value in KOREAN_QTY.items():
        if word in compact:
            return value
    m = QTY_DIGIT_RE.search(raw)
    if m:
        qty = int(m.group(1))
        if qty > 0:
            return qty
    return None


def extract_journal_fields_local(text: str) -> Dict[str, Any]:
    """확실한 로컬 파싱만. 명령 동의어 목록을 늘리지 않는다."""
    raw = (text or "").strip()
    if not raw:
        return {}
    fields: Dict[str, Any] = {}
    amount = extract_korean_amount(raw)
    if amount is not None:
        fields["unit_price"] = amount
        fields["amount_type"] = "total" if TOTAL_HINT_RE.search(raw) else "unit"
        if fields["amount_type"] == "total":
            fields["total_amount"] = amount
            fields.pop("unit_price", None)
    qty = extract_journal_qty(raw)
    if qty:
        fields["qty"] = qty
    if "어제" in raw:
        fields["date"] = seoul_yesterday()
    elif "오늘" in raw:
        fields["date"] = seoul_today()
    leftover = raw
    leftover = re.sub(r"(?:총\s*)?(?:\d+(?:\.\d+)?)\s*만\s*원?", " ", leftover)
    leftover = re.sub(r"(?:\d+(?:\.\d+)?)\s*천\s*원?", " ", leftover)
    leftover = re.sub(r"(?:\d{1,3}(?:,\d{3})+|\d+)\s*원", " ", leftover)
    leftover = re.sub(r"(?:하나|둘|셋|넷|다섯|\d+)\s*(?:건|개|장|박스)?", " ", leftover)
    leftover = leftover.replace("어제", " ").replace("오늘", " ").replace("총", " ")
    leftover = re.sub(r"\s+", " ", leftover).strip()
    if leftover:
        tokens = leftover.split()
        for i in range(len(tokens), 0, -1):
            cand = "".join(tokens[:i])
            spaced = " ".join(tokens[:i])
            for name in (spaced, cand):
                resolved, similar = resolve_vendor(name)
                if resolved and not similar:
                    fields["vendor"] = resolved
                    leftover = leftover[len(spaced):].strip() if leftover.startswith(spaced) else leftover[len(cand):].strip()
                    break
            else:
                continue
            break
        work = leftover.strip(" ,./")
        if work:
            fields["work_type"] = work
    return journal_fields_only(fields)


def ensure_event_table() -> None:
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS journal_webhook_events (
                event_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                created_at TEXT,
                result_summary TEXT
            )
            """
        )
        con.commit()


def get_processed_event(event_id: Optional[str]) -> Optional[str]:
    if not event_id:
        return None
    ensure_event_table()
    with get_connection() as con:
        row = con.execute(
            "SELECT result_summary FROM journal_webhook_events WHERE event_id = ?",
            (str(event_id),),
        ).fetchone()
    return row[0] if row else None


def remember_processed_event(
    event_id: Optional[str],
    user_id: str,
    channel_id: Optional[str],
    summary: str,
) -> None:
    if not event_id:
        return
    ensure_event_table()
    uid = (user_id or "").strip()
    cid = (channel_id or "").strip() or uid
    with get_connection() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO journal_webhook_events
            (event_id, user_id, channel_id, created_at, result_summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(event_id), uid, cid, datetime.now(SEOUL).isoformat(), (summary or "")[:300]),
        )
        con.commit()
