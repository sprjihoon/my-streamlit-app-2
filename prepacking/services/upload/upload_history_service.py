from __future__ import annotations

from prepacking.database import get_pp_connection

_UPLOAD_COLS = """upload_id, file_name, file_version, uploaded_at, uploaded_by,
                  data_start_date, data_end_date, row_count, applied_yn, note,
                  upload_status, skipped_count, total_count, error_message"""


def list_uploads(supplier_name: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 500))
    with get_pp_connection() as con:
        if supplier_name:
            cur = con.execute(
                f"""
                SELECT DISTINCT u.upload_id, u.file_name, u.file_version, u.uploaded_at,
                       u.uploaded_by, u.data_start_date, u.data_end_date, u.row_count,
                       u.applied_yn, u.note,
                       u.upload_status, u.skipped_count, u.total_count, u.error_message
                FROM pp_upload_files u
                LEFT JOIN pp_shipping_stats s ON s.upload_id = u.upload_id
                WHERE TRIM(s.supplier_name) = TRIM(?)
                   OR u.upload_status = 'processing'
                ORDER BY u.upload_id DESC
                LIMIT ?
                """,
                (supplier_name.strip(), limit),
            )
        else:
            cur = con.execute(
                f"""
                SELECT {_UPLOAD_COLS}
                FROM pp_upload_files
                ORDER BY upload_id DESC
                LIMIT ?
                """,
                (limit,),
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_upload_detail(upload_id: int) -> dict | None:
    with get_pp_connection() as con:
        cur = con.execute(
            f"""
            SELECT {_UPLOAD_COLS}
            FROM pp_upload_files
            WHERE upload_id = ?
            """,
            (int(upload_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def delete_upload(upload_id: int) -> bool:
    uid = int(upload_id)
    with get_pp_connection() as con:
        con.execute("DELETE FROM pp_shipping_stats WHERE upload_id = ?", (uid,))
        cur = con.execute("DELETE FROM pp_upload_files WHERE upload_id = ?", (uid,))
        con.commit()
        return cur.rowcount > 0


def mark_upload_applied(upload_id: int) -> bool:
    uid = int(upload_id)
    with get_pp_connection() as con:
        cur = con.execute(
            "UPDATE pp_upload_files SET applied_yn = 1 WHERE upload_id = ?",
            (uid,),
        )
        con.commit()
        return cur.rowcount > 0
