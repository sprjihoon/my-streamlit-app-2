"""Shared limits, SQL helpers, and DB context for bot tools."""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from logic.db import get_connection

logger = logging.getLogger("backend.app.services.bot_tools")

QUERY_DEFAULT_LIMIT = 20
QUERY_MAX_LIMIT = 50
QUERY_ALL_TABLE_LIMIT = 15
TRUSTED_EXCEL_UPLOAD = "excel_upload"
_SECRET_KEY_RE = re.compile(
    r"password|passwd|api[_-]?key|secret|token|credential|private[_-]?key|authorization|session|env",
    re.I,
)

def _stats_group_order(args: Dict, qty_col: str, amount_col: str) -> Tuple[str, str, int]:
    qty_expr = {"수량": "COALESCE(SUM(수량),0)"}.get(qty_col, "COALESCE(SUM(수량),0)")
    amount_expr = {
        "합계": "COALESCE(SUM(합계),0)",
        "비용": "COALESCE(SUM(비용),0)",
    }.get(amount_col, "COALESCE(SUM(합계),0)")
    metric = str(args.get("metric") or "quantity")
    order_expr = amount_expr if metric == "amount" else qty_expr
    sort_dir = "ASC" if str(args.get("sort") or "desc").lower() == "asc" else "DESC"
    try:
        limit = int(args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    return order_expr, sort_dir, max(1, min(limit, 50))

def _clamp_limit(value, default: int = QUERY_DEFAULT_LIMIT, maximum: int = QUERY_MAX_LIMIT) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, maximum))


def _clamp_offset(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, n)


def _sql_ident(name: str) -> str:
    return "[" + str(name).replace("]", "") + "]"


def _strip_secrets(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if not _SECRET_KEY_RE.search(str(k))}


def _fetch_allowed(
    con,
    table: str,
    columns: List[str],
    *,
    where: str = "",
    params: tuple = (),
    order_by: Optional[str] = None,
    limit: int = QUERY_DEFAULT_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    allowed_tables = {
        "vendors", "aliases", "out_basic", "out_extra", "shipping_zone",
        "material_rates", "storage_rates", "vendor_storage", "vendor_charges",
        "repair_work_type", "repair_defect",
    }
    if table not in allowed_tables:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset}
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset, "missing": True}
    real_cols = {c[1] for c in con.execute(f"PRAGMA table_info({_sql_ident(table)})")}
    cols = [c for c in columns if c in real_cols and not _SECRET_KEY_RE.search(c)]
    if not cols:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset}
    order_sql = ""
    if order_by and order_by in cols:
        order_sql = f" ORDER BY {_sql_ident(order_by)}"
    sql = f"SELECT {', '.join(_sql_ident(c) for c in cols)} FROM {_sql_ident(table)}"
    if where:
        sql += f" WHERE {where}"
    sql += f"{order_sql} LIMIT ? OFFSET ?"
    rows = con.execute(sql, (*params, limit, offset)).fetchall()
    out_rows = [_strip_secrets(dict(zip(cols, r))) for r in rows]
    return {
        "rows": out_rows,
        "truncated": len(out_rows) >= limit,
        "limit": limit,
        "offset": offset,
    }

def get_db_context_for_ai() -> str:
    """AI에게 제공할 DB 컨텍스트 요약 (작업일지 + 인보이스)"""
    try:
        today = datetime.now()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        month_end = today.strftime("%Y-%m-%d")
        
        with get_connection() as con:
            # 등록 업체
            vendors = [r[0] for r in con.execute(
                "SELECT vendor FROM vendors WHERE active != 'NO' OR active IS NULL ORDER BY vendor LIMIT 15"
            ).fetchall() if r[0]]
            
            # 자주 쓰는 작업종류
            work_types = [r[0] for r in con.execute(
                """SELECT 분류 FROM work_log WHERE 분류 IS NOT NULL
                   GROUP BY 분류 ORDER BY COUNT(*) DESC LIMIT 10"""
            ).fetchall() if r[0]]
            
            # 이번달 작업일지 통계
            stats = con.execute(
                f"SELECT COUNT(*), COALESCE(SUM(합계), 0) FROM work_log WHERE 날짜 BETWEEN ? AND ?",
                (month_start, month_end)
            ).fetchone()
            
            # 인보이스 총계
            inv_total = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices"
            ).fetchone()
            
            # 이번달 인보이스
            inv_month = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices WHERE created_at >= ?",
                (month_start,)
            ).fetchone()
            
            # 업체별 인보이스 누적 (상위 5개)
            inv_by_vendor = con.execute(
                """SELECT v.vendor, COUNT(*) as cnt, SUM(i.total_amount) as total
                   FROM invoices i
                   LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                   WHERE v.vendor IS NOT NULL
                   GROUP BY v.vendor ORDER BY total DESC LIMIT 5"""
            ).fetchall()
            
            # 최근 인보이스 3건
            recent_inv = con.execute(
                """SELECT v.vendor, i.total_amount, i.period_from, i.period_to
                   FROM invoices i
                   LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                   ORDER BY i.created_at DESC LIMIT 3"""
            ).fetchall()
        
        repair_ctx = ""
        try:
            from backend.app.services import repair_catalog
            repair_ctx = repair_catalog.catalog_context_for_ai()
        except Exception:
            pass

        # 컨텍스트 구성
        context_lines = [
            "## 현재 DB 정보 (참고용, 특정 기간 조회는 반드시 도구 호출!)",
            f"- 등록 업체: {', '.join(vendors[:10])}{'...' if len(vendors) > 10 else ''}",
            f"- 자주 쓰는 작업: {', '.join(work_types)}",
            f"- 이번달({month_start}~{month_end}) 작업일지: {stats[0]}건, {stats[1]:,}원",
            f"- 오늘: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})",
            "",
            "## 인보이스 정보 (전체 누적, 특정 기간은 get_invoice_stats 호출!)",
            f"- 전체 누적 인보이스: {inv_total[0]}건, 총 {inv_total[1]:,.0f}원",
            "",
            "⚠️ 특정 월/기간 데이터 요청 시: 반드시 get_work_log_stats 또는 get_invoice_stats 호출!",
            "⚠️ 이 컨텍스트 데이터를 특정 기간 답변에 사용하지 마세요!",
        ]
        if repair_ctx:
            context_lines.extend(["", "## 수선 마스터 (수선 건만. 하차/입고는 작업일지)", repair_ctx])
        
        return "\n".join(context_lines)
    except Exception as e:
        return f"## DB 정보 로드 오류: {e}"
