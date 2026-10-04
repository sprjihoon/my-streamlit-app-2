"""Repair log list, create, update, delete, stats, and export."""
from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional

from logic.db import get_connection

from fastapi import HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.services import repair_catalog

from .common import (
    _clean,
    _lookup_barcode,
    _resolve_vendor,
    _strip_option,
    ensure_repair_tables,
)
from .photos import _delete_image, _log_photos, dump_extra_images, parse_extra_images
from .router import router

class RepairLogCreate(BaseModel):
    날짜: str
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    작업: str
    수량: int = 1
    비용: int
    비고: Optional[str] = None
    작성자: Optional[str] = None
    출처: str = "manual"


class RepairLogUpdate(BaseModel):
    날짜: Optional[str] = None
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    작업: Optional[str] = None
    수량: Optional[int] = None
    비용: Optional[int] = None
    비고: Optional[str] = None

def _editor_name(token: Optional[str]) -> str:
    if not token:
        return "웹"
    with get_connection() as con:
        row = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
    return (row[0] if row and row[0] else None) or "웹"

def _log_where(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    work_type: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
) -> tuple[str, list]:
    where = "WHERE 1=1"
    params: list = []
    if period_from:
        where += " AND 날짜 >= ?"
        params.append(period_from)
    if period_to:
        where += " AND 날짜 <= ?"
        params.append(period_to)
    if vendor:
        where += " AND 업체명 = ?"
        params.append(vendor)
    if work_type:
        where += " AND 작업 LIKE ?"
        params.append(f"%{work_type}%")
    if defect:
        where += " AND 불량명 LIKE ?"
        params.append(f"%{defect}%")
    if author:
        where += " AND 작성자 LIKE ?"
        params.append(f"%{author}%")
    return where, params

@router.get("/stats")
async def get_stats(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
):
    ensure_repair_tables()
    where = "WHERE 1=1"
    params: list = []
    if period_from:
        where += " AND 날짜 >= ?"
        params.append(period_from)
    if period_to:
        where += " AND 날짜 <= ?"
        params.append(period_to)

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM repair_work_log {where}", params).fetchone()[0]
        amount = con.execute(
            f"SELECT COALESCE(SUM(비용), 0) FROM repair_work_log {where}", params
        ).fetchone()[0]
        today = con.execute(
            f"SELECT COUNT(*) FROM repair_work_log {where} AND 날짜 = date('now', 'localtime')",
            params,
        ).fetchone()[0]
        by_source = [
            {"출처": r[0], "count": r[1]}
            for r in con.execute(
                f"SELECT COALESCE(출처, 'unknown'), COUNT(*) FROM repair_work_log {where} GROUP BY 출처",
                params,
            ).fetchall()
        ]
    return {
        "total": total,
        "total_amount": int(amount or 0),
        "today": today,
        "by_source": by_source,
    }


@router.get("/export")
async def export_logs(
    start_date: str = Query(...),
    end_date: str = Query(...),
    vendor: Optional[str] = None,
    work_type: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
):
    from logic.repair_log_excel import EXCEL_LOG_LIMIT, create_repair_log_xlsx

    ensure_repair_tables()
    where, params = _log_where(start_date, end_date, vendor, work_type, defect, author)

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM repair_work_log {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고,
                       작성자, 저장시간, 출처, barcode_image, before_image, after_image, 수정자, 수정시간, extra_images
                FROM repair_work_log {where}
                ORDER BY 업체명, 날짜, id""",
            params,
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="해당 조건의 수선일지가 없습니다.")

    if total > EXCEL_LOG_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"사진 포함 엑셀은 한 번에 {EXCEL_LOG_LIMIT}건까지입니다. 업체나 기간을 더 좁혀 주세요. (현재 {total}건)",
        )

    logs = []
    for r in rows:
        log = {
            "id": r[0], "날짜": r[1], "업체명": r[2], "제품명": r[3], "옵션": r[4],
            "바코드": r[5], "불량명": r[6], "작업": r[7], "수량": r[8], "비용": r[9],
            "비고": r[10], "작성자": r[11], "저장시간": str(r[12]) if r[12] else None,
            "출처": r[13], "barcode_image": r[14], "before_image": r[15],
            "after_image": r[16], "수정자": r[17], "수정시간": str(r[18]) if r[18] else None,
            "extra_images": parse_extra_images(r[19]),
        }
        log["photos"] = _log_photos(log)
        logs.append(log)

    output = io.BytesIO(create_repair_log_xlsx(logs))
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=repair_log_{start_date}_{end_date}.xlsx"
        },
    )


# ─────────────────────────────────────
# Repair logs
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def list_logs(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    work_type: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
    limit: int = Query(default=50, le=2000),
    offset: int = 0,
):
    ensure_repair_tables()
    where = "WHERE 1=1"
    params: list = []
    if period_from:
        where += " AND 날짜 >= ?"
        params.append(period_from)
    if period_to:
        where += " AND 날짜 <= ?"
        params.append(period_to)
    if vendor:
        where += " AND 업체명 = ?"
        params.append(vendor)
    if work_type:
        where += " AND 작업 LIKE ?"
        params.append(f"%{work_type}%")
    if defect:
        where += " AND 불량명 LIKE ?"
        params.append(f"%{defect}%")
    if author:
        where += " AND 작성자 LIKE ?"
        params.append(f"%{author}%")

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM repair_work_log {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고,
                       작성자, 저장시간, 출처, barcode_image, before_image, after_image, 수정자, 수정시간, extra_images
                FROM repair_work_log {where}
                ORDER BY COALESCE(저장시간, 날짜) DESC, id DESC
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        vendors = [r[0] for r in con.execute(
            "SELECT DISTINCT 업체명 FROM repair_work_log WHERE 업체명 IS NOT NULL ORDER BY 업체명"
        ).fetchall()]
        work_types = [r[0] for r in con.execute(
            "SELECT DISTINCT 작업 FROM repair_work_log WHERE 작업 IS NOT NULL ORDER BY 작업"
        ).fetchall()]
        defects = [r[0] for r in con.execute(
            "SELECT DISTINCT 불량명 FROM repair_work_log WHERE 불량명 IS NOT NULL ORDER BY 불량명"
        ).fetchall()]
        authors = [r[0] for r in con.execute(
            "SELECT DISTINCT 작성자 FROM repair_work_log WHERE 작성자 IS NOT NULL ORDER BY 작성자"
        ).fetchall()]

    logs = []
    for r in rows:
        logs.append({
            "id": r[0],
            "날짜": r[1],
            "업체명": r[2],
            "제품명": r[3],
            "옵션": r[4],
            "바코드": r[5],
            "불량명": r[6],
            "작업": r[7],
            "수량": r[8],
            "비용": r[9],
            "비고": r[10],
            "작성자": r[11],
            "저장시간": str(r[12]) if r[12] else None,
            "출처": r[13],
            "barcode_image": r[14],
            "before_image": r[15],
            "after_image": r[16],
            "수정자": r[17],
            "수정시간": str(r[18]) if r[18] else None,
            "extra_images": parse_extra_images(r[19]),
        })
    return {
        "logs": logs,
        "total": total,
        "filters": {"vendors": vendors, "work_types": work_types, "defects": defects, "authors": authors},
    }

def insert_repair_log_record(
    *,
    날짜: str,
    작업: str,
    비용: int,
    업체명: Optional[str] = None,
    제품명: Optional[str] = None,
    옵션: Optional[str] = None,
    바코드: Optional[str] = None,
    불량명: Optional[str] = None,
    수량: int = 1,
    비고: Optional[str] = None,
    작성자: Optional[str] = None,
    출처: str = "manual",
    barcode_image: Optional[str] = None,
    before_image: Optional[str] = None,
    after_image: Optional[str] = None,
    extra_images: Optional[List[str]] = None,
    price_stated: bool = False,
    inbound_item_id: Optional[str] = None,   # 입고 품목 연결
    defect_case_id: Optional[str] = None,    # 입고 결함 케이스 ID
) -> dict:
    """수선일지 한 건 저장. 봇/웹 공통."""
    ensure_repair_tables()
    if not (작업 or "").strip() or 비용 is None:
        raise ValueError("작업과 비용은 필수입니다.")

    qty = 수량 or 1
    now = datetime.now().isoformat()
    vendor, product, option = 업체명, 제품명, _strip_option(옵션)
    barcode = _clean(바코드)
    work = 작업.strip()
    defect = _clean(불량명)
    resolved_work = repair_catalog.resolve_work_type(work)
    if resolved_work:
        work = resolved_work["작업명"]
    resolved_defect = repair_catalog.resolve_defect(defect)
    if resolved_defect:
        defect = resolved_defect["불량명"]

    with get_connection() as con:
        if barcode:
            found = _lookup_barcode(con, barcode)
            if found:
                vendor = vendor or found["업체명"]
                product = product or found["제품명"]
                option = option or found["옵션"]
        if vendor:
            vendor = _resolve_vendor(con, vendor)
        if not vendor or not product:
            raise ValueError("업체명과 제품명이 필요합니다. 바코드를 등록하거나 직접 입력하세요.")

        cur = con.execute(
            """INSERT INTO repair_work_log
               (날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 작업, 수량, 비용, 비고, 작성자, 저장시간, 출처,
                barcode_image, before_image, after_image, extra_images, inbound_item_id, defect_case_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                날짜, vendor, product, option, barcode, defect, work,
                qty, int(비용), _clean(비고), _clean(작성자), now, 출처,
                barcode_image, before_image, after_image, dump_extra_images(extra_images),
                inbound_item_id, defect_case_id,
            ),
        )
        con.commit()
        log_id = cur.lastrowid

    add_log(
        action_type="수선일지_생성",
        target_type="repair_work_log",
        target_id=str(log_id),
        target_name=f"{vendor} {work}",
        user_nickname=작성자 or "웹",
        details=f"날짜: {날짜}, 비용: {비용:,}원",
    )
    if price_stated:
        msg = f"표기된 가격 {int(비용):,}원으로 저장했습니다. ({vendor} {work})"
    else:
        msg = f"수선일지를 저장했습니다. {vendor} / {product} / {work} {int(비용):,}원"
    return {
        "success": True,
        "id": log_id,
        "message": msg,
        "업체명": vendor,
        "제품명": product,
        "옵션": option,
        "바코드": barcode,
        "불량명": defect,
        "작업": work,
        "비용": int(비용),
    }

@router.post("")
async def create_log(data: RepairLogCreate):
    try:
        return insert_repair_log_record(
            날짜=data.날짜,
            작업=data.작업,
            비용=data.비용,
            업체명=data.업체명,
            제품명=data.제품명,
            옵션=data.옵션,
            바코드=data.바코드,
            불량명=data.불량명,
            수량=data.수량,
            비고=data.비고,
            작성자=data.작성자,
            출처=data.출처,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{log_id}")
async def update_log(log_id: int, data: RepairLogUpdate, token: Optional[str] = Query(None)):
    ensure_repair_tables()
    with get_connection() as con:
        existing = con.execute(
            "SELECT id, 업체명, 작업 FROM repair_work_log WHERE id = ?", (log_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")

        payload = data.model_dump(exclude_unset=True)
        if "옵션" in payload:
            payload["옵션"] = _strip_option(payload["옵션"])
        if "바코드" in payload:
            payload["바코드"] = _clean(payload["바코드"])
        if "작업" in payload and payload["작업"]:
            resolved = repair_catalog.resolve_work_type(payload["작업"])
            payload["작업"] = resolved["작업명"] if resolved else payload["작업"].strip()
        if "불량명" in payload and payload["불량명"]:
            resolved_d = repair_catalog.resolve_defect(payload["불량명"])
            payload["불량명"] = resolved_d["불량명"] if resolved_d else payload["불량명"].strip()
        if "업체명" in payload and payload["업체명"]:
            payload["업체명"] = _resolve_vendor(con, payload["업체명"])

        updates, params = [], []
        for col, val in payload.items():
            updates.append(f"{col} = ?")
            params.append(val)

        if not updates:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")
        updates.append("수정자 = ?")
        params.append(_editor_name(token))
        updates.append("수정시간 = ?")
        params.append(datetime.now().isoformat())
        params.append(log_id)
        con.execute(f"UPDATE repair_work_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "message": "수선일지가 수정되었습니다."}


@router.delete("/{log_id}")
async def delete_log(log_id: int):
    ensure_repair_tables()
    with get_connection() as con:
        row = con.execute(
            """SELECT 날짜, 업체명, 작업, 비용, barcode_image, before_image, after_image, extra_images
               FROM repair_work_log WHERE id = ?""",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")
        con.execute("DELETE FROM repair_work_log WHERE id = ?", (log_id,))
        con.commit()

    for fn in (row[4], row[5], row[6], *parse_extra_images(row[7])):
        _delete_image(fn)

    add_log(
        action_type="수선일지_삭제",
        target_type="repair_work_log",
        target_id=str(log_id),
        target_name=f"{row[1]} {row[2]}",
        user_nickname="웹",
        details=f"날짜: {row[0]}, 비용: {row[3] or 0:,}원",
    )
    return {"success": True, "message": "수선일지가 삭제되었습니다."}
