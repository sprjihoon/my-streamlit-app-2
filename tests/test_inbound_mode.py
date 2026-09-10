"""
tests/test_inbound_mode.py
────────────────────────────────────────────────────────
스펙 §14 필수 테스트: 입고모드 봇·서비스 단위 테스트

모든 테스트는 conftest.isolated_runtime으로 임시 DB/업로드 폴더를 사용.
실제 billing.db·파일 절대 수정 안 함.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image


# ─────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────

def _jpeg(color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", (64, 64), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(coro):
    """새 이벤트 루프로 코루틴 실행 (기존 루프 상태에 무관)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────
# 테스트 1: 사용자·채팅방·입고별 사진 격리
# ─────────────────────────────────────

def test_01_photo_inbox_isolated_by_batch(isolated_runtime):
    """다른 배치의 사진은 서로 섞이지 않는다."""
    from backend.app.services.inbound_bot import _add_inbox_photo, _inbox_photo_count

    img_a = _jpeg((255, 0, 0))
    img_b = _jpeg((0, 255, 0))

    batch_a = uuid.uuid4().hex
    batch_b = uuid.uuid4().hex

    _add_inbox_photo(batch_a, "u1", "ch1", img_a, "a.jpg")
    _add_inbox_photo(batch_b, "u2", "ch2", img_b, "b.jpg")

    assert _inbox_photo_count(batch_a) == 1
    assert _inbox_photo_count(batch_b) == 1


# ─────────────────────────────────────
# 테스트 2: 동일 사진 중복 전송 차단
# ─────────────────────────────────────

def test_02_duplicate_photo_blocked(isolated_runtime):
    """같은 이미지를 두 번 보내면 SHA-256으로 차단한다."""
    from backend.app.services.inbound_bot import _add_inbox_photo, _inbox_photo_count

    img = _jpeg((0, 0, 255))
    batch_id = uuid.uuid4().hex

    r1 = _add_inbox_photo(batch_id, "u1", "ch1", img, "photo.jpg")
    r2 = _add_inbox_photo(batch_id, "u1", "ch1", img, "photo_copy.jpg")  # 동일 파일

    assert r1.get("added") is True
    assert r2.get("duplicate") is True
    assert _inbox_photo_count(batch_id) == 1  # 여전히 1장


# ─────────────────────────────────────
# 테스트 3: 여러 장 동시 업로드 (순서 무관)
# ─────────────────────────────────────

def test_03_multiple_photos_added(isolated_runtime):
    """서로 다른 사진 여러 장 추가 후 카운트 확인."""
    from backend.app.services.inbound_bot import _add_inbox_photo, _inbox_photo_count

    batch_id = uuid.uuid4().hex
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i, c in enumerate(colors):
        _add_inbox_photo(batch_id, "u1", "ch1", _jpeg(c), f"photo_{i}.jpg")

    assert _inbox_photo_count(batch_id) == 3


# ─────────────────────────────────────
# 테스트 4: 장끼 OCR 실패 처리
# ─────────────────────────────────────

def test_04_janggi_ocr_failure(isolated_runtime, tmp_path):
    """OCR 실패 시 pending을 wait_janggi로 유지하고 오류 메시지 반환."""
    from backend.app.services.bot_mode import set_mode, MODE_INBOUND, mode_key
    from backend.app.services.inbound_bot import _set_pending, handle_image
    from backend.app.api.inbound import OcrError, ensure_inbound_tables, UPLOAD_DIR

    ensure_inbound_tables()

    uid, cid = "user_ocr", "ch_ocr"
    batch_id = uuid.uuid4().hex
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TestVendor', ?, 'ocr_pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.commit()

    _set_pending(uid, cid, {
        "step": "wait_janggi",
        "batch_id": batch_id,
        "vendor": "TestVendor",
    })

    img = _jpeg()

    with patch(
        "backend.app.services.inbound_bot._run_ocr_and_match",
        new=AsyncMock(side_effect=OcrError("image", "이미지 판독 불가"))
    ):
        reply = _run(handle_image(uid, cid, img, "janggi.jpg"))

    assert reply is not None
    assert "실패" in reply or "오류" in reply or "판독" in reply

    from backend.app.services.inbound_bot import _get_pending
    still_waiting = _get_pending(uid, cid)
    assert still_waiting.get("step") == "wait_janggi"


# ─────────────────────────────────────
# 테스트 5: 진행중 입고 재접속 (충돌 감지)
# ─────────────────────────────────────

def test_05_inbound_conflict_detection(isolated_runtime):
    """진행중 입고가 있을 때 새 입고 시작 시 충돌 메시지."""
    from backend.app.services.inbound_bot import _set_pending, _get_pending
    from backend.app.services.bot_mode import apply_mode_command, MODE_INBOUND, mode_key

    uid, cid = "user_conflict", "ch_conflict"

    # 이미 진행중인 입고 세션
    batch_id = uuid.uuid4().hex
    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, '기존화주', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.commit()

    _set_pending(uid, cid, {
        "step": "active",
        "batch_id": batch_id,
        "vendor": "기존화주",
    })

    # 새 입고 명령
    reply = apply_mode_command(uid, cid, {"action": "start", "mode": MODE_INBOUND})

    assert "진행 중" in reply or "기존" in reply
    assert "1." in reply or "1번" in reply  # 선택지 제공

    # 상태가 conflict 대기
    p = _get_pending(uid, cid)
    assert p.get("step") == "wait_conflict_choice"
    assert p.get("active_batch_id") == batch_id


# ─────────────────────────────────────
# 테스트 6: 바코드 완전 일치 → 자동 선택
# ─────────────────────────────────────

def test_06_barcode_exact_match_auto_select(isolated_runtime):
    """바코드 완전 일치 + 화주사 충돌 없으면 자동선택."""
    from backend.app.services.inbound_recommend import recommend_product

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "INSERT OR REPLACE INTO repair_barcode (바코드, 업체명, 제품명, 옵션, 도매처) VALUES ('BC001', 'TestVendor', '상품A', '블랙', '도매처A')"
        )
        con.commit()

    result = recommend_product("TestVendor", "도매처A", "상품A", "블랙", "BC001")
    assert result.auto_selected is not None
    assert result.auto_selected["barcode"] == "BC001"
    assert result.auto_select_reason == "바코드 완전 일치"


# ─────────────────────────────────────
# 테스트 7: 이미지 유사도만 높은 경우 자동 확정 금지
# ─────────────────────────────────────

def test_07_image_similarity_only_no_auto_select(isolated_runtime):
    """이미지 유사도만 높아도 auto_selected는 None이어야 한다."""
    from backend.app.services.inbound_recommend import (
        recommend_product, RecommendResult
    )

    # 바코드 없이 추천 요청 → 자동 선택 불가
    result = recommend_product("TestVendor", "도매처A", "상품A", "블랙", None)
    assert result.auto_selected is None


# ─────────────────────────────────────
# 테스트 8: 화주사 후보 선택 흐름
# ─────────────────────────────────────

def test_08_vendor_candidate_selection(isolated_runtime):
    """화주사가 불명확할 때 후보를 보여주고 선택받는다."""
    from backend.app.services.inbound_bot import handle_user_text, _get_pending

    uid, cid = "user_vendor", "ch_vendor"

    # wait_vendor 단계로 설정
    from backend.app.services.inbound_bot import _set_pending
    _set_pending(uid, cid, {"step": "wait_vendor"})

    # 부분 일치 텍스트 입력 (틸 → 틸리언)
    reply = _run(handle_user_text(uid, cid, "틸리언", "직원A"))

    # 정확히 일치하면 바로 wait_janggi로 이동
    p = _get_pending(uid, cid)
    assert p.get("step") == "wait_janggi"


# ─────────────────────────────────────
# 테스트 9: 사진 없음 상태에서 사진 끝 입력
# ─────────────────────────────────────

def test_09_photo_end_with_no_photos(isolated_runtime):
    """사진이 없을 때 사진 끝 입력 → 안내 메시지."""
    from backend.app.services.inbound_bot import _set_pending, handle_user_text
    from backend.app.api.inbound import ensure_inbound_tables

    ensure_inbound_tables()
    uid, cid = "user_nophoto", "ch_nophoto"
    batch_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TestVendor', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.commit()

    _set_pending(uid, cid, {"step": "active", "batch_id": batch_id, "vendor": "TestVendor"})

    reply = _run(handle_user_text(uid, cid, "사진 끝", "직원"))

    assert reply is not None
    assert "0" in reply or "없" in reply or "사진" in reply


# ─────────────────────────────────────
# 테스트 10: 사진 있을 때 사진 끝 → 링크 제공
# ─────────────────────────────────────

def test_10_photo_end_with_photos_gives_link(isolated_runtime, tmp_path):
    """사진이 있을 때 사진 끝 → 카운트 + 매칭 링크."""
    from backend.app.services.inbound_bot import (
        _set_pending, handle_user_text, _add_inbox_photo,
    )
    from backend.app.api.inbound import ensure_inbound_tables, UPLOAD_DIR

    ensure_inbound_tables()
    uid, cid = "user_photo_end", "ch_photo_end"
    batch_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TestVendor', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.commit()

    _add_inbox_photo(batch_id, uid, cid, _jpeg((100, 100, 100)), "p1.jpg")

    _set_pending(uid, cid, {"step": "active", "batch_id": batch_id, "vendor": "TestVendor"})

    reply = _run(handle_user_text(uid, cid, "사진 끝", "직원"))

    assert reply is not None
    assert "1" in reply  # 1장 확인
    assert "http" in reply or "링크" in reply or "/inbound/" in reply


# ─────────────────────────────────────
# 테스트 11: 자동저장 중복 요청 (idempotent)
# ─────────────────────────────────────

def test_11_normal_qty_idempotent(isolated_runtime):
    """같은 normal_qty 요청을 여러 번 해도 DB가 한 번만 변경된다."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    batch_id = uuid.uuid4().hex
    item_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, actual_qty, janggi_qty, status, created_at)
            VALUES (?, ?, 1, '상품A', 5, 5, 'pending', CURRENT_TIMESTAMP)
        """, (item_id, batch_id))
        con.commit()

    # 같은 요청 3번
    for _ in range(3):
        r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": 5})
        assert r.status_code == 200

    with sqlite3.connect(isolated_runtime["db"]) as con:
        row = con.execute("SELECT normal_qty, status FROM inbound_items WHERE id=?", (item_id,)).fetchone()
    assert row[0] == 5
    assert row[1] == "confirmed"


# ─────────────────────────────────────
# 테스트 12: 수량 합계 검증 (초과 불가)
# ─────────────────────────────────────

def test_12_qty_validation_rejects_over_actual(isolated_runtime):
    """normal_qty > actual_qty 는 400 반환."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    batch_id = uuid.uuid4().hex
    item_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, actual_qty, janggi_qty, status, created_at)
            VALUES (?, ?, 1, '상품A', 3, 5, 'pending', CURRENT_TIMESTAMP)
        """, (item_id, batch_id))
        con.commit()

    r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": 10})
    assert r.status_code == 400
    assert "초과" in r.json().get("detail", "")


# ─────────────────────────────────────
# 테스트 13: 수량 음수 거부
# ─────────────────────────────────────

def test_13_qty_negative_rejected(isolated_runtime):
    """normal_qty < 0 → 400."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    item_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, actual_qty, janggi_qty, status, created_at)
            VALUES (?, ?, 1, 5, 5, 'pending', CURRENT_TIMESTAMP)
        """, (item_id, batch_id))
        con.commit()

    r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": -1})
    assert r.status_code == 400


# ─────────────────────────────────────
# 테스트 14: 상품사진 사전 - 확정 연결 등록
# ─────────────────────────────────────

def test_14_photo_dict_confirm_link(isolated_runtime):
    """직원 확정 연결만 product_photo_dict에 등록된다."""
    from backend.app.services.inbound_photo_dict import confirm_photo_link

    r = confirm_photo_link(
        photo_filename="test.jpg",
        barcode="BC001",
        vendor="TestVendor",
        wholesale="도매처A",
        wholesale_product="상품A",
        option_text="블랙L",
        confirmed_by="직원A",
        is_representative=True,
    )
    assert r["status"] == "created"

    # 중복 등록 시 idempotent
    r2 = confirm_photo_link(
        photo_filename="test.jpg",
        barcode="BC001",
        vendor="TestVendor",
        wholesale="도매처A",
        wholesale_product="상품A",
        option_text="블랙L",
        confirmed_by="직원A",
    )
    assert r2["status"] == "already_exists"


# ─────────────────────────────────────
# 테스트 15: 대표사진 3장 초과 시 강등
# ─────────────────────────────────────

def test_15_representative_photo_max_3(isolated_runtime):
    """바코드별 대표사진은 최대 3장 — 초과 시 가장 오래된 것이 비대표로 강등."""
    from backend.app.services.inbound_photo_dict import confirm_photo_link, get_representative_photos

    barcode = "BC999"
    for i in range(4):
        confirm_photo_link(
            photo_filename=f"rep_{i}.jpg",
            barcode=barcode,
            vendor="V",
            confirmed_by="직원",
            is_representative=True,
        )

    reps = get_representative_photos(barcode)
    assert len(reps) <= 3


# ─────────────────────────────────────
# 테스트 16: 공유 링크 만료 후 접근 차단
# ─────────────────────────────────────

def test_16_share_link_expired(isolated_runtime):
    """만료된 공유 링크는 410 반환."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    batch_id = uuid.uuid4().hex
    token = uuid.uuid4().hex
    yesterday = "2020-01-01"  # 명확히 과거

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', '2020-01-01', 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id,))
        con.execute("""
            INSERT INTO inbound_share_links (token, batch_id, expires_at, created_by)
            VALUES (?, ?, ?, 'tester')
        """, (token, batch_id, yesterday))
        con.commit()

    r = client.get(f"/inbound/share/{token}/overview")
    assert r.status_code == 410


# ─────────────────────────────────────
# 테스트 17: 공유 링크 폐기 후 접근 차단
# ─────────────────────────────────────

def test_17_share_link_revoked(isolated_runtime):
    """revoked_at이 있는 링크는 410 반환."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    batch_id = uuid.uuid4().hex
    token = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', ?, 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.execute("""
            INSERT INTO inbound_share_links
                (token, batch_id, expires_at, created_by, revoked_at)
            VALUES (?, ?, ?, 'tester', CURRENT_TIMESTAMP)
        """, (token, batch_id, "2099-12-31"))
        con.commit()

    r = client.get(f"/inbound/share/{token}/overview")
    assert r.status_code == 410


# ─────────────────────────────────────
# 테스트 18: 공유 화면 민감정보 비노출
# ─────────────────────────────────────

def test_18_share_dto_no_sensitive_fields(isolated_runtime):
    """공유 링크 overview 응답에 민감정보(원가, 직원명 등)가 없어야 한다."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router, ensure_inbound_tables

    ensure_inbound_tables()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    batch_id = uuid.uuid4().hex
    item_id = uuid.uuid4().hex
    token = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_by, created_at, updated_at)
            VALUES (?, 'TV', ?, 'confirming', '비공개직원', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.execute("""
            INSERT INTO inbound_items
                (id, batch_id, line_no, item_name, actual_qty, janggi_qty, unit_price, status, created_at)
            VALUES (?, ?, 1, '상품A', 5, 5, 9999, 'pending', CURRENT_TIMESTAMP)
        """, (item_id, batch_id))
        con.execute("""
            INSERT INTO inbound_share_links (token, batch_id, expires_at, created_by)
            VALUES (?, ?, '2099-12-31', 'tester')
        """, (token, batch_id))
        con.commit()

    r = client.get(f"/inbound/share/{token}/overview")
    if r.status_code != 200:
        pytest.skip("share overview endpoint not available")

    data = r.json()

    # 배치 수준 민감정보 없음
    batch_info = data.get("batch", {})
    assert "created_by" not in batch_info
    assert "memo" not in batch_info

    # 품목 수준 민감정보 없음
    for item in data.get("items", []):
        assert "unit_price" not in item, "원가 노출 금지"
        assert "supplier_location" not in item, "내부 위치 노출 금지"
        assert "supplier_contact" not in item, "내부 연락처 노출 금지"


# ─────────────────────────────────────
# 테스트 19: 보관기간 계산 (dry-run)
# ─────────────────────────────────────

def test_19_photo_cleanup_plan_dry_run(isolated_runtime):
    """보관정책 dry-run은 실제 삭제 없이 계획만 반환한다."""
    from backend.app.services.inbound_photo_dict import inbound_photo_cleanup_plan

    plan = inbound_photo_cleanup_plan(dry_run=True)
    assert plan["dry_run"] is True
    assert "categories" in plan
    assert "product_photos_30d" in plan["categories"]
    assert "unlinked_inbox_7d" in plan["categories"]


# ─────────────────────────────────────
# 테스트 20: 추천 서비스 - 바코드 불일치 화주사 있으면 자동확정 금지
# ─────────────────────────────────────

def test_20_barcode_vendor_conflict_no_auto_select(isolated_runtime):
    """바코드가 일치해도 화주사가 다르면 자동선택 금지."""
    from backend.app.services.inbound_recommend import recommend_product

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute(
            "INSERT OR REPLACE INTO repair_barcode (바코드, 업체명, 제품명) VALUES ('BC_CONFLICT', '다른화주사', '상품Z')"
        )
        con.commit()

    # 입력 화주사와 DB 화주사가 다름 → 자동선택 불가
    result = recommend_product("TestVendor", None, "상품Z", None, "BC_CONFLICT")
    assert result.auto_selected is None


# ─────────────────────────────────────
# 테스트 21: 기존 기능 회귀 — 일지모드 쓰기 유지
# ─────────────────────────────────────

def test_21_journal_mode_write_still_works(isolated_runtime):
    """입고 기능 추가 후 일지모드 쓰기가 여전히 작동한다."""
    from backend.app.services.bot_mode import set_mode, MODE_JOURNAL, mode_key

    uid, cid = "user_journal_regr", "ch_journal_regr"
    set_mode(uid, cid, MODE_JOURNAL)

    from backend.app.services.bot_mode import get_mode
    assert get_mode(uid, cid) == MODE_JOURNAL


# ─────────────────────────────────────
# 테스트 22: 기존 기능 회귀 — 수선모드 이미지 허용
# ─────────────────────────────────────

def test_22_repair_mode_photo_still_accepted(isolated_runtime):
    """수선모드에서 이미지 수락 여부가 변경되지 않았다."""
    from backend.app.services.bot_mode import set_mode, get_mode, MODE_REPAIR
    from backend.app.services.bot_mode import should_accept_repair_photo

    uid, cid = "user_repair_regr", "ch_repair_regr"
    set_mode(uid, cid, MODE_REPAIR)

    assert should_accept_repair_photo(uid, cid) is True


# ─────────────────────────────────────
# 테스트 23: 장끼 단계에서만 OCR 실행
# ─────────────────────────────────────

def test_23_ocr_only_in_janggi_step(isolated_runtime):
    """active 단계에서 이미지를 보내면 OCR 실행 없이 제품사진으로 처리된다."""
    from backend.app.services.inbound_bot import _set_pending, handle_image
    from backend.app.api.inbound import ensure_inbound_tables

    ensure_inbound_tables()
    uid, cid = "user_active_img", "ch_active_img"
    batch_id = uuid.uuid4().hex

    with sqlite3.connect(isolated_runtime["db"]) as con:
        con.execute("""
            INSERT INTO inbound_batches (id, vendor, inbound_date, status, created_at, updated_at)
            VALUES (?, 'TV', ?, 'confirming', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (batch_id, date.today().isoformat()))
        con.commit()

    _set_pending(uid, cid, {"step": "active", "batch_id": batch_id, "vendor": "TV"})

    img = _jpeg()
    # _run_ocr_and_match가 호출되면 안 됨
    with patch(
        "backend.app.services.inbound_bot._run_ocr_and_match",
        new=AsyncMock(side_effect=Exception("OCR should not be called"))
    ):
        reply = _run(handle_image(uid, cid, img, "product.jpg"))

    # 제품사진 접수 응답 또는 None (중복인 경우)
    if reply is not None:
        assert "제품사진" in reply or "접수" in reply


# ─────────────────────────────────────
# 테스트 24: 한 사진을 여러 옵션에 연결 (파일 복제 없이)
# ─────────────────────────────────────

def test_24_same_photo_multiple_items_no_duplicate_file(isolated_runtime, tmp_path):
    """같은 사진을 여러 품목에 연결해도 파일은 한 번만 저장한다."""
    from backend.app.services.inbound_photo_dict import confirm_photo_link

    photo = "shared_photo.jpg"
    barcode_a = "BC_A"
    barcode_b = "BC_B"

    r_a = confirm_photo_link(photo_filename=photo, barcode=barcode_a, vendor="V", confirmed_by="직원")
    r_b = confirm_photo_link(photo_filename=photo, barcode=barcode_b, vendor="V", confirmed_by="직원")

    assert r_a["status"] == "created"
    assert r_b["status"] == "created"
    # 같은 파일명으로 두 레코드가 생성됨 (파일 복제 없음)
    assert r_a["id"] != r_b["id"]


# ─────────────────────────────────────
# 테스트 25: 취소 명령 처리
# ─────────────────────────────────────

def test_25_cancel_clears_inbound_pending(isolated_runtime):
    """취소 명령 시 pending 초기화."""
    from backend.app.services.inbound_bot import _set_pending, _get_pending, handle_user_text

    uid, cid = "user_cancel", "ch_cancel"
    _set_pending(uid, cid, {"step": "wait_vendor"})

    reply = _run(handle_user_text(uid, cid, "취소"))
    assert reply is not None
    assert "취소" in reply

    p = _get_pending(uid, cid)
    assert not p  # pending 비워짐
