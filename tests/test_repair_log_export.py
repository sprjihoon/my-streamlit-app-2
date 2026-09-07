"""수선작업일지 엑셀 보고: 업체·기간 필터와 작업 사진만 포함한다. 임시 DB·업로드만 사용."""
from __future__ import annotations

import asyncio
import io
import struct
import zipfile
import zlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.api.repair_log import (
    _log_photos,
    _log_where,
    _query_repair_logs,
    export_logs,
    insert_repair_log_record,
)
from logic.repair_log_excel import create_repair_log_xlsx


def _png(path: Path, color=(30, 90, 180)) -> Path:
    w = h = 12
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


def _insert(**kwargs):
    defaults = dict(
        날짜="2026-09-05",
        작업="단순바느질",
        비용=1500,
        업체명="로지킴",
        제품명="릴리프T",
        불량명="구멍",
        수량=1,
        작성자="테스터",
        출처="manual",
    )
    defaults.update(kwargs)
    return insert_repair_log_record(**defaults)


def _body(resp) -> bytes:
    iterator = resp.body_iterator
    if hasattr(iterator, "__anext__"):
        async def collect():
            chunks = []
            async for chunk in iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        return asyncio.run(collect())
    return b"".join(iterator)


def _xlsx_media(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return [name for name in zf.namelist() if name.startswith("xl/media/")]


def test_query_keeps_only_selected_vendor_and_period():
    _insert(날짜="2026-09-05", 업체명="로지킴", 제품명="릴리프T")
    _insert(날짜="2026-09-05", 업체명="팔로우미코스메틱", 제품명="세럼")
    _insert(날짜="2026-08-01", 업체명="로지킴", 제품명="지난달")

    where, params = _log_where("2026-09-01", "2026-09-30", "로지킴")
    logs, total = _query_repair_logs(where, params)
    assert total == 1
    assert logs[0]["업체명"] == "로지킴"
    assert logs[0]["제품명"] == "릴리프T"


def test_log_photos_skip_barcode(isolated_runtime):
    repair_dir = isolated_runtime["repair"]
    work = _png(repair_dir / "work.png").name
    bar = _png(repair_dir / "bar.png", (200, 20, 20)).name
    photos = _log_photos({
        "barcode_image": bar,
        "before_image": work,
        "after_image": None,
        "extra_images": [],
    })
    labels = [label for label, _path in photos]
    assert "바코드" not in labels
    assert labels[0] == "사진1"
    assert photos[0][1] == repair_dir / work


def test_xlsx_embeds_work_photos_not_barcode(isolated_runtime):
    repair_dir = isolated_runtime["repair"]
    work = _png(repair_dir / "work.png")
    with_photo = create_repair_log_xlsx([{
        "날짜": "2026-09-05",
        "업체명": "로지킴",
        "제품명": "릴리프T",
        "작업": "단순바느질",
        "수량": 1,
        "비용": 1500,
        "photos": [("사진1", work)],
    }])
    empty = create_repair_log_xlsx([{
        "날짜": "2026-09-05",
        "업체명": "로지킴",
        "제품명": "릴리프T",
        "작업": "단순바느질",
        "수량": 1,
        "비용": 1500,
        "photos": [],
    }])
    assert with_photo[:2] == b"PK"
    assert _xlsx_media(with_photo)
    assert not _xlsx_media(empty)


def test_export_excel_filters_and_embeds_photo(isolated_runtime):
    repair_dir = isolated_runtime["repair"]
    before = _png(repair_dir / "p1.png", (20, 160, 80))
    extra = _png(repair_dir / "p2.png", (200, 80, 20))
    _insert(
        날짜="2026-09-05",
        업체명="로지킴",
        제품명="릴리프T",
        barcode_image="should-not-matter.png",
        before_image=before.name,
        extra_images=[extra.name],
    )
    _insert(날짜="2026-09-05", 업체명="팔로우미코스메틱", 제품명="세럼")

    resp = asyncio.run(export_logs(
        start_date="2026-09-01",
        end_date="2026-09-07",
        vendor="로지킴",
    ))
    assert "spreadsheetml" in (resp.media_type or "")
    data = _body(resp)
    assert data[:2] == b"PK"
    assert len(_xlsx_media(data)) == 2


def test_export_excel_empty_period_is_404():
    _insert(날짜="2026-08-01", 업체명="로지킴")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(export_logs(start_date="2026-09-01", end_date="2026-09-07", vendor="로지킴"))
    assert exc.value.status_code == 404


def test_export_excel_rejects_too_many_rows(monkeypatch):
    import logic.repair_log_excel as excelmod

    monkeypatch.setattr(excelmod, "EXCEL_LOG_LIMIT", 1)
    _insert(날짜="2026-09-05", 업체명="로지킴", 제품명="릴리프T")
    _insert(날짜="2026-09-06", 업체명="로지킴", 제품명="릴리프T")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(export_logs(start_date="2026-09-01", end_date="2026-09-07", vendor="로지킴"))
    assert exc.value.status_code == 400
