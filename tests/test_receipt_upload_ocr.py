"""영수증 업로드가 업무봇 장끼 OCR과 같은 판독을 저장하는지 확인한다."""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

from PIL import Image
from fastapi.testclient import TestClient

from backend.app.api.inbound.ocr import JANGGI_SCHEMA, OcrError, SYSTEM_PROMPT
from logic.db import get_connection


def _jpeg() -> bytes:
    img = Image.new("RGB", (80, 80), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _seed_user():
    from backend.app.api.auth import ensure_users_table

    ensure_users_table()
    with get_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, nickname, is_admin)
            VALUES ('receipt-tester', 'x', '테스터', 1)
            """
        )
        uid = con.execute(
            "SELECT user_id FROM users WHERE username='receipt-tester'"
        ).fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('receipt-token', ?)",
            (uid,),
        )
        con.commit()


def _handwritten_ocr() -> dict:
    return {
        "receipt": {
            "storeName": "수기상회",
            "receiptNo": None,
            "orderDate": "2026-09-08",
            "totalAmount": 18000,
            "address": "서울 중구 을지로 1",
            "businessNumber": "1234567890",
            "isHandwritten": True,
            "confidence": 0.8,
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


class _CaptureClient:
    def __init__(self, body: dict):
        self.body = body
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, *_args, **kwargs):
        self.payload = kwargs.get("json")
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(self.body)}}]
        }
        return resp


def test_receipt_upload_uses_bot_janggi_ocr(monkeypatch):
    """업로드는 업무봇 장끼 프롬프트로 판독하고 품목을 영수증에 저장한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _seed_user()
    captured = _CaptureClient(_handwritten_ocr())

    from backend.app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    with patch("httpx.AsyncClient", return_value=captured):
        res = client.post(
            "/receipt/upload",
            params={"token": "receipt-token"},
            files={"file": ("janggi.jpg", _jpeg(), "image/jpeg")},
        )

    assert res.status_code == 200, res.text
    assert captured.payload is not None
    prompt = captured.payload["messages"][0]["content"]
    assert "동대문 장끼" in prompt
    assert prompt.startswith(SYSTEM_PROMPT.split("반드시", 1)[0])
    assert "businessNumber" in prompt
    schema = captured.payload["response_format"]["json_schema"]
    assert schema["name"] == "receipt_ocr"
    assert "businessNumber" in schema["schema"]["properties"]["receipt"]["required"]
    assert "address" in schema["schema"]["properties"]["receipt"]["required"]
    assert "businessNumber" not in JANGGI_SCHEMA["properties"]["receipt"]["properties"]

    receipt_id = res.json()["receipt_id"]
    assert res.json()["needs_review"] is True

    detail = client.get("/receipt/" + receipt_id, params={"token": "receipt-token"})
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["store_name"] == "수기상회"
    assert body["address"] == "서울 중구 을지로 1"
    assert body["business_number"] == "123-45-67890"
    assert body["receipt_type"] == "장끼"
    assert body["is_handwritten"] is True
    assert body["needs_review"] is True
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["item_name"] == "상품B"
    assert item["unit_price"] == 18000
    assert item["quantity"] == 1
    assert "천원 단위 추정" in item["warnings"]


def test_business_number_marks_unclear_value_for_review():
    from backend.app.api.receipt import _normalize_business_number

    receipt = {"warnings": []}
    assert _normalize_business_number("12-3", receipt) == "12-3"
    assert receipt["needsReview"] is True
    assert "사업자등록번호 형식 확인" in receipt["warnings"]


def test_receipt_upload_rejects_unreadable_janggi_without_saving():
    """품목을 못 읽으면 영수증 행을 만들지 않는다."""
    _seed_user()
    from backend.app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    with patch(
        "backend.app.api.receipt._run_ocr",
        side_effect=OcrError("no_items", "품목을 찾지 못했어요. 다시 촬영하거나 직접 입력해주세요."),
    ):
        res = client.post(
            "/receipt/upload",
            params={"token": "receipt-token"},
            files={"file": ("janggi.jpg", _jpeg(), "image/jpeg")},
        )

    assert res.status_code == 422
    assert "품목" in res.json()["detail"]
    with get_connection() as con:
        count = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    assert count == 0


def test_owner_and_admin_can_delete_receipt():
    """올린 사람과 관리자는 영수증과 사진을 지운다. 다른 직원은 지우지 못한다."""
    _seed_user()
    from backend.app.api.receipt import _receipt_dir, ensure_receipt_tables
    from backend.app.main import app

    ensure_receipt_tables()
    image = _receipt_dir() / "to-delete.jpg"
    image.write_bytes(b"jpeg")
    with get_connection() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, nickname, is_admin)
            VALUES ('receipt-staff', 'x', '직원', 0)
            """
        )
        con.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, nickname, is_admin)
            VALUES ('receipt-other', 'x', '다른직원', 0)
            """
        )
        staff_id = con.execute(
            "SELECT user_id FROM users WHERE username='receipt-staff'"
        ).fetchone()[0]
        other_id = con.execute(
            "SELECT user_id FROM users WHERE username='receipt-other'"
        ).fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('staff-token', ?)",
            (staff_id,),
        )
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('other-token', ?)",
            (other_id,),
        )
        con.execute(
            """
            INSERT INTO receipts (id, user_id, image_filename, store_name)
            VALUES ('receipt-del', ?, 'to-delete.jpg', '삭제상회')
            """,
            (staff_id,),
        )
        con.execute(
            """
            INSERT INTO receipt_items (id, receipt_id, line_no, item_name, quantity, amount)
            VALUES ('item-del', 'receipt-del', 1, '상품', 1, 1000)
            """
        )
        con.commit()

    client = TestClient(app, raise_server_exceptions=False)
    denied = client.delete("/receipt/receipt-del", params={"token": "other-token"})
    assert denied.status_code == 404
    assert image.is_file()

    removed = client.delete("/receipt/receipt-del", params={"token": "staff-token"})
    assert removed.status_code == 200, removed.text
    assert removed.json()["success"] is True
    assert not image.exists()
    with get_connection() as con:
        assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM receipt_items").fetchone()[0] == 0

    con_image = _receipt_dir() / "admin-delete.jpg"
    con_image.write_bytes(b"jpeg")
    with get_connection() as con:
        con.execute(
            """
            INSERT INTO receipts (id, user_id, image_filename, store_name)
            VALUES ('receipt-admin', ?, 'admin-delete.jpg', '관리삭제')
            """,
            (staff_id,),
        )
        con.commit()
    admin = client.delete("/receipt/receipt-admin", params={"token": "receipt-token"})
    assert admin.status_code == 200, admin.text
    assert not con_image.exists()


def test_checked_receipts_delete_only_the_selection():
    """체크한 영수증만 지운다. 직원은 남의 영수증을 고르면 자기 것만 지워진다."""
    _seed_user()
    from backend.app.api.receipt import ensure_receipt_tables
    from backend.app.main import app

    ensure_receipt_tables()
    with get_connection() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, nickname, is_admin)
            VALUES ('receipt-staff', 'x', '직원', 0)
            """
        )
        staff_id = con.execute(
            "SELECT user_id FROM users WHERE username='receipt-staff'"
        ).fetchone()[0]
        admin_id = con.execute(
            "SELECT user_id FROM users WHERE username='receipt-tester'"
        ).fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id) VALUES ('staff-token', ?)",
            (staff_id,),
        )
        con.execute(
            """
            INSERT INTO receipts (id, user_id, store_name) VALUES
            ('keep-mine', ?, '남김'),
            ('drop-mine', ?, '삭제'),
            ('admin-slip', ?, '관리자영수증')
            """,
            (staff_id, staff_id, admin_id),
        )
        con.commit()

    client = TestClient(app, raise_server_exceptions=False)
    staff = client.post(
        "/receipt/delete",
        params={"token": "staff-token"},
        json={"ids": ["drop-mine", "admin-slip"]},
    )
    assert staff.status_code == 200, staff.text
    assert staff.json()["deleted"] == 1
    with get_connection() as con:
        left = {row[0] for row in con.execute("SELECT id FROM receipts")}
    assert left == {"keep-mine", "admin-slip"}

    admin = client.post(
        "/receipt/delete",
        params={"token": "receipt-token"},
        json={"ids": ["keep-mine", "admin-slip"]},
    )
    assert admin.status_code == 200, admin.text
    assert admin.json()["deleted"] == 2
    with get_connection() as con:
        assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0
