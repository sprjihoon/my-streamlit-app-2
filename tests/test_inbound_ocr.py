"""
tests/test_inbound_ocr.py - 입고 OCR 단위 테스트 (실제 OpenAI 호출 없음)

RUN_LIVE_OCR=1 환경변수가 있을 때만 실제 API 호출하는 live 테스트가 활성화된다.
"""
from __future__ import annotations

import asyncio
import io
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from backend.app.api.inbound import (
    OcrError,
    _normalize_image,
    _run_ocr,
    ensure_inbound_tables,
)


# ─────────────────────────────────────
# Fixture / 헬퍼
# ─────────────────────────────────────

def make_jpeg(width: int = 100, height: int = 100, color=(255, 0, 0)) -> bytes:
    """단색 JPEG 이미지 bytes 생성."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def make_jpeg_with_exif(width: int, height: int, orientation: int) -> bytes:
    """EXIF Orientation 태그를 포함한 JPEG bytes 생성."""
    img = Image.new("RGB", (width, height), color=(0, 200, 100))
    exif = img.getexif()
    exif[0x0112] = orientation  # Orientation tag
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _ocr_json(**overrides) -> dict:
    """기본 OCR 결과 JSON(유효한 Structured Output 형태)."""
    base = {
        "receipt": {
            "storeName": "테스트상회",
            "receiptNo": "12345",
            "orderDate": "2026-09-08",
            "totalAmount": 50000,
            "isHandwritten": False,
            "confidence": 0.95,
            "needsReview": False,
            "warnings": [],
        },
        "items": [
            {
                "lineNo": 1,
                "rawText": "상품A 빨강 M",
                "itemName": "상품A",
                "color": "빨강",
                "size": "M",
                "optionText": None,
                "unitPrice": 10000,
                "quantity": 5,
                "amount": 50000,
                "confidence": 0.95,
                "needsReview": False,
                "warnings": [],
            }
        ],
    }
    base.update(overrides)
    return base


def _handwritten_ocr_json() -> dict:
    """수기 장끼 OCR 결과 – 천원 단위 추정 경고 포함."""
    return {
        "receipt": {
            "storeName": "수기상회",
            "receiptNo": None,
            "orderDate": "2026-09-08",
            "totalAmount": 18000,
            "isHandwritten": True,
            "confidence": 0.80,
            "needsReview": True,
            "warnings": [],
        },
        "items": [
            {
                "lineNo": 1,
                "rawText": "상품B 18",
                "itemName": "상품B",
                "color": None,
                "size": None,
                "optionText": None,
                "unitPrice": 18000,
                "quantity": 1,
                "amount": 18000,
                "confidence": 0.75,
                "needsReview": True,
                "warnings": ["천원 단위 추정"],
            }
        ],
    }


def _make_api_resp(status_code: int, body: dict | None = None) -> MagicMock:
    """mock httpx response 생성."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    if body is not None:
        resp.json.return_value = body
    return resp


def _api_body(ocr_json: dict) -> dict:
    """OCR dict → OpenAI chat/completions 응답 형태."""
    return {
        "choices": [{"message": {"content": json.dumps(ocr_json)}}]
    }


class _AsyncCtx:
    """httpx.AsyncClient context manager mock."""

    def __init__(self, resp=None, timeout_exc=False):
        import httpx
        self._resp = resp
        self._timeout_exc = timeout_exc
        self._call_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def post(self, *_, **__):
        import httpx
        self._call_count += 1
        if self._timeout_exc:
            raise httpx.TimeoutException("timeout")
        return self._resp


class _AlwaysTimeoutCtx(_AsyncCtx):
    pass


class _Always500Ctx(_AsyncCtx):
    async def post(self, *_, **__):
        self._call_count += 1
        return _make_api_resp(500)


# ─────────────────────────────────────
# Test 1 – MIME 판별: 어떤 파일명이어도 정규화 후 JPEG
# ─────────────────────────────────────

def test_1_normalize_always_returns_jpeg():
    """.png 파일명 + JPEG 바이트 → 정규화 결과 MIME image/jpeg."""
    raw = make_jpeg(100, 100)
    norm_bytes, mime = _normalize_image(raw)

    assert mime == "image/jpeg", "MIME must be image/jpeg"
    out = Image.open(io.BytesIO(norm_bytes))
    assert out.format == "JPEG"


# ─────────────────────────────────────
# Test 2 – EXIF 회전 + 3000px → 2048px 이하
# ─────────────────────────────────────

@pytest.mark.parametrize("orientation", [3, 6, 8])
def test_2_normalize_exif_and_resize(orientation):
    """EXIF 회전(3,6,8) + 3000px 이미지 → 2048px 이하로 정규화."""
    raw = make_jpeg_with_exif(3000, 2000, orientation)
    norm_bytes, mime = _normalize_image(raw)

    assert mime == "image/jpeg"
    img = Image.open(io.BytesIO(norm_bytes))
    assert max(img.size) <= 2048, f"정규화 후 최대 변: {max(img.size)}"


# ─────────────────────────────────────
# Test 3 – 인쇄 장끼 Structured Output mock 파싱
# ─────────────────────────────────────

def test_3_run_ocr_parses_structured_output(monkeypatch):
    """인쇄 장끼 Structured Output mock → storeName·items 정상 파싱."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    ocr_json = _ocr_json()
    ctx = _AsyncCtx(resp=_make_api_resp(200, _api_body(ocr_json)))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    result = asyncio.run(_run())

    assert result["receipt"]["storeName"] == "테스트상회"
    assert len(result["items"]) == 1
    assert result["items"][0]["itemName"] == "상품A"
    assert result["items"][0]["color"] == "빨강"


# ─────────────────────────────────────
# Test 4 – 수기 천원 단위 → needsReview=true, "천원 단위 추정" 경고
# ─────────────────────────────────────

def test_4_handwritten_thousand_warning(monkeypatch):
    """수기 장끼 mock → needsReview=true, '천원 단위 추정' 경고 보존."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    ctx = _AsyncCtx(resp=_make_api_resp(200, _api_body(_handwritten_ocr_json())))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    result = asyncio.run(_run())
    item = result["items"][0]
    assert item["needsReview"] is True
    assert "천원 단위 추정" in item["warnings"]


# ─────────────────────────────────────
# Test 5 – OpenAI 401 → OcrError(kind="auth")
# ─────────────────────────────────────

def test_5_openai_401_raises_auth(monkeypatch):
    """OpenAI 401 응답 → OcrError(kind='auth')."""
    monkeypatch.setenv("OPENAI_API_KEY", "bad-key")

    ctx = _AsyncCtx(resp=_make_api_resp(401))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "auth"


# ─────────────────────────────────────
# Test 6 – TimeoutException → 1회 재시도 후 OcrError(kind="timeout")
# ─────────────────────────────────────

def test_6_timeout_retries_once(monkeypatch):
    """TimeoutException → 최대 1회 재시도 후 OcrError(kind='timeout')."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    ctx = _AsyncCtx(timeout_exc=True)

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "timeout"
    assert ctx._call_count == 2, f"재시도 포함 2회 호출 기대, 실제: {ctx._call_count}"


# ─────────────────────────────────────
# Test 7 – OpenAI 500 → 1회 재시도 후 OcrError(kind="server")
# ─────────────────────────────────────

def test_7_server_500_retries_once(monkeypatch):
    """OpenAI 500 응답 → 최대 1회 재시도 후 OcrError(kind='server')."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    ctx = _Always500Ctx()

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "server"
    assert ctx._call_count == 2, f"재시도 포함 2회 호출 기대, 실제: {ctx._call_count}"


# ─────────────────────────────────────
# Test 8 – 잘못된 JSON 응답 → OcrError(kind="schema")
# ─────────────────────────────────────

def test_8_invalid_json_raises_schema(monkeypatch):
    """잘못된 JSON 응답 → OcrError(kind='schema')."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    bad_resp = _make_api_resp(200, {
        "choices": [{"message": {"content": "NOT_VALID_JSON{{{"}}]
    })
    ctx = _AsyncCtx(resp=bad_resp)

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "schema"


# ─────────────────────────────────────
# Test 9 – OCR 실패 시 DB 행·배치 상태 불변
# ─────────────────────────────────────

def test_9_ocr_failure_preserves_db(isolated_runtime, monkeypatch):
    """OCR 실패 시 DB 품목·배치 상태가 변경되지 않는다 (테스트 9)."""
    monkeypatch.setenv("OPENAI_API_KEY", "bad-key")

    import logic.db as logic_db
    ensure_inbound_tables()

    batch_id = uuid.uuid4().hex
    item_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()

    with logic_db.get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, inbound_date, status, created_by, created_at, updated_at)
            VALUES (?, 'TestVendor', '2026-09-08', 'ocr_pending', 'test', ?, ?)
        """, (batch_id, now, now))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, status,
                 janggi_qty, actual_qty, missing_qty, created_at, memo)
            VALUES (?, ?, 1, '기존품목', 'confirmed', 3, 3, 0, ?, 'manual')
        """, (item_id, batch_id, now))
        con.commit()

    # OCR 401 실패 → OcrError 발생 (DB 변경 없어야 함)
    ctx = _AsyncCtx(resp=_make_api_resp(401))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "auth"

    # DB 불변 확인
    with logic_db.get_connection() as con:
        batch = con.execute(
            "SELECT status FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()
        items = con.execute(
            "SELECT COUNT(*) FROM inbound_items WHERE batch_id=?", (batch_id,)
        ).fetchone()
        item_row = con.execute(
            "SELECT item_name, status FROM inbound_items WHERE id=?", (item_id,)
        ).fetchone()

    assert batch is not None and batch[0] == "ocr_pending", "배치 상태가 바뀌면 안 된다"
    assert items[0] == 1, "기존 품목이 사라지면 안 된다"
    assert item_row is not None
    assert item_row[0] == "기존품목"
    assert item_row[1] == "confirmed"


# ─────────────────────────────────────
# Test 10 – 품목 0개 → OcrError(kind="no_items")
# ─────────────────────────────────────

def test_10_empty_items_raises_no_items(monkeypatch):
    """OCR 응답에 items=[] → OcrError(kind='no_items')."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    empty_ocr = {
        "receipt": {
            "storeName": None, "receiptNo": None, "orderDate": None,
            "totalAmount": None, "isHandwritten": False,
            "confidence": 0.5, "needsReview": True, "warnings": [],
        },
        "items": [],
    }
    ctx = _AsyncCtx(resp=_make_api_resp(200, _api_body(empty_ocr)))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            norm, mime = _normalize_image(make_jpeg())
            return await _run_ocr(norm, mime)

    with pytest.raises(OcrError) as exc_info:
        asyncio.run(_run())

    assert exc_info.value.kind == "no_items"


# ─────────────────────────────────────
# Test 11 – 성공 시에만 기존 OCR 품목 교체
# ─────────────────────────────────────

def test_11_success_replaces_ocr_items(isolated_runtime, monkeypatch):
    """OCR 성공 시 기존 OCR 품목이 교체되고 배치 상태가 confirming으로 변경된다 (테스트 11)."""
    import logic.db as logic_db
    from backend.app.api import inbound as inbound_mod

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    # 업로드 디렉터리 격리
    upload_dir = isolated_runtime["uploads"] / "inbound"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(inbound_mod, "UPLOAD_DIR", upload_dir)

    ensure_inbound_tables()

    batch_id = uuid.uuid4().hex
    old_item_id = uuid.uuid4().hex
    vendor = "TestVendor"
    now = datetime.utcnow().isoformat()

    with logic_db.get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, inbound_date, status, created_by, created_at, updated_at)
            VALUES (?, ?, '2026-09-08', 'ocr_pending', 'test', ?, ?)
        """, (batch_id, vendor, now, now))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, status,
                 janggi_qty, actual_qty, missing_qty, created_at, memo)
            VALUES (?, ?, 1, '옛날품목', 'pending', 2, 0, 0, ?, 'OCR')
        """, (old_item_id, batch_id, now))
        con.commit()

    # OCR mock – 신규 품목 1개 반환
    new_ocr = _ocr_json()
    new_ocr["items"][0]["itemName"] = "신품A"
    ctx = _AsyncCtx(resp=_make_api_resp(200, _api_body(new_ocr)))

    from backend.app.services.inbound_bot import _run_ocr_and_match
    from backend.app.api import inbound as inbound_mod

    _no_match = {
        "matched_barcode": None, "matched_vendor": None,
        "matched_product": None, "matched_option": None,
        "match_confidence": 0.0, "needs_matching": True,
    }

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx), \
             patch.object(inbound_mod, "_match_barcode", return_value=_no_match):
            return await _run_ocr_and_match(
                batch_id=batch_id,
                image_data=make_jpeg(),
                filename="test.jpg",
                vendor=vendor,
            )

    result = asyncio.run(_run())
    assert result["item_count"] == 1

    # DB 확인
    with logic_db.get_connection() as con:
        old = con.execute(
            "SELECT 1 FROM inbound_items WHERE id=?", (old_item_id,)
        ).fetchone()
        new_items = con.execute(
            "SELECT item_name FROM inbound_items WHERE batch_id=? AND memo='OCR'",
            (batch_id,),
        ).fetchall()
        batch = con.execute(
            "SELECT status FROM inbound_batches WHERE id=?", (batch_id,)
        ).fetchone()

    assert old is None, "기존 OCR 품목이 삭제돼야 한다"
    assert len(new_items) == 1, "새 OCR 품목 1개가 있어야 한다"
    assert new_items[0][0] == "신품A"
    assert batch[0] == "confirming", "배치 상태가 confirming으로 변경돼야 한다"


# ─────────────────────────────────────
# Live 테스트 (RUN_LIVE_OCR=1 환경변수 필요)
# ─────────────────────────────────────

import os as _os


# ─────────────────────────────────────
# Test 12–16 – _match_barcode: 실제 repair_barcode 스키마(제품명/상품명) 기반 매칭
# ─────────────────────────────────────

def _seed_repair_barcode(con, *, barcode, vendor, 제품명, 상품명, option, wholesale):
    """repair_barcode 테스트 행 삽입 (운영 스키마: 제품명/상품명/도매처 등)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS repair_barcode (
            바코드 TEXT, 업체명 TEXT, 제품명 TEXT, 옵션 TEXT,
            상품코드 TEXT, 로케이션 TEXT, 상품명 TEXT,
            출처 TEXT, 저장시간 TEXT, 도매처 TEXT
        )
    """)
    con.execute(
        "INSERT INTO repair_barcode VALUES (?,?,?,?,NULL,NULL,?,NULL,NULL,?)",
        (barcode, vendor, 제품명, option, 상품명, wholesale),
    )
    con.commit()


def test_12_match_by_제품명_option_exact(isolated_runtime):
    """1순위: 업체명+도매처+제품명+옵션 정확 매칭."""
    import logic.db as logic_db
    from backend.app.api.inbound import _match_barcode, ensure_inbound_tables

    ensure_inbound_tables()
    with logic_db.get_connection() as con:
        _seed_repair_barcode(
            con, barcode="BC001", vendor="테스트화주",
            제품명="제이가방", 상품명="제이가방 긴상품명", option="검정", wholesale="NODI",
        )

    result = _match_barcode("테스트화주", "제이가방", "검정", "NODI")
    assert result["matched_barcode"] == "BC001"
    assert result["match_confidence"] == 1.0
    assert result["needs_matching"] is False


def test_13_match_by_제품명_no_option(isolated_runtime):
    """2순위: 업체명+도매처+제품명 정확 매칭 (옵션 무시)."""
    import logic.db as logic_db
    from backend.app.api.inbound import _match_barcode, ensure_inbound_tables

    ensure_inbound_tables()
    with logic_db.get_connection() as con:
        _seed_repair_barcode(
            con, barcode="BC002", vendor="테스트화주",
            제품명="제이가방", 상품명="제이가방 긴상품명", option="아이", wholesale="NODI",
        )

    result = _match_barcode("테스트화주", "제이가방", None, "NODI")
    assert result["matched_barcode"] == "BC002"
    assert result["match_confidence"] == 0.85
    assert result["needs_matching"] is False


def test_14_match_by_상품명_fallback(isolated_runtime):
    """상품명(긴 이름) 컬럼으로 대체 매칭 (제품명이 다를 때)."""
    import logic.db as logic_db
    from backend.app.api.inbound import _match_barcode, ensure_inbound_tables

    ensure_inbound_tables()
    with logic_db.get_connection() as con:
        _seed_repair_barcode(
            con, barcode="BC003", vendor="테스트화주",
            제품명="짧은이름", 상품명="긴상품명전체", option=None, wholesale="NODI",
        )

    # 긴 상품명으로 검색 → 상품명 컬럼에서 일치
    result = _match_barcode("테스트화주", "긴상품명전체", None, "NODI")
    assert result["matched_barcode"] == "BC003"
    assert result["needs_matching"] is False


def test_15_match_partial_like(isolated_runtime):
    """4순위: 제품명 부분 일치(LIKE) 매칭."""
    import logic.db as logic_db
    from backend.app.api.inbound import _match_barcode, ensure_inbound_tables

    ensure_inbound_tables()
    with logic_db.get_connection() as con:
        _seed_repair_barcode(
            con, barcode="BC004", vendor="테스트화주",
            제품명="가방시리즈A", 상품명="가방시리즈A 전체상품명", option=None, wholesale=None,
        )

    result = _match_barcode("테스트화주", "가방시리즈", None, None)
    assert result["matched_barcode"] == "BC004"
    assert result["match_confidence"] == 0.5
    assert result["needs_matching"] is True  # 부분 일치는 needs_matching=True


def test_16_ocr_success_saves_inbound_items(isolated_runtime, monkeypatch):
    """OCR 성공 → inbound_items에 제품명 기반 매칭 결과 포함 저장."""
    import logic.db as logic_db
    from backend.app.api import inbound as inbound_mod
    from backend.app.api.inbound import ensure_inbound_tables
    from backend.app.services.inbound_bot import _run_ocr_and_match

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    upload_dir = isolated_runtime["uploads"] / "inbound"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(inbound_mod, "UPLOAD_DIR", upload_dir)

    ensure_inbound_tables()

    batch_id = uuid.uuid4().hex
    vendor = "테스트화주"
    now = datetime.utcnow().isoformat()

    with logic_db.get_connection() as con:
        con.execute("""
            INSERT INTO inbound_batches
                (id, vendor, inbound_date, status, created_by, created_at, updated_at)
            VALUES (?, ?, '2026-09-08', 'ocr_pending', 'test', ?, ?)
        """, (batch_id, vendor, now, now))
        # repair_barcode에 제품명 기반 행 삽입
        _seed_repair_barcode(
            con, barcode="BC_NODI_01", vendor=vendor,
            제품명="제이가방", 상품명="제이가방 긴상품명", option="검정", wholesale="NODI",
        )

    ocr_json = _ocr_json()
    ocr_json["receipt"]["storeName"] = "NODI"
    ocr_json["items"][0]["itemName"] = "제이가방"
    ocr_json["items"][0]["color"] = "검정"
    ctx = _AsyncCtx(resp=_make_api_resp(200, _api_body(ocr_json)))

    async def _run():
        with patch("httpx.AsyncClient", return_value=ctx):
            return await _run_ocr_and_match(
                batch_id=batch_id,
                image_data=make_jpeg(),
                filename="test.jpg",
                vendor=vendor,
            )

    result = asyncio.run(_run())
    assert result["item_count"] == 1

    with logic_db.get_connection() as con:
        items = con.execute(
            "SELECT item_name, matched_barcode FROM inbound_items WHERE batch_id=?",
            (batch_id,),
        ).fetchall()

    assert len(items) == 1
    assert items[0][0] == "제이가방"
    assert items[0][1] == "BC_NODI_01", "제품명 기반 바코드 매칭이 저장돼야 한다"


# ─────────────────────────────────────

@pytest.mark.skip(reason="RUN_LIVE_OCR=1 환경변수 설정 시에만 실행")
def test_live_ocr_with_real_api():
    """실제 OpenAI API 호출 (RUN_LIVE_OCR=1 및 OPENAI_API_KEY 필요)."""
    if not _os.getenv("RUN_LIVE_OCR"):
        pytest.skip("RUN_LIVE_OCR 환경변수 없음")

    async def _run():
        norm, mime = _normalize_image(make_jpeg(800, 600))
        return await _run_ocr(norm, mime)

    result = asyncio.run(_run())
    assert "receipt" in result
    assert "items" in result
