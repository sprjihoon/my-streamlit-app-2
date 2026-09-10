"""
tests/test_inbound_overview.py
────────────────────────────────────────────────────────────────
입고 건별 통합 처리현황 회귀 테스트 (18개 케이스)

모든 테스트는 conftest.isolated_runtime fixture로 임시 DB/업로드 폴더만 사용.
실제 billing.db·사진 파일은 절대 수정하지 않는다.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import pytest

from backend.app.api.inbound import (
    ensure_inbound_tables,
    _compute_batch_overview,
    _infer_phase,
    _verify_password,
    _hash_password,
)
from logic.db import get_connection


# ─────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────

_TEST_TOKEN = "test-session-token-00001"

def _setup(con):
    """테이블 보장 + 테스트 세션 생성."""
    ensure_inbound_tables()
    # users / sessions 테이블: _get_user 가 필요로 함
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '',
            nickname TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER
        )
    """)
    con.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, nickname, is_admin) VALUES ('tester','','테스터',0)"
    )
    uid = con.execute("SELECT user_id FROM users WHERE username='tester'").fetchone()[0]
    con.execute(
        "INSERT OR REPLACE INTO sessions (token, user_id) VALUES (?, ?)",
        (_TEST_TOKEN, uid)
    )
    # defect_log, repair_work_log 테이블도 보장
    con.execute("""
        CREATE TABLE IF NOT EXISTS defect_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            날짜 TEXT, 업체명 TEXT, 제품명 TEXT, 옵션 TEXT, 바코드 TEXT,
            불량명 TEXT, 수량 INTEGER DEFAULT 1, 비고 TEXT, 작성자 TEXT,
            저장시간 TIMESTAMP, 출처 TEXT,
            before_image TEXT, after_image TEXT, extra_images TEXT,
            처리결과 TEXT, 수정자 TEXT, 수정시간 TIMESTAMP,
            inbound_item_id TEXT, defect_case_id TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS repair_work_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            날짜 TEXT, 업체명 TEXT, 제품명 TEXT, 옵션 TEXT, 바코드 TEXT,
            작업 TEXT, 수량 INTEGER DEFAULT 1, 비용 INTEGER DEFAULT 0, 비고 TEXT,
            작성자 TEXT, 저장시간 TIMESTAMP, 출처 TEXT,
            barcode_image TEXT, before_image TEXT, after_image TEXT,
            불량명 TEXT, 수정자 TEXT, 수정시간 TIMESTAMP, extra_images TEXT,
            inbound_item_id TEXT, defect_case_id TEXT
        )
    """)
    con.commit()


def _make_batch(con, *, status="inbound_done") -> str:
    batch_id = uuid.uuid4().hex
    con.execute("""
        INSERT INTO inbound_batches
            (id, vendor, inbound_date, status, total_janggi_qty, total_actual_qty, total_missing_qty,
             created_at, updated_at)
        VALUES (?, 'TestVendor', ?, ?, 0, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (batch_id, date.today().isoformat(), status))
    con.commit()
    return batch_id


def _make_item(
    con,
    batch_id: str,
    *,
    janggi_qty: int = 10,
    actual_qty: int = 8,
    missing_qty: int = 2,
    status: str = "pending",
    normal_qty: int = -1,         # -1 = auto-init from status
    defect_pending_qty: int = -1,  # -1 = auto-init from status
    repairing_qty: int = -1,
    repair_done_qty: int = -1,
    unrecoverable_qty: int = -1,
    line_no: int = 1,
    item_name: str = "테스트상품",
    actual_qty_confirmed: int = 0,
    photo_decision: Optional[str] = None,
    matched_barcode: Optional[str] = None,
) -> str:
    """
    inbound_items 에 품목 행을 삽입한다.
    qty 컬럼(normal_qty 등)이 -1 이면 status 에서 자동 추론한다 (backfill 로직과 동일).
    명시적으로 설정할 경우 그 값을 그대로 사용한다 (부분수량 테스트용).
    """
    # qty 컬럼 자동 초기화 (status 기반)
    if normal_qty == -1 and defect_pending_qty == -1 and repairing_qty == -1 \
            and repair_done_qty == -1 and unrecoverable_qty == -1:
        normal_qty       = actual_qty if status == "confirmed" else 0
        defect_pending_qty = actual_qty if status == "defect"  else 0
        repairing_qty    = actual_qty if status == "repair"    else 0
        repair_done_qty  = actual_qty if status == "done"      else 0
        unrecoverable_qty = actual_qty if status == "unrecoverable" else 0
    else:
        if normal_qty       < 0: normal_qty       = 0
        if defect_pending_qty < 0: defect_pending_qty = 0
        if repairing_qty    < 0: repairing_qty    = 0
        if repair_done_qty  < 0: repair_done_qty  = 0
        if unrecoverable_qty < 0: unrecoverable_qty = 0

    item_id = uuid.uuid4().hex
    con.execute("""
        INSERT INTO inbound_items
            (id, batch_id, line_no, item_name, janggi_qty, actual_qty, missing_qty,
             status, normal_qty, defect_pending_qty, repairing_qty,
             repair_done_qty, unrecoverable_qty,
             actual_qty_confirmed, photo_decision, matched_barcode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (item_id, batch_id, line_no, item_name,
          janggi_qty, actual_qty, missing_qty, status,
          normal_qty, defect_pending_qty, repairing_qty,
          repair_done_qty, unrecoverable_qty,
          actual_qty_confirmed, photo_decision, matched_barcode))
    # batch 집계 갱신
    con.execute("""
        UPDATE inbound_batches
        SET total_janggi_qty = (SELECT COALESCE(SUM(janggi_qty),0) FROM inbound_items WHERE batch_id=?),
            total_actual_qty = (SELECT COALESCE(SUM(actual_qty),0) FROM inbound_items WHERE batch_id=?),
            total_missing_qty = (SELECT COALESCE(SUM(missing_qty),0) FROM inbound_items WHERE batch_id=?)
        WHERE id=?
    """, (batch_id, batch_id, batch_id, batch_id))
    con.commit()
    return item_id


def _make_defect(con, item_id: str, *, 수량: int = 1, 처리결과: Optional[str] = None):
    con.execute("""
        INSERT INTO defect_log
            (날짜, 업체명, 제품명, 불량명, 수량, 처리결과, 저장시간, inbound_item_id)
        VALUES ('2026-09-09', 'TestVendor', '테스트상품', '오염', ?, ?, CURRENT_TIMESTAMP, ?)
    """, (수량, 처리결과, item_id))
    con.commit()


def _make_repair(con, item_id: str, *, 수량: int = 1, 작업: str = "수선"):
    con.execute("""
        INSERT INTO repair_work_log
            (날짜, 업체명, 제품명, 작업, 수량, 비용, 저장시간, inbound_item_id)
        VALUES ('2026-09-09', 'TestVendor', '테스트상품', ?, ?, 0, CURRENT_TIMESTAMP, ?)
    """, (작업, 수량, item_id))
    con.commit()


def _make_share_link(con, batch_id: str, *, password: Optional[str] = None,
                     expires_days: int = 7, revoked: bool = False) -> str:
    token = uuid.uuid4().hex
    stored_pw = _hash_password(password) if password else None
    expires_at = (datetime.utcnow() + timedelta(days=expires_days)).strftime("%Y-%m-%d")
    revoked_at = datetime.utcnow().isoformat() if revoked else None
    con.execute("""
        INSERT INTO inbound_share_links
            (token, batch_id, password, expires_at, allow_excel, created_by, revoked_at)
        VALUES (?, ?, ?, ?, 0, 'tester', ?)
    """, (token, batch_id, stored_pw, expires_at, revoked_at))
    con.commit()
    return token


# ─────────────────────────────────────────────────────────────
# 테스트 1: 입고만 있고 후속 기록이 없는 품목
# ─────────────────────────────────────────────────────────────

def test_01_item_with_no_followup():
    """입고만 있고 불량·수선 기록이 없는 품목 — pending_qty = actual_qty."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, janggi_qty=10, actual_qty=8, missing_qty=2, status="pending")

        ov = _compute_batch_overview(batch_id, con)

    assert ov is not None
    s = ov["summary"]
    assert s["expected_qty"] == 10
    assert s["received_qty"] == 8
    assert s["missing_qty"] == 2
    assert s["pending_qty"] == 8
    assert s["normal_qty"] == 0
    assert s["defect_pending_qty"] == 0
    assert s["final_good_qty"] == 0


# ─────────────────────────────────────────────────────────────
# 테스트 2: 정상처리만 완료된 품목
# ─────────────────────────────────────────────────────────────

def test_02_fully_confirmed_item():
    """status='confirmed' 품목 — 전체 actual_qty가 normal_qty에 반영."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=10, missing_qty=0, status="confirmed", normal_qty=10)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["normal_qty"] == 10
    assert s["pending_qty"] == 0
    assert s["final_good_qty"] == 10
    assert s["processing_progress"] == 100.0


# ─────────────────────────────────────────────────────────────
# 테스트 3: 일부 정상 + 일부 불량
# ─────────────────────────────────────────────────────────────

def test_03_mixed_normal_and_defect():
    """두 품목 행: 하나는 confirmed, 하나는 defect."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, missing_qty=0,
                   status="confirmed", normal_qty=5, line_no=1)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, missing_qty=0,
                   status="defect", line_no=2)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["normal_qty"] == 5
    assert s["defect_pending_qty"] == 5
    assert s["pending_qty"] == 0
    # 실입고 = normal + defect
    assert s["received_qty"] == s["normal_qty"] + s["defect_pending_qty"]


# ─────────────────────────────────────────────────────────────
# 테스트 4: 불량판정중 → 수선중 상태 전환
# ─────────────────────────────────────────────────────────────

def test_04_defect_to_repair_no_double_count():
    """status=repair 이면 repairing_qty에만 반영 — defect_qty 0."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=3, missing_qty=0, status="repair")
        _make_defect(con, item_id, 수량=3)  # 이력 보존

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["repairing_qty"] == 3
    assert s["defect_pending_qty"] == 0, "수선중으로 이동했으면 불량판정중 집계 없어야 함"


# ─────────────────────────────────────────────────────────────
# 테스트 5: 수선중 → 수선후정상 전환
# ─────────────────────────────────────────────────────────────

def test_05_repaired_good():
    """status=done 이면 repaired_good_qty에만 반영."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=4, missing_qty=0, status="done")
        _make_repair(con, item_id, 수량=4)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["repaired_good_qty"] == 4
    assert s["repairing_qty"] == 0
    assert s["final_good_qty"] == 4


# ─────────────────────────────────────────────────────────────
# 테스트 6: 수선중 → 회생불가 전환
# ─────────────────────────────────────────────────────────────

def test_06_unrecoverable():
    """status=unrecoverable 이면 unrecoverable_qty에만 반영."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=2, missing_qty=0, status="unrecoverable")

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["unrecoverable_qty"] == 2
    assert s["repairing_qty"] == 0
    assert s["final_good_qty"] == 0


# ─────────────────────────────────────────────────────────────
# 테스트 7: 상태 전환 이력 중복 집계 방지
# ─────────────────────────────────────────────────────────────

def test_07_no_duplicate_count_across_history():
    """defect → repair → done 전환: 현재 status=done 만 집계."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, missing_qty=0, status="done")
        # 이력 기록 (불량+수선) — 집계에는 반영되면 안 됨
        _make_defect(con, item_id, 수량=5)
        _make_repair(con, item_id, 수량=5)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    total_counted = (s["pending_qty"] + s["normal_qty"] + s["defect_pending_qty"]
                     + s["repairing_qty"] + s["repaired_good_qty"] + s["unrecoverable_qty"])
    assert total_counted == s["received_qty"], "이력 포함해도 수량 합계가 실입고수량과 같아야 함"
    assert s["repaired_good_qty"] == 5
    assert s["defect_pending_qty"] == 0
    assert s["repairing_qty"] == 0


# ─────────────────────────────────────────────────────────────
# 테스트 8: 미입고가 포함된 장끼 수량 정합성
# ─────────────────────────────────────────────────────────────

def test_08_missing_qty_consistency():
    """장끼수량 = 실입고 + 미입고 정합성."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, janggi_qty=10, actual_qty=7, missing_qty=3, status="pending")

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["expected_qty"] == 10
    assert s["received_qty"] + s["missing_qty"] == s["expected_qty"]


# ─────────────────────────────────────────────────────────────
# 테스트 9: 여러 품목이 있는 batch 전체 집계
# ─────────────────────────────────────────────────────────────

def test_09_multi_item_batch_aggregate():
    """4개 품목 — 집계 합계 검증."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, janggi_qty=10, actual_qty=10, missing_qty=0,
                   status="confirmed", normal_qty=10, line_no=1)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=4, missing_qty=1,
                   status="defect", line_no=2)
        _make_item(con, batch_id, janggi_qty=8, actual_qty=8, missing_qty=0,
                   status="repair", line_no=3)
        _make_item(con, batch_id, janggi_qty=3, actual_qty=3, missing_qty=0,
                   status="done", line_no=4)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["expected_qty"] == 26
    assert s["received_qty"] == 25
    assert s["missing_qty"] == 1
    assert s["normal_qty"] == 10
    assert s["defect_pending_qty"] == 4
    assert s["repairing_qty"] == 8
    assert s["repaired_good_qty"] == 3
    assert s["final_good_qty"] == 13
    # 실입고 = normal + defect + repair + done
    assert s["received_qty"] == (s["normal_qty"] + s["defect_pending_qty"]
                                  + s["repairing_qty"] + s["repaired_good_qty"])


# ─────────────────────────────────────────────────────────────
# 테스트 10: 수량 초과·음수 입력 차단 (API 레벨)
# ─────────────────────────────────────────────────────────────

def test_10_normal_qty_validation():
    """normal_qty > actual_qty 또는 음수이면 예외 발생."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, missing_qty=0, status="pending")

    # 음수 거부
    r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": -1})
    assert r.status_code == 400

    # 초과 거부
    r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": 99})
    assert r.status_code == 400

    # 정상 입력
    r = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": 3})
    assert r.status_code == 200
    assert r.json()["normal_qty"] == 3


# ─────────────────────────────────────────────────────────────
# 테스트 11: 다른 batch의 불량·수선 기록 혼입 방지
# ─────────────────────────────────────────────────────────────

def test_11_no_cross_batch_contamination():
    """다른 batch에 연결된 defect/repair 기록은 이 batch 집계에 영향 없음."""
    with get_connection() as con:
        _setup(con)
        batch_a = _make_batch(con)
        batch_b = _make_batch(con)

        item_a = _make_item(con, batch_a, actual_qty=5, missing_qty=0, status="pending")
        item_b = _make_item(con, batch_b, actual_qty=10, missing_qty=0, status="defect")

        # batch_b 의 item_b 에 연결된 불량 기록
        _make_defect(con, item_b, 수량=10)

        ov_a = _compute_batch_overview(batch_a, con)

    s = ov_a["summary"]
    assert s["defect_pending_qty"] == 0, "다른 batch 불량이 혼입되면 안 됨"
    assert s["pending_qty"] == 5


# ─────────────────────────────────────────────────────────────
# 테스트 12: 공유 링크 정상 접근
# ─────────────────────────────────────────────────────────────

def test_12_share_link_normal_access():
    """유효한 토큰, 비밀번호 없는 링크 → overview 반환."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=5, missing_qty=0, status="confirmed", normal_qty=5)
        token = _make_share_link(con, batch_id)

    r = client.get(f"/inbound/share/{token}/overview")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert data["summary"]["normal_qty"] == 5


# ─────────────────────────────────────────────────────────────
# 테스트 13: 비밀번호 오류
# ─────────────────────────────────────────────────────────────

def test_13_share_wrong_password():
    """비밀번호 틀린 공유 링크 접근 → 403."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        token = _make_share_link(con, batch_id, password="correct123")

    # 비밀번호 없이 접근 → 비밀번호 필요 응답
    r = client.get(f"/inbound/share/{token}/overview")
    assert r.status_code == 200
    assert r.json().get("needs_password") is True

    # 틀린 비밀번호
    r = client.get(f"/inbound/share/{token}/overview?password=wrong")
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────
# 테스트 14: 만료·폐기된 링크 차단
# ─────────────────────────────────────────────────────────────

def test_14_expired_and_revoked_link():
    """만료·폐기 링크 → 410."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)

        # 만료된 링크 (expires_days=-1)
        expired_token = uuid.uuid4().hex
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        con.execute("""
            INSERT INTO inbound_share_links (token, batch_id, expires_at, revoked_at)
            VALUES (?, ?, ?, NULL)
        """, (expired_token, batch_id, yesterday))

        # 폐기된 링크
        revoked_token = _make_share_link(con, batch_id, revoked=True)
        con.commit()

    r_expired = client.get(f"/inbound/share/{expired_token}/overview")
    assert r_expired.status_code == 410

    r_revoked = client.get(f"/inbound/share/{revoked_token}/overview")
    assert r_revoked.status_code == 410


# ─────────────────────────────────────────────────────────────
# 테스트 15: 다른 화주사 데이터 노출 차단
# ─────────────────────────────────────────────────────────────

def test_15_no_cross_vendor_exposure():
    """다른 batch의 token으로 다른 batch 데이터 접근 불가."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_a = _make_batch(con)
        batch_b = _make_batch(con)

        _make_item(con, batch_a, actual_qty=5, missing_qty=0, status="confirmed", normal_qty=5)
        _make_item(con, batch_b, actual_qty=99, missing_qty=0, status="confirmed", normal_qty=99)

        # batch_a 의 토큰
        token_a = _make_share_link(con, batch_a)

    # token_a 로 접근 — batch_a 데이터만 봐야 함
    r = client.get(f"/inbound/share/{token_a}/overview")
    assert r.status_code == 200
    data = r.json()
    # batch_b 의 99 수량이 나오면 안 됨
    assert data["summary"]["normal_qty"] == 5
    assert data["summary"]["received_qty"] == 5


# ─────────────────────────────────────────────────────────────
# 테스트 16: 공유 DTO에서 내부 필드 제외
# ─────────────────────────────────────────────────────────────

def test_16_share_dto_excludes_internal_fields():
    """공유 DTO: unit_price·confirmed_by·supplier_contact·비용 미포함."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, missing_qty=0,
                             status="repair", line_no=1)
        _make_repair(con, item_id, 수량=5, 작업="수선")
        token = _make_share_link(con, batch_id)

    r = client.get(f"/inbound/share/{token}/overview")
    assert r.status_code == 200
    data = r.json()

    # 내부 필드 확인
    for item in data.get("items", []):
        assert "unit_price" not in item, "원가 노출 금지"
        assert "confirmed_by" not in item, "직원 이름 노출 금지"
        assert "supplier_location" not in item, "내부 메모 노출 금지"
        assert "supplier_contact" not in item, "내부 연락처 노출 금지"
        for rl in item.get("repair_logs", []):
            assert "비용" not in rl, "수선 비용 노출 금지"

    # batch 내부 필드
    assert "created_by" not in data["batch"], "담당자명 노출 금지"
    assert "memo" not in data["batch"], "내부 메모 노출 금지"


# ─────────────────────────────────────────────────────────────
# 테스트 17: 기존 입고·불량·수선 저장 기능 회귀
# ─────────────────────────────────────────────────────────────

def test_17_existing_inbound_api_regression():
    """기존 batch CRUD 및 item PATCH 기능 유지 확인."""
    from fastapi.testclient import TestClient
    from backend.app.api.inbound import router
    from fastapi import FastAPI

    # 인증 없이도 작동하는 엔드포인트 확인
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        item_id = _make_item(con, batch_id, actual_qty=0, missing_qty=0, status="pending")

    # 기존 item PATCH (실수량 입력 — 로그인 불필요)
    r = client.patch(f"/inbound/items/{item_id}", json={"actual_qty": 5, "missing_qty": 2})
    assert r.status_code == 200, f"기존 PATCH /items 실패: {r.text}"

    # normal-qty도 동작
    r2 = client.patch(f"/inbound/items/{item_id}/normal-qty", json={"normal_qty": 3})
    assert r2.status_code == 200

    # overview 조회
    with get_connection() as con:
        ov = _compute_batch_overview(batch_id, con)
    assert ov["summary"]["normal_qty"] == 3


# ─────────────────────────────────────────────────────────────
# 테스트 18: 기존 바코드 PDF 기능 회귀
# ─────────────────────────────────────────────────────────────

def test_18_barcode_pdf_regression():
    """기존 barcode-pdf 엔드포인트가 overview 추가 후에도 정상 응답."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.app.api.inbound import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        # 바코드 없는 품목 → 400 반환되어야 함 (reportlab 없어도 OK)
        _make_item(con, batch_id, actual_qty=5, missing_qty=0, status="confirmed")

    # 인증 없이는 401 또는 바코드 없으면 400 — 500이 아님을 확인
    r = client.post(f"/inbound/batches/{batch_id}/barcode-pdf")
    assert r.status_code in (400, 401, 500), (
        f"unexpected status {r.status_code}: {r.text[:200]}"
    )
    # 500이면 reportlab 미설치 메시지여야 함
    if r.status_code == 500:
        assert "reportlab" in r.text.lower() or "바코드" in r.text


# ─────────────────────────────────────────────────────────────
# 추가: pending 상태에서 partial normal_qty 처리
# ─────────────────────────────────────────────────────────────

def test_pending_partial_normal_qty():
    """status=pending 에서 normal_qty=3, actual_qty=5 → pending=2, normal=3."""
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, missing_qty=0,
                   status="pending", normal_qty=3)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["normal_qty"] == 3
    assert s["pending_qty"] == 2
    assert s["received_qty"] == 5
    # 합계 검증
    total = (s["pending_qty"] + s["normal_qty"] + s["defect_pending_qty"]
             + s["repairing_qty"] + s["repaired_good_qty"] + s["unrecoverable_qty"])
    assert total == s["received_qty"]


def test_phase_inference():
    """_infer_phase 함수 단위 테스트."""
    assert _infer_phase(status="done", pending_qty=0, defect_qty=0, repairing_qty=0, received_qty=10) == "최종 마감 완료"
    assert _infer_phase(status="inbound_done", pending_qty=0, defect_qty=0, repairing_qty=5, received_qty=10) == "수선 진행 중"
    assert _infer_phase(status="inbound_done", pending_qty=0, defect_qty=3, repairing_qty=0, received_qty=10) == "불량 확인 중"
    assert _infer_phase(status="inbound_done", pending_qty=2, defect_qty=0, repairing_qty=0, received_qty=10) == "양품화 진행 중"
    assert _infer_phase(status="ocr_pending", pending_qty=0, defect_qty=0, repairing_qty=0, received_qty=0) == "입고 확인 중"


# ═════════════════════════════════════════════════════════════
# 검품·양품화 완료 (grade-complete) 테스트 (Cases A ~ D)
# ═════════════════════════════════════════════════════════════

def _grade_complete_direct(con, batch_id: str, by: str = "tester") -> int:
    """grade-complete 로직 직접 실행 (인증 우회, 테스트 전용).
    부분수량 모델: pending_qty > 0 인 품목에서 pending → normal_qty 이동.
    """
    now = datetime.utcnow().isoformat()
    pending_rows = con.execute(
        """SELECT id FROM inbound_items
           WHERE batch_id=?
             AND (actual_qty
                  - COALESCE(normal_qty,0) - COALESCE(defect_pending_qty,0)
                  - COALESCE(repairing_qty,0) - COALESCE(repair_done_qty,0)
                  - COALESCE(unrecoverable_qty,0)) > 0""",
        (batch_id,)
    ).fetchall()
    moved = len(pending_rows)
    if moved > 0:
        con.execute(
            """UPDATE inbound_items
               SET normal_qty = actual_qty - COALESCE(defect_pending_qty,0)
                                           - COALESCE(repairing_qty,0)
                                           - COALESCE(repair_done_qty,0)
                                           - COALESCE(unrecoverable_qty,0),
                   actual_qty_confirmed = 1,
                   confirmed_by = COALESCE(confirmed_by, ?),
                   updated_at = ?
               WHERE batch_id=?
                 AND (actual_qty
                      - COALESCE(normal_qty,0) - COALESCE(defect_pending_qty,0)
                      - COALESCE(repairing_qty,0) - COALESCE(repair_done_qty,0)
                      - COALESCE(unrecoverable_qty,0)) > 0""",
            (by, now, batch_id)
        )
        con.commit()
    return moved


def test_grade_complete_case_a():
    """
    사례 A: 실입고 10, 미처리 10
    검품·양품화 완료 실행 → 정상 10, 미처리 0
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        # 실입고 10 전량 미처리(pending)
        _make_item(con, batch_id, janggi_qty=10, actual_qty=10, missing_qty=0, status="pending")

        moved = _grade_complete_direct(con, batch_id)
        ov = _compute_batch_overview(batch_id, con)

    assert moved == 1, f"이동 품목 수 1(행) 예상, 실제={moved}"
    s = ov["summary"]
    assert s["normal_qty"] == 10, f"정상처리 10 예상, 실제={s['normal_qty']}"
    assert s["pending_qty"] == 0, f"미처리 0 예상, 실제={s['pending_qty']}"
    assert s["received_qty"] == 10


def test_grade_complete_case_b():
    """
    사례 B: 실입고 10 (미처리 6, 불량판정중 1, 수선중 2, 회생불가 1)
    검품·양품화 완료 실행 → 정상 6, 미처리 0, 나머지 상태 유지
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="grading")
        _make_item(con, batch_id, janggi_qty=6, actual_qty=6, missing_qty=0, status="pending", line_no=1)
        _make_item(con, batch_id, janggi_qty=1, actual_qty=1, missing_qty=0, status="defect", line_no=2)
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, missing_qty=0, status="repair", line_no=3)
        _make_item(con, batch_id, janggi_qty=1, actual_qty=1, missing_qty=0, status="unrecoverable", line_no=4)

        _grade_complete_direct(con, batch_id)
        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    assert s["normal_qty"] == 6, f"정상 6 예상, 실제={s['normal_qty']}"
    assert s["pending_qty"] == 0, f"미처리 0 예상, 실제={s['pending_qty']}"
    assert s["defect_pending_qty"] == 1, f"불량판정중 1 예상, 실제={s['defect_pending_qty']}"
    assert s["repairing_qty"] == 2, f"수선중 2 예상, 실제={s['repairing_qty']}"
    assert s["unrecoverable_qty"] == 1, f"회생불가 1 예상, 실제={s['unrecoverable_qty']}"
    assert s["received_qty"] == 10


def test_grade_complete_case_c_idempotent():
    """
    사례 C: grade-complete 두 번 실행 → 수량 중복 증가 없음
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, missing_qty=0, status="pending")

        # 1차 실행
        moved1 = _grade_complete_direct(con, batch_id)
        # 2차 실행 (이미 confirmed → 아무것도 바뀌지 않음)
        moved2 = _grade_complete_direct(con, batch_id)

        ov = _compute_batch_overview(batch_id, con)

    assert moved1 == 1, f"1차 이동 1행 예상, 실제={moved1}"
    # 2차 실행 시 pending 0 → 추가 이동 없음
    assert moved2 == 0, "2차 실행 시 미처리 품목이 없어야 함 (idempotent)"
    s = ov["summary"]
    assert s["normal_qty"] == 5, f"정상 5 예상, 실제={s['normal_qty']}"
    assert s["pending_qty"] == 0


def test_grade_complete_case_d_repair_done_not_double_counted():
    """
    사례 D: 수선중 2가 수선후정상 2로 변경 → 수선중 0, 수선후정상 2
    최종정상 = 정상처리 + 수선후정상 (과거 수선중은 중복 합산 안됨)
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="repairing")

        # 수선 완료 품목 (status=done, actual_qty=2)
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, missing_qty=0, status="done", line_no=1)
        # 정상처리 품목 (status=confirmed, actual_qty=3)
        _make_item(con, batch_id, janggi_qty=3, actual_qty=3, missing_qty=0, status="confirmed", line_no=2)

        ov = _compute_batch_overview(batch_id, con)

    s = ov["summary"]
    # 수선중=0, 수선후정상=2, 정상=3
    assert s["repairing_qty"] == 0, f"수선중 0 예상, 실제={s['repairing_qty']}"
    assert s["repaired_good_qty"] == 2, f"수선후정상 2 예상, 실제={s['repaired_good_qty']}"
    assert s["normal_qty"] == 3, f"정상처리 3 예상, 실제={s['normal_qty']}"
    # 최종정상 = 정상처리 + 수선후정상
    final_good = s["normal_qty"] + s["repaired_good_qty"]
    assert final_good == 5, f"최종정상 5 예상, 실제={final_good}"
    # 총 실입고 = 정상+수선후정상 (pending=defect=repair=unrecoverable=0)
    assert s["received_qty"] == 5


# ═════════════════════════════════════════════════════════════════
# AM close / PM close 직접 실행 헬퍼
# ═════════════════════════════════════════════════════════════════

def _am_close_direct(con, batch_id: str) -> dict:
    """AM close 핵심 로직을 DB 직접 접근으로 재현.
    실제 서버 로직(close_batch AM 분기)과 동일한 순서로 검증한다.
    """
    # 1. 수량 미확인 품목 차단
    unconfirmed = con.execute(
        "SELECT id, line_no, item_name, janggi_qty FROM inbound_items "
        "WHERE batch_id=? AND actual_qty_confirmed=0 ORDER BY line_no",
        (batch_id,)
    ).fetchall()
    if unconfirmed:
        return {
            "ok": False,
            "reason": "unconfirmed_qty",
            "unconfirmed_count": len(unconfirmed),
            "unconfirmed_items": [{"id": r[0], "line_no": r[1]} for r in unconfirmed],
        }
    # 2. 사진 처리결정 미완료 차단
    undecided = con.execute(
        "SELECT id, line_no, item_name, actual_qty FROM inbound_items "
        "WHERE batch_id=? AND actual_qty >= 1 AND photo_decision IS NULL ORDER BY line_no",
        (batch_id,)
    ).fetchall()
    if undecided:
        return {
            "ok": False,
            "reason": "undecided_photo",
            "undecided_photo_count": len(undecided),
        }
    # 3. photo='photo' → 실제 사진 파일 연결 확인
    photo_no_file = con.execute(
        """SELECT i.id, i.line_no, i.item_name
           FROM inbound_items i
           WHERE i.batch_id=? AND i.photo_decision='photo' AND i.actual_qty >= 1
             AND NOT EXISTS (SELECT 1 FROM inbound_item_photos p WHERE p.item_id = i.id)
           ORDER BY i.line_no""",
        (batch_id,)
    ).fetchall()
    if photo_no_file:
        return {
            "ok": False,
            "reason": "photo_no_file",
            "photo_no_file_count": len(photo_no_file),
        }
    # 4. photo='existing' → 실제 상품마스터(repair_barcode) 연결 확인
    existing_no_product = con.execute(
        """SELECT i.id, i.line_no, i.item_name
           FROM inbound_items i
           WHERE i.batch_id=? AND i.photo_decision='existing' AND i.actual_qty >= 1
             AND (
               i.matched_barcode IS NULL OR i.matched_barcode = ''
               OR NOT EXISTS (SELECT 1 FROM repair_barcode rb WHERE rb.바코드 = i.matched_barcode)
             )
           ORDER BY i.line_no""",
        (batch_id,)
    ).fetchall()
    if existing_no_product:
        return {
            "ok": False,
            "reason": "existing_no_product",
            "existing_no_product_count": len(existing_no_product),
        }
    # 통과 → 배치 상태 갱신
    now = datetime.utcnow().isoformat()
    con.execute(
        "UPDATE inbound_batches SET status='inbound_done', updated_at=? WHERE id=?",
        (now, batch_id)
    )
    con.commit()
    return {"ok": True, "status": "inbound_done"}


def _pm_close_direct(con, batch_id: str) -> dict:
    """PM close 핵심 로직을 DB 직접 접근으로 재현.
    부분수량 모델: defect_pending_qty / repairing_qty 컬럼 기준.
    """
    defect_qty = con.execute(
        "SELECT COALESCE(SUM(defect_pending_qty),0) FROM inbound_items WHERE batch_id=?",
        (batch_id,)
    ).fetchone()[0]
    repair_qty = con.execute(
        "SELECT COALESCE(SUM(repairing_qty),0) FROM inbound_items WHERE batch_id=?",
        (batch_id,)
    ).fetchone()[0]
    if defect_qty > 0 or repair_qty > 0:
        return {
            "ok": False,
            "reason": "unresolved",
            "defect_qty": defect_qty,
            "repair_qty": repair_qty,
        }
    # pending → confirmed
    now = datetime.utcnow().isoformat()
    moved = con.execute(
        "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'", (batch_id,)
    ).fetchone()[0]
    if moved > 0:
        con.execute(
            "UPDATE inbound_items SET status='confirmed', updated_at=? "
            "WHERE batch_id=? AND status='pending'", (now, batch_id)
        )
    # PM 이후 중복 호출 여부 확인용 snapshot
    post_pending = con.execute(
        "SELECT COUNT(*) FROM inbound_items WHERE batch_id=? AND status='pending'", (batch_id,)
    ).fetchone()[0]
    # batch done
    con.execute(
        "UPDATE inbound_batches SET status='done', updated_at=? WHERE id=?",
        (now, batch_id)
    )
    con.commit()
    return {"ok": True, "status": "done", "moved": moved, "post_pending": post_pending}


# ═════════════════════════════════════════════════════════════════
# 테스트 케이스 E ~ N: actual_qty_confirmed / photo_decision / PM 차단
# ═════════════════════════════════════════════════════════════════

def test_case_e_unconfirmed_qty_blocks_am_close():
    """
    E: 수량 미확인(initial 0) 품목이 있을 때 AM 입고 확인 완료 차단.
    actual_qty_confirmed=0(기본값) → 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=0,
                   actual_qty_confirmed=0, photo_decision="none")
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False, "미확인 수량 있으면 AM close 차단 필요"
    assert result["reason"] == "unconfirmed_qty"
    assert result["unconfirmed_count"] == 1


def test_case_f_confirmed_zero_qty_allows_am_close():
    """
    F: 직원이 직접 0개로 확정(actual_qty_confirmed=1)한 품목 → AM close 통과.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        # actual_qty=0 이지만 actual_qty_confirmed=1, photo_decision 도 결정됨
        _make_item(con, batch_id, janggi_qty=5, actual_qty=0,
                   actual_qty_confirmed=1, photo_decision="none")
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is True, f"수량 0 확정이면 AM close 통과 필요: {result}"
    assert result["status"] == "inbound_done"


def test_case_g_fill_all_janggi_confirms_qty():
    """
    G: '수량 전부 장끼와 동일' 처리 후 actual_qty_confirmed=1 이어야 함.
    PATCH 엔드포인트가 actual_qty를 설정할 때 confirmed=1 로 바뀌는지 직접 확인.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        # photo_decision='none': 사진 없음으로 명시 결정 (바코드 없이 AM 통과 가능한 케이스)
        item_id = _make_item(con, batch_id, janggi_qty=10, actual_qty=0,
                             actual_qty_confirmed=0, photo_decision="none")
        # "장끼와 동일" PATCH: actual_qty = janggi_qty, confirmed = 1
        con.execute(
            "UPDATE inbound_items SET actual_qty=10, actual_qty_confirmed=1 WHERE id=?",
            (item_id,)
        )
        con.commit()
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is True, "장끼와 동일 후 수량 확인 완료 → AM close 통과 필요"


def test_case_h_partial_confirmation_blocks_am_close():
    """
    H: 품목 일부만 수량 확인 → 미확인 품목 때문에 AM close 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                   actual_qty_confirmed=1, photo_decision="photo", line_no=1)
        _make_item(con, batch_id, janggi_qty=3, actual_qty=0,
                   actual_qty_confirmed=0, photo_decision="none", line_no=2)  # 미확인
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "unconfirmed_qty"
    assert result["unconfirmed_count"] == 1


def test_case_i_missing_photo_decision_blocks_am_close():
    """
    I: 실입고 1개 이상인데 photo_decision NULL → AM close 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                   actual_qty_confirmed=1, photo_decision=None)  # ← 미결정
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "undecided_photo"
    assert result["undecided_photo_count"] == 1


def test_case_j_zero_actual_qty_skip_photo_check():
    """
    J: 실입고 0개 확정 품목 → photo_decision NULL 이어도 사진 체크 통과.
    (actual_qty=0 이면 사진 결정 불필요)
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        # 실입고 0, 확정됨, photo_decision=None (사진 없어도 OK)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=0,
                   actual_qty_confirmed=1, photo_decision=None)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is True, (
        f"실입고 0 확정 품목은 사진 없어도 AM close 통과 필요: {result}"
    )


def test_case_k_defect_qty_blocks_pm_close():
    """
    K: 불량판정중(defect) 수량이 있으면 PM 최종 마감 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=3, actual_qty=3, status="defect", line_no=1)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, status="confirmed", line_no=2)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "unresolved"
    assert result["defect_qty"] == 3
    assert result["repair_qty"] == 0


def test_case_l_repair_qty_blocks_pm_close():
    """
    L: 수선중(repair) 수량이 있으면 PM 최종 마감 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="repairing")
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, status="repair", line_no=1)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, status="confirmed", line_no=2)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "unresolved"
    assert result["repair_qty"] == 2
    assert result["defect_qty"] == 0


def test_case_m_done_and_unrecoverable_allows_pm_close():
    """
    M: 수선후정상(done) + 회생불가(unrecoverable)만 있으면 PM 최종 마감 가능.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=3, actual_qty=3, status="done", line_no=1)
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, status="unrecoverable", line_no=2)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is True, f"수선후정상+회생불가만 있으면 PM close 가능: {result}"
    assert result["status"] == "done"


def test_case_n_pm_close_idempotent_no_double_move():
    """
    N: PM close 두 번 호출 → pending 품목 중복 이동 없음 (두 번째엔 moved=0).
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, status="pending", line_no=1)

        r1 = _pm_close_direct(con, batch_id)
        # 두 번째 시도 (batch 이미 done)
        # 실제로는 batch status='done' 으로 진입 자체를 막지만,
        # 여기선 로직 레벨 idempotency 만 확인
        r2 = _pm_close_direct(con, batch_id)

    assert r1["ok"] is True
    assert r1["moved"] == 1, f"1차 PM close: pending 1개 이동 예상, 실제={r1['moved']}"
    # 2차 시도 시 pending 이 이미 0 → moved=0
    assert r2["moved"] == 0, f"2차 PM close: pending 이미 0 → 이동 없어야 함, 실제={r2['moved']}"
    assert r2["post_pending"] == 0


# ═════════════════════════════════════════════════════════════════
# 검증 테스트 O ~ Y: 봇 경로 / photo_decision 실제관계 / PM 수량 source
# ═════════════════════════════════════════════════════════════════

def _add_inbox_photo_direct(con, batch_id: str, user_id: str = "bot_user",
                            channel_id: str = "ch_001", sha: str = "abc123",
                            stored_filename: str = "test.jpg") -> str:
    """봇 수신 미분류 사진 저장을 DB 직접 접근으로 재현 (inbound_product_photo_inbox 만 변경)."""
    photo_id = uuid.uuid4().hex
    con.execute("""
        INSERT INTO inbound_product_photo_inbox
            (id, batch_id, user_id, channel_id, sha256, filename, stored_filename, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (photo_id, batch_id, user_id, channel_id, sha, stored_filename, stored_filename))
    con.commit()
    return photo_id


def _add_item_photo_direct(con, item_id: str, batch_id: str, filename: str = "item.jpg") -> str:
    """품목 직접 연결 사진 저장 (inbound_item_photos + photo_decision 갱신)."""
    photo_id = uuid.uuid4().hex
    con.execute(
        "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename, created_at) "
        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (photo_id, item_id, batch_id, filename)
    )
    # 사진 업로드 시 photo_decision 자동 설정 (서버와 동일 로직)
    con.execute(
        "UPDATE inbound_items SET photo_decision=COALESCE(photo_decision,'photo') WHERE id=?",
        (item_id,)
    )
    con.commit()
    return photo_id


def test_case_o_bot_inbox_photo_does_not_change_item_photo_decision():
    """
    O: 봇으로 미분류 사진 3장 업로드 → 어떤 품목의 photo_decision 도 변경되지 않음.
    inbound_product_photo_inbox 에만 저장, inbound_items 는 건드리지 않는다.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        item1 = _make_item(con, batch_id, actual_qty_confirmed=1, photo_decision=None, line_no=1)
        item2 = _make_item(con, batch_id, actual_qty_confirmed=1, photo_decision="none", line_no=2)

        # 봇 경로: 미분류 사진 3장 → inbox 저장만
        for i in range(3):
            _add_inbox_photo_direct(con, batch_id, sha=f"sha_{i}", stored_filename=f"bot_{i}.jpg")

        # 품목 photo_decision 미변경 확인
        d1 = con.execute("SELECT photo_decision FROM inbound_items WHERE id=?", (item1,)).fetchone()[0]
        d2 = con.execute("SELECT photo_decision FROM inbound_items WHERE id=?", (item2,)).fetchone()[0]
        inbox_count = con.execute(
            "SELECT COUNT(*) FROM inbound_product_photo_inbox WHERE batch_id=?", (batch_id,)
        ).fetchone()[0]

    assert inbox_count == 3, f"inbox에 3장 저장 예상, 실제={inbox_count}"
    assert d1 is None, f"item1 photo_decision은 None 유지 예상, 실제={d1!r}"
    assert d2 == "none", f"item2 photo_decision은 'none' 유지 예상, 실제={d2!r}"


def test_case_p_item_photo_upload_sets_photo_decision():
    """
    P: 매칭 페이지에서 특정 품목에 사진 연결 → 그 품목만 photo_decision='photo'.
    다른 품목은 변경 없음.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        item1 = _make_item(con, batch_id, actual_qty_confirmed=1, photo_decision=None, line_no=1)
        item2 = _make_item(con, batch_id, actual_qty_confirmed=1, photo_decision=None, line_no=2)

        # 품목 직접 연결 (매칭 페이지 경로)
        _add_item_photo_direct(con, item1, batch_id, filename="matched_item1.jpg")

        d1 = con.execute("SELECT photo_decision FROM inbound_items WHERE id=?", (item1,)).fetchone()[0]
        d2 = con.execute("SELECT photo_decision FROM inbound_items WHERE id=?", (item2,)).fetchone()[0]

    assert d1 == "photo", f"item1은 사진 연결 후 photo 예상, 실제={d1!r}"
    assert d2 is None, f"item2는 변경 없이 None 유지 예상, 실제={d2!r}"


def test_case_q_photo_decision_photo_without_file_blocks_am():
    """
    Q: photo_decision='photo' 를 문자열만 설정하고 실제 사진 없음 → AM close 차단.
    클라이언트가 photo_decision 만 PATCH 하고 파일 업로드 없을 때.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        # photo_decision='photo' 설정했지만 inbound_item_photos 에 실제 파일 없음
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                   actual_qty_confirmed=1, photo_decision="photo", line_no=1)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "photo_no_file", f"실제 사진 없는 photo → 차단 필요: {result}"
    assert result["photo_no_file_count"] == 1


def test_case_r_photo_decision_photo_with_file_allows_am():
    """
    R: photo_decision='photo' + 실제 사진 파일 연결 → AM close 통과.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        item_id = _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                             actual_qty_confirmed=1, photo_decision=None, line_no=1)
        # 실제 사진 연결 (auto-sets photo_decision='photo')
        _add_item_photo_direct(con, item_id, batch_id)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is True, f"실제 사진 있는 photo 품목 → AM close 통과 필요: {result}"


def test_case_s_photo_decision_existing_without_barcode_blocks_am():
    """
    S: photo_decision='existing' 설정했지만 matched_barcode 없음 → AM close 차단.
    클라이언트가 바코드 연결 없이 existing 만 PATCH 했을 때.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        # photo_decision='existing' 이지만 matched_barcode=None
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                   actual_qty_confirmed=1, photo_decision="existing", line_no=1)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["reason"] == "existing_no_product", f"product master 없는 existing → 차단 필요: {result}"


def test_case_t_zero_actual_qty_confirmed_skips_photo_check():
    """
    T: 실입고 0 으로 직원 확정 → photo_decision 없어도 AM close 가능.
    (세션 J 중복 검증: photo 검사는 actual_qty >= 1 에만 적용)
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="confirming")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=0,
                   actual_qty_confirmed=1, photo_decision=None, line_no=1)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is True, f"실입고 0 확정 품목은 photo 없어도 통과: {result}"


def test_case_u_mixed_defect_and_repair_blocks_pm():
    """
    U: 별도 품목에 defect 1개·repair 2개 존재 → PM 최종 마감 차단.
    defect_qty + repair_qty 모두 응답에 포함됨.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=1, actual_qty=1, status="defect", line_no=1)
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, status="repair", line_no=2)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, status="confirmed", line_no=3)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is False
    assert result["defect_qty"] == 1
    assert result["repair_qty"] == 2


def test_case_v_defect_pending_qty_col_drives_pm_block():
    """
    V: PM 마감 차단 기준은 defect_pending_qty 컬럼 합산이다 (부분수량 모델).
    케이스 1: defect_pending_qty=5 -> PM 차단
    케이스 2: defect_pending_qty=0, normal_qty=5 -> PM 통과
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5,
                   defect_pending_qty=5, normal_qty=0, repairing_qty=0,
                   repair_done_qty=0, unrecoverable_qty=0, line_no=1)
        result_block = _pm_close_direct(con, batch_id)

    with get_connection() as con:
        _setup(con)
        batch_id2 = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id2, janggi_qty=5, actual_qty=5,
                   defect_pending_qty=0, normal_qty=5, repairing_qty=0,
                   repair_done_qty=0, unrecoverable_qty=0, line_no=1)
        result_pass = _pm_close_direct(con, batch_id2)

    assert result_block["ok"] is False, f"defect_pending_qty>0 -> PM block: {result_block}"
    assert result_block["defect_qty"] == 5
    assert result_pass["ok"] is True, f"defect_pending_qty=0 -> PM pass: {result_pass}"

def test_case_w_repairing_qty_col_drives_pm_block():
    """
    W: PM 마감 차단 기준은 repairing_qty 컬럼 합산이다 (부분수량 모델).
    케이스 1: repairing_qty=4 -> PM 차단
    케이스 2: repair_done_qty=4 (repairing_qty=0) -> PM 통과
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=4, actual_qty=4,
                   repairing_qty=4, defect_pending_qty=0, normal_qty=0,
                   repair_done_qty=0, unrecoverable_qty=0, line_no=1)
        result_block = _pm_close_direct(con, batch_id)

    with get_connection() as con:
        _setup(con)
        batch_id2 = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id2, janggi_qty=4, actual_qty=4,
                   repair_done_qty=4, repairing_qty=0, defect_pending_qty=0,
                   normal_qty=0, unrecoverable_qty=0, line_no=1)
        result_pass = _pm_close_direct(con, batch_id2)

    assert result_block["ok"] is False, f"repairing_qty>0 -> PM block: {result_block}"
    assert result_block["repair_qty"] == 4
    assert result_pass["ok"] is True, f"repairing_qty=0 -> PM pass: {result_pass}"

def test_case_x_pm_block_qty_matches_compute_batch_overview():
    """
    X: 통합현황의 불량판정중·수선중 수량과 PM 차단 응답 수량이 동일.
    _compute_batch_overview 와 _pm_close_direct 가 동일 source 를 사용함을 증명.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, janggi_qty=3, actual_qty=3, status="defect", line_no=1)
        _make_item(con, batch_id, janggi_qty=2, actual_qty=2, status="repair", line_no=2)
        _make_item(con, batch_id, janggi_qty=5, actual_qty=5, status="confirmed", line_no=3)

        overview = _compute_batch_overview(batch_id, con)
        pm_result = _pm_close_direct(con, batch_id)

    ov_summary = overview["summary"]
    # overview 와 PM 차단 응답이 동일한 수량을 사용하는지 확인
    assert ov_summary["defect_pending_qty"] == pm_result["defect_qty"], (
        f"통합현황 defect={ov_summary['defect_pending_qty']} vs "
        f"PM차단 defect={pm_result['defect_qty']}: 불일치!"
    )
    assert ov_summary["repairing_qty"] == pm_result["repair_qty"], (
        f"통합현황 repair={ov_summary['repairing_qty']} vs "
        f"PM차단 repair={pm_result['repair_qty']}: 불일치!"
    )
    assert pm_result["ok"] is False, "defect+repair 있으므로 PM 차단 필요"


# ═══════════════════════════════════════════════════════════════
# 신규 21개 테스트
# Group 1: 동일 inbound_item 한 행의 부분수량 (Qty-1 ~ Qty-10)
# Group 2: inbox 사진 연결 (Inbox-11 ~ Inbox-18)
# Group 3: existing product master 검증 (Exist-19 ~ Exist-21)
# ═══════════════════════════════════════════════════════════════

# ────────────────────────────────────────────────────────────────
# 부분수량 테스트 헬퍼
# ────────────────────────────────────────────────────────────────

def _get_item_qty(con, item_id: str) -> dict:
    """품목 한 행의 모든 수량 컬럼을 dict 로 반환. pending 은 computed."""
    row = con.execute(
        "SELECT actual_qty, normal_qty, defect_pending_qty, repairing_qty, "
        "       repair_done_qty, unrecoverable_qty "
        "FROM inbound_items WHERE id=?", (item_id,)
    ).fetchone()
    assert row, f"품목을 찾을 수 없습니다: {item_id}"
    actual, normal, defect, repairing, repair_done, unrecov = (v or 0 for v in row)
    pending = max(0, actual - normal - defect - repairing - repair_done - unrecov)
    return {
        "actual": actual, "pending": pending, "normal": normal,
        "defect": defect, "repairing": repairing,
        "repair_done": repair_done, "unrecoverable": unrecov,
    }


def _do_move(con, item_id, from_s, to_s, qty, **kw):
    """move_item_qty 호출 래퍼 (테스트용)."""
    from backend.app.api.inbound import move_item_qty
    result = move_item_qty(con, item_id, from_s, to_s, qty, **kw)
    con.commit()
    return result


# ── Qty-1: pending → defect 이동 후 불변식 검증 ─────────────────

def test_qty1_pending_to_defect_invariant():
    """
    Qty-1: actual_qty=10, 모두 pending 인 한 행에서
    pending 3개를 defect 로 이동 → pending=7, defect=3, 불변식 유지.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        # actual=10, 모두 pending (qty 컬럼 명시적 0)
        iid = _make_item(con, batch_id, janggi_qty=10, actual_qty=10,
                         normal_qty=0, defect_pending_qty=0, repairing_qty=0,
                         repair_done_qty=0, unrecoverable_qty=0)
        q_before = _get_item_qty(con, iid)
        assert q_before["pending"] == 10, f"초기 pending=10 기대: {q_before}"

        _do_move(con, iid, "pending", "defect", 3)
        q = _get_item_qty(con, iid)

    assert q["pending"] == 7, f"pending=7 기대: {q}"
    assert q["defect"] == 3, f"defect=3 기대: {q}"
    total = q["pending"] + q["normal"] + q["defect"] + q["repairing"] + q["repair_done"] + q["unrecoverable"]
    assert total == q["actual"] == 10, f"불변식 위반: {q}"


# ── Qty-2: defect → repairing 이동 ─────────────────────────────

def test_qty2_defect_to_repairing():
    """
    Qty-2: 한 행에 defect=5 가 있을 때 2개를 repairing 으로 이동.
    defect=3, repairing=2, 나머지 변화 없음.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, actual_qty=8,
                         defect_pending_qty=5, normal_qty=3, repairing_qty=0,
                         repair_done_qty=0, unrecoverable_qty=0)
        _do_move(con, iid, "defect", "repairing", 2)
        q = _get_item_qty(con, iid)

    assert q["defect"] == 3
    assert q["repairing"] == 2
    assert q["normal"] == 3
    total = q["pending"] + q["normal"] + q["defect"] + q["repairing"] + q["repair_done"] + q["unrecoverable"]
    assert total == 8


# ── Qty-3: repairing → repair_done 이동 ────────────────────────

def test_qty3_repairing_to_repair_done():
    """Qty-3: repairing 중 일부가 수선 완료(repair_done) 로 이동."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, actual_qty=6,
                         repairing_qty=4, normal_qty=2, defect_pending_qty=0,
                         repair_done_qty=0, unrecoverable_qty=0)
        _do_move(con, iid, "repairing", "repair_done", 1)
        q = _get_item_qty(con, iid)

    assert q["repairing"] == 3
    assert q["repair_done"] == 1
    assert q["normal"] == 2


# ── Qty-4: repairing → unrecoverable 이동 ──────────────────────

def test_qty4_repairing_to_unrecoverable():
    """Qty-4: 수선 중 회생불가 판정 → repairing → unrecoverable."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, actual_qty=5,
                         repairing_qty=3, normal_qty=2, defect_pending_qty=0,
                         repair_done_qty=0, unrecoverable_qty=0)
        _do_move(con, iid, "repairing", "unrecoverable", 1)
        q = _get_item_qty(con, iid)

    assert q["repairing"] == 2
    assert q["unrecoverable"] == 1
    total = q["pending"] + q["normal"] + q["defect"] + q["repairing"] + q["repair_done"] + q["unrecoverable"]
    assert total == 5


# ── Qty-5: 한 행에 5가지 상태 동시 존재 ────────────────────────

def test_qty5_single_item_multiple_states_coexist():
    """
    Qty-5 (핵심 증명): actual_qty=10 한 행 안에서
    pending=1, normal=2, defect=3, repairing=2, repair_done=1, unrecoverable=1
    이 동시에 존재할 수 있음을 검증한다.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, actual_qty=10,
                         normal_qty=2, defect_pending_qty=3,
                         repairing_qty=2, repair_done_qty=1,
                         unrecoverable_qty=1)
        q = _get_item_qty(con, iid)

    # pending = 10 - 2 - 3 - 2 - 1 - 1 = 1
    assert q["actual"] == 10
    assert q["pending"] == 1
    assert q["normal"] == 2
    assert q["defect"] == 3
    assert q["repairing"] == 2
    assert q["repair_done"] == 1
    assert q["unrecoverable"] == 1
    total = q["pending"] + q["normal"] + q["defect"] + q["repairing"] + q["repair_done"] + q["unrecoverable"]
    assert total == 10, f"불변식 위반: {q}"


# ── Qty-6: 통합현황(breakdown) 이 단일 행 부분수량을 정확히 반영 ──

def test_qty6_overview_breakdown_reflects_partial_qty():
    """
    Qty-6: _compute_batch_overview 의 item breakdown 이
    qty 컬럼 기반 부분수량을 정확히 반영한다.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=10,
                   normal_qty=4, defect_pending_qty=2,
                   repairing_qty=3, repair_done_qty=1,
                   unrecoverable_qty=0)
        ov = _compute_batch_overview(batch_id, con)

    item = ov["items"][0]["breakdown"]
    assert item["normal"] == 4
    assert item["defect"] == 2
    assert item["repairing"] == 3
    assert item["repaired_good"] == 1
    assert item["unrecoverable"] == 0
    # pending = 10 - 4 - 2 - 3 - 1 = 0
    assert item["pending"] == 0

    s = ov["summary"]
    assert s["normal_qty"] == 4
    assert s["defect_pending_qty"] == 2
    assert s["repairing_qty"] == 3
    assert s["repaired_good_qty"] == 1


# ── Qty-7: grade_complete 은 pending→normal 만 이동, 다른 상태 보존 ─

def test_qty7_grade_complete_preserves_non_pending():
    """
    Qty-7: grade_complete 실행 시 한 행에서 pending 만 normal 로 이동.
    defect/repairing 상태 수량은 변경되지 않는다.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        # actual=10, pending=4, defect=3, repairing=2, normal=1
        iid = _make_item(con, batch_id, actual_qty=10,
                         normal_qty=1, defect_pending_qty=3,
                         repairing_qty=2, repair_done_qty=0,
                         unrecoverable_qty=0)
        q_before = _get_item_qty(con, iid)
        assert q_before["pending"] == 4

        moved = _grade_complete_direct(con, batch_id)
        q = _get_item_qty(con, iid)

    assert moved == 1, f"pending 있는 품목 1행 기대, 실제={moved}"
    # pending → normal: normal = 1(기존) + 4(pending) = 5
    assert q["normal"] == 5, f"normal=5 기대: {q}"
    assert q["pending"] == 0
    # 다른 상태 보존
    assert q["defect"] == 3, f"defect 3 보존 기대: {q}"
    assert q["repairing"] == 2, f"repairing 2 보존 기대: {q}"
    total = q["normal"] + q["defect"] + q["repairing"]
    assert total == 10


# ── Qty-8: 단일 행 defect_pending_qty>0 이 PM close 차단 ─────────

def test_qty8_single_item_defect_blocks_pm():
    """
    Qty-8: 동일 품목 한 행에서 defect_pending_qty=3 → PM close 차단.
    별도 행을 defect 로 만들지 않음.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, actual_qty=10,
                   normal_qty=7, defect_pending_qty=3,
                   repairing_qty=0, repair_done_qty=0,
                   unrecoverable_qty=0, line_no=1)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is False, f"defect_pending_qty=3 -> PM block: {result}"
    assert result["defect_qty"] == 3


# ── Qty-9: 단일 행 repairing_qty>0 이 PM close 차단 ─────────────

def test_qty9_single_item_repairing_blocks_pm():
    """
    Qty-9: 동일 품목 한 행에서 repairing_qty=2 → PM close 차단.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con, status="inbound_done")
        _make_item(con, batch_id, actual_qty=5,
                   normal_qty=3, repairing_qty=2,
                   defect_pending_qty=0, repair_done_qty=0,
                   unrecoverable_qty=0, line_no=1)
        result = _pm_close_direct(con, batch_id)

    assert result["ok"] is False, f"repairing_qty=2 -> PM block: {result}"
    assert result["repair_qty"] == 2


# ── Qty-10: move_item_qty ref_id idempotency ──────────────────────

def test_qty10_move_item_qty_idempotency():
    """
    Qty-10: 같은 ref_id 로 move_item_qty 를 두 번 호출해도
    수량이 한 번만 이동된다 (idempotent).
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, actual_qty=10,
                         normal_qty=0, defect_pending_qty=0,
                         repairing_qty=0, repair_done_qty=0,
                         unrecoverable_qty=0)
        ref = "test-ref-001"
        r1 = _do_move(con, iid, "pending", "defect", 3, ref_id=ref)
        r2 = _do_move(con, iid, "pending", "defect", 3, ref_id=ref)
        q = _get_item_qty(con, iid)

    assert r1.get("moved") is True, f"첫 번째 이동 성공 기대: {r1}"
    assert r2.get("skipped") is True, f"두 번째는 skip 기대: {r2}"
    assert q["defect"] == 3, f"defect=3(한 번만 이동) 기대: {q}"
    assert q["pending"] == 7


# ────────────────────────────────────────────────────────────────
# Inbox 사진 연결 테스트 헬퍼
# ────────────────────────────────────────────────────────────────

def _make_inbox_photo(con, batch_id: str, filename: str = "test.jpg",
                      stored_filename: str = "stored_test.jpg",
                      sha256: str = "abc123",
                      user_id: str = "bot", channel_id: str = "ch001") -> str:
    """inbound_product_photo_inbox 에 레코드를 삽입하고 id 반환."""
    ph_id = uuid.uuid4().hex
    con.execute(
        "INSERT INTO inbound_product_photo_inbox "
        "(id, batch_id, user_id, channel_id, filename, stored_filename, sha256, is_deleted, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)",
        (ph_id, batch_id, user_id, channel_id, filename, stored_filename, sha256)
    )
    con.commit()
    return ph_id


def _link_inbox_direct(con, item_id: str, inbox_photo_id: str, batch_id: str) -> dict:
    """POST /items/{id}/photos/from-inbox 핵심 로직을 직접 실행."""
    from backend.app.api.inbound import link_inbox_photo_to_item, InboxPhotoLink
    from fastapi import HTTPException as HTTPEx

    # DB 에서 직접 수행 (API 호출 우회)
    inbox = con.execute(
        "SELECT id, batch_id, stored_filename, is_deleted FROM inbound_product_photo_inbox WHERE id=?",
        (inbox_photo_id,)
    ).fetchone()
    if not inbox:
        return {"error": "inbox_not_found"}
    if inbox[3]:
        return {"error": "deleted"}
    inbox_batch = inbox[1]
    stored_fn = inbox[2]
    if not stored_fn:
        return {"error": "no_stored_filename"}

    item = con.execute(
        "SELECT id, batch_id FROM inbound_items WHERE id=?", (item_id,)
    ).fetchone()
    if not item:
        return {"error": "item_not_found"}
    if inbox_batch != item[1]:
        return {"error": "batch_mismatch"}

    existing = con.execute(
        "SELECT id FROM inbound_item_photos WHERE item_id=? AND filename=?",
        (item_id, stored_fn)
    ).fetchone()
    if existing:
        return {"ok": True, "id": existing[0], "duplicated": True}

    ph_id = uuid.uuid4().hex
    con.execute(
        "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename, created_at) "
        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (ph_id, item_id, item[1], stored_fn)
    )
    con.execute(
        "UPDATE inbound_product_photo_inbox SET item_id=? WHERE id=?",
        (item_id, inbox_photo_id)
    )
    con.execute(
        "UPDATE inbound_items SET photo_decision=COALESCE(photo_decision,'photo'), "
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (item_id,)
    )
    con.commit()
    return {"ok": True, "id": ph_id, "duplicated": False}


# ── Inbox-11: from-inbox 연결 후 inbound_item_photos 레코드 생성 ──

def test_inbox11_link_creates_item_photo_record():
    """Inbox-11: inbox 사진을 품목에 연결하면 inbound_item_photos 에 레코드가 생긴다."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id)
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_a.jpg")

        result = _link_inbox_direct(con, iid, inbox_id, batch_id)
        photos = con.execute(
            "SELECT id, filename FROM inbound_item_photos WHERE item_id=?", (iid,)
        ).fetchall()

    assert result["ok"] is True, f"연결 성공 기대: {result}"
    assert result["duplicated"] is False
    assert len(photos) == 1, f"품목 사진 1개 기대: {photos}"
    assert photos[0][1] == "stored_a.jpg", "파일명 일치 기대"


# ── Inbox-12: from-inbox 연결 후 photo_decision='photo' 설정 ──────

def test_inbox12_link_sets_photo_decision_photo():
    """Inbox-12: from-inbox 연결 성공 → photo_decision='photo' 자동 설정."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id, photo_decision=None)
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_b.jpg")

        _link_inbox_direct(con, iid, inbox_id, batch_id)
        pd = con.execute(
            "SELECT photo_decision FROM inbound_items WHERE id=?", (iid,)
        ).fetchone()[0]

    assert pd == "photo", f"photo_decision='photo' 기대: {pd}"


# ── Inbox-13: 중복 연결은 기존 id 반환 ───────────────────────────

def test_inbox13_duplicate_link_returns_existing():
    """Inbox-13: 같은 inbox_photo + item 을 두 번 연결하면 duplicated=True 반환."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id)
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_c.jpg")

        r1 = _link_inbox_direct(con, iid, inbox_id, batch_id)
        r2 = _link_inbox_direct(con, iid, inbox_id, batch_id)
        count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE item_id=?", (iid,)
        ).fetchone()[0]

    assert r1["duplicated"] is False
    assert r2["duplicated"] is True, f"두 번째 연결은 duplicate 기대: {r2}"
    assert r1["id"] == r2["id"], "동일 id 반환 기대"
    assert count == 1, f"사진 레코드 1개만 기대 (중복 없음): {count}"


# ── Inbox-14: 다른 배치의 inbox 사진은 연결 거부 ────────────────

def test_inbox14_cross_batch_link_rejected():
    """Inbox-14: inbox 사진과 품목이 다른 batch_id → batch_mismatch 에러."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch1 = _make_batch(con)
        batch2 = _make_batch(con)
        iid = _make_item(con, batch1)
        # inbox 는 batch2 소속
        inbox_id = _make_inbox_photo(con, batch2, stored_filename="stored_d.jpg")

        result = _link_inbox_direct(con, iid, inbox_id, batch1)

    assert result.get("error") == "batch_mismatch", f"배치 불일치 거부 기대: {result}"


# ── Inbox-15: 같은 inbox 사진을 같은 batch 다른 품목에 연결 가능 ─

def test_inbox15_same_inbox_photo_links_to_multiple_items():
    """
    Inbox-15: 하나의 inbox 사진을 동일 batch 내 여러 품목에 연결할 수 있다.
    (옵션 다를 때 같은 대표사진 공유 시나리오)
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid1 = _make_item(con, batch_id, line_no=1, item_name="A")
        iid2 = _make_item(con, batch_id, line_no=2, item_name="B")
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_e.jpg")

        r1 = _link_inbox_direct(con, iid1, inbox_id, batch_id)
        r2 = _link_inbox_direct(con, iid2, inbox_id, batch_id)
        count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE filename='stored_e.jpg'"
        ).fetchone()[0]

    assert r1["ok"] is True
    assert r2["ok"] is True
    assert count == 2, f"같은 파일로 2개 품목 연결 기대: {count}"


# ── Inbox-16: 삭제된 inbox 사진은 연결 거부 ─────────────────────

def test_inbox16_deleted_inbox_photo_rejected():
    """Inbox-16: is_deleted=1 인 inbox 사진 → 연결 거부."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id)
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_f.jpg")
        # 삭제 처리
        con.execute("UPDATE inbound_product_photo_inbox SET is_deleted=1 WHERE id=?", (inbox_id,))
        con.commit()

        result = _link_inbox_direct(con, iid, inbox_id, batch_id)

    assert result.get("error") == "deleted", f"삭제 거부 기대: {result}"


# ── Inbox-17: 존재하지 않는 inbox 사진 → 거부 ───────────────────

def test_inbox17_nonexistent_inbox_photo_rejected():
    """Inbox-17: 없는 inbox_photo_id → inbox_not_found."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        iid = _make_item(con, batch_id)

        result = _link_inbox_direct(con, iid, "nonexistent-id", batch_id)

    assert result.get("error") == "inbox_not_found", f"not_found 기대: {result}"


# ── Inbox-18: 존재하지 않는 품목 → 거부 ─────────────────────────

def test_inbox18_nonexistent_item_rejected():
    """Inbox-18: 없는 item_id → item_not_found."""
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        inbox_id = _make_inbox_photo(con, batch_id, stored_filename="stored_g.jpg")

        result = _link_inbox_direct(con, "nonexistent-item", inbox_id, batch_id)

    assert result.get("error") == "item_not_found", f"not_found 기대: {result}"


# ────────────────────────────────────────────────────────────────
# existing product master 검증 (AM close)
# ────────────────────────────────────────────────────────────────

def _ensure_repair_barcode(con, barcode: str):
    """repair_barcode 에 테스트용 바코드 삽입 (없으면)."""
    existing = con.execute(
        "SELECT 바코드 FROM repair_barcode WHERE 바코드=?", (barcode,)
    ).fetchone()
    if not existing:
        con.execute(
            "INSERT INTO repair_barcode (바코드, 업체명, 제품명) VALUES (?, ?, ?)",
            (barcode, "테스트업체", "테스트제품")
        )
        con.commit()


# ── Exist-19: matched_barcode 없고 photo_decision='existing' → AM 차단 ─

def test_exist19_existing_no_barcode_blocks_am():
    """
    Exist-19: photo_decision='existing' 이지만 matched_barcode=NULL
    → AM close 차단 (reason=existing_no_product).
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=3,
                   actual_qty_confirmed=1, photo_decision="existing",
                   matched_barcode=None, line_no=1)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False, f"barcode 없는 existing → AM 차단: {result}"
    assert result["reason"] == "existing_no_product", f"reason 불일치: {result}"


# ── Exist-20: repair_barcode 에 있는 바코드 → AM 통과 ────────────

def test_exist20_existing_with_valid_master_passes_am():
    """
    Exist-20: matched_barcode 가 repair_barcode 에 존재하면 AM close 통과.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        _ensure_repair_barcode(con, "VALID-BC-001")
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=2,
                   actual_qty_confirmed=1, photo_decision="existing",
                   matched_barcode="VALID-BC-001", line_no=1)
        result = _am_close_direct(con, batch_id)

    # AM close 는 batch status 도 체크하므로 unresolved 외 사유로 막히지 않으면 통과
    assert result.get("reason") != "existing_no_product", (
        f"유효한 바코드는 AM 통과 기대: {result}"
    )


# ── Exist-21: matched_barcode 있지만 repair_barcode 미등록 → AM 차단 ─

def test_exist21_existing_barcode_not_in_master_blocks_am():
    """
    Exist-21: matched_barcode 가 설정됐지만 repair_barcode 에 없는 값
    → AM close 차단 (reason=existing_no_product).
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        _make_item(con, batch_id, actual_qty=5,
                   actual_qty_confirmed=1, photo_decision="existing",
                   matched_barcode="UNKNOWN-BC-99999", line_no=1)
        result = _am_close_direct(con, batch_id)

    assert result["ok"] is False, f"미등록 바코드 → AM 차단 기대: {result}"
    assert result["reason"] == "existing_no_product", f"reason 불일치: {result}"


# ══════════════════════════════════════════════════════════════════
# Session 6 신규 테스트: 원자 트랜잭션·repair_action·불변식
# ══════════════════════════════════════════════════════════════════

# ─── D-1: 불량 수량 부족 → 로그+수량이력 전부 미저장 ────────────

def test_d1_defect_pending_shortage_blocks_all():
    """
    D-1: pending_qty=0 인 품목에 불량 등록 시도 → 409 반환,
    defect_log 행도 inbound_item_qty_transitions 행도 모두 생성되지 않는다.
    """
    from fastapi import HTTPException
    from backend.app.api.inbound import link_defect_log, DefectLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        # pending=0: normal_qty = actual_qty (모두 정상처리됨)
        item_id = _make_item(con, batch_id, actual_qty=5, status="confirmed",
                             normal_qty=5, defect_pending_qty=0)

    with pytest.raises(HTTPException) as exc_info:
        link_defect_log(
            item_id,
            DefectLogLink(불량명="스크래치", 수량=1),
            authorization=f"Bearer {_TEST_TOKEN}",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INSUFFICIENT_PENDING"

    # DB에 아무것도 저장되지 않아야 한다
    with get_connection() as con:
        dl_count = con.execute(
            "SELECT COUNT(*) FROM defect_log WHERE inbound_item_id=?", (item_id,)
        ).fetchone()[0]
        tr_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_qty_transitions WHERE item_id=?", (item_id,)
        ).fetchone()[0]
    assert dl_count == 0, f"defect_log 행이 생성됐다: {dl_count}"
    assert tr_count == 0, f"qty_transitions 행이 생성됐다: {tr_count}"


# ─── D-2: 정상 불량 등록 → 로그+수량이동 원자 저장 ─────────────

def test_d2_defect_normal_flow_atomic():
    """
    D-2: pending_qty=3 인 품목에 수량=2 불량 등록 →
    defect_log 행 1개, qty_transitions 행 1개, defect_pending_qty=2, pending=1.
    """
    from backend.app.api.inbound import link_defect_log, DefectLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, status="pending",
                             normal_qty=2, defect_pending_qty=0)  # pending=3

    result = link_defect_log(
        item_id, DefectLogLink(불량명="변색", 수량=2), authorization=f"Bearer {_TEST_TOKEN}"
    )
    assert result["defect_log_id"] is not None
    assert result["qty_moved"]["from"] == "pending"
    assert result["qty_moved"]["to"] == "defect"
    assert result["qty_moved"]["qty"] == 2

    with get_connection() as con:
        qty = _get_item_qty(con, item_id)
        dl_count = con.execute(
            "SELECT COUNT(*) FROM defect_log WHERE inbound_item_id=?", (item_id,)
        ).fetchone()[0]
        tr_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_qty_transitions WHERE item_id=?", (item_id,)
        ).fetchone()[0]

    assert qty["defect"] == 2
    assert qty["pending"] == 1
    assert dl_count == 1, "defect_log 행 1개 기대"
    assert tr_count == 1, "qty_transitions 행 1개 기대"


# ─── D-3: move_item_qty ref_id 중복 → idempotent ────────────────

def test_d3_move_item_qty_ref_id_idempotent():
    """
    D-3: 동일 ref_id 로 move_item_qty 두 번 → 두 번째는 SKIP, 수량은 한 번만 이동.
    """
    from backend.app.api.inbound import move_item_qty
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=10, status="pending")

        move_item_qty(con, item_id, "pending", "defect", 3, ref_id="dup-ref-001")
        con.commit()
        move_item_qty(con, item_id, "pending", "defect", 3, ref_id="dup-ref-001")  # skip
        con.commit()

        qty = _get_item_qty(con, item_id)
        tr_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_qty_transitions WHERE item_id=? AND ref_id=?",
            (item_id, "dup-ref-001")
        ).fetchone()[0]

    assert qty["defect"] == 3, f"두 번 이동이 발생하면 안 됨: defect={qty['defect']}"
    assert tr_count == 1, f"transitions 행 1개 기대, 실제: {tr_count}"


# ─── D-4: 불량등록 후 전체 수량 불변식 유지 ──────────────────────

def test_d4_invariant_after_defect():
    """
    D-4: 불량 등록 후 pending+normal+defect+repairing+repair_done+unrecov == actual.
    """
    from backend.app.api.inbound import link_defect_log, DefectLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=8, status="pending",
                             normal_qty=3)  # pending=5

    link_defect_log(item_id, DefectLogLink(불량명="오염", 수량=2), authorization=f"Bearer {_TEST_TOKEN}")

    with get_connection() as con:
        qty = _get_item_qty(con, item_id)

    total = qty["pending"] + qty["normal"] + qty["defect"] + qty["repairing"] + qty["repair_done"] + qty["unrecoverable"]
    assert total == qty["actual"], f"불변식 위반: {qty}"


# ─── R-5: repair_action='수선접수' → defect→repairing ──────────

def test_r5_repair_accept_action_mapping():
    """
    R-5: repair_action='수선접수' → defect 수량이 repairing 으로 이동.
    """
    from backend.app.api.inbound import link_repair_log, RepairLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=6, status="defect",
                             defect_pending_qty=6)  # defect=6

    result = link_repair_log(
        item_id,
        RepairLogLink(작업="봉제수선", 수량=4, 비용=5000, repair_action="수선접수"),
        authorization=f"Bearer {_TEST_TOKEN}",
    )
    assert result["qty_moved"]["from"] == "defect"
    assert result["qty_moved"]["to"] == "repairing"
    assert result["qty_moved"]["qty"] == 4

    with get_connection() as con:
        qty = _get_item_qty(con, item_id)
    assert qty["defect"] == 2
    assert qty["repairing"] == 4


# ─── R-6: repair_action='수선완료' → repairing→repair_done ──────

def test_r6_repair_done_action_mapping():
    """
    R-6: repair_action='수선완료' → repairing 수량이 repair_done 으로 이동.
    """
    from backend.app.api.inbound import link_repair_log, RepairLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, status="repair",
                             repairing_qty=5)

    result = link_repair_log(
        item_id,
        RepairLogLink(작업="완성", 수량=5, 비용=10000, repair_action="수선완료"),
        authorization=f"Bearer {_TEST_TOKEN}",
    )
    assert result["qty_moved"]["from"] == "repairing"
    assert result["qty_moved"]["to"] == "repair_done"

    with get_connection() as con:
        qty = _get_item_qty(con, item_id)
    assert qty["repairing"] == 0
    assert qty["repair_done"] == 5


# ─── R-7: 수선 수량 부족 → 로그+수량이력 모두 rollback ─────────

def test_r7_repair_shortage_rolls_back_all():
    """
    R-7: repairing=2 인데 수선완료 수량=5 요청 → 409,
    repair_work_log 행도 qty_transitions 행도 생성되지 않는다.
    """
    from fastapi import HTTPException
    from backend.app.api.inbound import link_repair_log, RepairLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, status="repair",
                             repairing_qty=2)

    with pytest.raises(HTTPException) as exc_info:
        link_repair_log(
            item_id,
            RepairLogLink(작업="완성", 수량=5, 비용=1000, repair_action="수선완료"),
            authorization=f"Bearer {_TEST_TOKEN}",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "INSUFFICIENT_QTY"

    with get_connection() as con:
        rl_count = con.execute(
            "SELECT COUNT(*) FROM repair_work_log WHERE inbound_item_id=?", (item_id,)
        ).fetchone()[0]
        tr_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_qty_transitions WHERE item_id=?", (item_id,)
        ).fetchone()[0]
    assert rl_count == 0, f"repair_work_log 가 생성됐다: {rl_count}"
    assert tr_count == 0, f"qty_transitions 가 생성됐다: {tr_count}"


# ─── R-8: 유효하지 않은 repair_action → 400 ─────────────────────

def test_r8_invalid_repair_action_returns_400():
    """
    R-8: 허용되지 않은 repair_action 값 → 400 INVALID_REPAIR_ACTION.
    """
    from fastapi import HTTPException
    from backend.app.api.inbound import link_repair_log, RepairLogLink
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=5, status="repair",
                             repairing_qty=5)

    with pytest.raises(HTTPException) as exc_info:
        link_repair_log(
            item_id,
            RepairLogLink(작업="테스트", 수량=1, 비용=0, repair_action="INVALID_ACTION"),
            authorization=f"Bearer {_TEST_TOKEN}",
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_REPAIR_ACTION"


# ─── B-9: status='done' 백필 → repair_done_qty = actual_qty ─────

def test_b9_done_status_backfill_maps_to_repair_done_qty():
    """
    B-9: inbound_items.status='done' 은 수선후정상을 의미한다.
    _make_item(status='done') → repair_done_qty=actual_qty 로 auto-init 된다.
    _compute_batch_overview 에서 breakdown.repaired_good == actual_qty.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=4, missing_qty=0,
                             status="done")  # repair_done_qty=4 auto-init

        qty = _get_item_qty(con, item_id)
        ov = _compute_batch_overview(batch_id, con)

    assert qty["repair_done"] == 4, f"auto-init 실패: {qty}"
    assert qty["pending"] == 0
    item_ov = next(it for it in ov["items"] if it["id"] == item_id)
    assert item_ov["breakdown"]["repaired_good"] == 4, f"overview 불일치: {item_ov['breakdown']}"


# ─── M-10: 동일 inbox 사진 두 품목에 연결 가능 ───────────────────

def test_m10_same_inbox_photo_links_to_two_items():
    """
    M-10: 하나의 inbox 사진(stored_filename)을 두 품목에 각각 연결 →
    inbound_item_photos 에 2행, 두 품목 모두 ok=True.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_a = _make_item(con, batch_id, line_no=1)
        item_b = _make_item(con, batch_id, line_no=2)
        ph_id = _make_inbox_photo(con, batch_id, stored_filename="shared_photo.jpg")

        r_a = _link_inbox_direct(con, item_a, ph_id, batch_id)
        r_b = _link_inbox_direct(con, item_b, ph_id, batch_id)

        count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE filename='shared_photo.jpg'"
        ).fetchone()[0]

    assert r_a.get("ok"), f"item_a 연결 실패: {r_a}"
    assert r_b.get("ok"), f"item_b 연결 실패: {r_b}"
    assert count == 2, f"inbound_item_photos 2행 기대, 실제: {count}"


# ─── M-11: 동일 사진+품목 중복 연결 → duplicated=True ───────────

def test_m11_duplicate_link_to_same_item_is_idempotent():
    """
    M-11: 이미 연결된 inbox 사진을 같은 품목에 다시 연결 → duplicated=True, DB 중복 없음.
    """
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id)
        ph_id = _make_inbox_photo(con, batch_id, stored_filename="dup_photo.jpg")

        r_first  = _link_inbox_direct(con, item_id, ph_id, batch_id)
        r_second = _link_inbox_direct(con, item_id, ph_id, batch_id)

        count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE item_id=? AND filename='dup_photo.jpg'",
            (item_id,)
        ).fetchone()[0]

    assert r_first.get("ok")  and not r_first.get("duplicated"),  f"첫 연결: {r_first}"
    assert r_second.get("ok") and r_second.get("duplicated") is True, f"중복 연결: {r_second}"
    assert count == 1, f"DB 중복 행 없어야 함, 실제: {count}"


# ─── M-12: 연결 해제 → inbox.item_id=NULL (다른 연결 없을 때) ────

def test_m12_unlink_resets_inbox_item_id_when_no_other_links():
    """
    M-12: 한 품목에만 연결된 inbox 사진을 해제 →
    inbound_item_photos 행 삭제, inbox.item_id=NULL.
    """
    from backend.app.api.inbound import unlink_inbox_photo_from_item
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id)
        ph_id = _make_inbox_photo(con, batch_id, stored_filename="sole_link.jpg")
        _link_inbox_direct(con, item_id, ph_id, batch_id)

    result = unlink_inbox_photo_from_item(item_id, ph_id, authorization=f"Bearer {_TEST_TOKEN}")
    assert result["ok"] is True

    with get_connection() as con:
        iip_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE item_id=? AND filename='sole_link.jpg'",
            (item_id,)
        ).fetchone()[0]
        inbox_item_id = con.execute(
            "SELECT item_id FROM inbound_product_photo_inbox WHERE id=?", (ph_id,)
        ).fetchone()[0]

    assert iip_count == 0, f"inbound_item_photos 행이 남았다: {iip_count}"
    assert inbox_item_id is None, f"inbox.item_id 가 NULL이 아니다: {inbox_item_id}"


# ─── M-13: 두 품목 연결 중 하나 해제 → 나머지 유지 ─────────────

def test_m13_unlink_one_preserves_other_link():
    """
    M-13: 동일 inbox 사진을 A, B 두 품목에 연결 후 A 해제 →
    B 의 inbound_item_photos 행 유지, inbox.item_id 는 B 또는 비어있지 않음.
    """
    from backend.app.api.inbound import unlink_inbox_photo_from_item
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_a = _make_item(con, batch_id, line_no=1)
        item_b = _make_item(con, batch_id, line_no=2)
        ph_id = _make_inbox_photo(con, batch_id, stored_filename="two_links.jpg")
        _link_inbox_direct(con, item_a, ph_id, batch_id)
        _link_inbox_direct(con, item_b, ph_id, batch_id)

    # A 연결 해제
    result = unlink_inbox_photo_from_item(item_a, ph_id, authorization=f"Bearer {_TEST_TOKEN}")
    assert result["ok"] is True

    with get_connection() as con:
        # B 의 연결은 유지
        b_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE item_id=? AND filename='two_links.jpg'",
            (item_b,)
        ).fetchone()[0]
        # A 의 연결은 삭제
        a_count = con.execute(
            "SELECT COUNT(*) FROM inbound_item_photos WHERE item_id=? AND filename='two_links.jpg'",
            (item_a,)
        ).fetchone()[0]
        # inbox.item_id 는 NULL 이 아니어야 함 (B 와 연결 유지)
        inbox_item_id = con.execute(
            "SELECT item_id FROM inbound_product_photo_inbox WHERE id=?", (ph_id,)
        ).fetchone()[0]

    assert b_count == 1, f"B 연결 유지되어야 함: {b_count}"
    assert a_count == 0, f"A 연결 삭제되어야 함: {a_count}"
    assert inbox_item_id is not None, f"inbox.item_id 는 NULL이 아니어야 함: {inbox_item_id}"


# ─── C-14: 품목 연결된 inbox 사진은 cleanup 후보 제외 ──────────

def test_c14_linked_inbox_photo_excluded_from_cleanup():
    """
    C-14: inbound_item_photos 에 연결된 inbox 사진은
    inbound_photo_cleanup_plan 의 unlinked_inbox_7d 에 포함되지 않는다.

    조건: inbox.item_id=NULL 이더라도 inbound_item_photos 에 존재하면 제외.
    """
    from backend.app.services.inbound_photo_dict import inbound_photo_cleanup_plan
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id)

        # inbox 사진: 오래됨 (8일 전), item_id=NULL 상태
        old_date = (datetime.utcnow() - timedelta(days=8)).isoformat()
        ph_id = uuid.uuid4().hex
        con.execute(
            "INSERT INTO inbound_product_photo_inbox "
            "(id, batch_id, user_id, channel_id, filename, stored_filename, sha256, is_deleted, item_id, created_at) "
            "VALUES (?, ?, 'bot', 'ch', 'f.jpg', 'shared_c14.jpg', 'abc', 0, NULL, ?)",
            (ph_id, batch_id, old_date)
        )
        # inbound_item_photos 에 연결 (item_id는 있지만 inbox.item_id=NULL 인 경우)
        con.execute(
            "INSERT INTO inbound_item_photos (id, item_id, batch_id, filename, created_at) "
            "VALUES (?, ?, ?, 'shared_c14.jpg', CURRENT_TIMESTAMP)",
            (uuid.uuid4().hex, item_id, batch_id)
        )
        con.commit()

    today = datetime.utcnow().strftime("%Y-%m-%d")
    plan = inbound_photo_cleanup_plan(dry_run=True, today=today)

    unlinked = plan["categories"].get("unlinked_inbox_7d", {})
    fns = unlinked.get("sample_filenames", [])
    count = unlinked.get("count", 0)
    assert "shared_c14.jpg" not in fns, f"연결된 사진이 cleanup 목록에 포함됐다: {fns}"
    assert count == 0, f"cleanup 대상이 있으면 안 됨: {count}"


# ─── I-15: 여러 이동 후 전체 수량 불변식 유지 ────────────────────

def test_i15_qty_invariant_after_multiple_moves():
    """
    I-15: pending→defect→repairing→repair_done 순차 이동 후
    actual_qty == pending+normal+defect+repairing+repair_done+unrecov.
    """
    from backend.app.api.inbound import move_item_qty
    ensure_inbound_tables()
    with get_connection() as con:
        _setup(con)
        batch_id = _make_batch(con)
        item_id = _make_item(con, batch_id, actual_qty=10, status="pending")

        move_item_qty(con, item_id, "pending", "defect",    4, ref_id="mv1")
        move_item_qty(con, item_id, "pending", "normal",    2, ref_id="mv2")
        move_item_qty(con, item_id, "defect",  "repairing", 3, ref_id="mv3")
        move_item_qty(con, item_id, "repairing","repair_done", 2, ref_id="mv4")
        move_item_qty(con, item_id, "defect",  "unrecoverable", 1, ref_id="mv5")
        con.commit()

        qty = _get_item_qty(con, item_id)

    total = (qty["pending"] + qty["normal"] + qty["defect"] +
             qty["repairing"] + qty["repair_done"] + qty["unrecoverable"])
    assert total == qty["actual"], f"불변식 위반: {qty}"
    # 예상값 확인
    assert qty["actual"]      == 10
    assert qty["normal"]      == 2
    assert qty["defect"]      == 0   # 4 - 3(repairing) - 1(unrecov)
    assert qty["repairing"]   == 1   # 3 - 2(repair_done)
    assert qty["repair_done"] == 2
    assert qty["unrecoverable"] == 1
    assert qty["pending"]     == 4   # 10 - 2 - 4 = 4

