"""NLU 모델·추론강도 환경변수. 실제 OpenAI는 호출하지 않는다."""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

from backend.app.api.naver_works_webhook import process_message
from backend.app.services.bot_mode import MODE_REPAIR, get_mode, set_mode
from backend.app.services.bot_nlu import (
    DEFAULT_NLU_MODEL,
    DEFAULT_REASONING_EFFORT,
    LAST_NLU_CALL,
    NLU_JSON_SCHEMA,
    NLU_TIMEOUT_SEC,
    _complete_chat,
    _supports_reasoning_effort,
    nlu_model,
    nlu_reasoning_effort,
)
from backend.app.services.conversation_state import get_conversation_manager
from logic.db import get_connection


def _repair_count():
    with get_connection() as con:
        return int(con.execute("SELECT COUNT(*) FROM repair_work_log").fetchone()[0])


def test_default_model_is_luna_with_low_reasoning():
    assert DEFAULT_NLU_MODEL == "gpt-5.6-luna"
    assert nlu_model() == "gpt-5.6-luna"
    assert DEFAULT_REASONING_EFFORT == "low"
    assert nlu_reasoning_effort() == "low"
    assert NLU_TIMEOUT_SEC == 8.0


def test_model_env_prefers_bot_nlu_then_nlu_model(monkeypatch):
    monkeypatch.delenv("BOT_NLU_MODEL", raising=False)
    monkeypatch.delenv("NLU_MODEL", raising=False)
    assert nlu_model() == "gpt-5.6-luna"
    monkeypatch.setenv("NLU_MODEL", "gpt-5.6-luna")
    assert nlu_model() == "gpt-5.6-luna"
    monkeypatch.setenv("BOT_NLU_MODEL", "gpt-4o-mini")
    assert nlu_model() == "gpt-4o-mini"


def test_reasoning_effort_allowlist(monkeypatch):
    monkeypatch.delenv("BOT_NLU_REASONING_EFFORT", raising=False)
    assert nlu_reasoning_effort() == "low"
    monkeypatch.setenv("BOT_NLU_REASONING_EFFORT", "HIGH")
    assert nlu_reasoning_effort() == "high"
    monkeypatch.setenv("BOT_NLU_REASONING_EFFORT", "banana")
    assert nlu_reasoning_effort() == "low"
    assert _supports_reasoning_effort("gpt-5.6-luna")
    assert not _supports_reasoning_effort("gpt-4o-mini")


def test_complete_chat_keeps_strict_schema_and_timeout():
    source = inspect.getsource(_complete_chat)
    assert "strict" in source
    assert "json_schema" in source
    assert "reasoning_effort" in source
    assert "NLU_TIMEOUT_SEC" in source
    assert NLU_JSON_SCHEMA["type"] == "object"


class _FakeMessage:
    content = '{"schema_version":"2.0","action":"unknown"}'


class _FakeChoice:
    message = _FakeMessage()


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7
    completion_tokens_details = type("D", (), {"reasoning_tokens": 3})()


class _FakeResponse:
    choices = [_FakeChoice()]
    usage = _FakeUsage()


def test_complete_chat_passes_reasoning_only_for_luna(monkeypatch):
    captured = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.clear()
            captured.update(kwargs)
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, api_key=None):
            self.chat = type("C", (), {"completions": _FakeCompletions()})()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("BOT_NLU_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("BOT_NLU_REASONING_EFFORT", "low")
    with patch("openai.AsyncOpenAI", _FakeClient):
        text = asyncio.run(_complete_chat([{"role": "user", "content": "{}"}]))
    assert text.startswith("{")
    assert captured["model"] == "gpt-5.6-luna"
    assert captured["reasoning_effort"] == "low"
    assert captured["timeout"] == 8.0
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert LAST_NLU_CALL["prompt_tokens"] == 11
    assert LAST_NLU_CALL["reasoning_tokens"] == 3

    captured.clear()
    monkeypatch.setenv("BOT_NLU_MODEL", "gpt-4o-mini")
    with patch("openai.AsyncOpenAI", _FakeClient):
        asyncio.run(_complete_chat([{"role": "user", "content": "{}"}]))
    assert captured["model"] == "gpt-4o-mini"
    assert "reasoning_effort" not in captured


def test_webhook_gpt_timeout_does_not_create_repair_draft(monkeypatch):
    monkeypatch.setenv("BOT_NLU_DISABLE", "0")
    uid, cid = "nlu-model-to", "nlu-model-ch"
    set_mode(uid, cid, MODE_REPAIR)
    before = _repair_count()

    async def _timeout(_messages):
        raise TimeoutError("nlu timeout")

    nw = AsyncMock()
    nw.send_text_message = AsyncMock()

    async def _run():
        with patch(
            "backend.app.api.naver_works_webhook.get_naver_works_client",
            return_value=nw,
        ), patch("backend.app.services.bot_nlu._complete_chat", _timeout):
            await process_message(uid, cid, "그냥 그거", "group", "장지훈")

    asyncio.run(_run())
    assert get_mode(uid, cid) == MODE_REPAIR
    assert _repair_count() == before
    draft = (get_conversation_manager().get_state(uid, cid) or {}).get("pending_data") or {}
    assert draft.get("entry_type") != "repair" or not draft.get("work_type")
    assert LAST_NLU_CALL.get("fallback") is True
    assert LAST_NLU_CALL.get("error") == "TimeoutError"
