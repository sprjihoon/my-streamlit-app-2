from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from prepacking.models.schemas import PPUploadListItem, PPUploadResponse, pp_optional_date_str
from prepacking.services.upload.shipping_stats_upload_service import upload_shipping_stats
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
    )


@router.post("/upload", response_model=PPUploadResponse)
async def post_upload(
    file: UploadFile = File(),
    supplier_name: str = Form(),
    uploaded_by: str = Form(""),
    note: str = Form(""),
) -> PPUploadResponse:
    suffix = Path(file.filename or "upload").suffix or ".dat"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = upload_shipping_stats(tmp_path, supplier_name, uploaded_by, note)
    finally:
        os.unlink(tmp_path)
    return PPUploadResponse(
        upload_id=int(result["upload_id"]),
        file_name=str(result.get("file_name") or ""),
        row_count=int(result.get("row_count") or 0),
        data_start_date=pp_optional_date_str(result.get("data_start_date")),
        data_end_date=pp_optional_date_str(result.get("data_end_date")),
    )


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
