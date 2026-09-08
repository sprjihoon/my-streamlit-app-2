"""
backend/app/api/defect_log.py - 불량일지 API
───────────────────────────────────────
수선작업일지와 동일 구조 + 처리결과(업체반송/반품/기타) 컬럼 추가.
비용/작업 개념 없음. 처리결과는 웹에서만 수동 입력.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.api.logs import add_log
from backend.app.api.repair_log import (
    UPLOAD_DIR,
    IMAGE_EXTS,
    _clean,
    _strip_option,
    _image_path,
    _resolve_vendor,
    _lookup_barcode,
    parse_extra_images,
    dump_extra_images,
    _delete_image,
    save_image_bytes,
    ensure_repair_tables,
    _save_upload,
)
from logic.db import get_connection

router = APIRouter(prefix="/defect-log", tags=["defect-log"])

DEFECT_RESULT_VALUES = ("업체반송", "반품", "기타")


# ─────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────

class DefectLogCreate(BaseModel):
    날짜: str
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    수량: int = 1
    비고: Optional[str] = None
    작성자: Optional[str] = None
    출처: str = "manual"
    처리결과: Optional[str] = None


class DefectLogUpdate(BaseModel):
    날짜: Optional[str] = None
    업체명: Optional[str] = None
    제품명: Optional[str] = None
    옵션: Optional[str] = None
    바코드: Optional[str] = None
    불량명: Optional[str] = None
    수량: Optional[int] = None
    비고: Optional[str] = None
    처리결과: Optional[str] = None


class DefectResultUpdate(BaseModel):
    처리결과: Optional[str] = None


# ─────────────────────────────────────
# DB
# ─────────────────────────────────────

def ensure_defect_tables():
    """불량일지 테이블 생성. repair_barcode 테이블도 함께 보장."""
    ensure_repair_tables()
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS defect_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                날짜 TEXT,
                업체명 TEXT,
                제품명 TEXT,
                옵션 TEXT,
                바코드 TEXT,
                불량명 TEXT,
                수량 INTEGER DEFAULT 1,
                비고 TEXT,
                작성자 TEXT,
                저장시간 TIMESTAMP,
                출처 TEXT,
                before_image TEXT,
                after_image TEXT,
                extra_images TEXT,
                처리결과 TEXT,
                수정자 TEXT,
                수정시간 TIMESTAMP
            )
        """)
        con.commit()


def _editor_name(token: Optional[str]) -> str:
    if not token:
        return "웹"
    with get_connection() as con:
        row = con.execute(
            "SELECT u.nickname FROM sessions s JOIN users u ON s.user_id = u.user_id WHERE s.token = ?",
            (token,),
        ).fetchone()
    return (row[0] if row and row[0] else None) or "웹"


def _log_photos(log: dict) -> list:
    photos = [
        ("사진1", _image_path(log.get("before_image"))),
        ("사진2", _image_path(log.get("after_image"))),
    ]
    for i, fn in enumerate(log.get("extra_images") or [], start=1):
        photos.append((f"추가{i}", _image_path(fn)))
    return photos


def _build_where(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
    result: Optional[str] = None,
    unresolved_only: bool = False,
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
    if defect:
        where += " AND 불량명 LIKE ?"
        params.append(f"%{defect}%")
    if author:
        where += " AND 작성자 LIKE ?"
        params.append(f"%{author}%")
    if result:
        where += " AND 처리결과 = ?"
        params.append(result)
    if unresolved_only:
        where += " AND (처리결과 IS NULL OR 처리결과 = '')"
    return where, params


# ─────────────────────────────────────
# Core insert (봇/웹 공통)
# ─────────────────────────────────────

def insert_defect_log_record(
    *,
    날짜: str,
    업체명: Optional[str] = None,
    제품명: Optional[str] = None,
    옵션: Optional[str] = None,
    바코드: Optional[str] = None,
    불량명: Optional[str] = None,
    수량: int = 1,
    비고: Optional[str] = None,
    작성자: Optional[str] = None,
    출처: str = "manual",
    before_image: Optional[str] = None,
    after_image: Optional[str] = None,
    extra_images: Optional[List[str]] = None,
) -> dict:
    ensure_defect_tables()
    qty = 수량 or 1
    now = datetime.now().isoformat()

    with get_connection() as con:
        vendor = _clean(업체명)
        product = _clean(제품명)
        option = _strip_option(옵션)
        barcode = _clean(바코드)
        defect = _clean(불량명)

        if barcode:
            found = _lookup_barcode(con, barcode)
            if found:
                vendor = vendor or found["업체명"]
                product = product or found["제품명"]
                option = option or found["옵션"]

        if vendor:
            vendor = _resolve_vendor(con, vendor)

        if not vendor or not product:
            raise ValueError("업체명과 제품명이 필요합니다.")

        cur = con.execute(
            """INSERT INTO defect_log
               (날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 수량, 비고, 작성자, 저장시간, 출처,
                before_image, after_image, extra_images)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                날짜, vendor, product, option, barcode, defect,
                qty, _clean(비고), _clean(작성자), now, 출처,
                before_image, after_image, dump_extra_images(extra_images),
            ),
        )
        con.commit()
        log_id = cur.lastrowid

    add_log(
        action_type="불량일지_생성",
        target_type="defect_log",
        target_id=str(log_id),
        target_name=f"{vendor} {defect or ''}",
        user_nickname=작성자 or "웹",
        details=f"날짜: {날짜}",
    )

    return {
        "success": True,
        "id": log_id,
        "message": f"불량일지를 저장했습니다. {vendor} / {product} / {defect or ''}",
        "업체명": vendor,
        "제품명": product,
        "불량명": defect,
    }


# ─────────────────────────────────────
# 이미지 서빙
# ─────────────────────────────────────

@router.get("/image/{filename}")
async def get_defect_image(filename: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(path)


# ─────────────────────────────────────
# Stats
# ─────────────────────────────────────

@router.get("/stats")
async def get_stats(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
):
    ensure_defect_tables()
    where, params = _build_where(period_from=period_from, period_to=period_to)
    with get_connection() as con:
        total = con.execute(
            f"SELECT COUNT(*) FROM defect_log {where}", params
        ).fetchone()[0]
        today = con.execute(
            f"SELECT COUNT(*) FROM defect_log {where} AND 날짜 = date('now', 'localtime')", params
        ).fetchone()[0]
        by_result = [
            {"처리결과": r[0] or "미처리", "count": r[1]}
            for r in con.execute(
                f"SELECT COALESCE(처리결과, '미처리'), COUNT(*) FROM defect_log {where} GROUP BY 처리결과",
                params,
            ).fetchall()
        ]
        unresolved = con.execute(
            f"SELECT COUNT(*) FROM defect_log {where} AND (처리결과 IS NULL OR 처리결과 = '')", params
        ).fetchone()[0]
    return {
        "total": total,
        "today": today,
        "unresolved": unresolved,
        "by_result": by_result,
    }


# ─────────────────────────────────────
# List
# ─────────────────────────────────────

@router.get("")
@router.get("/")
async def list_logs(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    vendor: Optional[str] = None,
    defect: Optional[str] = None,
    author: Optional[str] = None,
    result: Optional[str] = None,
    unresolved_only: bool = False,
    limit: int = Query(default=50, le=2000),
    offset: int = 0,
):
    ensure_defect_tables()
    where, params = _build_where(period_from, period_to, vendor, defect, author, result, unresolved_only)

    with get_connection() as con:
        total = con.execute(f"SELECT COUNT(*) FROM defect_log {where}", params).fetchone()[0]
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 제품명, 옵션, 바코드, 불량명, 수량, 비고,
                       작성자, 저장시간, 출처, before_image, after_image, extra_images,
                       처리결과, 수정자, 수정시간
                FROM defect_log {where}
                ORDER BY COALESCE(저장시간, 날짜) DESC, id DESC
                LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        ).fetchall()
        vendors = [r[0] for r in con.execute(
            "SELECT DISTINCT 업체명 FROM defect_log WHERE 업체명 IS NOT NULL ORDER BY 업체명"
        ).fetchall()]
        defects = [r[0] for r in con.execute(
            "SELECT DISTINCT 불량명 FROM defect_log WHERE 불량명 IS NOT NULL ORDER BY 불량명"
        ).fetchall()]
        authors = [r[0] for r in con.execute(
            "SELECT DISTINCT 작성자 FROM defect_log WHERE 작성자 IS NOT NULL ORDER BY 작성자"
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
            "수량": r[7],
            "비고": r[8],
            "작성자": r[9],
            "저장시간": str(r[10]) if r[10] else None,
            "출처": r[11],
            "before_image": r[12],
            "after_image": r[13],
            "extra_images": parse_extra_images(r[14]),
            "처리결과": r[15],
            "수정자": r[16],
            "수정시간": str(r[17]) if r[17] else None,
        })

    return {
        "logs": logs,
        "total": total,
        "filters": {"vendors": vendors, "defects": defects, "authors": authors},
    }


# ─────────────────────────────────────
# Create
# ─────────────────────────────────────

@router.post("")
async def create_log(data: DefectLogCreate):
    try:
        return insert_defect_log_record(
            날짜=data.날짜,
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


# ─────────────────────────────────────
# Update
# ─────────────────────────────────────

@router.put("/{log_id}")
async def update_log(log_id: int, data: DefectLogUpdate, token: Optional[str] = Query(None)):
    ensure_defect_tables()
    with get_connection() as con:
        existing = con.execute(
            "SELECT id FROM defect_log WHERE id = ?", (log_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="불량일지를 찾을 수 없습니다.")

        payload = data.model_dump(exclude_unset=True)

        # 처리결과 유효성 검사
        if "처리결과" in payload and payload["처리결과"] is not None:
            if payload["처리결과"] not in DEFECT_RESULT_VALUES:
                raise HTTPException(
                    status_code=400,
                    detail=f"처리결과는 {', '.join(DEFECT_RESULT_VALUES)} 중 하나여야 합니다.",
                )

        if "옵션" in payload:
            payload["옵션"] = _strip_option(payload["옵션"])
        if "바코드" in payload:
            payload["바코드"] = _clean(payload["바코드"])
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
        con.execute(f"UPDATE defect_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "message": "불량일지가 수정되었습니다."}


# ─────────────────────────────────────
# 처리결과 단독 업데이트 (PATCH)
# ─────────────────────────────────────

@router.patch("/{log_id}/result")
async def update_result(log_id: int, data: DefectResultUpdate, token: Optional[str] = Query(None)):
    ensure_defect_tables()
    result_val = data.처리결과
    if result_val is not None and result_val not in DEFECT_RESULT_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"처리결과는 {', '.join(DEFECT_RESULT_VALUES)} 중 하나여야 합니다.",
        )
    with get_connection() as con:
        existing = con.execute("SELECT id FROM defect_log WHERE id = ?", (log_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="불량일지를 찾을 수 없습니다.")
        con.execute(
            "UPDATE defect_log SET 처리결과 = ?, 수정자 = ?, 수정시간 = ? WHERE id = ?",
            (result_val, _editor_name(token), datetime.now().isoformat(), log_id),
        )
        con.commit()
    return {"success": True, "처리결과": result_val, "message": "처리결과가 업데이트되었습니다."}


# ─────────────────────────────────────
# Delete
# ─────────────────────────────────────

@router.delete("/{log_id}")
async def delete_log(log_id: int):
    ensure_defect_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT 날짜, 업체명, 불량명, before_image, after_image, extra_images FROM defect_log WHERE id = ?",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="불량일지를 찾을 수 없습니다.")
        con.execute("DELETE FROM defect_log WHERE id = ?", (log_id,))
        con.commit()

    for fn in (row[3], row[4], *parse_extra_images(row[5])):
        _delete_image(fn)

    add_log(
        action_type="불량일지_삭제",
        target_type="defect_log",
        target_id=str(log_id),
        target_name=f"{row[1]} {row[2] or ''}",
        user_nickname="웹",
        details=f"날짜: {row[0]}",
    )
    return {"success": True, "message": "불량일지가 삭제되었습니다."}


# ─────────────────────────────────────
# 사진 업로드
# ─────────────────────────────────────

@router.post("/{log_id}/photos")
async def upload_photos(
    log_id: int,
    before: Optional[UploadFile] = File(None),
    after: Optional[UploadFile] = File(None),
    extra: List[UploadFile] = File(default=[]),
):
    ensure_defect_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT before_image, after_image, extra_images FROM defect_log WHERE id = ?",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="불량일지를 찾을 수 없습니다.")

        updates, params = [], []
        mapping = [
            (before, "before_image", row[0]),
            (after, "after_image", row[1]),
        ]
        saved = {}
        for upload, col, old in mapping:
            if upload and upload.filename:
                filename = await _save_upload(upload)
                _delete_image(old)
                updates.append(f"{col} = ?")
                params.append(filename)
                saved[col] = filename

        extra_files = [f for f in (extra or []) if f and f.filename]
        if extra_files:
            extras = parse_extra_images(row[2])
            added = []
            for upload in extra_files:
                filename = await _save_upload(upload)
                extras.append(filename)
                added.append(filename)
            updates.append("extra_images = ?")
            params.append(dump_extra_images(extras))
            saved["extra_images"] = added

        if not updates:
            raise HTTPException(status_code=400, detail="업로드할 사진이 없습니다.")
        params.append(log_id)
        con.execute(f"UPDATE defect_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "saved": saved, "message": "사진이 저장되었습니다."}
