"""Repair photo files, purge, and upload."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from logic.db import get_connection

from fastapi import File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.app.api.logs import add_log

from .common import IMAGE_EXTS, UPLOAD_DIR, ensure_repair_tables
from .router import router

async def _save_upload(file: UploadFile) -> str:
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {ext}")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(await file.read())
    return filename


def _image_path(filename: Optional[str]) -> Optional[Path]:
    if not filename:
        return None
    name = Path(str(filename)).name
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return None
    root = UPLOAD_DIR.resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def parse_extra_images(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return [str(raw).strip()] if str(raw).strip() else []
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def dump_extra_images(names: Optional[List[str]]) -> Optional[str]:
    cleaned = [str(x).strip() for x in (names or []) if str(x).strip()]
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def _delete_image(filename: Optional[str]) -> bool:
    """서버 디스크의 수선 사진 파일을 실제로 삭제한다."""
    path = _image_path(filename)
    if not path or not path.is_file():
        return False
    try:
        path.unlink()
        return not path.exists()
    except OSError:
        return False


def _old_photo_cutoff(days: int = 60) -> str:
    return (datetime.now() - timedelta(days=max(1, days))).strftime("%Y-%m-%d")

def _log_photos(log: dict) -> list[tuple[str, Optional[Path]]]:
    """보고용 작업 사진만. 바코드 사진은 포함하지 않는다."""
    photos: list[tuple[str, Optional[Path]]] = [
        ("사진1", _image_path(log.get("before_image"))),
        ("사진2", _image_path(log.get("after_image"))),
    ]
    for i, fn in enumerate(log.get("extra_images") or [], start=1):
        photos.append((f"추가{i}", _image_path(fn)))
    return photos


def _collect_stale_photo_names(con, cutoff: str) -> tuple[set[str], int]:
    """60일 지난 바코드/전후 사진 + 어디에도 안 묶인 서버 파일."""
    cutoff_ts = datetime.strptime(cutoff, "%Y-%m-%d").timestamp()
    names: set[str] = set()
    rows = con.execute(
        """SELECT id, barcode_image, before_image, after_image, extra_images
           FROM repair_work_log
           WHERE (날짜 < ? OR IFNULL(저장시간, '') < ?)
             AND (
               IFNULL(barcode_image, '') != ''
               OR IFNULL(before_image, '') != ''
               OR IFNULL(after_image, '') != ''
               OR IFNULL(extra_images, '') != ''
             )""",
        (cutoff, cutoff),
    ).fetchall()
    for _id, barcode_fn, before_fn, after_fn, extra_raw in rows:
        for fn in (barcode_fn, before_fn, after_fn, *parse_extra_images(extra_raw)):
            if fn:
                names.add(Path(str(fn)).name)

    if UPLOAD_DIR.exists():
        for path in UPLOAD_DIR.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                if path.stat().st_mtime < cutoff_ts:
                    names.add(path.name)
            except OSError:
                continue

    names.update(_legacy_inbox_stale_filenames(con, cutoff))
    names.update(_v2_inbox_stale_filenames(con, cutoff))
    return names, len(rows)


def _inbox_filenames_older_than(rows, cutoff: str) -> set[str]:
    stale: set[str] = set()
    for fn, created in rows:
        if not fn:
            continue
        if created and str(created)[:10] < cutoff:
            stale.add(Path(str(fn)).name)
    return stale


def _legacy_inbox_stale_filenames(con, cutoff: str) -> set[str]:
    """legacy inbox cleanup: 구 user-PK 테이블의 60일 초과 임시 파일만."""
    try:
        inbox = con.execute(
            "SELECT filename, created_at FROM repair_photo_inbox_file"
        ).fetchall()
    except Exception:
        inbox = []
    return _inbox_filenames_older_than(inbox, cutoff)


def _v2_inbox_stale_filenames(con, cutoff: str) -> set[str]:
    """v2 inbox cleanup: (user_id, channel_id) 단위 60일 초과 임시 파일만."""
    try:
        inbox_v2 = con.execute(
            "SELECT filename, created_at FROM repair_photo_inbox_file_v2"
        ).fetchall()
    except Exception:
        inbox_v2 = []
    return _inbox_filenames_older_than(inbox_v2, cutoff)


def _clear_photo_refs(con, names: set[str]) -> int:
    """일지·인박스에서 해당 파일 참조를 완전히 끊는다."""
    if not names:
        return 0
    cleared = 0
    files = list(names)
    placeholders = ",".join("?" * len(files))
    for col in ("barcode_image", "before_image", "after_image"):
        cur = con.execute(
            f"""UPDATE repair_work_log SET {col} = NULL
                WHERE {col} IN ({placeholders})""",
            files,
        )
        cleared += cur.rowcount or 0
    extra_rows = con.execute(
        "SELECT id, extra_images FROM repair_work_log WHERE IFNULL(extra_images, '') != ''"
    ).fetchall()
    for log_id, raw in extra_rows:
        kept = [fn for fn in parse_extra_images(raw) if Path(str(fn)).name not in names]
        if kept != parse_extra_images(raw):
            con.execute(
                "UPDATE repair_work_log SET extra_images = ? WHERE id = ?",
                (dump_extra_images(kept), log_id),
            )
            cleared += 1
    try:
        # legacy inbox cleanup: 구 user-PK 잔여 행만
        con.execute(
            f"DELETE FROM repair_photo_inbox_file WHERE filename IN ({placeholders})",
            files,
        )
        con.execute(
            """DELETE FROM repair_photo_inbox
               WHERE user_id NOT IN (SELECT user_id FROM repair_photo_inbox_file)"""
        )
        # v2 inbox cleanup: 방 키 (user_id, channel_id)로 빈 메타만 삭제
        con.execute(
            f"DELETE FROM repair_photo_inbox_file_v2 WHERE filename IN ({placeholders})",
            files,
        )
        con.execute(
            """DELETE FROM repair_photo_inbox_v2
               WHERE NOT EXISTS (
                   SELECT 1 FROM repair_photo_inbox_file_v2 f
                   WHERE f.user_id = repair_photo_inbox_v2.user_id
                     AND f.channel_id = repair_photo_inbox_v2.channel_id
               )"""
        )
    except Exception:
        pass
    return cleared

@router.get("/image/{filename}")
async def get_repair_image(filename: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", filename):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없습니다.")
    return FileResponse(path)


@router.get("/photos/old")
async def old_photo_stats(days: int = Query(60, ge=1, le=365)):
    """60일(기본) 지난 수선 사진 건수. 바코드·고아 파일 포함."""
    ensure_repair_tables()
    cutoff = _old_photo_cutoff(days)
    with get_connection() as con:
        names, logs = _collect_stale_photo_names(con, cutoff)
    return {"cutoff": cutoff, "days": days, "logs": logs, "files": len(names)}


@router.post("/photos/purge-old")
async def purge_old_photos(days: int = Query(60, ge=1, le=365)):
    """60일 지난 사진을 서버 디스크에서 완전 삭제. 일지 행은 남긴다."""
    ensure_repair_tables()
    cutoff = _old_photo_cutoff(days)
    with get_connection() as con:
        names, logs = _collect_stale_photo_names(con, cutoff)
        deleted = 0
        for name in names:
            if _delete_image(name):
                deleted += 1
        _clear_photo_refs(con, names)
        con.commit()

    leftover = [
        name for name in names
        if (path := _image_path(name)) is not None and path.is_file()
    ]
    add_log(
        action_type="수선사진_정리",
        target_type="repair_work_log",
        target_id=cutoff,
        target_name=f"{days}일 이전 사진",
        user_nickname="웹",
        details=f"{logs}건 일지, 서버 파일 {deleted}개 완전 삭제 (기준일 {cutoff}, 잔여 {len(leftover)})",
    )
    return {
        "success": True,
        "cutoff": cutoff,
        "days": days,
        "logs": logs,
        "deleted_files": deleted,
        "remaining_files": leftover,
        "message": f"{cutoff} 이전 서버 사진 {deleted}장을 완전히 삭제했습니다. 일지는 그대로입니다.",
    }

def save_image_bytes(data: bytes, ext: str = ".jpg") -> str:
    ensure_repair_tables()
    ext = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return filename

@router.post("/{log_id}/photos")
async def upload_photos(
    log_id: int,
    before: Optional[UploadFile] = File(None),
    after: Optional[UploadFile] = File(None),
    barcode: Optional[UploadFile] = File(None),
    extra: List[UploadFile] = File(default=[]),
):
    ensure_repair_tables()
    with get_connection() as con:
        row = con.execute(
            "SELECT before_image, after_image, barcode_image, extra_images FROM repair_work_log WHERE id = ?",
            (log_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="수선일지를 찾을 수 없습니다.")

        updates, params = [], []
        mapping = [
            ("before", before, "before_image", row[0]),
            ("after", after, "after_image", row[1]),
        ]
        saved = {}
        for _, upload, col, old in mapping:
            if upload and upload.filename:
                filename = await _save_upload(upload)
                _delete_image(old)
                updates.append(f"{col} = ?")
                params.append(filename)
                saved[col] = filename

        extra_files = [f for f in (extra or []) if f and f.filename]
        if extra_files:
            extras = parse_extra_images(row[3])
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
        con.execute(f"UPDATE repair_work_log SET {', '.join(updates)} WHERE id = ?", params)
        con.commit()

    return {"success": True, "saved": saved, "message": "사진이 저장되었습니다."}
