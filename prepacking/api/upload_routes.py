from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from prepacking.models.schemas import PPUploadListItem, PPUploadResponse, PPUploadStatusResponse, pp_optional_date_str
from prepacking.services.upload.shipping_stats_upload_service import (
    DuplicateFileError,
    upload_shipping_stats,
)
from prepacking.services.upload.upload_history_service import (
    delete_upload,
    get_upload_detail,
    list_uploads,
    mark_upload_applied,
)

router = APIRouter(prefix="/pp/upload", tags=["prepacking-upload"])


def _upload_item_from_row(r: dict) -> PPUploadListItem:
    return PPUploadListItem(
        upload_id=int(r.get("upload_id") or 0),
        file_name=str(r.get("file_name") or ""),
        file_version=int(r.get("file_version") or 0),
        uploaded_at=str(r.get("uploaded_at") or ""),
        uploaded_by=str(r.get("uploaded_by") or ""),
        row_count=int(r.get("row_count") or 0),
        applied_yn=bool(r.get("applied_yn")),
        note=str(r.get("note") or ""),
        upload_status=str(r.get("upload_status") or "completed"),
        skipped_count=int(r.get("skipped_count") or 0),
        total_count=int(r.get("total_count") or 0),
    )


@router.post("/upload", response_model=PPUploadResponse)
async def post_upload(
    file: UploadFile = File(),
    supplier_name: str = Form(""),
    uploaded_by: str = Form(""),
    note: str = Form(""),
) -> PPUploadResponse:
    suffix = Path(file.filename or "upload").suffix or ".dat"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = upload_shipping_stats(tmp_path, supplier_name, uploaded_by, note)
    except DuplicateFileError as e:
        raise HTTPException(status_code=409, detail=str(e))
    finally:
        os.unlink(tmp_path)
    return PPUploadResponse(
        upload_id=int(result["upload_id"]),
        file_name=str(result.get("file_name") or ""),
        upload_status=str(result.get("upload_status") or "processing"),
    )


@router.get("/status/{upload_id}", response_model=PPUploadStatusResponse)
def get_upload_status(upload_id: int) -> PPUploadStatusResponse:
    row = get_upload_detail(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="upload_not_found")
    return PPUploadStatusResponse(
        upload_id=int(row.get("upload_id") or 0),
        upload_status=str(row.get("upload_status") or "completed"),
        row_count=int(row.get("row_count") or 0),
        skipped_count=int(row.get("skipped_count") or 0),
        total_count=int(row.get("total_count") or 0),
        error_message=str(row.get("error_message") or ""),
    )


@router.get("/suppliers")
def get_suppliers() -> list[str]:
    """Return distinct supplier names from pp_shipping_stats."""
    from prepacking.database import get_pp_connection

    with get_pp_connection() as con:
        cur = con.execute(
            """
            SELECT DISTINCT TRIM(supplier_name) AS name
            FROM pp_shipping_stats
            WHERE supplier_name IS NOT NULL AND TRIM(supplier_name) != ''
            ORDER BY name
            """
        )
        return [row[0] for row in cur.fetchall()]


@router.get("/list", response_model=list[PPUploadListItem])
def get_upload_list(
    supplier_name: str | None = None,
    limit: int = 50,
) -> list[PPUploadListItem]:
    rows = list_uploads(supplier_name=supplier_name, limit=limit)
    return [_upload_item_from_row(r) for r in rows]


@router.get("/{upload_id}")
def get_upload(upload_id: int) -> dict:
    row = get_upload_detail(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="upload_not_found")
    return row


@router.delete("/{upload_id}")
def remove_upload(upload_id: int) -> dict:
    ok = delete_upload(upload_id)
    if not ok:
        raise HTTPException(status_code=404, detail="upload_not_found")
    return {"ok": True, "upload_id": upload_id}


@router.patch("/{upload_id}/apply")
def apply_upload(upload_id: int) -> dict:
    if get_upload_detail(upload_id) is None:
        raise HTTPException(status_code=404, detail="upload_not_found")
    ok = mark_upload_applied(upload_id)
    return {"ok": bool(ok), "upload_id": upload_id}
