"""Repair-log search, stats, save, price, barcode, and catalog tools."""
import re
from typing import Any, Dict, List, Optional

from logic.db import get_connection

from .common import (
    _clamp_limit,
    _clamp_offset,
    _fetch_allowed,
    _stats_group_order,
    logger,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPAIR_GROUP_COLS = {"vendor": "업체명", "work_type": "작업", "worker": "작성자", "product": "제품명"}

def _safe_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text if _DATE_RE.match(text) else None

def _search_repair_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """저장된 수선일지 조회. SELECT allowlist만 사용한다."""
    try:
        conditions = ["1=1"]
        params: List[Any] = []
        mapping = {
            "vendor": "업체명",
            "product": "제품명",
            "work_type": "작업",
            "defect": "불량명",
            "worker": "작성자",
            "barcode": "바코드",
            "remark": "비고",
        }
        for key, col in mapping.items():
            value = (args.get(key) or "").strip()
            if value:
                conditions.append(f"{col} LIKE ?")
                params.append(f"%{value}%")
        start = _safe_date(args.get("start_date"))
        end = _safe_date(args.get("end_date"))
        if start:
            conditions.append("날짜 >= ?")
            params.append(start)
        if end:
            conditions.append("날짜 <= ?")
            params.append(end)
        limit = _clamp_limit(args.get("limit"))
        with get_connection() as con:
            rows = con.execute(
                f"""SELECT id, 날짜, 업체명, 제품명, 작업, 수량, 비용, 저장시간, 작성자, 불량명, 바코드, 비고
                    FROM repair_work_log
                    WHERE {' AND '.join(conditions)}
                    ORDER BY id DESC LIMIT ?""",
                params + [limit],
            ).fetchall()
        out = []
        for r in rows:
            saved = str(r[7])[:10] if r[7] else (str(r[1])[:10] if r[1] else "-")
            out.append({
                "id": r[0],
                "date": r[1] or saved,
                "vendor": r[2],
                "product": r[3],
                "work_type": r[4],
                "qty": r[5],
                "unit_price": r[6],
                "worker": r[8],
                "defect": r[9],
                "barcode": r[10],
                "remark": r[11],
            })
        return {"success": True, "count": len(out), "rows": out}
    except Exception:
        logger.exception("search_repair_logs_failed")
        return {"success": False, "error": "조회 중 문제가 생겼어요."}

def _get_repair_log_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    try:
        conditions = ["1=1"]
        params: List[Any] = []
        mapping = {
            "vendor": "업체명",
            "product": "제품명",
            "work_type": "작업",
            "defect": "불량명",
            "worker": "작성자",
            "barcode": "바코드",
            "remark": "비고",
        }
        for key, col in mapping.items():
            value = (args.get(key) or "").strip()
            if value:
                conditions.append(f"{col} LIKE ?")
                params.append(f"%{value}%")
        start = _safe_date(args.get("start_date"))
        end = _safe_date(args.get("end_date"))
        if start:
            conditions.append("날짜 >= ?")
            params.append(start)
        if end:
            conditions.append("날짜 <= ?")
            params.append(end)
        where = " AND ".join(conditions)
        with get_connection() as con:
            row = con.execute(
                f"""SELECT COUNT(*), COALESCE(SUM(수량),0), COALESCE(SUM(비용),0)
                    FROM repair_work_log WHERE {where}""",
                params,
            ).fetchone()
            group_col = _REPAIR_GROUP_COLS.get(str(args.get("group_by") or ""))
            groups = []
            if group_col:
                order_expr, sort_dir, group_limit = _stats_group_order(args, "수량", "비용")
                grouped = con.execute(
                    f"""SELECT {group_col}, COUNT(*), COALESCE(SUM(수량),0), COALESCE(SUM(비용),0)
                        FROM repair_work_log WHERE {where} AND {group_col} IS NOT NULL
                        GROUP BY {group_col} ORDER BY {order_expr} {sort_dir} LIMIT ?""",
                    (*params, group_limit),
                ).fetchall()
                groups = [{"name": g[0], "count": g[1], "qty": g[2], "amount": g[3]} for g in grouped]
        return {
            "success": True,
            "count": int(row[0] or 0),
            "qty": int(row[1] or 0),
            "total": int(row[2] or 0),
            "groups": groups,
        }
    except Exception:
        logger.exception("repair_log_stats_failed")
        return {"success": False, "error": "조회 중 문제가 생겼어요."}

def _save_repair_log(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.services.repair_bot import save_repair_from_tool
    return save_repair_from_tool(args, user_id, user_name)

def _lookup_repair_price(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.services import repair_catalog
    return repair_catalog.lookup_repair_price(
        args.get("vendor"), args.get("work_type"), args.get("product"),
    )

def _lookup_repair_barcode_tool(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.api.repair_log import _lookup_barcode, ensure_repair_tables
    ensure_repair_tables()
    code = (args.get("barcode") or "").strip()
    with get_connection() as con:
        found = _lookup_barcode(con, code)
    if not found:
        return {"success": False, "found": False, "message": "등록 안 된 바코드예요."}
    return {"success": True, "found": True, **found}

def _lookup_repair_catalog(args: Dict, user_id: str, user_name: str) -> Dict:
    """조회모드 전용. 카탈로그 테이블을 읽기만 하고 생성·시드하지 않는다."""
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    with get_connection() as con:
        works = _fetch_allowed(
            con, "repair_work_type", ["작업명", "기본비용", "별칭"],
            order_by="작업명", limit=limit, offset=offset,
        )
        defects = _fetch_allowed(
            con, "repair_defect", ["불량명", "별칭"],
            order_by="불량명", limit=limit, offset=offset,
        )
    result = {
        "success": True,
        "work_types": works["rows"],
        "defects": defects["rows"],
        "truncated": bool(works.get("truncated") or defects.get("truncated")),
        "limit": limit,
        "offset": offset,
    }
    if works.get("missing") or defects.get("missing"):
        result["message"] = "수선 카탈로그 테이블이 없어 조회하지 않았습니다."
    return result
