"""영수증 업로드가 업무봇 장끼 OCR과 같은 판독을 저장하는지 확인한다."""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

from PIL import Image
from fastapi.testclient import TestClient

from backend.app.api.inbound.ocr import OcrError, SYSTEM_PROMPT
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
    assert captured.payload["messages"][0]["content"] == SYSTEM_PROMPT
    assert captured.payload["response_format"]["json_schema"]["name"] == "janggi_ocr"

    receipt_id = res.json()["receipt_id"]
    assert res.json()["needs_review"] is True

    detail = client.get("/receipt/" + receipt_id, params={"token": "receipt-token"})
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["store_name"] == "수기상회"
    assert body["receipt_type"] == "장끼"
    assert body["is_handwritten"] is True
    assert body["needs_review"] is True
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["item_name"] == "상품B"
    assert item["unit_price"] == 18000
    assert item["quantity"] == 1
    assert "천원 단위 추정" in item["warnings"]


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
