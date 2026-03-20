from __future__ import annotations

from prepacking.common.enums import ExceptionType
from prepacking.database import ensure_pp_tables, get_pp_connection


def get_active_exceptions(supplier_name: str) -> list[dict]:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT exception_id, supplier_name, target_type, target_code, target_name,
                   exception_type, exception_reason, start_date, end_date, is_active,
                   created_by, created_at, memo
            FROM pp_exceptions
            WHERE supplier_name = ? AND is_active = 1
            ORDER BY exception_id DESC
            """,
            (supplier_name,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _in_date_window(target_date: str, start_date: str | None, end_date: str | None) -> bool:
    if start_date and str(start_date).strip() and target_date < str(start_date).strip():
        return False
    if end_date and str(end_date).strip() and target_date > str(end_date).strip():
        return False
    return True


def is_excluded(supplier_name: str, target_code: str, target_date: str) -> bool:
    ensure_pp_tables()
    tc = (target_code or "").strip()
    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT start_date, end_date
            FROM pp_exceptions
            WHERE supplier_name = ?
              AND is_active = 1
              AND target_code = ?
            """,
            (supplier_name, tc),
        )
        for start_date, end_date in cur.fetchall():
            if _in_date_window(target_date, start_date, end_date):
                return True
    return False


def add_exception(
    supplier_name: str,
    target_type: str,
    target_code: str,
    target_name: str,
    exception_type: str,
    reason: str,
    start_date: str | None = None,
    end_date: str | None = None,
    created_by: str = "",
) -> int:
    ensure_pp_tables()
    et = exception_type
    if et not in {e.value for e in ExceptionType}:
        et = ExceptionType.EXCLUDED.value
    with get_pp_connection() as con:
        cur = con.execute(
            """
            INSERT INTO pp_exceptions (
                supplier_name, target_type, target_code, target_name,
                exception_type, exception_reason, start_date, end_date,
                is_active, created_by, memo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, '')
            """,
            (
                supplier_name,
                target_type,
                target_code,
                target_name,
                et,
                reason,
                start_date,
                end_date,
                created_by,
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def remove_exception(exception_id: int) -> bool:
    ensure_pp_tables()
    with get_pp_connection() as con:
        cur = con.execute(
            "UPDATE pp_exceptions SET is_active = 0 WHERE exception_id = ?",
            (int(exception_id),),
        )
        con.commit()
        return cur.rowcount > 0
