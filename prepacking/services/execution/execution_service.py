from __future__ import annotations

import sqlite3

from prepacking.common.enums import ExecutionStatus, LocationAction
from prepacking.database import ensure_pp_tables, get_pp_connection
from prepacking.services.execution import execution_repository
from prepacking.services.location.location_history_service import record_history
from prepacking.services.location.location_service import update_location_capacity
from prepacking.services.stock.prepack_stock_service import create_stock


def execute_prepacking(
    recommendation_id: int,
    executed_qty: int,
    executed_by: str = "",
    location_code: str = "",
    memo: str = "",
) -> dict:
    ensure_pp_tables()
    if executed_qty <= 0:
        return {}
    with get_pp_connection() as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(
            "SELECT * FROM pp_recommendations WHERE recommendation_id = ?",
            (recommendation_id,),
        )
        rec_row = cur.fetchone()
    if not rec_row:
        return {}
    rec = dict(rec_row)
    pack_unit = int(rec.get("recommended_pack_unit") or 1)
    exec_id = execution_repository.insert_execution(
        {
            "recommendation_id": recommendation_id,
            "supplier_name": rec.get("supplier_name") or "",
            "target_type": rec.get("target_type") or "",
            "target_code": rec.get("target_code") or "",
            "target_name": rec.get("target_name") or "",
            "executed_qty": executed_qty,
            "executed_pack_unit": pack_unit,
            "executed_by": executed_by,
            "execution_status": ExecutionStatus.COMPLETED.value,
            "memo": memo,
        }
    )
    combo = rec.get("combination_key") or rec.get("target_code") or ""
    stock_id = create_stock(
        supplier_name=rec.get("supplier_name") or "",
        target_type=rec.get("target_type") or "",
        target_name=rec.get("target_name") or "",
        combination_key=combo,
        qty=executed_qty,
        location_code=location_code,
        execution_id=exec_id,
        option_name=rec.get("option_name") or "",
    )
    if location_code:
        update_location_capacity(location_code, executed_qty)
    record_history(
        stock_id,
        LocationAction.PUTAWAY.value,
        "",
        location_code,
        executed_qty,
        action_by=executed_by,
        reason="prepack_execute",
        recommendation_id=recommendation_id,
        execution_id=exec_id,
    )
    with get_pp_connection() as con:
        con.execute(
            """
            UPDATE pp_recommendations
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE recommendation_id = ?
            """,
            ("executed", recommendation_id),
        )
        con.commit()
    return execution_repository.get_execution_by_id(exec_id) or {}


def get_executions(
    supplier_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    return execution_repository.get_executions_filtered(
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
    )
